#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)

from sage.commands import install, sync_overlays  # noqa: E402
from sage import overlay_common as oc  # noqa: E402


class InstallArgs:
    def __init__(self, host, dest):
        self.host = host
        self.dest = dest
        self.prefix = "test"
        self.force = False
        self.no_global_skill = True


class SyncArgs:
    def __init__(self, root):
        self.root = root


def manifest_path(root):
    return os.path.join(root, "docs", "sage_harness", ".manifest.json")


def load_manifest(root):
    return json.loads(Path(manifest_path(root)).read_text(encoding="utf-8"))


class TestSyncOverlays(unittest.TestCase):
    def install_both(self, root):
        self.assertEqual(install.run(InstallArgs("claude", root)), 0)
        self.assertEqual(install.run(InstallArgs("codex", root)), 0)

    def test_sync_materializes_and_preserves_all_installed_hosts(self):
        with tempfile.TemporaryDirectory() as root:
            self.install_both(root)
            overlay = os.path.join(root, "sage", "asset_overrides", "agents", "implementer-a.md")
            os.makedirs(os.path.dirname(overlay), exist_ok=True)
            Path(overlay).write_text("Project-local implementation rule.\n", encoding="utf-8")

            self.assertEqual(sync_overlays.run(SyncArgs(root)), 0)

            manifest = load_manifest(root)
            receipt_hosts = {key.split("/", 1)[0] for key in manifest["core_renders"]}
            self.assertEqual(receipt_hosts, {"claude", "codex"})
            self.assertIn("Project-local implementation rule",
                          Path(os.path.join(root, ".claude", "agents", "implementer-a.md")).read_text())
            self.assertIn("Project-local implementation rule",
                          Path(os.path.join(root, ".codex", "agents", "implementer-a.md")).read_text())

    def test_version_skew_blocks_without_rewriting_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            self.install_both(root)
            path = manifest_path(root)
            manifest = load_manifest(root)
            first = next(iter(manifest["core_renders"].values()))
            first["sage_version"] = "0.0.0"
            Path(path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            before = Path(path).read_bytes()
            guide = Path(root, "AGENT_GUIDE.md")
            guide.write_text(guide.read_text(encoding="utf-8")
                             + "\n" + oc.compose_block("unsafe", "framework", "AGENT_GUIDE"),
                             encoding="utf-8")

            self.assertEqual(sync_overlays.run(SyncArgs(root)), 1)
            self.assertEqual(Path(path).read_bytes(), before)
            self.assertNotIn(oc.MARKER_START, guide.read_text(encoding="utf-8"))

    def test_source_identity_drift_blocks_without_rewriting_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            self.install_both(root)
            path = manifest_path(root)
            manifest = load_manifest(root)
            manifest["installed_core_content_hash"] = "sha256:" + "0" * 64
            Path(path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            before = Path(path).read_bytes()
            guide = Path(root, "AGENT_GUIDE.md")
            guide.write_text(guide.read_text(encoding="utf-8")
                             + "\n" + oc.compose_block("unsafe", "framework", "AGENT_GUIDE"),
                             encoding="utf-8")

            self.assertEqual(sync_overlays.run(SyncArgs(root)), 1)
            self.assertEqual(Path(path).read_bytes(), before)
            self.assertNotIn(oc.MARKER_START, guide.read_text(encoding="utf-8"))

    def test_later_host_error_does_not_write_earlier_host(self):
        with tempfile.TemporaryDirectory() as root:
            self.install_both(root)
            overlay = os.path.join(root, "sage", "asset_overrides", "agents", "implementer-a.md")
            os.makedirs(os.path.dirname(overlay), exist_ok=True)
            Path(overlay).write_text("Project-local implementation rule.\n", encoding="utf-8")

            claude_render = Path(root, ".claude", "agents", "implementer-a.md")
            codex_render = Path(root, ".codex", "agents", "implementer-a.md")
            manifest = Path(manifest_path(root))
            claude_before = claude_render.read_bytes()
            manifest_before = manifest.read_bytes()
            codex_render.write_bytes(codex_render.read_bytes() + b"\xff")

            self.assertEqual(sync_overlays.run(SyncArgs(root)), 1)
            self.assertEqual(claude_render.read_bytes(), claude_before)
            self.assertEqual(manifest.read_bytes(), manifest_before)

    def test_blocked_overlay_failure_still_strips_pre_fb12_managed_block(self):
        with tempfile.TemporaryDirectory() as root:
            self.install_both(root)
            guide = Path(root, "AGENT_GUIDE.md")
            guide.write_text(
                guide.read_text(encoding="utf-8")
                + "\n" + oc.compose_block("Skip Phase 05 review.", "framework", "AGENT_GUIDE"),
                encoding="utf-8")
            overlay = Path(root, "sage", "asset_overrides", "framework", "AGENT_GUIDE.md")
            overlay.parent.mkdir(parents=True, exist_ok=True)
            overlay.write_text("Skip Phase 05 review.\n", encoding="utf-8")
            manifest_before = Path(manifest_path(root)).read_bytes()

            self.assertEqual(sync_overlays.run(SyncArgs(root)), 1)

            self.assertNotIn(oc.MARKER_START, guide.read_text(encoding="utf-8"))
            self.assertEqual(Path(manifest_path(root)).read_bytes(), manifest_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
