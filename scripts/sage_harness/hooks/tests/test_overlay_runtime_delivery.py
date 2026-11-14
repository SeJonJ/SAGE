"""Product fixture tests for context delivery, independent of model behavior."""
import io
import json
import os
import time
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
HOOKS = REPO / 'scripts/sage_harness/hooks'
sys.path[:0] = [str(HOOKS / 'runtime'), str(HOOKS), str(REPO)]
import hook_runtime as hr
import run_hook
import io_claude
import io_codex
from sage import hook_entry


class OverlayRuntimeDelivery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write('sage/project-profile.yaml', '{}\n')
        self.write('sage/asset_overrides/skills/sage-team.md', 'SHARED_TEAM_MARKER\n')
        self.write('sage/asset_overrides.local/skills/sage-team.md', 'PERSONAL_TEAM_MARKER\n')
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for name in ('SAGE_PROFILE', 'SAGE_OVERLAY_ROLE', 'SAGE_PROJECT_ROOT'):
            os.environ.pop(name, None)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')

    def call(self, fn, host, raw, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = fn(host, str(self.root), str(HOOKS), json.dumps(raw), **kwargs)
        return rc, out.getvalue(), err.getvalue()

    def context(self, out, event):
        document = json.loads(out)
        self.assertEqual(document['hookSpecificOutput']['hookEventName'], event)
        return document['hookSpecificOutput']['additionalContext']

    def catalog_from(self, out, event):
        self.assertIn('SAGE_OVERLAY_CATALOG_V2', out, 'current boundary has no replacement catalog')
        text = self.context(out, event)
        start = text.index('{', text.index('SAGE_OVERLAY_CATALOG_V2'))
        return json.JSONDecoder().raw_decode(text[start:])[0]

    def non_sage_boundary(self):
        nested = self.root / 'vendor/non-sage'
        nested.mkdir(parents=True)
        (nested / '.git').mkdir()
        return nested

    def test_split_submit_replaces_parent_catalog_with_empty_then_restores_parent(self):
        nested = self.non_sage_boundary()
        for host in (io_claude, io_codex):
            with self.subTest(host=host.RUNTIME):
                raw = {'session_id': host.RUNTIME, 'prompt': 'SAGE-RISK: L3'}
                before = self.call(hr.run_capture_declared_risk, host, raw)
                self.assertEqual(before[0], 0, before[2])
                parent = self.catalog_from(before[1], 'UserPromptSubmit')
                middle = self.call(hr.run_capture_declared_risk, host, raw, overlay_root=str(nested))
                self.assertEqual(middle[0], 0, middle[2])
                empty = self.catalog_from(middle[1], 'UserPromptSubmit')
                self.assertEqual((empty['schema_version'], empty['root'], empty['role']),
                                 (2, str(nested.resolve()), 'root'))
                self.assertEqual((empty['sources'], empty['targets']), ({}, {}))
                self.assertNotEqual(empty['generation'], parent['generation'])
                self.assertNotIn('PERSONAL_TEAM_MARKER', middle[1] + middle[2])
                self.assertTrue((self.root / host.HOST_DIR / 'logs' /
                                 ('declared-risk-' + host.RUNTIME + '.json')).is_file())
                self.assertFalse((nested / host.HOST_DIR / 'logs').exists())
                after = self.call(hr.run_capture_declared_risk, host, raw)
                self.assertEqual(self.catalog_from(after[1], 'UserPromptSubmit'), parent)

    def test_split_reentry_events_supply_empty_replacement_even_with_parent_overlay_error(self):
        nested = self.non_sage_boundary()
        self.write('sage/asset_overrides/skills/typo.md', 'UNUSED_PARENT_BODY')
        for host in (io_claude, io_codex):
            for source in ('resume', 'fork', 'compact'):
                with self.subTest(host=host.RUNTIME, source=source):
                    rc, out, err = self.call(hr.run_session_start_snapshot, host,
                        {'source': source, 'session_id': host.RUNTIME}, overlay_root=str(nested))
                    self.assertEqual(rc, 0, err)
                    empty = self.catalog_from(out, 'SessionStart')
                    self.assertEqual((empty['root'], empty['sources'], empty['targets']),
                                     (str(nested.resolve()), {}, {}))
                    self.assertNotIn('UNUSED_PARENT_BODY', out + err)

    def test_split_empty_does_not_add_child_catalog_or_change_startup_deferral(self):
        nested = self.non_sage_boundary()
        for host in (io_claude, io_codex):
            rc, out, err = self.call(hr.run_session_start_snapshot, host,
                {'source': 'startup'}, overlay_root=str(nested))
            self.assertEqual(rc, 0, err)
            self.assertNotIn('SAGE_OVERLAY_CATALOG_V2', out)
            for child in ({'agent_id': 'child'}, {'parent_thread_id': 'parent'},
                          {'parent_session_id': 'parent'}):
                for fn in (hr.run_session_start_snapshot, hr.run_capture_declared_risk):
                    rc, out, err = self.call(fn, host, {'source': 'compact', **child},
                                             overlay_root=str(nested))
                    self.assertEqual(rc, 0, err)
                    self.assertNotIn('SAGE_OVERLAY_CATALOG_V2', out)
            with mock.patch.dict(os.environ, {'SAGE_OVERLAY_ROLE': 'reviewer'}):
                rc, out, err = self.call(hr.run_capture_declared_risk, host,
                                         {'prompt': 'continue'}, overlay_root=str(nested))
                self.assertEqual(rc, 0, err)
                self.assertNotIn('SAGE_OVERLAY_CATALOG_V2', out)

    def test_entry_protocol_parent_to_absent_to_parent_and_reentry_for_both_hosts(self):
        from sage.profile_compile import materialize_profile
        self.write('sage/project-profile.json', json.dumps(materialize_profile({})))
        nested = self.non_sage_boundary()
        env = dict(os.environ, PYTHONPATH=str(REPO), SAGE_PROJECT_ROOT=str(self.root),
                   CLAUDE_PROJECT_DIR=str(self.root), CODEX_PROJECT_ROOT=str(self.root),
                   PYTHONDONTWRITEBYTECODE='1')
        for host in (io_claude, io_codex):
            def entry(hook, cwd, **event):
                done = subprocess.run([sys.executable, '-m', 'sage.hook_entry',
                    '--runtime', host.RUNTIME, '--hook', hook],
                    input=json.dumps({'cwd': str(cwd), 'session_id': host.RUNTIME, **event}),
                    cwd=self.root, env=env, capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
                return done.stdout
            catalogs = [self.catalog_from(entry('capture-declared-risk', cwd,
                        prompt='SAGE-RISK: L3'), 'UserPromptSubmit')
                        for cwd in (self.root, nested, self.root)]
            self.assertEqual(catalogs[0], catalogs[2])
            self.assertEqual((catalogs[1]['root'], catalogs[1]['sources'], catalogs[1]['targets']),
                             (str(nested.resolve()), {}, {}))
            for source in ('resume', 'fork', 'compact'):
                current = self.catalog_from(entry('session-start-snapshot', nested, source=source),
                                            'SessionStart')
                self.assertEqual(current, catalogs[1])
            self.assertFalse((nested / host.HOST_DIR / 'logs').exists())

    def test_absent_replacement_reuses_collector_without_reading_overlay_bodies(self):
        import inspect
        import overlay_context
        from sage import overlay_delivery, overlay_common, overlay_local
        self.assertIn('empty_if_absent', inspect.signature(overlay_context.current).parameters,
                      'explicit absence replacement has not been implemented')
        nested = self.non_sage_boundary()
        raw = json.dumps({'prompt': 'continue'})
        unused = nested / 'sage/asset_overrides.local/skills'
        unused.mkdir(parents=True)
        (unused / 'sage-team.md').write_text('NON_SAGE_BODY_MUST_NOT_BE_READ')
        with mock.patch.object(overlay_local, '_read', side_effect=AssertionError('body read')), \
                mock.patch.object(overlay_common, 'read_text_lf', wraps=overlay_common.read_text_lf) as reader:
            text, issue = overlay_context.current(str(nested), raw, empty_if_absent=True)
        self.assertIsNone(issue)
        self.assertEqual(reader.call_count, 0)
        expected = overlay_delivery.render_catalog(overlay_delivery._collect(str(nested.resolve()), 'root', []))
        self.assertEqual(text, expected)
        self.assertEqual(overlay_context.current(str(nested), raw), ('', None))

    def test_submit_supplies_both_bodies_once_without_cli_fetch(self):
        for host in (io_claude, io_codex):
            with self.subTest(host=host.RUNTIME):
                rc, out, err = self.call(hr.run_capture_declared_risk, host,
                                         {'session_id': 's', 'prompt': 'continue'})
                self.assertEqual(rc, 0, err)
                text = self.context(out, 'UserPromptSubmit')
                self.assertEqual(text.count('SHARED_TEAM_MARKER'), 1)
                self.assertEqual(text.count('PERSONAL_TEAM_MARKER'), 1)

    def test_declared_risk_and_catalog_are_one_json_document(self):
        for host in (io_claude, io_codex):
            rc, out, err = self.call(hr.run_capture_declared_risk, host,
                {'session_id': 'risk', 'prompt': 'SAGE-RISK: L3'})
            self.assertEqual(rc, 0, err)
            text = self.context(out, 'UserPromptSubmit')
            self.assertIn('PERSONAL_TEAM_MARKER', text)
            self.assertIn('L3', text)
            state = json.loads((self.root / host.HOST_DIR / 'logs/declared-risk-risk.json').read_text())
            self.assertEqual(state['level'], 'L3')

    def test_startup_defers_bodies_to_submit(self):
        rc, out, err = self.call(hr.run_session_start_snapshot, io_claude,
                               {'session_id': 's', 'source': 'startup'})
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, '')

    def test_session_start_reads_each_root_source_once_for_validation_hash_and_body(self):
        from sage import overlay_common
        source = self.root / 'sage/asset_overrides/skills/sage-team.md'
        with mock.patch.object(overlay_common, 'read_text_lf', wraps=overlay_common.read_text_lf) as reader:
            rc, out, err = self.call(hr.run_session_start_snapshot, io_codex,
                                    {'session_id': 's', 'source': 'resume'})
        self.assertEqual(rc, 0, err)
        reads = [c for c in reader.call_args_list
                 if os.path.realpath(c.args[0]) == os.path.realpath(source)]
        self.assertEqual(len(reads), 1)
        self.assertIn('SHARED_TEAM_MARKER', self.context(out, 'SessionStart'))

    def test_resume_fork_and_compact_supply_current_bodies(self):
        for host in (io_claude, io_codex):
            for source in ('resume', 'fork', 'compact'):
                with self.subTest(host=host.RUNTIME, source=source):
                    rc, out, err = self.call(hr.run_session_start_snapshot, host,
                                            {'session_id': 's', 'source': source})
                    self.assertEqual(rc, 0, err)
                    text = self.context(out, 'SessionStart')
                    self.assertEqual(text.count('PERSONAL_TEAM_MARKER'), 1)
                    if source == 'compact':
                        self.assertIn('SAGE', text)

    def test_bad_inventory_marks_current_invalid_without_private_body(self):
        self.write('sage/asset_overrides.local/skills/typo.md', 'PRIVATE_BAD_INPUT')
        for host in (io_claude, io_codex):
            rc, out, err = self.call(hr.run_capture_declared_risk, host,
                                   {'session_id': 's', 'prompt': 'continue'})
            self.assertEqual(rc, 0)
            self.assertIn('SAGE_OVERLAY_UNAVAILABLE_V1', self.context(out, 'UserPromptSubmit'))
            self.assertNotIn('PERSONAL_TEAM_MARKER', out + err)
            self.assertNotIn('PRIVATE_BAD_INPUT', out + err)

    def test_invalid_submit_still_claims_and_writes_first_opportunity_baseline(self):
        (self.root / 'vault').mkdir()
        profile = {'pdca': {'enabled': True,
                            'phases': [{'id': '06', 'glob': 'plan_docs/06-*.md'}],
                            'retro': {'report_gate_enforce': 'enforce'}},
                   'knowledge_capture': {'retro_note': True, 'vault_path': str(self.root / 'vault')}}
        self.write('baseline-profile.json', json.dumps(profile))
        os.environ['SAGE_PROFILE'] = str(self.root / 'baseline-profile.json')
        self.write('plan_docs/06-before.md', 'original baseline')
        self.write('sage/asset_overrides.local/skills/typo.md', 'PRIVATE_BAD_INPUT')
        rc, out, err = self.call(hr.run_capture_declared_risk, io_claude,
                                {'session_id': 'first-blocked', 'prompt': 'continue'})
        self.assertEqual(rc, 0)
        baseline = self.root / '.claude/logs/session-snapshot-first-blocked.json'
        self.assertTrue(baseline.is_file(), 'blocked UPS skipped the independent 06 baseline')
        self.assertEqual(json.loads(baseline.read_text())['session_id'], 'first-blocked')
        self.assertTrue(Path(str(baseline) + '.attempt').is_file())
        before = baseline.read_bytes()
        self.write('plan_docs/06-before.md', 'changed after blocked first opportunity')
        (self.root / 'sage/asset_overrides.local/skills/typo.md').unlink()
        fixed = self.call(hr.run_capture_declared_risk, io_claude,
                          {'session_id': 'first-blocked', 'prompt': 'continue'})
        self.assertEqual(fixed[0], 0, fixed[2])
        self.assertEqual(baseline.read_bytes(), before)

    def test_start_error_preserves_baseline_and_reentry_attempts(self):
        self.write('sage/asset_overrides.local/skills/typo.md', 'PRIVATE_BAD_INPUT')
        with mock.patch.object(hr, '_ensure_session_06_snapshot', return_value=0) as baseline:
            rc, out, err = self.call(hr.run_session_start_snapshot, io_claude,
                                    {'session_id': 's', 'source': 'compact'})
        self.assertEqual(baseline.call_count, 1)
        self.assertNotIn('PERSONAL_TEAM_MARKER', out + err)
        self.assertIn('SAGE', self.context(out, 'SessionStart'))
        self.assertIn('overlay', err)

    def test_shared_l1_error_does_not_skip_baseline_or_reentry(self):
        self.write('sage/asset_overrides/skills/typo.md', 'BAD_SHARED')
        with mock.patch.object(hr, '_ensure_session_06_snapshot', return_value=0) as baseline:
            rc, out, err = self.call(hr.run_session_start_snapshot, io_claude,
                                    {'session_id': 's', 'source': 'compact'})
        self.assertEqual(rc, 0)
        self.assertEqual(baseline.call_count, 1)
        self.assertIn('SAGE', self.context(out, 'SessionStart'))
        self.assertNotIn('PERSONAL_TEAM_MARKER', out + err)

    def test_malformed_installed_span_remains_blocked_at_submit_and_tool_until_repaired(self):
        self.write('.claude/skills/sage-team/SKILL.md',
                   '# CORE\n<!-- >>> SAGE OVERLAY v1 START (edit sage/asset_overrides/, not here) -->\n')
        start = self.call(hr.run_session_start_snapshot, io_claude,
                          {'session_id': 's', 'source': 'resume'})
        self.assertEqual(start[0], 0)
        rc, out, err = self.call(hr.run_capture_declared_risk, io_claude, {'prompt': 'continue'})
        self.assertEqual(rc, 2)
        self.assertNotIn('PERSONAL_TEAM_MARKER', out + err)
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            rc = run_hook.dispatch('claude', 'generated-artifact-write-guard', str(self.root),
                str(HOOKS), json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'echo ok'}}))
        self.assertEqual(rc, 0)
        self.write('.claude/skills/sage-team/SKILL.md', '# CORE\n')
        fixed = self.call(hr.run_capture_declared_risk, io_claude, {'prompt': 'continue'})
        self.assertEqual(fixed[0], 0, fixed[2])

    def test_l1_sync_exception_suppresses_catalog_and_reports_failure(self):
        with mock.patch('sage.overlay_materialize.materialize', side_effect=PermissionError('PRIVATE')):
            rc, out, err = self.call(hr.run_session_start_snapshot, io_claude,
                                    {'session_id': 's', 'source': 'resume'})
        self.assertEqual(rc, 0)
        self.assertNotIn('PERSONAL_TEAM_MARKER', out + err)
        self.assertNotIn('PRIVATE', out + err)

    def test_routing_only_root_render_warns_until_sync(self):
        from sage import overlay_common, overlay_materialize
        for host in (io_claude, io_codex):
            with self.subTest(host=host.RUNTIME):
                path = f"{host.HOST_DIR}/skills/sage-team/SKILL.md"
                self.write(path, "# CORE\n" + overlay_common.wrap_routing_block("ROUTING_PRIVATE_SENTINEL"))
                rc, out, err = self.call(hr.run_capture_declared_risk, host, {"prompt": "continue"})
                self.assertEqual(rc, 0)
                self.assertIn('SAGE_OVERLAY_UNAVAILABLE_V1', self.context(out, 'UserPromptSubmit'))
                self.assertIn("sage sync-overlays", out)
                self.assertNotIn("PERSONAL_TEAM_MARKER", out + err)
                self.assertNotIn("ROUTING_PRIVATE_SENTINEL", out + err)
                _cr, _changed, errors = overlay_materialize.materialize(str(self.root), host.RUNTIME)
                self.assertEqual(errors, [])
                fixed = self.call(hr.run_capture_declared_risk, host, {"prompt": "continue"})
                self.assertEqual(fixed[0], 0, fixed[2])
                self.assertIn("PERSONAL_TEAM_MARKER", self.context(fixed[1], "UserPromptSubmit"))
                self.assertNotIn("ROUTING_PRIVATE_SENTINEL", (self.root / path).read_text())

    def test_uncleared_legacy_span_requires_successful_sync_before_submit(self):
        from sage.overlay_common import compose_block
        core = (REPO / 'templates/core/framework/.claude/skills/sage-team/SKILL.md').read_text()
        for name in ('hook_runtime.py', 'overlay_context.py'):
            self.write('sage_harness/hooks/runtime/' + name, (HOOKS / 'runtime' / name).read_text())
        self.write('.claude/skills/sage-team/SKILL.md', core + '\n' +
                   compose_block('OLD_SHARED_BODY', 'skills', 'sage-team'))
        bad = self.call(hr.run_capture_declared_risk, io_claude, {'prompt': 'continue'})
        self.assertEqual(bad[0], 0)
        start = self.call(hr.run_session_start_snapshot, io_claude,
                          {'session_id': 's', 'source': 'resume'})
        self.assertEqual(start[0], 0, start[2])
        self.assertIn('PERSONAL_TEAM_MARKER', self.context(start[1], 'SessionStart'))
        fixed = self.call(hr.run_capture_declared_risk, io_claude, {'prompt': 'continue'})
        self.assertEqual(fixed[0], 0, fixed[2])

    def test_marker_corruption_is_not_non_sage_passthrough(self):
        self.write('sage/project-profile.yaml', '[broken')
        rc, out, err = self.call(hr.run_capture_declared_risk, io_codex, {'prompt': 'continue'})
        self.assertEqual(rc, 2)
        self.assertNotIn('PERSONAL_TEAM_MARKER', out + err)

    def test_validator_exception_does_not_quote_input(self):
        with mock.patch('sage.overlay_delivery.collect_catalog', side_effect=ValueError('PRIVATE_EXCEPTION')):
            rc, out, err = self.call(hr.run_capture_declared_risk, io_claude, {'prompt': 'continue'})
        self.assertEqual(rc, 2)
        self.assertNotIn('PRIVATE_EXCEPTION', out + err)

    def test_external_fix_releases_next_submit_without_latch(self):
        self.write('sage/asset_overrides.local/skills/typo.md', 'PRIVATE_BAD_INPUT')
        first = self.call(hr.run_capture_declared_risk, io_codex, {'prompt': 'continue'})
        self.assertEqual(first[0], 0)
        (self.root / 'sage/asset_overrides.local/skills/typo.md').unlink()
        rc, out, err = self.call(hr.run_capture_declared_risk, io_codex, {'prompt': 'continue'})
        self.assertEqual(rc, 0, err)
        self.assertIn('PERSONAL_TEAM_MARKER', self.context(out, 'UserPromptSubmit'))

    def test_removed_overlay_supplies_empty_current_catalog(self):
        for path in self.root.glob('sage/asset_overrides*/skills/*.md'):
            path.unlink()
        rc, out, err = self.call(hr.run_capture_declared_risk, io_codex, {'prompt': 'continue'})
        self.assertEqual(rc, 0, err)
        text = self.context(out, 'UserPromptSubmit')
        self.assertIn('"sources":{}', text.replace(' ', ''))

    def test_headless_role_and_unmarked_child_get_no_root_catalog(self):
        for raw, role in (({'prompt': 'continue'}, 'reviewer'),
                          ({'prompt': 'continue', 'agent_id': 'child-1'}, None)):
            with self.subTest(role=role):
                if role:
                    os.environ['SAGE_OVERLAY_ROLE'] = role
                else:
                    os.environ.pop('SAGE_OVERLAY_ROLE', None)
                rc, out, err = self.call(hr.run_capture_declared_risk, io_codex, raw)
                self.assertEqual(rc, 0, err)
                self.assertNotIn('PERSONAL_TEAM_MARKER', out)

    def test_main_agent_type_alone_keeps_root_catalog(self):
        for host in (io_claude, io_codex):
            rc, out, err = self.call(hr.run_capture_declared_risk, host,
                                    {'prompt': 'continue', 'agent_type': 'diagnostic-root'})
            self.assertEqual(rc, 0, err)
            self.assertIn('PERSONAL_TEAM_MARKER', self.context(out, 'UserPromptSubmit'))

    def test_positive_child_identity_suppresses_new_root_catalog(self):
        for key in ('agent_id', 'parent_session_id', 'parent_thread_id'):
            for host in (io_claude, io_codex):
                with self.subTest(marker=key, host=host.RUNTIME):
                    rc, out, err = self.call(hr.run_capture_declared_risk, host,
                                            {'prompt': 'continue', key: 'native-child'})
                    self.assertEqual(rc, 0, err)
                    self.assertNotIn('PERSONAL_TEAM_MARKER', out)

    def test_invalid_inventory_allows_shell_diagnosis(self):
        self.write('sage/asset_overrides.local/skills/typo.md', 'PRIVATE_BAD_INPUT')
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = run_hook.dispatch('codex', 'generated-artifact-write-guard', str(self.root),
                str(HOOKS), json.dumps({'tool_name': 'Bash', 'tool_input': {'command': 'echo ok'}}))
        self.assertEqual(rc, 0)
        self.assertNotIn('PRIVATE_BAD_INPUT', out.getvalue() + err.getvalue())

    def test_valid_inventory_allows_reading_generated_skill(self):
        # Widening PreToolUse coverage must not turn a write guard into a read ban.
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = run_hook.dispatch('claude', 'generated-artifact-write-guard', str(self.root),
                str(HOOKS), json.dumps({'tool_name': 'Read', 'tool_input': {
                    'file_path': str(self.root / '.claude/skills/sage-team/SKILL.md')}}))
        self.assertEqual(rc, 0, err.getvalue())

    def test_oversize_is_unavailable_without_truncation(self):
        self.write('sage/asset_overrides.local/skills/sage-team.md', 'PRIVATE_LARGE_' * 1000)
        rc, out, err = self.call(hr.run_capture_declared_risk, io_claude, {'prompt': 'continue'})
        self.assertEqual(rc, 0)
        self.assertNotIn('PRIVATE_LARGE_', out + err)

    def test_claude_native_catalog_cap_is_checked_before_delivery(self):
        self.write('sage/asset_overrides.local/skills/sage-team.md', 'q' * 8000)
        claude = self.call(hr.run_capture_declared_risk, io_claude, {'prompt': 'continue'})
        self.assertEqual(claude[0], 0)
        self.assertNotIn('q' * 100, claude[1] + claude[2])
        codex = self.call(hr.run_capture_declared_risk, io_codex, {'prompt': 'continue'})
        self.assertEqual(codex[0], 0, codex[2])
        self.assertIn('q' * 8000, self.context(codex[1], 'UserPromptSubmit'))

    def test_merged_claude_submit_context_cannot_spill_to_preview(self):
        # Inject an oversized IO producer; keep the real risk decision and writes.
        def capture(level, root=None):
            print('r' * 9990)
        expired = self.root / '.claude/logs/declared-risk-expired.json'
        self.write('.claude/logs/declared-risk-expired.json', '{"level":"L3"}')
        old = time.time() - 3 * 86400
        os.utime(expired, (old, old))
        with mock.patch.object(io_claude, 'render_declared_capture', side_effect=capture):
            rc, out, err = self.call(hr.run_capture_declared_risk, io_claude,
                                    {'session_id': 'overflow', 'prompt': 'SAGE-RISK: L3'})
        self.assertEqual(rc, 2)
        self.assertNotIn('PERSONAL_TEAM_MARKER', out + err)
        self.assertFalse((self.root / '.claude/logs/declared-risk-overflow.json').exists(),
                         'blocked overflow must not capture risk state')
        self.assertTrue(expired.exists(), 'blocked overflow must not clean other risk state')

    def test_merged_overflow_does_not_clear_existing_risk_state(self):
        self.write('.claude/logs/declared-risk-overflow.json', '{"level":"L3"}')
        state = self.root / '.claude/logs/declared-risk-overflow.json'
        original = state.read_bytes()
        def clear(existed=True, root=None):
            print('r' * 9990)
        with mock.patch.object(io_claude, 'render_declared_clear', side_effect=clear):
            rc, out, err = self.call(hr.run_capture_declared_risk, io_claude,
                                    {'session_id': 'overflow', 'prompt': 'SAGE-RISK: clear'})
        self.assertEqual(rc, 2)
        self.assertTrue(state.exists(), 'blocked overflow cleared risk state')
        self.assertEqual(state.read_bytes(), original)

    def test_merged_session_overflow_cannot_drop_required_invalidation(self):
        def reentry(host, root, raw):
            host.render_session_context('r' * 9990)
        with mock.patch.object(hr, '_emit_compact_reentry', side_effect=reentry):
            rc, out, err = self.call(hr.run_session_start_snapshot, io_claude,
                                    {'session_id': 's', 'source': 'compact'})
        self.assertEqual(rc, 2)
        self.assertEqual(out, '')
        self.assertIn('host_context_too_large', err)

    def test_session_overlay_warning_does_not_hide_baseline_failure(self):
        self.write('sage/asset_overrides/skills/typo.md', 'BAD_SHARED')
        for host in (io_claude, io_codex):
            with mock.patch.object(hr, '_ensure_session_06_snapshot', return_value=2):
                rc, out, err = self.call(hr.run_session_start_snapshot, host,
                                        {'session_id': 'baseline-fails', 'source': 'compact'})
            self.assertEqual(rc, 2)
            self.assertIn('SAGE', self.context(out, 'SessionStart'))
            self.assertNotIn('PERSONAL_TEAM_MARKER', out + err)

    def test_non_sage_checkout_stays_pass_through(self):
        (self.root / 'sage/project-profile.yaml').unlink()
        rc, out, err = self.call(hr.run_capture_declared_risk, io_claude, {'prompt': 'continue'})
        self.assertEqual(rc, 0, err)
        self.assertEqual(out, '')


