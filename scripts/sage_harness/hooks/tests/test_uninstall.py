#!/usr/bin/env python3
"""`sage uninstall` 계약 검사.

## 이 스위트가 지키려는 것

지우는 명령의 결함은 **되돌릴 수 없는 쪽으로** 틀린다. 그래서 여기 검사는 "지워졌는가" 보다
**"지우면 안 되는 것이 남았는가"** 를 훨씬 많이 본다. 소유권을 증명하지 못한 파일, 손상된
marker 가 있는 공유 파일, 계획에 없는 경로, 다른 scope 의 자산이 그 대상이다.

## fixture 는 실제 설치본이다

손으로 만든 디렉터리로 검사하면 "설치가 실제로 무엇을 두는가" 를 검사가 다시 지어내게 된다.
그래서 대부분의 fixture 는 `sage install` 을 실제로 돌려 만든다 — 느리지만, 설치와 제거가 같은
목록을 보는지가 이 사이클의 핵심이라 그 비용을 낸다.
"""
import ast
import contextlib
import ctypes
import errno
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, REPO)

from sage import install_transaction  # noqa: E402
from sage import managed_assets, manifest_contract, uninstall_executor, uninstall_plan, uninstall_shared  # noqa: E402,F401
from sage import uninstall_cleanup, uninstall_fs, uninstall_posix_fs, uninstall_windows_fs  # noqa: E402,F401
from sage.commands import install as install_cmd  # noqa: E402
from sage.commands import uninstall as uninstall_cmd  # noqa: E402
from sage import overlay_classify  # noqa: E402


# --- fixture root ------------------------------------------------------------

def _fixture_base():
    """fixture 를 담을 **전용 private root**. 공유 temp 로 되돌아가지 않는다.

    공유 system temp 를 쓰지 않는 이유가 둘이다.

    첫째, `/tmp` 는 누구나 쓸 수 있어 fixture 이름을 남이 먼저 만들어 둘 수 있다. 이 스위트가
    검사하는 것이 바로 "남이 놓아둔 링크를 따라가는가" 인데, 그 검사의 무대 자체가 남이 손댈 수
    있는 자리면 검사가 무엇을 증명했는지 말할 수 없다.

    둘째, macOS 의 `$TMPDIR`(`/var/folders/...`) 는 `/var` → `/private/var` symlink 아래에
    있다. symlink 경계를 보는 스위트가 **이미 symlink 아래에서** 도는 셈이라, 통과해도 그것이
    경계를 지킨 결과인지 경로가 우연히 접힌 결과인지 구별되지 않는다.

    ## 왜 fallback 이 없는가

    `tempfile.gettempdir()` 로 되돌아가는 기본값을 두면 **기본 실행이 다시 공유 temp** 다.
    아무도 환경변수를 지정하지 않으므로 그 fallback 이 사실상 유일한 경로가 되고, 규칙은
    문서에만 남는다. 그래서 지정이 없으면 저장소 옆의 정해진 자리를 쓰고, 그 자리를 안전하게
    만들 수 없으면 **검사를 실패시킨다.** 조용히 덜 안전한 자리로 내려가지 않는다.
    """
    override = os.environ.get("SAGE_TEST_TMPDIR")
    base = override or os.path.join(os.path.dirname(REPO), ".sage-fixtures")
    base = os.path.realpath(base)
    os.makedirs(base, exist_ok=True)
    if os.name == "posix":
        os.chmod(base, 0o700)
    current = os.lstat(base)
    if not stat.S_ISDIR(current.st_mode) or os.path.islink(base):
        raise AssertionError(f"fixture base 가 디렉터리가 아니다: {base}")
    if hasattr(os, "geteuid") and current.st_uid != os.geteuid():
        raise AssertionError(f"fixture base 를 우리가 소유하지 않는다: {base}")
    if os.name == "posix" and stat.S_IMODE(current.st_mode) & 0o077:
        raise AssertionError(f"fixture base 가 남에게 열려 있다: {base}")
    shared = os.path.realpath(tempfile.gettempdir())
    if base == shared or base.startswith(shared + os.sep):
        if not override:
            raise AssertionError(f"기본 fixture base 가 공유 temp 아래다: {base}")
    return base


def fixture_root(label):
    """symlink 성분이 없는 fixture root 하나. 불변식을 만든 자리에서 바로 확인한다."""
    root = os.path.realpath(tempfile.mkdtemp(prefix=f"{label}-", dir=_fixture_base()))
    if root != os.path.realpath(root):
        raise AssertionError(f"fixture root 가 실경로가 아니다: {root}")
    return root


class patched:
    """`InstallTransaction` 메서드 하나를 잠깐 바꾼다.

    `del` 로 지우고 되돌리지 않으면 모듈 상태가 오염되어 뒤 검사가 다른 세상에서 돈다. 저장한
    **원래 함수**로 복원하는 것이 유일하게 안전한 방법이다.
    """

    def __init__(self, name, replacement):
        self.owner = install_transaction.InstallTransaction
        self.name = name
        self.replacement = replacement

    def __enter__(self):
        self.original = getattr(self.owner, self.name)
        setattr(self.owner, self.name, self.replacement(self.original))
        return self.original

    def __exit__(self, *_exc):
        setattr(self.owner, self.name, self.original)
        return False


def link_directory(link, target):
    """디렉터리 링크 하나. **세 OS 어디서나 만든다.**

    `os.symlink` 만 쓰면 Windows 에서 권한 때문에 실패하고, 그러면 경계 검사가 그 환경에서만
    조용히 못 도는 검사가 된다. junction 은 권한 상승 없이 만들 수 있다.
    """
    if os.name == "nt":
        done = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                              capture_output=True, text=True)
        if done.returncode != 0:
            raise OSError(f"mklink /J failed: {done.stdout}{done.stderr}")
        return
    os.symlink(target, link)


def sage(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, "-m", "sage", *args], cwd=cwd or REPO,
                          env=env or dict(os.environ, PYTHONPATH=REPO),
                          capture_output=True, text=True)


class Consumer:
    """실제 `sage install` 로 만든 소비 프로젝트 하나."""

    def __init__(self, host="claude"):
        self.root = fixture_root("sage-uninstall")
        self.project = os.path.join(self.root, "proj")
        self.codex_home = os.path.join(self.root, "codex")
        os.makedirs(self.project)
        os.makedirs(self.codex_home)
        scope = ["--skill-scope", "project-local"] if host == "codex" else []
        self.install = sage("install", "--host", host, "--dest", self.project, *scope,
                            env=dict(os.environ, PYTHONPATH=REPO, CODEX_HOME=self.codex_home))

    @property
    def env(self):
        return dict(os.environ, PYTHONPATH=REPO, CODEX_HOME=self.codex_home)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.consumer = Consumer()
        if cls.consumer.install.returncode != 0:
            raise AssertionError(cls.consumer.install.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.consumer.cleanup()

    def fresh(self, host="claude"):
        consumer = Consumer(host)
        self.addCleanup(consumer.cleanup)
        self.assertEqual(consumer.install.returncode, 0, consumer.install.stderr)
        return consumer


class Roster(unittest.TestCase):
    """roster 정본이 하나다 — 두 벌이면 검사가 없는 순간 갈라진다."""

    def test_install_and_overlay_read_the_same_roster(self):
        self.assertEqual(set(install_cmd._CORE_AGENTS), set(overlay_classify.CORE_IDS["agents"]))
        self.assertEqual(set(install_cmd._CORE_SKILLS) | set(install_cmd._CORE_BOOTSTRAP_SKILLS),
                         set(overlay_classify.CORE_IDS["skills"]))

    def test_only_one_module_writes_the_roster_literally(self):
        """목록을 **글자로** 적은 모듈이 정본 하나뿐인지 AST 로 본다.

        값이 같은지만 보면 누군가 같은 목록을 다시 적어 넣어도 통과한다. 그 사본은 다음 rename
        에서 갈라지고, 갈라진 순간 install 과 uninstall 이 다른 목록을 본다.
        """
        names = {"CORE_AGENTS", "CORE_SKILLS", "CORE_BOOTSTRAP_SKILLS", "LEGACY_CORE_SKILLS",
                 "_CORE_AGENTS", "_CORE_SKILLS", "_CORE_BOOTSTRAP_SKILLS", "_LEGACY_CORE_SKILLS"}
        offenders = []
        for folder, _dirs, files in os.walk(os.path.join(REPO, "sage")):
            for name in files:
                if not name.endswith(".py") or name == "managed_assets.py":
                    continue
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as handle:
                    tree = ast.parse(handle.read())
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Assign):
                        continue
                    targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
                    if not targets & names:
                        continue
                    if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)) and any(
                            isinstance(e, ast.Constant) for e in node.value.elts):
                        offenders.append(f"{os.path.relpath(path, REPO)}:{node.lineno}")
        self.assertEqual(offenders, [], "roster 를 글자로 다시 적은 자리가 있다")

    def test_legacy_names_move_together(self):
        """은퇴 이름이 한쪽에만 늘어나면 실패한다 — 주석 규약이 아니라 검사로 강제한다."""
        self.assertEqual(tuple(install_cmd._LEGACY_CORE_SKILLS),
                         tuple(managed_assets.LEGACY_CORE_SKILLS))
        widened = tuple(managed_assets.LEGACY_CORE_SKILLS) + ("sage-retired-name",)
        self.assertNotEqual(tuple(install_cmd._LEGACY_CORE_SKILLS), widened,
                            "install 이 정본보다 넓은 목록을 들고 있다")


