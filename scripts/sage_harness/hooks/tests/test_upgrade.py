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


# 비교에서 빼는 것. `__pycache__` 는 재생성 캐시라 내용이 실행마다 달라지고,
# `.sage/upgrades` 는 **실패 기록이 롤백에서 살아남아야** 하므로 의도적으로 남는다 —
# 무엇이 왜 실패했는지 사용자가 읽을 수 있어야 한다.
_TREE_SKIP_DIRS = {"__pycache__", ".git", ".venv"}
_TREE_SKIP_PREFIX = (os.path.join(".sage", "upgrades") + os.sep,)


def _tree(root):
    out = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _TREE_SKIP_DIRS]
        for name in files:
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root)
            if any(rel.startswith(prefix) for prefix in _TREE_SKIP_PREFIX):
                continue
            stat = os.stat(path)
            out[rel] = (Path(path).read_bytes(), stat.st_mode & 0o777, stat.st_mtime_ns)
    return out


class Args:
    def __init__(self, **kw):
        self.check = kw.get("check", False)
        self.apply = kw.get("apply", False)
        self.root = kw.get("root")
        self.force = kw.get("force", False)


def _install(root, profile=PROFILE, manifest=None, real=True):
    """실제 설치본을 만든다.

    손으로 만든 manifest 는 upgrade 가 선언 값만 고치던 시절의 fixture 였다. upgrade 가 이제
    CORE 배포·hook 재생성·overlay 재적용까지 하므로, **가짜 트리에서는 그 단계들이 검증되지
    않는다** — 정작 사용자가 겪는 경로가 미검증으로 남는다.

    `real=False` 는 판정 단계(blocker)만 보는 테스트용이다. 그 경우 위임 단계까지 가지 않는다.
    """
    if real:
        done = subprocess.run(
            [sys.executable, "-m", "sage", "install", "--host", "claude",
             "--prefix", "smoke", "--dest", str(root)],
            cwd=str(REPO), env=dict(os.environ, PYTHONPATH=str(REPO)),
            capture_output=True, text=True)
        assert done.returncode == 0, f"fixture install 실패:\n{done.stdout}\n{done.stderr}"
    else:
        os.makedirs(os.path.join(root, "docs", "sage_harness"), exist_ok=True)
        os.makedirs(os.path.join(root, "sage"), exist_ok=True)
    if manifest is not None:
        Path(root, "docs", "sage_harness", ".manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8")
    elif not real:
        Path(root, "docs", "sage_harness", ".manifest.json").write_text(
            json.dumps({"sage_version": __version__, "generator_version": __version__,
                        "host_runtime": "claude", "assets": {}}), encoding="utf-8")
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
            os.path.join("sage", "asset_overrides", "agents", "implementer-a.md"):
                "<!-- overlay -->\nproject rule\n",
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
        root = _install(tempfile.mkdtemp(), real=False, profile=(
            'project:\n  name: "c"\nsage:\n  required_version: "0.0.1"\n'
            '  required_version: "0.0.2"\n'))
        before = _tree(root)
        self.assertEqual(_run(root, apply=True), up.EXIT_BLOCKED)
        profile = os.path.join("sage", "project-profile.yaml")
        self.assertEqual(_tree(root)[profile], before[profile])

    def test_a_damaged_manifest_blocks_before_mutation(self):
        root = _install(tempfile.mkdtemp(), real=False)
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
        root = _install(tempfile.mkdtemp(), real=False, manifest={
            "sage_version": "0.0.1", "generator_version": __version__,
            "host_runtime": "claude", "assets": {}})
        before = _tree(root)
        self.assertEqual(_run(root, apply=True), up.EXIT_BLOCKED)
        profile = os.path.join("sage", "project-profile.yaml")
        self.assertEqual(_tree(root)[profile], before[profile])

    def test_force_proceeds_past_drift_it_does_not_own(self):
        """--force 는 "덮는 범위를 넓혀라"가 아니라 "소유하지 않은 drift 가 있어도 진행하라"다.

        manifest 는 이제 갱신된다 — upgrade 가 CORE 배포를 위임하므로 그 단계의 주인인
        `install` 이 receipt 를 다시 쓴다. 바뀌는 것 자체가 계약이고 **누가 썼는가**가 경계다.
        """
        root = _install(tempfile.mkdtemp())
        Path(root, "sage", "project-profile.yaml").write_text(PROFILE, encoding="utf-8")
        manifest_path = Path(root, "docs", "sage_harness", ".manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["sage_version"] = "0.0.1"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        self.assertEqual(_run(root, apply=True), up.EXIT_BLOCKED,
                         "소유하지 않은 drift 가 정상 apply 를 막지 못했다")
        self.assertEqual(_run(root, apply=True, force=True), up.EXIT_OK)
        self.assertIn(f'required_version: "{__version__}"',
                      Path(root, "sage", "project-profile.yaml").read_text(encoding="utf-8"))
        refreshed = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(refreshed["sage_version"], __version__,
                         "위임한 install 단계가 receipt 를 갱신하지 않았다")


