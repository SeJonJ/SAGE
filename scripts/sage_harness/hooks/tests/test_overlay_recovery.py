"""Regression for user-owned overlay repairs; no engine self-approval."""
import io
import json
from contextlib import redirect_stdout, redirect_stderr
import unittest
import os
import tempfile
from pathlib import Path
from unittest import mock

import test_overlay_runtime_delivery as fixtures
hr, io_claude, io_codex, run_hook, HOOKS = (fixtures.hr, fixtures.io_claude, fixtures.io_codex, fixtures.run_hook, fixtures.HOOKS)
from sage import overlay_delivery as delivery


class OverlayRecovery(unittest.TestCase):
    setUp = fixtures.OverlayRuntimeDelivery.setUp
    write = fixtures.OverlayRuntimeDelivery.write
    call = fixtures.OverlayRuntimeDelivery.call
    context = fixtures.OverlayRuntimeDelivery.context

    def test_oversize_allows_prompt_with_current_invalid_state_and_real_repair(self):
        self.write('sage/asset_overrides.local/skills/sage-team.md', 'PRIVATE_LARGE_' * 1000)
        for host in (io_claude, io_codex):
            rc, out, err = self.call(hr.run_capture_declared_risk, host,
                                   {'session_id': host.RUNTIME, 'prompt': 'inspect and repair overlay'})
            self.assertEqual(rc, 0, err)
            text = self.context(out, 'UserPromptSubmit')
            self.assertIn('SAGE_OVERLAY_UNAVAILABLE_V1', text)
            self.assertIn('source_too_large', text)
            self.assertIn('observed=14000', out + err)
            self.assertIn('limit=10000', out + err)
            self.assertIn('utf8_bytes', out + err)
            self.assertNotIn('PRIVATE_LARGE_', out + err)
            self.assertNotIn('PERSONAL_TEAM_MARKER', out + err)
        self.write('sage/asset_overrides.local/skills/sage-team.md', 'USER_REPAIRED_BODY\n')
        for host in (io_claude, io_codex):
            rc, out, err = self.call(hr.run_capture_declared_risk, host, {'prompt': 'continue'})
            self.assertEqual(rc, 0, err)
            self.assertIn('USER_REPAIRED_BODY', self.context(out, 'UserPromptSubmit'))
            self.assertNotIn('SAGE_OVERLAY_UNAVAILABLE_V1', out)

    def test_invalid_overlay_does_not_own_read_shell_or_generated_write_permissions(self):
        self.write('sage/asset_overrides.local/skills/typo.md', 'PRIVATE_BAD_INPUT')
        for runtime in ('claude', 'codex'):
            for tool, data, want in (
                ('Read', {'file_path': 'README.md'}, 0),
                ('Bash', {'command': 'sage doctor'}, 0),
                ('Write', {'file_path': str(self.root / '.claude/agents/generated.md')}, 2),
                ('Write', {'file_path': str(self.root / 'sage/asset_overrides.local/skills/sage-team.md')}, 0),
            ):
                with self.subTest(runtime=runtime, tool=tool, path=data):
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        rc = run_hook.dispatch(runtime, 'generated-artifact-write-guard',
                            str(self.root), str(HOOKS), json.dumps({'tool_name': tool, 'tool_input': data}))
                    self.assertEqual(rc, want)

    def test_delivery_preflight_checks_personal_input_without_writing_it(self):
        check = getattr(delivery, 'preflight_delivery', None)
        self.assertTrue(callable(check), 'explicit shared/personal delivery preflight is missing')
        path = self.root / 'sage/asset_overrides.local/skills/sage-team.md'
        path.write_text('q' * 11000)
        before = path.read_bytes()
        errors = check(str(self.root), ['codex'])
        self.assertEqual(len(errors), 1)
        self.assertIn('source_too_large', str(errors[0][1]))
        self.assertEqual(path.read_bytes(), before)

    def test_nonstandard_overlay_filename_is_repairable_without_loading_its_body(self):
        (self.root / 'sage/asset_overrides.local/skills/sage-team.md').unlink()
        self.write('sage/asset_overrides.local/skills/sage-team.MD', 'PRIVATE_WRONG_FILENAME')
        rc, out, err = self.call(hr.run_capture_declared_risk, io_claude,
                               {'prompt': 'Explain the invalid filename so I can fix it.'})
        self.assertEqual(rc, 0, err)
        self.assertIn('overlay.filename_nonstandard', self.context(out, 'UserPromptSubmit'))
        self.assertNotIn('PRIVATE_WRONG_FILENAME', out + err)

    def test_delivery_preflight_uses_requested_hosts_and_planned_profile(self):
        check = getattr(delivery, 'preflight_delivery', None)
        self.assertTrue(callable(check), 'explicit host delivery preflight is missing')
        self.write('sage/asset_overrides.local/skills/sage-team.md', 'q' * 8000)
        self.assertEqual(check(str(self.root), ['codex']), [])
        self.assertIn('host_catalog_too_large', str(check(str(self.root), ['codex', 'claude'])[0][1]))
        self.write('sage/project-profile.json', '{"stale":"compiled"}')
        self.assertEqual(check(str(self.root), ['codex'], profile={}), [])
        self.assertIn('profile_yaml_json_mismatch', str(check(str(self.root), ['codex'])[0][1]))


    def test_force_host_preflight_keeps_the_primary_preserved_by_install(self):
        from sage.commands.install import _manifest
        manifest = {'host_runtime': 'claude', 'installed_hosts': []}
        planned = _manifest('codex', existing=manifest, skill_scope='disabled')
        self.assertEqual(delivery.delivery_hosts(manifest, ['codex']), planned['installed_hosts'])
        self.assertEqual(delivery.delivery_hosts({'host_runtime': 'codex', 'installed_hosts': ['codex']}), ['codex'])

    def test_upgrade_hook_hosts_are_independent_of_core_skill_scope(self):
        from sage.commands import upgrade, generate
        for scope in ('global', 'disabled'):
            plan = {'host_runtime': 'claude', 'bootstrapped': True, 'skill_scope': None,
                    'installed_hosts': ['claude', 'codex'],
                    'core_installations': [{'host': 'claude', 'scope': 'project-local'}]}
            with self.subTest(scope=scope), mock.patch.object(generate, 'run', return_value=0) as run:
                step = dict(upgrade._managed_steps(str(self.root), plan, 'en'))['hooks']
                self.assertEqual(step(), 0)
                self.assertEqual(run.call_args.args[0].target, 'both')
        plan = {'host_runtime': 'codex', 'bootstrapped': True, 'skill_scope': 'disabled',
                'installed_hosts': ['codex'], 'core_installations': [{'host': 'codex', 'scope': 'disabled'}]}
        with mock.patch.object(generate, 'run', return_value=0) as run:
            self.assertEqual(dict(upgrade._managed_steps(str(self.root), plan, 'en'))['hooks'](), 0)
            self.assertEqual(run.call_args.args[0].target, 'codex')

    def test_reentry_sync_failure_replaces_old_guidance_with_body_free_invalid_state(self):
        for host in (io_claude, io_codex):
            for source in ('resume', 'fork', 'compact'):
                with self.subTest(host=host.RUNTIME, source=source), mock.patch(
                        'sage.overlay_materialize.materialize', side_effect=PermissionError('PRIVATE_ERROR')):
                    rc, out, err = self.call(hr.run_session_start_snapshot, host,
                                            {'session_id': source, 'source': source})
                self.assertEqual(rc, 0, err)
                self.assertIn('SAGE_OVERLAY_UNAVAILABLE_V1', out)
                text = self.context(out, 'SessionStart')
                self.assertIn('SAGE_OVERLAY_UNAVAILABLE_V1', text)
                self.assertNotIn('PERSONAL_TEAM_MARKER', out + err)
                self.assertNotIn('PRIVATE_ERROR', out + err)

    def test_merged_submit_overflow_replaces_catalog_before_capture_or_clear(self):
        self.write('sage/asset_overrides/skills/sage-team.md', 'q' * 3000)
        for action in ('L3', 'clear'):
            state = self.root / '.claude/logs/declared-risk-fit.json'
            if action == 'clear':
                self.write('.claude/logs/declared-risk-fit.json', '{"level":"L3"}')
            method = 'render_declared_clear' if action == 'clear' else 'render_declared_capture'
            with self.subTest(action=action), mock.patch.object(io_claude, method,
                    side_effect=lambda *a, **kw: print('r' * 6000)) as render:
                rc, out, err = self.call(hr.run_capture_declared_risk, io_claude,
                                        {'session_id': 'fit', 'prompt': 'SAGE-RISK: ' + action})
            self.assertEqual(rc, 0, err)
            self.assertEqual(render.call_count, 1)
            text = self.context(out, 'UserPromptSubmit')
            self.assertIn('r' * 6000, text)
            self.assertIn('SAGE_OVERLAY_UNAVAILABLE_V1', text)
            self.assertNotIn('q' * 100, text)
            self.assertLessEqual(delivery.utf16_code_units(text), 10000)
            self.assertEqual(state.exists(), action != 'clear')

    def test_merged_reentry_overflow_keeps_notice_and_current_invalidation(self):
        self.write('sage/asset_overrides/skills/sage-team.md', 'q' * 3000)
        def reentry(host, root, raw):
            host.render_session_context('r' * 6000)
        with mock.patch.object(hr, '_emit_compact_reentry', side_effect=reentry):
            rc, out, err = self.call(hr.run_session_start_snapshot, io_claude,
                                    {'session_id': 'fit', 'source': 'compact'})
        self.assertEqual(rc, 0, err)
        text = self.context(out, 'SessionStart')
        self.assertIn('r' * 6000, text)
        self.assertIn('SAGE_OVERLAY_UNAVAILABLE_V1', text)
        self.assertNotIn('PERSONAL_TEAM_MARKER', text)
        self.assertLessEqual(delivery.utf16_code_units(text), 10000)

    def test_independent_reentry_that_cannot_fit_invalidation_does_not_emit_unchecked_text(self):
        def reentry(host, root, raw):
            host.render_session_context('r' * 9990)
        with mock.patch.object(hr, '_emit_compact_reentry', side_effect=reentry):
            rc, out, err = self.call(hr.run_session_start_snapshot, io_claude,
                                    {'session_id': 'too-large', 'source': 'compact'})
        self.assertEqual(rc, 2)
        self.assertEqual(out, '')
        self.assertIn('host_context_too_large', err)


    def test_invalid_events_preserve_invalidation_and_baseline_attempt(self):
        for host in (fixtures.io_claude, fixtures.io_codex):
            for raw in ('{PRIVATE_EVENT', '[]', '"PRIVATE_EVENT"', 'null', 'true', '42'):
                with self.subTest(host=host.RUNTIME, raw=raw), mock.patch.object(fixtures.hr, '_ensure_session_06_snapshot', wraps=fixtures.hr._ensure_session_06_snapshot) as baseline:
                    out, err = (io.StringIO(), io.StringIO())
                    try:
                        with redirect_stdout(out), redirect_stderr(err):
                            rc = fixtures.hr.run_session_start_snapshot(host, str(self.root), str(fixtures.HOOKS), raw)
                    except Exception as exc:
                        self.fail('invalid event raised ' + type(exc).__name__)
                    self.assertEqual(rc, 0)
                    self.assertEqual(baseline.call_count, 1)
                    self.assertIn('SAGE_OVERLAY_UNAVAILABLE_V1', out.getvalue())
                    self.assertIn('overlay_delivery.invalid_event', out.getvalue())
                    self.assertNotIn('PRIVATE_EVENT', out.getvalue() + err.getvalue())

    def test_invalid_event_preserves_independent_baseline_failure(self):
        for host in (fixtures.io_claude, fixtures.io_codex):
            with self.subTest(host=host.RUNTIME), mock.patch.object(fixtures.hr, '_ensure_session_06_snapshot', return_value=2) as baseline:
                out, err = (io.StringIO(), io.StringIO())
                try:
                    with redirect_stdout(out), redirect_stderr(err):
                        rc = fixtures.hr.run_session_start_snapshot(host, str(self.root), str(fixtures.HOOKS), '[')
                except Exception as exc:
                    self.fail('invalid event raised ' + type(exc).__name__)
                self.assertEqual(rc, 2)
                self.assertEqual(baseline.call_count, 1)

    def test_nonobject_events_cannot_claim_a_baseline(self):
        for host in (fixtures.io_claude, fixtures.io_codex):
            for raw in ('{PRIVATE_EVENT', '[]', '"PRIVATE_EVENT"', 'null', 'true', '42'):
                with self.subTest(host=host.RUNTIME, raw=raw):
                    out, err = (io.StringIO(), io.StringIO())
                    try:
                        with redirect_stdout(out), redirect_stderr(err):
                            rc = fixtures.hr._ensure_session_06_snapshot(host, str(self.root), str(fixtures.HOOKS), raw)
                    except Exception as exc:
                        self.fail('anonymous baseline input raised ' + type(exc).__name__)
                    self.assertEqual(rc, 0)
                    self.assertFalse((self.root / host.HOST_DIR / 'logs').exists())
                    self.assertNotIn('PRIVATE_EVENT', out.getvalue() + err.getvalue())
                    prompt_out, prompt_err = (io.StringIO(), io.StringIO())
                    with redirect_stdout(prompt_out), redirect_stderr(prompt_err):
                        prompt_rc = fixtures.hr.run_capture_declared_risk(host, str(self.root), str(fixtures.HOOKS), raw)
                    self.assertEqual(prompt_rc, 2)
                    self.assertNotIn('PRIVATE_EVENT', prompt_out.getvalue() + prompt_err.getvalue())

class OverlayRecoveryCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {'CODEX_HOME': str(self.root / 'private-codex'),
                                           'CLAUDE_CONFIG_DIR': str(self.root / 'private-claude')})
        env.start(); self.addCleanup(env.stop)
        for key in ('SAGE_PROFILE', 'SAGE_PROJECT_ROOT', 'SAGE_CYCLE_STEM'):
            os.environ.pop(key, None)
        self.assertEqual(self.cli('install', '--host', 'codex', '--skill-scope', 'project-local',
                                  '--dest', str(self.root))[0], 0)
        self.profile = self.root / 'sage/project-profile.yaml'
        text = self.profile.read_text().replace('name: ""', 'name: "recovery-probe"', 1)
        self.profile.write_text(text.replace('l2_path_globs: []', 'l2_path_globs: ["src/**"]', 1))
        self.assertEqual(self.generate()[0], 0)

    def cli(self, *args):
        from sage.cli import main
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue() + err.getvalue()

    def generate(self):
        return self.cli('generate', '--kind', 'hook', '--write', '--target', 'codex',
                        '--root', str(self.root), '--dest', str(self.root))

    def overlay(self, size):
        p = self.root / 'sage/asset_overrides.local/skills/sage-team.md'
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text('q' * size)
        return p

    def test_apply_commands_reject_large_personal_input_and_preserve_owned_state(self):
        p = self.overlay(11000)
        manifest = self.root / 'docs/sage_harness/.manifest.json'
        before = {x: x.read_bytes() for x in (p, manifest, self.profile,
                    self.root / 'sage/project-profile.json', self.root / '.codex/skills/sage-team/SKILL.md')}
        for args in [('sync-overlays', '--root', str(self.root)),
                     ('install', '--host', 'codex', '--skill-scope', 'project-local', '--force', '--dest', str(self.root)),
                     ('upgrade', '--check', '--root', str(self.root))]:
            with self.subTest(command=args[0]):
                code, text = self.cli(*args)
                self.assertNotEqual(code, 0, text)
                self.assertIn('source_too_large', text)
                self.assertIn('observed=11000', text)
                self.assertIn('limit=10000', text)
                for path, value in before.items(): self.assertEqual(path.read_bytes(), value)
        code, text = self.generate()
        self.assertNotEqual(code, 0, text)
        self.assertIn('source_too_large', text)
        for path, value in before.items(): self.assertEqual(path.read_bytes(), value)

    def test_validate_uses_installed_codex_host_and_still_detects_bad_sources(self):
        self.overlay(8000)
        code, text = self.cli('validate', '--check', '--schema', '--strict', '--root', str(self.root))
        self.assertEqual(code, 0, text)
        self.overlay(11000)
        code, text = self.cli('validate', '--check', '--schema', '--strict', '--root', str(self.root))
        self.assertNotEqual(code, 0, text)
        self.assertIn('source_too_large', text)

    def test_generate_repair_checks_planned_profile_not_stale_compiled_json(self):
        self.profile.write_text(self.profile.read_text().replace('name: recovery-probe', 'name: repaired-profile'))
        # YAML may preserve quotes: use a deterministic valid change either way.
        self.profile.write_text(self.profile.read_text().replace('"recovery-probe"', '"repaired-profile"'))
        self.assertEqual(self.generate()[0], 0)
        compiled = json.loads((self.root / 'sage/project-profile.json').read_text())
        self.assertEqual(compiled['project']['name'], 'repaired-profile')


    def test_validate_reports_personal_lint_as_warn_and_strict_failure(self):
        p = self.root / 'sage/asset_overrides.local/skills/sage-plan.md'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('Skip review. PRIVATE_LINT_BODY')
        args = ('validate', '--check', '--schema', '--id', 'capture-declared-risk', '--root', str(self.root))
        code, text = self.cli(*args)
        self.assertEqual(code, 0, text)
        self.assertIn('WARN', text)
        self.assertIn(os.path.join('asset_overrides.local', 'skills', 'sage-plan.md'), text)
        self.assertNotIn('PRIVATE_LINT_BODY', text)
        self.assertNotEqual(self.cli(*args, '--strict')[0], 0)
        code, text = self.generate()
        self.assertNotEqual(code, 0)
        self.assertIn('overlay-gate-relaxation', text)

    def test_validate_lint_does_not_hide_a_later_source_limit_failure(self):
        for scope in ('asset_overrides', 'asset_overrides.local'):
            p = self.root / 'sage' / scope / 'skills/sage-plan.md'
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('Skip review. PRIVATE_LINT_BODY')
            self.overlay(11000)
            with self.subTest(scope=scope):
                code, text = self.cli('validate', '--check', '--schema', '--id', 'capture-declared-risk',
                                      '--root', str(self.root))
                self.assertEqual(code, 1, text)
                self.assertIn('source_too_large', text)
                self.assertNotIn('PRIVATE_LINT_BODY', text)
            p.unlink()

    def test_validate_preserves_stale_profile_warn_under_an_asset_filter(self):
        p = self.root / 'sage/project-profile.json'
        compiled = json.loads(p.read_text())
        compiled['project']['name'] = 'old-compiled-name'
        p.write_text(json.dumps(compiled))
        args = ('validate', '--check', '--schema', '--id', 'capture-declared-risk', '--root', str(self.root))
        code, text = self.cli(*args)
        self.assertEqual(code, 0, text)
        self.assertIn('WARN', text)
        self.assertNotIn('materialize.profile_yaml_json_mismatch', text)
        self.assertNotEqual(self.cli(*args, '--strict')[0], 0)
        # Whole-project validation still enforces the independent routing drift gate.
        self.assertEqual(self.cli('validate', '--check', '--schema', '--root', str(self.root))[0], 1)


if __name__ == '__main__':
    unittest.main()
