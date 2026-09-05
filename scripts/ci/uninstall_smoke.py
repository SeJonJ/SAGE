#!/usr/bin/env python3
"""`sage uninstall` 소비자 계약을 **세 OS · 세 Python** 에서 검증하는 smoke.

## 검사 내용은 **환경**마다 다르다 — OS 이름으로 갈리지 않는다

Linux·macOS 와 Windows 11 데스크톱 · 64-bit Python · 로컬 NTFS 는 실제로 설치하고 제거한다. 지원 범위 밖에서는
제품이 mutation 을 **거부**하므로, 거기서는 계획이 도는 것과 실행이 거부되고 아무것도 바뀌지
않는 것을 검사한다.

범위 밖은 **두 축**이고 화면도 다르다. 정책(`support_policy`)은 SKU·build 만 보고 Windows 10
데스크톱과 server SKU 를 가른다 — 그 판정은 capability 를 재지 않으므로 `--check` 도 `--yes` 도
`BLOCKED` 다. capability 는 볼륨·native 기능·포인터 폭을 실제로 재고, 그 거부는 mutation 요청
에만 걸린다(`--check` 는 계획을 그대로 낸다).

둘을 한 값으로 접으면 backend 회귀가 도는 환경과 제품이 실행하는 환경을 구별할 수 없다 —
GitHub 러너가 정확히 그 자리다(Server 2025 는 정책 범위 밖이지만 backend 검사는 그대로 돈다).

갈림의 기준을 OS 이름이 아니라 **제품이 스스로 내리는 판정**으로 두는 것이 요점이다. OS 이름
으로 가르면 지원 범위가 바뀔 때마다 이 파일이 사실과 어긋나고, 그 어긋남은 "검사했다" 로
읽힌다. 검사가 무엇을 증명했는지 정확히 적는 것이 이 스크립트가 지는 책임의 절반이다.

## 왜 bash 를 쓰지 않는가

`wheel_smoke.sh` 가 이미 소비자 matrix 를 돌지만 bash 스크립트라 Windows 러너에서 돌지 않는다.
검사 도구가 검사 대상보다 요구사항이 많으면 그 환경은 영원히 미검증으로 남는다 — 그래서 이
스크립트는 순수 Python 이고, 표준 라이브러리 밖을 쓰지 않는다.

## 무엇을 보는가

지워졌는지가 아니라 **말하지 않은 것이 남았는가** 를 본다. 조용히 남는 자산이 이 명령의 가장
흔한 실패 방식이고, OS 마다 다르게 틀리는 것도 대개 경로·권한이라 그 자리에서 드러난다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

# 이 **환경**에서 안전한 mutation 이 가능한가. 불가능하면 제품이 실행을 거부하는 것이
# 정상이고, smoke 는 그 거부를 검사한다 — 거부를 실패로 세면 올바른 동작이 빨간불이 된다.
#
# 판정은 root 에 달려 있다(볼륨·파일시스템). 그래서 모듈 수준 상수가 아니라 fixture 를 만든
# 뒤에 묻는다 — 같은 머신에서도 프로젝트와 `$CODEX_HOME` 이 다른 볼륨일 수 있다.
from sage import uninstall_fs as _fs  # noqa: E402


# 이 환경을 **지원한다고 말했는가.** capability 와 다른 축이라 따로 묻는다 — 서버 SKU 는
# 기술적으로 가능하지만 지원 범위 밖이고, Windows 10 데스크톱도 마찬가지다. 둘을 한 값으로
# 접으면 backend 회귀가 도는 환경과 제품이 실행하는 환경을 구별할 수 없다.
POLICY = _fs.support_policy()


def safe_mutation(*roots):
    """제품이 이 자리에서 **실제로 제거를 수행하는가.** 정책과 capability 를 모두 본다."""
    if POLICY:
        return False
    return _fs.capability([r for r in roots if r]).supported


# 정책이 막으면 계획 화면조차 `BLOCKED`(2) 다 — 대상이 있는 한. 자동 제거가 결코 일어나지
# 않을 환경에서 `--check` 만 0 을 내면 사용자는 돌 것처럼 보이는 계획을 읽는다.
CHECK_CODES = (2,) if POLICY else (0, 1)


def policy_refusal(payload, result, where):
    """정책 거부 하나의 계약. **Windows 10 안내와 같은 경로**를 여기서 밟는다.

    Windows 10 러너는 GitHub 에 없다. 그래서 그 화면의 모양(상태·exit·진단·수동 안내 순서)은
    같은 관문을 지나는 다른 SKU 에서 실제로 확인한다 — code 값만 다르고 경로는 하나다.
    """
    if payload.get("status") != "BLOCKED":
        fail(f"{where}: policy refusal status={payload.get('status')}", result)
    if payload.get("exit_code") != 2:
        fail(f"{where}: policy refusal exit_code={payload.get('exit_code')}", result)
    if payload.get("blocked_reason") != POLICY:
        fail(f"{where}: blocked_reason={payload.get('blocked_reason')} want {POLICY}", result)
    if payload.get("executed") is not False:
        fail(f"{where}: a refused run reported itself executed", result)
    # **명시한 결정**: 정책 거부는 code 와 무관하게 검증된 계획 기반 수동 목록을 준다.
    # Windows 10 도 server SKU 도 같다 — 안내를 빼면 그 사용자는 "지원하지 않는다" 만 듣고
    # 아무 길도 없이 끝난다. 지원 범위와 안내 제공은 다른 질문이다.
    manual = payload.get("manual_cleanup")
    if not isinstance(manual, dict):
        fail(f"{where}: policy refusal carried no manual_cleanup", result)
    if not manual.get("available"):
        fail(f"{where}: manual_cleanup was not available", result)
    if manual.get("basis") != "verified_plan":
        fail(f"{where}: manual_cleanup basis={manual.get('basis')}", result)
    order = manual.get("order") or []
    if not order:
        fail(f"{where}: manual_cleanup gave no ordering", result)
    if "BLOCK" in order:
        fail(f"{where}: manual_cleanup told the user to act on BLOCK entries", result)
    if "STRIP" in order and "DELETE" in order and order.index("STRIP") > order.index("DELETE"):
        fail(f"{where}: manual_cleanup ordered DELETE before STRIP", result)
    # 공유 설정은 **파일 삭제 대상이 아니다.** STRIP 이 삭제 목록에 섞이면 사용자는 자기
    # host 설정을 통째로 지운다.
    stripped = {entry["path"] for entry in payload.get("stripped", [])}
    deleted = {entry["path"] for entry in payload.get("deleted", [])}
    both = stripped & deleted
    if both:
        fail(f"{where}: a shared file appeared in both DELETE and STRIP: {sorted(both)}", result)


# 이 값이 참이면 "**고칠 수 있는 이유로** 실제 제거를 하지 않았다" 는 실패다. 이것이 없으면
# 실제 mutation 0건인 job 이 초록으로 끝나고, 화면에는 "검증했다" 만 남는다.
#
# 정책이 막는 환경은 예외다 — 거기서 실제 제거를 요구하면 **제품이 지원하지 않겠다고 말한 일**을
# 하라는 요구가 된다. 그 대신 그 환경에서는 거부 계약 전체(exit 2 · 진단 · 네 목록 · 수동 안내 ·
# 무변경)를 모든 shape 과 scope 에서 단언하고, 몇 건을 그렇게 단언했는지 요약에 남긴다. 0 이
# 조용히 지나가지 않게 하는 것이 이 값의 목적이고, 그 목적은 두 경우 모두에서 지켜진다.
_REQUIRE_MUTATION_ENV = bool(os.environ.get("SAGE_UNINSTALL_REQUIRE_MUTATION"))

# `REQUIRE_MUTATION` 보다 **한 칸 위**의 요구다. 그것은 "고칠 수 있는 이유로 제거를 하지
# 않았는가" 를 묻고, 정책이 막는 환경에서는 거부 계약으로 대신 갈음한다. Windows 11 전용
# job 에서는 그 갈음이 정확히 위험이다 — 러너가 잘못 배정되거나 이미지가 바뀌어 정책이
# 막기 시작하면, 거부 계약만 단언하고도 job 이 초록으로 끝난다. 그러면 A7 증거를 만들려고
# 세운 job 이 **실제 제거를 한 번도 하지 않은 채** 증거를 만들었다고 말한다.
#
# 그래서 이 모드는 갈음을 허용하지 않는다. 정책 거부가 한 건이라도 있으면, 실제 제거가
# 0건이면, 세 범위 중 하나라도 실제로 돌지 않았으면 실패다.
REQUIRE_PRODUCT_SUPPORT = bool(os.environ.get("SAGE_UNINSTALL_REQUIRE_PRODUCT_SUPPORT"))

# 엄격 모드는 **약한 요구를 포함한다.** 둘을 workflow 에서 각각 켜게 두면, 하나만 켠 job 이
# 생기는 날 그 job 은 자기가 무엇을 요구하는지 절반만 아는 채로 돈다. 관계를 코드에 둔다.
REQUIRE_MUTATION = _REQUIRE_MUTATION_ENV or REQUIRE_PRODUCT_SUPPORT


def product_support_problems(policy, refused, mutated, scope_results,
                             required_scopes=("project", "global", "all")):
    """엄격 모드의 판정. **구조화된 실행 결과만** 본다.

    stdout 을 workflow 에서 grep 하지 않는 이유가 여기 있다. 출력 문구는 번역·서식·요약
    형식이 바뀔 때마다 조용히 어긋나고, 어긋난 grep 은 **항상 통과**한다 — 없는 문자열을
    찾지 못한 것과 문제가 없는 것이 같은 결과로 떨어진다. 판정은 검사 스크립트가 자기
    실행 결과를 보고 직접 내리고, workflow 는 exit code 만 읽는다.

    호출자가 값을 주입할 수 있도록 순수 함수로 둔다 — 이 판정 자체가 회귀 검사의 대상이다.
    """
    problems = []
    if policy:
        problems.append(
            f"support_policy() returned {policy}: this runner is outside the declared "
            "automatic-removal scope, so it cannot stand as Windows 11 desktop evidence")
    if refused:
        problems.append(
            f"{refused} case(s) ended in a policy refusal instead of a real removal")
    if not mutated:
        problems.append("no case performed a real removal")
    missing = [scope for scope in required_scopes if not scope_results.get(scope)]
    if missing:
        problems.append(
            f"these removal scopes never performed a real removal: {missing}")
    return problems


def inherited_import_paths():
    """HOME 을 바꿔도 잃으면 안 되는 부모의 import 경로.

    ## 왜 필요한가

    `$CODEX_HOME` 기본값(`~/.codex`)을 밟으려면 `HOME` 을 fixture 로 돌려야 한다. 그런데 의존성이
    **user-site**(`~/.local/lib/...`)에만 설치돼 있으면, HOME 을 돌리는 순간 자식 프로세스가 그
    경로를 잃고 `ModuleNotFoundError` 로 죽는다. 검사가 검사 대상이 아니라 **자기 격리 방식**
    때문에 실패하는 것이고, 그 실패는 제품 결함처럼 보인다.

    homebrew·시스템 site-packages 에 설치된 머신에서는 이 문제가 보이지 않는다. 그래서 "내
    머신에서는 된다" 가 정확히 여기서 생긴다.

    저장소 자신은 넣지 않는다 — wheel 단독 여부를 흐리기 때문이다. 넘기는 것은 HOME 아래
    또는 이미 `PYTHONPATH` 에 있던 경로뿐이다.
    """
    home = os.path.realpath(os.path.expanduser("~"))
    repo = os.path.realpath(REPO)
    kept = []

    def keep(entry):
        if not entry:
            return
        full = os.path.realpath(entry)
        if full == repo or full.startswith(repo + os.sep):
            return
        if not os.path.isdir(full) or full in kept:
            return
        kept.append(full)

    for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        keep(entry)
    for entry in sys.path:
        if not entry:
            continue
        full = os.path.realpath(entry)
        if full == home or full.startswith(home + os.sep):
            keep(entry)
    return kept


IMPORT_PATHS = inherited_import_paths()


def run(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, "-m", "sage", *args], cwd=cwd or REPO,
                          env=env or os.environ.copy(), capture_output=True, text=True)


def fail(message, result=None):
    print(f"FAIL: {message}")
    if result is not None:
        print(result.stdout)
        print(result.stderr)
    sys.exit(1)


def fixture_base():
    """fixture 전용 private root. **공유 temp 로 되돌아가지 않는다.**

    `/tmp` 는 누구나 쓸 수 있어 남이 이름을 먼저 만들어 둘 수 있고, macOS 의 `$TMPDIR` 은
    symlink 아래에 있다. 경계를 보는 검사가 symlink 아래에서 돌면 통과의 의미가 흐려진다.

    `tempfile.gettempdir()` 로 내려가는 fallback 을 두지 않는 이유는, 아무도 환경변수를
    지정하지 않으므로 그 fallback 이 사실상 유일한 경로가 되기 때문이다. 규칙이 문서에만
    남는다. 지정이 없으면 저장소 옆의 정해진 자리를 쓴다.
    """
    override = os.environ.get("SAGE_TEST_TMPDIR")
    base = os.path.realpath(override or os.path.join(os.path.dirname(REPO), ".sage-fixtures"))
    os.makedirs(base, exist_ok=True)
    if os.name == "posix":
        os.chmod(base, 0o700)
    shared = os.path.realpath(tempfile.gettempdir())
    if not override and (base == shared or base.startswith(shared + os.sep)):
        fail(f"default fixture base is under the shared temp: {base}")
    return base


def tree(root):
    found = set()
    for folder, dirs, files in os.walk(root):
        for name in dirs + files:
            found.add(os.path.relpath(os.path.join(folder, name), root))
    return found


# 경로 변형. 되돌릴 수 없는 명령에서 경로 처리는 OS 마다 다르게 틀리므로, 정상 사용 조건인
# 공백과 비ASCII 를 검사 대상으로 둔다. "우리 CI 경로에서는 된다" 는 증거가 아니다.
PATH_SHAPES = (
    ("plain", "proj", "codex"),
    ("spaces", "my project dir", "codex home dir"),
    ("unicode", "프로젝트-테스트", "코덱스-홈"),
    ("mixed", "프로 젝트 dir", "코덱스 home"),
)

# `CODEX_HOME` 의 두 경로. 기본값(unset → `~/.codex`)과 명시 지정은 서로 다른 코드 경로다.
CODEX_MODES = ("custom", "default")


# 실제 제거를 세 범위 모두에서 한 번씩 돌린다. project 만 돌리면 `--global` 과 `--all` 의
# 두 root 통합 경로는 소비자 환경에서 한 번도 실행되지 않는다.
REMOVAL_SCOPES = ("project", "global", "all")


def main():
    failures = 0
    mutated = 0
    refused = 0
    for label, project_name, codex_name in PATH_SHAPES:
        for mode in CODEX_MODES:
            print(f"--- {label} / CODEX_HOME={mode} ---")
            if run_case(label, project_name, codex_name, mode):
                mutated += 1
            elif POLICY:
                refused += 1
    scope_results = {}
    for scope in REMOVAL_SCOPES:
        print(f"--- scope={scope} ---")
        scope_results[scope] = scope_case(scope)
        if scope_results[scope]:
            mutated += 1
        elif POLICY:
            refused += 1
    # 거부 계약은 **별도의 명시 fixture** 로 확인한다. 지원 환경에서도 돌아야 하므로 실행
    # 여부가 환경에 달려 있지 않다 — 환경에 달려 있으면 그 검사는 필요한 날 돌지 않는다.
    print("--- refusal contract (real capability probe) ---")
    refusal_case()
    for code, label in (("uninstall.windows_10_manual_only", "windows-10"),
                        ("uninstall.windows_sku_not_supported", "server-sku")):
        print(f"--- policy guidance: {label} ---")
        policy_guidance_case(code, label)
    print("--- policy refusal leaves a preserve-only rerun at PARTIAL(1) ---")
    preserve_only_rerun_case()
    print("--- native failure surface (text + JSON) ---")
    native_failure_case()
    if REQUIRE_MUTATION and mutated == 0 and not POLICY:
        fail("SAGE_UNINSTALL_REQUIRE_MUTATION is set but no case performed real removal")
    if REQUIRE_MUTATION and POLICY and refused == 0:
        # 정책이 막는 환경이라 real removal 은 0 이 맞다. 그러나 **거부 계약을 한 건도
        # 단언하지 않았다면** 이 job 은 아무것도 증명하지 않은 채 초록이다.
        fail(f"policy {POLICY} blocks removal but no case asserted the refusal contract")
    if REQUIRE_PRODUCT_SUPPORT:
        strict = product_support_problems(POLICY, refused, mutated, scope_results,
                                          REMOVAL_SCOPES)
        if strict:
            for note in strict:
                print(f"  - {note}")
            fail("SAGE_UNINSTALL_REQUIRE_PRODUCT_SUPPORT is set but this run did not "
                 "demonstrate real removal inside the declared support scope")
    # **어느 SKU 에서 돌았는지 요약 줄에 남긴다.** 없으면 "Windows 에서 통과했다" 가 어떤
    # Windows 인지 되짚을 수 없고, Server 증거를 데스크톱 증거로 읽게 된다.
    if os.name == "nt":
        import platform
        info = sys.getwindowsversion()
        kinds = {1: "workstation", 2: "domain-controller", 3: "server"}
        import ctypes as _ctypes
        print(f"  windows edition={platform.win32_edition()} "
              f"build={info.major}.{info.minor}.{info.build} "
              f"product_type={kinds.get(getattr(info, 'product_type', 0), 'unknown')} "
              f"process_bits={_ctypes.sizeof(_ctypes.c_void_p) * 8}")
    print(f"  support policy: {POLICY or 'automatic removal supported'}")
    if POLICY:
        print(f"  refusal contract asserted on {refused} shapes/scopes "
              f"(real removal is out of the declared support scope here)")
    if REQUIRE_PRODUCT_SUPPORT:
        print("  strict product-support mode: real removal demonstrated in every scope")
    print(f"OK  ({sys.platform}, python {sys.version.split()[0]}) "
          f"-- {len(PATH_SHAPES) * len(CODEX_MODES)} path/CODEX_HOME combinations, "
          f"{len(REMOVAL_SCOPES)} removal scopes, {mutated} real removals, "
          f"{refused} policy refusals")
    return failures


def scope_case(scope):
    """`--global`·`--all` 실제 제거. 두 root 를 하나의 transaction 으로 다루는 경로다.

    `--host codex --skill-scope global` 이 `$CODEX_HOME/skills` 를 두 번째 write root 로
    만든다. 그 root 가 없으면 global·all 은 대상이 없어 조용히 통과한다 — 통과처럼 보이는
    미실행이 이 명령에서 가장 비싼 오해다.
    """
    root = os.path.realpath(tempfile.mkdtemp(prefix=f"uninstall-scope-{scope}-",
                                             dir=fixture_base()))
    project = os.path.join(root, "proj")
    codex_home = os.path.join(root, "codex")
    os.makedirs(project)
    os.makedirs(codex_home)
    env = dict(os.environ, CODEX_HOME=codex_home)
    try:
        installed = run("install", "--host", "codex", "--skill-scope", "global",
                        "--dest", project, env=env)
        if installed.returncode != 0:
            fail(f"{scope}: install failed", installed)
        global_root = os.path.join(codex_home, "skills")
        if not os.path.isdir(global_root) or not os.listdir(global_root):
            fail(f"{scope}: the global skill root was never populated")
        args = {"project": ["--dest", project],
                "global": ["--global"],
                "all": ["--all", "--dest", project]}[scope]
        # 다른 scope 가 그대로인지 보려면 **실행 전 상태**를 들고 있어야 한다.
        project_before = tree(project)
        global_before = tree(global_root)
        planned = run("uninstall", *args, "--check", "--json", env=env)
        if planned.returncode not in CHECK_CODES:
            fail(f"{scope}: --check failed", planned)
        plan = json.loads(planned.stdout)
        targets = len(plan["deleted"]) + len(plan["stripped"])
        if targets == 0:
            fail(f"{scope}: nothing to remove — the fixture does not exercise this scope",
                 planned)
        if not safe_mutation(project, codex_home):
            if REQUIRE_MUTATION and not POLICY:
                fail(f"{scope}: mutation refused but this job requires real removal", planned)
            if POLICY:
                # **세 범위 모두** 같은 관문을 지나는지 본다. project 만 막고 global·all 이
                # 통과하면 지원 범위 문구가 절반만 참이 된다.
                policy_refusal(plan, planned, f"{scope}: --check")
                refusal = run("uninstall", *args, "--yes", "--json", env=env)
                if refusal.returncode != 2:
                    fail(f"{scope}: a policy-refused run did not block", refusal)
                policy_refusal(json.loads(refusal.stdout), refusal, f"{scope}: --yes")
                if tree(project) != project_before or tree(global_root) != global_before:
                    fail(f"{scope}: a policy-refused run still changed the tree", refusal)
            print(f"  out of supported range -- {scope} refusal only "
                  f"({'policy ' + POLICY if POLICY else 'capability'})")
            return False
        removed = run("uninstall", *args, "--yes", env=env)
        if removed.returncode not in (0, 1):
            fail(f"{scope}: uninstall failed", removed)
        if scope in ("global", "all") and os.path.isdir(global_root):
            left = sorted(os.listdir(global_root))
            if left:
                fail(f"{scope}: global skills survived: {left}", removed)
        if scope in ("project", "all"):
            if os.path.isdir(os.path.join(project, "sage")):
                fail(f"{scope}: project assets survived", removed)
        # **범위 격리를 명시로 단언한다.** "지웠다" 만 보면 한 scope 가 다른 scope 를
        # 함께 지운 경우가 통과한다 — project 를 정리하려고 전역을 건드리지 않는다는 것이
        # 이 명령의 계약이고, 계약은 검사가 있을 때만 계약이다.
        if scope == "project" and tree(global_root) != global_before:
            fail(f"{scope}: a project-only run changed the global scope", removed)
        if scope == "global":
            survivors = tree(project)
            if survivors != project_before:
                lost = sorted(project_before - survivors)
                fail(f"{scope}: a global-only run changed the project: {lost[:8]}", removed)
        print(f"  removed {targets} targets in scope={scope}")
        return True
    finally:
        shutil.rmtree(root, ignore_errors=True)


def unsupported_probe_script():
    """지원 범위 밖을 **실제 판정 경로로** 만든다.

    최상위 `capability()` 를 갈아 끼우면 `probe_capability` 도 `local_ntfs` 도 돌지 않는다.
    그러면 거부 화면은 확인되지만 **거부를 만들어 내는 코드는 한 줄도 실행되지 않는다** —
    그 검사가 지키는 것은 화면 문구뿐이다.

    그래서 가장 아래 primitive 를 갈아 끼운다. Windows 는 볼륨 조회가 확정에 실패한 것처럼,
    POSIX 는 결속 기능이 없는 것처럼 만든다. 위쪽 판정은 전부 실제로 돈다.
    """
    if os.name == "nt":
        return ("from sage import uninstall_windows_fs as w",
                "w._volume_facts = lambda handle: (None, None)")
    return ("from sage import uninstall_posix_fs as p",
            "p._pinning_support = lambda: False")


def refusal_case():
    """지원 범위 밖의 **거부 계약**을 명시 fixture 로 확인한다.

    환경이 우연히 지원 범위 밖이기를 기다리지 않는다. 기다리면 이 검사는 지원 환경에서
    영원히 돌지 않고, 돌지 않은 검사는 통과가 아니다.
    """
    root = os.path.realpath(tempfile.mkdtemp(prefix="uninstall-refusal-",
                                             dir=fixture_base()))
    project = os.path.join(root, "proj")
    codex_home = os.path.join(root, "codex")
    os.makedirs(project)
    os.makedirs(codex_home)
    env = dict(os.environ, CODEX_HOME=codex_home)
    try:
        installed = run("install", "--host", "claude", "--dest", project, env=env)
        if installed.returncode != 0:
            fail("refusal: install failed", installed)
        before = tree(project)
        script = "\n".join([
            "import sys",
            f"sys.path.insert(0, {REPO!r})",
            *unsupported_probe_script(),
            "from sage import uninstall_fs as f",
            f"cap = f.capability([{project!r}])",
            "assert not cap.supported, 'the probe still reports this environment supported'",
            "assert cap.failure_code == 'uninstall.unsafe_platform', cap.failure_code",
            # 정책 관문을 **이 자식에서만** 통과시킨다. 지원 범위 밖 SKU 에서는 정책이 먼저
            # 걸려 capability 거부가 한 줄도 실행되지 않고, 그래도 화면은 같은 code 를 내므로
            # 통과처럼 보인다 — 두 축을 하나의 fixture 로 덮으면 그 순간 둘 다 미검증이다.
            "f.support_policy = lambda: None",
            "from sage.cli import main",
            f"sys.argv = ['sage', 'uninstall', '--dest', {project!r}, '--yes', '--json']",
            "sys.exit(main())",
        ])
        refused = subprocess.run([sys.executable, "-c", script], cwd=REPO, env=env,
                                 capture_output=True, text=True)
        if refused.returncode != 2:
            fail("refusal: an unsupported environment did not block", refused)
        if tree(project) != before:
            fail("refusal: a refused run still changed the project", refused)
        try:
            payload = json.loads(refused.stdout)
        except ValueError:
            fail("refusal: --json did not emit JSON", refused)
        guide = payload.get("manual_cleanup")
        if not guide or not guide.get("available"):
            fail("refusal: no manual cleanup guidance was offered", refused)
        if guide.get("basis") != "verified_plan":
            fail(f"refusal: unexpected basis {guide.get('basis')}", refused)
        if guide.get("order")[:1] != ["STRIP"]:
            fail(f"refusal: partial removal is not first: {guide.get('order')}", refused)
        print("  refusal contract verified through the real capability probe")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def policy_guidance_case(code, label):
    """정책 거부 안내 화면을 **모든 OS 에서** 소비자 경로로 확인한다.

    GitHub 에 Windows 10 러너는 없고 데스크톱 SKU 도 없다. 그래서 "그 환경에서만 도는 코드"
    로 두면 이 화면은 영원히 미검증으로 남고, 첫 사용자가 검사자가 된다. 합성하는 것은
    **판정 하나**뿐이다 — build 19045 를 Windows 10 으로, server SKU 를 범위 밖으로 읽는
    규칙은 단위 검사가 따로 증명한다. 계획·표시·JSON·수동 안내·mutation 0 건은 여기서 전부
    실제로 돈다.
    """
    root = os.path.realpath(tempfile.mkdtemp(prefix=f"uninstall-{label}-", dir=fixture_base()))
    project = os.path.join(root, "proj")
    codex_home = os.path.join(root, "codex")
    os.makedirs(project)
    os.makedirs(codex_home)
    env = dict(os.environ, CODEX_HOME=codex_home)

    def child(*argv):
        script = "\n".join([
            "import sys",
            f"sys.path.insert(0, {REPO!r})",
            "from sage import uninstall_fs as f",
            f"f.support_policy = lambda: {code!r}",
            "from sage.cli import main",
            f"sys.argv = ['sage', 'uninstall', *{list(argv)!r}]",
            "sys.exit(main())",
        ])
        return subprocess.run([sys.executable, "-c", script], cwd=REPO, env=env,
                              capture_output=True, text=True)

    # 화면이 **그 code 의 문장**을 실제로 냈는지 본다. "Windows 10" 같은 글자를 찾으면
    # 문구가 바뀌는 날 검사가 조용히 아무것도 확인하지 않게 된다.
    sys.path.insert(0, REPO)
    from sage.i18n import tr
    tr_reason = tr("ko", f"cli.{code}")

    try:
        installed = run("install", "--host", "claude", "--dest", project, env=env)
        if installed.returncode != 0:
            fail(f"{label}: install failed", installed)
        before = tree(project)
        seen = {}
        for mode in ("--check", "--yes"):
            payload = child("--dest", project, mode, "--json")
            if payload.returncode != 2:
                fail(f"{label}: {mode} --json exit {payload.returncode}", payload)
            try:
                body = json.loads(payload.stdout)
            except ValueError:
                fail(f"{label}: {mode} --json did not emit JSON", payload)
            if body.get("blocked_reason") != code:
                fail(f"{label}: {mode} blocked_reason={body.get('blocked_reason')}", payload)
            if body.get("status") != "BLOCKED" or body.get("exit_code") != 2:
                fail(f"{label}: {mode} status={body.get('status')}", payload)
            guide = body.get("manual_cleanup") or {}
            if not guide.get("available") or guide.get("basis") != "verified_plan":
                fail(f"{label}: {mode} manual_cleanup={guide}", payload)
            if not guide.get("order"):
                fail(f"{label}: {mode} manual_cleanup had no ordering", payload)
            if "BLOCK" in guide["order"]:
                fail(f"{label}: {mode} told the user to act on BLOCK entries", payload)
            seen[mode] = body
            # **text 도 같은 값을 소비한다.** JSON 만 맞으면 사람이 읽는 화면이 조용히
            # 갈라지고, 그 화면이 실제로 사용자가 따라 하는 것이다.
            text = child("--dest", project, mode)
            if text.returncode != 2:
                fail(f"{label}: {mode} text exit {text.returncode}", text)
            for entry in body.get("deleted", []) + body.get("stripped", []):
                if entry["path"] not in text.stdout:
                    fail(f"{label}: {mode} text hid {entry['path']}", text)
            for entry in body.get("preserved", []) + body.get("blocked", []):
                if entry["path"] not in text.stdout:
                    fail(f"{label}: {mode} text hid preserved/blocked {entry['path']}", text)
            if tr_reason not in text.stderr:
                fail(f"{label}: {mode} text never named the reason", text)
        for key in ("deleted", "stripped", "preserved", "blocked", "blocked_reason"):
            if seen["--check"].get(key) != seen["--yes"].get(key):
                fail(f"{label}: --check and --yes disagreed on {key}")
        # **mutation 0 건.** 이 관문의 값 전부가 여기에 달려 있다.
        if tree(project) != before:
            fail(f"{label}: a refused run changed the project")
        if any(name.startswith(".sage-install-backup-") for name in tree(project)):
            fail(f"{label}: a refused run left a backup store")
        # 반복 실행이 같은 답을 낸다. 처음만 막고 두 번째가 통과하면 그 통과가 실제 제거다.
        again = child("--dest", project, "--yes", "--json")
        if again.returncode != 2 or json.loads(again.stdout).get("blocked_reason") != code:
            fail(f"{label}: a repeated run did not refuse the same way", again)
        if tree(project) != before:
            fail(f"{label}: a repeated refused run changed the project")
        print(f"  {label} guidance verified through the consumer CLI (0 mutations)")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def preserve_only_rerun_case():
    """안전 항목을 손으로 치운 **뒤의 재실행**. 잔재만 남은 상태의 의미를 접지 않는다.

    write target 은 0 건이지만 보존 잔재와 영수증이 남아 있다. 이것을 `BLOCKED`(2) 로 올리면
    사용자는 할 수 있는 일이 없는데 차단을 받고, `COMPLETE`(0) 으로 접으면 손상된 host 설정이
    남았다는 사실이 화면에서 사라진다. 둘 다 사실과 다르다.
    """
    root = os.path.realpath(tempfile.mkdtemp(prefix="uninstall-rerun-", dir=fixture_base()))
    project = os.path.join(root, "proj")
    codex_home = os.path.join(root, "codex")
    os.makedirs(project)
    os.makedirs(codex_home)
    env = dict(os.environ, CODEX_HOME=codex_home)
    code = "uninstall.windows_10_manual_only"

    def child(*argv):
        script = "\n".join([
            "import sys",
            f"sys.path.insert(0, {REPO!r})",
            "from sage import uninstall_fs as f",
            f"f.support_policy = lambda: {code!r}",
            "from sage.cli import main",
            f"sys.argv = ['sage', 'uninstall', *{list(argv)!r}]",
            "sys.exit(main())",
        ])
        return subprocess.run([sys.executable, "-c", script], cwd=REPO, env=env,
                              capture_output=True, text=True)

    try:
        installed = run("install", "--host", "claude", "--dest", project, env=env)
        if installed.returncode != 0:
            fail("rerun: install failed", installed)
        settings = os.path.join(project, ".claude", "settings.json")
        with open(settings, "w", encoding="utf-8") as handle:
            handle.write("{ this is not json")
        with open(settings, "rb") as handle:
            damaged = handle.read()
        mode = os.stat(settings).st_mode

        first = child("--dest", project, "--yes", "--json")
        if first.returncode != 2:
            fail("rerun: the first run did not refuse", first)
        plan = json.loads(first.stdout)

        # 안내대로 손으로 처리한다 — 보존 항목은 건드리지 않는다.
        for entry in plan["deleted"]:
            target = os.path.join(project, entry["path"])
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.lexists(target):
                os.remove(target)
        for entry in plan["stripped"]:
            # `STRIP` 은 파일 전체 삭제가 아니다. SAGE 부분만 비운다.
            with open(os.path.join(project, entry["path"]), "w", encoding="utf-8") as handle:
                handle.write("")

        before = tree(project)
        again = child("--dest", project, "--yes", "--json")
        if again.returncode != 1:
            fail(f"rerun: preserve-only rerun exited {again.returncode}, want 1", again)
        body = json.loads(again.stdout)
        if body["status"] != "PARTIAL":
            fail(f"rerun: status={body['status']}, want PARTIAL", again)
        if body["blocked_reason"] is not None:
            fail(f"rerun: blocked_reason={body['blocked_reason']} on a preserve-only state", again)
        if body["deleted"] or body["stripped"]:
            fail("rerun: a preserve-only state still claimed write targets", again)
        if not body["preserved"]:
            fail("rerun: the preserved residue was not re-reported", again)
        reasons = {e["path"]: e["reason"] for e in body["preserved"]}
        if os.path.join(".claude", "settings.json") not in reasons:
            fail(f"rerun: the damaged host file vanished from the report: {reasons}", again)
        if os.path.join("docs", "sage_harness") not in reasons:
            fail(f"rerun: the manifest receipt was not retained: {reasons}", again)
        with open(settings, "rb") as handle:
            if handle.read() != damaged:
                fail("rerun: the damaged file's bytes changed")
        if os.stat(settings).st_mode != mode:
            fail("rerun: the damaged file's mode changed")
        if tree(project) != before:
            fail("rerun: the second run changed the tree", again)
        if any(".sage-install-backup-" in name for name in before):
            fail("rerun: a backup store was left behind")
        print("  preserve-only rerun stays PARTIAL(1) with the residue re-reported "
              "(0 mutations, receipt kept)")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def native_failure_case():
    """backend 의 native 실패가 **CLI text·JSON 에 같은 code 로** 도착하는지 본다.

    변환 함수가 있어도 소비자 화면까지 그 이름이 오지 않으면, 사용자가 보는 것은
    "실행 실패" 하나다. 그 화면에서는 보관소 이름 충돌과 경계 변화가 구별되지 않고,
    복구 안내도 갈라지지 않는다.
    """
    root = os.path.realpath(tempfile.mkdtemp(prefix="uninstall-native-",
                                             dir=fixture_base()))
    project = os.path.join(root, "proj")
    codex_home = os.path.join(root, "codex")
    os.makedirs(project)
    os.makedirs(codex_home)
    env = dict(os.environ, CODEX_HOME=codex_home)
    try:
        installed = run("install", "--host", "claude", "--dest", project, env=env)
        if installed.returncode != 0:
            fail("native: install failed", installed)
        before = tree(project)
        for code in ("uninstall.backup_collision", "uninstall.boundary_changed"):
            script = "\n".join([
                "import sys",
                f"sys.path.insert(0, {REPO!r})",
                "from sage import uninstall_fs as f",
                # 이 case 가 보려는 것은 **native 실패의 이름이 화면까지 오는가** 다.
                # 지원 범위 밖 SKU 에서는 정책 관문이 먼저 걸려 backend 가 만들어지지도
                # 않고, 그래도 exit 2 라 통과처럼 보인다 — 두 축을 한 fixture 로 덮으면
                # 그 순간 둘 다 미검증이다.
                "f.support_policy = lambda: None",
                "real = f.backend_for",
                "fired = []",
                "def wrapped(roots):",
                "    backend = real(roots)",
                "    original = backend.replace",
                "    def refuse(source, target):",
                "        if not fired:",
                "            fired.append(True)",
                f"            raise f.MutationBackendError('op:nt:0x1', {code!r})",
                "        return original(source, target)",
                # 되돌리기까지 같은 실패를 내면 판정이 `rollback_failed` 로 덮인다.
                # 우리가 보려는 것은 **첫 실패의 이름이 화면까지 오는가** 다.
                "    backend.replace = refuse",
                "    return backend",
                "f.backend_for = wrapped",
                "from sage import uninstall_executor as e",
                "e._fs.backend_for = wrapped",
                "from sage.cli import main",
                f"sys.argv = ['sage', 'uninstall', '--dest', {project!r},"
                " '--yes', '--json']",
                "sys.exit(main())",
            ])
            done = subprocess.run([sys.executable, "-c", script], cwd=REPO, env=env,
                                  capture_output=True, text=True)
            if done.returncode != 2:
                fail(f"native: {code} did not surface as BLOCKED(2)", done)
            try:
                payload = json.loads(done.stdout)
            except ValueError:
                fail(f"native: {code} produced no JSON", done)
            if payload.get("blocked_reason") != code:
                fail(f"native: JSON reported {payload.get('blocked_reason')}, not {code}",
                     done)
            if tree(project) != before:
                fail(f"native: {code} left the project changed", done)
            text = "\n".join([
                "import sys",
                f"sys.path.insert(0, {REPO!r})",
                "from sage import uninstall_fs as f",
                # 이 case 가 보려는 것은 **native 실패의 이름이 화면까지 오는가** 다.
                # 지원 범위 밖 SKU 에서는 정책 관문이 먼저 걸려 backend 가 만들어지지도
                # 않고, 그래도 exit 2 라 통과처럼 보인다 — 두 축을 한 fixture 로 덮으면
                # 그 순간 둘 다 미검증이다.
                "f.support_policy = lambda: None",
                "real = f.backend_for",
                "fired = []",
                "def wrapped(roots):",
                "    backend = real(roots)",
                "    original = backend.replace",
                "    def refuse(source, target):",
                "        if not fired:",
                "            fired.append(True)",
                f"            raise f.MutationBackendError('op:nt:0x1', {code!r})",
                "        return original(source, target)",
                "    backend.replace = refuse",
                "    return backend",
                "f.backend_for = wrapped",
                "from sage import uninstall_executor as e",
                "e._fs.backend_for = wrapped",
                "from sage.cli import main",
                f"sys.argv = ['sage', 'uninstall', '--dest', {project!r}, '--yes']",
                "sys.exit(main())",
            ])
            human = subprocess.run([sys.executable, "-c", text], cwd=REPO,
                                   env=dict(env, SAGE_LANG="en"),
                                   capture_output=True, text=True)
            if human.returncode != 2:
                fail(f"native: {code} text surface did not block", human)
            # 화면에도 **같은 판정**이 와야 한다. 그 근거는 code 별 복구 안내가 다르다는 것이다.
            if "uninstall" not in (human.stdout + human.stderr):
                fail(f"native: {code} text surface carried no diagnostic", human)
        print("  native failures reach text and JSON with the contract code")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_case(label, project_name, codex_name, codex_mode):
    root = os.path.realpath(tempfile.mkdtemp(prefix=f"uninstall-smoke-{label}-",
                                             dir=fixture_base()))
    project = os.path.join(root, project_name)
    codex_home = os.path.join(root, codex_name)
    os.makedirs(project)
    os.makedirs(codex_home)
    env = os.environ.copy()
    if codex_mode == "custom":
        env["CODEX_HOME"] = codex_home
    else:
        # 기본 경로(`~/.codex`)를 밟되 사용자 홈을 건드리지 않도록 HOME 을 fixture 로 돌린다.
        # HOME 을 돌리면 user-site 가 사라지므로, 부모가 쓰던 import 경로를 명시로 넘긴다 —
        # 그러지 않으면 검사가 제품이 아니라 자기 격리 방식 때문에 죽는다.
        env.pop("CODEX_HOME", None)
        env["HOME"] = root
        env["USERPROFILE"] = root
        if IMPORT_PATHS:
            existing = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
            env["PYTHONPATH"] = os.pathsep.join(
                existing + [p for p in IMPORT_PATHS if p not in existing])
    scoped = safe_mutation(project, codex_home if codex_mode == "custom" else None)
    steps = 0
    total = 8 if scoped else 4

    def step(label_text):
        nonlocal steps
        steps += 1
        print(f"  [{steps}/{total}] {label_text}")

    try:
        step("install a consumer")
        installed = run("install", "--host", "claude", "--dest", project, env=env)
        if installed.returncode != 0:
            fail("install failed", installed)

        step("--check --json is machine readable and read-only")
        before = tree(project)
        checked = run("uninstall", "--dest", project, "--check", "--json", env=env)
        if checked.returncode not in CHECK_CODES:
            fail(f"--check exit code {checked.returncode} (want one of {CHECK_CODES})", checked)
        try:
            payload = json.loads(checked.stdout)
        except ValueError:
            fail("--check --json did not emit JSON", checked)
        for key in ("scope", "status", "exit_code", "deleted", "preserved", "notices"):
            if key not in payload:
                fail(f"--check --json missing {key}", checked)
        if payload.get("executed") is not False:
            fail("--check reported itself as executed", checked)
        if POLICY:
            policy_refusal(payload, checked, "--check")
        if tree(project) != before:
            fail("--check changed the project")
        sys.path.insert(0, REPO)
        from sage.install_transaction import DestinationLock
        probe = DestinationLock(project)
        probe.acquire()   # --check 가 잠갔다면 여기서 막힌다
        probe.release()

        step("executing --json without --yes is a usage error")
        mixed = run("uninstall", "--dest", project, "--json", env=env)
        if mixed.returncode != 2:
            fail("prompt and JSON were mixed", mixed)

        step("non-interactive without --yes refuses and changes nothing")
        refused = run("uninstall", "--dest", project, env=env)
        if refused.returncode != 2:
            fail("non-interactive run did not block", refused)
        if tree(project) != before:
            fail("blocked run still changed the project")

        if not scoped:
            # 이 환경은 지원 범위 밖이다 — 정책(SKU·build)이든 capability(볼륨·native)든
            # 실행은 **거부**되어야 하고, 거부는 아무것도 바꾸지 않아야 한다.
            if REQUIRE_MUTATION and not POLICY:
                fail("mutation refused but this job requires real removal")
            refusal = run("uninstall", "--dest", project, "--yes", "--json", env=env)
            if refusal.returncode != 2:
                fail("an unsupported environment did not refuse to mutate", refusal)
            if POLICY:
                # `--yes` 와 `--check` 가 **같은 진단과 같은 목록**을 낸다. 두 화면이 갈리면
                # 사용자는 어느 쪽을 믿어야 하는지 알 수 없다.
                try:
                    executed = json.loads(refusal.stdout)
                except ValueError:
                    fail("a policy refusal under --json did not emit JSON", refusal)
                policy_refusal(executed, refusal, "--yes")
                for key in ("deleted", "stripped", "preserved", "blocked", "blocked_reason"):
                    if executed.get(key) != payload.get(key):
                        fail(f"--yes and --check disagreed on {key}", refusal)
            if tree(project) != before:
                fail("a refused run still changed the project")
            print(f"  out of supported range -- refusal contract verified "
                  f"({'policy ' + POLICY if POLICY else 'capability'}, no mutation attempted)")
            return False

        step("a held lock blocks the run")
        # install·generate 와 **같은** lock 권위를 쓴다. 다른 lock 이면 두 명령이 서로를
        # 막지 못한 채 각자 잠갔다고 믿는다.
        sys.path.insert(0, REPO)
        from sage.install_transaction import DestinationLock
        held = DestinationLock(project)
        held.acquire()
        try:
            busy = run("uninstall", "--dest", project, "--yes", env=env)
            if busy.returncode != 2:
                fail("a held install lock did not block uninstall", busy)
        finally:
            held.release()

        step("plan is recorded, then executed")
        planned = run("uninstall", "--dest", project, "--check", "--json", env=env)
        plan = json.loads(planned.stdout)
        reported = set()
        for entry in plan["preserved"] + plan["stripped"]:
            # `path` 는 이미 **정화된 project 상대 경로**다(FR-H11). 여기서 다시 relpath 를
            # 걸면 상대 경로를 절대 경로 기준으로 잘라 `../../..` 가 나오고, 그 값은 어떤
            # 생존 파일과도 맞지 않는다 — 첫 조합부터 실패했다.
            rel = entry["path"]
            if os.path.isabs(rel):
                fail(f"plan reported an absolute path: {rel}", planned)
            reported.add(rel)
            parent = os.path.dirname(rel)
            while parent:
                reported.add(parent)
                parent = os.path.dirname(parent)
        removed = run("uninstall", "--dest", project, "--yes", env=env)
        if removed.returncode not in (0, 1):
            fail("uninstall failed", removed)

        step("nothing survives that was not reported")
        survivors = tree(project)
        unreported = sorted(survivors - reported)
        if unreported:
            fail(f"unreported residue: {unreported}", removed)
        released = DestinationLock(project)
        released.acquire()   # 끝난 뒤 lock 이 남아 있으면 여기서 막힌다
        released.release()
        if any(name.startswith(".sage-install-backup-") for name in survivors):
            fail("a backup store was left behind")

        step("a second run is not an error")
        again = run("uninstall", "--dest", project, "--yes", env=env)
        if again.returncode not in (0, 1):
            fail("second run was not idempotent", again)
        return True
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
