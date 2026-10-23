#!/usr/bin/env python3
import contextlib
from datetime import date
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)

from sage import context_packet  # noqa: E402
from sage.cli import main as cli_main  # noqa: E402
from sage.context_packet import ContextError, create_snapshot, restore_snapshot  # noqa: E402
from sage.profile_validate import severity_of, validate_profile  # noqa: E402


def _skip_on_windows_open(test):
    """부모 fd(`dir_fd`) 호출에 주입하는 시험. Windows 열기 분기에는 그 호출이 없다."""
    def wrapper(self):
        if context_packet._WINDOWS_OPEN:
            self.skipTest("dir_fd 주입 시험 — Windows 열기 분기는 TestContextPacketWindowsOpen 이 본다")
        return test(self)
    wrapper.__name__ = test.__name__
    wrapper.__doc__ = test.__doc__
    return wrapper


class TestContextPacket(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = {
            "project": {"name": "Example", "prefix": "example"},
            "risk": {"l2_path_globs": ["sage/**"]},
            "pdca": {
                "enabled": True,
                "phases": [
                    {"id": "00", "glob": "plan_docs/00-base_plan/**/*.md"},
                    {"id": "01", "glob": "plan_docs/01-plan/**/*.md"},
                    {"id": "02", "glob": "plan_docs/02-design/**/*.md"},
                    {"id": "03", "glob": "plan_docs/03-implementation/**/*.md"},
                    {"id": "04", "glob": "plan_docs/04-analyze/**/*.md"},
                    {"id": "05", "glob": "plan_docs/05-expert-review/**/*.md"},
                    {"id": "06", "glob": "plan_docs/06-report/**/*.md"},
                ],
            },
            "runtime": {
                "installed_hosts": ["claude", "codex"],
                "active_host": "claude",
                "external_reviewer": "opposite_runtime",
            },
            "context_management": {
                "compaction": {
                    "enabled": True,
                    "preserve": [
                        "architectural_decisions",
                        "open_bugs",
                        "file_ownership",
                        "pending_verifications",
                    ],
                    "max_snapshot_bytes": 1048576,
                }
            },
        }
        self._write_profile()
        self._write_phase("00", "00-base_plan", "# Base\n\nRisk Level: L3\n")
        self._write_phase("01", "01-plan", "# Plan\n\n| ID | Required |\n")
        self._write_phase("02", "02-design", "# Design\n\nDecision: portable packet\n")
        manifest = {"sage_version": "test", "installed_hosts": ["claude", "codex"]}
        self._write("docs/sage_harness/.manifest.json", json.dumps(manifest))

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _write_profile(self):
        self._write("sage/project-profile.yaml", yaml.safe_dump(self.profile, sort_keys=False))

    def _write_phase(self, phase, directory, body, nested=""):
        relative = f"plan_docs/{directory}/{nested}sandbox-cycle.md"
        return self._write(relative, f"Cycle-Stem: `sandbox-cycle`\n\n{body}")

    def _snapshot(self):
        return create_snapshot(
            self.root,
            "sandbox-cycle",
            "02",
            created_at="2026-07-17T06:00:00.000000Z",
        )

    def test_snapshot_and_restore_materialize_verified_preserved_context(self):
        made = self._snapshot()
        packet_path = Path(made["path"])
        self.assertTrue(packet_path.is_file())
        self.assertIn(".sage/context/snapshots/sandbox-cycle/02-ctx-", packet_path.as_posix())

        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        self.assertEqual(packet["payload"]["cycle"]["completed_phase"], "02")
        self.assertEqual(packet["payload"]["runtime"]["active_host"], "claude")
        self.assertEqual([item["phase"] for item in packet["payload"]["phase_docs"]], ["00", "01", "02"])
        self.assertNotIn("Decision: portable packet", packet_path.read_text(encoding="utf-8"))
        self.assertNotIn(str(self.root), packet_path.read_text(encoding="utf-8"))

        restored = restore_snapshot(self.root, packet_path)
        briefing = Path(restored["path"]).read_text(encoding="utf-8")
        self.assertEqual(restored["from_host"], "claude")
        self.assertEqual(restored["to_host"], "claude")
        self.assertEqual(restored["next_phase"], "03")
        self.assertIn("architectural_decisions", briefing)
        self.assertIn("Decision: portable packet", briefing)
        self.assertIn("source_sha256", briefing)

    def test_restore_reads_legacy_v1_packet_without_document_language(self):
        made = self._snapshot()
        current = Path(made["path"])
        packet = json.loads(current.read_text(encoding="utf-8"))
        packet["schema_version"] = 1
        del packet["payload"]["cycle"]["document_language"]

        import hashlib
        core = {key: packet[key] for key in ("schema_version", "created_at", "payload")}
        canonical = json.dumps(
            core, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        packet["integrity_sha256"] = "sha256:" + digest
        packet["snapshot_id"] = "ctx-" + digest[:16]
        legacy = current.parent / f"02-{packet['snapshot_id']}.json"
        legacy.write_text(json.dumps(packet), encoding="utf-8")

        restored = restore_snapshot(self.root, legacy)
        self.assertIsNone(restored["document_language"])
        self.assertEqual(restored["next_phase"], "03")

    def test_snapshot_requires_every_phase_through_completed_boundary(self):
        (self.root / "plan_docs/01-plan/sandbox-cycle.md").unlink()

        with self.assertRaisesRegex(ContextError, "missing through completed boundary.*01"):
            self._snapshot_at("2026-07-17T06:00:00.500000Z")

    def test_restore_accepts_only_active_host_alias_change_for_manual_handoff(self):
        made = self._snapshot()
        self.profile["runtime"]["active_host"] = "codex"
        self._write_profile()

        restored = restore_snapshot(self.root, made["path"])
        self.assertEqual((restored["from_host"], restored["to_host"]), ("claude", "codex"))
        self.assertTrue(restored["host_handoff"])

        self.profile["risk"]["l2_path_globs"].append("changed/**")
        self._write_profile()
        with self.assertRaisesRegex(ContextError, "profile semantic binding"):
            restore_snapshot(self.root, made["path"])

    def test_restore_rejects_packet_phase_and_manifest_tampering_without_output(self):
        made = self._snapshot()
        packet_path = Path(made["path"])

        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        packet["payload"]["cycle"]["completed_phase"] = "01"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        with self.assertRaisesRegex(ContextError, "integrity"):
            restore_snapshot(self.root, packet_path)

        made = self._snapshot_at("2026-07-17T06:00:01.000000Z")
        self._write_phase("02", "02-design", "# Design\n\nTampered\n")
        with self.assertRaisesRegex(ContextError, "phase document binding"):
            restore_snapshot(self.root, made["path"])

        self._write_phase("02", "02-design", "# Design\n\nDecision: portable packet\n")
        made = self._snapshot_at("2026-07-17T06:00:02.000000Z")
        self._write("docs/sage_harness/.manifest.json", "{}")
        with self.assertRaisesRegex(ContextError, "manifest binding"):
            restore_snapshot(self.root, made["path"])

        restored_dir = self.root / ".sage/context/restored"
        self.assertFalse(restored_dir.exists())

    def _snapshot_at(self, created_at):
        return create_snapshot(self.root, "sandbox-cycle", "02", created_at=created_at)

    def test_snapshot_rejects_disabled_duplicate_symlink_and_oversized_sources(self):
        self.profile["context_management"]["compaction"]["enabled"] = False
        self._write_profile()
        with self.assertRaisesRegex(ContextError, "disabled"):
            self._snapshot()

        self.profile["context_management"]["compaction"]["enabled"] = True
        self._write_profile()
        self._write_phase("02", "02-design", "# Duplicate\n", nested="nested/")
        with self.assertRaisesRegex(ContextError, "ambiguous"):
            self._snapshot()

        (self.root / "plan_docs/02-design/nested/sandbox-cycle.md").unlink()
        phase = self.root / "plan_docs/02-design/sandbox-cycle.md"
        target = self._write("outside.md", "Cycle-Stem: `sandbox-cycle`\n")
        phase.unlink()
        phase.symlink_to(target)
        with self.assertRaisesRegex(ContextError, "symlink"):
            self._snapshot()

        phase.unlink()
        self._write_phase("02", "02-design", "x" * 2048)
        self.profile["context_management"]["compaction"]["max_snapshot_bytes"] = 1024
        self._write_profile()
        with self.assertRaisesRegex(ContextError, "byte budget"):
            self._snapshot()

    def test_restore_rejects_snapshot_outside_managed_directory(self):
        made = self._snapshot()
        outside = self.root / "packet.json"
        outside.write_bytes(Path(made["path"]).read_bytes())
        with self.assertRaisesRegex(ContextError, "managed snapshot directory"):
            restore_snapshot(self.root, outside)

    def test_restore_rejects_rehashed_malformed_cycle_without_traceback(self):
        made = self._snapshot()
        packet_path = Path(made["path"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        packet["payload"]["cycle"]["stem"] = ["not", "a", "stem"]
        core = {key: packet[key] for key in ("schema_version", "created_at", "payload")}
        import hashlib
        canonical = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        packet["integrity_sha256"] = "sha256:" + digest
        packet["snapshot_id"] = "ctx-" + digest[:16]
        malformed = packet_path.parent / f"02-{packet['snapshot_id']}.json"
        malformed.write_text(json.dumps(packet), encoding="utf-8")
        with self.assertRaisesRegex(ContextError, "malformed context packet cycle"):
            restore_snapshot(self.root, malformed)

        packet = json.loads(Path(made["path"]).read_text(encoding="utf-8"))
        packet["payload"]["runtime"]["installed_hosts"] = [["codex"]]
        core = {key: packet[key] for key in ("schema_version", "created_at", "payload")}
        canonical = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        packet["integrity_sha256"] = "sha256:" + digest
        packet["snapshot_id"] = "ctx-" + digest[:16]
        malformed = packet_path.parent / f"02-{packet['snapshot_id']}.json"
        malformed.write_text(json.dumps(packet), encoding="utf-8")
        with self.assertRaisesRegex(ContextError, "runtime host binding"):
            restore_snapshot(self.root, malformed)

    def test_restore_rejects_rehashed_phase_sequence_and_next_phase_tampering(self):
        made = self._snapshot()

        def rehashed_packet(mutate):
            packet = json.loads(Path(made["path"]).read_text(encoding="utf-8"))
            mutate(packet)
            core = {key: packet[key] for key in ("schema_version", "created_at", "payload")}
            import hashlib
            canonical = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            digest = hashlib.sha256(canonical).hexdigest()
            packet["integrity_sha256"] = "sha256:" + digest
            packet["snapshot_id"] = "ctx-" + digest[:16]
            path = Path(made["path"]).parent / f"02-{packet['snapshot_id']}.json"
            path.write_text(json.dumps(packet), encoding="utf-8")
            return path

        missing_phase = rehashed_packet(lambda packet: packet["payload"]["phase_docs"].pop(1))
        with self.assertRaisesRegex(ContextError, "phase sequence"):
            restore_snapshot(self.root, missing_phase)

        wrong_next = rehashed_packet(
            lambda packet: packet["payload"]["cycle"].__setitem__("next_phase", "05"))
        with self.assertRaisesRegex(ContextError, "next phase"):
            restore_snapshot(self.root, wrong_next)

    def test_restore_uses_a_fence_longer_than_source_fence(self):
        self._write_phase("02", "02-design", "# Design\n\n~~~~markdown\ninner\n~~~~\n")
        made = self._snapshot()
        restored = restore_snapshot(self.root, made["path"])
        briefing = Path(restored["path"]).read_text(encoding="utf-8")
        self.assertIn("~~~~~markdown\nCycle-Stem", briefing)
        self.assertIn("\n~~~~~\n", briefing)

    def test_cli_registers_snapshot_and_restore(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli_main([
                "context", "snapshot", "--root", str(self.root),
                "--cycle-stem", "sandbox-cycle", "--phase", "02",
            ])
        self.assertEqual(rc, 0)
        snapshot_path = stdout.getvalue().splitlines()[0]
        self.assertTrue(Path(snapshot_path).is_file())

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = cli_main(["context", "restore", "--root", str(self.root), "--snapshot", snapshot_path])
        self.assertEqual(rc, 0)
        self.assertTrue(Path(stdout.getvalue().splitlines()[0]).is_file())

    def test_context_profile_contract_fails_closed_without_jsonschema(self):
        bad_values = [
            "enabled",
            {"compaction": "on"},
            {"compaction": {"enabled": "true", "preserve": ["open_bugs"]}},
            {"compaction": {"enabled": True, "preserve": "open_bugs"}},
            {"compaction": {"enabled": True, "preserve": ["unknown"]}},
            {"compaction": {"enabled": True, "preserve": []}},
            {"compaction": {"enabled": True, "preserve": ["open_bugs", "open_bugs"]}},
            {"compaction": {"enabled": True, "preserve": ["open_bugs"], "max_snapshot_bytes": 12}},
            {"compaction": {"enabled": True, "preserve": ["open_bugs"], "extra": True}},
        ]
        for bad in bad_values:
            profile = dict(self.profile)
            profile["context_management"] = bad
            self.assertEqual(severity_of(validate_profile(profile, REPO)), "FAIL", bad)

    def test_snapshot_rejects_malformed_project_and_runtime_as_context_errors(self):
        original = json.loads(json.dumps(self.profile))
        for mutation in ("project", "runtime"):
            profile = json.loads(json.dumps(original))
            if mutation == "project":
                profile["project"] = "Example"
            else:
                profile["runtime"]["installed_hosts"] = [["codex"]]
            self.profile = profile
            self._write_profile()
            with self.subTest(mutation=mutation):
                with self.assertRaises(ContextError):
                    self._snapshot_at(f"2026-07-17T06:00:0{3 if mutation == 'project' else 4}.000000Z")

    def test_snapshot_rejects_non_json_yaml_scalars_as_context_error(self):
        self.profile["options"] = {"release_date": date(2026, 7, 17)}
        self._write_profile()

        with self.assertRaisesRegex(ContextError, "JSON-compatible"):
            self._snapshot_at("2026-07-17T06:00:05.000000Z")

    @_skip_on_windows_open
    def test_snapshot_rejects_source_replaced_during_secure_open(self):
        phase = self.root / "plan_docs/02-design/sandbox-cycle.md"
        replacement = self._write(
            "replacement.md",
            "Cycle-Stem: `sandbox-cycle`\n\n# Replaced after metadata check\n",
        )
        real_open = os.open
        swapped = False

        def swapping_open(path, flags, *args, **kwargs):
            nonlocal swapped
            directory_fd = kwargs.get("dir_fd")
            parent_stat = os.stat(phase.parent)
            opened_parent = os.fstat(directory_fd) if directory_fd is not None else None
            if (not swapped and path == phase.name and opened_parent is not None
                    and (opened_parent.st_dev, opened_parent.st_ino)
                    == (parent_stat.st_dev, parent_stat.st_ino)):
                os.replace(replacement, phase)
                swapped = True
            return real_open(path, flags, *args, **kwargs)

        with mock.patch("sage.context_packet.os.open", side_effect=swapping_open):
            with self.assertRaisesRegex(ContextError, "changed during secure open"):
                self._snapshot_at("2026-07-17T06:00:06.000000Z")
        self.assertTrue(swapped, "교체 주입이 발동하지 않았다")

    @_skip_on_windows_open
    def test_snapshot_rejects_ancestor_replaced_with_symlink_during_secure_open(self):
        phase_dir = self.root / "plan_docs/02-design"
        original_dir = self.root / "plan_docs/02-design-original"
        outside = self.root.parent / f"{self.root.name}-outside"
        outside.mkdir()
        (outside / "sandbox-cycle.md").write_text(
            "Cycle-Stem: `sandbox-cycle`\n\n# Outside source\n", encoding="utf-8")
        real_open = os.open
        swapped = False

        def swapping_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if not swapped and path == "02-design" and kwargs.get("dir_fd") is not None:
                phase_dir.rename(original_dir)
                phase_dir.symlink_to(outside, target_is_directory=True)
                swapped = True
            return real_open(path, flags, *args, **kwargs)

        try:
            with mock.patch("sage.context_packet.os.open", side_effect=swapping_open):
                with self.assertRaisesRegex(ContextError, "secure read failed"):
                    self._snapshot_at("2026-07-17T06:00:07.000000Z")
            self.assertTrue(swapped, "교체 주입이 발동하지 않았다")
        finally:
            if phase_dir.is_symlink():
                phase_dir.unlink()
            if original_dir.exists():
                original_dir.rename(phase_dir)
            if outside.exists():
                for child in outside.iterdir():
                    child.unlink()
                outside.rmdir()


class TestContextPacketWindowsOpen(TestContextPacket):
    """#28 — 같은 계약을 **Windows 열기 분기**로 다시 본다.

    Windows 는 폴더를 `os.open` 으로 열 수 없고 `dir_fd` 도 없어 부모 fd 결속 읽기가 항상
    실패했다. Windows 분기는 경로로 열고 열기 전 `lstat` 과 열린 `fstat` 의 identity 를 대조한다.
    쓰는 API 가 POSIX 에도 있으므로 분기를 강제해 위의 모든 시험을 이 분기로 한 번 더 돌린다.
    `dir_fd` 에 주입하는 두 시험은 건너뛰고, 같은 뜻의 시험을 아래에 둔다.
    """

    def setUp(self):
        forced = mock.patch("sage.context_packet._WINDOWS_OPEN", True)
        forced.start()
        self.addCleanup(forced.stop)
        super().setUp()

    def _phase(self):
        return self.root / "plan_docs/02-design/sandbox-cycle.md"

    def test_windows_open_rejects_a_leaf_replaced_between_check_and_open(self):
        phase = self._phase()
        replacement = self._write(
            "replacement.md", "Cycle-Stem: `sandbox-cycle`\n\n# Replaced after lstat\n")
        real_open = os.open
        swapped = []

        def swapping_open(path, flags, *args, **kwargs):
            if not swapped and os.path.realpath(path) == os.path.realpath(phase):
                os.replace(replacement, phase)
                swapped.append(True)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch("sage.context_packet.os.open", side_effect=swapping_open):
            with self.assertRaisesRegex(ContextError, "changed during secure open"):
                self._snapshot_at("2026-07-17T06:00:08.000000Z")
        self.assertEqual(swapped, [True], "교체 주입이 발동하지 않았다")

    def _on_phase_read(self, action):
        """phase 문서를 읽는 첫 `os.read` 에서 `action` 을 한 번 실행한다."""
        phase_id = os.stat(self._phase()).st_ino
        real_read = os.read
        fired = []

        def reading(fd, size):
            if not fired and os.fstat(fd).st_ino == phase_id:
                action()
                fired.append(True)
            return real_read(fd, size)

        return mock.patch("sage.context_packet.os.read", side_effect=reading), fired

    def test_windows_open_rejects_an_ancestor_left_as_a_link_after_reading(self):
        """열린 파일은 진짜지만, 읽는 동안 조상이 링크로 바뀐 채 남았다면 그 결과를 쓰지 않는다."""
        if os.name == "nt":
            self.skipTest("실제 Windows 는 열린 파일의 조상 이름 변경을 막아 이 교체가 성립하지 않는다")
        phase_dir = self._phase().parent
        moved = self.root / "plan_docs/02-design-original"
        outside = Path(tempfile.mkdtemp())
        (outside / "sandbox-cycle.md").write_text(
            "Cycle-Stem: `sandbox-cycle`\n\n# Outside\n", encoding="utf-8")

        def swap():
            phase_dir.rename(moved)
            phase_dir.symlink_to(outside, target_is_directory=True)

        patched, fired = self._on_phase_read(swap)
        try:
            with patched:
                with self.assertRaisesRegex(ContextError, "symlink path"):
                    self._snapshot_at("2026-07-17T06:00:09.000000Z")
            self.assertEqual(fired, [True], "교체 주입이 발동하지 않았다")
        finally:
            if phase_dir.is_symlink():
                phase_dir.unlink()
            if moved.exists():
                moved.rename(phase_dir)

    def test_windows_open_detects_a_change_while_reading(self):
        def append():
            with open(self._phase(), "a", encoding="utf-8") as handle:
                handle.write("appended during read\n")

        patched, fired = self._on_phase_read(append)
        with patched:
            with self.assertRaisesRegex(ContextError, "changed while being read"):
                self._snapshot_at("2026-07-17T06:00:10.000000Z")
        self.assertEqual(fired, [True], "변경 주입이 발동하지 않았다")

    def test_windows_failure_carries_a_report_line_without_absolute_paths(self):
        """이슈에 그대로 붙일 수 있게 — 사용자 이름·프로젝트 이름이 든 절대 경로는 넣지 않는다."""
        phase = self._phase()
        real_open = os.open

        def denied(path, flags, *args, **kwargs):
            if os.path.realpath(path) == os.path.realpath(phase):
                raise PermissionError(13, "Access is denied")
            return real_open(path, flags, *args, **kwargs)

        with mock.patch("sage.context_packet.os.open", side_effect=denied):
            with self.assertRaises(ContextError) as raised:
                self._snapshot_at("2026-07-17T06:00:11.000000Z")
        message = str(raised.exception)
        self.assertIn("[report:", message)
        report = message[message.index("[report:"):]
        for needle in ("stage=open", "error=PermissionError", "errno=13",
                       "path=plan_docs/02-design/sandbox-cycle.md", "python="):
            self.assertIn(needle, report)
        self.assertNotIn(str(self.root), report)
        self.assertNotIn(os.path.realpath(self.root), report)
        self.assertNotIn(str(Path.home()), report)

    def test_windows_creates_context_folders_without_a_private_mode(self):
        """0o700 은 Windows 에서 「만든 주체만」 ACL 이 된다 — 관리자로 처음 만들면 일반 권한이 못 쓴다."""
        modes = []
        real_mkdir = Path.mkdir

        def spy(path_self, *args, **kwargs):
            modes.append(kwargs.get("mode", args[0] if args else None))
            return real_mkdir(path_self, *args, **kwargs)

        with mock.patch.object(Path, "mkdir", spy):
            self._snapshot_at("2026-07-17T06:00:12.000000Z")
        self.assertTrue(modes, "전제: context 폴더를 새로 만들었어야 한다")
        self.assertNotIn(0o700, modes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
