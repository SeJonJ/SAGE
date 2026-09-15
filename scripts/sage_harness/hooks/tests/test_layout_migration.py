#!/usr/bin/env python3
"""구 레이아웃 이행 — 다시 만들고, 검증하고, 증명된 것만 지운다.

## 왜 이 파일이 있는가

이행의 위험은 "옮기다 실패한다" 가 아니다. 이 설계는 옮기지 않는다 — SAGE 배포 자산의 바이트는
패키지가 원본을 갖고 있어서 신 경로에 다시 만들면 된다.

남는 위험은 셋이고, 전부 **지우는 쪽**에 있다.

  · 사용자 파일을 SAGE 것으로 잘못 보고 지운다
  · 검증되지 않은 트리로 게이트를 넘긴다
  · 우리가 만들지 않은 트리를 우리 것으로 착각하고 구 자산을 지운다

세 번째가 가장 조용하다. 사용자가 `sage_harness/` 를 자기 용도로 만들어 뒀다면, 공존 상태를
"중단된 이행" 으로 읽는 순간 그 트리를 정본으로 승격시키고 진짜 정본을 지운다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, REPO)

from sage import asset_paths as ap  # noqa: E402
from sage import layout_migration as lm  # noqa: E402
from sage import hook_entry  # noqa: E402

PROFILE = """project:
  name: "consumer"
  prefix: "consumer"
components:
  - { id: core, paths: ["app/core/**"] }
risk:
  l2_path_globs: ["*core/*.src"]
  l3_review_strategy: "claude_grep_first"