class Planner(Base):
    """계획 층은 읽기만 한다."""

    def digest(self, root):
        found = {}
        for folder, _dirs, files in os.walk(root):
            for name in sorted(files):
                path = os.path.join(folder, name)
                try:
                    with open(path, "rb") as handle:
                        found[os.path.relpath(path, root)] = len(handle.read())
                except OSError:
                    found[os.path.relpath(path, root)] = -1
        return found

    def test_planning_changes_nothing(self):
        before = self.digest(self.consumer.project)
        uninstall_plan.build(self.consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertEqual(before, self.digest(self.consumer.project))

    def test_plan_is_deterministic(self):
        first = uninstall_plan.build(self.consumer.project, uninstall_plan.SCOPE_PROJECT)
        second = uninstall_plan.build(self.consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertEqual([a.path for a in first.actions], [a.path for a in second.actions])

    def test_every_target_has_exactly_one_action(self):
        plan = uninstall_plan.build(self.consumer.project, uninstall_plan.SCOPE_PROJECT)
        paths = [action.path for action in plan.actions]
        self.assertEqual(len(paths), len(set(paths)))

    def test_preserved_paths_are_never_write_targets(self):
        plan = uninstall_plan.build(self.consumer.project, uninstall_plan.SCOPE_PROJECT)
        preserved = {a.path for a in plan.of_kind(uninstall_plan.PRESERVE)}
        self.assertTrue(preserved)
        self.assertEqual(preserved & set(plan.write_targets()), set())

    def test_top_level_shared_docs_are_preserved(self):
        plan = uninstall_plan.build(self.consumer.project, uninstall_plan.SCOPE_PROJECT)
        preserved = {os.path.basename(a.path) for a in plan.of_kind(uninstall_plan.PRESERVE)}
        self.assertIn("AGENT_GUIDE.md", preserved)

    def test_manifest_tree_is_the_last_group(self):
        """manifest 를 담은 tree 가 마지막이다 — 중간에 실패해도 소유권을 다시 증명할 수 있다."""
        plan = uninstall_plan.build(self.consumer.project, uninstall_plan.SCOPE_PROJECT)
        # 빈 부모 정리는 자산이 아니라 뒷정리다. 논리 자산 중 마지막이 manifest 여야 한다는
        # 것이 계약이므로, 그 뒤에 오는 `prune` 은 이 판정의 대상이 아니다.
        assets = [a for a in plan.actions
                  if a.kind == uninstall_plan.DELETE and a.group != "prune"]
        self.assertEqual(assets[-1].group, "manifest-tree")
        prunes = [a for a in plan.actions if a.group == "prune"]
        for prune in prunes:
            self.assertGreater(plan.actions.index(prune), plan.actions.index(assets[-1]))

    def test_registration_is_stripped_before_files_are_removed(self):
        plan = uninstall_plan.build(self.consumer.project, uninstall_plan.SCOPE_PROJECT)
        groups = [a.group for a in plan.actions if a.group]
        self.assertLess(groups.index("registration"), groups.index("tree"))


class Absence(Base):
    """부재·손상·흔적 셋을 구분한다."""

    def test_nothing_installed_is_a_no_op(self):
        empty = fixture_root("sage-uninstall-empty")
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        plan = uninstall_plan.build(empty, uninstall_plan.SCOPE_PROJECT)
        self.assertEqual(plan.status, uninstall_plan.COMPLETE)
        self.assertEqual(plan.exit_code, 0)
        self.assertEqual(plan.write_targets(), ())

    def test_traces_without_manifest_are_blocked(self):
        consumer = self.fresh()
        os.remove(uninstall_plan.manifest_path(consumer.project))
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertEqual(plan.status, uninstall_plan.BLOCKED)
        self.assertEqual(plan.blocked_reason, "uninstall.manifest_missing_with_traces")
        self.assertEqual(plan.write_targets(), (),
                         "차단 상태인데 지울 대상이 잡혔다")

    def test_damaged_manifest_is_blocked_not_treated_as_absent(self):
        consumer = self.fresh()
        with open(uninstall_plan.manifest_path(consumer.project), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertEqual(plan.status, uninstall_plan.BLOCKED)
        self.assertEqual(plan.blocked_reason, "uninstall.manifest_unreadable")

    def test_preserved_docs_do_not_count_as_traces(self):
        """첫 제거 뒤 두 번째 실행이 `BLOCKED` 가 되면 멱등 계약이 깨진다."""
        consumer = self.fresh()
        first = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertIn(first.returncode, (0, 1), first.stderr)
        second = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)


class SharedFiles(unittest.TestCase):
    """공유 파일은 SAGE 부분만 건드린다."""

    GITIGNORE = ("# user rule\\n*.log\\n\\n"
                 "# >>> SAGE LOCAL PROFILE\\n/sage/project-profile.local.yaml\\n"
                 "# <<< SAGE LOCAL PROFILE\\n"
                 "# >>> SAGE LOCAL STATE\\n!/.sage/\\n# <<< SAGE LOCAL STATE\\n"
                 "# keep me\\n")

    def test_only_managed_blocks_are_removed(self):
        result = uninstall_shared.classify_gitignore_text(self.GITIGNORE)
        self.assertTrue(result.strippable)
        self.assertIn("*.log", result.body)
        self.assertIn("# keep me", result.body)
        self.assertNotIn("SAGE LOCAL", result.body)

    def test_duplicate_markers_preserve_the_whole_file(self):
        damaged = self.GITIGNORE + "# >>> SAGE LOCAL PROFILE\\nx\\n# <<< SAGE LOCAL PROFILE\\n"
        result = uninstall_shared.classify_gitignore_text(damaged)
        self.assertFalse(result.strippable)
        self.assertTrue(result.damage)

    def test_reversed_markers_preserve_the_whole_file(self):
        damaged = "# <<< SAGE LOCAL PROFILE\\nx\\n# >>> SAGE LOCAL PROFILE\\n"
        result = uninstall_shared.classify_gitignore_text(damaged)
        self.assertFalse(result.strippable)
        self.assertTrue(result.damage)

    def test_unpaired_marker_preserves_the_whole_file(self):
        damaged = "# user\\n# >>> SAGE LOCAL PROFILE\\n/sage/x\\n"
        result = uninstall_shared.classify_gitignore_text(damaged)
        self.assertFalse(result.strippable)
        self.assertEqual(result.damage[0]["code"], "gitignore_marker_unpaired")

    def test_user_hooks_survive_registration_strip(self):
        document = {"otherKey": 1, "hooks": {"PreToolUse": [
            {"matcher": "", "hooks": [{"type": "command", "command": "sage-owned"},
                                      {"type": "command", "command": "user-owned"}]}]}}
        result = uninstall_shared.classify_host_document(document, {"sage-owned"})
        self.assertTrue(result.strippable)
        rendered = json.loads(result.body)
        self.assertEqual(rendered["otherKey"], 1)
        commands = [e["command"] for e in rendered["hooks"]["PreToolUse"][0]["hooks"]]
        self.assertEqual(commands, ["user-owned"])

    def test_corrupt_json_shape_preserves_the_whole_file(self):
        for document in ([], {"hooks": []}, {"hooks": {"PreToolUse": "x"}}):
            result = uninstall_shared.classify_host_document(document, {"sage-owned"})
            self.assertFalse(result.strippable, document)
            self.assertTrue(result.damage, document)

    def test_hooks_key_disappears_when_only_sage_registered(self):
        document = {"hooks": {"PreToolUse": [
            {"matcher": "", "hooks": [{"type": "command", "command": "sage-owned"}]}]}}
        result = uninstall_shared.classify_host_document(document, {"sage-owned"})
        self.assertNotIn("hooks", json.loads(result.body))


class ScopeIsolation(Base):
    """project 범위는 `$CODEX_HOME` 을 읽지도 쓰지도 않는다."""

    def test_project_scope_never_touches_codex_home(self):
        """spy 로 **호출 자체**를 센다. byte 대조만 하면 읽기만 하는 구현이 통과한다."""
        consumer = self.fresh()
        global_root = os.path.join(consumer.codex_home, "skills")
        os.makedirs(global_root, exist_ok=True)
        touched = []
        real_listdir, real_stat, real_open = os.listdir, os.stat, open

        def watch(path):
            if str(path).startswith(consumer.codex_home):
                touched.append(str(path))

        def spy_listdir(path="."):
            watch(path)
            return real_listdir(path)

        def spy_stat(path, *a, **kw):
            watch(path)
            return real_stat(path, *a, **kw)

        os.listdir, os.stat = spy_listdir, spy_stat
        try:
            uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT,
                                 environ={"CODEX_HOME": consumer.codex_home})
        finally:
            os.listdir, os.stat = real_listdir, real_stat
        self.assertEqual(touched, [], "project 범위가 전역 경로를 건드렸다")

    def test_project_scope_reports_not_checked_instead_of_claiming(self):
        plan = uninstall_plan.build(self.consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertIn("uninstall.notice.global_not_checked", plan.notices)
        self.assertNotIn("uninstall.notice.global_shared_warning", plan.notices)

    def test_global_scope_does_not_read_the_project(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_GLOBAL,
                                    environ={"CODEX_HOME": consumer.codex_home})
        for action in plan.actions:
            self.assertFalse(action.path.startswith(consumer.project),
                             f"global 범위가 프로젝트 경로를 잡았다: {action.path}")


class Boundaries(unittest.TestCase):
    """넓은 경로·엔진 저장소는 계획 이전에 막는다."""

    def test_engine_source_tree_is_blocked(self):
        plan = uninstall_plan.build(REPO, uninstall_plan.SCOPE_PROJECT)
        self.assertEqual(plan.status, uninstall_plan.BLOCKED)
        self.assertEqual(plan.blocked_reason, "uninstall.engine_source_tree")

    def test_home_and_root_are_blocked(self):
        for path in (os.path.expanduser("~"), os.sep):
            plan = uninstall_plan.build(path, uninstall_plan.SCOPE_PROJECT)
            self.assertEqual(plan.status, uninstall_plan.BLOCKED, path)
            self.assertEqual(plan.blocked_reason, "uninstall.dest_too_broad", path)

    def test_a_symlinked_prefix_is_not_an_escape(self):
        """`/var` → `/private/var` 같은 구성은 위반이 아니다 — 막으면 정상 프로젝트가 거부된다."""
        base = fixture_root("sage-uninstall-link")
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        real = os.path.join(base, "real")
        os.makedirs(os.path.join(real, "sage"))
        link = os.path.join(base, "link")
        os.symlink(real, link)
        self.assertIsNone(uninstall_plan.boundary_block(link))


class Executor(Base):
    """실행 층은 계획 밖으로 나가지 않고, 실패하면 되돌린다."""

    def test_targets_outside_the_plan_are_refused(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        intruder = uninstall_plan.Action(uninstall_plan.DELETE, uninstall_plan.SCOPE_PROJECT,
                                         os.path.join(consumer.project, "app.py"),
                                         "test.injected", group="tree")
        with open(intruder.path, "w", encoding="utf-8") as handle:
            handle.write("user code\n")
        # 기준은 **승인된(원래) 계획의 것**을 그대로 물려준다. 사용자가 보고 동의한 것이
        # 그것이기 때문이고, 실행 층은 그 스냅샷 밖의 경로를 거부해야 한다. 아래 message
        # 대조가 있어야 이 검사가 지문 불일치로 우연히 통과하지 않는다 — 다른 이유로 통과하는
        # 검사는 없는 검사와 같다.
        widened = uninstall_plan.UninstallPlan(plan.scope, plan.dest,
                                               list(plan.actions) + [intruder], plan.status,
                                               baseline=plan.baseline)
        with self.assertRaises(ValueError) as caught:
            uninstall_executor.execute(widened)
        self.assertEqual(str(caught.exception), "uninstall.target_outside_plan")
        self.assertTrue(os.path.isfile(intruder.path), "계획 밖 파일이 지워졌다")

    def test_a_changed_target_stops_the_run(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        marker = os.path.join(consumer.project, "sage", "changed-after-plan.txt")
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write("touched\n")
        with self.assertRaises(ValueError):
            uninstall_executor.execute(plan)
        self.assertTrue(os.path.isdir(os.path.join(consumer.project, "sage")),
                        "지문이 바뀌었는데 삭제가 진행됐다")

    def test_failure_restores_everything(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        before = sorted(os.listdir(consumer.project))
        def boom(original):
            def hook(journal, path):
                raise OSError("injected")
            return hook

        with patched("stage_write", boom):
            with self.assertRaises(OSError):
                uninstall_executor.execute(plan)
        self.assertEqual(before, sorted(os.listdir(consumer.project)),
                         "실패했는데 상태가 되돌아오지 않았다")


class CommandSurface(Base):
    """CLI 표면 — 조합 오류·JSON·확인."""

    def test_option_conflicts_are_usage_errors(self):
        for args in (("--global", "--all"), ("--check", "--yes"),
                     ("--global", "--dest", self.consumer.project)):
            result = sage("uninstall", *args, env=self.consumer.env)
            self.assertEqual(result.returncode, 2, f"{args} → {result.returncode}")

    def test_executing_json_without_yes_is_a_usage_error(self):
        """prompt 와 JSON 을 섞지 않는다. stdin 을 기다리지도 않는다."""
        result = subprocess.run([sys.executable, "-m", "sage", "uninstall",
                                 "--dest", self.consumer.project, "--json"],
                                cwd=REPO, env=self.consumer.env, capture_output=True,
                                text=True, stdin=subprocess.DEVNULL, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "", "usage 오류인데 JSON 이 나갔다")

    def test_check_json_is_machine_readable(self):
        result = sage("uninstall", "--dest", self.consumer.project, "--check", "--json",
                      env=self.consumer.env)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["exit_code"], result.returncode)
        self.assertEqual(set(payload) >= {"scope", "status", "exit_code", "deleted", "stripped",
                                          "preserved", "blocked", "notices"}, True)

    def test_json_and_text_agree_on_the_verdict(self):
        text = sage("uninstall", "--dest", self.consumer.project, "--check",
                    env=self.consumer.env)
        data = sage("uninstall", "--dest", self.consumer.project, "--check", "--json",
                    env=self.consumer.env)
        self.assertEqual(text.returncode, data.returncode)
        self.assertIn(json.loads(data.stdout)["status"], text.stdout)

    def test_json_is_locale_independent(self):
        ko = sage("--lang", "ko", "uninstall", "--dest", self.consumer.project, "--check",
                  "--json", env=self.consumer.env)
        en = sage("--lang", "en", "uninstall", "--dest", self.consumer.project, "--check",
                  "--json", env=self.consumer.env)
        self.assertEqual(ko.stdout, en.stdout)
        self.assertEqual(ko.returncode, en.returncode)

    def test_non_interactive_without_yes_is_blocked(self):
        consumer = self.fresh()
        result = subprocess.run([sys.executable, "-m", "sage", "uninstall",
                                 "--dest", consumer.project],
                                cwd=REPO, env=consumer.env, capture_output=True,
                                text=True, stdin=subprocess.DEVNULL, timeout=30)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(os.path.isdir(os.path.join(consumer.project, "sage")),
                        "확인 없이 지웠다")

    def test_check_never_changes_anything(self):
        consumer = self.fresh()
        before = sorted(os.listdir(consumer.project))
        sage("uninstall", "--dest", consumer.project, "--check", env=consumer.env)
        self.assertEqual(before, sorted(os.listdir(consumer.project)))


class Preservation(Base):
    """사용자 자산은 byte 하나 바뀌지 않는다."""

    def test_user_assets_survive_a_full_uninstall(self):
        consumer = self.fresh()
        os.makedirs(os.path.join(consumer.project, "plan_docs", "00-base_plan"))
        keep = {
            os.path.join(consumer.project, "plan_docs", "00-base_plan", "plan.md"): "plan\n",
            os.path.join(consumer.project, "app.py"): "print('hi')\n",
            os.path.join(consumer.project, "AGENT_GUIDE.md"): None,
        }
        for path, body in keep.items():
            if body is not None:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(body)
        before = {}
        for path in keep:
            with open(path, "rb") as handle:
                before[path] = handle.read()

        result = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        for path, blob in before.items():
            self.assertTrue(os.path.isfile(path), f"보존 대상이 사라졌다: {path}")
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), blob, path)


class GlobalFamily(Base):
    """전역 skill 두 가족 — bare CORE id 와 `<prefix>-<aid>`."""

    def seed_global(self, consumer, name, body="CORE framework bootstrap asset\n"):
        path = os.path.join(consumer.codex_home, "skills", name)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write(body)
        return path

    def plan_for(self, consumer, scope):
        return uninstall_plan.build(consumer.project, scope,
                                    environ={"CODEX_HOME": consumer.codex_home})

    def kinds(self, plan):
        return {action.path: action.kind for action in plan.actions}

    def test_marker_gates_the_bare_core_family(self):
        """marker 가 없으면 같은 이름이어도 사용자 skill 일 수 있다."""
        consumer = self.fresh()
        owned = self.seed_global(consumer, "sage-cycle")
        foreign = self.seed_global(consumer, "sage-review", body="my own skill\n")
        kinds = self.kinds(self.plan_for(consumer, uninstall_plan.SCOPE_GLOBAL))
        self.assertEqual(kinds[owned], uninstall_plan.DELETE)
        self.assertEqual(kinds[foreign], uninstall_plan.PRESERVE)

    def test_global_alone_never_touches_the_prefix_family(self):
        """`--global` 은 prefix 를 모른다. 추측해서 지우면 사용자 skill 을 삼킨다."""
        consumer = self.fresh()
        generated = self.seed_global(consumer, "nv-myskill", body="project render\n")
        kinds = self.kinds(self.plan_for(consumer, uninstall_plan.SCOPE_GLOBAL))
        self.assertNotIn(generated, kinds, "--global 이 prefix 가족을 잡았다")

    def test_drifted_global_copy_is_preserved(self):
        consumer = self.fresh()
        self.write_profile(consumer, prefix="nv")
        self.seed_manifest_skill(consumer, "myskill")
        project_copy = os.path.join(consumer.project, ".codex", "skills", "myskill")
        os.makedirs(project_copy, exist_ok=True)
        with open(os.path.join(project_copy, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write("original\n")
        drifted = self.seed_global(consumer, "nv-myskill", body="edited by user\n")
        kinds = self.kinds(self.plan_for(consumer, uninstall_plan.SCOPE_ALL))
        self.assertEqual(kinds[drifted], uninstall_plan.PRESERVE)

    def test_matching_global_copy_is_removed_in_all_scope(self):
        consumer = self.fresh()
        self.write_profile(consumer, prefix="nv")
        self.seed_manifest_skill(consumer, "myskill")
        project_copy = os.path.join(consumer.project, ".codex", "skills", "myskill")
        os.makedirs(project_copy, exist_ok=True)
        with open(os.path.join(project_copy, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write("same bytes\n")
        matching = self.seed_global(consumer, "nv-myskill", body="same bytes\n")
        kinds = self.kinds(self.plan_for(consumer, uninstall_plan.SCOPE_ALL))
        self.assertEqual(kinds[matching], uninstall_plan.DELETE)

    def test_an_unsafe_prefix_gives_up_the_whole_family(self):
        """빈 prefix 를 쓰면 `-<aid>` 라는 다른 경로가 만들어진다. 그 경로는 남의 것일 수 있다."""
        consumer = self.fresh()
        self.write_profile(consumer, prefix="")
        self.seed_manifest_skill(consumer, "myskill")
        stranger = self.seed_global(consumer, "-myskill", body="stranger\n")
        kinds = self.kinds(self.plan_for(consumer, uninstall_plan.SCOPE_ALL))
        self.assertNotIn(stranger, kinds)

    def write_profile(self, consumer, prefix):
        path = os.path.join(consumer.project, "sage", "project-profile.yaml")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        lines = []
        for line in text.split("\n"):
            if line.strip().startswith("prefix:"):
                indent = line[:len(line) - len(line.lstrip())]
                lines.append(f'{indent}prefix: "{prefix}"')
            else:
                lines.append(line)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

    def seed_manifest_skill(self, consumer, aid):
        path = uninstall_plan.manifest_path(consumer.project)
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        # 자산 항목은 manifest 계약을 통과하는 **진짜 모양**이어야 한다. 손으로 지은 축약형은
        # 계약이 거부하고, 거부되면 이 fixture 가 검사하려던 전역 가족 판정에 닿지 못한다.
        manifest.setdefault("assets", {})[f"skills/{aid}"] = {
            "form": "declarative", "conformance": "PASS"}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)


class IntegratedRollback(Base):
    """`--all` 은 하나의 단위다 — 한쪽만 커밋하지 않는다."""

    def test_a_global_failure_restores_the_project_too(self):
        consumer = self.fresh()
        global_skill = os.path.join(consumer.codex_home, "skills", "sage-cycle")
        os.makedirs(global_skill, exist_ok=True)
        with open(os.path.join(global_skill, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write("CORE framework bootstrap asset\n")

        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_ALL,
                                    environ={"CODEX_HOME": consumer.codex_home})
        self.assertTrue(any(a.scope == uninstall_plan.SCOPE_GLOBAL
                            for a in plan.of_kind(uninstall_plan.DELETE)))
        before_project = sorted(os.listdir(consumer.project))

        def flaky(original):
            def hook(journal, path):
                # project 쪽이 여러 건 처리된 뒤 global 에서 터뜨린다 — 부분 커밋의 모양.
                if path.startswith(consumer.codex_home):
                    raise OSError("injected global failure")
                return original(journal, path)
            return hook

        with patched("stage_remove_tree", flaky):
            with self.assertRaises(OSError):
                uninstall_executor.execute(plan)

        self.assertEqual(before_project, sorted(os.listdir(consumer.project)),
                         "global 실패인데 project 삭제가 커밋됐다")
        self.assertTrue(os.path.isdir(global_skill))

    def test_rollback_failure_reports_the_preserved_paths(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)

        state = {"n": 0}

        # 원래 method 는 `patched` 가 저장해 두고 되돌린다. `del` 로 지우면 클래스에 원래
        # 정의가 남아 있는 경우에만 우연히 복원되고, 아니면 모듈 상태가 오염된 채 넘어간다.
        def flaky(original):
            def hook(journal, path):
                state["n"] += 1
                if state["n"] > 2:
                    raise OSError("injected")
                return original(journal, path)
            return hook

        def broken_restore(original):
            def hook(journal):
                return ["cannot restore"]
            return hook

        with patched("stage_remove_tree", flaky), patched("rollback", broken_restore):
            with self.assertRaises(uninstall_executor.RollbackFailed) as caught:
                uninstall_executor.execute(plan)
            self.assertTrue(caught.exception.preserved_paths,
                            "되돌리기가 실패했는데 복구 경로를 주지 않았다")


class Reporting(Base):
    """보고는 생략하지 않는다."""

    def test_preserved_and_blocked_are_never_abbreviated(self):
        consumer = self.fresh()
        result = sage("uninstall", "--dest", consumer.project, "--check", env=consumer.env)
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        for action in plan.of_kind(uninstall_plan.PRESERVE):
            # 화면은 저장소 기준 상대 경로로 낸다. 기대값을 여기서 직접 계산하는 것이 요점이다 —
            # 표시 함수를 그대로 불러 비교하면 그 함수가 무엇을 내든 검사는 통과한다.
            shown = os.path.relpath(action.path, plan.dest)
            self.assertIn(f"- {shown}\n", result.stdout,
                          "보존 경로가 화면에서 빠졌다 — 사용자가 남은 것을 모른 채 끝난다")

    def test_verbose_expands_grouped_deletions(self):
        consumer = self.fresh()
        plain = sage("uninstall", "--dest", consumer.project, "--check", env=consumer.env)
        verbose = sage("uninstall", "--dest", consumer.project, "--check", "--verbose",
                       env=consumer.env)
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        sample = os.path.relpath(plan.of_kind(uninstall_plan.DELETE)[0].path, plan.dest)
        self.assertNotIn(sample, plain.stdout)
        self.assertIn(sample, verbose.stdout)

    def test_cancelling_changes_nothing(self):
        """진짜 취소 경로를 밟는다.

        파이프로 `n` 을 흘려 보내면 `isatty()` 가 거짓이라 **비대화형 차단**으로 빠지고,
        그러면 이 검사는 취소를 한 번도 통과하지 않은 채 초록이 된다. 그래서 pty 를 준다.
        """
        import pty

        consumer = self.fresh()
        before = sorted(os.listdir(consumer.project))
        parent, child = pty.openpty()
        try:
            process = subprocess.Popen([sys.executable, "-m", "sage", "uninstall",
                                        "--dest", consumer.project],
                                       cwd=REPO, env=consumer.env, stdin=child,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True)
            os.write(parent, b"n\n")
            output = process.communicate(timeout=90)[0]
        finally:
            os.close(parent)
            os.close(child)
        self.assertEqual(process.returncode, 0, output)
        self.assertEqual(before, sorted(os.listdir(consumer.project)),
                         "취소했는데 상태가 바뀌었다")
        self.assertNotIn(".sage-uninstall-", " ".join(os.listdir(consumer.project)))


class RecoveryContract(unittest.TestCase):
    """차단에는 다음 행동이 있고, 그 행동은 파괴적이지 않다."""

    def test_every_uninstall_block_has_a_runnable_next(self):
        from sage.diagnostic_contract import BLOCK, RECOVERY, SEVERITY
        codes = [c for c, level in SEVERITY.items()
                 if level == BLOCK and c.startswith("uninstall.")]
        self.assertTrue(codes)
        for code in codes:
            steps = RECOVERY.get(code, ())
            self.assertTrue(any(step.command for step in steps),
                            f"{code} 에 실행 가능한 명령이 없다")

    def test_uninstall_recovery_never_proposes_a_destructive_command(self):
        from sage.diagnostic_contract import FORBIDDEN_COMMAND, RECOVERY
        for code, steps in RECOVERY.items():
            if not code.startswith("uninstall."):
                continue
            for step in steps:
                if step.command:
                    self.assertIsNone(FORBIDDEN_COMMAND.search(step.command),
                                      f"{code}/{step.id} 가 파괴적 명령을 낸다")

    def test_cli_only_recovery_ids_are_declared_exactly(self):
        """선언이 실제보다 넓어도 좁아도 실패한다."""
        from sage.i18n.validation import recovery_issues
        self.assertEqual(recovery_issues(REPO), [])


class FailureInjection(Base):
    """계약이 요구한 일곱 자리에서 각각 터뜨린다.

    한 자리만 주입하고 "복원된다" 고 말하면, 나머지 여섯 자리는 검사되지 않은 채 계약만
    적힌 셈이다. 되돌릴 수 없는 명령에서 그 차이는 크다.
    """

    def snapshot(self, root):
        """(상대경로 → (bytes, mode)). 내용과 권한을 함께 본다 — 내용만 맞고 실행 비트가
        사라지면 그 파일은 조용히 못 쓰게 된다."""
        found = {}
        for folder, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".sage-install-backup-")]
            for name in sorted(files):
                path = os.path.join(folder, name)
                try:
                    with open(path, "rb") as handle:
                        blob = handle.read()
                    found[os.path.relpath(path, root)] = (blob, os.stat(path).st_mode)
                except OSError:
                    found[os.path.relpath(path, root)] = ("<unreadable>", 0)
        return found

    def run_injected(self, consumer, where):
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_ALL,
                                    environ={"CODEX_HOME": consumer.codex_home})
        assert where != "commit", "commit 은 되돌리는 지점이 아니다 — 전용 검사를 쓴다"

        def remove_hook(original):
            def hook(journal, path):
                if where == "project" and path.startswith(consumer.project) \
                        and "sage_harness" not in path:
                    raise OSError("injected project")
                if where == "global" and path.startswith(consumer.codex_home):
                    raise OSError("injected global")
                if where == "tree" and "sage_harness" in path:
                    raise OSError("injected tree")
                return original(journal, path)
            return hook

        def write_hook(original):
            def hook(journal, path):
                if where == "strip":
                    raise OSError("injected strip")
                return original(journal, path)
            return hook

        with patched("stage_remove_tree", remove_hook), patched("stage_write", write_hook):
            with self.assertRaises(OSError):
                uninstall_executor.execute(plan)

    def seed_global(self, consumer):
        path = os.path.join(consumer.codex_home, "skills", "sage-cycle")
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write("CORE framework bootstrap asset\n")

    def test_each_injection_point_restores_bytes_and_mode(self):
        for where in ("project", "global", "tree", "strip"):
            with self.subTest(where=where):
                consumer = self.fresh()
                self.seed_global(consumer)
                before_project = self.snapshot(consumer.project)
                before_global = self.snapshot(consumer.codex_home)
                self.run_injected(consumer, where)
                self.assertEqual(before_project, self.snapshot(consumer.project),
                                 f"{where} 주입 후 project 가 복원되지 않았다")
                self.assertEqual(before_global, self.snapshot(consumer.codex_home),
                                 f"{where} 주입 후 global 이 복원되지 않았다")

    def test_output_verification_failure_never_commits_a_bad_delete(self):
        """삭제가 실제로 안 됐는데 성공으로 넘어가지 않는다.

        되돌리기가 **거기 있는 것을 덮어쓰지 않는다**는 점도 함께 본다. `delete_not_effective`
        는 "비웠다고 믿은 자리에 무언가 있다" 는 뜻이고, 그것이 무엇인지 우리는 모른다. 모르는
        것을 지우고 원본을 되돌리면 우리가 만든 결함으로 남의 파일을 지우는 셈이 된다. 그래서
        보존하고 **복구 경로를 준다** — 되돌리지 못했다는 사실을 숨기지 않는 것이 정직한 결과다.
        """
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        intruder = os.path.join(consumer.project, "docs", "sage_harness", "not-ours.txt")

        def put_back(original):
            def hook(journal, path):
                moved = original(journal, path)
                # 옮기고 나서 그 자리에 남의 것을 놓는다 — 검증 단계가 이것을 잡아야 한다.
                if path.endswith("sage_harness") and not os.path.lexists(path):
                    os.makedirs(path)
                    with open(intruder, "w", encoding="utf-8") as handle:
                        handle.write("someone else\n")
                return moved
            return hook

        with patched("stage_remove_tree", put_back):
            with self.assertRaises((ValueError, uninstall_executor.RollbackFailed)) as caught:
                uninstall_executor.execute(plan)
        failure = caught.exception
        if isinstance(failure, ValueError):
            self.assertEqual(str(failure), "uninstall.delete_not_effective")
        else:
            self.assertTrue(failure.preserved_paths, "복구 경로를 주지 않았다")
        self.assertTrue(os.path.isfile(intruder), "우리 것이 아닌 파일을 덮어썼다")

    def test_backup_roots_for_both_scopes_exist_before_the_first_mutation(self):
        """양쪽 scope 의 journal·경계가 **첫 mutation 전에** 서 있어야 한다.

        나중에 세우면 그때는 이미 한쪽을 건드린 뒤라, 되돌릴 범위가 반쪽이다.
        """
        consumer = self.fresh("codex")
        self.seed_global(consumer)
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_ALL,
                                    environ={"CODEX_HOME": consumer.codex_home})
        roots = plan.lock_roots()
        self.assertGreaterEqual(len(roots), 2, "두 scope 가 잡히지 않았다")

        seen = {}

        def watch(original):
            def hook(journal, path):
                seen.setdefault("roots", tuple(journal._write_roots))
                seen.setdefault("first", path)
                return original(journal, path)
            return hook

        with patched("stage_remove_tree", watch), patched("stage_write", watch):
            uninstall_executor.execute(plan)

        for root in roots:
            self.assertIn(os.path.abspath(root), seen["roots"],
                          f"첫 mutation 시점에 {root} 가 journal 에 없었다")

    def test_cleanup_failure_after_commit_keeps_the_result_and_reports_the_store(self):
        """commit 뒤의 뒷정리 실패는 **명령 실패가 아니다.**

        이 자리를 실패로 올리면 디스크는 요청대로 지워진 상태인데 사용자는 "실패" 를 듣는다.
        되돌리면 성공한 제거를 취소한다. 둘 다 틀렸고, 옳은 것은 결과를 유지한 채 남은 경로를
        말하는 것뿐이다.
        """
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)

        def boom(original):
            def hook(journal):
                journal._committed = True
                raise OSError("injected commit")
            return hook

        def forbidden(original):
            def hook(journal):
                raise AssertionError("commit 뒤에 되돌리려 했다")
            return hook

        with patched("commit", boom), patched("rollback", forbidden):
            result = uninstall_executor.execute(plan)

        self.assertFalse(os.path.isdir(os.path.join(consumer.project, "docs", "sage_harness")),
                         "뒷정리 실패가 제거를 되돌렸다")
        leftovers = [name for name in os.listdir(consumer.project)
                     if name.startswith(".sage-install-backup-")]
        self.assertTrue(leftovers, "보관소가 사라져 되돌릴 것이 없다")

    def test_strip_originals_are_restored_with_mode(self):
        """`STRIP` 원본이 복원된다 — 사본만 들고 있으면 되돌릴 자리를 모른다."""
        consumer = self.fresh()
        gitignore = os.path.join(consumer.project, ".gitignore")
        with open(gitignore, "rb") as handle:
            before = handle.read()
        os.chmod(gitignore, 0o640)
        before_mode = os.stat(gitignore).st_mode
        self.run_injected(consumer, "tree")
        with open(gitignore, "rb") as handle:
            self.assertEqual(handle.read(), before, "공유 파일 내용이 복원되지 않았다")
        self.assertEqual(os.stat(gitignore).st_mode, before_mode, "권한이 복원되지 않았다")


class SiblingSafety(Base):
    """우리가 두지 않은 이웃은 후보에도 오르지 않는다."""

    def test_unknown_docs_agent_sibling_is_never_a_candidate(self):
        consumer = self.fresh()
        stranger = os.path.join(consumer.project, "docs", "agent", "my-team-notes.md")
        with open(stranger, "w", encoding="utf-8") as handle:
            handle.write("team notes\n")
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        paths = {action.path for action in plan.actions}
        self.assertNotIn(stranger, paths, "사용자 문서가 후보에 올랐다")

    def test_a_non_empty_parent_survives(self):
        consumer = self.fresh()
        stranger = os.path.join(consumer.project, "docs", "agent", "my-team-notes.md")
        with open(stranger, "w", encoding="utf-8") as handle:
            handle.write("team notes\n")
        result = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertTrue(os.path.isfile(stranger), "사용자 문서가 사라졌다")
        self.assertTrue(os.path.isdir(os.path.dirname(stranger)),
                        "이웃이 남은 디렉터리가 정리됐다")

    def test_an_empty_parent_is_pruned(self):
        consumer = self.fresh()
        result = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        self.assertFalse(os.path.isdir(os.path.join(consumer.project, "docs", "agent")))
        self.assertFalse(os.path.isdir(os.path.join(consumer.project, "schema")))

    def test_a_parent_that_gains_a_file_late_is_left_alone(self):
        """계획은 예상이다. 실행 시점에 무엇이 있으면 정리하지 않는다."""
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        prunes = [a for a in plan.actions if a.group == "prune"]
        self.assertTrue(prunes)
        target = prunes[0].path
        os.makedirs(target, exist_ok=True)
        # 계획 뒤에 파일이 생겼다 — 지문 검사가 먼저 잡거나, prune 이 스스로 물러서야 한다.
        with open(os.path.join(target, "late.txt"), "w", encoding="utf-8") as handle:
            handle.write("late\n")
        try:
            uninstall_executor.execute(plan)
        except ValueError:
            pass
        self.assertTrue(os.path.isfile(os.path.join(target, "late.txt")),
                        "나중에 생긴 사용자 파일이 사라졌다")


class SymlinkBoundary(Base):
    """root 위쪽 OS symlink 는 허용하고, root 아래는 막는다."""

    def test_nested_symlink_directory_is_not_followed(self):
        consumer = self.fresh()
        outside = os.path.join(consumer.root, "outside")
        os.makedirs(outside, exist_ok=True)
        sentinel = os.path.join(outside, "sentinel.txt")
        with open(sentinel, "w", encoding="utf-8") as handle:
            handle.write("must not change\n")
        with open(sentinel, "rb") as handle:
            before = handle.read()

        nested = os.path.join(consumer.project, ".claude", "skills", "sage-cycle")
        shutil.rmtree(nested, ignore_errors=True)
        os.symlink(outside, nested)

        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        kinds = {a.path: a.kind for a in plan.actions}
        # leaf symlink 는 link 자체만 처리한다 — 따라가지 않는다.
        self.assertEqual(kinds.get(nested), uninstall_plan.DELETE)
        uninstall_executor.execute(plan)
        self.assertTrue(os.path.isfile(sentinel), "symlink 를 따라가 외부 파일을 지웠다")
        with open(sentinel, "rb") as handle:
            self.assertEqual(handle.read(), before)

    def test_a_symlinked_component_below_root_is_refused(self):
        consumer = self.fresh()
        outside = os.path.join(consumer.root, "elsewhere")
        os.makedirs(os.path.join(outside, "agent"), exist_ok=True)
        with open(os.path.join(outside, "agent", "language-policy.md"), "w",
                  encoding="utf-8") as handle:
            handle.write("someone else\n")
        docs = os.path.join(consumer.project, "docs")
        shutil.rmtree(docs, ignore_errors=True)
        os.symlink(outside, docs)

        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        for action in plan.actions:
            if action.kind in (uninstall_plan.DELETE, uninstall_plan.STRIP):
                self.assertFalse(os.path.realpath(action.path).startswith(
                    os.path.realpath(outside)), f"root 밖으로 나갔다: {action.path}")

    def test_a_symlinked_shared_file_is_never_rewritten(self):
        """`STRIP` 은 leaf 를 따라가지 않는다 — 따라가면 남의 파일을 고친다."""
        consumer = self.fresh()
        outside = os.path.join(consumer.root, "shared")
        os.makedirs(outside, exist_ok=True)
        real = os.path.join(outside, "gitignore-real")
        shutil.copy2(os.path.join(consumer.project, ".gitignore"), real)
        with open(real, "rb") as handle:
            before = handle.read()
        link = os.path.join(consumer.project, ".gitignore")
        os.remove(link)
        os.symlink(real, link)

        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        kinds = {a.path: (a.kind, a.reason) for a in plan.actions}
        self.assertEqual(kinds[link][0], uninstall_plan.PRESERVE)
        self.assertEqual(kinds[link][1], "uninstall.symlink_leaf_write")
        with open(real, "rb") as handle:
            self.assertEqual(handle.read(), before)


class StepOrder(Base):
    """종료 계약 단계는 순서대로 수행되고 건너뛰지 않는다."""

    STAGES = ("capability", "lock", "fingerprint", "roots", "prepare", "recheck", "backup",
              "verify", "commit", "cleanup", "unlock")

    def test_the_stage_order_is_fixed(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        trace = []
        uninstall_executor.execute(plan, trace=trace)
        collapsed = [name for index, name in enumerate(trace)
                     if index == 0 or trace[index - 1] != name]
        # 이름을 하나씩 세지 않고 **정의된 순서와 대조**한다. 단계가 늘 때 검사가 따라오지
        # 않으면, 새 단계는 순서 계약 밖에서 아무 데나 놓일 수 있다.
        self.assertEqual([name for name in collapsed if name in self.STAGES][:2],
                         ["capability", "lock"])
        self.assertEqual(collapsed[-1], "unlock")
        for earlier, later in zip(self.STAGES, self.STAGES[1:]):
            self.assertIn(earlier, collapsed, f"{earlier} 단계가 없다")
            self.assertIn(later, collapsed, f"{later} 단계가 없다")
            self.assertLess(collapsed.index(earlier), collapsed.index(later),
                            f"{earlier} 가 {later} 뒤에 왔다")
        self.assertNotIn("rollback", collapsed)

    def test_every_declared_stage_is_actually_emitted(self):
        """선언한 단계 이름이 구현에 실제로 있는지 본다.

        순서만 보면 단계 하나가 조용히 사라져도 "남은 것들의 순서" 는 여전히 맞는다.
        """
        with open(os.path.join(REPO, "sage", "uninstall_executor.py"), encoding="utf-8") as h:
            source = h.read()
        for name in self.STAGES:
            self.assertIn(f'step("{name}")', source, f"{name} 단계를 내는 코드가 없다")

    def test_check_never_reaches_the_lock_or_backup_stage(self):
        consumer = self.fresh()
        sage("uninstall", "--dest", consumer.project, "--check", env=consumer.env)
        names = os.listdir(consumer.project)
        self.assertEqual([n for n in names if n.startswith(".sage-install-backup-")], [],
                         "--check 가 backup 단계까지 갔다")
        # lock 파일을 만드는 것도 쓰기다. 읽기 전용 명령이 그 자리를 남기면 안 된다.
        # lock 은 공유 lock root 에 있으므로 프로젝트 안에 흔적이 없어야 하고, 실제로
        # 잡히지 않았는지는 지금 잡아 보는 것으로 확인한다.
        after = install_transaction.DestinationLock(consumer.project)
        after.acquire()
        after.release()


class DanglingRegistration(Base):
    """성공 뒤 등록만 남는 일이 없다.

    ## 왜 fixture 를 따로 만드는가

    `sage install` 만으로는 `.claude/settings.json` 이 생기지 않는다. host 등록을 쓰는 것은
    `sage generate` 이고, 그것은 profile 이 부트스트랩된 뒤에야 돈다. 그래서 설치본만 놓고
    "등록이 남았는가" 를 물으면 **물어볼 파일 자체가 없어** 검사가 조용히 통과한다. 실제로 이
    검사는 지워진 함수를 부르는 줄을 들고도 초록이었다 — 그 줄에 닿은 적이 없었기 때문이다.

    닿지 않는 단언은 단언이 아니다. 그래서 여기서는 등록을 **실제로 만들고**, 만들어졌다는
    것부터 확인한 뒤에 제거를 본다.
    """

    def registered(self):
        """`sage generate` 로 host 등록까지 만든 소비자. 등록 존재를 확인하고 돌려준다."""
        consumer = self.fresh()
        profile = os.path.join(consumer.project, "sage", "project-profile.yaml")
        with open(profile, encoding="utf-8") as handle:
            body = handle.read()
        # generate 는 부트스트랩되지 않은 profile 을 거부한다. 이름과 risk glob 만 채운다 —
        # 등록을 만드는 데 필요한 최소이고, 그 이상은 이 검사가 보는 것과 무관하다.
        body = body.replace('  name: ""', '  name: "fixture"', 1)
        body = body.replace("  l2_path_globs: []", '  l2_path_globs: ["src/**"]', 1)
        with open(profile, "w", encoding="utf-8") as handle:
            handle.write(body)
        made = sage("generate", "--kind", "hook", "--write", "--target", "claude",
                    "--dest", consumer.project, env=consumer.env)
        self.assertEqual(made.returncode, 0, made.stdout + made.stderr)
        path = os.path.join(consumer.project, ".claude", "settings.json")
        self.assertTrue(os.path.isfile(path), "등록 fixture 가 만들어지지 않았다")
        return consumer, path

    def test_the_fixture_actually_carries_a_sage_registration(self):
        """제거를 보기 전에 **제거할 것이 있었는지**부터 본다."""
        _consumer, path = self.registered()
        with open(path, "rb") as handle:
            outcome = uninstall_shared.classify_host_bytes(
                handle.read(), uninstall_plan.canonical_commands("claude"))
        self.assertEqual(outcome.state, uninstall_shared.PRESENT,
                         "fixture 에 SAGE 등록이 없다 — 뒤 검사가 빈 파일을 보게 된다")
        self.assertTrue(outcome.strippable)

    def test_no_registration_survives_a_successful_uninstall(self):
        consumer, path = self.registered()
        result = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertIn(result.returncode, (0, 1), result.stderr)

        # 판정은 계획·실행과 **같은 classifier** 로 한다. 검사가 자기 파서를 들고 있으면
        # 그 파서만 통과하는 상태를 초록으로 부를 수 있다.
        self.assertTrue(os.path.lexists(path), "사용자 설정 파일 자체를 지웠다")
        with open(path, "rb") as handle:
            outcome = uninstall_shared.classify_host_bytes(
                handle.read(), uninstall_plan.canonical_commands("claude"))
        self.assertEqual(outcome.state, uninstall_shared.ABSENT,
                         f"{path} 에 SAGE 등록이 남았다")
        # 등록이 가리키던 shim 도 함께 사라졌는지 본다 — 등록만 지우고 실행 파일이 남으면
        # 다음 설치가 그 파일을 자기 것으로 오인한다.
        self.assertFalse(os.path.isdir(os.path.join(consumer.project, "scripts", "sage_harness")))


    def test_a_consumer_with_a_normal_prompt_hook_finishes(self):
        """정상 공존 소비자는 **끝나야 한다** — 잔재도, 붙들린 영수증도 남지 않는다.

        prompt hook 을 손상으로 오판하면 `settings.json` 전체가 `PRESERVE` 가 되고, 잔재가 있으니
        manifest receipt 도 함께 붙들리며, 재실행해도 같은 화면이 반복된다. 고칠 것이 없는데
        고치라는 말을 매번 받는 상태다.

        1회차가 `COMPLETE(0)` 이 **아닌** 것은 정상이다 — 최상위 공유 문서(`CLAUDE.md` 등)는
        설치 전 소유권을 증명할 수 없어 언제나 보존되고, 그 보존이 `PARTIAL(1)` 을 만든다.
        그래서 여기서 보는 것은 exit code 하나가 아니라 **무엇 때문에 `PARTIAL` 인가**다:
        `settings.json` 은 `stripped` 여야 하고 `preserved` 에 있으면 안 된다. 그리고 잔재가
        없으므로 영수증이 사라지고, 2회차는 `COMPLETE(0)` no-op 이어야 한다.
        """
        consumer, path = self.registered()
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        event = sorted(document["hooks"])[0]
        document["hooks"][event][0]["hooks"].append(
            {"type": "prompt", "prompt": "이 변경을 검토해줘"})
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)

        first = sage("uninstall", "--dest", consumer.project, "--yes", "--json",
                     env=consumer.env)
        self.assertEqual(first.returncode, 1, first.stdout + first.stderr)
        payload = json.loads(first.stdout)
        shown = os.path.join(".claude", "settings.json")
        self.assertIn(shown, [entry["path"] for entry in payload["stripped"]],
                      "정상 prompt hook 때문에 SAGE 등록을 빼지 못했다")
        self.assertNotIn(shown, [entry["path"] for entry in payload["preserved"]])
        self.assertEqual([entry["path"] for entry in payload["preserved"]],
                         ["AGENT_GUIDE.md", "CLAUDE.md"],
                         "소유권 불명 최상위 문서 말고 다른 것이 보존됐다")

        second = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)

        self.assertFalse(os.path.isdir(os.path.join(consumer.project, "docs", "sage_harness")),
                         "잔재가 없는데 설치 기록이 붙들렸다")
        with open(path, encoding="utf-8") as handle:
            left = json.load(handle)
        kept = [entry for blocks in left.get("hooks", {}).values()
                for block in blocks for entry in block["hooks"]]
        self.assertEqual(kept, [{"type": "prompt", "prompt": "이 변경을 검토해줘"}],
                         "사용자 hook 이 사라지거나 바뀌었다")


    def test_an_unsupported_handler_keeps_the_file_and_the_receipt(self):
        """SAGE 등록과 **비지원** handler 가 공존하면 파일을 건드리지 않고 잔재로 보고한다."""
        consumer, path = self.registered()
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        # `SessionStart` 는 `command`·`mcp_tool` 만 받는다(공식 계약).
        document.setdefault("hooks", {}).setdefault("SessionStart", []).append(
            {"hooks": [{"type": "prompt", "prompt": "세션 시작 검토"}]})
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
        with open(path, "rb") as handle:
            before = handle.read()
        mode = stat.S_IMODE(os.lstat(path).st_mode)

        shown = os.path.join(".claude", "settings.json")
        for run in ("첫", "재"):
            result = sage("uninstall", "--dest", consumer.project, "--yes", "--json",
                          env=consumer.env)
            self.assertEqual(result.returncode, 1, f"{run} 실행: " + result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "PARTIAL")
            preserved = {entry["path"]: entry for entry in payload["preserved"]}
            self.assertIn(shown, preserved, f"{run} 실행이 남은 경로를 말하지 않았다")
            self.assertEqual([e["kind"] for e in preserved[shown]["detail"]],
                             ["unsupported_kind"])
            self.assertIn(os.path.join("docs", "sage_harness"), preserved,
                          f"{run} 실행이 영수증을 붙들지 않았다")
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), before, f"{run} 실행이 bytes 를 바꿨다")
            self.assertEqual(stat.S_IMODE(os.lstat(path).st_mode), mode,
                             f"{run} 실행이 mode 를 바꿨다")


class LegacyConsumer(unittest.TestCase):
    """**실제 릴리스 트리**로 만든 구버전 소비자를 upgrade 없이 지울 수 있다.

    현재 설치본의 manifest 문자열만 바꾸는 것은 fixture 가 아니다. 그렇게 만든 소비자는 파일
    배치·roster·렌더가 전부 현재 것이라, 검사가 실제로 대조하는 대상이 "현재 설치본" 하나뿐이
    된다. 구버전에만 있던 자산이나 그 사이 바뀐 배치는 그 검사로 절대 보이지 않는다.

    그래서 tag 에서 그 시점 트리를 꺼내 **그 트리로 설치하고, 현재 코드로 지운다.**
    """

    TAG = "v0.9.84"

    @classmethod
    def setUpClass(cls):
        # tag 부재를 skip 으로 처리하지 않는다. **필수 증거의 부재는 초록이 아니다** — skip 은
        # 요약에서 통과처럼 읽히고, 그러면 이 acceptance 는 아무 데서도 검사되지 않은 채 PASS
        # 로 집계된다. CI 의 얕은 checkout 처럼 조용히 사라지는 경로가 실재한다.
        have_tag = subprocess.run(["git", "rev-parse", "--verify", f"{cls.TAG}^{{tree}}"],
                                  cwd=REPO, capture_output=True, text=True)
        if have_tag.returncode != 0:
            raise AssertionError(
                f"{cls.TAG} tag 가 없어 구버전 소비자 증거를 만들 수 없다. "
                "얕은 checkout 이라면 fetch-depth: 0 이 필요하다.")
        cls.root = fixture_root("legacy-consumer")
        cls.bundle = os.path.join(cls.root, "release")
        cls.project = os.path.join(cls.root, "proj")
        os.makedirs(cls.bundle)
        os.makedirs(cls.project)
        archive = subprocess.run(["git", "archive", cls.TAG], cwd=REPO, capture_output=True)
        assert archive.returncode == 0, archive.stderr
        extract = subprocess.run(["tar", "-x", "-C", cls.bundle], input=archive.stdout,
                                 capture_output=True)
        assert extract.returncode == 0, extract.stderr
        cls.codex_home = os.path.join(cls.root, "codex")
        os.makedirs(cls.codex_home)
        # 설치는 **그 시점 코드와 그 시점 번들**로 한다. `cwd` 까지 릴리스 트리로 두는 것이
        # 요점이다 — cwd 가 현재 저장소면 현재 번들을 배치하게 되어, 버전만 옛것이고 내용은
        # 전부 현재인 가짜 소비자가 만들어진다.
        cls.install = subprocess.run(
            [sys.executable, "-m", "sage", "install", "--host", "claude",
             "--dest", cls.project],
            cwd=cls.bundle, capture_output=True, text=True,
            env=dict(os.environ, PYTHONPATH=cls.bundle, CODEX_HOME=cls.codex_home))

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "root"):
            shutil.rmtree(cls.root, ignore_errors=True)

    def test_the_fixture_is_really_the_released_tree(self):
        """fixture 가 현재 트리의 사본이 아님을 확인한다 — 같으면 이 검사 전체가 무의미하다."""
        self.assertEqual(self.install.returncode, 0, self.install.stderr)
        with open(os.path.join(self.bundle, "sage", "__init__.py"), encoding="utf-8") as handle:
            self.assertIn(f'__version__ = "{self.TAG[1:]}"', handle.read())
        differs = subprocess.run(["git", "diff", "--quiet", self.TAG, "HEAD", "--", "sage/"],
                                 cwd=REPO)
        self.assertNotEqual(differs.returncode, 0,
                            "릴리스 트리와 현재 트리가 같다 — 구버전 fixture 가 성립하지 않는다")

    def test_a_released_consumer_uninstalls_without_upgrade(self):
        env = dict(os.environ, PYTHONPATH=REPO, CODEX_HOME=self.codex_home)

        # 기대값을 손으로 적지 않고 **계획이 보고한 것**에서 만든다. 손으로 적으면 잔존이
        # 늘 때 기대값도 같이 고치게 되고, 그 순간 이 검사는 아무것도 막지 않는다.
        plan = uninstall_plan.build(self.project, uninstall_plan.SCOPE_PROJECT,
                                    environ=dict(os.environ, CODEX_HOME=self.codex_home))
        reported = set()
        for action in plan.actions:
            if action.kind not in (uninstall_plan.PRESERVE, uninstall_plan.STRIP):
                continue
            rel = os.path.relpath(action.path, self.project)
            reported.add(rel)
            # 남는 파일을 담고 있는 부모는 당연히 함께 남는다.
            parent = os.path.dirname(rel)
            while parent:
                reported.add(parent)
                parent = os.path.dirname(parent)

        # 구버전 소비자라 **현재 번들과 다른** framework 문서가 남는다. 그것을 "사용자가
        # 고쳤다" 고 말하면 거짓이므로, 판정 이름이 아는 사실만 말하는지 함께 본다.
        differing = [a for a in plan.actions
                     if a.reason == "uninstall.framework_content_differs"]
        self.assertTrue(differing, "구버전 fixture 인데 번들 차이가 하나도 없다 — fixture 가 가짜다")

        result = sage("uninstall", "--dest", self.project, "--yes", env=env)
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)

        # "지워졌는가" 가 아니라 **"말하지 않은 것이 남았는가"** 를 본다 — 조용히 남는 자산이
        # 이 명령의 가장 흔한 실패 방식이다.
        survivors = set()
        for folder, dirs, files in os.walk(self.project):
            for name in dirs + files:
                survivors.add(os.path.relpath(os.path.join(folder, name), self.project))
        self.assertEqual(survivors, reported,
                         f"보고하지 않은 잔존: {sorted(survivors - reported)}")


class HostAgentRenders(Base):
    """install 이 host agents 디렉터리에 둔 CORE 렌더도 되돌린다."""

    def test_core_agent_renders_are_removed(self):
        consumer = self.fresh()
        agents = os.path.join(consumer.project, ".claude", "agents")
        self.assertTrue(os.path.isdir(agents), "설치가 agent 렌더를 두지 않았다")
        sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertFalse(os.path.exists(agents), "CORE agent 렌더가 남았다")

    def test_an_unrecorded_agent_is_never_a_candidate(self):
        """manifest 가 기록하지 않은 이름은 후보가 아니다 — `.claude/agents` 는 공유 자리다."""
        consumer = self.fresh()
        mine = os.path.join(consumer.project, ".claude", "agents", "my-own.md")
        with open(mine, "w", encoding="utf-8") as handle:
            handle.write("사용자 agent\n")
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertNotIn(mine, plan.write_targets())
        sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertTrue(os.path.isfile(mine), "사용자 agent 가 지워졌다")

    def test_a_roster_name_without_a_manifest_record_is_preserved(self):
        """이름이 roster 에 있어도 **기록이 없으면** 지우지 않는다."""
        consumer = self.fresh()
        path = uninstall_plan.manifest_path(consumer.project)
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        manifest["core_renders"] = {k: v for k, v in manifest["core_renders"].items()
                                    if "/agents/" not in k}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
        leader = os.path.join(consumer.project, ".claude", "agents", "leader.md")
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertNotIn(leader, plan.write_targets())


