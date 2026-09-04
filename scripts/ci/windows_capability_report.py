#!/usr/bin/env python3
"""Windows capability 판정이 **어느 관문에서 갈렸는지** 찍는다.

`probe_capability` 는 어느 관문에서 멈추든 같은 `uninstall.unsafe_platform` 하나를 낸다.
사용자에게는 그것이 옳다 — 왜 안 되는지가 아니라 무엇을 하면 되는지가 필요하다. 그런데
**CI 로그에서도** 그 하나만 보이면, 지원해야 할 환경이 거부로 떨어졌을 때 원인을 알 방법이
없다. 그 환경은 원격에만 있고, 실패한 job 은 그 환경을 들고 있는 유일한 자리다.

그래서 같은 관문들을 순서대로 다시 밟으며 각 단계의 실측값을 낸다. 판정하지 않고 보고만
하므로 **항상 exit 0** 이다 — 이 스크립트가 job 을 붉게 만들면 진짜 실패가 가려진다.

출력은 ASCII 만 쓴다. Windows 러너 콘솔은 cp1252/cp949 로 열려 한글이 물음표로 뭉개진다.
"""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def main():
    print("== windows capability diagnostics ==")
    print(f"  platform={sys.platform} python={sys.version.split()[0]}")
    if os.name != "nt":
        print("  not applicable on this platform")
        return 0

    from sage import uninstall_windows_fs as w

    print(f"  is_windows={w._is_windows()}")
    print(f"  windows_10_or_later={w._windows_10_or_later()}")
    try:
        print(f"  getwindowsversion={tuple(sys.getwindowsversion())}")
    except Exception as exc:                                   # noqa: BLE001
        print(f"  getwindowsversion raised: {exc!r}")

    api = w._Api.get()
    for name in ("NtCreateFile", "SetFileInformationByHandle",
                 "GetVolumeInformationByHandleW", "GetFileInformationByHandleEx"):
        print(f"  api.{name}={bool(getattr(api, name, None))}")

    roots = [os.path.join(REPO, "."), tempfile.gettempdir()]
    for root in roots:
        report_root(w, os.path.abspath(root))

    from sage import uninstall_fs as _fs
    cap = _fs.capability(tuple(os.path.abspath(r) for r in roots))
    print(f"  capability supported={cap.supported} backend={cap.backend} "
          f"failure_code={cap.failure_code} filesystem={cap.filesystem} "
          f"local_volume={cap.local_volume} identity_source={cap.identity_source}")
    print(f"  primitives={cap.primitives}")
    real_run()
    return 0


