#!/usr/bin/env python3
"""플랫폼 smoke 와 publish preflight — 릴리스 증거 게이트.

publish 는 되돌릴 수 없다. 그래서 이 게이트들이 **실제로 막는가**를 확인한다. 통과만 확인하면
"아무것도 검사하지 않는 검사"가 통과로 세어지고, 그게 릴리스 당일에 처음 드러난다.

각 검사가 실패를 만들었을 때 실제로 non-zero 로 끝나는지를 직접 만든 위반 상태로 확인한다.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
PREFLIGHT = REPO / "scripts" / "ci" / "publish_preflight.py"
SMOKE = REPO / "scripts" / "ci" / "platform_smoke.py"


def _run(script, *args, cwd=None):
    return subprocess.run([sys.executable, str(script), *args],
                          cwd=str(cwd or REPO), capture_output=True, text=True)


class TestPreflightBlocksWhatItClaims(unittest.TestCase):
    def test_a_mismatched_tag_blocks(self):
        """tag 와 version 이 다르면 사용자가 설치한 것과 tag 가 가리키는 것이 다르다."""
        done = _run(PREFLIGHT, "--tag", "v0.0.0-not-the-version")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("tag-version", done.stderr)

    def test_the_matching_tag_passes_that_check(self):
        from sage import __version__
        done = _run(PREFLIGHT, "--tag", f"v{__version__}")
        self.assertNotIn("tag-version", done.stderr)

    def test_a_pull_request_ref_is_not_read_as_a_tag(self):
        """`GITHUB_REF_NAME` 은 PR 에서 `6/merge`, 브랜치 push 에서 `main` 이다.

        그걸 tag 로 읽으면 릴리스가 아닌 실행이 전부 tag 불일치로 떨어진다 — 릴리스 전에 증거를
        미리 맞춰 보려고 PR 에서 돌리는 job 이 정작 그 이유 하나로 항상 빨간불이 되고, 나머지
        7건의 신호도 같이 죽는다. 원격에서 실제로 그렇게 났다."""
        for ref_type, ref_name in (("branch", "6/merge"), ("branch", "main"), (None, "main")):
            environment = dict(os.environ, GITHUB_REF_NAME=ref_name)
            environment.pop("GITHUB_REF_TYPE", None)
            if ref_type:
                environment["GITHUB_REF_TYPE"] = ref_type
            done = subprocess.run([sys.executable, str(PREFLIGHT)], cwd=str(REPO),
                                  capture_output=True, text=True, env=environment)
            with self.subTest(ref_type=ref_type, ref_name=ref_name):
                self.assertNotIn("FAIL tag-version", done.stdout)
                # 건너뛴 것을 `OK` 로 찍으면 검사한 것과 구별되지 않는다.
                self.assertIn("SKIP tag-version", done.stdout)

    def test_a_real_tag_ref_is_still_compared(self):
        """건너뛰기가 tag 가 있는 실행까지 조용히 끄면 릴리스 게이트가 사라진다."""
        environment = dict(os.environ, GITHUB_REF_TYPE="tag",
                           GITHUB_REF_NAME="v0.0.0-not-the-version")
        done = subprocess.run([sys.executable, str(PREFLIGHT)], cwd=str(REPO),
                              capture_output=True, text=True, env=environment)
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("FAIL tag-version", done.stdout)

    def test_a_catalog_gap_blocks(self):
        """한쪽에만 있는 key 는 런타임 fallback 으로 조용히 넘어간다 — build 에서 잡아야 한다."""
        module = _load_preflight()
        original = module.check_catalog_parity.__globals__
        findings = module.check_catalog_parity()
        self.assertEqual(findings, [], f"현재 catalog 가 이미 어긋나 있다: {findings[:3]}")
        # 인위적 결손을 만들어 검사가 실제로 반응하는지 본다.
        from sage.i18n import CATALOGS
        removed_key = next(iter(CATALOGS["en"]))
        removed_value = CATALOGS["en"].pop(removed_key)
        try:
            self.assertTrue(module.check_catalog_parity(), "catalog 결손을 잡지 못했다")
        finally:
            CATALOGS["en"][removed_key] = removed_value

    def test_korean_left_in_the_english_catalog_blocks(self):
        """publish 게이트는 key 결손만 보지 않는다 — 영어 값 안의 한국어도 막아야 한다.

        인벤토리는 코드를 스캔하므로 catalog 값에 남은 한국어를 세지 못한다. 게이트가 이걸
        놓치면 인벤토리 0 으로 release 해도 `--lang en` 화면에 한국어가 나간다.
        """
        module = _load_preflight()
        from sage.i18n import CATALOGS
        key = "cli.root.help_option"
        original = CATALOGS["en"][key]
        for probe in ("이 문장은 영어여야 한다", "first\\nsecond"):
            CATALOGS["en"][key] = probe
            try:
                self.assertTrue(module.check_catalog_parity(),
                                f"catalog 내용 결함을 잡지 못했다: {probe!r}")
            finally:
                CATALOGS["en"][key] = original

    def test_a_missing_english_pair_blocks(self):
        module = _load_preflight()
        self.assertEqual(module.check_document_pairs(), [],
                         "현재 문서 짝이 이미 어긋나 있다")
        orphan = REPO / "docs" / "_preflight_probe.md"
        orphan.write_text("probe\n", encoding="utf-8")
        try:
            findings = module.check_document_pairs()
            self.assertTrue(findings, "영어 짝 없는 문서를 잡지 못했다")
        finally:
            orphan.unlink(missing_ok=True)

    def test_a_placeholder_version_blocks(self):
        module = _load_preflight()
        real = module._engine_version
        module._engine_version = lambda: "0.0.0"
        try:
            self.assertTrue(module.check_version_is_not_a_placeholder())
        finally:
            module._engine_version = real

    def test_upgrade_evidence_rejects_scalar_only_apply(self):
        """등록만 보지 않는다 — 실제 구 설치본에 신규 managed 자산이 생겨야 완료다."""
        module = _load_preflight()
        findings = module._managed_upgrade_findings(0, False, None)
        self.assertTrue(findings, "신규 managed CORE 자산을 배포하지 않는 upgrade가 통과했다")
        self.assertIn("language-policy", str(findings[0]))
        runner = REPO / "scripts" / "sage_harness" / "hooks" / "tests" / "run-all.sh"
        self.assertIn("test_upgrade.py", runner.read_text(encoding="utf-8"))

    def test_unmigrated_user_messages_block_release(self):
        """최신 목록도 key 없는 항목이 있으면 완료가 아니다."""
        module = _load_preflight()
        findings = module._inventory_completion_findings([
            {"key": "cli.ready", "hook_reachable": False},
            {"key": None, "hook_reachable": True},
        ])
        self.assertTrue(findings, "catalog key 없는 사용자 표시 literal이 있는데 release가 허용됐다")
        self.assertIn("미이관", str(findings[0]))

    def test_preflight_never_mutates_the_repository(self):
        """검사 도구가 version 을 올리면 승인 경계가 사라진다."""
        before = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                                capture_output=True, text=True).stdout
        _run(PREFLIGHT)
        after = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                               capture_output=True, text=True).stdout
        self.assertEqual(before, after, "preflight 가 저장소를 바꿨다")

    def test_every_check_runs_even_after_one_fails(self):
        """첫 실패에서 멈추면 두 번째 문제를 다음 실행에서야 발견한다."""
        done = _run(PREFLIGHT, "--tag", "v0.0.0-not-the-version")
        for name in ("catalog", "localization-debt", "docs-pair", "inventory", "upgrade"):
            self.assertIn(name, done.stdout, f"{name} 검사가 실행되지 않았다")

    def test_every_preflight_check_is_registered(self):
        """정의만 하고 CHECKS 에 넣지 않으면 그 검사는 영원히 안 돈다."""
        module = _load_preflight()
        defined = {name for name in dir(module) if name.startswith("check_")}
        # CHECKS 는 lambda 로 감싸 등록하므로 이름을 함수 객체가 아니라 선언 블록에서 찾는다.
        block = PREFLIGHT.read_text(encoding="utf-8").split("CHECKS = (")[1].split("\n)")[0]
        registered = {name for name in defined if f"{name}(" in block}
        self.assertEqual(defined, registered, f"등록 안 된 검사: {sorted(defined - registered)}")

    def test_remaining_localization_debt_blocks_publish(self):
        """추적 검사는 통과해도 publish 는 남은 부채 자체를 실패로 봐야 한다.

        목록에 적어뒀다는 사실이 출하 근거가 될 수 없다 — 그렇지 않으면 인벤토리 0 에
        도달하는 순간 영어 화면에 한국어가 남은 채로 릴리스가 열린다.

        6배치 완료 시점에는 실제 저장소의 KOREAN_IN_ENGLISH_DEBT·KOREAN_JUDGEMENT_DEBT 가
        정당하게 비어 있어(모든 표시 언어 부채가 이관됨) 실제 데이터로는 "부채가 남아 있는"
        상태를 재현할 수 없다. release_debt_issues 자체를 mock 으로 대체해 이 preflight 검사가
        그 반환값을 그대로 Finding 으로 실어 나른다는 배선만 확인한다(부채 판정 로직 자체는
        test_diagnostics_contract.py 가 별도로 검증)."""
        module = _load_preflight()
        from sage.i18n.validation import catalog_issues

        self.assertEqual([], catalog_issues(str(REPO)))        # 추적: 통과(실제 부채 0)

        import sage.i18n.validation as validation_module
        with mock.patch.object(validation_module, "release_debt_issues",
                               return_value=["runtime/fake.leak: 판정이 한국어 문장을 돌려준다"]):
            findings = module.check_localization_debt()        # 릴리스: mock 된 잔존 부채를 그대로 전달
        self.assertTrue(findings, "부채가 남았는데 publish 가 열렸다")
        rendered = " ".join(str(f) for f in findings)
        self.assertIn("fake.leak", rendered)

    def test_a_new_leak_blocks_publish_even_if_it_is_not_declared_debt(self):
        module = _load_preflight()
        from sage.i18n import CATALOGS
        key = "cli.root.help_option"
        original = CATALOGS["en"][key]
        CATALOGS["en"][key] = "이 문장은 영어여야 한다"
        try:
            rendered = " ".join(str(f) for f in module.check_localization_debt())
            self.assertIn(key, rendered, "선언되지 않은 신규 누출이 publish 를 막지 않았다")
        finally:
            CATALOGS["en"][key] = original


class TestPlatformSmokeContract(unittest.TestCase):
    def test_the_smoke_does_not_require_bash(self):
        """bash 없는 환경에서 도는지가 검사 대상인데 검사 도구가 bash 를 요구하면 모순이다."""
        source = SMOKE.read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""'):
                continue
            self.assertNotIn('"bash"', stripped, line)
            self.assertNotIn("'bash'", stripped, line)

    def test_a_failing_check_is_never_reported_as_a_skip(self):
        """조용한 skip 은 통과로 세어져 플랫폼 하나가 미검증인 채 릴리스에 실린다."""
        source = SMOKE.read_text(encoding="utf-8")
        self.assertIn("return 1", source)
        self.assertNotIn("SkipTest", source)

    def test_every_declared_check_is_registered(self):
        """정의만 하고 CHECKS 에 넣지 않으면 그 항목은 영원히 안 돈다."""
        module = _load_smoke()
        defined = {name for name in dir(module) if name.startswith("check_")}
        registered = {check.__name__ for check in module.CHECKS}
        self.assertEqual(defined, registered, f"등록 안 된 검사: {sorted(defined - registered)}")

    def test_the_ci_workflow_runs_it_on_every_supported_platform(self):
        """POSIX 둘은 hosted matrix, Windows 는 self-hosted 전용 job 이다.

        Windows 를 hosted matrix 에서 뺀 것은 축소가 아니라 **증거의 종류를 바로잡은 것**이다.
        GitHub-hosted Windows 는 Server 2025 이고 server SKU 는 지원 범위 밖이라, 거기서 나온
        초록은 데스크톱 증거가 될 수 없는데 로그에서는 같은 초록으로 보인다. 그래서 세는 것은
        러너 이름이 아니라 **platform smoke 가 실제로 실행되는 자리**다.
        """
        workflow = _ci_workflow()
        ran_on = set()
        for job in workflow["jobs"].values():
            for step in job.get("steps", []):
                if "platform_smoke.py" in (step.get("run") or ""):
                    runs_on = job["runs-on"]
                    if isinstance(runs_on, list):
                        ran_on.add("self-hosted-windows-11")
                    else:
                        ran_on.update(job.get("strategy", {}).get("matrix", {}).get("os")
                                      or [runs_on])
        self.assertEqual(ran_on, {"ubuntu-latest", "macos-latest", "self-hosted-windows-11"},
                         f"platform smoke 가 도는 자리: {sorted(ran_on)}")

    def test_the_publish_workflow_blocks_on_preflight(self):
        """릴리스 당일에만 도는 검사는 릴리스 당일에 처음 실패한다 — CI 에도 같은 것이 있어야 한다."""
        publish = (REPO / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        self.assertIn("publish_preflight.py", publish)
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("publish_preflight.py", ci)

    def test_the_smoke_survives_a_non_utf8_console(self):
        """Windows 기본 stdout 은 cp1252 다. 거기서 요약 한 줄이 죽으면 플랫폼 전체가 빨간불이다.

        원격에서 실제로 그렇게 났다 — 검사 7건이 모두 `OK` 를 찍은 **뒤** 마지막 한국어 요약에서
        UnicodeEncodeError 로 끝났다. `encoding` 검사는 설치본의 출력만 보기 때문에 스크립트
        자신의 출력 경로는 아무도 보지 않았다. 여기서는 cp1252 콘솔을 흉내내 그 경로를 건다."""
        done = subprocess.run(
            [sys.executable, str(SMOKE), "--help"], cwd=str(REPO), capture_output=True,
            env=dict(os.environ, PYTHONIOENCODING="cp1252"))
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        probe = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, {str(SMOKE.parent)!r}); import platform_smoke; "
             "print('통과 0 / 실패 0')"],
            capture_output=True, env=dict(os.environ, PYTHONIOENCODING="cp1252"))
        self.assertEqual(probe.returncode, 0,
                         "cp1252 콘솔에서 한국어 출력이 죽는다\n"
                         + probe.stderr.decode("utf-8", "replace"))

    def test_preflight_jobs_fetch_the_supported_floor_tag(self):
        """v0.9.84 fixture를 읽는 검사가 shallow checkout에서 이유 없이 실패하면 안 된다."""
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        release_job = ci.split("  release_evidence:", 1)[1]
        self.assertIn("fetch-depth: 0", release_job)
        publish = (REPO / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
        self.assertIn("fetch-depth: 0", publish)


def _ci_workflow():
    import yaml
    return yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"))


def _workflow_triggers(workflow):
    """`on:` 은 YAML 에서 **불리언 True 로 파싱된다.** 문자열 키로 찾으면 언제나 빈손이다."""
    return workflow.get("on", workflow.get(True))


# GitHub `if:` 식의 **좁은 부분집합**을 실제로 계산한다.
#
# 왜 문자열 포함 검사로 끝내지 않는가: 조건이 어긋나는 방식은 대개 문자열이 없어지는 것이
# 아니라 **뜻이 바뀌는 것**이다(`&&` 가 `||` 가 되거나, 비교 대상이 base 로 바뀌거나).
# 포함 검사는 그 전부를 통과시킨다. 그래서 fork PR·라벨 없음·push 를 실제 event 로 넣어
# 계산한다.
#
# 모르는 토큰은 **해석하지 않고 던진다.** 조건이 이 문법 밖으로 나가는 날 검사가 조용히
# 통과하면, 그때부터 이 검사는 아무것도 지키지 않으면서 지키는 것처럼 보인다.
_LITERAL = re.compile(r"^'([^']*)'$")
_CONTAINS = re.compile(r"^contains\(\s*([A-Za-z0-9_.*]+)\s*,\s*('[^']*')\s*\)$")


class UnsupportedCondition(Exception):
    """이 평가기가 모르는 문법. 통과가 아니라 실패로 떨어뜨리기 위한 것."""


def _lookup(path, context):
    value = context
    for part in path.split("."):
        if part == "*":
            return [item for item in value]
        # **null 속성은 오류가 아니다.** GitHub 에서 `github.event.label` 은 라벨과 무관한
        # 이벤트에서 null 이고, `null.name` 은 다시 null 이다(비교는 거짓이 된다). 그것을
        # 오류로 다루면 `synchronize` 반례가 "문법을 모른다" 로 떨어져, 실제로 무엇이 막는지를
        # 확인하지 못한 채 통과한다.
        if value is None:
            return None
        if not isinstance(value, dict) or part not in value:
            raise UnsupportedCondition(f"unknown context path: {path}")
        value = value[part]
    return value


def _operand(token, context):
    literal = _LITERAL.match(token)
    if literal:
        return literal.group(1)
    return _lookup(token, context)


def evaluate_condition(expression, context):
    terms = [term.strip() for term in re.split(r"&&", " ".join(expression.split()))]
    if any("||" in term for term in terms):
        raise UnsupportedCondition("this evaluator does not implement ||")
    for term in terms:
        found = _CONTAINS.match(term)
        if found:
            path, needle = found.groups()
            head, _, field = path.partition(".*.")
            haystack = _lookup(head, context)
            values = [item.get(field) for item in haystack] if field else haystack
            if _operand(needle, context) not in values:
                return False
            continue
        left, op, right = term.partition("==")
        if op != "==":
            raise UnsupportedCondition(f"unsupported term: {term}")
        if _operand(left.strip(), context) != _operand(right.strip(), context):
            return False
    return True


def _pull_request_event(*, repo="SeJonJ/SAGE", labels=(), event_name="pull_request",
                        action="labeled", label="run-win11-uninstall"):
    """GitHub 이 실제로 싣는 모양으로 만든다.

    `label` 은 **그 이벤트가 나른 라벨**이다 — `labeled`·`unlabeled` 에서만 값이 있고 나머지
    에서는 null 이다. `labels` 는 그 순간 PR 에 붙어 있는 라벨 전부다. 둘을 구별하지 않으면
    "지금 승인했다" 와 "전에 승인한 적이 있다" 가 같은 값이 되고, 이 job 의 계약은 정확히 그
    구별 위에 서 있다.
    """
    return {
        "github": None,
        "event_name": event_name,
        "repository": "SeJonJ/SAGE",
        "event": {
            "action": action,
            "label": {"name": label} if label else None,
            "pull_request": {"head": {"repo": {"full_name": repo}},
                             "labels": [{"name": name} for name in labels]},
        },
    }


APPROVAL_LABEL = "run-win11-uninstall"


def evidence_contract_problems(script):
    """증거 단계가 **실제로 대조하고 실패하는가**. 문제 목록을 돌려준다.

    문자열 존재만 보면 세 값을 찍기만 하고 넘어가는 단계도 통과한다 — 그 단계는 어긋난
    트리에서 증거를 만들었다고 말하면서 초록으로 끝난다. 그래서 보는 것은 셋이다: 실제
    트리를 읽었는가, 승인된 head 와 대조했는가, 어긋나면 실패하는가.

    `pwsh` 로 실행해 확인하지 않는 이유는, 그 인터프리터가 없는 머신에서 이 검사가 조용히
    건너뛰기 때문이다. 건너뛴 검사는 통과로 세어지고, 그것이 이 저장소가 반복해서 겪은
    실패 방식이다. 그래서 스크립트를 구조로 읽는다 — 그리고 이 읽기 자체가 무언가를
    지키는지는 mutation 으로 따로 확인한다.
    """
    problems = []
    lines = [line.strip() for line in script.splitlines() if line.strip()]

    def assigned_from(needle):
        for line in lines:
            if "=" in line and needle in line.split("=", 1)[1]:
                name = line.split("=", 1)[0].strip()
                if name.startswith("$"):
                    return name
        return None

    checked_out = assigned_from("git rev-parse HEAD")
    approved = assigned_from("github.event.pull_request.head.sha")
    if checked_out is None:
        problems.append("the checked-out commit is never read (git rev-parse HEAD)")
    if approved is None:
        problems.append("the approved head.sha is never captured")
    if checked_out and approved:
        guard = [line for line in lines
                 if line.startswith("if") and checked_out in line and approved in line]
        if not guard:
            problems.append("the two commits are never compared")
        elif not any("-ne" in line for line in guard):
            problems.append("the comparison does not fail on a mismatch")
        else:
            # 대조만 하고 넘어가면 어긋난 트리에서도 초록이다. 실패로 끝나야 한다.
            body = script.split(guard[0], 1)[1].split("}", 1)[0]
            if "throw" not in body and "exit 1" not in body:
                problems.append("a mismatch does not end the step non-zero")
    # `GITHUB_SHA` 는 merge 커밋일 수 있으므로 **일치를 요구하면 안 된다.**
    for line in lines:
        if line.startswith("if") and "GITHUB_SHA" in line and approved and approved in line:
            problems.append("GITHUB_SHA is required to equal head.sha, which is not true "
                            "for a pull_request event")
    return problems

class TestTheWindowsEvidenceJobIsFencedIn(unittest.TestCase):
    """self-hosted 러너는 **남의 코드를 내 머신에서 실행한다.**

    fork PR 이 여기 닿으면 그 PR 의 workflow 가 러너를 그대로 가져간다. 그리고 승인이 지속
    상태이면, 한 번 승인한 뒤 밀어 넣은 **검토하지 않은 커밋**이 자동으로 실행된다. 둘 다
    검사 하나가 빠지는 것과는 다른 종류의 사고다.
    """

    def setUp(self):
        self.workflow = _ci_workflow()
        self.job = self.workflow["jobs"]["windows11_uninstall"]
        # 평가기가 계산한 값이 아니라 **워크플로에 적힌 식**을 그대로 쓴다.
        self.condition = self.job["if"]

    def decide(self, condition=None, **event):
        return evaluate_condition(condition or self.condition,
                                  {"github": _pull_request_event(**event)})

    # ---- 문법 자체 ----

    def test_the_condition_is_written_in_the_grammar_this_test_can_check(self):
        """평가기가 모르는 문법으로 바뀌면 **통과가 아니라 실패**여야 한다."""
        with self.assertRaises(UnsupportedCondition):
            evaluate_condition("github.actor == 'x' || true", {"github": {"actor": "x"}})

    def test_the_condition_names_the_same_repository_comparison_explicitly(self):
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository",
                      " ".join(self.condition.split()))

    # ---- 필수 회귀 1~5 ----

    def test_only_a_labeled_event_with_this_label_runs(self):
        """1. 같은 저장소 PR 의 `run-win11-uninstall` **labeled 이벤트만** 실행."""
        self.assertTrue(self.decide(action="labeled", label=APPROVAL_LABEL))

    def test_a_new_commit_does_not_reuse_a_standing_label(self):
        """2. **이 rework 의 핵심.** 라벨이 남아 있어도 `synchronize` 는 실행하지 않는다.

        지속 상태로 보면 한 번의 승인이 이후 커밋 전부에 적용된다 — 검토한 커밋에 라벨을 붙여
        돌린 뒤 새 커밋을 밀면, 검토하지 않은 코드가 자기 머신에서 자동 실행된다. 그것은
        승인이 아니라 승인의 재사용이다.
        """
        self.assertFalse(self.decide(action="synchronize", label=None,
                                     labels=(APPROVAL_LABEL,)))

    def test_opening_or_reopening_a_labelled_pull_request_does_not_run(self):
        """3. `opened`·`reopened` 만으로는 실행하지 않는다 — 라벨이 이미 붙어 있어도."""
        for action in ("opened", "reopened"):
            with self.subTest(action=action):
                self.assertFalse(self.decide(action=action, label=None,
                                             labels=(APPROVAL_LABEL,)))

    def test_a_fork_pull_request_never_runs_even_when_labelled(self):
        """4. fork PR 은 라벨을 붙여도 실행하지 않는다. 라벨은 fork 쪽에서도 붙을 수 있다."""
        self.assertFalse(self.decide(repo="someone-else/SAGE",
                                     action="labeled", label=APPROVAL_LABEL))

    def test_removing_and_reattaching_the_label_runs_the_current_commit(self):
        """5. 라벨을 떼었다가 **현재 커밋에** 다시 붙이면 실행된다.

        떼는 사건(`unlabeled`)은 실행하지 않는다 — 그렇지 않으면 승인을 취소하는 행위가
        실행을 부른다.
        """
        self.assertFalse(self.decide(action="unlabeled", label=APPROVAL_LABEL))
        self.assertTrue(self.decide(action="labeled", label=APPROVAL_LABEL))

    def test_a_different_label_on_an_already_labelled_pull_request_does_not_run(self):
        """다른 라벨을 하나 더 붙이는 것으로 열리면, 승인은 다시 지속 상태가 된다."""
        self.assertFalse(self.decide(action="labeled", label="documentation",
                                     labels=(APPROVAL_LABEL, "documentation")))

    def test_a_push_to_main_does_not_run(self):
        """push 마다 열리면 이 머신은 실제 제거를 상시로 도는 자리가 된다."""
        self.assertFalse(self.decide(event_name="push", action="labeled",
                                     label=APPROVAL_LABEL))

    # ---- 필수 회귀 6~8: mutation ----
    #
    # 반례가 통과하는 것만으로는 그 반례가 무언가를 지킨다는 증거가 되지 않는다. 지키는 문장을
    # 하나씩 지우고, 지운 쪽이 **실제로 열리는지** 본다.

    def test_dropping_the_action_check_opens_the_unlabelled_event(self):
        """6. `event.action` 검사를 지우면 **라벨을 떼는 행위가 실행을 부른다.**

        `unlabeled` 이벤트도 `github.event.label` 에 그 라벨을 싣기 때문이다. 지금은
        `types` 에 `unlabeled` 가 없어 run 이 만들어지지 않지만, 방어를 trigger 목록 하나에만
        걸어 두면 그 목록이 늘어나는 날 조용히 열린다.
        """
        mutated = " ".join(self.condition.split()).replace(
            "github.event.action == 'labeled' && ", "")
        self.assertNotEqual(mutated, " ".join(self.condition.split()),
                            "지울 문장을 찾지 못했다 — 검사가 낡았다")
        self.assertTrue(evaluate_condition(
            mutated, {"github": _pull_request_event(action="unlabeled",
                                                    label=APPROVAL_LABEL)}),
            "관문을 지웠는데도 막힌다 — 이 대비가 성립하지 않는다")
        self.assertFalse(self.decide(action="unlabeled", label=APPROVAL_LABEL))
        types = _workflow_triggers(self.workflow)["pull_request"]["types"]
        self.assertNotIn("unlabeled", types, "두 번째 방어선도 열려 있다")

    def test_reverting_to_a_standing_label_check_reopens_the_reuse_hole(self):
        """7. `event.label.name` 을 `contains(labels)` 로 되돌리면 **지적된 구멍이 그대로 난다.**"""
        mutated = (" ".join(self.condition.split())
                   .replace("github.event.action == 'labeled' && ", "")
                   .replace(f"github.event.label.name == '{APPROVAL_LABEL}'",
                            f"contains(github.event.pull_request.labels.*.name, "
                            f"'{APPROVAL_LABEL}')"))
        self.assertIn("contains(", mutated, "되돌릴 문장을 찾지 못했다 — 검사가 낡았다")
        standing = {"github": _pull_request_event(action="synchronize", label=None,
                                                  labels=(APPROVAL_LABEL,))}
        self.assertTrue(evaluate_condition(mutated, standing),
                        "되돌렸는데도 막힌다 — 이 대비가 성립하지 않는다")
        self.assertFalse(evaluate_condition(self.condition, standing))

    def test_dropping_the_same_repository_check_opens_fork_pull_requests(self):
        """8. 저장소 대조를 지우면 fork PR 이 자기 머신에서 돈다."""
        one_line = " ".join(self.condition.split())
        mutated = one_line.replace(
            " && github.event.pull_request.head.repo.full_name == github.repository", "")
        self.assertNotEqual(mutated, one_line, "지울 문장을 찾지 못했다 — 검사가 낡았다")
        fork = {"github": _pull_request_event(repo="someone-else/SAGE",
                                              action="labeled", label=APPROVAL_LABEL)}
        self.assertTrue(evaluate_condition(mutated, fork),
                        "관문을 지웠는데도 막힌다 — 이 대비가 성립하지 않는다")
        self.assertFalse(evaluate_condition(self.condition, fork))

    # ---- trigger·권한·증거 ----

    def test_labelling_a_pull_request_starts_the_workflow(self):
        """`labeled` 가 없으면 라벨을 붙여도 run 이 생기지 않는다 — 조건만 참인 채 아무 일도
        일어나지 않고, 사용자는 빈 커밋을 밀어야 한다."""
        triggers = _workflow_triggers(self.workflow)
        types = triggers["pull_request"]["types"]
        for kind in ("opened", "synchronize", "reopened", "labeled"):
            self.assertIn(kind, types, f"pull_request types 에 {kind} 가 없다")

    def test_the_job_holds_no_write_permission(self):
        """self-hosted 러너에서 쓰기 토큰을 들고 도는 것은, 실행되는 코드가 러너 머신뿐 아니라
        저장소까지 건드릴 수 있다는 뜻이다."""
        self.assertEqual(self.job.get("permissions"), {"contents": "read"})

    def test_the_checkout_pins_the_approved_commit_and_drops_credentials(self):
        """승인한 커밋을 그대로 받아야 증거가 어느 트리에서 나왔는지 말할 수 있다."""
        checkout = next(step for step in self.job["steps"]
                        if str(step.get("uses", "")).startswith("actions/checkout"))
        options = checkout.get("with") or {}
        self.assertEqual(options.get("ref"),
                         "${{ github.event.pull_request.head.sha }}",
                         "기본 checkout 은 base 와 합친 merge 커밋이다")
        self.assertIs(options.get("persist-credentials"), False)

    def evidence_step(self):
        return next(step for step in self.job["steps"]
                    if "Evidence commit" in (step.get("name") or ""))

    def test_the_evidence_step_fails_when_the_tree_is_not_the_approved_commit(self):
        """A7·A19 는 **어느 커밋에서 돌았는가** 가 곧 증거의 내용이다.

        세 값을 찍기만 하고 넘어가면, 어긋난 트리에서 만든 로그가 증거라고 말하면서 초록으로
        끝난다. 대조하고 실패해야 그 로그가 자기가 무엇을 검증했는지 말할 수 있다.
        """
        step = self.evidence_step()
        self.assertEqual(step.get("shell"), "pwsh")
        self.assertEqual(evidence_contract_problems(step["run"]), [])

    def test_the_evidence_step_does_not_require_github_sha_to_match(self):
        """`pull_request` 에서 `GITHUB_SHA` 는 **merge 커밋**일 수 있다.

        이 job 은 승인한 `head.sha` 를 일부러 checkout 하므로 두 값은 정상적으로 다르다.
        일치를 요구하면 정상 실행이 붉어지고, 로그를 읽는 사람은 정상 차이를 결함으로 읽는다.
        """
        run = self.evidence_step()["run"]
        self.assertIn("GITHUB_SHA", run, "참고값조차 남기지 않으면 되짚을 실마리가 없다")
        guards = [line.strip() for line in run.splitlines()
                  if line.strip().startswith("if")]
        for line in guards:
            self.assertNotIn("GITHUB_SHA", line,
                             "정상적으로 다를 수 있는 두 값의 일치를 요구한다")

    def test_the_evidence_contract_check_actually_catches_a_broken_step(self):
        """**mutation.** 검사기가 무엇을 지키는지 확인한다 — 구조로 읽는 검사일수록 필요하다."""
        intact = self.evidence_step()["run"]
        self.assertEqual(evidence_contract_problems(intact), [])
        mutations = {
            "대조 제거": lambda t: "\n".join(
                line for line in t.splitlines()
                if not line.strip().startswith("if") and "throw" not in line
                and not line.strip() == "}"),
            "실패 제거": lambda t: t.replace("throw ", "echo "),
            "비교 뒤집기": lambda t: t.replace("-ne", "-eq"),
            "트리를 읽지 않음": lambda t: t.replace("git rev-parse HEAD", '"unknown"'),
        }
        for label, mutate in mutations.items():
            with self.subTest(mutation=label):
                broken = mutate(intact)
                self.assertNotEqual(broken, intact, f"{label}: 바꿀 자리를 찾지 못했다")
                self.assertTrue(evidence_contract_problems(broken),
                                f"{label}: 부순 단계를 통과시킨다")

    # ---- 러너·단계 ----

    def test_the_runner_is_pinned_to_the_supported_environment(self):
        self.assertEqual(self.job["runs-on"],
                         ["self-hosted", "windows", "x64", "win11", "sage-uninstall"])

    def test_the_fail_closed_gate_runs_before_every_other_script(self):
        """게이트는 **맨 앞**이어야 한다 — 제거 검사보다 앞이면 충분하지 않다.

        진단 단계들은 "보고만 한다" 고 적혀 있지만 실제로는 native 호출을 하고, capability
        report 의 `real_run()` 은 실제 install·uninstall 까지 돈다. 게이트를 그 뒤에 두면
        잘못 배정된 러너에서 **막으려던 mutation 이 진단을 찍는 과정에서 그대로 일어난다.**
        """
        runs = [step.get("run") or "" for step in self.job["steps"]]
        gate = next(i for i, run in enumerate(runs) if "--require-product-support" in run)
        for i, run in enumerate(runs):
            if "scripts/ci/" in run and i != gate:
                self.assertGreater(i, gate,
                                   f"게이트보다 먼저 도는 검사 스크립트가 있다: {run.strip()}")

    def test_every_required_windows_check_runs_in_this_job(self):
        runs = " ".join(step.get("run") or "" for step in self.job["steps"])
        for script in ("windows_rename_probe.py", "windows_capability_report.py",
                       "platform_smoke.py", "uninstall_smoke.py",
                       "uninstall_race_smoke.py", "uninstall_core_checks.py"):
            self.assertIn(script, runs)

    def test_the_uninstall_checks_run_on_three_pythons_and_platform_smoke_on_one(self):
        versions = self.job["strategy"]["matrix"]["python-version"]
        self.assertEqual(versions, ["3.10", "3.11", "3.12"])
        smoke = next(step for step in self.job["steps"]
                     if "platform_smoke.py" in (step.get("run") or ""))
        self.assertEqual(smoke.get("if"), "matrix.python-version == '3.12'")
        for step in self.job["steps"]:
            if "uninstall_" in (step.get("run") or ""):
                self.assertIsNone(step.get("if"),
                                  f"uninstall 검사가 Python 하나로 좁혀졌다: {step.get('name')}")

    def test_the_strict_mode_is_actually_set_on_the_removal_evidence(self):
        """엄격 모드가 없으면 정책이 막는 러너에서도 이 job 이 초록으로 끝난다."""
        for step in self.job["steps"]:
            run = step.get("run") or ""
            if "uninstall_smoke.py" in run or "uninstall_core_checks.py" in run:
                self.assertEqual(step.get("env", {})
                                 .get("SAGE_UNINSTALL_REQUIRE_PRODUCT_SUPPORT"), "1",
                                 f"{step.get('name')} 에 엄격 모드가 없다")

    def test_the_workflow_does_not_grep_stdout_to_decide(self):
        """어긋난 grep 은 **항상 통과**한다 — 없는 문자열을 못 찾은 것과 문제가 없는 것이
        같은 결과로 떨어지기 때문이다. 판정은 스크립트가 자기 실행 결과로 내린다."""
        for step in self.job["steps"]:
            run = step.get("run") or ""
            for banned in ("grep", "Select-String", "findstr"):
                self.assertNotIn(banned, run, f"{step.get('name')} 이 출력 문자열로 판정한다")


class TestTheHostedMatricesKeepTheirPosixCoverage(unittest.TestCase):
    """Windows 를 옮기면서 **기존 두 OS 를 같이 잃는** 것이 가장 흔한 사고다."""

    def setUp(self):
        self.jobs = _ci_workflow()["jobs"]

    def test_the_platform_matrix_still_covers_ubuntu_and_macos(self):
        matrix = self.jobs["platform"]["strategy"]["matrix"]
        self.assertEqual(matrix["os"], ["ubuntu-latest", "macos-latest"])

    def test_the_uninstall_matrix_still_covers_ubuntu_and_macos_on_three_pythons(self):
        matrix = self.jobs["uninstall_matrix"]["strategy"]["matrix"]
        self.assertEqual(matrix["os"], ["ubuntu-latest", "macos-latest"])
        self.assertEqual(matrix["python-version"], ["3.10", "3.11", "3.12"])

    def test_the_hosted_matrices_no_longer_claim_windows_evidence(self):
        """server SKU 러너의 초록을 데스크톱 증거로 읽는 자리를 아예 없앤다."""
        for name in ("platform", "uninstall_matrix"):
            matrix = self.jobs[name]["strategy"]["matrix"]
            self.assertNotIn("windows-latest", matrix["os"])

    def test_the_hook_regression_and_release_jobs_are_untouched(self):
        self.assertEqual(self.jobs["test"]["runs-on"], "ubuntu-latest")
        self.assertEqual(self.jobs["test"]["strategy"]["matrix"]["python-version"],
                         ["3.10", "3.11", "3.12"])
        self.assertEqual(self.jobs["release_evidence"]["runs-on"], "ubuntu-latest")
        self.assertEqual(self.jobs["packaging"]["runs-on"], "ubuntu-latest")


class TestTheEngineIsNotStaleAgainstItself(unittest.TestCase):
    """레포 자신의 manifest 가 자기 소스와 맞는가.

    hook runtime 이나 게이트 core 를 고치면 `hook_runtime_hash`·`canonical_hash` 가 낡는다.
    CI 는 그걸 `sage validate --check --schema` 로 잡지만 로컬 하네스는 보지 않았고, 그래서 이
    브랜치에서만 재스탬프 커밋이 7번 나왔다 — 매번 push 한 뒤 원격에서 처음 알았다는 뜻이다.

    이 검사는 CI 와 **같은 명령**을 돌린다. 하네스가 초록인데 CI 가 빨간 구간을 없애는 것이
    목적이라, 여기서만 통과하는 완화된 판정을 따로 만들지 않는다."""

    def test_self_validate_is_clean(self):
        done = subprocess.run([sys.executable, "-m", "sage", "validate", "--check", "--schema"],
                              cwd=str(REPO), capture_output=True, text=True,
                              env=dict(os.environ, PYTHONPATH=str(REPO)))
        self.assertEqual(done.returncode, 0,
                         "레포가 자기 manifest 와 어긋난다 — 재계산한 해시를 "
                         "docs/sage_harness/.manifest.json 에 반영하세요.\n"
                         + done.stdout[-2000:] + done.stderr[-2000:])


class TestReadinessDocument(unittest.TestCase):
    def test_both_languages_exist_and_link_to_each_other(self):
        korean = REPO / "docs" / "release-readiness.md"
        english = REPO / "docs" / "release-readiness.en.md"
        self.assertTrue(korean.is_file() and english.is_file())
        self.assertIn("release-readiness.en.md", korean.read_text(encoding="utf-8"))
        self.assertIn("release-readiness.md", english.read_text(encoding="utf-8"))

    def test_released_is_not_a_readiness_state(self):
        """도구는 릴리스 가능 여부까지만 말한다 — 그 경계를 넘으면 승인 절차가 사라진다."""
        for name in ("release-readiness.md", "release-readiness.en.md"):
            body = (REPO / "docs" / name).read_text(encoding="utf-8")
            self.assertIn("READY_FOR_USER_RELEASE_DECISION", body)
            self.assertIn("NOT READY", body)

    def test_the_english_mirror_has_no_korean_prose(self):
        import re as _re
        body = (REPO / "docs" / "release-readiness.en.md").read_text(encoding="utf-8")
        body = _re.sub(r"`[^`]*`", "", body)
        body = _re.sub(r"\[[^\]]*\]\([^)]*\)", "", body)
        self.assertIsNone(_re.search(r"[가-힣]", body))


class TestRunAllRegistration(unittest.TestCase):
    def test_this_suite_is_wired(self):
        self.assertIn("test_release_readiness.py",
                      (HERE / "run-all.sh").read_text(encoding="utf-8"))


def _load(path, name):
    import importlib.util
    sys.path.insert(0, str(REPO))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_preflight():
    return _load(PREFLIGHT, "_preflight")


def _load_smoke():
    return _load(SMOKE, "_smoke")


if __name__ == "__main__":
    unittest.main()
