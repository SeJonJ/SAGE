#!/usr/bin/env python3
"""Windows capability 판정이 **어느 관문에서 갈렸는지** 찍는다.

`probe_capability` 는 어느 관문에서 멈추든 같은 `uninstall.unsafe_platform` 하나를 낸다.
사용자에게는 그것이 옳다 — 왜 안 되는지가 아니라 무엇을 하면 되는지가 필요하다. 그런데
**CI 로그에서도** 그 하나만 보이면, 지원해야 할 환경이 거부로 떨어졌을 때 원인을 알 방법이
없다. 그 환경은 원격에만 있고, 실패한 job 은 그 환경을 들고 있는 유일한 자리다.

그래서 같은 관문들을 순서대로 다시 밟으며 각 단계의 실측값을 낸다. 판정하지 않고 보고만
하므로 **항상 exit 0** 이다 — 이 스크립트가 job 을 붉게 만들면 진짜 실패가 가려진다.

출력은 ASCII 만 쓴다. Windows 러너 콘솔은 cp1252/cp949 로 열려 한글이 물음표로 뭉개진다.

## `--require-product-support` — 보고와 **다른 일**

보고만 하는 스크립트를 게이트로 쓰면 게이트가 없는 것과 같다. exit 0 은 "지원 범위 안이다" 가
아니라 "찍었다" 이고, 둘은 화면에서 구별되지 않는다. Windows 11 전용 job 은 배정된 러너가
정말 그 환경인지를 **제거를 시작하기 전에** 확정해야 하므로, 이 플래그가 같은 판정을 한 번 더
읽어 fail-closed 로 막는다. 근거는 제품이 스스로 내리는 값(`support_policy` · `capability`)이고,
CI 전용 버전·build·filesystem 판정표를 여기에 새로 만들지 않는다 — 표가 둘이 되는 순간 제품이
거부하는 환경에서 CI 만 통과하는 자리가 생긴다.
"""
import os
import platform
import sys
import tempfile

# 이 파일은 `<repo>/scripts/ci/` 에 있다. `dirname` 을 **두 번**만 하면 `<repo>/scripts` 가
# 나오고, 그 값으로 계산한 fixture base 는 실제 검사가 쓰는 자리와 한 칸 어긋난다 — 게이트가
# 엉뚱한 볼륨을 재고 통과하면 그 통과는 아무것도 말하지 않는다. 실제로 그렇게 어긋나 있었다.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)


def gate_roots():
    """게이트가 재는 자리는 **검사가 실제로 건드릴 자리**여야 한다.

    그래서 자리를 여기서 다시 계산하지 않고 `uninstall_smoke.fixture_base()` 를 그대로
    부른다. 규칙을 두 군데 적으면 한쪽만 고쳐지는 날이 오고, 어긋난 쪽이 게이트라면 그
    게이트는 통과하면서 아무것도 지키지 않는다.

    저장소·temp 는 재지 않는다. 실제 mutation 은 fixture base 아래에서만 일어나므로, 다른
    자리를 함께 재면 게이트가 무엇을 보장했는지가 흐려진다.
    """
    from uninstall_smoke import fixture_base
    return [fixture_base()]