class TestManagedAssetDelivery(unittest.TestCase):
    """**신규 managed CORE 파일이 실제로 배포되는가.**

    이 사이클이 `language-policy.md` 를 새 CORE 자산으로 추가했다. 선언 값만 고치는 upgrade 는
    사용자에게 "업그레이드했다"고 말하면서 그 파일을 주지 않는다 — 그러면 정책 문서를 참조하는
    모든 안내가 없는 파일을 가리킨다. 조용히 통과하면 안 되는 자리라 직접 확인한다.
    """

    POLICY_REL = os.path.join("docs", "agent", "language-policy.md")

    def _aged_install(self):
        """설치 후 신규 CORE 자산과 receipt 를 지워 구버전 소비자를 만든다."""
        root = _install(tempfile.mkdtemp())
        Path(root, "sage", "project-profile.yaml").write_text(PROFILE, encoding="utf-8")
        policy = Path(root, self.POLICY_REL)
        if policy.is_file():
            policy.unlink()
        manifest_path = Path(root, "docs", "sage_harness", ".manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["sage_version"] = "0.9.84"
        renders = manifest.get("core_renders")
        if isinstance(renders, dict):
            for key in [k for k in renders if "language-policy" in k]:
                renders.pop(key)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return root, manifest_path

    def test_a_new_core_asset_and_its_receipt_arrive_together(self):
        root, manifest_path = self._aged_install()
        self.assertFalse(Path(root, self.POLICY_REL).is_file(), "전제: 신규 자산이 없는 상태")

        self.assertEqual(_run(root, apply=True, force=True), up.EXIT_OK)

        self.assertTrue(Path(root, self.POLICY_REL).is_file(),
                        "upgrade 후에도 신규 CORE 자산이 배포되지 않았다")
        renders = json.loads(manifest_path.read_text(encoding="utf-8")).get("core_renders") or {}
        self.assertTrue(any("language-policy" in key for key in renders),
                        f"자산은 배포됐으나 receipt 가 없다: {sorted(renders)[:5]}")

    def test_hooks_are_regenerated_so_validate_is_not_stale(self):
        """선언만 고치면 hook 산출물이 낡은 채 남아 validate 가 STALE 로 끝난다."""
        root, _ = self._aged_install()
        self.assertEqual(_run(root, apply=True, force=True), up.EXIT_OK)
        done = subprocess.run(
            [sys.executable, "-m", "sage", "validate", "--check"],
            cwd=root, env=dict(os.environ, PYTHONPATH=str(REPO)),
            capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 3,
                            f"upgrade 뒤에도 STALE 이다 — hook 재생성이 제 일을 못 했다\n{done.stdout}")

    def test_the_whole_operation_rolls_back_when_a_later_step_fails(self):
        """단계 사이 실패는 앞 단계가 이미 커밋된 상태다 — 전체를 되돌려야 한다."""
        root, _ = self._aged_install()
        before = _tree(root)
        real = up._managed_steps

        def failing(root_, plan, language):
            steps = list(real(root_, plan, language))
            def explode():
                raise OSError("injected failure after earlier steps committed")
            return steps[:1] + [("validate", explode)]

        up._managed_steps = failing
        try:
            self.assertEqual(_run(root, apply=True, force=True), up.EXIT_BLOCKED)
        finally:
            up._managed_steps = real
        after = _tree(root)
        self.assertEqual(set(after) - set(before), set(),
                         "실패 후에도 새 파일이 남았다")
        for rel, value in before.items():
            self.assertEqual(after.get(rel)[:2] if after.get(rel) else None, value[:2],
                             f"{rel} 이 복원되지 않았다")

    def test_a_second_apply_changes_nothing(self):
        """전체 upgrade 의 멱등 — 좁은 scalar 만이 아니라 배포·재생성까지 포함해서."""
        root, _ = self._aged_install()
        self.assertEqual(_run(root, apply=True, force=True), up.EXIT_OK)
        first = {rel: value[:2] for rel, value in _tree(root).items()}
        self.assertEqual(_run(root, apply=True, force=True), up.EXIT_OK)
        second = {rel: value[:2] for rel, value in _tree(root).items()}
        self.assertEqual(first, second, "두 번째 apply 가 트리를 바꿨다")


class TestProfileJsonSyncOnRequiredVersionChange(unittest.TestCase):
    """required_version 을 바꾸는 upgrade 는 core-assets 위임 전에 compiled json 도 맞춘다.

    이 짝은 upgrade 가 생기기 전까지 실제로 어긋나 본 적이 없다 — 기존 모든 upgrade 테스트는
    설치버전=엔진버전이라 required_version 자체가 바뀌지 않는다. 실제 버전이 바뀌는 순간에만
    core-assets 단계 내부의 `overlay_materialize.load_profile` 일치 검사가 갈라진다
    (`materialize.profile_yaml_json_mismatch`).
    """

    def _bootstrapped_pair(self, root, old_version):
        """실제 install 로 부트스트랩된 소비자 + old_version 으로 짝이 맞는 yaml/json."""
        _install(root)
        text = PROFILE.replace('required_version: "0.0.1"', f'required_version: "{old_version}"')
        Path(root, "sage", "project-profile.yaml").write_text(text, encoding="utf-8")
        import yaml
        from sage.profile_compile import materialize_profile
        compiled = materialize_profile(yaml.safe_load(text))
        Path(root, "sage", "project-profile.json").write_text(
            json.dumps(compiled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return root

    def test_required_version_refreshes_compiled_profile_before_managed_steps(self):
        import sage
        from unittest import mock
        root = self._bootstrapped_pair(tempfile.mkdtemp(), "0.0.1")
        seen = {}
        real_steps = up._managed_steps

        def spying(root_, plan, language):
            steps = list(real_steps(root_, plan, language))
            self.assertTrue(steps, "부트스트랩된 fixture 인데 managed steps 가 비었다")

            def first_step_check():
                import yaml as _yaml
                seen["yaml"] = _yaml.safe_load(
                    Path(root_, "sage", "project-profile.yaml").read_text(encoding="utf-8")
                )["sage"]["required_version"]
                seen["json"] = json.loads(
                    Path(root_, "sage", "project-profile.json").read_text(encoding="utf-8")
                )["sage"]["required_version"]
                return 0

            return [(steps[0][0], first_step_check)]

        up._managed_steps = spying
        try:
            with mock.patch.object(sage, "__version__", "9.9.9"):
                result = _run(root, apply=True, force=True)
        finally:
            up._managed_steps = real_steps

        self.assertEqual(result, up.EXIT_OK)
        self.assertEqual(seen.get("yaml"), "9.9.9")
        self.assertEqual(seen.get("json"), "9.9.9",
                         "core-assets 진입 시점에 json 이 아직 old version 이었다")
        body = Path(root, "sage", "project-profile.yaml").read_text(encoding="utf-8")
        self.assertIn("# 주석은 보존돼야 한다", body, "yaml 재직렬화로 주석이 사라졌다")
        self.assertIn('name: "consumer"', body)

    def test_preexisting_yaml_json_mismatch_blocks_without_mutation(self):
        """upgrade 이전부터 어긋나 있던 pair 를 upgrade 가 조용히 덮어 고치지 않는다."""
        import io
        from contextlib import redirect_stderr, redirect_stdout
        root = tempfile.mkdtemp()
        _install(root)
        Path(root, "sage", "project-profile.yaml").write_text(PROFILE, encoding="utf-8")
        # 실제 컴파일 결과와 무관한 최소 json — upgrade 가 시작하기 전부터 이미 어긋나 있다.
        Path(root, "sage", "project-profile.json").write_text(
            json.dumps({"sage": {"required_version": "0.0.9"}}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        before = _tree(root)

        called = {"managed": False}
        real_steps = up._managed_steps

        def spying(*a, **kw):
            called["managed"] = True
            return real_steps(*a, **kw)

        up._managed_steps = spying
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                result = _run(root, apply=True, force=True)
        finally:
            up._managed_steps = real_steps

        self.assertNotEqual(result, up.EXIT_OK)
        self.assertFalse(called["managed"], "사전 pair 불일치인데도 managed steps 가 호출됐다")
        after = _tree(root)
        self.assertEqual(after, before, "사전 불일치가 있는데도 트리가 바뀌었다")
        combined = out.getvalue() + err.getvalue()
        self.assertIn("project-profile.yaml", combined, combined)
        self.assertIn("다릅니다", combined, combined)

    def test_later_step_failure_restores_refreshed_yaml_and_json(self):
        """required_version + json 동기화가 끝난 뒤 실패해도 둘 다 원래 bytes·mode 로 되돌린다."""
        import sage
        from unittest import mock
        root = self._bootstrapped_pair(tempfile.mkdtemp(), "0.0.1")
        yaml_path = Path(root, "sage", "project-profile.yaml")
        json_path = Path(root, "sage", "project-profile.json")
        before_yaml = (yaml_path.read_bytes(), os.stat(yaml_path).st_mode & 0o777)
        before_json = (json_path.read_bytes(), os.stat(json_path).st_mode & 0o777)

        real_steps = up._managed_steps

        def failing(root_, plan, language):
            def explode():
                raise OSError("injected failure after required_version + json refresh committed")
            return [("core-assets", explode)]

        up._managed_steps = failing
        try:
            with mock.patch.object(sage, "__version__", "9.9.9"):
                result = _run(root, apply=True, force=True)
        finally:
            up._managed_steps = real_steps

        self.assertEqual(result, up.EXIT_BLOCKED)
        self.assertEqual((yaml_path.read_bytes(), os.stat(yaml_path).st_mode & 0o777), before_yaml,
                         "rollback 이 yaml 을 원래대로 되돌리지 않았다")
        self.assertEqual((json_path.read_bytes(), os.stat(json_path).st_mode & 0o777), before_json,
                         "rollback 이 json 을 원래대로 되돌리지 않았다")

    def test_profile_pair_refresh_is_version_agnostic(self):
        """0.9.84→1.0.0 전용 분기가 아니다 — 임의의 OLD→NEW 에서 같은 코드가 동작한다."""
        import sage
        from unittest import mock
        import yaml as _yaml
        root = self._bootstrapped_pair(tempfile.mkdtemp(), "1.0.0")
        real_steps = up._managed_steps

        def noop_steps(root_, plan, language):
            return [(name, (lambda: 0)) for name, _ in real_steps(root_, plan, language)]

        def apply_once():
            up._managed_steps = noop_steps
            try:
                with mock.patch.object(sage, "__version__", "1.1.0"):
                    return _run(root, apply=True, force=True)
            finally:
                up._managed_steps = real_steps

        self.assertEqual(apply_once(), up.EXIT_OK)
        yaml_version = _yaml.safe_load(
            Path(root, "sage", "project-profile.yaml").read_text(encoding="utf-8"))["sage"]["required_version"]
        json_version = json.loads(
            Path(root, "sage", "project-profile.json").read_text(encoding="utf-8"))["sage"]["required_version"]
        self.assertEqual(yaml_version, "1.1.0")
        self.assertEqual(json_version, "1.1.0")

        profile_rel = os.path.join("sage", "project-profile.yaml")
        json_rel = os.path.join("sage", "project-profile.json")
        after_first = _tree(root)
        self.assertEqual(apply_once(), up.EXIT_OK, "두 번째 apply(멱등) 가 실패했다")
        after_second = _tree(root)
        self.assertEqual(after_second[profile_rel][:2], after_first[profile_rel][:2],
                         "두 번째 apply 가 yaml 을 다시 썼다")
        self.assertEqual(after_second[json_rel][:2], after_first[json_rel][:2],
                         "두 번째 apply 가 json 을 다시 썼다")


class TestRunsWhenOtherCommandsWouldNot(unittest.TestCase):
    def test_an_unbootstrapped_profile_runs_but_does_not_report_success(self):
        """FR-U03 은 "호출 가능" 이지 "성공" 이 아니다.

        부트스트랩 미완이면 CORE 를 배포할 수 없다. 그 상태로 exit 0 을 내면 사용자는 업그레이드가
        됐다고 믿는데 새 자산이 없다 — 이 명령에서 가장 위험한 실패다. 그래서 명령은 **돌되**
        blocker 로 끝나고, 무엇이 왜 안 됐는지 말한다.

        중요한 것은 부트스트랩 게이트가 실행 자체를 거부하지 않는다는 점이다. 거부하면 버전
        불일치의 탈출 통로가 사라진다.
        """
        root = _install(tempfile.mkdtemp(), real=False,
                        profile='sage:\n  required_version: "0.0.1"\n')
        self.assertEqual(_run(root, check=True), up.EXIT_BLOCKED)
        self.assertEqual(_run(root, apply=True), up.EXIT_BLOCKED)
        reports = list(Path(root, ".sage", "upgrades").glob("*.json"))
        self.assertTrue(reports, "실행되지 않아 보고서조차 없다")
        payload = json.loads(sorted(reports)[-1].read_text(encoding="utf-8"))
        self.assertTrue(payload["blockers"], "차단 사유를 기록하지 않았다")

    def test_an_unbootstrapped_profile_is_not_mutated(self):
        """배포하지 못할 상태에서 선언 값만 고쳐 놓으면 절반만 옮겨간 트리가 남는다."""
        root = _install(tempfile.mkdtemp(), real=False,
                        profile='sage:\n  required_version: "0.0.1"\n')
        before = _tree(root)[os.path.join("sage", "project-profile.yaml")]
        _run(root, apply=True)
        self.assertEqual(_tree(root)[os.path.join("sage", "project-profile.yaml")], before)

    def test_a_missing_profile_reports_instead_of_inventing_one(self):
        root = _install(tempfile.mkdtemp(), real=False, profile=None)
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

    def test_a_damaged_declared_language_blocks_instead_of_being_overwritten(self):
        """선언된 값이 ko|en 이 아니면 이행이 아니라 손상이다.

        기본값으로 덮으면 사이클의 언어 계약이 도구 손에 조용히 바뀌고, 원래 무엇이 적혀
        있었는지도 함께 사라진다. 게이트가 그 사이클 문서를 어느 언어로 읽을지가 달라지므로
        표시 문제가 아니라 판정 문제다."""
        for declared in ("fr", "", "EN", 3, None):
            root = _install(tempfile.mkdtemp())
            os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
            state = {"version": 2, "cycle_stem": "demo", "document_language": declared}
            Path(root, ".sage", "cycle.json").write_text(json.dumps(state), encoding="utf-8")
            with self.subTest(declared=declared):
                self.assertNotEqual(_run(root, apply=True), up.EXIT_OK,
                                    "손상된 선언 언어가 통과했다")
                data = json.loads(Path(root, ".sage", "cycle.json").read_text(encoding="utf-8"))
                self.assertEqual(data["document_language"], declared,
                                 "손상된 값을 기본값으로 덮어썼다")

    def test_only_a_genuine_v1_declaration_migrates(self):
        """이행은 언어를 **지어내는** 동작이라, 전제가 서는 상태에서만 해야 한다.

        marker 이전 사이클이 한국어로 시작했다는 호환 기본값을 명시로 적는 것이 이행이다.
        v2 인데 선언이 없거나, version 이 1·2 가 아니거나, v1 인데 이미 선언이 있는 상태는
        그 전제가 서지 않는다. 같은 기본값으로 덮으면 사이클의 언어 계약을 도구가 조용히
        바꾸고 원래 값도 함께 사라진다 — 표시가 아니라 판정에 영향을 준다.

        앞선 수정은 `document_language: fr` 만 막아서 나머지 변형이 그대로 남아 있었다."""
        for state in ({"version": 2, "cycle_stem": "demo"},
                      {"version": 3, "cycle_stem": "demo"},
                      {"version": 1, "cycle_stem": "demo", "document_language": "en"},
                      {"version": 1},
                      {"cycle_stem": "demo"}):
            root = _install(tempfile.mkdtemp())
            os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
            Path(root, ".sage", "cycle.json").write_text(json.dumps(state), encoding="utf-8")
            with self.subTest(state=state):
                self.assertNotEqual(_run(root, apply=True), up.EXIT_OK,
                                    "이행 전제가 없는 상태가 통과했다")
                after = json.loads(Path(root, ".sage", "cycle.json").read_text(encoding="utf-8"))
                self.assertEqual(after, state, "이행 대상이 아닌 state 를 도구가 고쳐 썼다")

    def test_the_state_blocker_names_what_is_wrong(self):
        """무엇이 어긋났는지 없이 막으면 사용자는 파일을 열어 추측해야 한다."""
        root = _install(tempfile.mkdtemp())
        os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
        Path(root, ".sage", "cycle.json").write_text(
            json.dumps({"version": 3, "cycle_stem": "demo"}), encoding="utf-8")
        for language in ("ko", "en"):
            _, blockers = up._plan(root, language)
            with self.subTest(language=language):
                joined = " ".join(blockers)
                self.assertIn("version=3", joined)
                self.assertIn("cycle.json", joined)
                self.assertNotIn("message_key=", joined)

    def test_the_blocker_names_the_offending_value_in_both_languages(self):
        for language in ("ko", "en"):
            root = _install(tempfile.mkdtemp())
            os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
            Path(root, ".sage", "cycle.json").write_text(
                json.dumps({"version": 2, "cycle_stem": "demo", "document_language": "fr"}),
                encoding="utf-8")
            _, blockers = up._plan(root, language)
            with self.subTest(language=language):
                joined = " ".join(blockers)
                self.assertIn("fr", joined)
                self.assertNotIn("message_key=", joined)


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
        # v0.9.84 **소비자**는 `/sage-init` 를 마친 상태다. 템플릿 원본은 부트스트랩 이전이라
        # 그대로 쓰면 CORE 배포 경로를 타지 않고 skip 으로 끝난다 — 조용한 skip 은 통과로
        # 세어져 실제 upgrade 경로가 미검증인 채 남는다.
        template = Path(cls._tmp, "templates", "project-profile.yaml").read_text(encoding="utf-8")
        Path(cls.root, "sage", "project-profile.yaml").write_text(
            template
            + '\nproject:\n  name: "aged-consumer"\n  prefix: "aged"\n'
              'components:\n  - { id: core, paths: ["src/**"] }\n'
              'risk:\n  l2_path_globs: ["src/**"]\n',
            encoding="utf-8")
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
        # skip 하지 않는다 — 실제 트리에서 도는지가 이 테스트의 존재 이유다.
        self.assertEqual(_run(self.root, apply=True, force=True), up.EXIT_OK)
        profile = os.path.join("sage", "project-profile.yaml")
        after_first = _tree(self.root)[profile]
        self.assertEqual(_run(self.root, apply=True, force=True), up.EXIT_OK)
        self.assertEqual(_tree(self.root)[profile], after_first,
                         "실제 트리에서 두 번째 apply 가 파일을 다시 썼다")


class TestFailureMessagesFollowLanguage(unittest.TestCase):
    """실패 경로(rollback·미지 write kind·단계 exit)의 문구도 language_of() 를 따른다.

    조직 전체 upgrade 를 실패시켜 이 경로들을 자연히 밟게 하기는 어려워(멱등·잠금·단계 순서가
    실제 설치본을 요구) 관련 함수를 직접 호출해 --lang en 렌더를 고정한다.
    """

    def test_restore_tree_reports_failures_in_english(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "x.txt")
            Path(path).write_text("x", encoding="utf-8")
            with mock.patch("sage.commands.upgrade.os.unlink",
                            side_effect=OSError("permission denied")):
                restored, problems = up._restore_tree(root, {}, language="en")
            self.assertFalse(restored)
            self.assertTrue(any("delete failed" in p for p in problems), problems)
            self.assertFalse(any("삭제 실패" in p for p in problems), problems)

    def test_write_declaration_unknown_kind_raises_in_english(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(RuntimeError) as ctx:
                up._write_declaration(root, {"kind": "bogus", "path": "irrelevant"}, language="en")
        self.assertIn("unknown write kind: bogus", str(ctx.exception))
        self.assertNotIn("알 수 없는", str(ctx.exception))


class TestRunAllRegistration(unittest.TestCase):
    def test_this_suite_is_wired(self):
        body = (HERE / "run-all.sh").read_text(encoding="utf-8")
        self.assertIn("test_upgrade.py", body)


if __name__ == "__main__":
    unittest.main()
