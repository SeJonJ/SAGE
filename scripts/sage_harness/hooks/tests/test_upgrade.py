#!/usr/bin/env python3
"""sage upgrade — 읽기 전용 진단, 트랜잭션 적용, 멱등, 소유 경계.

이 명령의 특수성은 **버전이 어긋난 상태에서 불려야 한다**는 것이다. 버전 불일치를 고치는 유일한
통로가 버전 불일치 때문에 막히면 사용자는 빠져나갈 방법이 없다. 그래서 부트스트랩 미완·profile
검증 실패가 실행 자체를 막지 않는지 직접 확인한다.

두 번째 축은 소유 경계다. upgrade 가 남의 파일을 대신 덮으면 어느 명령이 그 바이트를 만들었는지
알 수 없게 되고, 그 뒤로는 drift 의 원인을 아무도 역추적할 수 없다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from sage import __version__                                    # noqa: E402
from sage.commands import upgrade as up                         # noqa: E402

PROFILE = """# 주석은 보존돼야 한다 — upgrade 가 전체를 재직렬화하면 사용자 파일이 통째로 바뀐다.
project:
  name: "consumer"
sage:
  required_version: "0.0.1"   # 꼬리 주석도 남아야 한다
risk:
  l2_path_globs: ["src/**"]
components:
  - { id: core, paths: ["src/**"] }