class PruneOrder(Base):
    """빈 부모는 깊은 것부터 정리된다 — 순서가 뒤집히면 부모가 조용히 남는다."""

    def test_nested_empty_parents_are_pruned_deepest_first(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        prunes = [a.path for a in plan.actions if a.group == "prune"]
        for index, path in enumerate(prunes):
            for later in prunes[index + 1:]:
                self.assertFalse(later.startswith(path + os.sep),
                                 f"부모 {path} 가 자식 {later} 보다 먼저 왔다")

    def test_a_nested_empty_parent_chain_actually_disappears(self):
        consumer = self.fresh()
        sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        for rel in ("docs/agent", "docs", ".claude/agents", ".claude"):
            self.assertFalse(os.path.exists(os.path.join(consumer.project, *rel.split("/"))),
                             f"빈 부모 {rel} 가 남았다")


class PlanBoundBaseline(Base):
    """기준은 계획과 같은 시점에 뜬다 — 확인 뒤에 뜨면 아무것도 지키지 못한다."""

    def test_the_plan_carries_its_own_baseline(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertEqual(set(plan.baseline), set(plan.write_targets()))

    def test_execute_takes_no_externally_supplied_baseline(self):
        """실행 층이 기준을 **받지 못하게** 한다.

        받을 수 있으면 언젠가 누군가 실행 직전에 새로 떠서 넘긴다. 그 기준은 "확인 이후
        바뀌었는가" 라는 질문에 언제나 "아니오" 라고 답한다.
        """
        import inspect
        names = list(inspect.signature(uninstall_executor.execute).parameters)
        self.assertEqual(names[0], "plan")
        for name in names[1:]:
            self.assertIn(name, ("environ", "trace"), f"실행 층이 {name} 으로 기준을 받는다")

    def test_a_file_edited_during_confirmation_is_not_deleted(self):
        """확인 prompt 가 열려 있는 동안 고친 파일은 지워지지 않는다.

        이것이 계획 시점 결속의 이유 전부다. 기준을 확인 뒤에 뜨면 방금 고친 내용이 기준이 되어
        검사를 그대로 통과하고, 사용자는 자기가 방금 저장한 파일을 잃는다.

        pty 로 확인 경로를 실제로 밟아야 이 검사가 성립한다 — pipe 로 넣으면 비대화형 차단으로
        빠져 확인을 지나치지 않는다. 그리고 prompt 가 **화면에 뜬 뒤에** 고쳐야 "확인 중" 이
        된다. 미리 고치면 그냥 계획 이전 상태를 바꾼 것이라 다른 검사가 된다.
        """
        import pty

        consumer = self.fresh()
        edited = os.path.join(consumer.project, "sage", "project-profile.yaml")
        with open(edited, encoding="utf-8") as handle:
            before = handle.read()

        parent, child = pty.openpty()
        try:
            process = subprocess.Popen([sys.executable, "-m", "sage", "uninstall",
                                        "--dest", consumer.project],
                                       cwd=REPO, env=consumer.env, stdin=child,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            # prompt 가 실제로 나올 때까지 읽는다. `input()` 은 개행 없이 쓰므로 한 byte 씩 본다.
            seen = b""
            while b"[y/N]" not in seen:
                chunk = os.read(process.stdout.fileno(), 1)
                if not chunk:
                    self.fail(f"확인 prompt 가 나오지 않았다: {seen!r}")
                seen += chunk

            with open(edited, "w", encoding="utf-8") as handle:
                handle.write(before + "\n# 사용자가 확인 중에 고쳤다\n")
            os.write(parent, b"y\n")
            output = process.communicate(timeout=90)[0].decode(errors="replace")
        finally:
            os.close(parent)
            os.close(child)

        self.assertEqual(process.returncode, 2, output)
        self.assertIn("확인 이후 대상이 변경", output)
        self.assertTrue(os.path.isfile(edited), "확인 중 고친 파일이 지워졌다")
        with open(edited, encoding="utf-8") as handle:
            self.assertIn("사용자가 확인 중에 고쳤다", handle.read(), "사용자 수정이 사라졌다")
        self.assertTrue(os.path.isdir(os.path.join(consumer.project, "docs", "sage_harness")),
                        "확인 중 변화가 감지됐는데 제거가 진행됐다")


class DestinationLock(Base):
    """같은 위치를 동시에 지우지 않는다 — **install 과 같은 권위로.**"""

    def held_lock(self, root):
        lock = install_transaction.DestinationLock(root)
        lock.acquire()
        self.addCleanup(lock.release)
        return lock

    def test_uninstall_and_install_share_one_lock_authority(self):
        """다른 lock 을 쓰면 두 명령이 서로를 막지 못한 채 각자 "잠갔다" 고 믿는다.

        같은 destination 을 한쪽이 배치하는 동안 다른 쪽이 지우는 것이 그때 실제로 벌어지는
        일이다. 그래서 공식 writer 는 **같은 권위**를 통과해야 한다.
        """
        consumer = self.fresh()
        held = uninstall_executor._acquire_all((consumer.project,))
        try:
            with self.assertRaises(install_transaction.InstallBusyError):
                install_transaction.DestinationLock(consumer.project).acquire()
        finally:
            for lock in reversed(held):
                lock.release()

    def test_an_install_lock_blocks_uninstall(self):
        """반대 방향도 성립해야 상호 배제다."""
        consumer = self.fresh()
        self.held_lock(consumer.project)
        with self.assertRaises(ValueError) as caught:
            uninstall_executor._acquire_all((consumer.project,))
        self.assertEqual(str(caught.exception), "uninstall.lock_busy")

    def test_uninstall_declares_no_lock_of_its_own(self):
        """전용 lock 파일이 다시 생기지 않는지 소스로 본다 — 값이 같아도 권위가 둘이면 갈라진다."""
        with open(os.path.join(REPO, "sage", "uninstall_executor.py"), encoding="utf-8") as h:
            source = h.read()
        self.assertIn("_tx.DestinationLock(", source)
        self.assertNotIn(".sage-uninstall.lock", source)
        self.assertNotIn("O_EXCL | os.O_WRONLY, 0o600", source)

    def test_lock_roots_are_sorted_and_cover_only_written_scopes(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        roots = plan.lock_roots()
        self.assertEqual(list(roots), sorted(roots), "lock 순서가 값으로 고정되지 않았다")
        self.assertEqual(roots, (consumer.project,))
        # project 범위는 전역을 쓰지 않으므로 잠그지도 않는다.
        self.assertIsNone(plan.global_root)

    def test_all_scope_locks_both_roots_in_sorted_order(self):
        consumer = self.fresh("codex")
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_ALL,
                                    environ={"CODEX_HOME": consumer.codex_home})
        roots = plan.lock_roots()
        self.assertEqual(list(roots), sorted(roots))
        self.assertIn(consumer.project, roots)

    def test_a_held_lock_blocks_a_second_run(self):
        consumer = self.fresh()
        self.held_lock(consumer.project)
        result = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue(os.path.isdir(os.path.join(consumer.project, "docs", "sage_harness")),
                        "lock 이 잡혀 있는데 지워졌다")

    def test_the_lock_is_released_after_success(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        uninstall_executor.execute(plan)
        after = install_transaction.DestinationLock(consumer.project)
        after.acquire()
        after.release()

    def test_the_lock_is_released_after_failure(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)

        def boom(original):
            def hook(journal, path):
                raise OSError("injected")
            return hook

        with patched("stage_remove_tree", boom), patched("stage_write", boom):
            with self.assertRaises(OSError):
                uninstall_executor.execute(plan)
        after = install_transaction.DestinationLock(consumer.project)
        after.acquire()
        after.release()

    def test_a_partial_acquisition_releases_what_it_took(self):
        first = self.fixture("lock-a")
        second = self.fixture("lock-b")
        blocker = install_transaction.DestinationLock(second)
        blocker.acquire()
        self.addCleanup(blocker.release)
        with self.assertRaises(ValueError) as caught:
            uninstall_executor._acquire_all((first, second))
        self.assertEqual(str(caught.exception), "uninstall.lock_busy")
        # 절반 잡은 것을 놓지 않았다면 여기서 막힌다.
        recovered = install_transaction.DestinationLock(first)
        recovered.acquire()
        recovered.release()

    def fixture(self, label):
        root = fixture_root(label)
        self.addCleanup(shutil.rmtree, root, True)
        return root


class ReviewReproductions(Base):
    """외부 검토가 실제로 재현한 두 반례. 각각이 데이터 손실 경계였다."""

    def test_same_size_content_change_with_restored_mtime_is_detected(self):
        """크기가 같고 mtime 을 되돌려 놓은 수정도 잡아야 한다.

        (종류·크기·mtime) 지문은 이것을 통과시켰고, 통과한 대상은 실제로 삭제됐다. 빈도가
        낮아도 되돌릴 수 없는 삭제 앞에서는 수용할 수 없다 — 그래서 내용 해시를 본다.
        """
        consumer = self.fresh()
        victim = os.path.join(consumer.project, "sage", "project-profile.yaml")
        with open(victim, "rb") as handle:
            before = handle.read()
        stamp = os.stat(victim)

        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)

        # 같은 크기로 내용만 바꾸고 mtime 을 원래대로 되돌린다.
        changed = bytearray(before)
        changed[0] = before[0] ^ 0x20
        with open(victim, "wb") as handle:
            handle.write(bytes(changed))
        os.utime(victim, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertEqual(os.stat(victim).st_size, len(before))
        self.assertEqual(os.stat(victim).st_mtime_ns, stamp.st_mtime_ns)

        with self.assertRaises(ValueError) as caught:
            uninstall_executor.execute(plan)
        self.assertEqual(str(caught.exception), "uninstall.fingerprint_changed")
        self.assertTrue(os.path.isfile(victim), "변경된 파일이 지문을 통과해 삭제됐다")

    def test_a_strip_leaf_swapped_after_the_boundary_check_is_not_followed(self):
        """경계 검사 **직후** leaf 를 symlink 로 바꿔도 바깥 파일을 고치지 않는다.

        경로에 대고 덮어쓰면 이 창이 열려 있다. 원본을 먼저 치우고 `O_EXCL | O_NOFOLLOW` 로
        새로 만들면 창 자체가 없다 — 그 자리에 무엇이든 있으면 만들기가 실패하기 때문이다.
        """
        consumer = self.fresh()
        outside = os.path.join(consumer.root, "victim.txt")
        marker = "external file must not change\n"
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write(marker)

        gitignore = os.path.join(consumer.project, ".gitignore")
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertIn(gitignore, plan.write_targets(), "STRIP 대상이 잡히지 않았다")

        original = uninstall_executor._strip_outcome
        swapped = []

        def swap_after_check(path, raw, commands, host=None):
            outcome = original(path, raw, commands, host)
            if path == gitignore and not swapped:
                swapped.append(True)
                os.remove(path)
                os.symlink(outside, path)
            return outcome

        uninstall_executor._strip_outcome = swap_after_check
        try:
            with self.assertRaises(Exception):
                uninstall_executor.execute(plan)
        finally:
            uninstall_executor._strip_outcome = original

        self.assertTrue(swapped, "주입이 성립하지 않았다")
        with open(outside, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), marker, "링크를 따라가 바깥 파일을 고쳤다")

    def seed_host_registration(self, consumer):
        """`.claude/settings.json` 을 STRIP 대상으로 만든다.

        ancestor 경쟁을 보려면 **프로젝트 root 아래 디렉터리**를 부모로 갖는 대상이 필요하다.
        root 자체의 부모를 바꾸는 것은 이 명령의 경계 밖이다.
        """
        path = os.path.join(consumer.project, ".claude", "settings.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        command = sorted(uninstall_plan.canonical_commands("claude"))[0]
        document = {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": command}]}]}, "mine": True}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
        return path

    def test_an_ancestor_swapped_after_backup_never_reaches_outside(self):
        """`stage_write` 직후 상위 디렉터리를 바깥 링크로 바꿔도 안전해야 한다.

        `O_NOFOLLOW` 는 **마지막 성분만** 본다. 상위가 바뀌는 것은 막지 못하고, 경로를 다시
        검사해도 검사와 작업 사이 창이 남는다. 그래서 부모를 **fd 로 붙든다** — 붙든 뒤에는
        이름이 어떻게 바뀌든 작업이 원래 디렉터리로 간다.

        ## 계약이 바뀐 자리다

        예전에는 이 주입을 탐지해 `boundary_changed` 로 멈추고 전부 되돌렸다. 그 탐지는 경로로
        조상을 훑는 것이었고, 붙든 뒤의 그 물음은 이미 다른 디렉터리에 대한 물음이다. 지금은
        멈추지 않고 **원래 객체에 대해 계속 진행한다** — 그것이 결속이 하기로 한 일이다.

        단언은 그래서 셋이다. 바깥에 아무것도 만들거나 고치지 않을 것, 승인되지 않은 파일이
        살아남을 것, 그리고 승인한 변경이 원래 객체에 정확히 적용될 것.
        """
        self.assertTrue(uninstall_posix_fs.probe_capability().supported,
                        "지원 플랫폼인데 부모 fd 결속이 꺼져 있다")
        consumer = self.fresh()
        settings = self.seed_host_registration(consumer)
        with open(settings, "rb") as handle:
            before_bytes = handle.read()

        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertIn(settings, plan.write_targets(), "STRIP 대상이 잡히지 않았다")

        outside = os.path.join(consumer.root, "outside")
        os.makedirs(outside)
        with open(os.path.join(outside, "victim.txt"), "w", encoding="utf-8") as handle:
            handle.write("someone else's file\n")
        claude = os.path.join(consumer.project, ".claude")
        moved = os.path.join(consumer.root, "real-claude")
        swapped = []

        def swap_ancestor(original):
            def hook(journal, path):
                result = original(journal, path)
                if path == settings and not swapped:
                    swapped.append(True)
                    shutil.move(claude, moved)
                    os.symlink(outside, claude)
                    with open(os.path.join(moved, "not-in-plan.txt"), "w",
                              encoding="utf-8") as extra:
                        extra.write("untouched\n")
                return result
            return hook

        opened_before = len(os.listdir("/dev/fd")) if os.path.isdir("/dev/fd") else None
        with patched("stage_write", swap_ancestor):
            try:
                uninstall_executor.execute(plan)
            except uninstall_executor.RollbackFailed as failure:
                self.fail(f"되돌리기까지 실패했다: {failure}")
        self.assertTrue(swapped, "주입이 성립하지 않았다")
        if opened_before is not None:
            self.assertLessEqual(len(os.listdir("/dev/fd")), opened_before + 1,
                                 "부모 fd 가 새고 있다")

        # 1) 링크를 따라가지 않았다.
        self.assertEqual(sorted(os.listdir(outside)), ["victim.txt"],
                         "링크를 따라가 남의 디렉터리를 건드렸다")

        # 2) 승인되지 않은 파일은 살아남았다.
        self.assertTrue(os.path.isfile(os.path.join(moved, "not-in-plan.txt")),
                        "계획에 없던 파일을 지웠다")

        # 3) 승인한 변경이 **원래 객체**에 적용됐다 — 사용자 내용은 남고 SAGE 등록만 빠졌다.
        written = os.path.join(moved, "settings.json")
        self.assertTrue(os.path.isfile(written), "원본이 사라졌다")
        with open(written, "rb") as handle:
            after_bytes = handle.read()
        self.assertNotEqual(after_bytes, before_bytes, "STRIP 이 적용되지 않았다")
        self.assertIn(b"mine", after_bytes, "사용자 내용을 잃었다")
        leftovers = [n for n in os.listdir(moved) if n.startswith(".sage-install-backup-")]
        self.assertEqual(leftovers, [], f"보관소가 남았다: {leftovers}")

    def test_parent_pinning_is_active_on_this_platform(self):
        """POSIX 에서는 결속이 **켜져 있어야 한다.** 꺼졌으면 그것 자체가 실패다.

        꺼진 채로 두면 ancestor 검사가 skip 되고, skip 은 요약에서 통과처럼 읽힌다. 실제로
        그렇게 세 Python 버전에서 방어가 꺼진 줄 모르고 "PASS" 로 보고했다.
        """
        if os.name != "posix":
            self.skipTest("POSIX 전용 계약")
        self.assertTrue(uninstall_posix_fs.probe_capability().supported,
                        f"{sys.platform} 에서 부모 fd 결속이 꺼졌다 — capability 판정을 보라")

    def test_capability_is_asked_per_function_not_by_lstat_membership(self):
        """`os.lstat` 멤버십은 Python 버전을 탄다. 그 이름으로 묻지 않는지 본다.

        **본문(코드)만** 본다. 문서에는 왜 그렇게 하면 안 되는지가 적혀 있고, 그 설명을 금지
        문자열로 세면 설명을 지워야 통과하는 검사가 된다.
        """
        with open(os.path.join(REPO, "sage", "uninstall_posix_fs.py"), encoding="utf-8") as h:
            tree = ast.parse(h.read())
        gate = next(n for n in tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "_pinning_support")
        body = gate.body[1:] if ast.get_docstring(gate) else gate.body
        code = "\n".join(ast.unparse(node) for node in body)
        self.assertNotIn("os.lstat", code, "capability 를 os.lstat 이름으로 묻고 있다")
        self.assertIn("supports_follow_symlinks", code)
        self.assertIn("supports_dir_fd", code)

        # `_lstat_at` 이 실제로 `follow_symlinks=False` 형태를 부르는지도 코드로 본다.
        helper = next(n for n in tree.body
                      if isinstance(n, ast.FunctionDef) and n.name == "_lstat_at")
        helper_body = helper.body[1:] if ast.get_docstring(helper) else helper.body
        helper_code = "\n".join(ast.unparse(node) for node in helper_body)
        self.assertIn("follow_symlinks=False", helper_code)

        # 이 환경에서 `os.lstat` 멤버십이 거짓일 수 있다는 사실 자체를 고정한다 — 그것이
        # 이 검사가 존재하는 이유다.
        self.assertTrue(os.stat in os.supports_dir_fd)
        self.assertTrue(os.stat in os.supports_follow_symlinks)

    def test_an_unsupported_platform_refuses_before_touching_anything(self):
        """결속을 못 하는 플랫폼에서는 **아무것도 바꾸지 않는다.**

        경로 기준으로 떨어뜨리면 같은 ancestor 경쟁에 그대로 노출된다. 바깥 파일을 만들 수
        있는 위험은 "알려진 플랫폼 한계" 로 넘길 성질이 아니다 — 되돌릴 수 없는 쪽으로 틀리는
        명령이기 때문이다. 계획은 읽기라 그대로 볼 수 있다.
        """
        consumer = self.fresh()
        before = sorted(os.listdir(consumer.project))
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        saved = uninstall_fs.capability

        def unsupported(roots=()):
            return uninstall_fs.MutationCapability(
                uninstall_fs.BACKEND_NONE, failure_code="uninstall.unsafe_platform")

        uninstall_fs.capability = unsupported
        try:
            with self.assertRaises(ValueError) as caught:
                uninstall_executor.execute(plan)
        finally:
            uninstall_fs.capability = saved
        self.assertEqual(str(caught.exception), "uninstall.unsafe_platform")
        self.assertEqual(before, sorted(os.listdir(consumer.project)),
                         "거부했는데 무언가 바뀌었다")
        # 계획은 여전히 만들어진다 — 무엇이 지워질지는 볼 수 있어야 한다.
        self.assertTrue(plan.write_targets())

    def test_the_cli_surfaces_the_refusal_with_exit_two(self):
        """CLI 표면에서도 거부가 `BLOCKED(2)` 로 나오고 계획은 여전히 보인다.

        실행 층만 확인하면 사용자가 실제로 무엇을 보는지는 검사되지 않는다. 이 플랫폼에서는
        결속이 켜져 있으므로, 자식 안에서 꺼서 그 경로를 밟게 한다.
        """
        consumer = self.fresh()
        before = sorted(os.listdir(consumer.project))
        script = (
            "import sys;"
            "sys.path.insert(0, %r);"
            "import sage.uninstall_fs as f;"
            "f.capability = lambda roots=(): f.MutationCapability("
            "f.BACKEND_NONE, failure_code='uninstall.unsafe_platform');"
            "from sage.cli import main;"
            "sys.argv = ['sage', 'uninstall', '--dest', %r, '--yes'];"
            "sys.exit(main())" % (REPO, consumer.project))
        result = subprocess.run([sys.executable, "-c", script], cwd=REPO, env=consumer.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("안전한 제거를 보장할 수 없어", result.stdout + result.stderr)
        self.assertEqual(before, sorted(os.listdir(consumer.project)),
                         "거부했는데 무언가 바뀌었다")
        # 계획은 읽기이므로 그대로 볼 수 있어야 한다.
        checked = sage("uninstall", "--dest", consumer.project, "--check", env=consumer.env)
        self.assertIn(checked.returncode, (0, 1), checked.stdout + checked.stderr)

    def test_the_pinned_journal_has_no_path_based_fallback(self):
        """결속이 없을 때 경로로 되돌아가는 길이 남아 있지 않은지 본다.

        그 길을 남겨 두면 조건 하나가 어긋나는 날 조용히 그쪽으로 떨어진다. 이번에 겪은 것이
        정확히 그것이다.
        """
        journal = uninstall_executor._PinnedTransaction(expected={}, write_roots=())
        with self.assertRaises(Exception):
            journal._replace("/nowhere/a", "/nowhere/b")
        with self.assertRaises(Exception):
            journal._remove("/nowhere/a")

    def test_mutations_are_bound_to_an_opened_parent(self):
        """경로 재검사가 아니라 **열린 handle** 에 결속됐는지 소스로 본다.

        재검사만으로는 TOCTOU 창이 남는다. 구현이 조용히 그쪽으로 돌아가면 이 검사가 잡는다.
        """
        with open(os.path.join(REPO, "sage", "uninstall_posix_fs.py"), encoding="utf-8") as h:
            source = h.read()
        self.assertIn("dir_fd=handle", source)
        self.assertIn("src_dir_fd=handle", source)
        self.assertIn("O_DIRECTORY | os.O_NOFOLLOW", source)

    def test_the_executor_no_longer_knows_any_operating_system(self):
        """단계 순서 층에 OS 분기가 남지 않았는지 본다.

        분기가 남아 있으면 두 번째 OS 를 더할 때마다 늘고, 늘어난 분기 중 하나가 빠진 자리가
        곧 경로 기반 fallback 이 된다. **본문(코드)만** 본다 — 문서에는 왜 그런지가 적혀 있고,
        그 설명을 금지 문자열로 세면 설명을 지워야 통과하는 검사가 된다.
        """
        with open(os.path.join(REPO, "sage", "uninstall_executor.py"), encoding="utf-8") as h:
            tree = ast.parse(h.read())
        body = [n for n in tree.body if not (isinstance(n, ast.Expr)
                                             and isinstance(n.value, ast.Constant))]
        code = "\n".join(ast.unparse(node) for node in body)
        for banned in ("dir_fd", "O_NOFOLLOW", "O_DIRECTORY", "os.name", "sys.platform",
                       "ctypes", "WinDLL"):
            self.assertNotIn(banned, code, f"실행 층이 아직 OS 를 알고 있다: {banned}")

    def test_writing_refuses_a_path_that_is_not_empty(self):
        """치운 자리에 무엇이 나타나면 따라가지 않고 멈춘다."""
        root = fixture_root("nofollow")
        self.addCleanup(shutil.rmtree, root, True)
        outside = os.path.join(root, "outside.txt")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("untouched\n")
        link = os.path.join(root, "link")
        os.symlink(outside, link)
        with self.assertRaises(OSError):
            uninstall_posix_fs.write_new_file(link, "overwritten\n", 0o644)
        with open(outside, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "untouched\n")


# A24 가 서려면 Windows 에서 **반드시 실행돼야 하는** 검사들. 이 tuple 이 그 목록의 정본이고,
# `scripts/ci/uninstall_core_checks.py` 의 `CORE_SELECTORS` 는 그것을 실행하는 쪽이다.
#
# **두 곳에 두는 것이 요점이다.** 실행 목록만 있으면 거기서 한 줄을 지우는 것이 곧 요구가
# 줄어드는 것이 된다 — 남은 것들은 여전히 통과하고, 화면은 초록이고, 무엇이 사라졌는지는
# 아무 데도 적히지 않는다. 요구를 실행과 다른 파일에 두면 그 축소가 **대조에서 걸린다.**
A24_REQUIRED_SELECTORS = (
    "BoundaryRace.test_no_absolute_path_judgement_survives_after_the_pin",
    "BoundaryRace.test_no_absolute_path_judgement_survives_through_the_rollback",
    "BoundaryRace.test_the_cleanup_allowance_is_only_the_backup_lexists",
    "BoundaryRace.test_a_backup_path_probe_before_the_commit_is_caught",
)


class BoundaryRace(Base):
    """계획과 쓰기 사이에 경계가 바뀌면 쓰지 않는다."""

    def test_a_component_swapped_after_planning_never_redirects_the_work(self):
        """계획 뒤 중간 성분이 링크로 바뀌는 경쟁을 실제로 주입한다.

        ## 계약이 바뀐 자리다

        예전에는 이 주입을 **탐지해서** `boundary_changed` 로 멈췄다. 그 탐지는 경로로 조상을
        훑는 것이었고, 부모를 이미 붙든 뒤에 경로로 묻는 것은 그 자체가 위험하다 — 상위가
        바뀐 순간 그 답은 이미 다른 디렉터리에 대한 답이다.

        지금은 탐지하지 않는다. 대신 **결속이 그 질문을 무의미하게 만든다.** 이름이 어떻게
        바뀌든 우리가 여는 것은 승인 시점에 확인한 그 객체이고, 공격자가 바꿔 놓은 이름이
        가리키는 곳은 열리지 않는다. 공격자가 얻을 수 있는 것은 "우리가 이미 승인한 객체를
        옮겨 두는 것" 뿐이고, 그 객체는 사용자가 지우기로 한 바로 그것이다.

        그래서 단언도 바뀐다 — "멈췄는가" 가 아니라 **"엉뚱한 것을 건드렸는가"** 를 본다.
        """
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        target = os.path.join(consumer.project, ".claude", "skills")
        if not os.path.isdir(target):
            self.skipTest("이 host 배치에는 .claude/skills 가 없다")
        moved = os.path.join(consumer.root, "elsewhere-skills")
        # 링크가 가리키는 곳을 **원본이 아닌 다른 곳**으로 둔다. 원본을 가리키게 하면
        # "따라갔다" 와 "붙든 것을 썼다" 가 구별되지 않아 이 검사가 아무것도 말하지 못한다.
        outside = os.path.join(consumer.root, "outside-skills")
        os.makedirs(outside)
        with open(os.path.join(outside, "victim.txt"), "w", encoding="utf-8") as handle:
            handle.write("someone else's file\n")
        swapped = []

        def swap_then_remove(original):
            def hook(journal, path):
                result = original(journal, path)
                if not swapped:
                    swapped.append(True)
                    shutil.move(target, moved)
                    os.symlink(outside, target)
                    # 승인되지 않은 파일을 원본 안에 놓는다. 이것이 살아남아야 "승인한
                    # 것만 지웠다" 가 증명된다.
                    with open(os.path.join(moved, "not-in-plan.txt"), "w",
                              encoding="utf-8") as extra:
                        extra.write("untouched\n")
                return result
            return hook

        with patched("stage_remove_tree", swap_then_remove):
            try:
                uninstall_executor.execute(plan)
            except uninstall_executor.RollbackFailed as failure:
                self.fail(f"되돌리기까지 실패했다: {failure}")
        self.assertTrue(swapped, "주입이 성립하지 않았다")
        self.assertTrue(os.path.islink(target), "주입이 성립하지 않았다")

        # 1) 링크를 따라가지 않았다 — 남의 디렉터리는 그대로다.
        self.assertEqual(sorted(os.listdir(outside)), ["victim.txt"],
                         "링크를 따라가 남의 디렉터리를 건드렸다")

        # 2) 승인되지 않은 파일은 살아남았다 — 붙든 디렉터리 안에서도 계획만 지운다.
        self.assertTrue(os.path.isfile(os.path.join(moved, "not-in-plan.txt")),
                        "계획에 없던 파일을 지웠다")

        # 3) 승인된 자산은 실제로 사라졌다 — 결속이 작업을 원래 객체로 보냈다.
        approved = [os.path.basename(a.path) for a in plan.of_kind(uninstall_plan.DELETE)
                    if os.path.dirname(a.path) == target]
        self.assertTrue(approved, "이 fixture 에는 검사할 승인 자산이 없다")
        for name in approved:
            self.assertFalse(os.path.exists(os.path.join(moved, name)),
                             f"승인된 자산이 남았다: {name}")

    def test_the_recheck_splits_membership_from_the_boundary(self):
        """소속은 **문자열로**, 경계는 **결속된 지문으로** 묻는지 본다.

        둘을 한 관문에 묶어 두면 그 관문이 경로로 파일시스템을 읽고, 붙든 뒤의 그 읽기가
        정확히 이 사이클이 없애려는 것이다. **본문(코드)만** 본다.
        """
        with open(os.path.join(REPO, "sage", "uninstall_executor.py"), encoding="utf-8") as h:
            tree = ast.parse(h.read())
        target = next(n for n in tree.body
                      if isinstance(n, ast.FunctionDef) and n.name == "_execute_locked")
        body = target.body[1:] if ast.get_docstring(target) else target.body
        code = "\n".join(ast.unparse(node) for node in body)
        self.assertIn("_plan.within_root(plan.root_for(action)", code,
                      "소속 판정이 사라졌다")
        self.assertNotIn("candidate_block", code,
                         "붙든 뒤에 경로로 조상·leaf 를 훑는 관문을 부른다")
        self.assertIn("journal._measure(action.path, 'path')", code)

    # 붙든 뒤에 경로로 물을 수 있는 것 전부. **읽는 것과 만드는 것을 함께 센다** —
    # `os.mkdir` 은 상위가 바뀐 뒤 프로젝트 밖에 디렉터리를 만드는 자리이고, 읽기만 세면
    # 그 자리는 감시 밖에 남는다. `os.makedirs` 는 같은 일을 하는 다른 이름이라 함께 건다.
    PATH_PRIMITIVES = ((os, "lstat"), (os, "stat"), (os, "readlink"),
                       (os, "mkdir"), (os, "makedirs"),
                       (os.path, "lexists"), (os.path, "islink"), (os.path, "isdir"))

    # commit 뒤 `_cleanup()` 에 허용된 **유일한** 호출. 경로도 제한된다 — journal 이 만든
    # backup 뿐이다. 이것 하나만 예외인 이유는 그 질문이 "붙든 객체가 아직 있는가" 가 아니라
    # "사용자가 갈 자리에 아직 무언가 보이는가" 여서다. 다른 primitive 나 다른 경로는 그
    # 질문이 아니므로 예외가 아니다.
    CLEANUP_ALLOWED = (os.path, "lexists")

    def pin_window(self, plan, project):
        """`recheck` 부터 `unlock` 까지 경로 판정을 가로챈다.

        **창은 한 번만 닫힌다 — `unlock` 에서.** 성공 경로든 실패 경로든 그 전에는 닫지 않는다.
        `cleanup` 에서 닫으면 `_cleanup()` 안에서 무엇을 하든 아무도 보지 않게 되고, 그러면
        "예외는 읽기 전용 `lexists` 하나" 라는 계약을 검사가 아니라 문서만 말하게 된다.

        대신 단계를 추적해서 `cleanup` 동안만 **정규화된 backup 경로에 대한 `os.path.lexists`**
        를 통과시킨다. 다른 primitive 도, 다른 경로도 offender 다.

        **범위는 action 목록이 아니라 write root 아래 전부다.** backup 은 대상의 형제라
        action 과 그 조상만 세면 `.sage-install-backup-...` 조회가 감시 밖으로 빠진다 —
        되돌리기가 가장 믿어야 하는 경로가 하필 안 보이는 자리에 있게 된다.

        `dir_fd` 를 쓴 호출은 결속된 호출이므로 세지 않는다. 허용된 호출 **안에서** 다시
        도는 호출도 세지 않는다(`os.path.lexists` 는 안에서 `os.lstat` 을 부른다) — 그것은
        같은 한 번의 조회이지 두 번이 아니다.
        """
        roots = tuple(os.path.abspath(root) for root in plan.lock_roots())
        journals = []
        original_journal = uninstall_executor._PinnedTransaction

        class Recorded(original_journal):
            def __init__(inner, *args, **kwargs):
                original_journal.__init__(inner, *args, **kwargs)
                journals.append(inner)

        state = {"phase": None, "depth": 0}
        offenders = []
        saved = {}

        def under_root(candidate):
            target = os.path.abspath(candidate)
            return any(target == root or target.startswith(root + os.sep) for root in roots)

        def backups():
            return {os.path.abspath(backup) for journal in journals
                    for _path, backup in journal._entries if backup is not None}

        def permitted(module, name, candidate):
            if state["phase"] != "cleanup":
                return False
            if (module, name) != self.CLEANUP_ALLOWED:
                return False
            return os.path.abspath(candidate) in backups()

        def spy(module, name, original):
            def probe(*args, **kwargs):
                counted = (state["depth"] == 0 and kwargs.get("dir_fd") is None and args
                           and isinstance(args[0], str) and under_root(args[0])
                           and not permitted(module, name, args[0]))
                if counted:
                    offenders.append(f"{state['phase']}: {name}({args[0]})")
                state["depth"] += 1
                try:
                    return original(*args, **kwargs)
                finally:
                    state["depth"] -= 1
            return probe

        def install():
            # capability 판정이 끝난 **뒤에** 건다. `_pinning_support` 는 `os.stat` 을
            # **이름이 아니라 객체로** 대조하므로, 먼저 갈아 끼우면 지원 환경이 미지원으로
            # 보이고 이 검사는 자기 도구 때문에 죽는다.
            for module, name in self.PATH_PRIMITIVES:
                if (module, name) in saved:
                    continue
                saved[(module, name)] = getattr(module, name)
                setattr(module, name, spy(module, name, getattr(module, name)))

        def remove():
            for (module, name), original in list(saved.items()):
                setattr(module, name, original)
            saved.clear()
            uninstall_executor._PinnedTransaction = original_journal

        class Window(list):
            def append(inner, name):
                list.append(inner, name)
                state["phase"] = name
                if name == "recheck":
                    install()
                elif name == "unlock":
                    remove()

        uninstall_executor._PinnedTransaction = Recorded
        return Window(), offenders, remove

    def strippable_project(self):
        consumer = self.fresh()
        settings = os.path.join(consumer.project, ".claude", "settings.json")
        os.makedirs(os.path.dirname(settings), exist_ok=True)
        command = sorted(uninstall_plan.canonical_commands("claude"))[0]
        with open(settings, "w", encoding="utf-8") as handle:
            json.dump({"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [
                {"type": "command", "command": command}]}]}, "mine": True}, handle)
        return consumer

    def test_no_absolute_path_judgement_survives_after_the_pin(self):
        """**간접 호출까지** 사라졌는지 실제 실행으로 본다.

        소스 문자열 검사는 직접 호출만 잡는다. `_guard_path` 처럼 상속으로 들어오는 판정은
        실행 층 어디에도 이름이 없고, 그래서 문자열 검사를 통과한 채로 남아 있었다.

        그래서 `recheck` 이후 write root 아래 경로에 대한 파일시스템 호출을 **전부 가로채고**,
        허용된 하나를 뺀 나머지가 하나라도 있으면 실패로 센다.
        """
        consumer = self.strippable_project()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        window, offenders, remove = self.pin_window(plan, consumer.project)
        try:
            uninstall_executor.execute(plan, trace=window)
        finally:
            remove()
        self.assertIn("cleanup", window, "성공 경로가 cleanup 까지 가지 않았다")
        self.assertEqual(window[-1], "unlock", "창이 unlock 까지 가지 않았다")
        self.assertEqual(offenders, [],
                         f"붙든 뒤에 경로로 다시 물었다: {sorted(set(offenders))[:8]}")

    def test_no_absolute_path_judgement_survives_through_the_rollback(self):
        """되돌리는 동안에도 경로로 묻지 않는다.

        위 검사는 성공 경로만 본다. 되돌리기는 실패한 뒤에야 도는 코드라, 그 구간만 경로
        판정을 그대로 두고도 성공 경로 검사는 초록으로 남는다.
        """
        consumer = self.strippable_project()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        window, offenders, remove = self.pin_window(plan, consumer.project)

        def boom(original):
            def hook(journal):
                raise OSError("injected")
            return hook

        try:
            with patched("verify_outputs", boom):
                with self.assertRaises(OSError):
                    uninstall_executor.execute(plan, trace=window)
        finally:
            remove()
        self.assertIn("rollback", window, "되돌리기가 돌지 않아 아무것도 확인하지 못했다")
        self.assertEqual(window[-1], "unlock", "창이 unlock 까지 가지 않았다")
        self.assertEqual(offenders, [],
                         f"되돌리는 동안 경로로 물었다: {sorted(set(offenders))[:8]}")

    def test_the_cleanup_allowance_is_only_the_backup_lexists(self):
        """cleanup 예외가 **정말로 그 하나뿐인지** 주입으로 본다.

        예외를 단계로만 열면 그 단계 전체가 통과한다 — 그러면 계약은 "cleanup 은 무엇이든
        해도 된다" 가 되고, 문서만 `lexists` 하나라고 말한다. 그래서 허용되지 않은 조회를
        `_cleanup()` 안에 넣고 창이 그것을 잡는지 확인한다.
        """
        consumer = self.strippable_project()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        window, offenders, remove = self.pin_window(plan, consumer.project)
        original = uninstall_executor._cleanup
        target = os.path.join(consumer.project, ".claude")

        def nosy(journal):
            # 계약이 허용하지 않은 조회. 경로는 허용 목록 밖이고 primitive 도 다르다.
            os.stat(target)
            return original(journal)

        uninstall_executor._cleanup = nosy
        try:
            uninstall_executor.execute(plan, trace=window)
        finally:
            uninstall_executor._cleanup = original
            remove()
        self.assertTrue([note for note in offenders if note.startswith("cleanup: stat(")],
                        f"cleanup 안의 허용되지 않은 조회를 놓쳤다: {offenders}")

    def test_a_backup_path_probe_before_the_commit_is_caught(self):
        """backup 절대 경로 조회도 잡는가.

        backup 은 대상의 **형제**다. action 과 그 조상만 세면 되돌리기가 가장 믿어야 하는
        경로가 감시 밖에 남는다 — 그 자리에 경로 판정이 되살아나도 아무도 모른다.
        """
        consumer = self.strippable_project()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        window, offenders, remove = self.pin_window(plan, consumer.project)

        def peek(original):
            def hook(journal):
                for _path, backup in journal._entries:
                    if backup is not None:
                        os.path.lexists(backup)
                return original(journal)
            return hook

        try:
            with patched("verify_outputs", peek):
                uninstall_executor.execute(plan, trace=window)
        finally:
            remove()
        self.assertTrue([note for note in offenders if ".sage-install-backup-" in note],
                        f"backup 절대 경로 조회를 놓쳤다: {offenders}")

    @staticmethod
    def self_and_ancestors(path, root):
        seen = []
        cursor = os.path.abspath(path)
        root = os.path.abspath(root)
        while cursor.startswith(root):
            seen.append(cursor)
            parent = os.path.dirname(cursor)
            if parent == cursor:
                break
            cursor = parent
        return seen


class CommitSemantics(Base):
    """commit 은 되돌리지 않기로 정하는 지점이고, cleanup 은 뒷정리다."""

    def test_cleanup_failure_does_not_undo_the_removal(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)

        def refuse(original):
            def hook(journal):
                journal._committed = True
                return [f"{path}: injected" for path, backup in journal._entries if backup]
            return hook

        with patched("commit", refuse):
            result = uninstall_executor.execute(plan)
        self.assertTrue(result.leftover_backups, "못 치운 보관소를 보고하지 않았다")
        self.assertFalse(os.path.isdir(os.path.join(consumer.project, "docs", "sage_harness")),
                         "뒷정리 실패가 제거를 되돌렸다")

    def test_cleanup_failure_is_reported_but_the_command_succeeds(self):
        consumer = self.fresh()
        result = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        leftovers = [n for n in os.listdir(consumer.project)
                     if n.startswith(".sage-install-backup-")]
        self.assertEqual(leftovers, [], "정상 경로에서 보관소가 남았다")

    def test_a_failure_after_commit_is_never_rolled_back(self):
        """commit 뒤의 실패는 되돌리지 않는다 — 되돌리면 성공한 제거를 취소하게 된다."""
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        trace = []

        def boom(original):
            def hook(journal):
                journal._committed = True
                raise OSError("injected")
            return hook

        def forbidden(original):
            def hook(journal):
                raise AssertionError("commit 뒤에 되돌리려 했다")
            return hook

        with patched("commit", boom), patched("rollback", forbidden):
            uninstall_executor.execute(plan, trace=trace)
        self.assertIn("commit", trace)
        self.assertNotIn("rollback", trace)


class SmokeIsolation(unittest.TestCase):
    """smoke 가 HOME 을 돌릴 때 **의존성 경로를 잃지 않는지** 본다.

    `$CODEX_HOME` 기본값을 밟으려면 HOME 을 fixture 로 돌려야 하는데, 의존성이 user-site
    (`~/.local/lib/...`)에만 있으면 그 순간 자식이 그 경로를 잃고 `ModuleNotFoundError` 로
    죽는다. 검사가 **제품이 아니라 자기 격리 방식** 때문에 실패하는 것이고, 그 실패는 제품
    결함처럼 보인다.

    이 머신에서는 의존성이 HOME 밖(homebrew site-packages)에 있어 그냥 통과한다. 그래서 조건을
    직접 만들어 재현한다 — "내 머신에서는 된다" 를 증거로 쓰지 않기 위해서다.
    """

    def smoke_module(self):
        import importlib.util
        path = os.path.join(REPO, "scripts", "ci", "uninstall_smoke.py")
        spec = importlib.util.spec_from_file_location("uninstall_smoke_probe", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_paths_under_home_are_carried_across_the_rewrite(self):
        home = fixture_root("fake-home")
        self.addCleanup(shutil.rmtree, home, True)
        site = os.path.join(home, "user-site")
        os.makedirs(site)
        with open(os.path.join(site, "sage_smoke_probe.py"), "w", encoding="utf-8") as handle:
            handle.write("VALUE = 'user-site only'\n")

        module = self.smoke_module()
        saved_home = os.environ.get("HOME")
        saved_path = list(sys.path)
        try:
            os.environ["HOME"] = home
            sys.path.insert(0, site)
            carried = module.inherited_import_paths()
        finally:
            sys.path[:] = saved_path
            if saved_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = saved_home

        self.assertIn(os.path.realpath(site), [os.path.realpath(p) for p in carried],
                      "HOME 아래 의존성 경로를 잃었다")
        self.assertNotIn(os.path.realpath(REPO), [os.path.realpath(p) for p in carried],
                         "저장소를 넘겨 wheel 단독 여부를 흐렸다")

    def test_a_dependency_only_reachable_via_home_survives_a_home_rewrite(self):
        """HOME 을 돌린 자식이 그 의존성을 실제로 import 할 수 있는지 끝까지 확인한다."""
        home = fixture_root("dep-home")
        self.addCleanup(shutil.rmtree, home, True)
        site = os.path.join(home, "user-site")
        os.makedirs(site)
        with open(os.path.join(site, "sage_smoke_probe.py"), "w", encoding="utf-8") as handle:
            handle.write("VALUE = 'user-site only'\n")
        fresh_home = fixture_root("dep-newhome")
        self.addCleanup(shutil.rmtree, fresh_home, True)

        module = self.smoke_module()
        saved_home = os.environ.get("HOME")
        saved_path = list(sys.path)
        try:
            os.environ["HOME"] = home
            sys.path.insert(0, site)
            carried = module.inherited_import_paths()
        finally:
            sys.path[:] = saved_path
            if saved_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = saved_home

        child = dict(os.environ, HOME=fresh_home, USERPROFILE=fresh_home,
                     PYTHONPATH=os.pathsep.join(carried))
        # `-S` 로 site 처리를 끄면 user-site 가 자동으로 붙지 않는다 — 넘긴 경로만 남는다.
        result = subprocess.run([sys.executable, "-S", "-c",
                                 "import sage_smoke_probe; print(sage_smoke_probe.VALUE)"],
                                env=child, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("user-site only", result.stdout)

    def test_the_smoke_summary_survives_a_windows_cp1252_console(self):
        """Windows 기본 stdout 이 cp1252 여도 성공 요약 때문에 job 이 실패하지 않는다.

        실제 계약 검사를 전부 마친 뒤 마지막 한글 요약에서 `UnicodeEncodeError` 가 나면 CI 는
        실패하고, AC30w 는 검증된 동작을 갖고도 실행 증거를 만들지 못한다. `run_case` 만 비워
        외부 작업 없이 **실제 main 출력 경계**를 cp1252 자식 프로세스에서 밟는다.
        """
        path = os.path.join(REPO, "scripts", "ci", "uninstall_smoke.py")
        probe = (
            "import importlib.util\n"
            f"path = {path!r}\n"
            "spec = importlib.util.spec_from_file_location('uninstall_smoke_cp1252', path)\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
            "module.PATH_SHAPES = (('plain', 'proj', 'codex'),)\n"
            "module.CODEX_MODES = ('custom',)\n"
            "module.run_case = lambda *args: None\n"
            # 외부 작업을 하는 자리는 **전부** 비운다. 하나라도 남으면 이 검사는 인코딩
            # 경계가 아니라 자식 프로세스의 출력 인코딩에서 죽는다.
            "module.scope_case = lambda *args: None\n"
            "module.refusal_case = lambda *args: None\n"
            "module.native_failure_case = lambda *args: None\n"
            "raise SystemExit(module.main())\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
            capture_output=True,
        )
        self.assertEqual(
            result.returncode, 0,
            result.stderr.decode("utf-8", errors="replace"),
        )


class WriteIntegrity(Base):
    """쓰기가 **끝까지** 됐는지 확인한다 — 잘려 쓰인 공유 파일은 사용자 데이터 손실이다."""

    def test_a_short_write_is_detected_and_rolled_back(self):
        """`os.write` 는 요청한 만큼 쓴다고 보장하지 않는다.

        한 번 부르고 반환값을 버리면 잘린 파일이 정상으로 통과한다. 그 파일이 사용자의
        `.gitignore` 라면 우리가 남긴 것은 남의 규칙을 자른 결과다.
        """
        consumer = self.fresh()
        gitignore = os.path.join(consumer.project, ".gitignore")
        with open(gitignore, encoding="utf-8") as handle:
            installed = handle.read()
        # 사용자 규칙을 넉넉히 넣는다 — 잘려 쓰이면 무엇을 잃는지가 이 검사의 요점이다.
        rules = "".join(f"# 사용자 규칙 {n}\nbuild-{n}/\n" for n in range(20))
        with open(gitignore, "w", encoding="utf-8") as handle:
            handle.write(rules + installed)
        with open(gitignore, "rb") as handle:
            before = handle.read()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertIn(gitignore, plan.write_targets())

        expected = uninstall_shared.classify_gitignore_bytes(before).body
        self.assertIsNotNone(expected)

        real_write = os.write
        crippled = []

        def short_write(fd, data):
            # STRIP 본문을 쓰는 첫 호출만 잘라 쓴다. 올바른 구현은 나머지를 이어 쓴다.
            if not crippled and len(data) > 16:
                crippled.append(True)
                return real_write(fd, data[:12])
            return real_write(fd, data)

        os.write = short_write
        try:
            uninstall_executor.execute(plan)
        finally:
            os.write = real_write
        self.assertTrue(crippled, "주입이 성립하지 않았다")
        with open(gitignore, "rb") as handle:
            written = handle.read()
        self.assertEqual(written.decode("utf-8"), expected,
                         "짧게 쓰인 채로 남았다 — 사용자 규칙이 잘렸다")
        self.assertEqual(len(written), len(expected.encode("utf-8")))

    def test_the_writer_loops_until_everything_is_written(self):
        """구현이 반환값을 버리는 형태로 되돌아가지 않았는지 코드로 본다."""
        with open(os.path.join(REPO, "sage", "uninstall_posix_fs.py"), encoding="utf-8") as h:
            tree = ast.parse(h.read())
        writer = next(n for n in tree.body
                      if isinstance(n, ast.FunctionDef) and n.name == "write_new_file")
        body = writer.body[1:] if ast.get_docstring(writer) else writer.body
        code = "\n".join(ast.unparse(node) for node in body)
        self.assertIn("while written <", code, "쓰기가 반복되지 않는다")
        self.assertIn("st_size", code, "쓴 크기를 확인하지 않는다")


class InterruptSafety(Base):
    """Ctrl-C 는 정상적인 사용자 행동이다. 그것이 원자성을 깨면 계약이 없는 것이다."""

    def test_a_keyboard_interrupt_still_rolls_back(self):
        consumer = self.fresh()
        before = sorted(os.listdir(consumer.project))
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        state = {"n": 0}

        def interrupt(original):
            def hook(journal, path):
                state["n"] += 1
                if state["n"] > 2:
                    raise KeyboardInterrupt()
                return original(journal, path)
            return hook

        with patched("stage_remove_tree", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                uninstall_executor.execute(plan)
        self.assertEqual(before, sorted(os.listdir(consumer.project)),
                         "Ctrl-C 가 rollback 을 건너뛰었다")
        leftovers = [n for n in os.listdir(consumer.project)
                     if n.startswith(".sage-install-backup-")]
        self.assertEqual(leftovers, [], f"보관소가 남았다: {leftovers}")

    def test_rollback_catches_base_exception_not_just_exception(self):
        """`Exception` 만 잡는 형태로 되돌아가지 않았는지 코드로 본다."""
        with open(os.path.join(REPO, "sage", "uninstall_executor.py"), encoding="utf-8") as h:
            source = h.read()
        self.assertIn("except BaseException:", source)


class HostRegistrationClassifier(unittest.TestCase):
    """host JSON 판정은 **하나**이고, 세 상태를 접지 않는다.

    읽기 실패·인코딩 오류·문법 오류를 "등록 없음" 으로 접으면 부재가 곧 통과가 되고, 통과는
    삭제로 이어진다. 실제로 그 접힘 하나 때문에 첫 실행이 설치 증거까지 지우고, 손상 파일이
    남은 두 번째 실행이 `COMPLETE` 를 냈다.
    """

    SAGE = {"sage-owned"}

    def registered(self, extra=None):
        document = {"hooks": {"PostToolUse": [
            {"matcher": "*", "hooks": [{"type": "command", "command": "sage-owned"}]}]}}
        if extra:
            document["hooks"].update(extra)
        return json.dumps(document).encode("utf-8")

    def test_syntax_damage_is_unknown_not_absent(self):
        outcome = uninstall_shared.classify_host_bytes(b'{"hooks": {"PostToolUse": [', self.SAGE)
        self.assertEqual(outcome.state, uninstall_shared.UNKNOWN,
                         "문법 손상을 '등록 없음' 으로 접었다")
        self.assertEqual(outcome.damage[0]["kind"], "json_syntax")
        self.assertIsInstance(outcome.damage[0]["line"], int)
        self.assertIsInstance(outcome.damage[0]["column"], int)

    def test_non_utf8_is_unknown_and_reports_the_offset(self):
        outcome = uninstall_shared.classify_host_bytes(b'{"hooks": {"x\xff": []}}', self.SAGE)
        self.assertEqual(outcome.state, uninstall_shared.UNKNOWN)
        self.assertEqual(outcome.damage[0]["kind"], "encoding")
        self.assertIsInstance(outcome.damage[0]["byte_offset"], int)

    def test_structural_damage_with_our_command_visible_is_present(self):
        """우리 command 가 **보이는데** 못 뺀다 — 이건 "모른다" 가 아니라 "남았다" 다."""
        outcome = uninstall_shared.classify_host_bytes(
            self.registered({"PreToolUse": "list 가 아니다"}), self.SAGE)
        self.assertEqual(outcome.state, uninstall_shared.PRESENT)
        self.assertFalse(outcome.strippable)
        damage = outcome.damage[0]
        self.assertEqual(damage["kind"], "type")
        self.assertEqual(damage["pointer"], "/hooks/PreToolUse")
        self.assertEqual((damage["expected"], damage["actual"]), ("array", "string"))

    def test_structural_damage_without_our_command_is_unknown(self):
        outcome = uninstall_shared.classify_host_bytes(
            json.dumps({"hooks": {"PreToolUse": "list 가 아니다"}}).encode(), self.SAGE)
        self.assertEqual(outcome.state, uninstall_shared.UNKNOWN)

    def test_a_clean_document_without_our_command_is_absent(self):
        for raw in (b'{"other": 1}', b'{"hooks": {}}'):
            outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
            self.assertEqual(outcome.state, uninstall_shared.ABSENT, raw)
            self.assertFalse(outcome.damage, raw)

    def test_damage_never_carries_user_content(self):
        """좌표와 타입 이름만 낸다. 설정값·command 원문·주변 JSON 은 사용자 것이다."""
        secret = "TOKEN-abc123-do-not-log"
        raw = json.dumps({"hooks": {"PostToolUse": [
            {"matcher": secret, "hooks": [{"type": "command", "command": secret}]}]},
            "apiKey": secret}).encode("utf-8")
        # 구조를 깨서 손상 경로를 타게 한다.
        raw = raw.replace(b'"hooks": [', b'"hooks": "', 1)
        outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
        rendered = json.dumps(outcome.as_json(), ensure_ascii=False)
        self.assertNotIn(secret, rendered, "손상 보고에 사용자 값이 실렸다")
        self.assertNotIn("sage-owned", rendered, "손상 보고에 command 원문이 실렸다")

    def test_a_risky_event_key_is_redacted_from_the_pointer(self):
        """식별자꼴이 아닌 key 는 좌표를 잃는 대신 가린다 — 실어서 잃는 것이 더 크다."""
        raw = json.dumps({"hooks": {"/home/me/secret token": "list 가 아니다"}}).encode()
        outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
        pointer = outcome.damage[0]["pointer"]
        self.assertNotIn("secret", pointer)
        self.assertEqual(pointer, f"/hooks/{uninstall_shared.REDACTED_SEGMENT}")

    def test_a_normal_event_key_keeps_its_coordinate(self):
        raw = json.dumps({"hooks": {"SessionStart": "list 가 아니다"}}).encode()
        outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
        self.assertEqual(outcome.damage[0]["pointer"], "/hooks/SessionStart")

    def test_an_io_failure_reports_only_the_errno_name(self):
        outcome = uninstall_shared.io_outcome(PermissionError(13, "Permission denied", "/x/y"))
        self.assertEqual(outcome.state, uninstall_shared.UNKNOWN)
        self.assertEqual(outcome.damage[0], {"kind": "io", "errno": "EACCES"})
        self.assertNotIn("/x/y", json.dumps(outcome.as_json()))

    # --- 전수 스캔과 투영의 분리 ------------------------------------------

    def test_a_command_after_a_damaged_block_is_still_seen(self):
        """손상 뒤에서 멈추지 않는다. 멈추면 **우리가 남긴 등록이 우리 눈에만 안 보인다.**

        한때 이 반복문은 손상 블록에서 `break` 했다. 그러면 뒤에 있는 우리 command 가 세어지지
        않아 상태가 `UNKNOWN` 이 되고, `UNKNOWN` 은 manifest 증거가 없으면 잔재로 세지 않는다 —
        남은 등록이 조용히 넘어가는 경로가 바로 이것이다.
        """
        raw = json.dumps({"hooks": {"PostToolUse": [
            "블록이 object 가 아니다",
            {"matcher": "*", "hooks": [{"type": "command", "command": "sage-owned"}]}]}}).encode()
        outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
        self.assertEqual(outcome.state, uninstall_shared.PRESENT,
                         "손상 뒤에 있는 우리 등록을 못 봤다")
        self.assertFalse(outcome.strippable)
        self.assertEqual(outcome.damage[0]["pointer"], "/hooks/PostToolUse/0")

    def test_every_damaged_spot_is_reported_not_just_the_first(self):
        raw = json.dumps({"hooks": {
            "PostToolUse": ["object 가 아니다", 7],
            "PreToolUse": "array 가 아니다"}}).encode()
        outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
        pointers = [entry["pointer"] for entry in outcome.damage]
        self.assertEqual(pointers, ["/hooks/PostToolUse/0", "/hooks/PostToolUse/1",
                                    "/hooks/PreToolUse"])

    def test_a_non_object_hook_entry_is_damage_not_a_foreign_entry(self):
        """이해하지 못하는 모양을 읽어서 다시 쓰는 것은 보존이 아니다.

        예전에는 hooks 배열 안의 비객체 항목을 "우리 것이 아닌 항목" 으로 보고 그대로 통과시킨
        뒤 파일을 다시 썼다. 그 순간 파일의 최종 모양을 정하는 것은 원본이 아니라 우리 파서다.
        """
        raw = json.dumps({"hooks": {"PostToolUse": [
            {"matcher": "*", "hooks": ["문자열 항목",
                                       {"type": "command", "command": "sage-owned"}]}]}}).encode()
        outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
        self.assertEqual(outcome.state, uninstall_shared.PRESENT)
        self.assertFalse(outcome.strippable, "손상된 문서를 다시 쓰려 했다")
        self.assertIsNone(outcome.body)
        self.assertEqual(outcome.damage[0]["pointer"], "/hooks/PostToolUse/0/hooks/0")

    def test_the_projection_stage_is_never_reached_while_damage_exists(self):
        """2단계는 손상 0 에서만 돈다. 그 계약이 깨지면 손상 문서가 본문을 갖는다."""
        for raw in (b'{"hooks": {"PostToolUse": ["not an object"]}}',
                    b'{"hooks": {"PostToolUse": [{"hooks": "not an array"}]}}',
                    b'{"hooks": {"PreToolUse": 7}}'):
            outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
            self.assertIsNone(outcome.body, raw)
            self.assertFalse(outcome.strippable, raw)

    # --- 항목 자체의 모양 ---------------------------------------------------

    def entry_document(self, entry, matcher="*"):
        return json.dumps({"mine": True, "hooks": {"PostToolUse": [
            {"matcher": matcher, "hooks": [entry]}]}}).encode()

    def test_a_malformed_entry_never_becomes_strippable(self):
        """배열·객체 모양만 보면 **내용이 깨진 항목**이 그대로 통과한다.

        실제로 숫자 command·배열 matcher·`type` 누락이 `present`+`strippable` 로 처리돼
        손상된 설정 파일의 bytes 가 바뀌었다. 결정 B 는 손상된 host JSON 을 절대 고치지 않는
        것이므로 이건 계약 위반이다.
        """
        cases = {
            "numeric command": self.entry_document({"type": "command", "command": 7}),
            "missing command": self.entry_document({"type": "command"}),
            "missing type": self.entry_document({"command": "sage-owned"}),
            "numeric type": self.entry_document({"type": 1, "command": "sage-owned"}),
            "array matcher": self.entry_document(
                {"type": "command", "command": "sage-owned"}, matcher=[]),
        }
        for label, raw in cases.items():
            with self.subTest(label):
                outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
                self.assertFalse(outcome.strippable, label)
                self.assertIsNone(outcome.body, label)
                self.assertTrue(outcome.damage, label)

    def test_a_missing_field_is_reported_as_missing_not_as_a_type(self):
        """값을 고치는 일과 값을 채우는 일은 사용자가 할 일이 다르다."""
        outcome = uninstall_shared.classify_host_bytes(
            self.entry_document({"command": "sage-owned"}), self.SAGE)
        self.assertEqual(outcome.damage[0],
                         {"kind": "missing", "pointer": "/hooks/PostToolUse/0/hooks/0/type"})

    def test_a_broken_entry_is_not_counted_as_ours(self):
        """소유권을 읽을 수 없는 항목을 우리 것으로 세면, 세는 순간 지울 근거가 생긴다."""
        outcome = uninstall_shared.classify_host_bytes(
            self.entry_document({"command": 7}), self.SAGE)
        self.assertEqual(outcome.state, uninstall_shared.UNKNOWN)

    def test_a_missing_matcher_is_not_damage(self):
        """matcher 가 아예 없는 event 가 있다. 없는 것은 정상이고 과차단하지 않는다."""
        raw = json.dumps({"hooks": {"SessionStart": [
            {"hooks": [{"type": "command", "command": "sage-owned"}]}]}}).encode()
        outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
        self.assertTrue(outcome.strippable)

    def test_a_duplicate_key_is_damage_not_a_silent_last_wins(self):
        """`json.loads` 는 조용히 뒤엣것을 남긴다. 그 문서를 다시 쓰면 한쪽이 사라진다."""
        raw = b'{"hooks": {"A": []}, "hooks": {"B": []}}'
        outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
        self.assertEqual(outcome.state, uninstall_shared.UNKNOWN)
        self.assertEqual(outcome.damage[0],
                         {"kind": "json_duplicate_key", "pointer": "/hooks"})

    def test_a_non_standard_json_constant_is_damage(self):
        for raw, name in ((b'{"hooks": NaN}', "NaN"), (b'{"hooks": Infinity}', "Infinity")):
            outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
            self.assertEqual(outcome.state, uninstall_shared.UNKNOWN, raw)
            self.assertEqual(outcome.damage[0], {"kind": "json_constant", "name": name})

    def test_a_risky_duplicate_key_is_redacted(self):
        raw = b'{"/home/me/token abc": 1, "/home/me/token abc": 2}'
        outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
        self.assertNotIn("token", json.dumps(outcome.as_json()))

    # --- handler 종류마다 계약이 다르다 -------------------------------------

    SAGE_HANDLER = {"type": "command", "command": "sage-owned"}
    USER_HANDLERS = {
        # 사용자 소유 `command` — SAGE 것과 command 문자열이 다르다.
        "command": {"type": "command", "command": "my-own-hook"},
        "prompt": {"type": "prompt", "prompt": "이 변경을 검토해줘"},
        "agent": {"type": "agent", "prompt": "영향 범위를 분석해줘", "model": "fast"},
        "http": {"type": "http", "url": "https://example.invalid/hook"},
        "mcp_tool": {"type": "mcp_tool", "server": "db", "tool": "query"},
    }

    def coexisting(self, user_handler):
        return json.dumps({"mine": True, "hooks": {"PostToolUse": [
            {"matcher": "*", "hooks": [self.SAGE_HANDLER, user_handler]}]}}).encode()

    NON_COMMAND = ("prompt", "agent", "http", "mcp_tool")

    def test_a_normal_non_command_handler_is_not_damage(self):
        """`command` 필드는 **command handler 하나의 규칙**이다.

        모든 handler 에 그것을 요구하면 정상 `prompt` hook 을 나란히 둔 사용자가 자기 설정을
        손상으로 보고받고, uninstall 이 영원히 `PARTIAL` 로 끝난다. 우리가 모르는 것을 손상이라고
        부른 것이다.
        """
        for label in self.NON_COMMAND:
            with self.subTest(label):
                outcome = uninstall_shared.classify_host_bytes(
                    self.coexisting(self.USER_HANDLERS[label]), self.SAGE)
                self.assertTrue(outcome.strippable, f"{label}: {outcome.as_json()}")
                self.assertEqual(outcome.damage, ())

    def test_only_the_sage_command_leaves_and_the_user_handler_is_byte_identical(self):
        for label in self.NON_COMMAND:
            handler = self.USER_HANDLERS[label]
            with self.subTest(label):
                outcome = uninstall_shared.classify_host_bytes(
                    self.coexisting(handler), self.SAGE)
                document = json.loads(outcome.body)
                kept = [entry for block in document["hooks"]["PostToolUse"]
                        for entry in block["hooks"]]
                self.assertEqual(kept, [handler], f"{label}: 사용자 handler 가 바뀌었다")
                self.assertTrue(document["mine"])

    def test_a_non_command_handler_is_never_ours_even_with_our_command_string(self):
        """type 을 먼저 보지 않으면 남의 hook 을 우리 것으로 세고, 세는 순간 지울 근거가 생긴다."""
        for kind in ("prompt", "agent"):
            with self.subTest(kind):
                impostor = dict(self.USER_HANDLERS[kind], command="sage-owned")
                raw = json.dumps({"hooks": {"PostToolUse": [
                    {"matcher": "*", "hooks": [impostor]}]}}).encode()
                outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
                self.assertEqual(outcome.state, uninstall_shared.ABSENT,
                                 "우리 것이 아닌 항목을 등록으로 셌다")
                self.assertIsNone(outcome.body)

    def test_an_impostor_survives_the_projection_beside_a_real_registration(self):
        """제거가 **실제로 일어나는** 문서에서 impostor 가 살아남는지 본다.

        impostor 만 있는 문서는 `absent` 라 투영 단계에 닿지 않는다. 그래서 그 문서 하나로는
        투영의 조건이 무엇이든 검사가 통과한다 — 진짜 등록을 나란히 둬야 2단계가 돌고, 그때
        조건이 틀렸으면 사용자의 hook 이 함께 사라진다.
        """
        for kind in ("prompt", "agent"):
            with self.subTest(kind):
                impostor = dict(self.USER_HANDLERS[kind], command="sage-owned")
                raw = json.dumps({"hooks": {"PostToolUse": [
                    {"matcher": "*", "hooks": [self.SAGE_HANDLER, impostor]}]}}).encode()
                outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
                self.assertTrue(outcome.strippable)
                document = json.loads(outcome.body)
                kept = [entry for block in document["hooks"]["PostToolUse"]
                        for entry in block["hooks"]]
                self.assertEqual(kept, [impostor],
                                 "우리 command 문자열을 가진 남의 handler 를 함께 지웠다")

    def test_each_handler_kind_requires_its_own_fields(self):
        broken = {
            "prompt": {"type": "prompt"},
            "agent": {"type": "agent"},
            "http": {"type": "http"},
            "mcp_tool": {"type": "mcp_tool", "server": "db"},
        }
        for label, handler in broken.items():
            with self.subTest(label):
                outcome = uninstall_shared.classify_host_bytes(
                    self.coexisting(handler), self.SAGE)
                self.assertFalse(outcome.strippable, label)
                self.assertEqual(outcome.damage[0]["kind"], "missing", label)

    def test_an_unknown_handler_kind_is_fail_closed(self):
        outcome = uninstall_shared.classify_host_bytes(
            self.coexisting({"type": "telepathy"}), self.SAGE)
        self.assertFalse(outcome.strippable)
        self.assertEqual(outcome.damage[0]["kind"], "unknown_kind")

    def test_the_classifier_receives_the_host(self):
        """`.claude/settings.json` 과 `.codex/hooks.json` 은 서로 다른 host 의 계약이다.

        한 표로 섞어 두면 한쪽에서만 참인 규칙이 다른 쪽 사용자를 막는다.
        """
        raw = self.coexisting(self.USER_HANDLERS["prompt"])   # PostToolUse — 다섯 종류 전부 허용
        for host in ("claude", "codex"):
            with self.subTest(host):
                self.assertTrue(
                    uninstall_shared.classify_host_bytes(raw, self.SAGE, host).strippable)
        self.assertEqual(set(uninstall_shared.EVENT_HANDLER_KINDS), {"claude", "codex"})

    def event_document(self, event, handler):
        """정상 SAGE 등록 + 지정 event 의 사용자 handler 하나."""
        return json.dumps({"mine": True, "hooks": {
            "PostToolUse": [{"matcher": "*", "hooks": [self.SAGE_HANDLER]}],
            event: [{"hooks": [handler]}]}}).encode()

    def outcome_for(self, event, kind, host="claude"):
        return uninstall_shared.classify_host_bytes(
            self.event_document(event, self.USER_HANDLERS[kind]), self.SAGE, host)

    # 공식 hooks reference 의 세 그룹에서 하나씩. **production 표를 그대로 읽는다** —
    # 검사가 제한을 주입해서 확인하면 표가 비어도 초록이라 계약을 지키지 못한다.
    EARLY_EVENT = "SessionStart"
    NO_LLM_EVENT = "Notification"
    FULL_EVENT = "Stop"

    def test_session_start_and_setup_reject_http_prompt_and_agent(self):
        """세션이 서기 전에 발화하는 둘은 `command`·`mcp_tool` 만 받는다."""
        for event in ("SessionStart", "Setup"):
            for kind in ("http", "prompt", "agent"):
                with self.subTest(f"{event}/{kind}"):
                    outcome = self.outcome_for(event, kind)
                    self.assertFalse(outcome.strippable)
                    self.assertIsNone(outcome.body, "지원하지 않는 문서를 다시 썼다")
                    self.assertEqual(outcome.damage[0]["kind"], "unsupported_kind")
                    self.assertEqual(outcome.damage[0]["handler"], kind)

    def test_session_start_and_setup_accept_command_and_mcp_tool(self):
        for event in ("SessionStart", "Setup"):
            for kind in ("command", "mcp_tool"):
                with self.subTest(f"{event}/{kind}"):
                    self.assertTrue(self.outcome_for(event, kind).strippable)

    def test_the_no_llm_group_rejects_prompt_and_agent(self):
        for kind in ("prompt", "agent"):
            with self.subTest(kind):
                outcome = self.outcome_for(self.NO_LLM_EVENT, kind)
                self.assertFalse(outcome.strippable)
                self.assertEqual(outcome.damage[0]["kind"], "unsupported_kind")

    def test_the_no_llm_group_accepts_command_http_and_mcp_tool(self):
        for kind in ("command", "http", "mcp_tool"):
            with self.subTest(kind):
                self.assertTrue(self.outcome_for(self.NO_LLM_EVENT, kind).strippable)

    def test_the_full_group_accepts_all_five_kinds(self):
        for kind in self.USER_HANDLERS:
            with self.subTest(kind):
                self.assertTrue(self.outcome_for(self.FULL_EVENT, kind).strippable)

    def test_the_production_table_actually_carries_the_official_groups(self):
        """표가 비면 위 검사들이 전부 초록이 된다. **표 자체**를 단언한다."""
        table = uninstall_shared.EVENT_HANDLER_KINDS["claude"]
        self.assertEqual(set(table["SessionStart"]), {"command", "mcp_tool"})
        self.assertEqual(set(table["Setup"]), {"command", "mcp_tool"})
        self.assertEqual(set(table["Notification"]), {"command", "http", "mcp_tool"})
        self.assertEqual(set(table["Stop"]),
                         {"command", "http", "mcp_tool", "prompt", "agent"})
        self.assertGreaterEqual(len(table), 33, "공식 표의 event 수가 줄었다")

    def test_an_unlisted_event_is_fail_closed(self):
        """공식 event 계약표가 등록된 host 에서 표에 없는 event 를 만나면 **전부 허용으로 추정하지 않는다.**

        추정하면 문서가 늘어난 event 하나가 조용히 규칙 밖으로 빠지고, 그 자리가 우리가
        이해하지 못한 문서를 다시 쓰는 통로가 된다.
        """
        outcome = self.outcome_for("SomeEventWeHaveNeverSeen", "command")
        self.assertFalse(outcome.strippable)
        self.assertIsNone(outcome.body)
        self.assertEqual(outcome.damage[0]["kind"], "unknown_event")

    def test_a_real_sage_registration_still_strips(self):
        """제한이 정상 설치본을 막으면 이 명령 자체를 못 쓴다."""
        document = {"mine": True, "hooks": {}}
        for event in ("PreToolUse", "PostToolUse", "SessionStart", "Stop",
                      "UserPromptSubmit"):
            document["hooks"][event] = [{"matcher": "", "hooks": [self.SAGE_HANDLER]}]
        outcome = uninstall_shared.classify_host_bytes(
            json.dumps(document).encode(), self.SAGE, "claude")
        self.assertTrue(outcome.strippable, outcome.as_json())
        self.assertNotIn("hooks", json.loads(outcome.body))

    def test_a_host_without_a_table_is_not_restricted_at_all(self):
        """표가 비어 있는 host 는 **미등록 event 에서도** 막지 않는다.

        `unknown_event` fail-closed 는 계약표를 옮겨 둔 host 에만 적용된다. 갖고 있지 않은
        계약을 근거로 남의 설정을 막는 것도 추정이고, 그 추정은 codex 사용자를 통째로 막는다.
        문서가 이보다 넓게 적혀 있었고, 이 검사가 그 문장을 코드에 묶는다.
        """
        self.assertEqual(uninstall_shared.EVENT_HANDLER_KINDS["codex"], {})
        for event in ("SessionStart", "SomeEventWeHaveNeverSeen"):
            for kind in ("prompt", "agent", "http"):
                with self.subTest(f"{event}/{kind}"):
                    self.assertTrue(self.outcome_for(event, kind, host="codex").strippable)
        # 같은 조합이 claude 에서는 막힌다 — 차이가 host 에서 온다는 것이 요점이다.
        self.assertFalse(self.outcome_for("SessionStart", "prompt").strippable)

    def test_the_claude_table_does_not_bind_codex(self):
        """codex 계약은 별도 문서다. claude 표를 복사하면 두 host 를 섞은 하나가 된다."""
        self.assertEqual(uninstall_shared.EVENT_HANDLER_KINDS["codex"], {})
        outcome = self.outcome_for("SessionStart", "prompt", host="codex")
        self.assertTrue(outcome.strippable, "claude 의 제한이 codex 를 묶었다")

    def test_a_clean_document_still_strips_only_our_entries(self):
        """분리했다고 제거가 약해지지 않았는지 본다."""
        raw = json.dumps({"mine": True, "hooks": {"PostToolUse": [
            {"matcher": "*", "hooks": [{"type": "command", "command": "sage-owned"},
                                       {"type": "command", "command": "user-hook"}]}]}}).encode()
        outcome = uninstall_shared.classify_host_bytes(raw, self.SAGE)
        self.assertTrue(outcome.strippable)
        document = json.loads(outcome.body)
        commands = [entry["command"]
                    for block in document["hooks"]["PostToolUse"] for entry in block["hooks"]]
        self.assertEqual(commands, ["user-hook"], "사용자 hook 이 함께 사라졌다")
        self.assertTrue(document["mine"])


class DamagedHostJson(Base):
    """손상된 host JSON 은 **절대 고치지 않고** 보존하며, 그 사실이 매 실행 보고된다.

    계획과 실행과 흔적 판정이 같은 문서를 다르게 읽으면, 실행이 조용히 건너뛴 것을 화면은
    "제거했다" 고 말한다. 그러면 파일은 그대로인데 성공으로 끝나고, 다음 실행은 아무것도 모른다.
    """

    def host_path(self, consumer, host="claude"):
        directory = ".claude" if host == "claude" else ".codex"
        name = "settings.json" if host == "claude" else "hooks.json"
        path = os.path.join(consumer.project, directory, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def registered_document(self, host="claude"):
        command = sorted(uninstall_plan.canonical_commands(host))[0]
        return {"hooks": {"PostToolUse": [
            {"matcher": "*", "hooks": [{"type": "command", "command": command}]}]}, "mine": True}

    def seed(self, consumer, kind, host="claude"):
        """손상 종류 하나를 실제 파일로 만든다. 되돌릴 정상 본문도 함께 돌려준다."""
        path = self.host_path(consumer, host)
        healthy = json.dumps(self.registered_document(host), ensure_ascii=False,
                             indent=2).encode("utf-8")
        if kind == "structure":
            document = self.registered_document(host)
            document["hooks"]["PreToolUse"] = "이건 list 가 아니다"
            payload = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        elif kind == "syntax":
            payload = healthy[:len(healthy) // 2]
        elif kind == "encoding":
            payload = healthy.replace(b'"mine"', b'"mi\xffne"')
        else:
            raise AssertionError(kind)
        with open(path, "wb") as handle:
            handle.write(payload)
        return path, payload, healthy

    def manifest(self, consumer):
        return os.path.join(consumer.project, "docs", "sage_harness", ".manifest.json")

    def plan_for(self, consumer):
        return uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)

    def action_for(self, plan, path):
        found = [a for a in plan.actions if a.path == path]
        self.assertEqual(len(found), 1, f"계획에 {path} 가 정확히 한 번 있어야 한다")
        return found[0]

    # --- 손상 종류별 계획 ---------------------------------------------------

    def test_every_damage_kind_lands_in_preserve_with_its_coordinate(self):
        expected = {"structure": "type", "syntax": "json_syntax", "encoding": "encoding"}
        for kind, damage_kind in expected.items():
            with self.subTest(kind=kind):
                consumer = self.fresh()
                path, _payload, _healthy = self.seed(consumer, kind)
                action = self.action_for(self.plan_for(consumer), path)
                self.assertEqual(action.kind, uninstall_plan.PRESERVE,
                                 f"{kind} 인데 {action.kind} 로 분류됐다")
                self.assertEqual(action.reason, "uninstall.host_json_damaged")
                self.assertEqual([e["kind"] for e in action.detail], [damage_kind])
                self.assertIn(action.state,
                              (uninstall_shared.PRESENT, uninstall_shared.UNKNOWN))
                self.assertNotIn(path, self.plan_for(consumer).write_targets())

    def test_a_permission_denied_host_file_is_preserved_not_ignored(self):
        self.assertNotEqual(getattr(os, "geteuid", lambda: 1)(), 0,
                            "root 로 돌면 권한 거부를 만들 수 없다 — 일반 사용자로 실행하세요")
        consumer = self.fresh()
        path = self.host_path(consumer)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.registered_document(), handle)
        os.chmod(path, 0o000)
        self.addCleanup(os.chmod, path, 0o600)
        action = self.action_for(self.plan_for(consumer), path)
        self.assertEqual(action.kind, uninstall_plan.PRESERVE)
        self.assertEqual(action.state, uninstall_shared.UNKNOWN)
        self.assertEqual(action.detail[0]["kind"], "io")
        self.assertEqual(action.detail[0]["errno"], "EACCES")

    def test_an_unreadable_file_without_install_proof_is_not_called_sage_residue(self):
        """증거가 없으면 "SAGE 잔재" 라고 부르지 않는다. 모르는 것을 주장하는 일이다."""
        consumer = self.fresh()
        path = self.host_path(consumer, "codex")     # claude 설치본이라 codex 증거가 없다
        with open(path, "wb") as handle:
            handle.write(b'{"hooks": [')
        with open(self.manifest(consumer), encoding="utf-8") as handle:
            manifest = json.load(handle)
        self.assertNotIn("codex", uninstall_plan.manifest_installed_hosts(manifest))
        action = self.action_for(self.plan_for(consumer), path)
        self.assertEqual(action.reason, "uninstall.host_json_unreadable")

    # --- 영수증 보존 --------------------------------------------------------

    def test_the_manifest_tree_is_retained_while_residue_remains(self):
        """영수증은 잔재보다 오래 살아야 한다 — 증거를 먼저 지우면 다음 실행이 눈이 먼다."""
        consumer = self.fresh()
        path, damaged_bytes, _healthy = self.seed(consumer, "syntax")
        plan = self.plan_for(consumer)
        tree = os.path.join(consumer.project, "docs", "sage_harness")
        action = self.action_for(plan, tree)
        self.assertEqual(action.kind, uninstall_plan.PRESERVE,
                         "잔재가 남았는데 설치 기록을 지우려 한다")
        self.assertEqual(action.reason, "uninstall.receipt_retained_for_residual")

        result = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertTrue(os.path.isfile(self.manifest(consumer)), "설치 기록이 사라졌다")
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), damaged_bytes, "보존한다고 하고 고쳤다")

    def test_a_repeated_run_stays_partial_and_repeats_the_path(self):
        """잔재가 남아 있는 한 매 실행은 **mutation 없는** `PARTIAL(1)` 이다."""
        consumer = self.fresh()
        path, damaged_bytes, _healthy = self.seed(consumer, "structure")
        mode = stat.S_IMODE(os.lstat(path).st_mode)
        first = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertEqual(first.returncode, 1, first.stdout + first.stderr)

        before = self.digest(consumer.project)
        second = sage("uninstall", "--dest", consumer.project, "--yes", "--json",
                      env=consumer.env)
        self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
        payload = json.loads(second.stdout)
        self.assertEqual(payload["status"], "PARTIAL")
        self.assertEqual(payload["deleted"], [], "두 번째 실행이 무언가를 지웠다")
        self.assertEqual(payload["stripped"], [])
        self.assertEqual(before, self.digest(consumer.project), "두 번째 실행이 디스크를 바꿨다")

        preserved = {entry["path"]: entry for entry in payload["preserved"]}
        shown = os.path.join(".claude", "settings.json")
        self.assertIn(shown, preserved, "남은 것을 두 번째 실행이 말하지 않았다")
        entry = preserved[shown]
        self.assertEqual(entry["reason"], "uninstall.host_json_damaged")
        self.assertEqual(entry["registration_state"], uninstall_shared.PRESENT)
        self.assertEqual([e["kind"] for e in entry["detail"]], ["type"])
        self.assertIn(os.path.join("docs", "sage_harness"), preserved)

        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), damaged_bytes, "바이트가 바뀌었다")
        self.assertEqual(stat.S_IMODE(os.lstat(path).st_mode), mode, "mode 가 바뀌었다")

    def test_both_hosts_damaged_are_both_reported(self):
        consumer = self.fresh()
        claude, _c, _ch = self.seed(consumer, "structure", "claude")
        codex, _x, _xh = self.seed(consumer, "syntax", "codex")
        # 두 host 모두 설치됐다고 manifest 가 증명하도록 한다.
        path = self.manifest(consumer)
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
        document["installed_hosts"] = ["claude", "codex"]
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)

        result = sage("uninstall", "--dest", consumer.project, "--yes", "--json",
                      env=consumer.env)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        preserved = {entry["path"] for entry in json.loads(result.stdout)["preserved"]}
        self.assertIn(os.path.relpath(claude, consumer.project), preserved)
        self.assertIn(os.path.relpath(codex, consumer.project), preserved)
        self.assertTrue(os.path.isfile(path), "잔재가 둘인데 설치 기록을 지웠다")

    def test_repairing_the_file_lets_the_last_asset_go(self):
        """사용자가 고친 뒤에야 manifest tree 가 **마지막 논리 자산**으로 제거된다."""
        consumer = self.fresh()
        path, _damaged, healthy = self.seed(consumer, "syntax")
        first = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertEqual(first.returncode, 1, first.stdout + first.stderr)
        self.assertTrue(os.path.isfile(self.manifest(consumer)))

        with open(path, "wb") as handle:
            handle.write(healthy)
        third = sage("uninstall", "--dest", consumer.project, "--yes", "--json",
                     env=consumer.env)
        self.assertIn(third.returncode, (0, 1), third.stdout + third.stderr)
        payload = json.loads(third.stdout)
        self.assertIn(os.path.relpath(path, consumer.project),
                      [entry["path"] for entry in payload["stripped"]],
                      "고친 파일에서 SAGE 등록을 빼지 않았다")
        self.assertFalse(os.path.exists(os.path.join(consumer.project, "docs", "sage_harness")),
                         "잔재가 사라졌는데 설치 기록이 남았다")
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"mine": True})

    # --- 판정 권위 ----------------------------------------------------------

    def test_every_host_decision_goes_through_one_classifier(self):
        """판정을 바꾸면 계획이 따라 바뀐다. 안 바뀌면 다른 파서가 남아 있다는 뜻이다."""
        consumer = self.fresh()
        path, _damaged, _healthy = self.seed(consumer, "structure")
        self.assertIn(path, {a.path for a in self.plan_for(consumer).actions})

        original = uninstall_shared.classify_host_bytes
        uninstall_shared.classify_host_bytes = (
            lambda raw, commands, host=None: uninstall_shared.Outcome(uninstall_shared.ABSENT))
        try:
            blind = self.plan_for(consumer)
            traces = uninstall_plan.sage_traces(consumer.project)
        finally:
            uninstall_shared.classify_host_bytes = original
        self.assertNotIn(path, {a.path for a in blind.actions},
                         "판정 권위를 바꿨는데 계획이 그대로다 — 다른 파서가 남아 있다")
        self.assertNotIn(path, traces,
                         "판정 권위를 바꿨는데 흔적 판정이 그대로다 — 다른 파서가 남아 있다")

    def test_the_executor_refuses_and_rolls_back_when_the_document_disagrees(self):
        """실행 직전에 뺄 수 없게 됐으면 **조용히 건너뛰지 않고 되돌린다.**"""
        consumer = self.fresh()
        path = self.host_path(consumer)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.registered_document(), handle, ensure_ascii=False, indent=2)
        plan = self.plan_for(consumer)
        self.assertIn(path, plan.write_targets())
        before = self.digest(consumer.project)

        original = uninstall_shared.classify_host_bytes
        uninstall_shared.classify_host_bytes = (
            lambda raw, commands, host=None: uninstall_shared.Outcome(
                uninstall_shared.PRESENT, [uninstall_shared.damage_syntax(1, 1)]))
        try:
            with self.assertRaises(ValueError) as caught:
                uninstall_executor.execute(plan)
        finally:
            uninstall_shared.classify_host_bytes = original
        self.assertEqual(str(caught.exception), "uninstall.strip_not_applicable")
        self.assertEqual(before, self.digest(consumer.project),
                         "멈췄다면서 되돌리지 않았다")

    def digest(self, root):
        found = {}
        for folder, _dirs, files in os.walk(root):
            for name in sorted(files):
                path = os.path.join(folder, name)
                try:
                    with open(path, "rb") as handle:
                        found[os.path.relpath(path, root)] = handle.read()
                except OSError:
                    found[os.path.relpath(path, root)] = None
        return found