# 실패한 명령과 **같은 프로세스 조건**에서 판정을 다시 낸다. 부모에서 참이 나오는 판정이
# 자식에서 거짓이면 원인은 경로가 아니라 프로세스에 있다.
CHILD_PROBE = r"""
import hashlib, os, stat, sys
sys.path.insert(0, os.environ["SAGE_REPO"])
from sage import uninstall_plan as p, uninstall_fs as f
project = sys.argv[1]
sentinel = sys.argv[2]

def snapshot(root):
    seen = {}
    for base, dirs, names in os.walk(root):
        for name in sorted(names):
            full = os.path.join(base, name)
            rel = os.path.relpath(full, root)
            info = os.lstat(full)
            with open(full, "rb") as fp:
                digest = hashlib.sha256(fp.read()).hexdigest()
            seen[rel] = (digest, stat.S_IMODE(info.st_mode))
    return seen

def backups(root):
    return sorted(os.path.relpath(os.path.join(b, n), root)
                  for b, dirs, names in os.walk(root)
                  for n in list(dirs) + list(names)
                  if n.startswith(".sage-install-backup-"))

before = snapshot(project)
sentinel_before = snapshot(os.path.dirname(sentinel))
plan = p.build(project, p.SCOPE_PROJECT)
roots = plan.lock_roots()
cap = f.capability(roots)
print("child capability supported=%s failure_code=%s source=%s"
      % (cap.supported, cap.failure_code, cap.identity_source))

# **전파된 terminal 실패 하나만 센다.** 하강 중의 부재·not-directory 는 정상 제어 흐름이라
# 수백 건 나오고, 그것을 전부 찍으면 진짜 실패가 그 안에 묻힌다.
from sage import uninstall_executor as ex

# 어느 rename 에서 갈리는지 **경로 없이** 센다. fixture 로는 열 칸이 다 통과하는데 실제
# 실행만 실패하므로, 실패한 시도의 성격(몇 번째인지·깊이·디렉터리인지·이름 길이)이 남은
# 유일한 판별축이다. 이름 자체는 싣지 않는다.
attempts = []
failures = []
original_replace = ex._PinnedTransaction._replace
def counted(self, source, target):
    rel = os.path.relpath(source, project)
    parents = getattr(self.backend, "parents", {})
    shape = {"n": len(attempts) + 1,
             "depth": len(rel.split(os.sep)),
             "is_dir": os.path.isdir(source),
             "name_len": len(os.path.basename(source)),
             "backup_len": len(os.path.basename(target)),
             "hidden": os.path.basename(source).startswith("."),
             # 이 대상 자체를 우리가 **부모로 붙들고 있는가.** 붙든 디렉터리를 옮기는 것과
             # 그렇지 않은 것은 Windows 에서 다른 조작이다.
             "is_pinned_parent": os.path.abspath(source) in parents,
             # 되돌리는 방향인가. backup 이름이 원래 이름보다 짧으면 복원 쪽이다.
             "restoring": os.path.basename(source).startswith(".sage-install-backup-")}
    attempts.append(shape)
    try:
        return original_replace(self, source, target)
    except BaseException as exc:
        shape["failed"] = getattr(exc, "diagnostic", None) or type(exc).__name__
        shape["native"] = getattr(exc, "native", None) or {
            "operation": getattr(exc, "op", None), "error_code": getattr(exc, "code", None)}
        failures.append(shape)
        raise
ex._PinnedTransaction._replace = counted

trace = []
outcome = None
try:
    result = ex.execute(plan, trace=trace)
    outcome = "ok removed=%d leftover_backups=%r" % (len(result.processed),
                                                     result.leftover_backups)
except f.NativeFailure as exc:
    outcome = "NativeFailure %s native=%r" % (exc, exc.native)
except BaseException as exc:
    outcome = "%s: %s" % (type(exc).__name__, exc)
print("child execute=%s" % outcome)
print("child trace_tail=%r" % (trace[-4:],))
print("child rename_attempts=%d failures=%d" % (len(attempts), len(failures)))
for shape in failures:
    print("child rename_FAILED=%r" % (shape,))
forward = [a for a in attempts if not a["restoring"]]
print("child rename_forward_ok=%d of %d" % (
    len([a for a in forward if "failed" not in a]), len(forward)))

failed = not outcome.startswith("ok")
if failed:
    # mutation 이후 실패였다면 되돌리기가 실제로 섰는지부터 증명한다.
    after = snapshot(project)
    print("child rollback bytes_and_mode_identical=%s" % (after == before))
    if after != before:
        changed = sorted(set(after) ^ set(before)) or [
            k for k in before if before[k] != after.get(k)]
        print("child rollback changed_count=%d" % len(changed))
    print("child rollback outside_sentinel_unchanged=%s"
          % (snapshot(os.path.dirname(sentinel)) == sentinel_before))
    print("child rollback backup_residue=%d" % len(backups(project)))
    print("child rollback status_not_mistaken_for_success=%s" % True)
else:
    print("child rollback backup_residue=%d" % len(backups(project)))
    print("child outside_sentinel_unchanged=%s"
          % (snapshot(os.path.dirname(sentinel)) == sentinel_before))
"""


def report_root(w, root):
    """root 하나의 관문별 실측값. **실제 실행이 쓰는 바로 그 경로**로도 불러야 한다.

    임의의 디렉터리로만 확인하면 "이 머신은 지원된다" 까지만 알 수 있다. 거부가 난 자리는
    그 머신의 **그 경로**이고, 둘이 다를 수 있다는 것이 이번에 실제로 드러난 사실이다.
    """
    print(f"  --- root {root}")
    try:
        handle = w._open_root(root)
    except Exception as exc:                                   # noqa: BLE001
        print(f"      _open_root raised: {type(exc).__name__}: {exc}")
        return
    try:
        try:
            ok, filesystem, local = w.local_ntfs(handle)
            print(f"      local_ntfs ok={ok} filesystem={filesystem!r} local={local}")
        except Exception as exc:                               # noqa: BLE001
            print(f"      local_ntfs raised: {type(exc).__name__}: {exc}")
        try:
            attributes, tag = w._tag_info(handle)
            print(f"      attributes=0x{attributes:08x} reparse_tag=0x{tag:08x} "
                  f"is_reparse={bool(attributes & w.FILE_ATTRIBUTE_REPARSE_POINT)}")
        except Exception as exc:                               # noqa: BLE001
            print(f"      _tag_info raised: {type(exc).__name__}: {exc}")
            attributes = None
        info = os.stat(root)
        print(f"      os.stat mode=0o{w._stat_mode(info):o} "
              f"st_dev={info.st_dev} st_ino={info.st_ino}")
        # **여기가 가장 자주 갈리는 자리다.** 어느 source 도 `os.stat` 과 맞지 않으면
        # 지원 환경이 거부로 떨어지고, 그 어긋남은 안전하지만 원인이 보이지 않는다.
        for source in w.IDENTITY_SOURCES:
            try:
                derived = w.identity(handle, source=source)
                mode = w._mode_of(attributes) if attributes is not None else None
                anchor = (w._stat_mode(info), info.st_dev, info.st_ino)
                print(f"      identity[{source}] = {(mode,) + derived} "
                      f"anchor = {anchor} match={((mode,) + derived) == anchor}")
            except Exception as exc:                           # noqa: BLE001
                print(f"      identity[{source}] raised: {type(exc).__name__}: {exc}")
        try:
            names = w._entries(handle)
            print(f"      _entries ok, {len(names)} names")
        except Exception as exc:                               # noqa: BLE001
            print(f"      _entries raised: {type(exc).__name__}: {exc}")
    finally:
        w._close(handle)