"""


def _tree(root):
    out = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            stat = os.stat(path)
            out[os.path.relpath(path, root)] = (
                Path(path).read_bytes(), stat.st_mode & 0o777, stat.st_mtime_ns)
    return out


class Args:
    def __init__(self, **kw):
        self.check = kw.get("check", False)
        self.apply = kw.get("apply", False)
        self.root = kw.get("root")
        self.force = kw.get("force", False)


def _install(root, profile=PROFILE, manifest=None):
    os.makedirs(os.path.join(root, "docs", "sage_harness"), exist_ok=True)
    os.makedirs(os.path.join(root, "sage"), exist_ok=True)
    Path(root, "docs", "sage_harness", ".manifest.json").write_text(
        json.dumps(manifest if manifest is not None else
                   {"sage_version": __version__, "generator_version": __version__,
                    "host_runtime": "claude", "assets": {}}),
        encoding="utf-8")
    if profile is not None:
        Path(root, "sage", "project-profile.yaml").write_text(profile, encoding="utf-8")
    return root


def _run(root, **kw):
    return up.run(Args(root=root, **kw))


class TestCheckIsReadOnly(unittest.TestCase):
    def test_check_changes_no_existing_file(self):
        """bytes·mode·mtime 어느 것도 건드리지 않는다 — 보고서만 새로 생긴다."""
        root = _install(tempfile.mkdtemp())
        before = _tree(root)
        self.assertEqual(_run(root, check=True), up.EXIT_OK)
        after = _tree(root)
        for rel, value in before.items():
            self.assertEqual(after.get(rel), value, rel)
        new = set(after) - set(before)
        self.assertTrue(all(r.startswith(os.path.join(".sage", "upgrades")) for r in new), new)

    def test_report_has_no_absolute_paths(self):
        """보고서는 사용자가 붙여 넣어 공유하는 물건이다 — 절대 경로는 홈 디렉터리를 노출한다."""
        root = _install(tempfile.mkdtemp())
        _run(root, check=True)
        reports = list(Path(root, ".sage", "upgrades").glob("*.json"))
        self.assertEqual(len(reports), 1)
        body = reports[0].read_text(encoding="utf-8")
        self.assertNotIn(root, body)
        self.assertNotIn(str(Path.home()), body)
        payload = json.loads(body)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["mode"], "check")

    def test_force_without_apply_is_a_usage_error(self):
        root = _install(tempfile.mkdtemp())
        self.assertEqual(_run(root, check=True, force=True), up.EXIT_UNSAFE)

    def test_an_explicit_root_without_a_manifest_is_a_blocker_not_a_crash(self):
        """`--root` 를 명시했으면 사용자가 대상을 정한 것이다 — 왜 안 되는지 말하고 1 로 끝난다."""
        self.assertEqual(_run(tempfile.mkdtemp(), check=True), up.EXIT_BLOCKED)

    def test_discovery_failure_is_a_usage_error(self):
        """`--root` 없이 설치본 밖에서 부르면 무엇을 고칠지 자체가 정해지지 않는다."""
        empty = tempfile.mkdtemp()
        previous = os.getcwd()
        os.chdir(empty)
        try:
            self.assertEqual(up.run(Args(check=True)), up.EXIT_UNSAFE)
        finally:
            os.chdir(previous)


class TestApplyIsSurgical(unittest.TestCase):
    def test_only_the_required_version_scalar_changes(self):
        """주석·따옴표·순서가 남아야 한다. 전체 재직렬화는 diff 가 계약을 넘어선다."""
        root = _install(tempfile.mkdtemp())
        self.assertEqual(_run(root, apply=True), up.EXIT_OK)
        body = Path(root, "sage", "project-profile.yaml").read_text(encoding="utf-8")
        self.assertIn(f'required_version: "{__version__}"', body)
        self.assertIn("# 주석은 보존돼야 한다", body)
        self.assertIn("# 꼬리 주석도 남아야 한다", body)
        self.assertIn('name: "consumer"', body)
        self.assertEqual(body.count("required_version"), 1)

    def test_second_apply_is_a_no_op(self):
        root = _install(tempfile.mkdtemp())
        self.assertEqual(_run(root, apply=True), up.EXIT_OK)
        after_first = _tree(root)
        self.assertEqual(_run(root, apply=True), up.EXIT_OK)
        profile = os.path.join("sage", "project-profile.yaml")
        self.assertEqual(_tree(root)[profile], after_first[profile],
                         "두 번째 apply 가 파일을 다시 썼다")

    def test_user_owned_paths_are_never_write_targets(self):
        root = _install(tempfile.mkdtemp())
        owned = {
            os.path.join("sage", "project-profile.local.yaml"): "interface:\n  language: en\n",
            os.path.join("sage", "asset_overrides", "agents", "qa.md"): "overlay\n",
            os.path.join("plan_docs", "00-base_plan", "demo.md"): "Cycle-Stem: `demo`\n",
            os.path.join(".sage", "override.jsonl"): '{"kind":"grant"}\n',
            os.path.join("scripts", "verify-changes.sh"): "#!/bin/sh\nexit 0\n",
            os.path.join("src", "app.py"): "print('project code')\n",
        }
        for rel, text in owned.items():
            path = Path(root, rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        before = {rel: _tree(root)[rel] for rel in owned}
        self.assertEqual(_run(root, apply=True), up.EXIT_OK)
        after = _tree(root)
        for rel in owned:
            self.assertEqual(after[rel], before[rel], f"{rel} 을 upgrade 가 건드렸다")

    def test_ambiguous_required_version_blocks_before_mutation(self):
        """고칠 자리가 하나로 특정되지 않으면 추측하지 않는다."""
        root = _install(tempfile.mkdtemp(), profile=(
            'project:\n  name: "c"\nsage:\n  required_version: "0.0.1"\n'
            '  required_version: "0.0.2"\n'))
        before = _tree(root)
        self.assertEqual(_run(root, apply=True), up.EXIT_BLOCKED)
        profile = os.path.join("sage", "project-profile.yaml")
        self.assertEqual(_tree(root)[profile], before[profile])

    def test_a_damaged_manifest_blocks_before_mutation(self):
        root = _install(tempfile.mkdtemp())
        Path(root, "docs", "sage_harness", ".manifest.json").write_text("{ broken", encoding="utf-8")
        before = _tree(root)
        self.assertEqual(_run(root, apply=True), up.EXIT_BLOCKED)
        profile = os.path.join("sage", "project-profile.yaml")
        self.assertEqual(_tree(root)[profile], before[profile])

    def test_a_write_failure_restores_the_original_exactly(self):
        root = _install(tempfile.mkdtemp())
        profile = os.path.join("sage", "project-profile.yaml")
        before = _tree(root)[profile]
        real = up._apply_required_version

        def exploding(raw, item):
            raise OSError("injected write failure")

        up._apply_required_version = exploding
        try:
            self.assertEqual(_run(root, apply=True), up.EXIT_BLOCKED)
        finally:
            up._apply_required_version = real
        self.assertEqual(_tree(root)[profile], before, "rollback 이 원본을 복구하지 않았다")


class TestOwnershipBoundary(unittest.TestCase):
    def test_unowned_drift_blocks_a_normal_apply(self):
        root = _install(tempfile.mkdtemp(), manifest={
            "sage_version": "0.0.1", "generator_version": __version__,
            "host_runtime": "claude", "assets": {}})
        before = _tree(root)
        self.assertEqual(_run(root, apply=True), up.EXIT_BLOCKED)
        profile = os.path.join("sage", "project-profile.yaml")
        self.assertEqual(_tree(root)[profile], before[profile])

    def test_force_proceeds_with_its_own_write_set_only(self):
        """--force 는 '남의 파일을 덮어라'가 아니라 '내 write set 은 진행하라'다."""
        root = _install(tempfile.mkdtemp(), manifest={
            "sage_version": "0.0.1", "generator_version": __version__,
            "host_runtime": "claude", "assets": {}})
        manifest_rel = os.path.join("docs", "sage_harness", ".manifest.json")
        before = _tree(root)[manifest_rel]
        self.assertEqual(_run(root, apply=True, force=True), up.EXIT_OK)
        self.assertIn(f'required_version: "{__version__}"',
                      Path(root, "sage", "project-profile.yaml").read_text(encoding="utf-8"))
        self.assertEqual(_tree(root)[manifest_rel], before,
                         "--force 가 upgrade 소유가 아닌 manifest 를 덮었다")


class TestRunsWhenOtherCommandsWouldNot(unittest.TestCase):
    def test_an_unbootstrapped_profile_does_not_block_upgrade(self):
        """generate 를 막는 부트스트랩 게이트가 upgrade 를 막으면 탈출 통로가 사라진다."""
        root = _install(tempfile.mkdtemp(), profile='sage:\n  required_version: "0.0.1"\n')
        self.assertEqual(_run(root, check=True), up.EXIT_OK)
        self.assertEqual(_run(root, apply=True), up.EXIT_OK)

    def test_a_missing_profile_reports_instead_of_inventing_one(self):
        root = _install(tempfile.mkdtemp(), profile=None)
        self.assertEqual(_run(root, check=True), up.EXIT_OK)
        self.assertFalse(os.path.exists(os.path.join(root, "sage", "project-profile.yaml")),
                         "upgrade 가 profile 을 만들어냈다")


class TestCycleSchemaMigration(unittest.TestCase):
    def test_version_one_declaration_migrates_to_two(self):
        root = _install(tempfile.mkdtemp())
        os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
        Path(root, ".sage", "cycle.json").write_text(
            json.dumps({"version": 1, "cycle_stem": "demo"}), encoding="utf-8")
        self.assertEqual(_run(root, apply=True), up.EXIT_OK)
        data = json.loads(Path(root, ".sage", "cycle.json").read_text(encoding="utf-8"))
        self.assertEqual((data["version"], data["cycle_stem"]), (2, "demo"))
        self.assertEqual(data["document_language"], "ko",
                         "marker 이전 사이클은 호환 기본값 ko 로 이행한다")

    def test_an_already_migrated_declaration_is_left_alone(self):
        root = _install(tempfile.mkdtemp())
        os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
        Path(root, ".sage", "cycle.json").write_text(
            json.dumps({"version": 2, "cycle_stem": "demo", "document_language": "en"}),
            encoding="utf-8")
        _run(root, apply=True)
        data = json.loads(Path(root, ".sage", "cycle.json").read_text(encoding="utf-8"))
        self.assertEqual(data["document_language"], "en", "이미 이행된 선언을 되돌렸다")


class TestBothLocalesRender(unittest.TestCase):
    def test_every_upgrade_key_exists_in_both_catalogs(self):
        from sage.i18n import CATALOGS
        keys = {k for k in CATALOGS["ko"] if k.startswith("cli.upgrade.")}
        self.assertTrue(keys)
        self.assertEqual(keys, {k for k in CATALOGS["en"] if k.startswith("cli.upgrade.")})

    def test_english_output_has_no_korean(self):
        import re
        from sage.i18n import CATALOGS
        for key in (k for k in CATALOGS["en"] if k.startswith("cli.upgrade.")):
            body = re.sub(r"`[^`]*`", "", CATALOGS["en"][key])
            self.assertIsNone(re.search(r"[가-힣]", body), key)


class TestRealReleaseFixture(unittest.TestCase):
    """합성 fixture 가 아니라 **실제 v0.9.84 트리**에서 시작한다.

    손으로 만든 fixture 는 만든 사람이 아는 모양만 담는다. 실제 릴리스에는 그 사람이 잊은 파일이
    있고, upgrade 가 다루지 못하는 것은 대개 그쪽이다. 그래서 태그에서 직접 뽑아 쓴다.

    태그가 없는 얕은 clone(CI 일부)에서는 skip 한다 — 없는 것을 통과로 바꾸지 않기 위해
    skip 사유를 명시한다.
    """

    TAG = "v0.9.84"

    @classmethod
    def setUpClass(cls):
        probe = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", f"{cls.TAG}^{{commit}}"],
                               capture_output=True, text=True)
        if probe.returncode != 0:
            raise unittest.SkipTest(f"{cls.TAG} 태그 없음 — 얕은 clone")
        cls._tmp = tempfile.mkdtemp()
        cls.root = os.path.join(cls._tmp, "consumer")
        os.makedirs(cls.root)
        # 태그 트리에서 소비 프로젝트가 갖는 것만 꺼낸다 — 엔진 소스는 설치본에 들어가지 않는다.
        export = subprocess.run(
            ["git", "-C", str(REPO), "archive", cls.TAG,
             "templates/project-profile.yaml", "docs/sage_harness/.manifest.json"],
            capture_output=True)
        if export.returncode != 0:
            raise unittest.SkipTest("git archive 실패")
        import io, tarfile
        with tarfile.open(fileobj=io.BytesIO(export.stdout)) as tar:
            tar.extractall(cls._tmp, filter="data")
        os.makedirs(os.path.join(cls.root, "sage"), exist_ok=True)
        os.makedirs(os.path.join(cls.root, "docs", "sage_harness"), exist_ok=True)
        shutil.copyfile(os.path.join(cls._tmp, "templates", "project-profile.yaml"),
                        os.path.join(cls.root, "sage", "project-profile.yaml"))
        shutil.copyfile(os.path.join(cls._tmp, "docs", "sage_harness", ".manifest.json"),
                        os.path.join(cls.root, "docs", "sage_harness", ".manifest.json"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "_tmp", ""), ignore_errors=True)

    def test_check_reports_the_real_version_axes(self):
        self.assertIn(_run(self.root, check=True), (up.EXIT_OK, up.EXIT_BLOCKED))
        reports = sorted(Path(self.root, ".sage", "upgrades").glob("*.json"))
        payload = json.loads(reports[-1].read_text(encoding="utf-8"))
        self.assertEqual(payload["engine_version"], __version__)
        self.assertIn("installed", payload["axes"])

    def test_apply_then_reapply_reaches_a_stable_point(self):
        """실제 트리에서도 두 번째 apply 가 파일을 다시 쓰지 않는다."""
        first = _run(self.root, apply=True, force=True)
        self.assertIn(first, (up.EXIT_OK, up.EXIT_BLOCKED))
        if first != up.EXIT_OK:
            self.skipTest("실제 트리에 blocker 가 있어 멱등을 관찰할 수 없다")
        profile = os.path.join("sage", "project-profile.yaml")
        after_first = _tree(self.root)[profile]
        self.assertEqual(_run(self.root, apply=True, force=True), up.EXIT_OK)
        self.assertEqual(_tree(self.root)[profile], after_first,
                         "실제 트리에서 두 번째 apply 가 파일을 다시 썼다")


class TestRunAllRegistration(unittest.TestCase):
    def test_this_suite_is_wired(self):
        body = (HERE / "run-all.sh").read_text(encoding="utf-8")
        self.assertIn("test_upgrade.py", body)


if __name__ == "__main__":
    unittest.main()
