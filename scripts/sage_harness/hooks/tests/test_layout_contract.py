#!/usr/bin/env python3
"""레이아웃 판정과 쓰기 경계.

## 왜 이 파일이 있는가

소비 프로젝트의 SAGE 트리를 `scripts/sage_harness/` 에서 `sage_harness/` 로 옮기면서, 경로
property 가 "신 경로에 `runtime/` 이 있으면 신 경로, 없으면 구 경로" 로 **폴백**하게 만들었다.
그 property 에 "읽기용" 이라고 적어 두었지만 실제로는 `generate` 의 adapter 쓰기 목록이 같은
값을 받아 갔다.

```
resolve_hooks_dir() → AssetPaths.adapter() → canonical_adapter_writes → 실제 write
```

구 레이아웃 프로젝트에서 **조용히 구 경로에 쓰는 통로**였고, 전체 테스트가 통과하는 동안에도
남아 있었다. 주석이 계약을 말하고 코드가 그것을 어기는 형태이며, 이 사이클이 고치고 있던
결함과 같은 종류다.

그래서 둘을 갈랐다.

  · 판정 — `detect_layout()` 한 곳에서만 파일시스템을 본다
  · 계산 — `AssetPaths(..., layout=...)` 는 주입된 값으로만 경로를 만든다

이 파일은 그 경계가 유지되는지 본다. 경로 property 가 디스크 상태에 따라 값을 바꾸기 시작하면
여기서 걸린다.
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, REPO)

from sage import asset_paths as ap  # noqa: E402


def _consumer(root, layout):
    """소비 프로젝트 모양만 만든다.

    판정 기준은 디렉터리가 아니라 **sentinel 파일**(`runtime/run_hook.py`)이다. `hook_entry` 가
    코어를 고를 때 보는 것과 같은 파일이어야, 도구가 "여기가 정본" 이라고 말하는 자리와 실제로
    게이트가 도는 자리가 갈리지 않는다.
    """
    rel = {"current": ap._HOOKS_REL, "legacy": ap.LEGACY_HOOKS_REL}[layout]
    sentinel = os.path.join(root, rel, ap.SENTINEL_REL)
    os.makedirs(os.path.dirname(sentinel), exist_ok=True)
    Path(sentinel).write_text("# sentinel\n", encoding="utf-8")


class DetectLayout(unittest.TestCase):
    def test_engine_source_tree(self):
        self.assertEqual(ap.detect_layout(REPO), ap.LAYOUT_ENGINE)

    def test_current_consumer_only(self):
        with tempfile.TemporaryDirectory() as root:
            _consumer(root, "current")
            self.assertEqual(ap.detect_layout(root), ap.LAYOUT_CONSUMER_CURRENT)

    def test_legacy_consumer_only(self):
        with tempfile.TemporaryDirectory() as root:
            _consumer(root, "legacy")
            self.assertEqual(ap.detect_layout(root), ap.LAYOUT_CONSUMER_LEGACY)

    def test_both_layouts_is_a_conflict(self):
        """둘 다 있으면 고르지 않는다.

        어느 쪽 hook 이 돌지는 게이트 코드가 무엇이 되는지의 문제다. 도구가 임의로 정하면
        사용자는 자기 게이트가 바뀐 줄 모른다.
        """
        with tempfile.TemporaryDirectory() as root:
            _consumer(root, "current")
            _consumer(root, "legacy")
            self.assertEqual(ap.detect_layout(root), ap.LAYOUT_CONFLICT)

    def test_empty_destination_is_current(self):
        """빈 디렉터리는 구 레이아웃이 아니다 — 아직 아무것도 없다는 뜻일 뿐이다."""
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(ap.detect_layout(root), ap.LAYOUT_CONSUMER_CURRENT)

    def test_conflict_refuses_to_produce_a_path(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                ap.layout_hooks_dir(root, ap.LAYOUT_CONFLICT)


class AssetPathsIsPure(unittest.TestCase):
    """경로 계산은 디스크를 보지 않는다."""

    def test_paths_do_not_change_with_filesystem_state(self):
        with tempfile.TemporaryDirectory() as root:
            paths = ap.AssetPaths(root, "hook", "demo")
            before = (paths.core, paths.native, paths.adapter("claude"))
            # 구 레이아웃을 실제로 만들어 둔다. 폴백이 남아 있으면 값이 바뀐다.
            _consumer(root, "legacy")
            self.assertEqual((paths.core, paths.native, paths.adapter("claude")), before)

    def test_layout_selects_the_tree(self):
        root = "/does/not/exist"
        current = ap.AssetPaths(root, "hook", "demo", layout=ap.LAYOUT_CONSUMER_CURRENT)
        legacy = ap.AssetPaths(root, "hook", "demo", layout=ap.LAYOUT_CONSUMER_LEGACY)
        engine = ap.AssetPaths(root, "hook", "demo", layout=ap.LAYOUT_ENGINE)
        self.assertIn("/sage_harness/hooks/", current.core)
        self.assertIn("/scripts/sage_harness/hooks/", legacy.core)
        self.assertEqual(legacy.core, engine.core)

    def test_default_layout_is_the_current_consumer(self):
        """기본값이 구 레이아웃이면, layout 을 넘기지 않은 호출부가 조용히 구 경로에 쓴다."""
        self.assertEqual(ap.AssetPaths("/r", "hook", "d").layout, ap.LAYOUT_CONSUMER_CURRENT)


class WriteBoundary(unittest.TestCase):
    """설치·생성이 만드는 자리는 신 레이아웃 하나뿐이다."""

    def _install(self, dest, *extra):
        return subprocess.run(
            [sys.executable, "-m", "sage", "install", "--host", "claude", "--dest", dest, *extra],
            cwd=REPO, capture_output=True, text=True)

    def test_fresh_install_creates_only_the_current_tree(self):
        with tempfile.TemporaryDirectory() as dest:
            done = self._install(dest)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue(os.path.isdir(os.path.join(dest, "sage_harness", "hooks")))
            self.assertFalse(os.path.exists(os.path.join(dest, "scripts", "sage_harness")))
            self.assertFalse(os.path.exists(os.path.join(dest, "schema")))

    def test_user_siblings_survive(self):
        with tempfile.TemporaryDirectory() as dest:
            os.makedirs(os.path.join(dest, "scripts"))
            own = Path(dest, "scripts", "deploy.sh")
            own.write_text("echo mine\n", encoding="utf-8")
            self.assertEqual(self._install(dest).returncode, 0)
            self.assertEqual(own.read_text(encoding="utf-8"), "echo mine\n")

    def test_install_refuses_when_both_layouts_exist(self):
        """공존 상태에서 배치하면 어느 쪽이 정본인지 더 모호해진다."""
        with tempfile.TemporaryDirectory() as dest:
            _consumer(dest, "current")
            _consumer(dest, "legacy")
            done = self._install(dest)
            self.assertEqual(done.returncode, 1)
            self.assertIn("구·신 레이아웃", done.stderr)


class InstallNeverCreatesCoexistence(unittest.TestCase):
    """`install` 은 공존을 거부할 뿐 아니라 **새로 만들지도 않는다.**

    앞의 `WriteBoundary` 는 "이미 공존하면 거부한다" 만 봤다. 그 검사를 통과하면서도
    **구 레이아웃 프로젝트에 install 하면 신 경로에 써서 공존을 만들고 있었다** — 다음
    실행부터는 자기가 만든 상태를 자기가 거부한다. 문서가 판본 차이에 `--force` 를 권하므로
    1.0 사용자가 안내대로만 해도 도달한다.

    신 경로 우선 해석 때문에 그 순간 사용자가 구 트리에 쓴 hook 이 조용히 가려진다. 게이트
    코드가 바뀌는데 사용자는 모른다.

    그래서 계약을 넓힌다 — **어떤 정상 입력에서도 공존을 만들지 않는다.**
    """

    def _legacy_project(self, dest):
        done = subprocess.run(
            [sys.executable, "-m", "sage", "install", "--host", "claude", "--dest", dest],
            cwd=REPO, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        os.makedirs(os.path.join(dest, "scripts", "sage_harness"))
        os.rename(os.path.join(dest, "sage_harness", "hooks"),
                  os.path.join(dest, "scripts", "sage_harness", "hooks"))
        os.rename(os.path.join(dest, "sage_harness", "schema"), os.path.join(dest, "schema"))
        os.rename(os.path.join(dest, "sage_harness", "verify-changes.sh"),
                  os.path.join(dest, "scripts", "verify-changes.sh"))
        os.rmdir(os.path.join(dest, "sage_harness"))

    def _install(self, dest, *extra):
        return subprocess.run(
            [sys.executable, "-m", "sage", "install", "--host", "claude", "--dest", dest, *extra],
            cwd=REPO, capture_output=True, text=True)

    def test_legacy_install_updates_in_place(self):
        for extra in ([], ["--force"]):
            with self.subTest(force=bool(extra)), tempfile.TemporaryDirectory() as dest:
                self._legacy_project(dest)
                done = self._install(dest, *extra)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(ap.detect_layout(dest), ap.LAYOUT_CONSUMER_LEGACY)
                self.assertFalse(os.path.exists(os.path.join(dest, "sage_harness")))

    def test_legacy_install_places_every_asset_in_the_old_tree(self):
        """hook 만 제자리에 두고 schema·verify 를 신 경로에 쓰면 트리가 반쪽으로 갈린다."""
        with tempfile.TemporaryDirectory() as dest:
            self._legacy_project(dest)
            self.assertEqual(self._install(dest, "--force").returncode, 0)
            for rel in (os.path.join("scripts", "sage_harness", "hooks"),
                        "schema", os.path.join("scripts", "verify-changes.sh")):
                self.assertTrue(os.path.exists(os.path.join(dest, rel)), rel)
            self.assertFalse(os.path.exists(os.path.join(dest, "sage_harness")))

    def test_legacy_install_delivers_the_fixed_hook_core(self):
        """제자리 갱신의 목적은 위치 보존이 아니라 **구 설치본이 이번 수정을 받는 것**이다.

        받지 못하면 1.0 사용자는 엔진 없이 크래시하는 게이트를 계속 쓰게 된다 — 그 크래시는
        exit 1 이라 통과로 읽힌다.
        """
        with tempfile.TemporaryDirectory() as dest:
            self._legacy_project(dest)
            self.assertEqual(self._install(dest, "--force").returncode, 0)
            core = os.path.join(dest, "scripts", "sage_harness", "hooks")
            self.assertTrue(os.path.isfile(os.path.join(core, "done_criteria_contract.py")))
            body = Path(core, "pre_implementation_gate_core.py").read_text(encoding="utf-8")
            self.assertNotIn("_SOURCE_ROOT", body)

    def test_a_user_hook_in_the_old_tree_is_not_shadowed(self):
        with tempfile.TemporaryDirectory() as dest:
            self._legacy_project(dest)
            own = Path(dest, "scripts", "sage_harness", "hooks", "my_project_hook.py")
            own.write_text("# mine\n", encoding="utf-8")
            self.assertEqual(self._install(dest, "--force").returncode, 0)
            self.assertEqual(own.read_text(encoding="utf-8"), "# mine\n")
            # 신 트리가 없으므로 hook_entry 가 구 트리를 고르고, 이 파일은 계속 보인다.
            self.assertFalse(os.path.exists(os.path.join(dest, "sage_harness")))

    def test_conflict_blocks_even_with_force(self):
        """`--force` 는 덮어쓰기 허가이지 정본 판정 위임이 아니다."""
        with tempfile.TemporaryDirectory() as dest:
            _consumer(dest, "current")
            _consumer(dest, "legacy")
            done = self._install(dest, "--force")
            self.assertEqual(done.returncode, 1)
            self.assertIn("구·신 레이아웃", done.stderr)


# `UpgradeReportsButDoesNotMigrate` 는 여기 있었다. **자동 이행 미지원**을 못박던 테스트다.
#
# 그 계약은 "옮기는 것이 안전하지 않다" 는 판단에서 나왔는데, 전제가 틀렸다 — SAGE 배포 자산은
# 옮길 필요가 없다. 패키지가 원본을 갖고 있으므로 신 경로에 다시 만들고 구 것을 지우면 된다.
#
# 이행 계약은 `test_layout_migration.py` 가 소유한다. 여기 빈 자리를 남기는 이유는, 이 파일만
# 읽은 사람이 "이행 계약이 어디 갔나" 를 묻지 않게 하기 위해서다.


if __name__ == "__main__":
    unittest.main(verbosity=2)