def real_run():
    """실제 소비자를 하나 만들어 제거까지 돌리고 **기계가 읽는 결과**를 낸다.

    capability 가 참인데도 smoke 가 `BLOCKED` 로 죽으면 원인은 그 뒤에 있다. 사람용 출력은
    `blocked_reason` 을 문장으로 풀어 쓰므로 어느 코드인지 되짚을 수 없고, Windows 콘솔
    인코딩까지 겹치면 그마저 읽히지 않는다. `--json` 은 코드를 그대로 들고 있다.
    """
    import json
    import shutil
    import subprocess

    print("  --- real install/uninstall (json)")
    base = os.path.join(os.path.dirname(REPO), ".sage-fixtures")
    os.makedirs(base, exist_ok=True)
    root = os.path.realpath(tempfile.mkdtemp(prefix="capability-report-", dir=base))
    project = os.path.join(root, "proj")
    codex_home = os.path.join(root, "codex")
    os.makedirs(project)
    os.makedirs(codex_home)
    env = os.environ.copy()
    env["CODEX_HOME"] = codex_home
    env["SAGE_REPO"] = REPO

    def sage(*args):
        return subprocess.run([sys.executable, "-m", "sage", *args], cwd=REPO, env=env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")

    try:
        installed = sage("install", "--host", "claude", "--dest", project)
        print(f"      install rc={installed.returncode}")
        if installed.returncode != 0:
            print(f"      install stderr: {installed.stderr[-800:]}")
            return
        # **실행이 실제로 쓰는 root 로 다시 판정한다.** 위의 임의 디렉터리 판정이 참이어도
        # 이 경로에서 거짓이면 거부가 난다 — 그 둘을 같은 것으로 보면 원인이 보이지 않는다.
        from sage import uninstall_fs as _fs
        from sage import uninstall_plan as _plan
        from sage import uninstall_windows_fs as w
        plan = _plan.build(project, _plan.SCOPE_PROJECT)
        lock_roots = plan.lock_roots()
        print(f"      plan.status={plan.status!r} lock_roots={lock_roots}")
        for root in lock_roots:
            report_root(w, os.path.abspath(root))
        cap = _fs.capability(lock_roots)
        print(f"      capability(lock_roots) supported={cap.supported} "
              f"failure_code={cap.failure_code} filesystem={cap.filesystem} "
              f"local_volume={cap.local_volume} identity_source={cap.identity_source}")
        print(f"      primitives={cap.primitives}")

        # **거부는 `sage` 프로세스 안에서 났다.** 부모 프로세스에서 참이 나오는 판정이
        # 자식에서 거짓이면, 갈리는 것은 경로가 아니라 그 프로세스의 무엇이다. 그래서
        # 같은 env·같은 cwd 의 자식에서 똑같은 두 줄을 찍어 본다.
        removed = sage("uninstall", "--dest", project, "--yes", "--json")
        print(f"      uninstall rc={removed.returncode}")
        try:
            payload = json.loads(removed.stdout)
        except ValueError:
            print(f"      stdout was not json: {removed.stdout[-1200:]}")
            print(f"      stderr: {removed.stderr[-800:]}")
            return
        for key in ("scope", "status", "exit_code", "executed", "blocked_reason"):
            print(f"      {key}={payload.get(key)!r}")
        for key in ("notices", "detail", "manual", "basis", "rollback_reasons",
                    "preserved_paths", "leftover_backups"):
            if payload.get(key):
                print(f"      {key}={json.dumps(payload[key], ensure_ascii=True)[:900]}")

        # 거부는 아무것도 바꾸지 않았으므로 소비자는 그대로다. 같은 fixture 로 실행 층을
        # 직접 돌려, 진단 code 로 접히기 전의 native 실패를 이름과 정수로 붙잡는다.
        sentinel = os.path.join(root, "outside", "sentinel.txt")
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        with open(sentinel, "w", encoding="utf-8") as fp:
            fp.write("untouched\n")
        probe = subprocess.run(
            [sys.executable, "-c", CHILD_PROBE, project, sentinel], cwd=REPO, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("      --- same-env child probe (executor level)")
        for line in (probe.stdout or "").strip().splitlines():
            print(f"      {line}")
        if probe.returncode != 0:
            print(f"      child rc={probe.returncode} stderr: {probe.stderr[-1500:]}")
        # 열린 handle 잔여의 대리 관측. Windows 에서 자식 안의 handle 이 살아 있으면 이
        # 삭제가 공유 위반으로 실패한다. 직접 세는 방법이 없으므로 대리임을 명시한다.
        try:
            shutil.rmtree(project)
            print("      handle residue (proxy: rmtree of project) = none")
        except OSError:
            print("      handle residue (proxy: rmtree of project) = BLOCKED")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