def product_support_gate():
    """지원 범위 안인가를 **제품의 판정으로** 확정한다. `(problems, evidence)`.

    여기서 하나라도 어긋나면 uninstall 검사를 돌리지 않는다. 범위 밖 러너에서 나온 초록은
    Windows 11 데스크톱 증거가 아닌데, 로그만 보면 같은 초록이다.
    """
    evidence = {}
    if os.name != "nt":
        return ["this gate only runs on Windows"], evidence

    from sage import uninstall_fs as _fs
    from sage import uninstall_windows_fs as w

    problems = []
    info = sys.getwindowsversion()
    kinds = {1: "workstation", 2: "domain-controller", 3: "server"}
    product_type = getattr(info, "product_type", 0)
    evidence["edition"] = platform.win32_edition()
    evidence["build"] = f"{info.major}.{info.minor}.{info.build}"
    evidence["product_type"] = kinds.get(product_type, "unknown")
    # **아키텍처 판정은 제품의 것이다.** CI 가 자기 비교를 하나 더 들면 제품이 실행하는
    # 환경과 CI 가 증거를 만드는 환경이 갈리고, 갈린 뒤에는 어느 쪽이 옳은지 물을 자리가
    # 없다. 값은 증거로 남기되 **판정은 `native_floor` 와 `capability.supported` 가 낸다.**
    evidence["machine"] = w.process_architecture()
    evidence["process_bits"] = w.process_bits()
    evidence["native_floor"] = w.native_floor()

    # SKU·build 판정의 상수는 **제품의 것**을 읽는다. 여기에 숫자를 다시 적으면 지원 범위를
    # 옮기는 날 한쪽만 옮겨지고, 어긋난 쪽이 CI 라면 아무도 모른다.
    if product_type != w.VER_NT_WORKSTATION:
        problems.append(f"product_type={evidence['product_type']} (want workstation)")
    if info.build < w.WINDOWS_11_MIN_BUILD:
        problems.append(f"build={info.build} is below the Windows 11 floor "
                        f"{w.WINDOWS_11_MIN_BUILD}")
    # 폭과 아키텍처는 **제품의 `native_floor` 가 이미 fail-closed 로 막는다.** 여기서는 그
    # 결과를 읽고, 어긋났을 때 사람이 원인을 되짚을 수 있도록 두 값을 함께 적는다.
    if not evidence["native_floor"]:
        problems.append(
            f"native_floor()=False (process_bits={evidence['process_bits']} want "
            f"{w.WIN64_POINTER_SIZE * 8}, machine={evidence['machine']!r} want "
            f"{w.WIN64_ARCHITECTURE!r}, build={evidence['build']})")

    policy = _fs.support_policy()
    evidence["support_policy"] = policy
    if policy:
        problems.append(f"support_policy()={policy} (want None)")

    # 로컬 NTFS 판정은 **제품이 이미 내린다** — `capability()` 안의 `local_ntfs` 가 볼륨과
    # 파일시스템을 함께 확정하고, 확정 실패는 언제나 거짓 쪽이다. 그래서 여기서 파일시스템
    # 이름 목록을 새로 들지 않고 그 결과를 읽는다. 이름은 증거로 남긴다.
    roots = gate_roots()
    evidence["gate_roots"] = roots
    cap = _fs.capability(tuple(roots))
    evidence["filesystem"] = cap.filesystem
    evidence["local_volume"] = cap.local_volume
    evidence["capability_supported"] = cap.supported
    evidence["capability_failure_code"] = cap.failure_code
    if not cap.local_volume:
        problems.append("capability.local_volume is not True (want a local volume)")
    if cap.supported is not True:
        problems.append(f"capability.supported={cap.supported} "
                        f"failure_code={cap.failure_code} (want True)")
    return problems, evidence


