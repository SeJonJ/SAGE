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
import os, sys
sys.path.insert(0, os.environ["SAGE_REPO"])
from sage import uninstall_plan as p, uninstall_fs as f
project = sys.argv[1]
plan = p.build(project, p.SCOPE_PROJECT)
roots = plan.lock_roots()
print("child plan.status=%r global_root=%r" % (plan.status, plan.global_root))
print("child lock_roots=%r" % (roots,))
cap = f.capability(roots)
print("child capability supported=%s failure_code=%s filesystem=%s local=%s source=%s"
      % (cap.supported, cap.failure_code, cap.filesystem, cap.local_volume,
         cap.identity_source))
print("child os.name=%r frozen=%r" % (os.name, getattr(sys, "frozen", False)))
try:
    f.backend_for(roots).close()
    print("child backend_for=ok")
except Exception as exc:
    print("child backend_for raised %s: %s" % (type(exc).__name__, exc))

# capability 도 backend_for 도 참이면 거부는 **그 뒤 native 호출**에서 났다는 뜻이다.
# 실행 층은 `MutationBackendError` 를 진단 code 하나로 옮기며 `op:kind:code` 문자열을
# 버린다 — 그 문자열에는 경로가 없고 API 이름과 정수만 있는데도 어디에도 남지 않는다.
# 그래서 여기서 가로채 찍는다.
from sage import uninstall_executor as ex, uninstall_windows_fs as w
seen = []
original = w.WindowsMutationError.__init__
def spy(self, op, code, ntstatus=False):
    seen.append("%s:%s:%#x" % (op, "nt" if ntstatus else "win32", code))
    original(self, op, code, ntstatus=ntstatus)
w.WindowsMutationError.__init__ = spy
trace = []
try:
    result = ex.execute(plan, trace=trace)
    print("child execute=ok removed=%d" % len(result.processed))
except BaseException as exc:
    print("child execute raised %s: %s" % (type(exc).__name__, exc))
print("child native failures=%r" % (seen,))
print("child trace=%r" % (trace,))
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
        probe = subprocess.run(
            [sys.executable, "-c", CHILD_PROBE, project], cwd=REPO, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("      --- same-env child probe (executor level)")
        for line in (probe.stdout or "").strip().splitlines():
            print(f"      {line}")
        if probe.returncode != 0:
            print(f"      child rc={probe.returncode} stderr: {probe.stderr[-1500:]}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