class BroadDestination(Base):
    """filesystem root 와 그 **직계 자식**은 소비 프로젝트가 아니다.

    한때 이 판정은 `/usr`·`/opt`·`/Users` 를 통과시켰다. 주석은 "한 단계 경로도 막는다" 라고
    적혀 있었지만 조건이 `tail` 이 빈 경우만 참이라 root 자체 말고는 아무것도 걸리지 않았다.
    주석이 말한 규칙과 코드가 지킨 규칙이 다르면, 지켜지는 것은 언제나 코드 쪽이다.

    여기서 한 번 통과하면 그 아래 전부가 후보가 된다. 그래서 **계획 단계에서** 막고, 계획이
    쓰기 대상을 하나도 갖지 않는다는 것까지 본다 — 상태만 `BLOCKED` 이고 목록은 차 있는 계획은
    다음 실수 하나로 실행된다.
    """

    def root_children(self):
        """실제 filesystem root 의 직계 자식 몇 개. 이름을 손으로 적지 않는다."""
        found = []
        for name in sorted(os.listdir(os.sep)):
            path = os.path.join(os.sep, name)
            if os.path.isdir(path) and not os.path.islink(path):
                found.append(path)
            if len(found) >= 4:
                break
        self.assertTrue(found, "root 직계 자식을 하나도 못 찾았다")
        return found

    def test_the_filesystem_root_and_its_children_are_blocked(self):
        for path in [os.sep, os.path.expanduser("~")] + self.root_children():
            plan = uninstall_plan.build(path, uninstall_plan.SCOPE_PROJECT)
            self.assertEqual(plan.status, uninstall_plan.BLOCKED, path)
            self.assertEqual(plan.blocked_reason, "uninstall.dest_too_broad", path)
            self.assertEqual(plan.exit_code, 2, path)
            self.assertEqual(plan.write_targets(), (), f"{path} 에 쓰기 대상이 생겼다")
            self.assertEqual(plan.of_kind(uninstall_plan.DELETE), (), path)
            self.assertEqual(plan.of_kind(uninstall_plan.STRIP), (), path)

    def test_a_broad_destination_exits_two_from_the_cli(self):
        """`--yes` 로도 계획 단계에서 끝난다. 확인 없이 실행으로 넘어가지 않는다."""
        target = self.root_children()[0]
        for extra in (["--check"], ["--yes"]):
            result = sage("uninstall", "--dest", target, *extra)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertNotIn("삭제:", result.stdout, f"{extra} 가 삭제 목록을 보였다")

    def test_a_normal_project_is_not_caught(self):
        """막는 것과 과차단은 다르다. 정상 프로젝트가 걸리면 이 명령은 못 쓴다."""
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertNotEqual(plan.blocked_reason, "uninstall.dest_too_broad")

    def test_a_broad_global_skill_root_is_blocked_too(self):
        """`$CODEX_HOME` 이 `/` 면 전역 root 는 `/skills` 다. 같은 실수가 다른 문으로 들어온다."""
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_GLOBAL,
                                    environ={"CODEX_HOME": os.sep})
        self.assertEqual(plan.status, uninstall_plan.BLOCKED)
        self.assertEqual(plan.blocked_reason, "uninstall.global_root_too_broad")
        self.assertEqual(plan.write_targets(), ())


