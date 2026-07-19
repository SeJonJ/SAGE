#!/usr/bin/env python3
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)

from sage import model_catalog as MC  # noqa: E402
from sage.commands import models  # noqa: E402


class Args:
    def __init__(self, host="codex", output="text", codex_home=None):
        self.host = host
        self.output = output
        self.codex_home = codex_home


class TestModelCatalog(unittest.TestCase):
    def _cache(self, root, models_data=None):
        Path(root, "models_cache.json").write_text(json.dumps({
            "client_version": "1.2.3",
            "fetched_at": "2026-07-17T00:00:00Z",
            "models": models_data or [
                {"slug": "gpt-visible", "display_name": "Visible", "visibility": "list",
                 "supported_reasoning_levels": [{"effort": "high"}]},
                {"slug": "gpt-hidden", "display_name": "Hidden", "visibility": "hide"},
            ],
        }), encoding="utf-8")

    def test_codex_cache_lists_visible_models_with_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            self._cache(d)
            result = MC.discover("codex", codex_home=d)
        self.assertEqual(result["source"], "codex-local-cache")
        self.assertEqual(result["verification"], "cache-confirmed")
        self.assertFalse(result["account_verified"])
        self.assertEqual([m["id"] for m in result["candidates"]], ["gpt-visible"])
        self.assertEqual(result["candidates"][0]["reasoning_efforts"], ["high"])

    def test_codex_cache_rejects_symlink_and_oversized_file(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as target:
            self._cache(target)
            os.symlink(Path(target, "models_cache.json"), Path(d, "models_cache.json"))
            result = MC.discover("codex", codex_home=d)
            self.assertEqual(result["verification"], "unavailable")
            self.assertTrue(any("symlink" in issue for issue in result["issues"]))
        with tempfile.TemporaryDirectory() as d:
            Path(d, "models_cache.json").write_bytes(b"x" * (MC.MAX_CACHE_BYTES + 1))
            result = MC.discover("codex", codex_home=d)
            self.assertTrue(any("size" in issue for issue in result["issues"]))

    def test_malformed_codex_entries_are_ignored_not_coerced(self):
        with tempfile.TemporaryDirectory() as d:
            self._cache(d, [{"slug": 123, "visibility": "list"},
                            {"slug": "", "visibility": "list"},
                            {"slug": "ok", "visibility": "list"}])
            result = MC.discover("codex", codex_home=d)
        self.assertEqual([m["id"] for m in result["candidates"]], ["ok"])
        self.assertTrue(result["issues"])

    def test_claude_aliases_are_never_reported_as_account_confirmed(self):
        result = MC.discover("claude")
        self.assertEqual(result["source"], "claude-cli-aliases")
        self.assertEqual(result["verification"], "syntax-only/account-unverified")
        self.assertIn("opus", [m["id"] for m in result["candidates"]])
        self.assertFalse(result["account_verified"])

    def test_cli_json_preserves_verification_label(self):
        with tempfile.TemporaryDirectory() as d:
            self._cache(d)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = models.run(Args(codex_home=d, output="json"))
        self.assertEqual(rc, 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["verification"], "cache-confirmed")
        self.assertFalse(result["account_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