class EventRootResolution(unittest.TestCase):
    def test_current_checkout_overrides_stale_startup_environment(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'sage').mkdir()
            Path(root, 'sage/project-profile.yaml').write_text('{}')
            child = Path(root, 'src'); child.mkdir()
            with mock.patch.dict(os.environ, {'SAGE_PROJECT_ROOT': '/stale/checkout'}):
                got = hook_entry._resolve_event_root('codex', None, json.dumps({'cwd': str(child)}))
            self.assertEqual(got, os.path.realpath(root))

    def test_linked_checkout_event_root_keeps_gate_target_inside(self):
        with tempfile.TemporaryDirectory() as folder:
            real = Path(folder, 'real'); real.mkdir()
            (real / 'sage').mkdir()
            (real / 'sage/project-profile.yaml').write_text('{}')
            alias = Path(folder, 'alias')
            try:
                alias.symlink_to(real, target_is_directory=True)
            except OSError:
                self.skipTest('symlink creation unavailable')
            got = hook_entry._resolve_event_root(
                'claude', None, json.dumps({'cwd': str(alias)}))
            # The existing gate consumes lexical paths. Canonicalizing only the
            # root makes a path in this same checkout appear outside the gate.
            for gate_root in (got, str(alias)):
                for target in (real / 'src/task.py', alias / 'src/task.py'):
                    self.assertEqual(hr.make_rel(gate_root)(str(target)), 'src/task.py')
            from sage.overlay_delivery import collect_catalog
            self.assertEqual(collect_catalog(got)['root'], os.path.realpath(real))

    def test_non_sage_git_boundary_does_not_climb_into_parent_project(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'sage').mkdir()
            Path(root, 'sage/project-profile.yaml').write_text('{}')
            child = Path(root, 'consumer'); child.mkdir(); (child / '.git').mkdir()
            got = hook_entry._resolve_event_root('claude', None, json.dumps({'cwd': str(child)}))
            self.assertEqual(got, os.path.realpath(child))

    def test_bare_git_boundary_does_not_inherit_parent_personal_sources(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'sage').mkdir()
            Path(root, 'sage/project-profile.yaml').write_text('{}')
            child = Path(root, 'bare'); child.mkdir()
            (child / 'HEAD').write_text('ref: refs/heads/main\n')
            (child / 'objects').mkdir(); (child / 'refs').mkdir()
            got = hook_entry._resolve_event_root('codex', None, json.dumps({'cwd': str(child)}))
            self.assertEqual(got, os.path.realpath(child))


if __name__ == '__main__':
    unittest.main()