"""


def _sage(args, cwd):
    return subprocess.run([sys.executable, "-m", "sage", *args], cwd=cwd,
                          capture_output=True, text=True)


def _legacy_project(dest):
    """1.0 이 배치한 모양. 현재 install 로 만든 뒤 구 자리로 되돌린다.

    실제 v1.0.0 태그로 만든 소비 프로젝트와 구조가 같다는 것은 사이클 중에 대조했다. 여기서
    태그를 꺼내지 않는 이유는 회귀가 네트워크·worktree 에 의존하면 안 되기 때문이다.
    """
    done = _sage(["install", "--host", "claude", "--dest", dest], cwd=REPO)
    assert done.returncode == 0, done.stderr
    os.makedirs(os.path.join(dest, "scripts", "sage_harness"))
    os.rename(os.path.join(dest, "sage_harness", "hooks"),
              os.path.join(dest, "scripts", "sage_harness", "hooks"))
    os.rename(os.path.join(dest, "sage_harness", "schema"), os.path.join(dest, "schema"))
    os.rename(os.path.join(dest, "sage_harness", "verify-changes.sh"),
              os.path.join(dest, "scripts", "verify-changes.sh"))
    os.rmdir(os.path.join(dest, "sage_harness"))
    Path(dest, "sage", "project-profile.yaml").write_text(PROFILE, encoding="utf-8")
    os.makedirs(os.path.join(dest, "plan_docs", "00-base_plan"), exist_ok=True)
    Path(dest, "plan_docs", "00-base_plan", "main.md").write_text(
        "Cycle-Stem: `main`\nRisk Level: L2\n", encoding="utf-8")


def _manifest(root):
    with open(os.path.join(root, "docs", "sage_harness", ".manifest.json"), encoding="utf-8") as h:
        return json.load(h)


class WhatGetsRemoved(unittest.TestCase):
    """지우는 근거는 **증명**이지 위치가 아니다."""

    def test_a_file_we_did_not_ship_is_kept(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            mine = Path(dest, "scripts", "sage_harness", "hooks", "notes.md")
            mine.write_text("# 내 메모\n", encoding="utf-8")
            plan = lm.plan(dest, manifest=_manifest(dest))
            kept = dict(plan["preserve"])
            self.assertIn(os.path.join("scripts", "sage_harness", "hooks", "notes.md"), kept)
            self.assertNotIn(os.path.join("scripts", "sage_harness", "hooks", "notes.md"),
                             plan["remove"])

    def test_an_edited_shared_file_is_kept(self):
        """`verify-changes.sh` 는 공유 디렉터리의 낱개 파일이라 **바이트로** 증명한다."""
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            verify = Path(dest, "scripts", "verify-changes.sh")
            verify.write_text(verify.read_text(encoding="utf-8") + "# 내가 고침\n",
                              encoding="utf-8")
            plan = lm.plan(dest, manifest=_manifest(dest))
            self.assertIn(os.path.join("scripts", "verify-changes.sh"),
                          dict(plan["preserve"]))

    def test_an_untouched_shared_file_is_removed_despite_the_path_token(self):
        """이 사이클이 바꾼 경로 토큰 때문에 손대지 않은 파일이 '수정본' 으로 읽히면,
        `scripts/` 는 어느 프로젝트에서도 정리되지 않는다. 우리가 만든 차이다."""
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            verify = Path(dest, "scripts", "verify-changes.sh")
            verify.write_text(
                verify.read_text(encoding="utf-8").replace(
                    "sage_harness/verify-changes.sh", "scripts/verify-changes.sh"),
                encoding="utf-8")
            plan = lm.plan(dest, manifest=_manifest(dest))
            self.assertIn(os.path.join("scripts", "verify-changes.sh"), plan["remove"])

    def test_a_symlink_is_never_removed(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            link = os.path.join(dest, "scripts", "sage_harness", "hooks", "elsewhere.py")
            os.symlink("/etc/hosts", link)
            plan = lm.plan(dest, manifest=_manifest(dest))
            rel = os.path.join("scripts", "sage_harness", "hooks", "elsewhere.py")
            self.assertEqual(dict(plan["preserve"]).get(rel), "symlink")


class UserCodeBlocks(unittest.TestCase):
    """사용자가 쓴 코드는 옮기지도, 조용히 끄지도 않는다."""

    def test_a_registered_project_hook_blocks_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            Path(dest, ap.LEGACY_HOOKS_REL, "my_guard_core.py").write_text(
                'CONTRACT_VERSION = "1"\n', encoding="utf-8")
            manifest = _manifest(dest)
            manifest["assets"]["hooks/my-guard"] = {"origin": "project", "form": "core_adapter"}
            plan = lm.plan(dest, manifest=manifest)
            self.assertIn(("project_hook", "hooks/my-guard"), plan["blockers"])

    def test_a_registration_without_code_gets_its_own_reason(self):
        """복구 절차가 다르다 — "새 자리에 다시 만들라" 가 성립하지 않는 상태다."""
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            manifest = _manifest(dest)
            manifest["assets"]["hooks/my-guard"] = {"origin": "project", "form": "core_adapter"}
            plan = lm.plan(dest, manifest=manifest)
            self.assertIn(("project_hook_missing_core", "hooks/my-guard"), plan["blockers"])

    def test_a_custom_review_strategy_blocks(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            profile = {"risk": {"l3_review_strategy": "our_own_review"}}
            plan = lm.plan(dest, manifest=_manifest(dest), profile=profile)
            self.assertIn(("custom_strategy", "our_own_review"), plan["blockers"])

    def test_a_builtin_strategy_does_not_block(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            profile = {"risk": {"l3_review_strategy": "claude_grep_first"}}
            plan = lm.plan(dest, manifest=_manifest(dest), profile=profile)
            self.assertEqual(plan["blockers"], [])


class TransitionOwnership(unittest.TestCase):
    """공존이 **우리가 만든 것**이라는 증거 없이는 구 자산을 지우지 않는다."""

    def _half_migrated(self, dest):
        _legacy_project(dest)
        with ap.layout_override(dest, ap.LAYOUT_CONSUMER_CURRENT):
            from sage.commands import install
            args = type("A", (), {"host": "claude", "dest": dest, "prefix": "sage",
                                  "force": True, "no_global_skill": False,
                                  "skill_scope": None})()
            assert install.run(args) == 0

    def test_an_interrupted_migration_is_recognised(self):
        with tempfile.TemporaryDirectory() as dest:
            self._half_migrated(dest)
            self.assertEqual(ap.detect_layout(dest), ap.LAYOUT_CONFLICT)
            plan = lm.plan(dest, manifest=_manifest(dest))
            self.assertTrue(plan["in_transition"])
            self.assertEqual(plan["blockers"], [])

    def test_a_tree_we_did_not_place_blocks(self):
        """사용자가 `sage_harness/` 를 자기 용도로 쓰고 있었다면, 공존을 중단된 이행으로 읽는
        순간 그 트리가 정본이 되고 진짜 정본이 지워진다."""
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            runtime = os.path.join(dest, ap._HOOKS_REL, "runtime")
            os.makedirs(runtime)
            Path(runtime, "run_hook.py").write_text("print('mine')\n", encoding="utf-8")
            plan = lm.plan(dest, manifest=_manifest(dest))
            self.assertTrue(any(kind == "unexpected_current" for kind, _ in plan["blockers"]))

    def test_the_gate_keeps_running_from_the_old_tree_mid_transition(self):
        """전환 구간의 정본은 아직 구 트리다. 신 트리는 배치됐을 뿐 검증되지 않았다."""
        from sage import hook_entry
        with tempfile.TemporaryDirectory() as dest:
            self._half_migrated(dest)
            self.assertEqual(hook_entry._resolve_core_dir(dest, None),
                             os.path.join(dest, ap.LEGACY_HOOKS_REL))


class NeverReachesOutsideTheProject(unittest.TestCase):
    """경로 기반 삭제는 조상 하나가 링크면 그대로 밖으로 나간다.

    첫 구현이 그랬다. 구 트리의 부모를 프로젝트 밖 디렉터리로 향하는 symlink 로 만들고 이행을
    돌리자 **바깥 파일이 실제로 지워졌다.** 이 저장소가 부모 핸들 backend 를 따로 만든 이유가
    그대로 적용되는 자리인데, 이행만 그 경계를 우회하고 있었다.
    """

    def test_a_symlinked_ancestor_is_not_a_layout(self):
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as dest:
            runtime = os.path.join(outside, "hooks", "runtime")
            os.makedirs(runtime)
            victim = Path(runtime, "run_hook.py")
            victim.write_text("# 프로젝트 밖\n", encoding="utf-8")
            os.makedirs(os.path.join(dest, "scripts"))
            os.symlink(outside, os.path.join(dest, "scripts", "sage_harness"))

            # sentinel 은 leaf 만 보면 정상 파일이다. 조상을 봐야 밖이라는 것이 드러난다.
            self.assertNotEqual(ap.detect_layout(dest), ap.LAYOUT_CONSUMER_LEGACY)
            self.assertFalse(lm.plan(dest)["needed"])
            self.assertTrue(victim.is_file(), "프로젝트 밖 파일이 삭제됐다")


class NeverOverwritesTheNewNamespace(unittest.TestCase):
    """sentinel 이 없다는 것은 **그 자리가 비었다는 증명이 아니다.**

    사용자가 `sage_harness/` 를 먼저 쓰고 있으면 판정은 여전히 legacy 이고, 그 뒤 배치가
    사용자 파일을 덮는다 — 이행이 데이터를 지우는 통로가 된다.
    """

    def test_an_occupied_target_blocks_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            mine = Path(dest, ap.SAGE_TREE, "verify-changes.sh")
            mine.parent.mkdir(parents=True, exist_ok=True)
            mine.write_text("echo USER-OWNED\n", encoding="utf-8")

            plan = lm.plan(dest, manifest=_manifest(dest))
            self.assertTrue(any(kind == "occupied_current" for kind, _ in plan["blockers"]))

            done = _sage(["upgrade", "--apply", "--root", dest], cwd=REPO)
            self.assertEqual(done.returncode, 1)
            self.assertEqual(mine.read_text(encoding="utf-8"), "echo USER-OWNED\n")

    def test_any_unverified_content_blocks_regardless_of_name(self):
        """이름으로 거르지 않는다.

        "설치 파일과 겹치지 않으니 괜찮다" 는 규칙은 그 파일을 **uninstall 날까지** 살려 둔다.
        `uninstall` 은 이 트리를 SAGE 관리 대상으로 다루므로 그때 함께 사라진다. 트리에 대한
        선언이 "여기 있는 것은 SAGE 가 덮어쓴다" 이면, 그 선언과 동작이 같아야 한다.
        """
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            mine = Path(dest, ap.SAGE_TREE, "my-notes.md")
            mine.parent.mkdir(parents=True, exist_ok=True)
            mine.write_text("# mine\n", encoding="utf-8")
            plan = lm.plan(dest, manifest=_manifest(dest))
            self.assertTrue(any(kind == "occupied_current" for kind, _ in plan["blockers"]))

    def test_install_applies_the_same_rule(self):
        with tempfile.TemporaryDirectory() as dest:
            squat = Path(dest, ap.SAGE_TREE, "notes.md")
            squat.parent.mkdir(parents=True)
            squat.write_text("# mine\n", encoding="utf-8")
            done = _sage(["install", "--host", "claude", "--dest", dest], cwd=REPO)
            self.assertEqual(done.returncode, 1)
            self.assertEqual(squat.read_text(encoding="utf-8"), "# mine\n")

    def test_the_check_is_repeated_after_the_lock_is_taken(self):
        """검사와 첫 변경 사이는 **아직 아무것도 막지 못한 구간**이다.

        점유 검사를 lock 획득 전에만 하면, 그 사이에 만들어진 사용자 파일은 검사를 거치지
        않은 채 기계 소유 트리에 남는다. install 은 exit 0 으로 끝나고, 그 파일은
        `uninstall` 날에 사라진다.
        """
        from sage import install_transaction as tx
        from sage.cli import build_parser
        from sage.commands import install as install_cmd

        with tempfile.TemporaryDirectory() as dest:
            mine = Path(dest, ap.SAGE_TREE, "user-owned.txt")
            original = tx.DestinationLock.acquire

            def acquire(self):
                # 사전 검사는 끝났다. lock 을 잡는 이 순간에 사용자가 파일을 만든다.
                if not mine.exists():
                    mine.parent.mkdir(parents=True, exist_ok=True)
                    mine.write_text("사용자 파일\n", encoding="utf-8")
                return original(self)

            tx.DestinationLock.acquire = acquire
            try:
                args = build_parser().parse_args(
                    ["install", "--host", "claude", "--dest", dest])
                code = install_cmd.run(args)
            finally:
                tx.DestinationLock.acquire = original

            self.assertNotEqual(code, 0)
            self.assertEqual(mine.read_text(encoding="utf-8"), "사용자 파일\n")
            self.assertFalse(Path(dest, ap._HOOKS_REL, ap.SENTINEL_REL).exists(),
                             "차단했는데 SAGE 자산이 배치됐다")

    def test_our_own_bytecode_cache_does_not_block(self):
        """`__pycache__` 는 **우리 코드를 실행한 부산물**이다.

        막으면 교착이 생긴다 — 이행이 한 번 실패하면 그 시도가 남긴 캐시 때문에 다음 실행이
        영구 차단된다. 스냅샷이 `__pycache__` 를 제외하므로 복원도 지우지 못한다.
        """
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            cache = Path(dest, ap._HOOKS_REL, "__pycache__", "x.cpython-314.pyc")
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"\x00")
            plan = lm.plan(dest, manifest=_manifest(dest))
            self.assertFalse(any(kind == "occupied_current" for kind, _ in plan["blockers"]))

    def test_the_cache_exception_is_only_for_real_caches(self):
        """예외를 넓게 열면 그 예외가 그대로 우회로가 된다.

        `__pycache__` 안의 정규 `.pyc` 만 우리 부산물이다. 그 밖의 `.pyc` 는 사용자가 둔
        파일이고, 이름만 `__pycache__` 인 링크는 가리키는 곳을 우리가 모른다.
        """
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            loose = Path(dest, ap._HOOKS_REL, "mine.pyc")
            loose.parent.mkdir(parents=True, exist_ok=True)
            loose.write_bytes(b"\x00")
            self.assertIn(os.path.join(ap._HOOKS_REL, "mine.pyc"),
                          lm.current_namespace_occupants(dest))
            loose.unlink()

            other = Path(dest, ap._HOOKS_REL, "__pycache__", "notes.md")
            other.parent.mkdir(parents=True, exist_ok=True)
            other.write_text("# mine\n", encoding="utf-8")
            self.assertIn(os.path.join(ap._HOOKS_REL, "__pycache__", "notes.md"),
                          lm.current_namespace_occupants(dest))

    def test_a_tree_that_points_outside_is_reported_as_occupied(self):
        """빈 목록은 "아무도 없다" 는 뜻이다.

        `sage_harness/` 자체가 밖을 가리킬 때 빈 목록을 내면, 차단은 뒤쪽 install transaction
        이 하더라도 **막힌 이유가 계획에 드러나지 않는다.** 첫 mutation 전에 막는다는 계약은
        판정이 그 사실을 말할 수 있어야 성립한다.
        """
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            Path(outside, "notes.md").write_text("# 프로젝트 밖\n", encoding="utf-8")
            os.symlink(outside, os.path.join(dest, ap.SAGE_TREE))

            self.assertEqual(lm.current_namespace_occupants(dest), [ap.SAGE_TREE])
            plan = lm.plan(dest, manifest=_manifest(dest))
            self.assertTrue(any(kind == "occupied_current" for kind, _ in plan["blockers"]))

            done = _sage(["upgrade", "--apply", "--root", dest], cwd=REPO)
            self.assertEqual(done.returncode, 1)
            self.assertTrue(Path(outside, "notes.md").is_file(), "프로젝트 밖 파일이 사라졌다")


class ProvenBytesAreCheckedAgainAtRemoval(unittest.TestCase):
    """계획이 증명한 바이트와 실제로 지우는 바이트가 같아야 한다.

    대조를 **결속 전에** 하면 확인은 경로로 열고 삭제는 handle 로 하는 셈이 된다. 그 사이가
    그대로 경쟁 구간이고, 우리가 읽어 증명한 파일과 지우는 파일이 다를 수 있다.
    """

    def test_a_target_that_changed_after_planning_is_not_removed(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            plan = lm.plan(dest, manifest=_manifest(dest))
            sentinel = os.path.join(ap.LEGACY_HOOKS_REL, ap.SENTINEL_REL)
            changed = next(rel for rel in plan["remove"] if rel != sentinel)
            Path(dest, changed).write_text("# 계획 뒤에 바뀌었다\n", encoding="utf-8")

            _activated, removed, leftover = lm.apply(dest, plan)
            self.assertNotIn(changed, removed)
            self.assertIn(changed, leftover)
            self.assertTrue(Path(dest, changed).is_file())


class RemovalListMatchesInstall(unittest.TestCase):
    def test_migration_only_removes_what_install_places(self):
        """install 은 `tests/`·`__pycache__`·`.pyc` 를 배치하지 않는다. 삭제 목록이 원본 트리를
        그대로 순회하면, **v1.0 이 배치한 적 없는 같은 경로의 사용자 파일**이 후보가 된다."""
        from sage import _resources
        placed = _resources.installable_hook_relpaths()
        self.assertFalse([rel for rel in placed if rel.split(os.sep)[0] == "tests"])
        self.assertFalse([rel for rel in placed if rel.endswith(".pyc")])
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            victim = Path(dest, ap.LEGACY_HOOKS_REL, "tests", "my_test.py")
            victim.parent.mkdir(parents=True, exist_ok=True)
            victim.write_text("# mine\n", encoding="utf-8")
            plan = lm.plan(dest, manifest=_manifest(dest))
            rel = os.path.join(ap.LEGACY_HOOKS_REL, "tests", "my_test.py")
            self.assertNotIn(rel, plan["remove"])
            self.assertIn(rel, dict(plan["preserve"]))


class RuntimeMustLoadBeforeAnythingIsRemoved(unittest.TestCase):
    """`validate` 는 해시와 스키마를 본다. 그것으로는 **이 트리로 hook 이 설 수 있는가** 를
    말하지 못한다 — 확인 없이 구 자산을 지우면 되돌아갈 자리가 없다."""

    def test_a_placed_tree_loads_without_the_engine(self):
        with tempfile.TemporaryDirectory() as dest:
            done = _sage(["install", "--host", "claude", "--dest", dest], cwd=REPO)
            self.assertEqual(done.returncode, 0, done.stderr)
            loads, detail = lm.runtime_loads(dest)
            self.assertTrue(loads, detail)

    def test_a_broken_runtime_is_caught(self):
        with tempfile.TemporaryDirectory() as dest:
            self.assertEqual(
                _sage(["install", "--host", "claude", "--dest", dest], cwd=REPO).returncode, 0)
            Path(dest, ap._HOOKS_REL, "runtime", "run_hook.py").write_text(
                "raise RuntimeError('broken')\n", encoding="utf-8")
            loads, _detail = lm.runtime_loads(dest)
            self.assertFalse(loads)

    def test_the_probe_really_runs_without_the_engine(self):
        """엔진이 import 되는 환경에서 이 검사를 돌리면, 부재를 검사한다고 주장하면서 실제로는
        존재를 검사한다. 이 테스트 프로세스에는 엔진이 있으므로 그 구분이 중요하다."""
        with tempfile.TemporaryDirectory() as dest:
            self.assertEqual(
                _sage(["install", "--host", "claude", "--dest", dest], cwd=REPO).returncode, 0)
            core = Path(dest, ap._HOOKS_REL, "runtime", "run_hook.py")
            core.write_text("import sage\n" + core.read_text(encoding="utf-8"),
                            encoding="utf-8")
            loads, _detail = lm.runtime_loads(dest)
            self.assertFalse(loads, "엔진이 가려지지 않아 `import sage` 가 성공했다")


class UserExtensionsStayPut(unittest.TestCase):
    """등록된 project hook 이 있으면 **첫 변경 전에 멈춘다.** 그리고 그게 전부다.

    한때 `--unregister` 로 출구를 열어 봤다. 그 명령은 adapter 를 지우고 manifest 를
    갱신해야 하는데, 두 변경 모두 `InstallTransaction` 밖에서 경로로 이뤄졌다 — 이 사이클이
    이미 두 번 고친 결함(조상이 밖을 가리키면 삭제가 프로젝트 밖에 닿는다)을 세 번째로
    만들었다. 사용자 코드의 생명주기를 여는 일은 이 릴리즈의 범위가 아니다.

    그래서 계약은 하나로 줄었다 — **차단하고, 구 레이아웃에서 계속 동작한다.**
    """

    def _with_project_hook(self, dest):
        _legacy_project(dest)
        Path(dest, "docs", "sage_harness", "hooks", "my-guard.md").write_text(
            "---\nid: my-guard\nkind: hook\nruntime_bindings:\n"
            '  claude: { event: PreToolUse, matcher: "Write", timeout: 10 }\n'
            '  codex: { event: PreToolUse, matcher: "apply_patch", timeout: 10 }\n'
            "---\n\n프로젝트 전용 게이트.\n", encoding="utf-8")
        Path(dest, ap.LEGACY_HOOKS_REL, "my_guard_core.py").write_text(
            'CONTRACT_VERSION = "1"\n\n\ndef main():\n    return 0\n', encoding="utf-8")
        done = _sage(["generate", "--kind", "hook", "--id", "my-guard", "--write",
                      "--target", "both", "--root", dest, "--dest", dest], cwd=REPO)
        assert done.returncode == 0, done.stderr

    def test_migration_stops_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as dest:
            self._with_project_hook(dest)
            core = Path(dest, ap.LEGACY_HOOKS_REL, "my_guard_core.py")
            spec = Path(dest, "docs", "sage_harness", "hooks", "my-guard.md")
            before = (core.read_text(encoding="utf-8"), spec.read_text(encoding="utf-8"))

            done = _sage(["upgrade", "--apply", "--root", dest], cwd=REPO)
            self.assertEqual(done.returncode, 1)
            self.assertEqual((core.read_text(encoding="utf-8"),
                              spec.read_text(encoding="utf-8")), before)
            # 구 레이아웃 그대로여야 한다 — 차단은 되돌리는 것이 아니라 시작하지 않는 것이다.
            self.assertEqual(ap.detect_layout(dest), ap.LAYOUT_CONSUMER_LEGACY)
            self.assertTrue(Path(dest, ap.LEGACY_HOOKS_REL, ap.SENTINEL_REL).is_file())

    def test_the_project_hook_still_runs_from_the_old_tree(self):
        """차단한 설치본은 **계속 동작해야 한다.** 멈춰 세운 대가가 기능 정지면 안 된다."""
        with tempfile.TemporaryDirectory() as dest:
            self._with_project_hook(dest)
            _sage(["upgrade", "--apply", "--root", dest], cwd=REPO)
            self.assertEqual(hook_entry._resolve_core_dir(dest, None),
                             ap.legacy_hooks_dir(dest))

    # v1.0.0 이 구 레이아웃에 쓴 adapter 본문. 태그를 꺼내지 않고 고정값으로 둔다 — 회귀가 git 이력에
    # 의존하면 얕은 clone 에서 조용히 약해진다.
    _V1_0_ADAPTER = (
        "#!/bin/bash\n"
        "# generated by sage generate - project hook adapter; do not edit.\n"
        'PROJECT_ROOT="${{SAGE_PROJECT_ROOT:-${{{root_env}:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}}}"\n'
        'CORE_DIR="$PROJECT_ROOT/scripts/sage_harness/hooks"\n'
        '[ -z "${{SAGE_PROFILE:-}}" ] && [ -f "$PROJECT_ROOT/sage/project-profile.json" ] && '
        'export SAGE_PROFILE="$PROJECT_ROOT/sage/project-profile.json"\n'
        'PY="${{SAGE_PYTHON:-python3}}"; command -v "$PY" >/dev/null 2>&1 || PY=python\n'
        'exec "$PY" "$CORE_DIR/runtime/run_hook.py" --runtime {host} --hook {hook_id} '
        '--root "$PROJECT_ROOT" --core-dir "$CORE_DIR"\n'
    )

    def _adapter(self, dest, host, hook_id="my-guard"):
        return Path(dest, ap.LEGACY_HOOKS_REL, "adapters", host, f"{hook_id}.sh")

    def test_an_adapter_written_by_1_0_stays_canonical(self):
        """1.0 이 쓴 adapter 가 있는 설치본에서 generate 가 그 파일을 손상으로 읽으면 등록 갱신이 전부 막힌다."""
        with tempfile.TemporaryDirectory() as dest:
            self._with_project_hook(dest)
            for host, root_env in (("claude", "CLAUDE_PROJECT_DIR"), ("codex", "CODEX_PROJECT_ROOT")):
                self._adapter(dest, host).write_text(
                    self._V1_0_ADAPTER.format(root_env=root_env, host=host, hook_id="my-guard"),
                    encoding="utf-8")
            before = {host: self._adapter(dest, host).read_bytes() for host in ("claude", "codex")}
            hashes = _manifest(dest)["assets"]["hooks/my-guard"]["adapter_hash"]

            done = _sage(["generate", "--kind", "hook", "--write", "--target", "both",
                          "--root", dest, "--dest", dest], cwd=REPO)

            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual({host: self._adapter(dest, host).read_bytes()
                              for host in ("claude", "codex")}, before)
            self.assertEqual(_manifest(dest)["assets"]["hooks/my-guard"]["adapter_hash"], hashes)

    def test_a_project_hook_registered_on_the_old_layout_really_runs(self):
        """경로 해석이 아니라 **실행**으로 본다. adapter 는 `hook_entry` 를 거치지 않고 자기 CORE_DIR 를 넘긴다."""
        with tempfile.TemporaryDirectory() as dest:
            self._with_project_hook(dest)
            Path(dest, ap.LEGACY_HOOKS_REL, "my_guard_core.py").write_text(
                'CONTRACT_VERSION = "1"\n\n\ndef decide(event, profile, snapshot):\n'
                "    return {'status': 'block', 'exit_code': 2, 'message': 'legacy project decision'}\n",
                encoding="utf-8")
            done = _sage(["generate", "--kind", "hook", "--id", "my-guard", "--write",
                          "--target", "both", "--root", dest, "--dest", dest], cwd=REPO)
            self.assertEqual(done.returncode, 0, done.stderr)
            events = {
                "claude": {"tool_name": "Write", "tool_input": {"file_path": "app/core/a.src"}},
                "codex": {"tool_name": "apply_patch",
                          "tool_input": {"command": "*** Update File: app/core/a.src\n+x"}},
            }
            for host, event in events.items():
                with self.subTest(host=host):
                    adapter = self._adapter(dest, host)
                    self.assertIn('CORE_DIR="$PROJECT_ROOT/scripts/sage_harness/hooks"',
                                  adapter.read_text(encoding="utf-8"))
                    result = subprocess.run(
                        ["bash", str(adapter)], input=json.dumps(event), capture_output=True, text=True,
                        env=dict(os.environ, SAGE_PROJECT_ROOT=dest, SAGE_PYTHON=sys.executable))
                    detail = f"stdout={result.stdout!r} stderr={result.stderr!r}"
                    self.assertEqual(result.returncode, 2, detail)
                    self.assertIn("legacy project decision", result.stderr, detail)
                    self.assertNotIn("No such file", result.stderr, detail)

    def test_absorb_reads_the_old_layout_core(self):
        """구 트리의 core 를 고쳤는데 신 경로를 보고 "변경 없음" 이라고 하면 사용자는 반영을 건너뛴다."""
        with tempfile.TemporaryDirectory() as dest:
            self._with_project_hook(dest)
            with open(Path(dest, ap.LEGACY_HOOKS_REL, "my_guard_core.py"), "a", encoding="utf-8") as fh:
                fh.write("# edited in place\n")
            done = _sage(["--lang", "en", "absorb", "--kind", "hook", "--id", "my-guard",
                          "--root", dest], cwd=REPO)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("~ canonical:", done.stdout)
            self.assertIn("scripts/sage_harness/hooks/my_guard_core.py", done.stdout.replace(os.sep, "/"))

    def test_no_unregister_escape_hatch_is_offered(self):
        """출구를 제공하지 않기로 했으면 **CLI 에도 없어야 한다.**

        옵션만 남고 동작이 사라지면 사용자는 절차의 절반까지 가서 막힌다.
        """
        done = _sage(["generate", "--help"], cwd=REPO)
        self.assertNotIn("--unregister", done.stdout + done.stderr)


class TheGateCodeNeverComesFromOutsideTheProject(unittest.TestCase):
    """어느 코드가 게이트인가 — 이 질문의 답이 프로젝트 밖이면 거버넌스가 없는 것이다.

    `detect_layout` 은 조상을 보는데 `hook_entry` 는 sentinel 파일 하나만 봤다. 그래서 판정은
    "구 트리는 없다" 고 말하고 진입점은 그 트리를 골랐다 — **판정과 해석이 갈린 세 번째 자리**다.
    """

    def _outside_tree(self, box, rel):
        dest = os.path.join(box, "proj")
        outside = os.path.join(box, "outside")
        runtime = os.path.join(outside, "hooks", "runtime")
        os.makedirs(runtime)
        Path(runtime, "run_hook.py").write_text("# 프로젝트 밖 코어\n", encoding="utf-8")
        target = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.symlink(outside, target)
        return dest, os.path.join(runtime, "run_hook.py")

    def test_a_symlinked_legacy_tree_is_not_chosen(self):
        with tempfile.TemporaryDirectory() as box:
            dest, outside_core = self._outside_tree(box, ap.LEGACY_HOOKS_REL.replace(
                os.path.join("scripts", "sage_harness", "hooks"),
                os.path.join("scripts", "sage_harness")))
            picked = hook_entry._resolve_core_dir(dest, None)
            self.assertNotEqual(os.path.realpath(picked),
                                os.path.dirname(os.path.dirname(outside_core)))
            self.assertFalse(os.path.realpath(picked).startswith(
                os.path.realpath(os.path.join(box, "outside"))))

    def test_a_symlinked_current_tree_is_not_chosen(self):
        with tempfile.TemporaryDirectory() as box:
            dest, _outside_core = self._outside_tree(box, ap.SAGE_TREE)
            picked = hook_entry._resolve_core_dir(dest, None)
            self.assertFalse(os.path.realpath(picked).startswith(
                os.path.realpath(os.path.join(box, "outside"))))

    def test_legacy_first_still_holds_for_real_trees(self):
        """방어를 넣느라 정상 계약을 깨지 않았는가. 전환점은 여전히 구 sentinel 이다."""
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            for rel in (ap.SENTINEL_REL,):
                target = Path(dest, ap._HOOKS_REL, rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("def dispatch():\n    return 0\n", encoding="utf-8")
            self.assertEqual(hook_entry._resolve_core_dir(dest, None),
                             ap.legacy_hooks_dir(dest))
            Path(dest, ap.LEGACY_HOOKS_REL, ap.SENTINEL_REL).unlink()
            self.assertEqual(hook_entry._resolve_core_dir(dest, None),
                             ap.hooks_dir(dest))


class TheEngineFreeProbeOwnsItsWorkspace(unittest.TestCase):
    """검사 하나가 남의 파일을 덮는 통로가 되면 안 된다.

    stub 을 공유 temp 의 **고정 이름**에 두면 그 이름을 남이 먼저 만들어 둘 수 있다. 그 안의
    `sage/` 가 프로젝트 밖을 가리키면 우리가 거기에 `__init__.py` 를 쓴다.
    """

    def test_the_probe_does_not_reuse_a_shared_fixed_path(self):
        legacy = os.path.join(tempfile.gettempdir(), "sage-migration-engine-absent")
        shutil.rmtree(legacy, ignore_errors=True)
        with tempfile.TemporaryDirectory() as dest:
            self.assertEqual(
                _sage(["install", "--host", "claude", "--dest", dest], cwd=REPO).returncode, 0)
            lm.runtime_loads(dest)
            self.assertFalse(os.path.exists(legacy), "고정 경로를 다시 쓴다")

    def test_a_squatted_workspace_cannot_reach_outside(self):
        legacy = os.path.join(tempfile.gettempdir(), "sage-migration-engine-absent")
        shutil.rmtree(legacy, ignore_errors=True)
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as dest:
            victim = Path(outside, "__init__.py")
            victim.write_text("# 사용자 파일\n", encoding="utf-8")
            os.makedirs(legacy, exist_ok=True)
            os.symlink(outside, os.path.join(legacy, "sage"))
            try:
                self.assertEqual(
                    _sage(["install", "--host", "claude", "--dest", dest], cwd=REPO).returncode, 0)
                loads, _detail = lm.runtime_loads(dest)
                self.assertTrue(loads)
                self.assertEqual(victim.read_text(encoding="utf-8"), "# 사용자 파일\n")
            finally:
                shutil.rmtree(legacy, ignore_errors=True)


class ReportingIsBestEffort(unittest.TestCase):
    """**안내를 못 만드는 것과 이행이 실패한 것은 다른 사건이다.**

    빈 부모 보고가 `apply()` 의 반환값을 만드는 마지막 단계였다. 거기서 오른 `OSError` 가
    호출부의 `except` 에 걸려 `migration_not_activated` 로 읽혔는데, 그 시점에 구 sentinel 은
    이미 지워져 있다 — **전환이 끝났는데 끝나지 않았다고 보고**했고, 출력은 "구 경로도
    그대로" 라고 말했다.

    원인은 예외를 안 잡은 것이 아니라 **실패해도 되는 코드가 실패하면 안 되는 코드의 반환
    경로에 있었던 것**이다. 그래서 조회를 `apply()` 밖으로 뺐다.
    """

    def test_apply_returns_only_the_transition_result(self):
        """부가 진단을 같은 튜플에 실으면 그 진단의 실패가 이행 실패로 읽힌다."""
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            plan = lm.plan(dest, manifest=_manifest(dest))
            self.assertEqual(len(lm.apply(dest, plan)), 3)

    def test_a_failing_reporter_keeps_the_activation_and_exit_zero(self):
        """**호출부의 방어를 직접 친다.**

        함수 안쪽에 실패를 주입하면 그 예외를 함수가 스스로 삼키므로 바깥 `except` 는 한 번도
        돌지 않는다. 그러면 "격리했다" 는 주장의 근거가 사실은 안쪽 방어뿐이다.
        """
        from sage.commands import upgrade as upgrade_cmd

        with tempfile.TemporaryDirectory() as dest:
            # `_finalize_layout` 은 신 트리가 배치·검증을 마친 뒤에 불린다. 그 상태를 만들어야
            # 이 테스트가 검사하려는 자리(보고 실패)까지 실제로 도달한다.
            _legacy_project(dest)
            with ap.layout_override(dest, ap.LAYOUT_CONSUMER_CURRENT):
                from sage.commands import install
                args = type("A", (), {"host": "claude", "dest": dest, "prefix": "sage",
                                      "force": True, "no_global_skill": False,
                                      "skill_scope": None})()
                assert install.run(args) == 0
            plan = {"migration": lm.plan(dest, manifest=_manifest(dest))}
            original = lm.empty_legacy_dirs

            def raises(_root):
                raise PermissionError("report denied")

            lm.empty_legacy_dirs = raises
            try:
                self.assertEqual(upgrade_cmd._finalize_layout(dest, plan, "ko"), (True, 1))
            finally:
                lm.empty_legacy_dirs = original
            self.assertEqual(ap.detect_layout(dest), ap.LAYOUT_CONSUMER_CURRENT)
            self.assertFalse(Path(dest, ap.LEGACY_HOOKS_REL, ap.SENTINEL_REL).exists())

    def test_only_the_unreadable_parent_drops_out_of_the_report(self):
        """한 경로 때문에 나머지 안내까지 잃지 않는다.

        `chmod 000` 을 쓰지 않는다 — Windows 에서 읽기 차단을 보장하지 않아, 거기서는 이
        테스트가 아무것도 검사하지 않은 채 통과한다.
        """
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            plan = lm.plan(dest, manifest=_manifest(dest))
            lm.apply(dest, plan)
            readable = lm.empty_legacy_dirs(dest)
            self.assertIn("schema", readable)

            blind = os.path.join(dest, "schema")
            real = os.listdir

            def denied(path, *args, **kwargs):
                if str(path) == blind:
                    raise PermissionError("report denied")
                return real(path, *args, **kwargs)

            os.listdir = denied
            try:
                partial = lm.empty_legacy_dirs(dest)
            finally:
                os.listdir = real
            self.assertNotIn("schema", partial)
            self.assertEqual(set(readable) - set(partial), {"schema"})


class LeftoverConvergesOnRerun(unittest.TestCase):
    """정리 중 파일 하나를 못 지우면 sentinel 은 이미 없으므로 판정이 `consumer` 다.

    거기서 멈추면 그 파일은 **영영 남는다** — "다음 실행에서 정리가 완료된다" 는 안내가
    거짓이 된다. Windows 실기에서 파일을 잠가 재현했고, 여기서는 잔재 상태를 직접 만든다.
    """

    def test_a_leftover_legacy_asset_is_cleaned_on_the_next_run(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            self.assertEqual(_sage(["upgrade", "--apply", "--root", dest],
                                   cwd=REPO).returncode, 0)
            self.assertEqual(ap.detect_layout(dest), ap.LAYOUT_CONSUMER_CURRENT)

            # 정리에 실패해 하나가 남은 상태를 만든다 — sentinel 은 이미 없다.
            stray = Path(dest, ap.LEGACY_HOOKS_REL, "runtime", "hook_runtime.py")
            stray.parent.mkdir(parents=True, exist_ok=True)
            source = Path(REPO, "scripts", "sage_harness", "hooks", "runtime", "hook_runtime.py")
            stray.write_bytes(source.read_bytes())

            plan = lm.plan(dest, manifest=_manifest(dest))
            self.assertTrue(plan["needed"])
            self.assertTrue(plan["cleanup_only"])
            done = _sage(["upgrade", "--apply", "--root", dest], cwd=REPO)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertFalse(stray.exists())

    def test_cleanup_only_does_not_claim_an_activation(self):
        """전환은 이미 끝났다. 다시 "전환했다" 고 말하면 사용자는 무엇이 바뀌었는지 오해한다."""
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            self.assertEqual(_sage(["upgrade", "--apply", "--root", dest],
                                   cwd=REPO).returncode, 0)
            stray = Path(dest, ap.LEGACY_HOOKS_REL, ".gitkeep")
            stray.parent.mkdir(parents=True, exist_ok=True)
            stray.write_text("", encoding="utf-8")
            done = _sage(["upgrade", "--apply", "--root", dest], cwd=REPO)
            self.assertNotIn("활성 경로 전환", done.stdout)


class EndToEnd(unittest.TestCase):
    def _upgrade(self, dest, mode):
        return _sage(["upgrade", mode, "--root", dest], cwd=REPO)

    def test_one_apply_switches_the_layout_and_keeps_user_files(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            Path(dest, "scripts", "deploy.sh").write_text("echo mine\n", encoding="utf-8")
            Path(dest, "scripts", "sage_harness", "hooks", "notes.md").write_text(
                "# 내 메모\n", encoding="utf-8")

            done = self._upgrade(dest, "--apply")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(ap.detect_layout(dest), ap.LAYOUT_CONSUMER_CURRENT)

            # 신 트리가 완전한가
            for rel in ("hooks", "schema", "verify-changes.sh"):
                self.assertTrue(os.path.exists(os.path.join(dest, "sage_harness", rel)), rel)
            # 구 SAGE 자산은 사라졌는가. **디렉터리는 남을 수 있다** — 빈 부모를 재귀로
            # 지우면 그 재귀가 링크를 만날 수 있어, 빈 폴더 하나를 치우려고 그 위험을 지지
            # 않는다. 남은 빈 폴더는 보고만 한다.
            self.assertFalse(os.listdir(os.path.join(dest, "schema")))
            self.assertFalse(os.path.exists(
                os.path.join(dest, "scripts", "sage_harness", "hooks", "runtime", "run_hook.py")))
            # 사용자 파일은 바이트 그대로인가
            self.assertEqual(Path(dest, "scripts", "deploy.sh").read_text(encoding="utf-8"),
                             "echo mine\n")
            self.assertEqual(
                Path(dest, "scripts", "sage_harness", "hooks", "notes.md").read_text(
                    encoding="utf-8"), "# 내 메모\n")

    def test_a_second_apply_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            self.assertEqual(self._upgrade(dest, "--apply").returncode, 0)
            again = self._upgrade(dest, "--apply")
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertEqual(ap.detect_layout(dest), ap.LAYOUT_CONSUMER_CURRENT)

    def test_check_changes_nothing(self):
        with tempfile.TemporaryDirectory() as dest:
            _legacy_project(dest)
            before = sorted(os.listdir(dest))
            self._upgrade(dest, "--check")
            self.assertEqual(ap.detect_layout(dest), ap.LAYOUT_CONSUMER_LEGACY)
            self.assertFalse(os.path.exists(os.path.join(dest, "sage_harness")))
            self.assertTrue(set(before).issubset(set(os.listdir(dest))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