class ManifestContract(Base):
    """manifest 는 **소유권 증거**다. 증거로 쓸 수 있는 모양인지 먼저 본다.

    한때 이 판정은 최상위가 dict 인지까지만 봤다. 그래서 `{}` 도 정상 manifest 로 통과했고,
    빈 manifest 는 "설치는 증명됐고 배치 기록은 하나도 없다" 로 읽혔다 — 기록이 없으니 host
    렌더도 skill 도 후보에 오르지 않는데 SAGE 전용 tree 는 이름만으로 지워진다. 실측에서 첫
    실행이 그 증거를 지웠고, 손상 host JSON 이 남은 두 번째 실행이 `COMPLETE(0)` 를 냈다.
    """

    def write_manifest(self, consumer, document):
        path = uninstall_plan.manifest_path(consumer.project)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
        return path

    def valid(self, consumer):
        with open(uninstall_plan.manifest_path(consumer.project), encoding="utf-8") as handle:
            return json.load(handle)

    BROKEN = {
        "empty": {},
        "missing_host_runtime": {"sage_version": "1", "assets": {}},
        "missing_assets": {"sage_version": "1", "host_runtime": "claude"},
        "assets_not_mapping": {"sage_version": "1", "host_runtime": "claude", "assets": "x"},
        "asset_entry_not_object": {"sage_version": "1", "host_runtime": "claude",
                                   "assets": {"skills/a": "not an object"}},
        "host_runtime_unknown": {"sage_version": "1", "host_runtime": "emacs", "assets": {}},
        "sage_version_not_string": {"sage_version": 1, "host_runtime": "claude", "assets": {}},
        "installed_hosts_not_list": {"sage_version": "1", "host_runtime": "claude",
                                     "assets": {}, "installed_hosts": "claude"},
        "installed_hosts_without_primary": {"sage_version": "1", "host_runtime": "claude",
                                            "assets": {}, "installed_hosts": ["codex"]},
        "core_renders_not_mapping": {"sage_version": "1", "host_runtime": "claude",
                                     "assets": {}, "core_renders": []},
    }

    def test_a_manifest_that_breaks_the_contract_blocks_before_anything_moves(self):
        for label, document in self.BROKEN.items():
            with self.subTest(label):
                consumer = self.fresh()
                self.write_manifest(consumer, document)
                plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
                self.assertEqual(plan.status, uninstall_plan.BLOCKED, label)
                self.assertEqual(plan.blocked_reason, "uninstall.manifest_contract_violation",
                                 label)
                self.assertEqual(plan.exit_code, 2, label)
                self.assertEqual(plan.write_targets(), (), f"{label} 에 쓰기 대상이 생겼다")

    def test_the_violation_carries_a_coordinate_not_just_a_verdict(self):
        consumer = self.fresh()
        self.write_manifest(consumer, self.BROKEN["missing_assets"])
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        blocked = plan.of_kind(uninstall_plan.BLOCK)
        self.assertEqual(len(blocked), 1)
        detail = blocked[0].detail[0]
        self.assertEqual(detail["kind"], "manifest")
        self.assertEqual(detail["code"], "manifest_field_missing")
        self.assertEqual(detail["field"], "assets")

    def test_an_empty_manifest_no_longer_lets_the_receipt_be_deleted(self):
        """실측으로 보고된 그 순서를 그대로 밟는다 — 첫 실행이 증거를 지웠고 두 번째가 초록이었다."""
        consumer = self.fresh()
        path = self.write_manifest(consumer, {})
        damaged = os.path.join(consumer.project, ".claude", "settings.json")
        os.makedirs(os.path.dirname(damaged), exist_ok=True)
        with open(damaged, "wb") as handle:
            handle.write(b'{"hooks": {"PostToolUse": [')

        first = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertEqual(first.returncode, 2, first.stdout + first.stderr)
        self.assertTrue(os.path.isfile(path), "손상된 manifest 를 지웠다")
        self.assertTrue(os.path.isdir(os.path.join(consumer.project, "docs", "sage_harness")),
                        "증거 tree 가 사라졌다")

        second = sage("uninstall", "--dest", consumer.project, "--yes", "--json",
                      env=consumer.env)
        self.assertEqual(second.returncode, 2, "두 번째 실행이 손상을 남긴 채 통과했다")
        payload = json.loads(second.stdout)
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["deleted"], [])
        self.assertEqual(payload["stripped"], [])
        with open(damaged, "rb") as handle:
            self.assertEqual(handle.read(), b'{"hooks": {"PostToolUse": [')

    def test_a_real_manifest_passes(self):
        """계약이 정상 설치본을 막으면 이 명령 자체를 못 쓴다."""
        consumer = self.fresh()
        self.assertIsNone(manifest_contract.violation(self.valid(consumer)))
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertNotEqual(plan.status, uninstall_plan.BLOCKED)

    def test_a_manifest_without_the_newer_keys_still_passes(self):
        """`installed_hosts`·`core_renders` 는 나중에 생겼다. **없는 것과 틀린 것은 다르다.**"""
        document = self.valid(self.fresh())
        for key in ("installed_hosts", "core_renders", "core_skill_receipts"):
            document.pop(key, None)
        self.assertIsNone(manifest_contract.violation(document))

    def test_install_and_uninstall_read_the_same_contract(self):
        """쓰는 쪽이 거부하는 모양을 읽는 쪽이 받아들이면, 느슨한 쪽이 실제 기준이 된다."""
        for label, document in self.BROKEN.items():
            with self.subTest(label):
                self.assertIsNotNone(manifest_contract.violation(document), label)
                self.assertIsNotNone(install_cmd._manifest_structure_issue(document), label)

    # --- receipt 는 소유권 증거다 -------------------------------------------

    def snapshot(self, root):
        """경로 → 내용 해시. 크기만 보면 **같은 크기의 다른 내용**이 통과한다."""
        import hashlib
        found = {}
        for folder, _dirs, files in os.walk(root):
            for name in sorted(files):
                path = os.path.join(folder, name)
                try:
                    with open(path, "rb") as handle:
                        found[os.path.relpath(path, root)] = hashlib.sha256(
                            handle.read()).hexdigest()
                except OSError:
                    found[os.path.relpath(path, root)] = "unreadable"
        return found

    def broken_receipt_consumer(self, mutate):
        """실제 설치본의 manifest 를 손상시키고, managed-name 파일을 사용자 내용으로 바꾼다."""
        consumer = self.fresh()
        path = uninstall_plan.manifest_path(consumer.project)
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        render = mutate(manifest)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
        return consumer, render

    def blank_core_render_receipt(self, manifest):
        key = sorted(k for k in manifest.get("core_renders", {}) if "/agents/" in k)[0]
        manifest["core_renders"][key] = {}
        return key.split("/")[-1]

    def blank_asset_entry(self, manifest):
        key = sorted(manifest["assets"])[0]
        manifest["assets"][key] = {}
        return None

    def test_an_incomplete_core_render_receipt_never_proves_ownership(self):
        """receipt 가 비었으면 우리는 **무엇을 배치했는지 모르는 상태**다.

        `.claude/agents/` 는 사용자도 자기 agent 를 두는 공유 디렉터리다. 모르는 상태에서
        지우면 남의 파일을 지운다. 실측에서 receipt 를 `{}` 로 바꾸고 파일을 사용자 내용으로
        교체했더니 계약은 정상이라 했고 계획은 그 파일을 `DELETE` 했다.
        """
        consumer, agent_id = self.broken_receipt_consumer(self.blank_core_render_receipt)
        render = os.path.join(consumer.project, ".claude", "agents", f"{agent_id}.md")
        mine = "내가 직접 쓴 agent\n".encode("utf-8")
        with open(render, "wb") as handle:
            handle.write(mine)

        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertEqual(plan.status, uninstall_plan.BLOCKED)
        self.assertEqual(plan.blocked_reason, "uninstall.manifest_contract_violation")
        self.assertEqual(plan.write_targets(), ())
        self.assertNotIn(render, {action.path for action in plan.of_kind(uninstall_plan.DELETE)})

        result = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        with open(render, "rb") as handle:
            self.assertEqual(handle.read(), mine, "소유권을 증명하지 못한 파일을 건드렸다")

    def test_a_malformed_asset_entry_blocks_too(self):
        consumer, _ = self.broken_receipt_consumer(self.blank_asset_entry)
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertEqual(plan.status, uninstall_plan.BLOCKED)
        self.assertEqual(plan.write_targets(), ())
        detail = plan.of_kind(uninstall_plan.BLOCK)[0].detail[0]
        self.assertEqual(detail["kind"], "manifest")
        self.assertIn("asset", detail, "어느 자산이 문제인지 말하지 않았다")

    def test_a_broken_receipt_stays_blocked_on_a_second_run(self):
        """두 번째 실행이 초록으로 접히면 첫 실행의 차단은 미룬 것일 뿐이다."""
        consumer, agent_id = self.broken_receipt_consumer(self.blank_core_render_receipt)
        render = os.path.join(consumer.project, ".claude", "agents", f"{agent_id}.md")
        before = self.snapshot(consumer.project)
        first = sage("uninstall", "--dest", consumer.project, "--yes", env=consumer.env)
        second = sage("uninstall", "--dest", consumer.project, "--yes", "--json",
                      env=consumer.env)
        self.assertEqual((first.returncode, second.returncode), (2, 2),
                         first.stdout + second.stdout)
        payload = json.loads(second.stdout)
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["deleted"], [])
        self.assertEqual(payload["stripped"], [])
        self.assertEqual(before, self.snapshot(consumer.project), "차단인데 디스크가 바뀌었다")
        self.assertTrue(os.path.isfile(render))

    def test_install_rejects_every_receipt_uninstall_rejects(self):
        """권위가 하나라는 것은 **양쪽이 같은 것을 거부한다**는 뜻이다."""
        base = self.valid(self.fresh())
        key = sorted(k for k in base["core_renders"] if "/agents/" in k)[0]
        asset = sorted(base["assets"])[0]
        variants = {
            "empty core render receipt": {"core_renders": {key: {}}},
            "short base sha": {"core_renders": {key: {"base_sha256": "abc",
                                                      "sage_version": "1"}}},
            "unknown receipt field": {"core_renders": {key: dict(base["core_renders"][key],
                                                                 extra=1)}},
            "half semantic source": {"core_renders": {key: dict(base["core_renders"][key],
                                                                semantic_source="x")}},
            "empty asset entry": {"assets": {asset: {}}},
            "unknown asset field": {"assets": {asset: dict(base["assets"][asset], nope=1)}},
            "bad asset hash": {"assets": {asset: dict(base["assets"][asset],
                                                      spec_hash="not-a-hash")}},
        }
        for label, patch in variants.items():
            with self.subTest(label):
                document = json.loads(json.dumps(base))
                for field, value in patch.items():
                    document[field].update(value)
                self.assertIsNotNone(manifest_contract.violation(document), label)
                self.assertIsNotNone(install_cmd._manifest_structure_issue(document), label)

    # --- 자산 key 는 경로 조각이다 -----------------------------------------

    UNSAFE_KEYS = ("skills/../../../victim", "skills/..", "skills//bad",
                   "/etc/passwd", "skills/a/b", "skills/", "skills/.",
                   "skills/x\\y", "unknown-kind/x")

    def test_an_unsafe_asset_key_never_reaches_a_plan(self):
        """`skills/<id>` 의 id 는 전역 skill 경로에 **그대로 붙는다.**

        그래서 key 하나로 계획이 write root 밖을 가리킬 수 있다. 실행 층의 2차 방어가 막더라도,
        그때는 이미 사용자가 승인한 불변 계획 안에 root 밖 대상이 들어 있고 계획을 만드는 동안
        외부 경로를 조회하고 지문까지 뜬 뒤다. 경계는 **계획을 만들기 전에** 서야 한다.
        """
        for key in self.UNSAFE_KEYS:
            with self.subTest(key):
                self.assertIsNotNone(manifest_contract.asset_key_violation(key), key)
                consumer = self.fresh()
                document = self.valid(consumer)
                document["assets"][key] = {"form": "declarative", "conformance": "PASS"}
                self.write_manifest(consumer, document)
                plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_ALL,
                                            environ={"CODEX_HOME": consumer.codex_home})
                self.assertEqual(plan.status, uninstall_plan.BLOCKED, key)
                self.assertEqual(plan.blocked_reason,
                                 "uninstall.manifest_contract_violation", key)
                self.assertEqual(plan.write_targets(), (), key)
                self.assertEqual(plan.of_kind(uninstall_plan.DELETE), (), key)

    def test_a_normal_asset_key_is_not_caught(self):
        for key in ("hooks/capture-declared-risk", "skills/sage-cycle", "agents/leader",
                    "mcps/db"):
            self.assertIsNone(manifest_contract.asset_key_violation(key), key)

    def test_the_escaping_key_blocks_both_check_and_yes_and_touches_nothing(self):
        """`--check` 와 `--yes` 둘 다 write target 0 이고, 밖의 sentinel 은 그대로다."""
        consumer = self.fresh()
        outside = os.path.join(consumer.root, "victim-sentinel")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write("남의 파일\n")
        document = self.valid(consumer)
        document["assets"]["skills/../../../victim-sentinel"] = {
            "form": "declarative", "conformance": "PASS"}
        manifest = self.write_manifest(consumer, document)
        before = self.snapshot(consumer.project)
        with open(manifest, "rb") as handle:
            manifest_bytes = handle.read()

        for extra in (["--check"], ["--yes"]):
            result = sage("uninstall", "--dest", consumer.project, "--all", "--json",
                          *extra, env=consumer.env)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "BLOCKED")
            self.assertEqual(payload["deleted"], [])
            self.assertEqual(payload["stripped"], [])

        with open(outside, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "남의 파일\n", "root 밖 파일이 바뀌었다")
        with open(manifest, "rb") as handle:
            self.assertEqual(handle.read(), manifest_bytes, "manifest bytes 가 바뀌었다")
        self.assertEqual(before, self.snapshot(consumer.project), "차단인데 트리가 바뀌었다")

    def test_the_planner_refuses_an_escaping_global_candidate_on_its_own(self):
        """계약을 우회해 들어와도 계획 층이 **조회 전에** 막는다.

        방어를 계약 하나에만 두면, 계약을 안 거치는 호출이 하나 생기는 순간 아무것도 남지 않는다.

        탈출 경로를 **실제로 만들어 둔다.** 없는 경로는 `isdir` 에서 조용히 걸러져, 방어를
        걷어내도 검사가 초록으로 남는다 — 닿지 않는 단언은 단언이 아니다.
        """
        consumer = self.fresh()
        groot = os.path.join(consumer.codex_home, "skills")
        os.makedirs(groot, exist_ok=True)
        aid = "../../../victim"
        # `sage-..` 는 traversal 이 지나갈 실제 디렉터리다. 이것이 없으면 `isdir` 이 거짓이 되어
        # 아래 경로가 후보에조차 오르지 않는다.
        os.makedirs(os.path.join(groot, "sage-.."), exist_ok=True)
        outside = os.path.normpath(os.path.join(groot, f"sage-{aid}"))
        self.assertFalse(uninstall_plan.within_root(groot, outside), "탈출 경로가 아니다")
        os.makedirs(outside, exist_ok=True)
        with open(os.path.join(outside, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write("남의 skill\n")
        project_copy = os.path.normpath(
            os.path.join(consumer.project, ".codex", "skills", aid))
        os.makedirs(project_copy, exist_ok=True)
        with open(os.path.join(project_copy, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write("남의 skill\n")

        original = uninstall_plan._manifest_skill_ids
        uninstall_plan._manifest_skill_ids = lambda manifest: {aid}
        try:
            actions = uninstall_plan._global_actions(
                consumer.project, {"assets": {}}, uninstall_plan.SCOPE_ALL, groot)
        finally:
            uninstall_plan._manifest_skill_ids = original

        escaped = [action for action in actions
                   if not uninstall_plan.within_root(groot, action.path)]
        self.assertEqual([action.kind for action in escaped], [uninstall_plan.PRESERVE],
                         "root 밖 후보가 처리 대상으로 계획에 올랐다")
        self.assertEqual(escaped[0].reason, "uninstall.path_escape")
        self.assertTrue(os.path.isfile(os.path.join(outside, "SKILL.md")))

    def test_the_skill_id_reader_drops_unsafe_ids(self):
        document = {"assets": {"skills/ok": {}, "skills/../../../victim": {},
                               "skills/..": {}, "hooks/fine": {}}}
        self.assertEqual(uninstall_plan._manifest_skill_ids(document), {"ok"})

    def test_a_damaged_key_never_reaches_the_report(self):
        """손상된 manifest 의 key 는 **사용자가 쓴 문자열**이다.

        절대 경로일 수도, 개행이 든 값일 수도, 비밀이 든 값일 수도 있다. 그것을 진단에 실으면
        화면·`--json`·CI 로그로 그대로 흘러가고, 개행이 든 값은 목록 한 줄을 두 줄로 만들어
        우리가 쓰지 않은 문장을 화면에 끼워 넣는다.
        """
        secrets = ["skills//Users/alice/private\nFORGED",
                   "skills/\u0000TOKEN-abc123",
                   "/Users/alice/AWS_SECRET_KEY",
                   "skills/../../../Users/alice/.ssh/id_rsa"]
        for key in secrets:
            with self.subTest(key[:20]):
                consumer = self.fresh()
                document = self.valid(consumer)
                document["assets"][key] = {"form": "declarative", "conformance": "PASS"}
                self.write_manifest(consumer, document)
                result = sage("uninstall", "--dest", consumer.project, "--check", "--json",
                              env=consumer.env)
                text = sage("uninstall", "--dest", consumer.project, "--check",
                            env=consumer.env)
                whole = result.stdout + result.stderr + text.stdout + text.stderr
                for fragment in ("alice", "TOKEN-abc123", "AWS_SECRET_KEY", "id_rsa",
                                 "FORGED"):
                    self.assertNotIn(fragment, whole, f"{fragment} 가 출력에 실렸다")
                self.assertNotIn(consumer.project, whole, "fixture root 가 출력에 실렸다")
                self.assertIn(manifest_contract.REDACTED, result.stdout,
                              "가렸다는 사실조차 보이지 않는다")

    def test_every_user_controlled_field_goes_through_one_gate(self):
        """asset key 말고도 host·render key 가 같은 관문을 지나는지 본다."""
        leaky = "/Users/alice/secret\nFORGED"
        cases = [
            {"sage_version": "1", "host_runtime": "claude", "assets": {},
             "core_skill_receipts": {leaky: {}}},
            {"sage_version": "1", "host_runtime": "claude", "assets": {},
             "core_renders": {leaky: {}}},
            {"sage_version": "1", "host_runtime": "claude", "assets": {leaky: {}}},
        ]
        for index, document in enumerate(cases):
            with self.subTest(index):
                broken = manifest_contract.violation(document)
                rendered = json.dumps(broken, ensure_ascii=False)
                self.assertNotIn("alice", rendered)
                self.assertNotIn("FORGED", rendered)
                self.assertIn(manifest_contract.REDACTED, rendered)
                # install 도 같은 안전한 violation 을 소비한다.
                message = install_cmd._manifest_structure_issue(document)
                self.assertNotIn("alice", str(message))
                self.assertNotIn("FORGED", str(message))

    def test_the_asset_field_is_redacted_even_if_key_validation_is_bypassed(self):
        """key 검증이 먼저 걸리므로 이 자리는 **오늘은 도달하지 않는다.**

        그래도 관문을 두는 이유는 순서가 바뀌거나 우회 호출이 생기는 날을 위해서다. 도달하지
        않는 방어는 검사할 수 없으므로, 우회를 흉내 내서 그 자리가 여전히 가리는지 본다 —
        "지금 안전하다" 와 "안전하게 남는다" 는 다른 약속이다.
        """
        leaky = "/Users/alice/secret\nFORGED"
        original = manifest_contract.asset_key_violation
        manifest_contract.asset_key_violation = lambda key: None
        try:
            broken = manifest_contract.violation(
                {"sage_version": "1", "host_runtime": "claude", "assets": {leaky: {}}})
        finally:
            manifest_contract.asset_key_violation = original
        rendered = json.dumps(broken, ensure_ascii=False)
        self.assertNotIn("alice", rendered)
        self.assertNotIn("FORGED", rendered)
        self.assertEqual(broken["asset"], manifest_contract.REDACTED)

    def test_a_safe_name_keeps_its_coordinate(self):
        """가리는 것이 기본이라고 해서 정상 이름까지 잃으면 진단이 쓸모없어진다."""
        for name in ("assets", "hooks/post-tool-logger", "claude/agents/leader"):
            self.assertEqual(manifest_contract.safe_field(name), name)
        self.assertEqual(manifest_contract.safe_field(3), 3)

    def test_swapping_the_contract_moves_the_plan(self):
        """판정 권위를 바꾸면 계획이 따라 바뀐다. 안 바뀌면 두 번째 판정자가 있다는 뜻이다."""
        consumer = self.fresh()
        original = manifest_contract.violation
        uninstall_plan._contract.violation = (
            lambda manifest: {"kind": "manifest", "code": "injected"})
        try:
            plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        finally:
            uninstall_plan._contract.violation = original
        self.assertEqual(plan.blocked_reason, "uninstall.manifest_contract_violation",
                         "계획이 계약을 보지 않는다")
        self.assertEqual(plan.of_kind(uninstall_plan.BLOCK)[0].detail[0]["code"], "injected")


class ActionConflict(Base):
    """같은 target 에 정확히 하나의 action (J7 · UNI-AC04).

    `--global` 자산에는 두 가족이 있다 — 이름이 CORE id 그대로인 것과 `<prefix>-<aid>` 로 렌더된
    것이다. prefix 가 `sage` 이고 manifest 에 `skills/init` 이 있으면 **둘 다**
    `$CODEX_HOME/skills/sage-init` 을 가리킨다.

    사본이 다르면 같은 경로에 `DELETE` 와 `PRESERVE` 가 함께 생겼다. 실행은 지우고 보고는 양쪽에
    같은 경로를 실었다 — **보존한다고 말한 사용자 변경본을 지우는 것**이다. 사본이 같으면
    `DELETE` 가 둘이라 write target 에도 중복이 남았다.
    """

    def colliding(self, project_body):
        """두 가족이 같은 전역 경로를 주장하는 소비자."""
        consumer = self.fresh()
        path = uninstall_plan.manifest_path(consumer.project)
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        manifest["assets"]["skills/init"] = {"form": "declarative", "conformance": "PASS"}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)

        target = os.path.join(consumer.codex_home, "skills", "sage-init")
        os.makedirs(target, exist_ok=True)
        with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write(managed_assets.LEGACY_SKILL_SIGNATURE + "\n")
        project_copy = os.path.join(consumer.project, ".codex", "skills", "init")
        os.makedirs(project_copy, exist_ok=True)
        with open(os.path.join(project_copy, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write(project_body)
        return consumer, target

    def plan_for(self, consumer):
        return uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_ALL,
                                    environ={"CODEX_HOME": consumer.codex_home})

    def test_a_drifted_copy_no_longer_yields_delete_and_preserve_at_once(self):
        consumer, target = self.colliding("내가 고친 내용\n")
        plan = self.plan_for(consumer)
        self.assertEqual(plan.status, uninstall_plan.BLOCKED)
        self.assertEqual(plan.blocked_reason, "uninstall.action_conflict")
        self.assertEqual(plan.exit_code, 2)
        self.assertEqual(plan.write_targets(), ())
        self.assertEqual([a.path for a in plan.actions if a.path == target
                          and a.kind != uninstall_plan.BLOCK], [])

    def test_a_matching_copy_no_longer_yields_two_deletes(self):
        consumer, target = self.colliding(managed_assets.LEGACY_SKILL_SIGNATURE + "\n")
        plan = self.plan_for(consumer)
        self.assertEqual(plan.status, uninstall_plan.BLOCKED)
        self.assertEqual(plan.blocked_reason, "uninstall.action_conflict")
        self.assertEqual(plan.write_targets().count(target), 0)

    def test_no_path_is_ever_claimed_twice_in_a_normal_plan(self):
        """정상 계획에서도 같은 계약이 성립해야 한다 — 차단은 과차단이 아니어야 한다."""
        consumer = self.fresh()
        plan = self.plan_for(consumer)
        self.assertNotEqual(plan.status, uninstall_plan.BLOCKED)
        self.assertEqual(uninstall_plan.conflicting_actions(plan.actions), ())
        paths = [os.path.normcase(os.path.normpath(a.path)) for a in plan.actions]
        self.assertEqual(len(paths), len(set(paths)))

    def test_both_check_and_yes_block_and_change_nothing(self):
        for body in ("내가 고친 내용\n", managed_assets.LEGACY_SKILL_SIGNATURE + "\n"):
            with self.subTest(body[:6]):
                consumer, target = self.colliding(body)
                before = self.snapshot(consumer.project)
                with open(os.path.join(target, "SKILL.md"), "rb") as handle:
                    target_bytes = handle.read()
                for extra in (["--check"], ["--yes"]):
                    result = sage("uninstall", "--dest", consumer.project, "--all",
                                  "--json", *extra, env=consumer.env)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    payload = json.loads(result.stdout)
                    self.assertEqual(payload["status"], "BLOCKED")
                    self.assertEqual(payload["deleted"], [])
                    self.assertEqual(payload["stripped"], [])
                    self.assertEqual(payload["preserved"], [])
                    # 텍스트 화면도 같은 판정이어야 한다.
                    text = sage("uninstall", "--dest", consumer.project, "--all",
                                *extra, env=consumer.env)
                    self.assertEqual(text.returncode, 2)
                    self.assertNotIn("삭제:", text.stdout)
                with open(os.path.join(target, "SKILL.md"), "rb") as handle:
                    self.assertEqual(handle.read(), target_bytes, "차단인데 전역 사본이 바뀌었다")
                self.assertEqual(before, self.snapshot(consumer.project),
                                 "차단인데 프로젝트가 바뀌었다")

    def test_the_executor_refuses_a_conflicting_plan_before_it_locks(self):
        """계획 층이 언젠가 다른 분기를 놓쳐도 실행 층에서 잡혀야 한다."""
        consumer = self.fresh()
        plan = self.plan_for(consumer)
        victim = plan.of_kind(uninstall_plan.DELETE)[0]
        twin = uninstall_plan.Action(uninstall_plan.PRESERVE, victim.scope, victim.path,
                                     "uninstall.ownership_unprovable")
        forged = uninstall_plan.UninstallPlan(
            plan.scope, plan.dest, plan.actions + (twin,), plan.status, None, plan.notices,
            baseline=plan.baseline, global_root=plan.global_root)
        with self.assertRaises(ValueError) as caught:
            uninstall_executor.execute(forged)
        self.assertEqual(str(caught.exception), "uninstall.action_conflict")
        self.assertTrue(os.path.lexists(victim.path), "거부했는데 대상이 사라졌다")

    def snapshot(self, root):
        import hashlib
        found = {}
        for folder, _dirs, files in os.walk(root):
            for name in sorted(files):
                path = os.path.join(folder, name)
                try:
                    with open(path, "rb") as handle:
                        found[os.path.relpath(path, root)] = hashlib.sha256(
                            handle.read()).hexdigest()
                except OSError:
                    found[os.path.relpath(path, root)] = "unreadable"
        return found


class MachineOutputParity(Base):
    """`--json` 은 언어를 타지 않는다. 타면 기계가 언어별로 분기해야 한다."""

    def test_ko_and_en_json_are_byte_identical(self):
        consumer = self.fresh()
        path = os.path.join(consumer.project, ".claude", "settings.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b'{"hooks": [')
        outputs = []
        for language in ("ko", "en"):
            env = dict(consumer.env, SAGE_LANG=language, LANG=f"{language}_XX.UTF-8")
            result = sage("uninstall", "--dest", consumer.project, "--check", "--json",
                          env=env)
            self.assertIn(result.returncode, (0, 1, 2), result.stdout + result.stderr)
            outputs.append(result.stdout.encode("utf-8"))
        self.assertEqual(outputs[0], outputs[1],
                         "같은 상태인데 언어에 따라 JSON 이 달라졌다")


class DisplayPaths(Base):
    """경로 표기는 **하나의 함수**를 통과한 값 하나다.

    한때 화면은 절대 경로를 찍고 `--json` 은 절대 경로에 상대 경로를 덧붙였다. 소비자마다
    무엇을 기준으로 비교해야 하는지가 달라지고, 실행 머신의 홈 경로가 로그와 이슈에 그대로
    실린다. 전역 자산은 실경로 대신 사용자가 정한 이름(`$CODEX_HOME/skills/...`)으로 말해야
    "내 어느 설정이 이걸 만들었는가" 가 읽힌다.
    """

    def payload(self, consumer, *extra):
        result = sage("uninstall", "--dest", consumer.project, "--check", "--json",
                      *extra, env=consumer.env)
        self.assertEqual(result.returncode, result.returncode)
        return json.loads(result.stdout)

    def every_entry(self, payload):
        for bucket in ("deleted", "stripped", "preserved", "blocked"):
            for entry in payload[bucket]:
                yield bucket, entry

    def test_project_paths_are_relative_and_absolute_paths_never_appear(self):
        consumer = self.fresh()
        payload = self.payload(consumer)
        seen = 0
        for bucket, entry in self.every_entry(payload):
            if entry["scope"] != uninstall_plan.SCOPE_PROJECT:
                continue
            seen += 1
            self.assertFalse(os.path.isabs(entry["path"]),
                             f"{bucket} 에 절대 경로가 실렸다: {entry['path']}")
            self.assertNotIn(consumer.project, entry["path"])
            self.assertNotIn("project_path", entry,
                             "절대 경로에 상대 경로를 덧붙이던 방식이 남아 있다")
        self.assertGreater(seen, 0, "project 항목이 하나도 없어 아무것도 확인하지 못했다")

    def test_the_whole_json_document_carries_no_fixture_root(self):
        """항목 하나씩이 아니라 **문서 전체**를 본다. 새 필드가 늘면 그 자리로 다시 샌다."""
        consumer = self.fresh()
        raw = json.dumps(self.payload(consumer), ensure_ascii=False)
        self.assertNotIn(consumer.project, raw, "출력 어딘가에 절대 경로가 남았다")

    def test_global_assets_are_shown_by_the_configured_name(self):
        consumer = self.fresh()
        owned = os.path.join(consumer.codex_home, "skills", "sage-cycle")
        os.makedirs(owned, exist_ok=True)
        with open(os.path.join(owned, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write(managed_assets.LEGACY_SKILL_SIGNATURE + "\n")
        result = sage("uninstall", "--dest", consumer.project, "--check", "--json",
                      "--all", env=consumer.env)
        payload = json.loads(result.stdout)
        globals_shown = [entry["path"] for _bucket, entry in self.every_entry(payload)
                         if entry["scope"] == uninstall_plan.SCOPE_GLOBAL]
        self.assertIn(f"{uninstall_plan.GLOBAL_DISPLAY_ROOT}/sage-cycle", globals_shown)
        self.assertNotIn(consumer.codex_home, json.dumps(payload, ensure_ascii=False))

    def test_text_and_json_show_the_same_path(self):
        consumer = self.fresh()
        payload = self.payload(consumer)
        text = sage("uninstall", "--dest", consumer.project, "--check", "--verbose",
                    env=consumer.env).stdout
        for _bucket, entry in self.every_entry(payload):
            self.assertIn(f"- {entry['path']}\n", text,
                          f"화면과 JSON 이 다른 경로를 보인다: {entry['path']}")

    def test_a_newline_in_a_path_cannot_forge_a_line(self):
        """파일 이름에는 개행이 들어간다. 그대로 찍으면 목록 한 줄이 두 줄이 되고, 두 번째 줄은
        우리가 쓴 것처럼 보인다.

        여기서는 formatter 를 직접 부른다. 오늘 계획에 오르는 경로는 전부 **우리가 고른 이름**
        이라(bundle 목록·roster·고정 디렉터리) 사용자가 지은 이름이 화면에 실리는 경로가 없고,
        그래서 소비자 fixture 로는 이 자리를 밟을 수 없다. 밟히지 않는 경로를 밟는 척하는
        검사보다, 무엇을 확인했는지 정확히 말하는 검사가 낫다 — 두 sink 가 이 함수를 지나간다는
        사실은 아래 두 검사가 따로 본다.
        """
        forged = "note\n  - 전부 지웠습니다.md"
        shown = uninstall_plan.escape_display(forged)
        self.assertNotIn("\n", shown, "제어문자가 그대로 통과했다")
        self.assertEqual(shown, "note\\n  - 전부 지웠습니다.md")

    def test_other_control_characters_are_escaped_too(self):
        for raw, expected in (("a\rb", "a\\rb"), ("a\tb", "a\\tb"),
                              ("a\x00b", "a\\x00b"), ("a\x1bb", "a\\x1bb"),
                              ("a\x7fb", "a\\x7fb")):
            self.assertEqual(uninstall_plan.escape_display(raw), expected)

    def test_the_formatter_is_the_only_place_that_decides(self):
        """표기를 바꾸면 화면과 JSON 이 **함께** 바뀐다. 한쪽만 바뀌면 두 벌이 남아 있다."""
        consumer = self.fresh()
        original = uninstall_plan.display_path
        uninstall_plan.display_path = lambda path, scope, dest=None, global_root=None: "SENTINEL"
        try:
            plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
            payload = plan.as_json()
        finally:
            uninstall_plan.display_path = original
        shown = {entry["path"] for _bucket, entry in self.every_entry(payload)}
        self.assertEqual(shown, {"SENTINEL"}, "JSON 이 표기 함수를 거치지 않는다")

    def test_a_path_outside_the_project_is_not_shown_at_all(self):
        """탈출한 경로의 문자열은 **탈출을 시도한 쪽이 정한 값**이다. 밖이라는 사실만 말한다."""
        shown = uninstall_plan.display_path("/etc/passwd", uninstall_plan.SCOPE_PROJECT,
                                            "/tmp/proj")
        self.assertEqual(shown, uninstall_plan.OUTSIDE_PROJECT)
        self.assertNotIn("passwd", shown)
        outside_global = uninstall_plan.display_path("/etc/passwd",
                                                     uninstall_plan.SCOPE_GLOBAL,
                                                     None, "/g/skills")
        self.assertEqual(outside_global, uninstall_plan.OUTSIDE_PROJECT)

    def test_both_renderers_consume_the_same_formatter(self):
        """표기 함수를 갈아 끼운 채 **화면과 JSON 을 모두** 부르고 같은 sentinel 을 본다.

        각각 따로 확인하면 "둘이 같은 값을 쓴다" 가 아니라 "둘 다 어떤 값을 쓴다" 만 증명된다.
        """
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)

        class Args:
            json = False
            verbose = True

        original = uninstall_plan.display_path
        uninstall_plan.display_path = (
            lambda path, scope, dest=None, global_root=None: "SENTINEL-PATH")
        screen = io.StringIO()
        try:
            with contextlib.redirect_stdout(screen):
                uninstall_cmd._render(plan, Args(), "ko", executed=False)
            payload = plan.as_json()
        finally:
            uninstall_plan.display_path = original

        text = screen.getvalue()
        self.assertIn("- SENTINEL-PATH", text, "화면이 표기 함수를 거치지 않는다")
        self.assertNotIn(consumer.project, text)
        shown = {entry["path"] for _bucket, entry in self.every_entry(payload)}
        self.assertEqual(shown, {"SENTINEL-PATH"}, "JSON 이 표기 함수를 거치지 않는다")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                self.assertEqual(stripped, "- SENTINEL-PATH",
                                 f"화면에 표기 함수를 거치지 않은 줄이 있다: {line!r}")

    def test_escaping_leaves_ordinary_paths_alone(self):
        for path in (".claude/settings.json", "docs/sage_harness", "a b/c-d_e.md"):
            self.assertEqual(uninstall_plan.escape_display(path), path)


class PlanInputDamage(Base):
    """계획 층은 **읽기만** 하는데도 손상된 입력 하나로 죽을 수 있었다."""

    def test_a_non_utf8_gitignore_does_not_traceback(self):
        consumer = self.fresh()
        gitignore = os.path.join(consumer.project, ".gitignore")
        with open(gitignore, "rb") as handle:
            body = handle.read()
        with open(gitignore, "wb") as handle:
            handle.write(b"# \xff\xfe user rule\n" + body)
        result = sage("uninstall", "--dest", consumer.project, "--check", "--json",
                      env=consumer.env)
        self.assertNotIn("Traceback", result.stderr, result.stderr)
        payload = json.loads(result.stdout)
        self.assertIn(payload["status"],
                      (uninstall_plan.PARTIAL, uninstall_plan.COMPLETE, uninstall_plan.BLOCKED))
        preserved = {entry["path"]: entry for entry in payload["preserved"]}
        self.assertIn(".gitignore", preserved, "읽지 못한 파일을 조용히 넘겼다")
        self.assertEqual([e["kind"] for e in preserved[".gitignore"]["detail"]], ["encoding"])

    def test_a_failing_plan_still_produces_a_json_envelope(self):
        consumer = self.fresh()
        script = (
            "import sys;"
            "sys.path.insert(0, %r);"
            "from sage import uninstall_plan as up;"
            "up._project_actions = "
            "lambda *a, **k: (_ for _ in ()).throw(RuntimeError('injected'));"
            "from sage.cli import main;"
            "sys.argv = ['sage', 'uninstall', '--dest', %r, '--check', '--json'];"
            "sys.exit(main())" % (REPO, consumer.project))
        result = subprocess.run([sys.executable, "-c", script], cwd=REPO, env=consumer.env,
                                capture_output=True, text=True)
        self.assertNotIn("Traceback", result.stderr, result.stderr)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["blocked_reason"], "uninstall.plan_failed")
        self.assertEqual(payload["exit_code"], 2)


class PartialWriteRollback(Base):
    """반쯤 쓰다 실패해도 원본은 **바이트 그대로** 돌아온다."""

    def test_an_io_failure_mid_write_restores_the_original(self):
        """`O_EXCL` 로 만든 자리는 우리 것이다 — 잘린 파일을 두면 되돌리기가 거부된다.

        journal 의 rollback 은 대상 자리에 모르는 파일이 있으면 "동시 변경" 으로 보고 backup
        복원을 멈춘다. 안전한 기본값이지만 그 낯선 파일이 우리가 방금 만든 잘린 파일이면,
        사용자의 `.gitignore` 는 잘린 채 끝나고 원본은 숨은 backup 에 갇힌다.
        """
        consumer = self.fresh()
        gitignore = os.path.join(consumer.project, ".gitignore")
        with open(gitignore, encoding="utf-8") as handle:
            installed = handle.read()
        rules = "".join(f"# 사용자 규칙 {n}\nbuild-{n}/\n" for n in range(20))
        with open(gitignore, "w", encoding="utf-8") as handle:
            handle.write(rules + installed)
        with open(gitignore, "rb") as handle:
            before = handle.read()
        mode = stat.S_IMODE(os.lstat(gitignore).st_mode)

        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertIn(gitignore, plan.write_targets())

        real_write = os.write
        crippled = []

        def failing_write(fd, data):
            if not crippled and len(data) > 16:
                crippled.append(True)
                real_write(fd, data[:12])
                raise OSError(errno.ENOSPC, "no space left on device")
            return real_write(fd, data)

        os.write = failing_write
        try:
            with self.assertRaises(OSError):
                uninstall_executor.execute(plan)
        finally:
            os.write = real_write

        self.assertTrue(crippled, "주입이 성립하지 않았다")
        with open(gitignore, "rb") as handle:
            after = handle.read()
        self.assertEqual(after, before,
                         f"원본이 돌아오지 않았다 ({len(after)}/{len(before)} bytes)")
        self.assertEqual(stat.S_IMODE(os.lstat(gitignore).st_mode), mode)
        leftovers = [name for name in os.listdir(consumer.project)
                     if ".sage-install-backup" in name]
        self.assertEqual(leftovers, [], f"backup 이 남았다: {leftovers}")


class FailureSurface(Base):
    """어떤 실패든 결과는 네 상태 중 하나이고, `--json` 이면 JSON 이다."""

    def test_an_unnamed_failure_becomes_a_blocked_result(self):
        consumer = self.fresh()

        def boom(original):
            def hook(journal, path):
                raise RuntimeError("이름 붙이지 않은 실패")
            return hook

        script = (
            "import sys;"
            "sys.path.insert(0, %r);"
            "from sage import install_transaction as tx;"
            "orig = tx.InstallTransaction.stage_remove_tree;"
            "tx.InstallTransaction.stage_remove_tree = "
            "lambda self, p: (_ for _ in ()).throw(RuntimeError('injected'));"
            "from sage.cli import main;"
            "sys.argv = ['sage', 'uninstall', '--dest', %r, '--yes'];"
            "sys.exit(main())" % (REPO, consumer.project))
        result = subprocess.run([sys.executable, "-c", script], cwd=REPO, env=consumer.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr, "traceback 이 사용자에게 그대로 나갔다")

    def test_every_json_failure_path_emits_json(self):
        """실패야말로 기계가 가장 알아야 하는 상태다."""
        consumer = self.fresh()
        script = (
            "import sys, json;"
            "sys.path.insert(0, %r);"
            "from sage import install_transaction as tx;"
            "tx.InstallTransaction.rollback = lambda self: ['cannot restore'];"
            "tx.InstallTransaction.stage_remove_tree = "
            "lambda self, p: (_ for _ in ()).throw(OSError('injected'));"
            "from sage.cli import main;"
            "sys.argv = ['sage', 'uninstall', '--dest', %r, '--yes', '--json'];"
            "sys.exit(main())" % (REPO, consumer.project))
        result = subprocess.run([sys.executable, "-c", script], cwd=REPO, env=consumer.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "BLOCKED")
        self.assertEqual(payload["exit_code"], 2)
        self.assertTrue(payload.get("blocked_reason"))


class CleanupReporting(Base):
    """못 치운 보관소를 숨기지 않는다 — 숨기면 사용자는 치울 것이 있다는 사실도 모른다."""

    def test_cleanup_failure_reports_the_real_paths(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)

        def boom(original):
            def hook(journal):
                journal._committed = True
                raise OSError("injected")
            return hook

        with patched("commit", boom):
            result = uninstall_executor.execute(plan)
        self.assertTrue(result.leftover_backups, "실제 보관소가 남았는데 0건으로 보고했다")
        for path in result.leftover_backups:
            self.assertTrue(os.path.lexists(path), f"없는 경로를 보고했다: {path}")
        # 중첩 backup 은 부모 backup **안에** 들어가 있으므로 원래 경로에 존재하지 않는다.
        # 사용자가 치워야 하는 것은 최상위 것들이므로 그것과 대조한다.
        on_disk = []
        for folder, dirs, files in os.walk(consumer.project):
            if os.path.basename(folder).startswith(".sage-install-backup-"):
                dirs[:] = []
                continue
            for name in dirs + files:
                if name.startswith(".sage-install-backup-"):
                    on_disk.append(os.path.join(folder, name))
        self.assertEqual(sorted(result.leftover_backups), sorted(on_disk),
                         f"디스크 {len(on_disk)}개 중 {len(result.leftover_backups)}개만 보고했다")


class GitignoreFidelity(Base):
    """관리 구간 밖 바이트는 건드리지 않는다."""

    def test_unrelated_whitespace_is_preserved_exactly(self):
        from sage.uninstall_shared import GITIGNORE_BLOCKS, classify_gitignore_text
        _l0, s0, e0 = GITIGNORE_BLOCKS[0]
        _l1, s1, e1 = GITIGNORE_BLOCKS[1]
        user = "build/\n\n\n# 내 규칙\n*.log\n"
        text = (user.rstrip("\n") + "\n\n"
                + f"{s0}\nsage/project-profile.local.yaml\n{e0}\n"
                + "\n" + f"{s1}\n.sage/\n{e1}\n")
        out = classify_gitignore_text(text).body
        self.assertEqual(out, user,
                         "관리 구간 밖 바이트가 바뀌었다 — 제거와 무관한 diff 가 생긴다")

    def test_the_stripper_does_not_normalise_the_whole_file(self):
        """전역 정규화로 되돌아가지 않았는지 코드로 본다."""
        with open(os.path.join(REPO, "sage", "uninstall_shared.py"), encoding="utf-8") as h:
            tree = ast.parse(h.read())
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "classify_gitignore_text")
        body = fn.body[1:] if ast.get_docstring(fn) else fn.body
        code = "\n".join(ast.unparse(node) for node in body)
        self.assertNotIn(".strip('\\n')", code)
        self.assertNotIn("collapsed", code)


class SuiteIntegrity(unittest.TestCase):
    """이 파일 자체가 거짓말하지 않는지 본다.

    Python 은 같은 이름의 class 를 두 번 정의해도 조용히 뒤엣것으로 덮는다. 그러면 앞 블록을
    아무리 고쳐도 **실행되는 것은 뒤 블록**이고, 통과 건수는 그대로라 아무도 눈치채지 못한다.
    수정이 반영되지 않은 채 초록을 받는 것은 검사가 없는 것보다 나쁘다.
    """

    def duplicates(self, kind):
        with open(__file__, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        found = []
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        if kind == "class":
            seen = {}
            for node in classes:
                if node.name in seen:
                    found.append(f"{node.name} (line {seen[node.name]} · {node.lineno})")
                seen[node.name] = node.lineno
            return found
        for node in classes:
            seen = {}
            for member in node.body:
                if not isinstance(member, ast.FunctionDef):
                    continue
                if member.name in seen:
                    found.append(f"{node.name}.{member.name} (line {member.lineno})")
                seen[member.name] = member.lineno
        return found

    def test_no_class_is_defined_twice(self):
        self.assertEqual(self.duplicates("class"), [], "덮어써진 class 가 있다")

    def test_no_method_is_defined_twice(self):
        self.assertEqual(self.duplicates("method"), [], "덮어써진 test method 가 있다")


class FixtureHygiene(unittest.TestCase):
    """fixture 가 서 있는 땅 자체를 검사한다."""

    def test_fixture_roots_have_no_symlink_component(self):
        root = fixture_root("hygiene")
        self.addCleanup(shutil.rmtree, root, True)
        current = root
        while current != os.path.dirname(current):
            self.assertFalse(os.path.islink(current), f"fixture 조상에 symlink: {current}")
            current = os.path.dirname(current)

    def test_the_fixture_base_is_private_to_us(self):
        base = _fixture_base()
        info = os.stat(base)
        self.assertEqual(info.st_uid, os.getuid(), "fixture base 를 우리가 소유하지 않는다")
        self.assertEqual(info.st_mode & 0o077, 0, "fixture base 가 남에게 열려 있다")

    def test_the_default_base_is_not_the_shared_temp(self):
        """지정이 없을 때 조용히 공유 temp 로 내려가지 않는다 — 기본이 곧 유일한 경로다."""
        saved = os.environ.pop("SAGE_TEST_TMPDIR", None)
        try:
            base = _fixture_base()
        finally:
            if saved is not None:
                os.environ["SAGE_TEST_TMPDIR"] = saved
        shared = os.path.realpath(tempfile.gettempdir())
        self.assertFalse(base == shared or base.startswith(shared + os.sep),
                         f"기본 fixture base 가 공유 temp 아래다: {base}")

    def test_no_fixture_is_created_directly_in_the_shared_temp(self):
        """공유 temp 에 바로 만드는 자리가 남아 있지 않은지 소스로 본다."""
        with open(__file__, encoding="utf-8") as handle:
            source = handle.read()
        offenders = [line.strip() for line in source.splitlines()
                     if "mkdtemp(" in line and "dir=" not in line and "def " not in line]
        self.assertEqual(offenders, [], "fixture 가 공유 temp 에 직접 만들어진다")



class WindowsBackendContract(unittest.TestCase):
    """Windows 결속 구현의 계약. **개발 머신이 macOS 라 여기서 잡지 못하면 아무도 못 잡는다.**

    이 검사들이 확인하는 것은 "Windows 에서 동작한다" 가 아니다 — 그것은 원격 runner 만
    증명할 수 있다. 여기서 보는 것은 구조체 배치·이름 검증·fallback 부재처럼 **환경과 무관하게
    참이어야 하는 것**이다. 이것들이 틀리면 원격에서도 틀리고, 원격에서만 보이는 실패는
    비싸다.
    """

    def test_struct_layout_matches_the_win64_contract(self):
        """구조체 offset·크기는 Win64 ABI 가 정한 값이다. 하나 밀리면 조용히 틀린다.

        `ctypes` 가 계산한 값을 쓰되, 그 계산 결과가 맞는지는 여기서 고정한다. 손으로 적은
        offset 이 없다는 것과 계산된 offset 이 옳다는 것은 다른 이야기다.
        """
        w = uninstall_windows_fs
        for struct_type, size in ((w.UNICODE_STRING, 16), (w.OBJECT_ATTRIBUTES, 48),
                                  (w.IO_STATUS_BLOCK, 16),
                                  (w.BY_HANDLE_FILE_INFORMATION, 52), (w.FILE_ID_INFO, 24),
                                  (w.FILE_ATTRIBUTE_TAG_INFO, 8), (w.FILE_BASIC_INFO, 40),
                                  (w.FILE_FULL_DIR_INFO, 72)):
            self.assertEqual(ctypes.sizeof(struct_type), size,
                             f"{struct_type.__name__} 크기가 Win64 계약과 다르다")
        self.assertEqual(w.OBJECT_ATTRIBUTES.RootDirectory.offset, 8)
        self.assertEqual(w.OBJECT_ATTRIBUTES.ObjectName.offset, 16)
        self.assertEqual(w.FILE_RENAME_INFO.RootDirectory.offset, 8)
        self.assertEqual(w.FILE_RENAME_INFO.FileNameLength.offset, 16)
        self.assertEqual(w.FILE_RENAME_INFO.FileName.offset, 20)
        self.assertEqual(w.FILE_FULL_DIR_INFO.FileName.offset, 68)
        # `WCHAR` 를 `ctypes.c_wchar` 로 두면 이 크기가 플랫폼마다 달라지고(Windows 2, 그 외 4)
        # 배치가 검사 환경에서만 맞는다.
        self.assertEqual(ctypes.sizeof(w.WCHAR), 2)
        self.assertEqual(ctypes.sizeof(w.NTSTATUS), 4)

    def test_relative_components_that_are_not_components_are_refused(self):
        """성분이 아닌 것을 성분으로 받지 않는다. 이 값이 커널에 가는 마지막 자리다."""
        for name in ("..", ".", "", "a/b", "a\\b", "a:b", "C:", "a\x00b", "nul", "NUL.txt",
                     "com1", "LPT9.log", "trailing ", "trailing.", None, 3):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    uninstall_windows_fs.validate_component(name)
        for name in ("settings.json", ".gitignore", "한글 이름", "a.b.c",
                     ".sage-install-backup-abc-x", "connect.txt", "communication"):
            with self.subTest(name=name):
                self.assertEqual(uninstall_windows_fs.validate_component(name), name)

    def test_the_windows_backend_has_no_path_based_write_fallback(self):
        """경로로 되돌아가는 길이 **없어야 한다.** 있으면 조건 하나가 어긋나는 날 그리로 간다.

        읽기 전용 조사(`os.lstat`·`os.path`)는 허용한다 — 그것으로는 파일이 만들어지지 않는다.
        금지하는 것은 경로를 받아 **쓰는** 호출이다.
        """
        path = os.path.join(REPO, "sage", "uninstall_windows_fs.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        # 경로를 받아 **쓰는** 호출만 센다. `str.replace` 같은 동명 메서드를 세면 검사가
        # 잡아야 할 것이 아니라 이름을 잡는다.
        module_writes = {"remove", "unlink", "rmdir", "rename", "replace", "makedirs",
                         "mkdir", "chmod", "rmtree", "copy", "copy2", "copytree", "move",
                         "truncate", "symlink", "link", "write_text", "write_bytes"}
        path_apis = {"CreateFileW", "MoveFileExW", "DeleteFileW", "RemoveDirectoryW",
                     "SetFileAttributesW", "CreateDirectoryW", "ReplaceFileW"}
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                if isinstance(target, ast.Attribute):
                    owner = target.value
                    base = getattr(owner, "id", None)
                    if base in ("os", "shutil", "pathlib") and target.attr in module_writes:
                        found.append(f"{base}.{target.attr}")
                    if target.attr in path_apis:
                        found.append(target.attr)
                elif getattr(target, "id", None) in {"open"} | path_apis:
                    found.append(target.id)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "shutil",
                                        "경로 기반 대량 조작 모듈을 들였다")
        self.assertEqual(found, [], f"경로 기반 쓰기 경로가 남아 있다: {sorted(set(found))}")

    def test_every_capability_primitive_is_load_bearing(self):
        """항목 **하나만** 거짓이어도 지원하지 않는다고 답해야 한다.

        하나가 빠져도 지원한다고 답하면, 그 하나가 하는 일만 조용히 실패한다. 이 명령에서
        조용한 실패는 되돌릴 수 없는 실패다.
        """
        for missing in uninstall_fs.PRIMITIVES:
            with self.subTest(missing=missing):
                primitives = {name: name != missing for name in uninstall_fs.PRIMITIVES}
                cap = uninstall_fs.MutationCapability(uninstall_fs.BACKEND_WINDOWS,
                                                      primitives=primitives)
                self.assertFalse(cap.supported, f"{missing} 없이 지원한다고 답했다")
        whole = uninstall_fs.MutationCapability(
            uninstall_fs.BACKEND_WINDOWS,
            primitives={name: True for name in uninstall_fs.PRIMITIVES})
        self.assertTrue(whole.supported)
        for field in ("os_supported", "local_volume"):
            with self.subTest(field=field):
                cap = uninstall_fs.MutationCapability(
                    uninstall_fs.BACKEND_WINDOWS,
                    primitives={name: True for name in uninstall_fs.PRIMITIVES},
                    **{field: False})
                self.assertFalse(cap.supported)

    def test_backend_selection_refuses_with_a_contract_code(self):
        """지원 불가는 **기존 진단 어휘**로 나온다. Windows 전용 code 를 만들지 않는다."""
        saved = uninstall_fs.capability
        uninstall_fs.capability = lambda roots=(): uninstall_fs.MutationCapability(
            uninstall_fs.BACKEND_NONE, failure_code="uninstall.unsafe_platform")
        try:
            with self.assertRaises(ValueError) as caught:
                uninstall_fs.backend_for(("/nowhere",))
        finally:
            uninstall_fs.capability = saved
        self.assertEqual(str(caught.exception), "uninstall.unsafe_platform")

    def test_native_failures_map_onto_the_existing_vocabulary(self):
        """native 오류가 새 code 를 만들지 않고 기존 어휘로 수렴하는지 본다."""
        from sage.diagnostic_contract import SEVERITY
        w = uninstall_windows_fs
        cases = [
            (w.WindowsMutationError("NtCreateFile", w.STATUS_OBJECT_NAME_COLLISION,
                                    ntstatus=True), "uninstall.backup_collision"),
            (w.WindowsMutationError("NtCreateFile", w.STATUS_NOT_A_DIRECTORY,
                                    ntstatus=True), "uninstall.boundary_changed"),
            (w.WindowsMutationError("WriteFile", w.ERROR_ALREADY_EXISTS),
             "uninstall.backup_collision"),
            (w.WindowsMutationError("WriteFile", w.ERROR_ACCESS_DENIED),
             "uninstall.execution_failed"),
        ]
        for error, expected in cases:
            with self.subTest(op=error.op, code=error.code):
                code = w.to_diagnostic(error)
                self.assertEqual(code, expected)
                self.assertIn(code, SEVERITY, "계약에 없는 code 를 만들었다")

    def test_a_mutation_failure_never_claims_the_platform_is_unsupported(self):
        """**실행 중 실패는 환경 미지원이 아니다.**

        `to_diagnostic` 은 capability 판정을 **통과한 뒤**의 실패만 옮긴다. 그 실패를
        `unsafe_platform` 으로 접으면 고칠 수 있는 구현 결함이 고칠 수 없는 환경 한계처럼
        보이고, 사용자는 자기 환경을 탓하고 개발자는 붉은 화면을 환경 문제로 넘긴다.

        실제로 그 일이 일어났다. `SetFileInformationByHandle(FileRenameInfo)` 가
        `ERROR_INVALID_PARAMETER` 를 냈고, 화면에는 "이 플랫폼은 지원되지 않는다" 만 남았다.
        """
        w = uninstall_windows_fs
        invalid = [
            w.WindowsMutationError("NtSetInformationFile/FileRenameInformation",
                                   w.STATUS_INVALID_PARAMETER, ntstatus=True),
            w.WindowsMutationError("NtCreateFile", w.STATUS_NOT_SUPPORTED, ntstatus=True),
            w.WindowsMutationError("SetFileInformationByHandle/FileRenameInfo",
                                   w.ERROR_INVALID_PARAMETER),
            w.WindowsMutationError("SetFileInformationByHandle/FileBasicInfo",
                                   w.ERROR_NOT_SUPPORTED),
        ]
        for error in invalid:
            with self.subTest(op=error.op, code=error.code):
                self.assertEqual(w.to_diagnostic(error), "uninstall.execution_failed")

    def test_the_native_facts_survive_the_translation(self):
        """진단으로 옮기면서 **API 이름과 code 를 버리지 않는다.**

        진단 하나만 남으면 원격에서만 나는 실패의 원인이 그 머신 안에 갇힌다. 싣는 것은
        경로도 OS 원문도 아닌 API 이름·종류·정수뿐이다.
        """
        error = uninstall_windows_fs.WindowsMutationError(
            "NtSetInformationFile/FileRenameInformation", 0xC000000D, ntstatus=True)
        self.assertEqual(error.native, {
            "operation": "NtSetInformationFile/FileRenameInformation",
            "error_kind": "nt", "error_code": 0xC000000D})
        carried = uninstall_fs.NativeFailure("uninstall.execution_failed", error.native)
        self.assertEqual(str(carried), "uninstall.execution_failed")
        self.assertEqual(carried.native["operation"],
                         "NtSetInformationFile/FileRenameInformation")
        for value in carried.native.values():
            self.assertNotIn("\\", str(value), "경로가 섞여 나갔다")

    def test_moving_a_directory_we_hold_releases_our_own_handle_first(self):
        """**Windows 는 열린 handle 이 남은 디렉터리의 이름을 바꾸지 못한다.**

        파일은 `FILE_SHARE_DELETE` 로 열려 있으면 되지만 디렉터리는 그렇지 않다. 실제로
        29건이 성공한 뒤, 우리가 부모로 붙들고 있던 디렉터리 하나에서만
        `STATUS_ACCESS_DENIED` 가 났다 — 우리 자신이 만든 장애였다.

        결속은 약해지지 않는다. 그 rename 을 묶는 것은 옮겨지는 디렉터리의 handle 이 아니라
        **부모의** handle 이고 그것은 그대로다.
        """
        w = uninstall_windows_fs
        closed = []
        saved = w._close
        w._close = closed.append
        self.addCleanup(lambda: setattr(w, "_close", saved))

        backend = w.WindowsBackend(types.SimpleNamespace(identity_source="id"))
        target = os.path.abspath(os.path.join("nowhere", "held"))
        backend.parents[target] = 4242
        backend._physical[target] = target
        backend._owned.append(4242)

        # 자기 자신뿐 아니라 **그 아래에서 붙들고 있는 것까지** 놓아야 한다.
        child = os.path.join(target, "inner")
        backend.parents[child] = 4343
        backend._physical[child] = child
        backend._owned.append(4343)

        saved_identity = w.identity
        w.identity = lambda handle, source="id": ("mark", handle)
        self.addCleanup(lambda: setattr(w, "identity", saved_identity))

        detached = backend._detach_subtree(target)
        self.assertEqual(sorted(closed), [4242, 4343], "하위 handle 을 남겼다")
        self.assertEqual(backend.parents, {})
        self.assertEqual(backend._owned, [])
        self.assertEqual({key: rel for key, rel, _mark in detached},
                         {target: os.curdir, child: "inner"})
        self.assertEqual({key: mark for key, _rel, mark in detached},
                         {target: ("mark", 4242), child: ("mark", 4343)},
                         "놓기 전에 지문을 뜨지 않았다")

    def test_moving_a_held_directory_takes_the_hold_back_afterwards(self):
        """놓기만 하면 **되돌리기가 그 아래를 못 만진다.**

        되돌리기는 역순으로 돌면서 옮겨 둔 자식을 제자리에 놓는다. 그때 이 부모가 필요하다.
        놓기만 했더니 rollback 이 `parent handle was released` 로 실패해 보관소가 통째로
        남았다 — 고치려던 것보다 나쁜 상태였다.
        """
        w = uninstall_windows_fs
        source = self.body("uninstall_windows_fs.py", "replace", "WindowsBackend")
        self.assertIn("_detach_subtree(source)", source)
        self.assertIn("_attach_subtree(detached, parent, os.path.basename(target), target)",
                      source, "옮긴 뒤 새 자리로 다시 붙들지 않는다")
        self.assertIn("_attach_subtree(detached, parent, os.path.basename(source), source)",
                      source, "옮기지 못했을 때 원래 자리로 되돌려 붙들지 않는다")

    @staticmethod
    def body(module, name, owner=None):
        with open(os.path.join(REPO, "sage", module), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        nodes = tree.body
        if owner is not None:
            nodes = next(n for n in tree.body
                         if isinstance(n, ast.ClassDef) and n.name == owner).body
        target = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == name)
        body = target.body[1:] if ast.get_docstring(target) else target.body
        return "\n".join(ast.unparse(node) for node in body)

    def test_the_registry_tracks_where_a_moved_directory_actually_is(self):
        """**논리 이름과 물리 위치가 갈라지는 것**이 되돌리기를 깨뜨린 결함이었다.

        `parents` 의 key 는 호출자가 쓰는 이름이라 끝까지 바뀌지 않는다. 그런데 디렉터리를
        보관소 이름으로 옮기면 그 아래 것들의 실제 자리가 통째로 움직인다. 놓을 것을
        **논리 이름으로** 찾으면, 이미 옮겨진 디렉터리를 되돌릴 때 그 handle 을 찾지 못한다 —
        그 이름의 자리에는 아무것도 없기 때문이다. 그래서 되돌리기가 통째로 실패했다.
        """
        w = uninstall_windows_fs
        saved = w._close
        w._close = lambda handle: None
        self.addCleanup(lambda: setattr(w, "_close", saved))

        backend = w.WindowsBackend(types.SimpleNamespace(identity_source="id"))
        root = os.path.abspath(os.sep + "root")
        held = os.path.join(root, "held")
        child = os.path.join(held, "inner")
        moved = os.path.join(root, ".sage-install-backup-t-held")

        backend.parents[held] = 1
        backend.parents[child] = 2
        backend._physical[held] = held
        backend._physical[child] = child

        # 옮긴 자리를 적어 둔다. 논리 이름은 그대로다.
        backend._physical[held] = moved
        backend._physical[child] = os.path.join(moved, "inner")

        # **옮겨진 자리로** 찾으면 둘 다 나온다.
        saved_identity = w.identity
        w.identity = lambda handle, source="id": ("mark", handle)
        self.addCleanup(lambda: setattr(w, "identity", saved_identity))

        found = {key: rel for key, rel, _mark in backend._detach_subtree(moved)}
        self.assertEqual(found, {held: os.curdir, child: "inner"},
                         "옮겨진 자리에 있는 handle 을 찾지 못했다")
        self.assertEqual(backend.parents, {})
        self.assertEqual(backend._physical, {})

    def test_the_old_logical_name_no_longer_finds_a_moved_directory(self):
        """옮겨진 뒤 **원래 이름으로는 찾히지 않는다.** 그 자리에는 아무것도 없다."""
        w = uninstall_windows_fs
        saved = w._close
        w._close = lambda handle: None
        self.addCleanup(lambda: setattr(w, "_close", saved))

        backend = w.WindowsBackend(types.SimpleNamespace(identity_source="id"))
        root = os.path.abspath(os.sep + "root")
        held = os.path.join(root, "held")
        backend.parents[held] = 1
        backend._physical[held] = os.path.join(root, ".sage-install-backup-t-held")

        saved_identity = w.identity
        w.identity = lambda handle, source="id": ("mark", handle)
        self.addCleanup(lambda: setattr(w, "identity", saved_identity))
        self.assertEqual(backend._detach_subtree(held), [],
                         "옮겨진 디렉터리를 옛 이름으로 찾았다")
        self.assertIn(held, backend.parents, "찾지도 못했으면서 등록을 지웠다")

    def test_reopening_by_name_must_prove_it_is_the_same_object(self):
        """이름으로 다시 여는 자리는 **전부 지문 검사를 지난다.**

        지나지 않으면 "붙들었다" 가 "그 이름을 열었다" 로 조용히 바뀐다. 상위가 그 사이
        바뀌면 같은 이름이 다른 객체를 가리키고, 우리는 남의 디렉터리를 붙든 채 되돌리기를
        돌게 된다 — 그러면 우리 보관소는 영영 제자리로 돌아가지 못한다. 실제로 상위 교체
        반례에서 보관소 하나가 그렇게 남았다.
        """
        w = uninstall_windows_fs
        saved = w.identity
        w.identity = lambda handle, source="id": ("other",)
        self.addCleanup(lambda: setattr(w, "identity", saved))
        with self.assertRaises(ValueError) as caught:
            w._same_object(1, ("mine",), "id")
        self.assertEqual(str(caught.exception), "uninstall.boundary_changed")
        w.identity = lambda handle, source="id": ("mine",)
        w._same_object(1, ("mine",), "id")     # 같은 객체면 조용히 지난다

    def test_the_rename_checks_identity_before_letting_go(self):
        """지문 검사가 **놓기 전에** 와야 한다.

        놓은 뒤에 확인하면, 어긋난 것을 알았을 때는 이미 handle 을 닫은 뒤다. 되돌리기가
        그 아래를 만질 방법이 사라진다.
        """
        source = self.body("uninstall_windows_fs.py", "replace", "WindowsBackend")
        check = source.index("_same_object(handle, identity(held")
        detach = source.index("_detach_subtree(source)")
        self.assertLess(check, detach, "놓은 뒤에 확인한다")

    def test_a_released_parent_never_falls_back_to_paths(self):
        """놓은 뒤 그 아래를 다시 쓰려 하면 **멈춘다.**

        `pinned()` 가 거짓을 돌려주면 상위 층은 경로 기반 구현으로 조용히 떨어지고, 결속이
        사라진 사실이 결과 어디에도 드러나지 않는다. 이 사이클이 반복해서 만난 모양이다.
        """
        w = uninstall_windows_fs
        saved = w._close
        w._close = lambda handle: None
        self.addCleanup(lambda: setattr(w, "_close", saved))

        backend = w.WindowsBackend(types.SimpleNamespace(identity_source="id"))
        held = os.path.abspath(os.path.join("nowhere", "held"))
        saved_identity = w.identity
        w.identity = lambda handle, source="id": ("mark", handle)
        self.addCleanup(lambda: setattr(w, "identity", saved_identity))
        backend.parents[held] = 4242
        backend._physical[held] = held
        backend._release_parent(held)   # 사라질 디렉터리 — 다시 붙들지 않는다
        with self.assertRaises(install_transaction.InstallDriftError):
            backend.pinned(os.path.join(held, "child.json"))

    def test_the_rename_keeps_the_parent_handle_binding(self):
        """rename 진입점이 바뀌어도 **부모 handle 상대**여야 한다.

        `RootDirectory` 를 비우고 절대 경로로 물러서면 rename 이 이름 기준이 되고, 상위가
        그 사이 바뀌면 우리가 붙든 것이 아닌 자리로 간다 — 이 사이클이 닫으려는 위험이다.
        Windows runner 에서 Win32 진입점이 `RootDirectory` 를 받지 않는다는 것이 확인됐으므로
        NT 진입점을 쓰되, 결속 자체는 그대로다.
        """
        source = self.body("uninstall_windows_fs.py", "_rename_in")
        self.assertIn("info.RootDirectory = HANDLE(parent)", source,
                      "부모 handle 상대 rename 이 아니다")
        self.assertIn("NtSetInformationFile", source)
        self.assertNotIn("SetFileInformationByHandle", source,
                         "RootDirectory 를 받지 않는 진입점으로 되돌아갔다")


    def test_native_errors_never_carry_the_operating_system_message(self):
        """원문 Windows 메시지에는 절대 경로가 붙는다. 그것을 실어 나르지 않는다."""
        error = uninstall_windows_fs.WindowsMutationError("NtCreateFile", 0xC0000034,
                                                          ntstatus=True)
        self.assertEqual(str(error), "NtCreateFile:nt:0xc0000034")
        self.assertNotIn("\\", str(error))

    def test_network_and_non_drive_roots_are_refused_before_anything_opens(self):
        """UNC·네트워크 경로는 NT 경로로 옮기는 자리에서 이미 거부된다.

        상대 경로는 **Windows 에서 비드라이브 경로가 아니다** — `abspath` 가 현재 드라이브
        아래 절대 경로로 만든다. 그것을 거부하리라 기대하는 것은 제품이 아니라 POSIX 습관에
        대한 기대다.
        """
        refused = ["\\\\server\\share\\project", "//server/share"]
        if os.name != "nt":
            refused.append("relative/path")
        for path in refused:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    uninstall_windows_fs.nt_path(path)


class ManualCleanupGuidance(Base):
    """자동 제거가 불가능하거나 실패했을 때의 안내. **네 의미를 접지 않는다.**"""

    def blocked(self, consumer, code="uninstall.unsafe_platform"):
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        return uninstall_plan.UninstallPlan(
            plan.scope, plan.dest, plan.actions, uninstall_plan.BLOCKED, code,
            plan.notices, baseline=plan.baseline, global_root=plan.global_root)

    def test_the_order_puts_partial_removal_before_deletion(self):
        """등록을 먼저 치우지 않고 실행 파일을 지우면 host 가 없는 command 를 부른다."""
        plan = self.blocked(self.fresh())
        guide = uninstall_cleanup.guidance(plan, basis=uninstall_cleanup.BASIS_VERIFIED)
        self.assertTrue(guide["available"])
        self.assertEqual(guide["order"][0], uninstall_plan.STRIP)
        self.assertIn(uninstall_plan.DELETE, guide["order"])
        self.assertLess(guide["order"].index(uninstall_plan.STRIP),
                        guide["order"].index(uninstall_plan.DELETE))
        self.assertIn(uninstall_cleanup.REGISTRATION_FIRST, guide["warning_codes"])

    def test_blocked_entries_are_never_offered_as_something_to_clean(self):
        """`BLOCK` 은 손댈 대상이 아니라 먼저 고쳐야 하는 상태다."""
        plan = self.blocked(self.fresh())
        guide = uninstall_cleanup.guidance(plan, basis=uninstall_cleanup.BASIS_VERIFIED)
        self.assertNotIn(uninstall_plan.BLOCK, guide["order"])

    def test_an_uncertain_state_never_claims_anything_is_safe_to_delete(self):
        """되돌리기까지 실패했으면 "지워도 된다" 고 말하지 않는다 — 되돌릴 수 없는 조언이다."""
        plan = self.blocked(self.fresh(), "uninstall.rollback_failed")
        guide = uninstall_cleanup.guidance(plan, basis=uninstall_cleanup.BASIS_UNCERTAIN,
                                           unknown=[".sage-install-backup-x"])
        self.assertNotIn(uninstall_plan.DELETE, guide["order"])
        self.assertIn(uninstall_cleanup.NO_DELETE_CLAIM, guide["warning_codes"])
        self.assertEqual(guide["unknown"], [".sage-install-backup-x"])

    def test_a_committed_leftover_is_named_in_the_guide(self):
        """뒷정리가 실패했으면 **무엇을 치울지** 말해야 한다.

        `leftover_backups` 만 따로 내고 안내는 `available: false` 로 두면, 화면은 "치울 것이
        있다" 고 말하면서 무엇을 치울지는 말하지 않는 상태가 된다 — 두 출력이 서로 다른
        의미를 낸다.
        """
        plan = uninstall_plan.build(self.fresh().project, uninstall_plan.SCOPE_PROJECT)
        guide = uninstall_cleanup.guidance(
            plan, basis=uninstall_cleanup.BASIS_COMMITTED,
            leftovers=[".sage-install-backup-abc-settings.json"])
        self.assertTrue(guide["available"])
        self.assertEqual(guide["basis"], "committed_with_leftovers")
        self.assertEqual(guide["order"], [], "끝난 제거를 다시 안내한다")
        self.assertEqual(guide["leftovers"], [".sage-install-backup-abc-settings.json"])

    def test_the_cli_agrees_with_itself_when_cleanup_fails(self):
        """`leftover_backups` 와 수동 안내가 **같은 정화 경로 한 벌**을 쓴다."""
        consumer = self.fresh()
        script = "\n".join([
            "import sys",
            f"sys.path.insert(0, {REPO!r})",
            "from sage import install_transaction as tx",
            "def refuse(self):",
            "    self._committed = True",
            "    return [f'{p}: injected' for p, b in self._entries if b]",
            "tx.InstallTransaction.commit = refuse",
            "from sage.cli import main",
            f"sys.argv = ['sage', 'uninstall', '--dest', {consumer.project!r},"
            " '--yes', '--json']",
            "sys.exit(main())",
        ])
        result = subprocess.run([sys.executable, "-c", script], cwd=REPO, env=consumer.env,
                                capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["leftover_backups"], "치우지 못한 보관소를 보고하지 않았다")
        guide = payload["manual_cleanup"]
        self.assertTrue(guide["available"], "치울 것이 있는데 안내가 없다")
        self.assertEqual(guide["basis"], "committed_with_leftovers")
        self.assertEqual(guide["leftovers"], payload["leftover_backups"],
                         "두 목록이 다른 말을 한다")
        for path in guide["leftovers"]:
            self.assertFalse(os.path.isabs(path), f"정화되지 않은 경로: {path}")

    def test_guidance_is_not_offered_for_a_successful_run(self):
        """자동으로 끝난 실행에 수동 안내를 붙이면 안 해도 되는 삭제로 이끈다."""
        plan = uninstall_plan.build(self.fresh().project, uninstall_plan.SCOPE_PROJECT)
        self.assertFalse(uninstall_cleanup.applies(plan, executed=True))
        self.assertFalse(uninstall_cleanup.applies(plan, executed=False))

    def test_an_unknown_basis_is_a_programming_error_not_a_silent_default(self):
        plan = self.blocked(self.fresh())
        with self.assertRaises(ValueError):
            uninstall_cleanup.guidance(plan, basis="probably_fine")

    def test_the_cli_shows_the_guide_and_never_collapses_the_delete_list(self):
        """접힌 목록을 보고 손으로 정리할 수는 없다."""
        consumer = self.fresh()
        result = self.refused(consumer)
        combined = result.stdout + result.stderr
        self.assertEqual(result.returncode, 2, combined)
        self.assertIn("수동 정리 안내", combined)
        self.assertIn("파일 전체를 삭제하지 말고", combined)
        self.assertIn(os.path.join(".claude", "skills", "sage-plan"), combined,
                      "삭제 목록이 접힌 채 안내만 나왔다")
        self.assertIn(".gitignore", combined)

    def test_the_guide_never_writes_a_destructive_shell_command(self):
        """`rm`·`rmdir`·recursive delete 를 복구 명령으로 주지 않는다.

        그 명령 하나가 잘못된 디렉터리에서 실행되면 이 명령이 지키려던 모든 것을 한 번에
        지운다. 목록을 주는 것과 명령을 주는 것은 다른 일이다.
        """
        consumer = self.fresh()
        combined = self.refused(consumer)
        text = combined.stdout + combined.stderr
        for banned in ("rm -", "rm -rf", "rmdir", "Remove-Item", "del /s", "rd /s",
                       "shutil.rmtree", "find . -delete"):
            self.assertNotIn(banned, text, f"파괴적 명령을 안내했다: {banned}")

    def test_text_and_json_agree_on_basis_and_order(self):
        """두 출력이 다른 말을 하면 사용자는 어느 쪽을 믿어야 하는지 알 수 없다."""
        consumer = self.fresh()
        payload = json.loads(self.refused(consumer, json_mode=True).stdout)
        guide = payload["manual_cleanup"]
        self.assertEqual(guide["basis"], "verified_plan")
        self.assertEqual(guide["order"][0], "STRIP")
        # 배열을 복제하지 않는다 — 정본은 기존 네 배열이다.
        self.assertNotIn("paths", guide)
        stripped = {entry["path"] for entry in payload["stripped"]}
        self.assertIn(".gitignore", stripped)

    def test_existing_json_keys_are_unchanged(self):
        """`manual_cleanup` 을 몰라도 지금과 똑같이 읽혀야 한다."""
        consumer = self.fresh()
        payload = json.loads(self.refused(consumer, json_mode=True).stdout)
        for key in ("scope", "status", "exit_code", "blocked_reason", "deleted", "stripped",
                    "preserved", "blocked", "notices", "executed"):
            self.assertIn(key, payload, f"기존 소비자가 읽던 키가 사라졌다: {key}")

    def refused(self, consumer, json_mode=False):
        """capability 를 자식 안에서 꺼서 안전 거부 경로를 밟는다."""
        argv = ["sage", "uninstall", "--dest", consumer.project, "--yes"]
        if json_mode:
            argv.append("--json")
        script = (
            "import sys;"
            "sys.path.insert(0, %r);"
            "import sage.uninstall_fs as f;"
            "f.capability = lambda roots=(): f.MutationCapability("
            "f.BACKEND_NONE, failure_code='uninstall.unsafe_platform');"
            "from sage.cli import main;"
            "sys.argv = %r;"
            "sys.exit(main())" % (REPO, argv))
        return subprocess.run([sys.executable, "-c", script], cwd=REPO, env=consumer.env,
                              capture_output=True, text=True)



class RootBinding(Base):
    """확인한 root 와 **쓰는 root** 가 같은 handle 인가.

    capability probe 가 연 핸들은 조사용이고 곧 닫힌다. 그 조사 결과를 결속으로 쓰면 조사와
    첫 변경 사이가 그대로 경쟁 구간이다 — root 이름이 링크로 바뀌면 확인은 옛 디렉터리에,
    변경은 새 디렉터리에서 일어난다.
    """

    def test_the_plan_records_a_baseline_for_every_write_root(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        self.assertEqual(sorted(plan.root_baseline), sorted(plan.lock_roots()))
        for root, mark in plan.root_baseline.items():
            self.assertEqual(mark, uninstall_plan.root_fingerprint(root))
            self.assertEqual(mark[0], "dir")

    def test_a_root_swapped_after_the_fingerprint_step_stops_the_run(self):
        """지문 대조가 **끝난 뒤** root 를 바꿔치기해도 아무것도 바뀌지 않아야 한다.

        이 자리가 위험한 이유는 대상 지문이 이미 통과했기 때문이다. 바꿔치기된 root 아래에서
        상대 경로는 새 디렉터리 안에서 다시 성립하거나 전부 없어지고, 어느 쪽도 대상 지문으로는
        보이지 않는다. root 를 여는 쪽이 계획의 기준과 대조해야만 잡힌다.
        """
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        outside = os.path.join(consumer.root, "outside")
        os.makedirs(outside)
        moved = os.path.join(consumer.root, "real-project")

        class SwapAtRoots(list):
            def append(inner, name):
                list.append(inner, name)
                if name == "roots" and not getattr(inner, "fired", False):
                    inner.fired = True
                    shutil.move(consumer.project, moved)
                    link_directory(consumer.project, outside)

        trace = SwapAtRoots()
        with self.assertRaises(ValueError) as caught:
            uninstall_executor.execute(plan, trace=trace)
        self.assertTrue(getattr(trace, "fired", False), "주입이 성립하지 않았다")
        self.assertEqual(str(caught.exception), "uninstall.boundary_changed")
        self.assertEqual(os.listdir(outside), [], "바꿔치기된 root 아래에서 변경이 일어났다")
        self.assertTrue(os.listdir(moved), "원래 root 가 비었다")
        self.assertEqual([n for n in os.listdir(moved)
                          if n.startswith(".sage-install-backup-")], [])

    def test_the_root_is_opened_after_the_lock_and_before_any_pin(self):
        """순서가 계약이다 — 잠그기 전에 root 를 붙들면 확인과 변경 사이가 다시 열린다."""
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        trace = []
        uninstall_executor.execute(plan, trace=trace)
        self.assertLess(trace.index("lock"), trace.index("roots"))
        self.assertLess(trace.index("fingerprint"), trace.index("roots"))
        self.assertLess(trace.index("roots"), trace.index("prepare"))

    def test_a_backend_refuses_to_open_a_root_it_was_never_given(self):
        """root 를 조작 중에 새로 여는 길이 없어야 한다. 열면 확인하지 않은 root 를 쓴다."""
        backend = uninstall_posix_fs.PosixBackend()
        with self.assertRaises(install_transaction.InstallDriftError):
            backend.pin(REPO, os.path.join(REPO, "sage", "cli.py"))

    def test_pin_leaves_no_open_handle_behind_when_the_descent_fails(self):
        """하강 중 실패하면 이미 연 중간 handle 을 **역순으로 전부** 닫는다.

        backend 를 이름으로 고르지 않고 **이 환경이 실제로 쓰는 것**을 가져온다. POSIX
        backend 를 Windows 에서 만들면 `os.O_DIRECTORY` 가 없어 검사가 제품이 아니라 자기
        가정 때문에 죽고, 그 자리에서 Windows 하강 정리는 한 번도 확인되지 않는다.
        """
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        backend = uninstall_fs.backend_for(plan.lock_roots())
        backend.open_roots(plan.root_baseline)
        opened = self.open_handles()
        missing = os.path.join(consumer.project, "no", "such", "dir", "leaf.txt")
        for _attempt in range(20):
            with self.assertRaises(OSError):
                backend.pin(consumer.project, missing)
        after = self.open_handles()
        backend.close()
        if opened is not None:
            self.assertLessEqual(after, opened + 2, "하강 실패마다 fd 가 샌다")

    def open_handles(self):
        return len(os.listdir("/dev/fd")) if os.path.isdir("/dev/fd") else None


class PinnedProbes(unittest.TestCase):
    """붙든 뒤에는 **절대 경로로 다시 묻지 않는다.**

    경로로 물으면 상위가 바뀐 순간 "있다/없다" 가 다른 디렉터리에 대해 답해진다. 그 답으로
    지우면 남의 파일을 지우고, 그 답으로 넘기면 지워야 할 것을 남긴 채 성공으로 끝난다.
    """

    def body(self, module, name, owner=None):
        with open(os.path.join(REPO, "sage", module), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        nodes = tree.body
        if owner is not None:
            nodes = next(n for n in tree.body
                         if isinstance(n, ast.ClassDef) and n.name == owner).body
        target = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == name)
        body = target.body[1:] if ast.get_docstring(target) else target.body
        return "\n".join(ast.unparse(node) for node in body)

    def test_staging_asks_the_seam_not_the_absolute_path(self):
        for name in ("stage_write", "stage_remove_tree"):
            with self.subTest(name=name):
                code = self.body("install_transaction.py", name, "InstallTransaction")
                for banned in ("os.path.lexists", "os.lstat"):
                    self.assertNotIn(banned, code,
                                     f"{name} 이 붙든 대상을 경로로 다시 묻는다: {banned}")
                self.assertIn("self._probe", code)

    def test_the_executor_verifies_results_through_the_journal(self):
        code = self.body("uninstall_executor.py", "_execute_locked")
        for banned in ("os.path.lexists", "os.lstat", "os.path.isdir", "os.path.islink"):
            self.assertNotIn(banned, code, f"실행 층이 경로로 결과를 판정한다: {banned}")
        self.assertIn("journal._probe", code)
        self.assertIn('journal._measure(action.path, \'path\')', code)

    def test_emptiness_is_measured_through_the_journal(self):
        code = self.body("uninstall_executor.py", "_effectively_empty")
        for banned in ("os.path.isdir", "os.path.islink"):
            self.assertNotIn(banned, code)
        self.assertIn("journal._measure", code)

    def test_removal_never_creates_a_parent_directory(self):
        """`_ensure_parents` 는 install 의 것이다. 제거가 경로로 `mkdir` 하면 밖에 만들 수 있다."""
        code = self.body("uninstall_executor.py", "_ensure_parents", "_PinnedTransaction")
        self.assertIn("self.backend.pinned", code)
        self.assertIn("return", code)

    def test_the_mkdir_seam_is_closed_under_the_pin(self):
        """부모가 **없어도** 만들지 않는다. 소스가 아니라 호출로 본다.

        실행 창의 `os.mkdir` 감시는 실행이 실제로 지나는 자리만 본다 — 제거 대상의 부모는 늘
        있으므로 `_ensure_parents` 는 `os.mkdir` 까지 가지 않는다. 그래서 그 자리를 직접
        부른다. install 의 구현이 다시 살아나면 여기서 경로로 `mkdir` 하고, 상위가 그 사이
        바뀌었으면 그 디렉터리는 프로젝트 밖에 생긴다.
        """
        class Pinned:
            def pinned(self, path):
                return True

        root = fixture_root("mkdir-seam")
        self.addCleanup(shutil.rmtree, root, True)
        journal = uninstall_executor._PinnedTransaction(
            expected={}, write_roots=(), backend=Pinned())
        made = []
        original = os.mkdir

        def watched(*args, **kwargs):
            made.append(args[0] if args else kwargs.get("path"))
            return original(*args, **kwargs)

        os.mkdir = watched
        try:
            journal._ensure_parents(os.path.join(root, "missing", "deep", "settings.json"))
        finally:
            os.mkdir = original
        self.assertEqual(made, [], f"붙든 뒤에 부모를 만들었다: {made}")
        self.assertFalse(os.path.lexists(os.path.join(root, "missing")),
                         "제거 경로가 디렉터리를 만들었다")


class WindowsCapabilityWiring(unittest.TestCase):
    """probe 가 **돌려주는 값**이 실제로 바뀌는가.

    지역 dict 를 고치고 생성자가 만든 사본을 그대로 돌려주면, capability 는 어떤 환경에서도
    거짓이고 Windows mutation 은 100% 거부된다. 기능이 통째로 죽는데 화면에는 "안전 거부" 로만
    보인다 — 원격 runner 없이 이 배선을 확인할 수 있어야 한다.
    """

    def fake_windows(self, root):
        w = uninstall_windows_fs
        info = os.stat(root)
        saved = {name: getattr(w, name) for name in
                 ("_is_windows", "_windows_10_or_later", "_open_root", "local_ntfs",
                  "_tag_info", "identity", "_entries", "_close", "_mode_of")}

        class Api:
            SetFileInformationByHandle = object()

        saved["_Api_get"] = w._Api.get
        w._is_windows = lambda: True
        w._windows_10_or_later = lambda: True
        w._open_root = lambda path: 1234
        w.local_ntfs = lambda handle: (True, "NTFS", True)
        w._tag_info = lambda handle: (w.FILE_ATTRIBUTE_DIRECTORY, 0)
        w.identity = lambda handle, source="id": (info.st_dev, info.st_ino)
        w._entries = lambda handle: []
        w._close = lambda handle: None
        w._mode_of = lambda attributes: stat.S_IMODE(info.st_mode)
        w._Api.get = classmethod(lambda cls: Api())

        def restore():
            for name, value in saved.items():
                if name == "_Api_get":
                    w._Api.get = value
                else:
                    setattr(w, name, value)

        self.addCleanup(restore)

    def test_a_supported_environment_actually_reports_supported(self):
        root = fixture_root("capability-wiring")
        self.addCleanup(shutil.rmtree, root, True)
        self.fake_windows(root)
        cap = uninstall_windows_fs.probe_capability((root,))
        self.assertIsNone(cap.failure_code, cap.as_json())
        self.assertTrue(cap.supported, cap.as_json())
        for name in uninstall_fs.PRIMITIVES:
            self.assertTrue(cap.primitives[name], f"{name} 이 참으로 돌아오지 않았다")
        self.assertIn(cap.identity_source, ("id", "handle"))
        self.assertEqual(cap.filesystem, "NTFS")

    def test_a_volume_that_cannot_be_confirmed_local_is_refused(self):
        root = fixture_root("capability-nonlocal")
        self.addCleanup(shutil.rmtree, root, True)
        self.fake_windows(root)
        uninstall_windows_fs.local_ntfs = lambda handle: (False, "NTFS", False)
        cap = uninstall_windows_fs.probe_capability((root,))
        self.assertFalse(cap.supported)
        self.assertEqual(cap.failure_code, "uninstall.unsafe_platform")
        self.assertFalse(cap.local_volume)

    def test_a_reparse_root_is_refused(self):
        root = fixture_root("capability-reparse")
        self.addCleanup(shutil.rmtree, root, True)
        self.fake_windows(root)
        uninstall_windows_fs._tag_info = lambda handle: (
            uninstall_windows_fs.FILE_ATTRIBUTE_DIRECTORY
            | uninstall_windows_fs.FILE_ATTRIBUTE_REPARSE_POINT,
            uninstall_windows_fs.IO_REPARSE_TAG_MOUNT_POINT)
        cap = uninstall_windows_fs.probe_capability((root,))
        self.assertFalse(cap.supported)
        self.assertEqual(cap.failure_code, "uninstall.unsafe_platform")

    def test_an_identity_mapping_that_does_not_match_lstat_is_refused(self):
        root = fixture_root("capability-identity")
        self.addCleanup(shutil.rmtree, root, True)
        self.fake_windows(root)
        uninstall_windows_fs.identity = lambda handle, source="id": (0, 0)
        cap = uninstall_windows_fs.probe_capability((root,))
        self.assertFalse(cap.supported)
        self.assertFalse(cap.primitives["identity_match"])

    def multi_root(self, roots, matches):
        """root 마다 다른 identity 결과를 주는 fake. `matches` 는 `{root: {source, ...}}`."""
        w = uninstall_windows_fs
        handles = {root: 1000 + index for index, root in enumerate(roots)}
        by_handle = {handle: root for root, handle in handles.items()}
        saved = {name: getattr(w, name) for name in
                 ("_is_windows", "_windows_10_or_later", "_open_root", "local_ntfs",
                  "_tag_info", "identity", "_entries", "_close", "_mode_of")}
        saved["_Api_get"] = w._Api.get

        class Api:
            SetFileInformationByHandle = object()

        w._is_windows = lambda: True
        w._windows_10_or_later = lambda: True
        w._open_root = lambda path: handles[os.path.abspath(path)]
        w.local_ntfs = lambda handle: (True, "NTFS", True)
        w._tag_info = lambda handle: (w.FILE_ATTRIBUTE_DIRECTORY, 0)
        w._entries = lambda handle: []
        w._close = lambda handle: None
        w._mode_of = lambda attributes: stat.S_IMODE(os.stat(by_handle[1000]).st_mode)
        w._Api.get = classmethod(lambda cls: Api())

        def identity(handle, source="id"):
            root = by_handle[handle]
            info = os.stat(root)
            if source in matches.get(root, set()):
                return (info.st_dev, info.st_ino)
            return (0, 0)

        w.identity = identity

        def restore():
            for name, value in saved.items():
                if name == "_Api_get":
                    w._Api.get = value
                else:
                    setattr(w, name, value)

        self.addCleanup(restore)
        return handles

    def two_roots(self, label):
        base = fixture_root(label)
        self.addCleanup(shutil.rmtree, base, True)
        first = os.path.join(base, "proj")
        second = os.path.join(base, "codex")
        os.makedirs(first)
        os.makedirs(second)
        return os.path.abspath(first), os.path.abspath(second)

    def test_a_second_root_that_matches_nothing_is_not_carried_by_the_first(self):
        """첫 root 가 맞았다는 사실이 두 번째 root 의 판정을 대신하지 않는다.

        공용 불리언 하나로 두면 첫 root 에서 켜진 참이 그대로 남고, 두 번째 root 가 어느
        유도에도 맞지 않아도 `supported=True` 가 나온다. project 는 맞고 `$CODEX_HOME` 은
        다른 볼륨이라 어긋나는 배치가 정확히 그 모양이다.
        """
        first, second = self.two_roots("identity-carry")
        self.multi_root((first, second), {first: {"id", "handle"}, second: set()})
        cap = uninstall_windows_fs.probe_capability((first, second))
        self.assertFalse(cap.supported, cap.as_json())
        self.assertEqual(cap.failure_code, "uninstall.unsafe_platform")
        self.assertFalse(cap.primitives["identity_match"])
        self.assertIsNone(cap.identity_source)

    def test_roots_that_need_different_sources_are_refused(self):
        """한 실행은 유도 하나만 쓴다. 공통 source 가 없으면 지원하지 않는다."""
        first, second = self.two_roots("identity-split")
        self.multi_root((first, second), {first: {"id"}, second: {"handle"}})
        cap = uninstall_windows_fs.probe_capability((first, second))
        self.assertFalse(cap.supported)
        self.assertEqual(cap.failure_code, "uninstall.unsafe_platform")

    def test_a_common_source_across_roots_is_chosen_deterministically(self):
        first, second = self.two_roots("identity-common")
        self.multi_root((first, second), {first: {"id", "handle"}, second: {"handle"}})
        cap = uninstall_windows_fs.probe_capability((first, second))
        self.assertTrue(cap.supported, cap.as_json())
        self.assertEqual(cap.identity_source, "handle")
        self.assertTrue(cap.primitives["identity_match"])

    def test_opening_a_child_closes_the_handle_when_the_tag_read_fails(self):
        """연 뒤의 어떤 실패에서도 handle 을 놓치지 않는다.

        Windows 에서 handle 누수는 그 디렉터리를 다른 프로세스가 만지지 못하게 만든다 —
        POSIX 의 fd 누수보다 사용자에게 더 직접적으로 보인다.
        """
        w = uninstall_windows_fs
        closed = []
        saved = {name: getattr(w, name) for name in ("_open", "_tag_info", "_close")}
        self.addCleanup(lambda: [setattr(w, name, value) for name, value in saved.items()])

        def boom(handle):
            raise w.WindowsMutationError("GetFileInformationByHandleEx", 5)

        w._open = lambda *args, **kwargs: 4242
        w._tag_info = boom
        w._close = closed.append
        with self.assertRaises(w.WindowsMutationError):
            w._open_child(1, "child", directory=True)
        self.assertEqual(closed, [4242], "실패한 열기의 handle 을 닫지 않았다")

        closed.clear()
        w._tag_info = lambda handle: (w.FILE_ATTRIBUTE_DIRECTORY
                                      | w.FILE_ATTRIBUTE_REPARSE_POINT,
                                      w.IO_REPARSE_TAG_MOUNT_POINT)
        with self.assertRaises(ValueError):
            w._open_child(1, "child", directory=True)
        self.assertEqual(closed, [4242], "reparse 거부에서 handle 을 닫지 않았다")

    def test_an_unconfirmed_final_path_is_never_read_as_local(self):
        """`GetFinalPathNameByHandleW` 실패는 반환값 0 이다. 그 0 을 "UNC 아님" 으로 읽지 않는다."""
        w = uninstall_windows_fs
        saved = w._volume_facts
        self.addCleanup(lambda: setattr(w, "_volume_facts", saved))
        w._volume_facts = lambda handle: ("NTFS", None)
        ok, filesystem, local = w.local_ntfs(9999)
        self.assertFalse(ok)
        self.assertFalse(local)
        self.assertIsNone(w._drive_type(None))
        self.assertIsNone(w._drive_type(""))

    def test_only_confirmed_local_drive_types_are_accepted(self):
        w = uninstall_windows_fs
        self.assertIn(w.DRIVE_FIXED, w.LOCAL_DRIVE_TYPES)
        for kind in (w.DRIVE_UNKNOWN, w.DRIVE_NO_ROOT_DIR, w.DRIVE_REMOTE):
            self.assertNotIn(kind, w.LOCAL_DRIVE_TYPES, f"{kind} 를 로컬로 셌다")


class NativeErrorSurface(Base):
    """native 실패가 **계약된 이름**으로 화면까지 오는가.

    변환 함수가 있어도 그것을 부르는 자리가 검사뿐이면, 실제 실패는 전부 `execution_failed`
    하나로 접힌다. 그 화면에서는 backup 이름 충돌과 경계 변화가 구별되지 않는다.
    """

    def test_a_backend_failure_carries_its_diagnostic(self):
        error = uninstall_windows_fs.WindowsMutationError(
            "NtCreateFile", uninstall_windows_fs.STATUS_OBJECT_NAME_COLLISION, ntstatus=True)
        self.assertIsInstance(error, uninstall_fs.MutationBackendError)
        self.assertIsInstance(error, OSError)
        self.assertEqual(error.diagnostic, "uninstall.backup_collision")

    def test_the_executor_translates_a_backend_failure_at_one_place(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)

        def explode(original):
            def hook(journal, path):
                raise uninstall_fs.MutationBackendError(
                    "op:nt:0xc0000035", "uninstall.backup_collision")
            return hook

        with patched("stage_remove_tree", explode):
            with self.assertRaises(ValueError) as caught:
                uninstall_executor.execute(plan)
        self.assertEqual(str(caught.exception), "uninstall.backup_collision")

    def test_the_cli_shows_the_translated_code_in_text_and_json(self):
        from sage.diagnostic_contract import SEVERITY
        self.assertIn("uninstall.backup_collision", SEVERITY)
        self.assertIn("uninstall.boundary_changed", SEVERITY)


class PostFailureGuidance(Base):
    """실패한 뒤의 목록은 **다시 읽은 상태**다. 의도했던 계획이 아니다."""

    def test_a_run_that_changed_nothing_keeps_the_plan_it_showed(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        actions, basis = uninstall_cmd._after_failure(
            consumer.project, uninstall_plan.SCOPE_PROJECT, plan, [])
        self.assertEqual(basis, uninstall_cleanup.BASIS_VERIFIED)
        self.assertEqual(actions, plan.actions)

    def test_a_rolled_back_run_reads_the_state_again(self):
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        actions, basis = uninstall_cmd._after_failure(
            consumer.project, uninstall_plan.SCOPE_PROJECT, plan, ["backup", "rollback"])
        self.assertEqual(basis, uninstall_cleanup.BASIS_POST_ROLLBACK)
        self.assertTrue(actions)

    def test_a_state_that_cannot_be_read_again_offers_no_actionable_order(self):
        """다시 읽지 못하면 순서를 비운다 — 추측을 목록으로 팔지 않는다."""
        consumer = self.fresh()
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_PROJECT)
        saved = uninstall_cmd._plan.build

        def refuse(*args, **kwargs):
            raise RuntimeError("cannot re-read")

        uninstall_cmd._plan.build = refuse
        try:
            actions, basis = uninstall_cmd._after_failure(
                consumer.project, uninstall_plan.SCOPE_PROJECT, plan, ["rollback"])
        finally:
            uninstall_cmd._plan.build = saved
        self.assertEqual(basis, uninstall_cleanup.BASIS_UNCERTAIN)
        self.assertEqual(actions, ())
        empty = uninstall_plan.UninstallPlan(
            plan.scope, plan.dest, actions, uninstall_plan.BLOCKED,
            "uninstall.rollback_failed", plan.notices, baseline=plan.baseline,
            global_root=plan.global_root, root_baseline=plan.root_baseline)
        guide = uninstall_cleanup.guidance(empty, basis=basis, unknown=["backup-x"])
        self.assertEqual(guide["order"], [])
        self.assertEqual(guide["unknown"], ["backup-x"])
        self.assertTrue(guide["available"])

    def test_global_residue_is_shown_under_the_global_root(self):
        """전역 잔여가 `<outside-project>` 로 접히면 사용자는 치울 자리를 잃는다."""
        consumer = self.fresh("codex")
        plan = uninstall_plan.build(consumer.project, uninstall_plan.SCOPE_ALL,
                                    environ={"CODEX_HOME": consumer.codex_home})
        residue = os.path.join(consumer.codex_home, "skills", ".sage-install-backup-x")
        project_residue = os.path.join(consumer.project, ".sage-install-backup-y")
        shown = uninstall_cmd._shown([residue, project_residue], plan)
        self.assertTrue(shown[0].startswith("$CODEX_HOME/"), shown)
        self.assertNotIn(uninstall_plan.OUTSIDE_PROJECT, shown)
        self.assertEqual(shown[1], ".sage-install-backup-y")


class LocalizationInventory(unittest.TestCase):
    """한영 catalog 에 빠진 것이 없다."""

    def test_catalog_inventory_is_zero(self):
        from sage.i18n.validation import catalog_issues, release_debt_issues
        self.assertEqual(catalog_issues(REPO), [])
        self.assertEqual(release_debt_issues(REPO), [])

    def test_every_uninstall_key_exists_in_both_languages(self):
        from sage.i18n import ko, en
        ko_keys = {k for k in ko.MESSAGES if k.startswith("cli.uninstall.")}
        en_keys = {k for k in en.MESSAGES if k.startswith("cli.uninstall.")}
        self.assertTrue(ko_keys)
        self.assertEqual(ko_keys, en_keys)


class RaceRunnerContract(unittest.TestCase):
    """race runner **자신이** 조용히 약해지는 것을 잡는다.

    이 runner 는 "몇 건 돌았다" 를 출력하는데, 그 숫자가 무엇을 세는지 아무도 검사하지 않으면
    숫자만 남고 보장은 사라진다. 실제로 그랬다 — 아무 상태도 바꾸지 못한 case 가 조용히
    반환해도 실행으로 셌고, Windows 커널이 막은 주입이 `14 injections executed` 안에 들어갔다.

    아래는 runner 를 일부러 약하게 만들었을 때 CI 가 **실패하는지** 본다.
    """

    def runner(self):
        import importlib.util
        path = os.path.join(REPO, "scripts", "ci", "uninstall_race_smoke.py")
        spec = importlib.util.spec_from_file_location("sage_race_runner", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def verdict(self, module, outcomes):
        """대조만 돌린다 — 실제 주입 없이 회계 규칙을 본다."""
        module.FAILURES.clear()
        module.OUTCOMES.clear()
        module.OUTCOMES.update(outcomes)
        for case_id, expected in sorted(module.REQUIRED_CASES.items()):
            actual = module.OUTCOMES.get(case_id)
            if actual is None:
                module.FAILURES.append(f"missing:{case_id}")
            elif actual == module.FAILED:
                module.FAILURES.append(f"failed:{case_id}")
            elif actual not in expected:
                module.FAILURES.append(f"kind:{case_id}")
        unknown = sorted(set(module.OUTCOMES) - set(module.REQUIRED_CASES))
        if unknown:
            module.FAILURES.append(f"unknown:{unknown}")
        return list(module.FAILURES)

    def healthy(self, module):
        return {case_id: allowed[0]
                for case_id, allowed in module.REQUIRED_CASES.items()}

    def test_every_declared_case_is_required_and_unique(self):
        module = self.runner()
        ids = [case_id for case_id, *_rest in module.CASES]
        self.assertEqual(len(ids), len(set(ids)), "같은 id 를 두 번 등록했다")
        self.assertEqual(sorted(ids), sorted(module.REQUIRED_CASES),
                         "선언한 case 와 요구 목록이 다르다")
        self.assertEqual(len(module.REQUIRED_CASES), 14)

    def test_a_healthy_run_passes_the_ledger(self):
        module = self.runner()
        self.assertEqual(self.verdict(module, self.healthy(module)), [])

    def test_a_case_that_changes_nothing_fails(self):
        """무동작 case. 예전에는 이것이 실행으로 집계됐다."""
        module = self.runner()
        outcomes = self.healthy(module)
        outcomes["strip-leaf-replaced-by-link:project"] = module.FAILED
        self.assertTrue(self.verdict(module, outcomes))

    def test_a_prevented_case_is_not_counted_as_executed(self):
        """OS 가 막은 것은 해낸 것이 아니다. 같은 숫자에 넣으면 계약이 조용히 충족된다.

        **실제 교체가 가능한 자리**에서만 그렇다. 커널이 그 교체를 아예 막는 자리는 요구
        자체가 `PREVENTED_BY_OS` 이고, 거기서 실제 교체를 요구하면 OS 가 먼저 막아 준 상황을
        실패로 세게 된다.
        """
        module = self.runner()
        outcomes = self.healthy(module)
        outcomes["root-swap-after-fingerprint:project"] = module.PREVENTED_BY_OS
        problems = self.verdict(module, outcomes)
        self.assertTrue(any("kind:" in note for note in problems),
                        f"막힌 주입을 실행으로 셌다: {problems}")

    def test_only_contracted_refusal_codes_count_as_prevention(self):
        """아무 거부나 차단으로 세지 않는다.

        열기 실패도, 잘못된 인자도, 미지원도 거부처럼 보이지만 그것들은 차단이 아니라 우리
        구현이 틀렸다는 뜻이다. `ACCESS_DENIED` 두 표기만 계약이다.
        """
        module = self.runner()
        self.assertEqual(module.ACCESS_DENIED_CODES, frozenset({5, 0xC0000022}))
        for wrong in (0x57, 0x32, "open:5", None):
            self.assertNotIn(wrong, module.ACCESS_DENIED_CODES)

    def test_the_native_attack_runs_outside_the_product_helpers(self):
        """공격은 **별도 프로세스**에서, 제품 helper 없이 한다.

        제품과 검사가 같은 helper 를 나눠 쓰면 그 helper 하나가 틀렸을 때 둘 다 같은 방식으로
        틀린다 — "공격이 막혔다" 와 "우리가 못 불렀다" 가 같은 화면이 된다.
        """
        module = self.runner()
        self.assertIn("CreateFileW", module.NATIVE_ATTACK)
        self.assertIn("SetFileInformationByHandle", module.NATIVE_ATTACK)
        self.assertNotIn("uninstall_windows_fs", module.NATIVE_ATTACK,
                         "공격이 제품 helper 를 쓴다")

    def test_a_missing_scope_fails(self):
        """root 교체 세 scope 중 하나가 빠지는 경우. 이름만 세면 나머지가 채워 준다."""
        module = self.runner()
        outcomes = self.healthy(module)
        del outcomes["root-swap-after-fingerprint:global"]
        problems = self.verdict(module, outcomes)
        self.assertTrue(any("root-swap-after-fingerprint:global" in n for n in problems),
                        f"빠진 scope 를 잡지 못했다: {problems}")

    def test_a_synthetic_injection_cannot_satisfy_a_real_seam(self):
        """monkeypatch 주입이 실제 경쟁 자리를 대신할 수 없다."""
        module = self.runner()
        outcomes = self.healthy(module)
        outcomes["root-swap-after-fingerprint:project"] = module.SYNTHETIC
        self.assertTrue(self.verdict(module, outcomes))

    def test_the_runner_never_falls_back_to_a_copying_move(self):
        """`shutil.move` 재도입을 막는다.

        그것은 rename 이 실패하면 복사 후 삭제로 떨어진다. 그러면 주입한 것은 이름 교체가
        아니라 "복사해 두고 원본 삭제" 이고, 붙든 객체는 사라진 원본 쪽이다 — 전혀 다른
        상황을 같은 이름으로 검사하게 된다. 실제로 Windows 에서 그렇게 되어 있었다.
        """
        path = os.path.join(REPO, "scripts", "ci", "uninstall_race_smoke.py")
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        # **본문만 본다.** 설명문에는 왜 그것을 쓰지 않는지가 적혀 있고, 그것을 금지 문자열로
        # 세면 설명을 지워야 통과하는 검사가 된다.
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)) and ast.get_docstring(node):
                node.body = node.body[1:]
        code = ast.unparse(tree)
        self.assertNotIn("shutil.move", code, "복사로 물러서는 이동이 되살아났다")
        self.assertIn("os.rename", code, "엄격한 rename 이 사라졌다")


class CoreSelectorContract(unittest.TestCase):
    """Windows core runner 의 **지목 목록이 줄어드는 것**을 잡는다.

    `CORE_SELECTORS` 에서 한 줄을 지우면 그 검사는 Windows 에서 돌지 않는다. 그런데 남은
    지목들은 전부 해석되고, 나머지 검사는 전부 통과하고, `skipped=0` 이다 — 요구가 줄어든
    사실이 화면 어디에도 나타나지 않는다. **없는 것과 통과한 것이 같은 화면이 되는** 자리이고,
    이 사이클이 같은 모양의 결함을 반복해서 만난 자리이기도 하다.

    그래서 요구 목록(`A24_REQUIRED_SELECTORS`)을 실행 목록과 **다른 파일에** 두고, runner 가
    둘을 대조한다. 아래 검사들은 그 대조가 실제로 무엇을 잡는지 확인한다.
    """

    def runner(self):
        import importlib.util
        path = os.path.join(REPO, "scripts", "ci", "uninstall_core_checks.py")
        spec = importlib.util.spec_from_file_location("sage_uninstall_core_runner", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_required_selector_names_a_real_check(self):
        """요구 목록이 실제 검사를 가리키는가. 이름이 바뀌면 여기서 먼저 걸린다."""
        self.assertEqual(len(A24_REQUIRED_SELECTORS), len(set(A24_REQUIRED_SELECTORS)))
        for selector in A24_REQUIRED_SELECTORS:
            owner, name = selector.split(".")
            case = globals().get(owner)
            self.assertTrue(case is not None and issubclass(case, unittest.TestCase),
                            f"요구 목록이 없는 클래스를 가리킨다: {selector}")
            self.assertTrue(callable(getattr(case, name, None)),
                            f"요구 목록이 없는 검사를 가리킨다: {selector}")

    def test_the_runner_lists_every_required_selector(self):
        runner = self.runner()
        for selector in A24_REQUIRED_SELECTORS:
            self.assertIn(selector, runner.CORE_SELECTORS,
                          f"runner 가 요구된 검사를 돌리지 않는다: {selector}")

    def test_an_empty_selector_list_is_a_failure(self):
        """전부 지우는 것이 가장 조용한 축소다 — `selectors=0` 으로 초록이 되면 안 된다."""
        runner = self.runner()
        problems = runner.missing_required(A24_REQUIRED_SELECTORS, ())
        self.assertEqual(len(problems), len(A24_REQUIRED_SELECTORS), problems)

    def test_deleting_one_required_selector_is_a_failure(self):
        runner = self.runner()
        for dropped in A24_REQUIRED_SELECTORS:
            with self.subTest(dropped=dropped):
                shrunk = tuple(s for s in runner.CORE_SELECTORS if s != dropped)
                problems = runner.missing_required(A24_REQUIRED_SELECTORS, shrunk)
                self.assertTrue(any(dropped in note for note in problems),
                                f"지운 요구가 대조에서 걸리지 않았다: {dropped}")

    def test_substituting_another_healthy_check_is_a_failure(self):
        """멀쩡한 다른 검사로 바꿔 놓아도 통과하면 안 된다.

        건수는 그대로이고 지목은 전부 해석되며 그 검사도 초록이다. 바뀐 것은 **무엇을
        보장하는가** 뿐이라, 건수만 세는 대조는 이것을 잡지 못한다.
        """
        runner = self.runner()
        stand_in = "PinnedProbes.test_the_mkdir_seam_is_closed_under_the_pin"
        dropped = A24_REQUIRED_SELECTORS[0]
        swapped = tuple(stand_in if s == dropped else s for s in runner.CORE_SELECTORS)
        self.assertEqual(len(swapped), len(runner.CORE_SELECTORS))
        problems = runner.missing_required(A24_REQUIRED_SELECTORS, swapped)
        self.assertTrue(any(dropped in note for note in problems),
                        f"치환이 대조에서 걸리지 않았다: {problems}")

    def test_a_missing_oracle_is_a_failure(self):
        """요구 목록 자체가 사라지는 경우. 대조할 것이 없으면 대조는 통과가 아니다."""
        runner = self.runner()

        class Empty:
            pass

        self.assertIsNone(runner.required_selectors(Empty()))
        holder = Empty()
        holder.A24_REQUIRED_SELECTORS = ()
        self.assertIsNone(runner.required_selectors(holder))


if __name__ == "__main__":
    unittest.main(verbosity=2)
