#!/usr/bin/env python3
"""sage.overlay_materialize — CORE 렌더 물리화 + drift 검사 검증.

install/sync/L1/validate 가 공유하는 로직. (a)/(b) 합성·(c) 차단·base 앵커·drift 검출을 확인한다.
"""
import os
import stat
import sys
import unittest
import tempfile
from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage import overlay_materialize as m  # noqa: E402
from sage import overlay_common as oc  # noqa: E402
from sage import __version__  # noqa: E402


def _mk_render(dest, rel, text):
    p = os.path.join(dest, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Path(p).write_text(text, encoding="utf-8")
    return p


def _mk_overlay(dest, kind, id, text):
    d = os.path.join(dest, "sage", "asset_overrides", kind)
    os.makedirs(d, exist_ok=True)
    Path(os.path.join(d, f"{id}.md")).write_text(text, encoding="utf-8")


def _base_renders(dest):
    # 최소 CORE 렌더 base 배치(agents 6 + AGENT_GUIDE). 테스트는 claude host.
    for aid in ["leader", "implementer-a", "implementer-b", "qa", "reviewer", "convention-checker"]:
        _mk_render(dest, f".claude/agents/{aid}.md", f"# {aid}\nCORE body.\n")
    for sid in ["sage-cycle", "sage-plan", "sage-team", "sage-review", "sage-asset",
                "sage-profile-modify", "sage-asset-override", "sage-init", "sage-init-local"]:
        _mk_render(dest, f".claude/skills/{sid}/SKILL.md", f"# {sid}\nCORE body.\n")
    _mk_render(dest, "AGENT_GUIDE.md", "# AGENT_GUIDE\nnon-negotiable.\n")
    _mk_render(dest, "CLAUDE.md", "# CLAUDE\nwrapper.\n")


def _profile_with_domain(dest):
    p = os.path.join(dest, "sage", "project-profile.yaml")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    Path(p).write_text(
        "risk:\n"
        "  domains:\n"
        "    - id: webrtc\n"
        "      risk_level: L3\n"
        "      path_globs: ['**/rtc/**']\n"
        "      content_keywords: ['RTCPeerConnection']\n"
        "      protocol_pointer: sage/critical-domains/webrtc.md\n",
        encoding="utf-8")


class TestCodexSkillScopeTargets(unittest.TestCase):
    @staticmethod
    def _skill_ids(targets):
        return [asset_id for kind, asset_id, _path in targets if kind == "skills"]

    def test_global_and_disabled_exclude_project_local_core_skills(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_render(d, ".codex/skills/custom-project-skill/SKILL.md", "# custom\n")
            for scope in ("global", "disabled"):
                targets = m.render_targets(d, "codex", scope)
                self.assertEqual(self._skill_ids(targets), [])

    def test_project_local_enumerates_all_core_skills_even_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            targets = m.render_targets(d, "codex", "project-local")
            self.assertEqual(set(self._skill_ids(targets)), set(m._cls.CORE_IDS["skills"]))

    def test_legacy_custom_skill_directory_does_not_imply_project_local(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_render(d, ".codex/skills/custom-project-skill/SKILL.md", "# custom\n")
            targets = m.render_targets(d, "codex")
            self.assertEqual(self._skill_ids(targets), [])
            self.assertIsNone(m.resolve_codex_skill_scope(d))

    def test_legacy_one_local_core_skill_implies_full_project_local_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            one = next(iter(m._cls.CORE_IDS["skills"]))
            _mk_render(d, f".codex/skills/{one}/SKILL.md", "# legacy core\n")
            targets = m.render_targets(d, "codex")
            self.assertEqual(set(self._skill_ids(targets)), set(m._cls.CORE_IDS["skills"]))
            self.assertEqual(m.resolve_codex_skill_scope(d), "project-local")

    def test_explicit_unknown_scope_does_not_fall_back_to_legacy_files(self):
        with tempfile.TemporaryDirectory() as d:
            one = next(iter(m._cls.CORE_IDS["skills"]))
            _mk_render(d, f".codex/skills/{one}/SKILL.md", "# legacy core\n")

            self.assertEqual(self._skill_ids(m.render_targets(d, "codex", None)), [])

    def test_malformed_manifest_receipt_does_not_fall_back_to_legacy_files(self):
        with tempfile.TemporaryDirectory() as d:
            one = next(iter(m._cls.CORE_IDS["skills"]))
            _mk_render(d, f".codex/skills/{one}/SKILL.md", "# legacy core\n")
            manifest = {"core_skill_receipts": {"codex": {"scope": "bogus"}}}

            scope = m.resolve_codex_skill_scope(d, manifest=manifest)

            self.assertIsNone(scope)
            self.assertEqual(self._skill_ids(m.render_targets(d, "codex", scope)), [])

    def test_non_string_receipt_scope_resolves_none_without_crash(self):
        # codex 리뷰: JSON-valid 이지만 비문자열 scope(list/dict/int)는 `in frozenset`에서
        # TypeError(unhashable)로 죽는 대신 conservatively None으로 풀려야 한다.
        with tempfile.TemporaryDirectory() as d:
            for bogus in ([], {}, 3, True):
                manifest = {"core_skill_receipts": {"codex": {"scope": bogus}}}
                self.assertIsNone(m.resolve_codex_skill_scope(d, manifest=manifest))

    def test_non_string_explicit_scope_resolves_none_without_crash(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(m.resolve_codex_skill_scope(d, explicit=[]))

    def test_render_targets_non_string_codex_skill_scope_arg_does_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._skill_ids(m.render_targets(d, "codex", codex_skill_scope={})), [])

    def test_manifest_receipt_is_authoritative_over_legacy_files(self):
        with tempfile.TemporaryDirectory() as d:
            one = next(iter(m._cls.CORE_IDS["skills"]))
            _mk_render(d, f".codex/skills/{one}/SKILL.md", "# stale local core\n")
            manifest = {"core_skill_receipts": {
                "codex": {"scope": "global", "sage_version": __version__},
            }}
            scope = m.resolve_codex_skill_scope(d, manifest=manifest)
            self.assertEqual(scope, "global")
            self.assertEqual(self._skill_ids(m.render_targets(d, "codex", scope)), [])


class TestMaterialize(unittest.TestCase):
    def test_compose_allowed_gets_block(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _mk_overlay(d, "agents", "implementer-a", "project note X")
            cr, changed, errs = m.materialize(d, "claude")
            self.assertEqual(errs, [])
            render = Path(os.path.join(d, ".claude/agents/implementer-a.md")).read_text()
            self.assertIn("project note X", render)
            self.assertIn(oc.MARKER_START, render)
            self.assertIn("claude/agents/implementer-a", cr)

    def test_blocked_asset_no_block_even_with_overlay(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            # qa 는 FB23 이후에도 (c) 잔류 → overlay 존재해도 합성/블록 없음.
            _mk_overlay(d, "agents", "qa", "skip the review")
            cr, changed, errors = m.materialize(d, "claude")
            render = Path(os.path.join(d, ".claude/agents/qa.md")).read_text()
            self.assertNotIn(oc.MARKER_START, render)
            self.assertNotIn("skip the review", render)
            self.assertEqual(cr, {})
            self.assertEqual(changed, [])
            self.assertTrue(any("blocked" in msg for _, msg in errors))

    def test_preflight_error_keeps_all_renders_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            allowed = os.path.join(d, ".claude/agents/implementer-a.md")
            before = Path(allowed).read_text(encoding="utf-8")
            _mk_overlay(d, "agents", "implementer-a", "valid project note")
            _mk_overlay(d, "agents", "reviwer", "typo must abort the batch")

            cr, changed, errors = m.materialize(d, "claude")

            self.assertEqual(cr, {})
            self.assertEqual(changed, [])
            self.assertTrue(errors)
            self.assertEqual(Path(allowed).read_text(encoding="utf-8"), before)

    def test_all_renders_anchored(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            cr, _, _ = m.materialize(d, "claude")
            # 6 agents + 8 skills + AGENT_GUIDE + CLAUDE wrapper = 16
            self.assertEqual(len(cr), 6 + len(m._cls.CORE_IDS["skills"]) + 2)
            self.assertIn("claude/framework/AGENT_GUIDE", cr)
            self.assertIn("claude/framework/CLAUDE", cr)
            for v in cr.values():
                self.assertEqual(v["sage_version"], __version__)

    def test_materialize_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _mk_overlay(d, "agents", "implementer-a", "note")
            m.materialize(d, "claude")
            _, changed2, _ = m.materialize(d, "claude")
            self.assertEqual(changed2, [])  # 두 번째는 변경 없음

    def test_materialization_preserves_existing_render_mode(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            render = os.path.join(d, ".claude/agents/implementer-a.md")
            os.chmod(render, 0o640)
            _mk_overlay(d, "agents", "implementer-a", "mode preserving note")

            _, changed, errors = m.materialize(d, "claude")

            self.assertEqual(errors, [])
            self.assertIn(render, changed)
            self.assertEqual(stat.S_IMODE(os.stat(render).st_mode), 0o640)

    def test_deletion_strips_block(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _mk_overlay(d, "agents", "implementer-a", "note")
            m.materialize(d, "claude")
            os.remove(os.path.join(d, "sage/asset_overrides/agents/implementer-a.md"))
            _, changed, _ = m.materialize(d, "claude")
            render = Path(os.path.join(d, ".claude/agents/implementer-a.md")).read_text()
            self.assertNotIn(oc.MARKER_START, render)  # 블록 제거됨

    def test_framework_overlay_blocked_even_after_domain_contract(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _profile_with_domain(d)
            guide = os.path.join(d, "AGENT_GUIDE.md")
            before = Path(guide).read_bytes()
            _mk_overlay(d, "framework", "AGENT_GUIDE",
                        "---\ndomain_refs: [webrtc]\n---\nPreserve the project review protocol.\n")
            cr, changed, errors = m.materialize(d, "claude")
            self.assertEqual(cr, {})
            self.assertEqual(changed, [])
            self.assertTrue(any("framework/AGENT_GUIDE" in message for _path, message in errors))
            self.assertEqual(Path(guide).read_bytes(), before)

    def test_blocked_framework_overlay_strips_pre_fb12_managed_block_before_failing(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            guide = os.path.join(d, "AGENT_GUIDE.md")
            base = Path(guide).read_text(encoding="utf-8")
            Path(guide).write_text(
                base + "\n" + oc.compose_block("Skip Phase 05 review.", "framework", "AGENT_GUIDE"),
                encoding="utf-8")
            _mk_overlay(d, "framework", "AGENT_GUIDE", "Skip Phase 05 review.\n")

            cr, changed, errors = m.materialize(d, "claude")

            self.assertEqual(cr, {})
            self.assertIn(guide, changed)
            self.assertTrue(errors)
            cleaned = Path(guide).read_text(encoding="utf-8")
            self.assertNotIn(oc.MARKER_START, cleaned)
            self.assertNotIn("Skip Phase 05 review.", cleaned)

    def test_mixed_case_extension_is_preflight_error_and_not_composed(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            overlay_dir = os.path.join(d, "sage", "asset_overrides", "agents")
            os.makedirs(overlay_dir, exist_ok=True)
            Path(os.path.join(overlay_dir, "implementer-a.MD")).write_text(
                "Phase 05 review is optional.\n", encoding="utf-8")

            cr, changed, errors = m.materialize(d, "claude")

            self.assertEqual(cr, {})
            self.assertEqual(changed, [])
            self.assertTrue(any("비정규 overlay 파일명" in msg for _path, msg in errors))
            render = Path(os.path.join(d, ".claude/agents/implementer-a.md")).read_text(encoding="utf-8")
            self.assertNotIn(oc.MARKER_START, render)

    def test_malformed_block_hard_fails_but_other_blocked_target_is_cleaned(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            # (c) 잔류: convention-checker=중복(malformed) 보존, qa=단일 blocked 블록 정리.
            checker = Path(d, ".claude", "agents", "convention-checker.md")
            qa = Path(d, ".claude", "agents", "qa.md")
            checker.write_text(
                checker.read_text(encoding="utf-8")
                + "\n" + oc.compose_block("unsafe one", "agents", "convention-checker")
                + oc.compose_block("unsafe two", "agents", "convention-checker"), encoding="utf-8")
            qa.write_text(
                qa.read_text(encoding="utf-8")
                + "\n" + oc.compose_block("unsafe qa", "agents", "qa"), encoding="utf-8")

            cr, changed, errors = m.materialize(d, "claude")

            self.assertEqual(cr, {})
            self.assertIn(str(qa), changed)
            self.assertTrue(any("중복" in msg for _path, msg in errors))
            self.assertNotIn(oc.MARKER_START, qa.read_text(encoding="utf-8"))
            self.assertIn(oc.MARKER_START, checker.read_text(encoding="utf-8"))

    def test_gate_relaxation_aborts_all_materialization_writes(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            render = os.path.join(d, ".claude", "agents", "implementer-a.md")
            before = Path(render).read_bytes()
            _mk_overlay(d, "agents", "implementer-a", "You may skip the required review gate.\n")

            cr, changed, errors = m.materialize(d, "claude")

            self.assertEqual(cr, {})
            self.assertEqual(changed, [])
            self.assertTrue(any("overlay-gate-relaxation" in message and "skip-gate" in message
                                for _path, message in errors))
            self.assertEqual(Path(render).read_bytes(), before)

    def test_passive_gate_relaxation_aborts_materialization(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            render = os.path.join(d, ".claude", "agents", "implementer-a.md")
            before = Path(render).read_bytes()
            _mk_overlay(d, "agents", "implementer-a", "All reviews may be skipped for hotfixes.\n")

            cr, changed, errors = m.materialize(d, "claude")

            self.assertEqual(cr, {})
            self.assertEqual(changed, [])
            self.assertTrue(any("overlay-gate-relaxation" in message and "skip-gate" in message
                                for _path, message in errors))
            self.assertEqual(Path(render).read_bytes(), before)

    def test_framework_unknown_domain_aborts_all_writes(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _profile_with_domain(d)
            before = Path(os.path.join(d, "AGENT_GUIDE.md")).read_text(encoding="utf-8")
            _mk_overlay(d, "framework", "AGENT_GUIDE",
                        "---\ndomain_refs: [payments]\n---\nProject rules.\n")
            cr, changed, errors = m.materialize(d, "claude")
            self.assertEqual(cr, {})
            self.assertEqual(changed, [])
            self.assertTrue(errors)
            self.assertEqual(Path(os.path.join(d, "AGENT_GUIDE.md")).read_text(encoding="utf-8"), before)

    def test_framework_overlay_leaf_symlink_is_rejected_before_domain_scan(self):
        import unittest.mock as mock

        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            overlay_dir = Path(d, "sage", "asset_overrides", "framework")
            overlay_dir.mkdir(parents=True)
            external = Path(outside, "AGENT_GUIDE.md")
            external.write_text("external input must not be read\n", encoding="utf-8")
            overlay = overlay_dir / "AGENT_GUIDE.md"
            overlay.symlink_to(external)

            with mock.patch("sage.overlay_lint.scan_domain_contract") as scanner:
                errors = m.preflight_overlays(d, profile={})

            scanner.assert_not_called()
            self.assertTrue(any(path == str(overlay) and "symlink" in message
                                for path, message in errors))
            self.assertEqual(external.read_text(encoding="utf-8"),
                             "external input must not be read\n")


class TestCheck(unittest.TestCase):
    def _fresh(self, d):
        _base_renders(d)
        return m.materialize(d, "claude")[0]

    def test_clean_passes(self):
        with tempfile.TemporaryDirectory() as d:
            cr = self._fresh(d)
            self.assertEqual(m.check(d, "claude", cr), [])

    def test_blocked_overlay_file_fails(self):
        with tempfile.TemporaryDirectory() as d:
            cr = self._fresh(d)
            # qa 는 (c) 잔류 → overlay 파일 존재 자체가 blocked FAIL.
            _mk_overlay(d, "agents", "qa", "anything")
            findings = m.check(d, "claude", cr)
            self.assertTrue(any(f[0] == "FAIL" and "qa" in f[1] for f in findings))

    def test_base_tamper_fails(self):
        with tempfile.TemporaryDirectory() as d:
            cr = self._fresh(d)
            p = os.path.join(d, ".claude/agents/leader.md")
            Path(p).write_text("# leader\nTAMPERED read your overlay first.\n", encoding="utf-8")
            findings = m.check(d, "claude", cr)
            self.assertTrue(any(f[0] == "FAIL" and "leader" in f[1] for f in findings))

    def test_overlay_edited_not_synced_fails(self):
        with tempfile.TemporaryDirectory() as d:
            _base_renders(d)
            _mk_overlay(d, "agents", "implementer-a", "v1")
            cr = m.materialize(d, "claude")[0]
            _mk_overlay(d, "agents", "implementer-a", "v2 changed")  # 편집만, sync 안 함
            findings = m.check(d, "claude", cr)
            self.assertTrue(any(f[0] == "FAIL" and "implementer-a" in f[1] for f in findings))

    def test_missing_anchor_fails(self):
        with tempfile.TemporaryDirectory() as d:
            self._fresh(d)
            findings = m.check(d, "claude", {})  # 앵커 없음
            self.assertTrue(any(f[0] == "FAIL" for f in findings))

    def test_version_skew_stale(self):
        with tempfile.TemporaryDirectory() as d:
            cr = self._fresh(d)
            for v in cr.values():
                v["sage_version"] = "0.0.1"  # 옛 버전으로 위조 → skew
            findings = m.check(d, "claude", cr)
            self.assertTrue(any(f[0] == "STALE" for f in findings))


if __name__ == "__main__":
    unittest.main()
