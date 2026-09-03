#!/usr/bin/env python3
"""Windows matrix 에서 **핵심 계약 검사**를 돌리고 skip 0 을 단언한다.

## 왜 필요한가

hook 회귀 job 은 ubuntu 하나다. 그래서 결속·capability·오류 표면·수동 안내 계약을 지키는
검사들은 Windows 에서 **한 번도 실행된 적이 없다.** 실행된 적 없는 검사는 통과가 아니다.

그리고 skip 을 세지 않으면 그 사실이 보이지 않는다. 지난 사이클에서 정확히 그 일이 있었다 —
capability 판정 하나가 어긋나 핵심 검사가 세 Python 버전에서 전부 skip 되었고, 요약은 초록
이었다. **skip 은 통과가 아니다.**

## 무엇을 돌리는가

`test_uninstall.py` 의 계약 검사군을 그대로 가져다 돈다. 검사를 여기에 복사하지 않는 이유는
두 벌이 되면 한쪽만 고쳐지기 때문이다.

담는 방법은 둘이다. 클래스 전체(`CORE_CLASSES`)와, 클래스째 담을 수 없는 검사를 하나씩
지목하는 것(`CORE_SELECTORS`). 두 번째가 필요한 이유는 skip 을 실패로 세기 때문이다 — 정당한
조건부 skip 이 하나라도 있는 클래스는 통째로 담을 수 없고, 그렇다고 빼 두면 그 안의 필수
검사가 Windows 에서 영영 돌지 않는다. **누락은 skip 으로 세지지 않으므로 `skipped=0` 이 그
사실을 가린다.** 지목이 빗나가는 모든 방식은 그래서 hard failure 다.

Windows 에서는 그 위에 **실제 판정 경로 통합 검사**를 더한다. 단위 검사는 배선을 보지만,
"이 환경이 실제로 지원된다고 답하는가" 는 그 환경에서만 답할 수 있다.
"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)

from sage import uninstall_fs as _fs               # noqa: E402

# 이 목록이 "핵심 Windows 검사" 의 정본이다. 이름을 여기 한 벌만 두는 이유는, 목록이 두
# 군데 있으면 한쪽에 추가한 검사가 다른 쪽에서 영원히 돌지 않기 때문이다.
CORE_CLASSES = (
    "WindowsBackendContract",
    "WindowsCapabilityWiring",
    "RootBinding",
    "PinnedProbes",
    "NativeErrorSurface",
    "PostFailureGuidance",
    "ManualCleanupGuidance",
    "CoreSelectorContract",
)

# 클래스째 넣을 수 없지만 **반드시 Windows 에서 돌아야 하는** 검사들.
#
# `BoundaryRace` 에는 host 배치에 따라 정당하게 `skipTest` 하는 검사가 있고, 이 runner 는
# skip 하나를 실패로 센다. 그래서 클래스를 통째로 넣으면 계약과 무관한 이유로 job 이 붉어진다.
# 그렇다고 빼 두면 A24 의 근거인 실행 중 가로채기 네 건이 Windows 에서 **한 번도 돌지 않는다** —
# 그리고 그 누락은 skip 으로 세지지 않으므로 `skipped=0` 이 그 사실을 가린다. 없는 것과 통과한
# 것이 같은 화면으로 보이는 자리이고, 그것이 이 파일이 처음 생긴 이유다.
#
# 그래서 클래스가 아니라 **검사 하나를 정확히 지목한다.** 지목이 빗나가는 모든 방식(없는 이름,
# 중복, 0건 선택)은 조용한 누락으로 떨어지므로 전부 hard failure 다.
CORE_SELECTORS = (
    "BoundaryRace.test_no_absolute_path_judgement_survives_after_the_pin",
    "BoundaryRace.test_no_absolute_path_judgement_survives_through_the_rollback",
    "BoundaryRace.test_the_cleanup_allowance_is_only_the_backup_lexists",
    "BoundaryRace.test_a_backup_path_probe_before_the_commit_is_caught",
)


def required_selectors(module):
    """요구 목록의 **정본은 검사 파일이 들고 있다.** 여기 것은 실행 목록이다.

    둘을 한 파일에 두면 지목 하나를 지우는 것이 곧 요구를 지우는 것이 된다 — 남은 지목은
    전부 해석되고, `selectors=3` 은 `selectors=4` 와 똑같이 초록이다. 줄어든 사실이 어디에도
    적히지 않는 축소이고, 그것이 이 파일이 막으려는 바로 그 모양이다.

    목록 자체가 사라지거나 비면 대조할 것이 없다. 그때는 통과가 아니라 실패다.
    """
    oracle = getattr(module, "A24_REQUIRED_SELECTORS", None)
    if not isinstance(oracle, tuple) or not oracle:
        return None
    return oracle


def missing_required(oracle, selectors):
    """요구된 것 중 실행 목록에 없는 것. 치환도 여기서 걸린다 — 건수가 아니라 이름을 본다."""
    listed = set(selectors)
    return [f"required selector is not listed: {name}"
            for name in oracle if name not in listed]


def resolve_selectors(module, loader, covered):
    """`Class.test_name` 을 검사 하나로 정확히 푼다. 애매하면 통과시키지 않는다.

    `covered` 는 `CORE_CLASSES` 가 이미 담은 검사들이다. 같은 검사를 두 번 담으면 건수만
    늘고 보장은 늘지 않으며, 나중에 클래스가 목록에 들어온 사실이 여기서 조용히 가려진다.
    """
    problems = []
    tests = []
    seen = set()
    for selector in CORE_SELECTORS:
        if selector in seen:
            problems.append(f"selector is listed twice: {selector}")
            continue
        seen.add(selector)
        if selector.count(".") != 1:
            problems.append(f"selector is not 'Class.test_name': {selector}")
            continue
        class_name, test_name = selector.split(".")
        case = getattr(module, class_name, None)
        if case is None or not isinstance(case, type) or not issubclass(case, unittest.TestCase):
            problems.append(f"selector names no test class: {selector}")
            continue
        matched = [name for name in loader.getTestCaseNames(case) if name == test_name]
        if not matched:
            # 이름이 바뀌면 0건이 된다. 0건을 통과로 세면 이 목록은 아무것도 지키지 않는다.
            problems.append(f"selector matched 0 checks: {selector}")
            continue
        if len(matched) > 1:
            problems.append(f"selector matched {len(matched)} checks: {selector}")
            continue
        if selector in covered:
            problems.append(f"selector is already covered by CORE_CLASSES: {selector}")
            continue
        tests.append(case(test_name))
    return tests, problems


def load_tests_module():
    path = os.path.join(REPO, "scripts", "sage_harness", "hooks", "tests",
                        "test_uninstall.py")
    spec = importlib.util.spec_from_file_location("sage_uninstall_core_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def windows_probe_integration():
    """Windows 에서 **실제** capability 판정 경로를 끝까지 돌린다.

    단위 검사는 배선(돌려주는 값이 바뀌는가)을 본다. 이 검사는 그 위에서 "이 환경이 실제로
    지원된다고 답하는가" 를 본다 — 그 답은 이 환경에서만 나온다.

    **root 를 둘 준다.** 실제 배치가 그렇기 때문이다 — project 와 `$CODEX_HOME` 은 서로 다른
    디렉터리이고, 다른 볼륨일 수도 있다. 하나만 주면 root 를 순회하며 판정을 합치는 경로가
    한 번도 돌지 않고, 그 경로가 바로 "첫 root 의 참이 두 번째로 새는" 결함이 살던 자리다.
    """
    from uninstall_smoke import fixture_base
    import shutil
    import tempfile

    base = os.path.realpath(tempfile.mkdtemp(prefix="uninstall-core-", dir=fixture_base()))
    project = os.path.join(base, "proj")
    codex_home = os.path.join(base, "codex", "skills")
    os.makedirs(project)
    os.makedirs(codex_home)
    try:
        problems = []
        cap = _fs.capability((project, codex_home))
        if not cap.supported:
            problems.append(f"two roots: supported=False failure_code={cap.failure_code} "
                            f"filesystem={cap.filesystem} primitives={cap.primitives}")
        if cap.backend != _fs.BACKEND_WINDOWS:
            problems.append(f"backend={cap.backend}")
        if cap.identity_source is None:
            problems.append("identity_source was never determined")
        if not cap.local_volume:
            problems.append("local_volume=False on local temp directories")
        # 한 root 만 주는 경로도 함께 본다 — project 범위 실행이 그 모양이다.
        single = _fs.capability((project,))
        if not single.supported:
            problems.append(f"single root: supported=False failure_code="
                            f"{single.failure_code}")
        if single.identity_source != cap.identity_source:
            problems.append(f"identity source differs by root count: "
                            f"{single.identity_source} vs {cap.identity_source}")
        return problems, cap
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main():
    sys.path.insert(0, HERE)
    module = load_tests_module()
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    covered = set()
    for name in CORE_CLASSES:
        case = getattr(module, name, None)
        if case is None:
            print(f"FAIL: core check class is missing: {name}")
            return 1
        suite.addTests(loader.loadTestsFromTestCase(case))
        covered.update(f"{name}.{test}" for test in loader.getTestCaseNames(case))

    oracle = required_selectors(module)
    if oracle is None:
        print("== uninstall core checks ==")
        print("FAIL: required selector list (A24_REQUIRED_SELECTORS) is missing or empty")
        return 1

    selected, selector_problems = resolve_selectors(module, loader, covered)
    selector_problems = missing_required(oracle, CORE_SELECTORS) + selector_problems
    if selector_problems:
        # 지목이 서지 않으면 **아무것도 돌리지 않는다.** 나머지가 초록이면 그 화면이 곧
        # "핵심 검사가 돌았다" 로 읽히고, 지목이 빗나간 사실은 그 뒤에 묻힌다.
        print("== uninstall core checks ==")
        for note in selector_problems:
            print(f"  - {note}")
        print(f"FAIL: {len(selector_problems)} core selector(s) did not resolve")
        return 1
    for test in selected:
        suite.addTest(test)
    selected_ids = {test.id().split(".", 1)[-1] for test in selected}

    total = suite.countTestCases()
    print(f"== uninstall core checks ({sys.platform}, python "
          f"{sys.version.split()[0]}) ==")
    print(f"  {len(CORE_CLASSES)} classes + {len(selected)} selectors, {total} checks")
    # **해석된 이름을 그대로 찍는다.** 건수만 남기면 로그를 나중에 읽는 사람이 "넷이 돌았다"
    # 까지만 알고 "어느 넷인가" 는 모른다 — 치환은 정확히 그 틈에서 보이지 않는다.
    for test in selected:
        print(f"  selector: {test.id().split('.', 1)[-1]}")
    result = unittest.TextTestRunner(verbosity=1, stream=sys.stdout).run(suite)

    failed = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)
    print(f"  ran={result.testsRun} failed={failed} skipped={skipped} "
          f"selectors={len(selected)}")
    problems = []
    if failed:
        problems.append(f"{failed} core checks failed")
    if skipped:
        # **skip 은 통과가 아니다.** 돌지 않은 검사를 초록으로 세면 그 방어는 있다고 말할 수 없다.
        names = [str(test) for test, _reason in result.skipped]
        problems.append(f"{skipped} core checks were skipped: {names}")
        # 지목한 검사가 skip 되면 그 지목은 아무것도 하지 않은 것이다. 따로 이름을 낸다.
        missed = sorted(n for n in (t.id().split(".", 1)[-1] for t, _r in result.skipped)
                        if n in selected_ids)
        if missed:
            problems.append(f"selected core checks were skipped: {missed}")

    if os.name == "nt":
        notes, cap = windows_probe_integration()
        if notes:
            problems.append("windows capability integration: " + "; ".join(notes))
        else:
            print(f"  windows capability: supported filesystem={cap.filesystem} "
                  f"identity_source={cap.identity_source}")
    else:
        print("  windows capability integration: not applicable on this platform")

    if problems:
        print()
        for note in problems:
            print(f"  - {note}")
        return 1
    print("  core checks passed with 0 skips")
    return 0


if __name__ == "__main__":
    sys.exit(main())