def require_product_support():
    print("== windows product-support gate (fail-closed) ==")
    problems, evidence = product_support_gate()
    for key in ("edition", "build", "product_type", "machine", "process_bits",
                "native_floor", "filesystem", "local_volume", "support_policy",
                "capability_supported", "capability_failure_code", "gate_roots"):
        if key in evidence:
            print(f"  {key}={evidence[key]}")
    if problems:
        for note in problems:
            print(f"  - {note}")
        print(f"FAIL: {len(problems)} product-support condition(s) not met -- "
              "uninstall checks must not run here")
        return 1
    print("  gate passed: this runner is inside the declared automatic-removal scope")
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if "--require-product-support" in argv:
        return require_product_support()
    print("== windows capability diagnostics ==")
    print(f"  platform={sys.platform} python={sys.version.split()[0]}")
    if os.name != "nt":
        print("  not applicable on this platform")
        return 0

    from sage import uninstall_windows_fs as w

    print(f"  is_windows={w._is_windows()}")
    # 두 축을 **따로** 낸다. `native_floor` 는 기술 바닥(이 진입점이 같은 모양인가),
    # `support_policy` 는 지원 범위 문구(이 SKU 를 지원한다고 말했는가)다. 하나로 접으면
    # 서버에서 backend 가 도는 사실과 제품이 실행을 거부하는 사실이 같은 줄에 뭉개진다.
    # **process bitness 를 함께 남긴다.** 구조체 배치가 Win64 ABI 하나를 전제하므로, 어떤
    # 폭에서 돌았는지가 로그에 없으면 "Windows 에서 통과했다" 가 어떤 Windows 인지 되짚을 수
    # 없다 — SKU 에서 한 번 겪은 일이 폭에서 반복된다.
    print(f"  process_bits={w.process_bits()} (win64 contract={w.WIN64_POINTER_SIZE * 8})")
    print(f"  native_floor={w.native_floor()}")
    print(f"  windows_release={w.windows_release()}")
    print(f"  support_policy={w.support_policy() or 'automatic removal supported'}")
    # **edition·build·filesystem 을 함께 남긴다.** 어느 SKU 에서 돌았는지가 로그에 없으면
    # "Windows 에서 통과했다" 가 어떤 Windows 인지 아무도 되짚을 수 없다. 실제로 Server 2025
    # 증거를 데스크톱 증거로 읽을 뻔했다.
    try:
        info = sys.getwindowsversion()
        kinds = {1: "workstation", 2: "domain-controller", 3: "server"}
        print(f"  getwindowsversion={tuple(info)}")
        print(f"  build={info.major}.{info.minor}.{info.build} "
              f"product_type={kinds.get(getattr(info, 'product_type', 0), 'unknown')} "
              f"service_pack={info.service_pack!r}")
        print(f"  edition={platform.win32_edition()} "
              f"is_iot={platform.win32_is_iot()} release={platform.release()}")
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
    # **이 함수는 실제로 설치하고 제거한다.** 보고 스크립트 안에 있다는 이유로 무해해 보이지만
    # 여기서 일어나는 것은 native mutation 이다. 그래서 제품이 이 환경을 실행 대상으로 인정할
    # 때만 돈다 — 잘못 배정된 러너에서 게이트보다 먼저 이 함수가 돌면, 막으려던 mutation 이
    # 진단을 찍는 과정에서 그대로 일어난다.
    problems, _evidence = product_support_gate()
    if problems:
        print("      skipped: this environment is outside the declared support scope")
        for note in problems:
            print(f"      - {note}")
        return
    base = gate_roots()[0]
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

        # **새 소비자에서 돌린다.** 앞의 제거가 실패했으면 그 fixture 는 이미 손상돼 있고,
        # 손상된 자리에서 남은 몇 개를 처리한 성공은 "깨끗한 제거가 된다" 는 증거가 아니다.
        # 실제로 그렇게 읽어서 한 번 잘못 판단했다.
        sentinel = os.path.join(root, "outside", "sentinel.txt")
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        with open(sentinel, "w", encoding="utf-8") as fp:
            fp.write("untouched\n")
        second = os.path.join(root, "proj2")
        os.makedirs(second)
        again = sage("install", "--host", "claude", "--dest", second)
        print(f"      second install rc={again.returncode}")
        probe = subprocess.run(
            [sys.executable, "-c", CHILD_PROBE, second, sentinel], cwd=REPO, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("      --- same-env child probe (executor level)")
        for line in (probe.stdout or "").strip().splitlines():
            print(f"      {line}")
        if probe.returncode != 0:
            print(f"      child rc={probe.returncode} stderr: {probe.stderr[-1500:]}")
        # 열린 handle 잔여의 대리 관측. Windows 에서 자식 안의 handle 이 살아 있으면 이
        # 삭제가 공유 위반으로 실패한다. 직접 세는 방법이 없으므로 대리임을 명시한다.
        try:
            shutil.rmtree(second)
            print("      handle residue (proxy: rmtree of project) = none")
        except OSError:
            print("      handle residue (proxy: rmtree of project) = BLOCKED")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
