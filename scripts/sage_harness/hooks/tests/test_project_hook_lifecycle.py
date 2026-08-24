#!/usr/bin/env python3
"""Project-authored hook registration and dual-host runtime lifecycle."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from sage.commands import generate as gen  # noqa: E402
from sage.commands import install  # noqa: E402
from sage.commands import validate  # noqa: E402
from sage.install_transaction import DestinationLock, InstallTransaction  # noqa: E402
from sage import __version__  # noqa: E402
from sage.runtime_api import HOOK_RUNTIME_API  # noqa: E402
from test_generate import Args, make_root  # noqa: E402
from test_install import Args as InstallArgs  # noqa: E402

RUNTIME = os.path.join(REPO, "scripts", "sage_harness", "hooks", "runtime")
sys.path.insert(0, RUNTIME)
import run_hook  # noqa: E402


def project_spec(hook_id="demo-project-gate", claude_matcher="Write|Edit|MultiEdit"):
    return f"""---
id: {hook_id}
kind: hook
runtime_bindings:
  claude: {{ event: PreToolUse, matcher: "{claude_matcher}", timeout: 10 }}
  codex: {{ event: PreToolUse, matcher: "apply_patch", timeout: 10 }}
---
## intent
Project gate.
"""


def project_core(status="block", exit_code=2, include_version=True):
    version = 'CONTRACT_VERSION = "1"\n' if include_version else ""
    return (version + "\n"
            "def decide(event, profile, snapshot):\n"
            f"    return {{'status': {status!r}, 'exit_code': {exit_code}, "
            "'message': 'project decision'}\n")


def add_orphan(root, hook_id="demo-project-gate", spec=None, core=None):
    Path(root, "docs", "sage_harness", "hooks", f"{hook_id}.md").write_text(
        spec or project_spec(hook_id), encoding="utf-8")
    Path(root, "scripts", "sage_harness", "hooks", f"{hook_id.replace('-', '_')}_core.py").write_text(
        core or project_core(), encoding="utf-8")


def file_tree(root):
    result = {}
    for base, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            relative = os.path.relpath(path, root)
            result[relative] = (Path(path).read_bytes(), os.stat(path).st_mode & 0o777)
    return result


class TestProjectHookRegistration(unittest.TestCase):
    def test_valid_orphan_registers_every_surface_atomically(self):
        with tempfile.TemporaryDirectory() as root:
            make_root(root)
            add_orphan(root)
            Path(root, "sage").mkdir()
            Path(root, "sage", "project-profile.yaml").write_text(
                "project: { name: lifecycle }\nrisk:\n  l2_path_globs: ['src/**']\n",
                encoding="utf-8")

            rc = gen.run(Args(id="demo-project-gate", target="both", dest=root,
                              root=root, write=True))

            self.assertEqual(rc, 0)
            manifest = json.loads(Path(root, "docs", "sage_harness", ".manifest.json").read_text())
            entry = manifest["assets"]["hooks/demo-project-gate"]
            self.assertEqual(entry["origin"], "project")
            self.assertEqual(entry["form"], "core_adapter")
            self.assertEqual(entry["adapter_contract_version"], "1")
            shutil.copytree(RUNTIME, Path(root, "scripts", "sage_harness", "hooks", "runtime"),
                            dirs_exist_ok=True)
            shutil.copyfile(Path(REPO, "scripts", "sage_harness", "hooks", "cycle_binding.py"),
                            Path(root, "scripts", "sage_harness", "hooks", "cycle_binding.py"))
            shutil.copyfile(Path(REPO, "scripts", "sage_harness", "hooks", "risk_declaration.py"),
                            Path(root, "scripts", "sage_harness", "hooks", "risk_declaration.py"))
            shutil.copyfile(Path(REPO, "scripts", "sage_harness", "hooks", "path_risk.py"),
                            Path(root, "scripts", "sage_harness", "hooks", "path_risk.py"))
            for runtime in ("claude", "codex"):
                with self.subTest(runtime=runtime):
                    self.assertTrue(Path(root, "scripts", "sage_harness", "hooks", "adapters",
                                         runtime, "demo-project-gate.sh").is_file())
                    self.assertTrue(Path(root, f".{runtime}", "hooks", "demo-project-gate.sh").is_file())
                    raw = (json.dumps({"tool_name": "Write", "tool_input": {"file_path": "src/a.py"}})
                           if runtime == "claude" else
                           json.dumps({"tool_name": "apply_patch", "tool_input": {
                               "command": "*** Update File: src/a.py\n+x"}}))
                    env = dict(os.environ, SAGE_PROJECT_ROOT=root, SAGE_PYTHON=sys.executable)
                    result = subprocess.run(
                        [str(Path(root, "scripts", "sage_harness", "hooks", "adapters",
                                  runtime, "demo-project-gate.sh"))],
                        input=raw, capture_output=True, text=True, env=env,
                    )
                    detail = f"stdout={result.stdout!r}, stderr={result.stderr!r}"
                    self.assertEqual(result.returncode, 2, detail)
                    self.assertIn("project decision", result.stderr, detail)
                    self.assertNotIn("Traceback", result.stderr, detail)

    def test_new_project_hook_requires_both_before_first_write(self):
        with tempfile.TemporaryDirectory() as root:
            make_root(root)
            add_orphan(root)
            before = Path(root, "docs", "sage_harness", ".manifest.json").read_bytes()
            err = StringIO()
            with redirect_stderr(err):
                rc = gen.run(Args(id="demo-project-gate", target="claude", dest=root,
                                  root=root, write=True))
            self.assertEqual(rc, 2)
            self.assertIn("--target both", err.getvalue())
            self.assertEqual(Path(root, "docs", "sage_harness", ".manifest.json").read_bytes(), before)
            self.assertFalse(Path(root, "scripts", "sage_harness", "hooks", "adapters",
                                  "claude", "demo-project-gate.sh").exists())

    def test_binding_whitespace_and_missing_contract_are_rejected(self):
        cases = (
            (project_spec(claude_matcher=" Write|Edit"), project_core(), "공백"),
            (project_spec(), project_core(include_version=False), "CONTRACT_VERSION"),
        )
        for spec, core, reason in cases:
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as root:
                make_root(root)
                add_orphan(root, spec=spec, core=core)
                err = StringIO()
                with redirect_stderr(err):
                    rc = gen.run(Args(id="demo-project-gate", target="both", dest=root,
                                      root=root, write=True))
                self.assertEqual(rc, 2)
                self.assertIn(reason, err.getvalue())

    def test_mid_write_failure_rolls_back_manifest_hosts_shims_and_adapters(self):
        # Profile, manifest, two host JSON files, six shims, and two adapters: 12 writes.
        for fail_at in range(1, 13):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as root:
                make_root(root)
                add_orphan(root)
                Path(root, "sage").mkdir()
                Path(root, "sage", "project-profile.yaml").write_text(
                    "project: { name: lifecycle }\nrisk:\n  l2_path_globs: ['src/**']\n",
                    encoding="utf-8",
                )
                before = file_tree(root)
                original_write = gen._oc.write_text_lf
                calls = {"count": 0}

                def fail_write(path, body, mode=None):
                    calls["count"] += 1
                    if calls["count"] == fail_at:
                        raise OSError(f"injected write failure {fail_at}")
                    return original_write(path, body, mode=mode)

                with mock.patch.object(sys, "dont_write_bytecode", True), \
                        mock.patch.object(gen._oc, "write_text_lf", side_effect=fail_write), \
                        redirect_stderr(StringIO()), redirect_stdout(StringIO()):
                    rc = gen.run(Args(id="demo-project-gate", target="both", dest=root,
                                      root=root, write=True))

                self.assertEqual(rc, 1)
                self.assertEqual(calls["count"], fail_at)
                self.assertEqual(file_tree(root), before)

    def test_record_and_output_verification_failures_roll_back(self):
        injections = (
            ("record_output", OSError("record failure")),
            ("verify_outputs", OSError("verify failure")),
        )
        for method, failure in injections:
            with self.subTest(method=method), tempfile.TemporaryDirectory() as root:
                make_root(root)
                add_orphan(root)
                before = file_tree(root)
                with mock.patch.object(InstallTransaction, method, side_effect=failure), \
                        redirect_stderr(StringIO()), redirect_stdout(StringIO()):
                    rc = gen.run(Args(id="demo-project-gate", target="both", dest=root,
                                      root=root, write=True))
                self.assertEqual(rc, 1)
                self.assertEqual(file_tree(root), before)

    def test_busy_destination_fails_before_writes(self):
        with tempfile.TemporaryDirectory() as root:
            make_root(root)
            add_orphan(root)
            before = file_tree(root)
            lock = DestinationLock(root)
            lock.acquire()
            try:
                with redirect_stderr(StringIO()):
                    rc = gen.run(Args(id="demo-project-gate", target="both", dest=root,
                                      root=root, write=True))
            finally:
                lock.release()
            self.assertEqual(rc, 1)
            self.assertEqual(file_tree(root), before)

    def test_preflight_manifest_drift_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            make_root(root)
            add_orphan(root)
            manifest_path = Path(root, "docs", "sage_harness", ".manifest.json")
            original_compile = gen._compile_profile
            changed = {"done": False}

            def drift(*args, **kwargs):
                result = original_compile(*args, **kwargs)
                manifest = json.loads(manifest_path.read_text())
                manifest["external_edit"] = True
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                changed["done"] = True
                return result

            with mock.patch.object(gen, "_compile_profile", side_effect=drift), \
                    redirect_stderr(StringIO()), redirect_stdout(StringIO()):
                rc = gen.run(Args(id="demo-project-gate", target="both", dest=root,
                                  root=root, write=True))
            self.assertEqual(rc, 1)
            self.assertTrue(changed["done"])
            self.assertTrue(json.loads(manifest_path.read_text())["external_edit"])
            self.assertFalse(Path(root, ".claude", "settings.json").exists())
            self.assertFalse(Path(root, "scripts", "sage_harness", "hooks", "adapters",
                                  "claude", "demo-project-gate.sh").exists())

    def test_distributed_template_can_register_a_hook(self):
        with tempfile.TemporaryDirectory() as root:
            make_root(root)
            template = Path(REPO, "templates", "hook.spec.md").read_text(encoding="utf-8")
            spec = template.replace('id: ""', "id: demo-project-gate", 1)
            add_orphan(root, spec=spec)
            rc = gen.run(Args(id="demo-project-gate", target="both", dest=root,
                              root=root, write=True))
            self.assertEqual(rc, 0)

    def test_validate_distinguishes_pending_and_invalid_orphans(self):
        class VArgs:
            kind = "hook"; check = True; schema = False; strict = False; id = None

        for valid in (True, False):
            with self.subTest(valid=valid), tempfile.TemporaryDirectory() as root:
                make_root(root)
                if valid:
                    add_orphan(root)
                else:
                    Path(root, "docs", "sage_harness", "hooks",
                         "demo-project-gate.md").write_text(project_spec(), encoding="utf-8")
                args = VArgs(); args.root = root
                out = StringIO()
                with redirect_stdout(out):
                    rc = validate.run(args)
                if valid:
                    self.assertIn("registration pending", out.getvalue())
                    self.assertIn("--target both", out.getvalue())
                else:
                    self.assertEqual(rc, 1)
                    self.assertIn("등록할 수 없음", out.getvalue())
                    self.assertIn("canonical core", out.getvalue())

    def test_origin_stamp_is_recovered_but_form_corruption_is_rejected(self):
        for corruption in ("origin", "form", "entry"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as root:
                make_root(root)
                add_orphan(root)
                self.assertEqual(gen.run(Args(id="demo-project-gate", target="both", dest=root,
                                              root=root, write=True)), 0)
                manifest_path = Path(root, "docs", "sage_harness", ".manifest.json")
                manifest = json.loads(manifest_path.read_text())
                key = "hooks/demo-project-gate"
                if corruption == "origin":
                    manifest["assets"][key].pop("origin")
                elif corruption == "form":
                    manifest["assets"][key]["form"] = "native"
                else:
                    manifest["assets"][key] = "damaged"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                err = StringIO()
                with redirect_stderr(err), redirect_stdout(StringIO()):
                    hook_id = None if corruption == "origin" else "demo-project-gate"
                    rc = gen.run(Args(id=hook_id, target="both", dest=root,
                                      root=root, write=True))
                if corruption == "origin":
                    self.assertEqual(rc, 0)
                    repaired = json.loads(manifest_path.read_text())
                    self.assertEqual(repaired["assets"][key]["origin"], "project")
                else:
                    self.assertEqual(rc, 2)
                    self.assertIn("form" if corruption == "form" else "object", err.getvalue())

    def test_all_hook_generate_uses_project_contract_not_legacy_binding_parser(self):
        with tempfile.TemporaryDirectory() as root:
            make_root(root)
            add_orphan(root)
            self.assertEqual(gen.run(Args(id="demo-project-gate", target="both", dest=root,
                                          root=root, write=True)), 0)
            manifest_path = Path(root, "docs", "sage_harness", ".manifest.json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["assets"]["hooks/demo-project-gate"].pop("origin")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            spec_path = Path(root, "docs", "sage_harness", "hooks", "demo-project-gate.md")
            spec_path.write_text(
                project_spec().replace('matcher: "apply_patch"', 'matcher: "exec_command"'),
                encoding="utf-8",
            )
            codex_path = Path(root, ".codex", "hooks.json")
            codex_before = codex_path.read_bytes()
            err = StringIO()

            with redirect_stderr(err), redirect_stdout(StringIO()):
                rc = gen.run(Args(id=None, target="both", dest=root, root=root, write=True))

            self.assertEqual(rc, 2)
            self.assertIn("apply_patch", err.getvalue())
            self.assertEqual(codex_path.read_bytes(), codex_before)
            self.assertNotIn("exec_command", codex_path.read_text(encoding="utf-8"))

    def test_install_and_generate_use_canonical_manifest_key_order(self):
        def assert_canonical(path):
            body = Path(path).read_text(encoding="utf-8")
            value = json.loads(body)
            self.assertEqual(
                body,
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            )

        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as codex_home:
            with mock.patch.dict(os.environ, {"CODEX_HOME": codex_home}):
                self.assertEqual(install.run(InstallArgs("claude", root)), 0)
                manifest_path = Path(root, "docs", "sage_harness", ".manifest.json")
                assert_canonical(manifest_path)
                Path(root, "sage", "project-profile.yaml").write_text(
                    "project: { name: lifecycle }\nrisk:\n  l2_path_globs: ['src/**']\n",
                    encoding="utf-8",
                )
                add_orphan(root)
                self.assertEqual(gen.run(Args(id="demo-project-gate", target="both", dest=root,
                                              root=root, write=True)), 0)
                assert_canonical(manifest_path)
                self.assertEqual(install.run(InstallArgs("claude", root, force=True)), 0)
                assert_canonical(manifest_path)

    def test_force_manifest_rebuild_preserves_project_origin_entry(self):
        entry = {
            "origin": "project", "form": "core_adapter", "conformance": "PASS",
            "adapter_contract_version": "1",
        }
        rebuilt = install._manifest(
            "claude", existing={"assets": {"hooks/demo-project-gate": entry}},
            core_renders={}, skill_scope="project-local")
        self.assertEqual(rebuilt["assets"]["hooks/demo-project-gate"], entry)


class TestProjectHookRuntime(unittest.TestCase):
    def _runtime_root(self, core_text=None):
        temp = tempfile.TemporaryDirectory()
        root = temp.name
        os.makedirs(Path(root, "docs", "sage_harness"), exist_ok=True)
        os.makedirs(Path(root, "scripts", "sage_harness", "hooks"), exist_ok=True)
        shutil.copytree(RUNTIME, Path(root, "scripts", "sage_harness", "hooks", "runtime"))
        shutil.copyfile(Path(REPO, "scripts", "sage_harness", "hooks", "cycle_binding.py"),
                        Path(root, "scripts", "sage_harness", "hooks", "cycle_binding.py"))
        shutil.copyfile(Path(REPO, "scripts", "sage_harness", "hooks", "risk_declaration.py"),
                        Path(root, "scripts", "sage_harness", "hooks", "risk_declaration.py"))
        shutil.copyfile(Path(REPO, "scripts", "sage_harness", "hooks", "path_risk.py"),
                        Path(root, "scripts", "sage_harness", "hooks", "path_risk.py"))
        # 이 fixture 는 **정상 설치된** 소비 프로젝트다. 그래서 runtime API marker 를 갖는다 —
        # 1.0 manifest 에서 marker 부재는 legacy 가 아니라 손상이고, `sage-hook` 이 project core
        # 를 import 하기 전에 닫는다. marker 없는 fixture 는 "project 결정이 host 를 막는가" 가
        # 아니라 "손상된 설치가 막히는가" 를 재는 물건이 된다.
        Path(root, "docs", "sage_harness", ".manifest.json").write_text(json.dumps({
            "generator_version": __version__,
            "runtime_api": {"required": HOOK_RUNTIME_API},
            "assets": {"hooks/demo-project-gate": {
                "origin": "project", "form": "core_adapter", "conformance": "PASS",
                "adapter_contract_version": "1",
            }}
        }), encoding="utf-8")
        Path(root, "scripts", "sage_harness", "hooks", "demo_project_gate_core.py").write_text(
            core_text or project_core(), encoding="utf-8")
        profile_dir = Path(root, "sage")
        profile_dir.mkdir()
        Path(profile_dir, "project-profile.yaml").write_text("{}\n", encoding="utf-8")
        profile = Path(profile_dir, "project-profile.json")
        profile.write_text("{}\n", encoding="utf-8")
        return temp, root, str(profile)

    def _raw(self, runtime):
        if runtime == "claude":
            return json.dumps({"tool_name": "Write", "tool_input": {"file_path": "src/a.py"}})
        return json.dumps({"tool_name": "apply_patch", "tool_input": {
            "command": "*** Update File: src/a.py\n+x\n"}})

    def test_registered_project_decision_blocks_both_hosts(self):
        temp, root, profile = self._runtime_root()
        try:
            with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                for runtime in ("claude", "codex"):
                    with self.subTest(runtime=runtime):
                        err = StringIO()
                        with redirect_stderr(err):
                            rc = run_hook.dispatch(runtime, "demo-project-gate", root,
                                                   os.path.join(root, "scripts", "sage_harness", "hooks"),
                                                   self._raw(runtime))
                        self.assertEqual(rc, 2)
                        self.assertIn("project decision", err.getvalue())
        finally:
            temp.cleanup()

    def test_manifest_and_decision_corruption_fail_closed(self):
        cases = (
            (project_core(status="block", exit_code=1), None, "decision"),
            (project_core(), "{", "manifest"),
        )
        for core_text, manifest_text, reason in cases:
            with self.subTest(reason=reason):
                temp, root, profile = self._runtime_root(core_text)
                try:
                    if manifest_text is not None:
                        Path(root, "docs", "sage_harness", ".manifest.json").write_text(manifest_text)
                    with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                        err = StringIO()
                        with redirect_stderr(err):
                            rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                                   os.path.join(root, "scripts", "sage_harness", "hooks"),
                                                   self._raw("codex"))
                    self.assertEqual(rc, 2)
                    self.assertIn(reason, err.getvalue().lower())
                finally:
                    temp.cleanup()

    def test_missing_broken_and_drifted_core_fail_for_the_exact_reason(self):
        cases = ("missing", "broken", "drift")
        for case in cases:
            with self.subTest(case=case):
                temp, root, profile = self._runtime_root()
                try:
                    core_path = Path(root, "scripts", "sage_harness", "hooks",
                                     "demo_project_gate_core.py")
                    if case == "missing":
                        core_path.unlink()
                        expected = "canonical core missing"
                    elif case == "broken":
                        core_path.write_text("not python !!!", encoding="utf-8")
                        expected = "core import failed"
                    else:
                        manifest_path = Path(root, "docs", "sage_harness", ".manifest.json")
                        manifest = json.loads(manifest_path.read_text())
                        manifest["assets"]["hooks/demo-project-gate"]["adapter_contract_version"] = "2"
                        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                        expected = "contract drift"
                    with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                        err = StringIO()
                        with redirect_stderr(err):
                            rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                                   os.path.join(root, "scripts", "sage_harness", "hooks"),
                                                   self._raw("codex"))
                    self.assertEqual(rc, 2)
                    self.assertIn(expected, err.getvalue())
                finally:
                    temp.cleanup()

    def test_malformed_entry_and_extra_decision_field_fail_closed(self):
        extra_decision = (project_core().replace("'message': 'project decision'",
                                                 "'message': 'project decision', 'extra': True"))
        cases = ((None, "entry"), (extra_decision, "exactly"))
        for core_text, reason in cases:
            with self.subTest(reason=reason):
                temp, root, profile = self._runtime_root(core_text)
                try:
                    if core_text is None:
                        path = Path(root, "docs", "sage_harness", ".manifest.json")
                        manifest = json.loads(path.read_text())
                        manifest["assets"]["hooks/demo-project-gate"] = "damaged"
                        path.write_text(json.dumps(manifest), encoding="utf-8")
                    with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                        err = StringIO()
                        with redirect_stderr(err):
                            rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                                   os.path.join(root, "scripts", "sage_harness", "hooks"),
                                                   self._raw("codex"))
                    self.assertEqual(rc, 2)
                    self.assertIn(reason, err.getvalue())
                finally:
                    temp.cleanup()

    def test_project_plan_reads_symlink_escape_is_blocked(self):
        core = (project_core() + "\ndef plan_reads(event, profile):\n"
                "    return {'globs': ['evidence/*']}\n")
        temp, root, profile = self._runtime_root(core)
        outside = tempfile.TemporaryDirectory()
        try:
            Path(outside.name, "secret.txt").write_text("secret", encoding="utf-8")
            Path(root, "evidence").mkdir()
            os.symlink(Path(outside.name, "secret.txt"), Path(root, "evidence", "secret.txt"))
            with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                err = StringIO()
                with redirect_stderr(err):
                    rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                           os.path.join(root, "scripts", "sage_harness", "hooks"),
                                           self._raw("codex"))
            self.assertEqual(rc, 2)
            self.assertIn("outside project root", err.getvalue())
            self.assertNotIn("secret\n", err.getvalue())
        finally:
            outside.cleanup()
            temp.cleanup()

    def test_project_plan_reads_internal_symlink_is_still_blocked(self):
        core = (project_core() + "\ndef plan_reads(event, profile):\n"
                "    return {'globs': ['evidence/link.txt']}\n")
        temp, root, profile = self._runtime_root(core)
        try:
            Path(root, "evidence").mkdir()
            Path(root, "evidence", "source.txt").write_text("inside", encoding="utf-8")
            os.symlink("source.txt", Path(root, "evidence", "link.txt"))
            with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                err = StringIO()
                with redirect_stderr(err):
                    rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                           os.path.join(root, "scripts", "sage_harness", "hooks"),
                                           self._raw("codex"))
            self.assertEqual(rc, 2)
            self.assertIn("matched symlink", err.getvalue())
        finally:
            temp.cleanup()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO contract requires POSIX mkfifo")
    def test_project_plan_reads_non_regular_path_is_blocked_without_reading(self):
        core = (project_core() + "\ndef plan_reads(event, profile):\n"
                "    return {'globs': ['evidence/pipe']}\n")
        temp, root, profile = self._runtime_root(core)
        try:
            Path(root, "evidence").mkdir()
            os.mkfifo(Path(root, "evidence", "pipe"))
            with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                err = StringIO()
                with redirect_stderr(err):
                    rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                           os.path.join(root, "scripts", "sage_harness", "hooks"),
                                           self._raw("codex"))
            self.assertEqual(rc, 2)
            self.assertIn("unsupported non-regular path", err.getvalue())
        finally:
            temp.cleanup()

    def test_project_plan_reads_recursive_glob_skips_directories(self):
        core = ("CONTRACT_VERSION = '1'\n\n"
                "def plan_reads(event, profile):\n"
                "    return {'globs': ['plan_docs/**']}\n\n"
                "def decide(event, profile, snapshot):\n"
                "    valid = (snapshot['glob_results']['plan_docs/**'] == "
                "['plan_docs/00.md'] and snapshot['files']['plan_docs/00.md'] == 'plan')\n"
                "    return {'status': 'ok' if valid else 'block', "
                "'exit_code': 0 if valid else 2, 'message': 'snapshot checked'}\n")
        temp, root, profile = self._runtime_root(core)
        try:
            Path(root, "plan_docs").mkdir()
            Path(root, "plan_docs", "nested").mkdir()
            Path(root, "plan_docs", "00.md").write_text("plan", encoding="utf-8")
            with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                err = StringIO()
                with redirect_stderr(err):
                    rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                           os.path.join(root, "scripts", "sage_harness", "hooks"),
                                           self._raw("codex"))
            self.assertEqual(rc, 0, err.getvalue())
            self.assertIn("snapshot checked", err.getvalue())
        finally:
            temp.cleanup()

    def test_snapshot_shape_is_uniform_without_plan_reads(self):
        # plan_reads 는 선택이지만 snapshot 형태는 선택이 아니다. 부재 시 {} 를 주면
        # core 의 snapshot['files'] 가 KeyError 로 죽고 저작자는 SAGE 내부 버그로 안내받는다.
        core = ("CONTRACT_VERSION = '1'\n\n"
                "def decide(event, profile, snapshot):\n"
                "    valid = snapshot['glob_results'] == {} and snapshot['files'] == {}\n"
                "    return {'status': 'ok' if valid else 'block', "
                "'exit_code': 0 if valid else 2, 'message': 'snapshot shape checked'}\n")
        temp, root, profile = self._runtime_root(core)
        try:
            with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                err = StringIO()
                with redirect_stderr(err):
                    rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                           os.path.join(root, "scripts", "sage_harness", "hooks"),
                                           self._raw("codex"))
            self.assertEqual(rc, 0, err.getvalue())
            self.assertIn("snapshot shape checked", err.getvalue())
        finally:
            temp.cleanup()

    def test_plan_reads_without_globs_key_is_author_contract_failure(self):
        # {} 반환은 계약 위반인데 통과했다. 차단하되 저작자가 고칠 수 있는 오류로 안내해야 한다.
        core = ("CONTRACT_VERSION = '1'\n\n"
                "def plan_reads(event, profile):\n"
                "    return {}\n\n"
                "def decide(event, profile, snapshot):\n"
                "    return {'status': 'ok', 'exit_code': 0, 'message': 'reached decide'}\n")
        temp, root, profile = self._runtime_root(core)
        try:
            with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                err = StringIO()
                with redirect_stderr(err):
                    rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                           os.path.join(root, "scripts", "sage_harness", "hooks"),
                                           self._raw("codex"))
            self.assertEqual(rc, 2)
            self.assertIn("plan_reads must return", err.getvalue())
            self.assertIn("project hook contract failure", err.getvalue())
            self.assertNotIn("internal dispatch failure", err.getvalue())
            self.assertNotIn("reached decide", err.getvalue())
        finally:
            temp.cleanup()

    def test_codex_move_destination_reaches_project_event_changes(self):
        # project hook 도 Phase04 추출기를 쓴다. 이동 목적지가 빠지면 project 게이트도 함께
        # 눈이 멀고, 원본이 실리면 04 밖으로 빼는 작업이 작성으로 오인된다(J-10).
        core = ("CONTRACT_VERSION = '1'\n\n"
                "def decide(event, profile, snapshot):\n"
                "    seen = sorted((c['path'], c['op']) for c in event['changes'])\n"
                "    return {'status': 'ok', 'exit_code': 0, 'message': repr(seen)}\n")
        temp, root, profile = self._runtime_root(core)
        try:
            raw = json.dumps({"tool_name": "apply_patch", "tool_input": {
                "command": "*** Update File: docs/scratch.md\n*** Move to: plan_docs/04-analyze/x.md\n+x\n"}})
            with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                err = StringIO()
                with redirect_stderr(err):
                    rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                           os.path.join(root, "scripts", "sage_harness", "hooks"), raw)
            self.assertEqual(rc, 0, err.getvalue())
            self.assertIn("('plan_docs/04-analyze/x.md', 'move')", err.getvalue())
            # 이동 원본은 문서가 생기는 경로가 아니다 — 실리면 move-out 오탐의 재료가 된다.
            self.assertNotIn("docs/scratch.md", err.getvalue())
        finally:
            temp.cleanup()

    def test_external_core_dir_cannot_replace_registered_project_core(self):
        temp, root, profile = self._runtime_root()
        outside = tempfile.TemporaryDirectory()
        try:
            Path(root, "scripts", "sage_harness", "hooks", "demo_project_gate_core.py").unlink()
            Path(outside.name, "demo_project_gate_core.py").write_text(
                project_core(status="ok", exit_code=0), encoding="utf-8")
            with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                err = StringIO()
                with redirect_stderr(err):
                    rc = run_hook.dispatch("codex", "demo-project-gate", root, outside.name,
                                           self._raw("codex"))
            self.assertEqual(rc, 2)
            self.assertIn("canonical core missing", err.getvalue())
        finally:
            outside.cleanup()
            temp.cleanup()

    def test_unregistered_unknown_id_preserves_version_skew_exit_zero(self):
        temp, root, profile = self._runtime_root()
        try:
            with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                self.assertEqual(run_hook.dispatch("codex", "future-hook", root,
                                                   os.path.join(root, "scripts", "sage_harness", "hooks"),
                                                   self._raw("codex")), 0)
        finally:
            temp.cleanup()

    def test_registered_project_hook_without_compiled_profile_fails_closed(self):
        temp, root, profile = self._runtime_root()
        try:
            Path(profile).unlink()
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("SAGE_PROFILE", None)
                err = StringIO()
                with redirect_stderr(err):
                    rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                           os.path.join(root, "scripts", "sage_harness", "hooks"),
                                           self._raw("codex"))
            self.assertEqual(rc, 2)
            self.assertIn("compiled profile is missing", err.getvalue())
        finally:
            temp.cleanup()

    def test_profile_contract_errors_are_not_reported_as_internal_failures(self):
        """저작자가 고칠 수 있는 profile 계약 오류를 SAGE 내부 버그로 표시하면 고칠 곳을 못 찾는다."""
        cases = {
            "malformed json": "{ broken",
            "checklist 계약 위반": json.dumps({"checklist_scan_targets": ["plan_docs/*.md"]}),
        }
        for reason, body in cases.items():
            with self.subTest(reason=reason):
                temp, root, profile = self._runtime_root()
                try:
                    Path(profile).write_text(body, encoding="utf-8")
                    with mock.patch.dict(os.environ, {"SAGE_PROFILE": profile}):
                        err = StringIO()
                        with redirect_stderr(err):
                            rc = run_hook.dispatch("codex", "demo-project-gate", root,
                                                   os.path.join(root, "scripts", "sage_harness", "hooks"),
                                                   self._raw("codex"))
                    self.assertEqual(rc, 2)
                    self.assertIn("profile contract failure", err.getvalue())
                    self.assertNotIn("internal dispatch failure", err.getvalue())
                finally:
                    temp.cleanup()

    def test_sage_hook_console_entrypoint_blocks_both_hosts(self):
        temp, root, _profile = self._runtime_root()
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = REPO + os.pathsep + env.get("PYTHONPATH", "")
            core_dir = os.path.join(root, "scripts", "sage_harness", "hooks")
            for runtime in ("claude", "codex"):
                with self.subTest(runtime=runtime):
                    result = subprocess.run(
                        [sys.executable, "-m", "sage.hook_entry", "--runtime", runtime,
                         "--hook", "demo-project-gate", "--root", root,
                         "--core-dir", core_dir],
                        input=self._raw(runtime), capture_output=True, text=True, env=env,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("project decision", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main(verbosity=2)
