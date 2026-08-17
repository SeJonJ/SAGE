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

    def test_the_ci_workflow_runs_it_on_three_operating_systems(self):
        workflow = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("platform_smoke.py", workflow)
        for runner in ("ubuntu-latest", "macos-latest", "windows-latest"):
            self.assertIn(runner, workflow)

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
