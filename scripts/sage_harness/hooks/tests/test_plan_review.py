#!/usr/bin/env python3
"""Plan review boundary tests; no paid models or installed-project mutations."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
import yaml
from sage.commands import plan_review as PR
from sage.peer_process import PeerRun, run_peer
import sage.peer_process as peer_process
from sage.profile_validate import validate_profile


class PlanReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.profile = yaml.safe_load((REPO / "templates/project-profile.yaml").read_text())
        self.profile['pdca']['plan_review'] = {'enabled': True, 'levels': ['L2', 'L3']}
        self.profile['pdca']['phases'] = [
            {'id': p, 'glob': f'plans/{p}/**/*.md'} for p in ('00', '01', '02')]
        # Keep unrelated phase references in the shipped template valid.
        self.profile['pdca']['phases'] += [
            {'id': p, 'glob': f'plans/{p}/**/*.md'} for p in ('03', '04', '05', '06')]
        self.write_profile()
        self.plans = []
        for p in ('00', '01', '02'):
            path = self.root / 'plans' / p / 'test.md'
            path.parent.mkdir(parents=True)
            path.write_text('Cycle-Stem: test\nDocument-Language: ko\n'
                            + ('Risk Level: L3\n' if p == '00' else '')
                            + '## 계획\n근거를 확인합니다.\n', encoding='utf-8')
            self.plans.append(str(path.relative_to(self.root)))
        self.args = argparse.Namespace(root=str(self.root), host='codex', stem='test',
                                       plan=self.plans, source=[], timeout=300,
                                       max_input_bytes=1048576, output=None, json=True)
        self.host = mock.patch.object(PR, 'detect_current_host', return_value='codex')
        self.host.start()
        self.addCleanup(self.host.stop)
        self.peer = mock.patch.object(PR, 'run_peer', return_value=PeerRun(
            'codex', ok=True, review='FINDINGS: none\nREVIEWED: plans\nUNVERIFIED: source absent',
            controls='full', usage=None, tool_calls=0))
        self.invoke = self.peer.start()
        self.addCleanup(self.peer.stop)

    def write_profile(self):
        path = self.root / 'sage/project-profile.yaml'
        path.parent.mkdir(exist_ok=True)
        path.write_text(yaml.safe_dump(self.profile), encoding='utf-8')

    def execute(self):
        return PR.execute(self.args)

    def test_disabled_skips_missing_inputs_and_host(self):
        self.profile['pdca'].pop('plan_review')
        self.write_profile()
        self.args.plan = ['missing.md']
        self.args.source = ['missing.txt']
        self.args.host = 'claude'
        result = self.execute()
        self.assertEqual((result['status'], result['reason']), ('SKIPPED', 'disabled'))
        self.invoke.assert_not_called()
        PR.detect_current_host.assert_not_called()

    def test_registered_cli_dispatches_and_emits_one_json_result(self):
        from sage.cli import main
        output = io.StringIO()
        argv = ['--lang', 'en', 'plan-review', '--root', str(self.root),
                '--host', 'codex', '--stem', 'test', '--json']
        for path in self.plans:
            argv += ['--plan', path]
        with redirect_stdout(output):
            code = main(argv)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'COMPLETE')

    def test_invalid_profile_is_not_disabled_success(self):
        self.profile['pdca']['plan_review'] = {'enabled': 'false'}
        self.write_profile()
        self.assertEqual(self.execute()['status'], 'INVALID_INPUT')
        self.invoke.assert_not_called()

    def test_semantics_reject_config_without_schema(self):
        for config in (None, [], {'enabled': 1}, {'levels': []}, {'levels': ['L1']},
                       {'levels': ['L2', 'L2']}, {'levels': [[]]}, {'timeout_seconds': 300}):
            with self.subTest(config=config), mock.patch('sage.profile_validate._schema_issues', return_value=[]):
                self.profile['pdca']['plan_review'] = config
                issues = validate_profile(self.profile, str(self.root))
                self.assertTrue(any(s == 'FAIL' and getattr(d, 'code', '') == 'plan_review.config_invalid'
                                    for s, d in issues))

    def test_standard_snapshot_direct_save_and_controlled_contract(self):
        result = self.execute()
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertIsNone(result['usage'])
        self.assertEqual(len(result['inputs']), 3)
        entry = result['inputs'][0]
        self.assertEqual(entry['sha256'], hashlib.sha256(
            (self.root / self.plans[0]).read_bytes()).hexdigest())
        stored = Path(result['output_path'])
        self.assertEqual(json.loads(stored.read_text()), result)
        self.assertTrue(stored.is_relative_to(self.root / '.sage/plan-reviews'))
        _, kwargs = self.invoke.call_args
        self.assertTrue(kwargs['require_controls'])
        self.assertIsNone(kwargs.get('root'))
        self.assertIn('Do not read any additional files', kwargs['contract'])
        self.assertNotIn('Verification evidence in the packet is authoritative', kwargs['contract'])

    def test_level_excluded_before_host_and_source(self):
        self.profile['pdca']['plan_review']['levels'] = ['L2']
        self.write_profile()
        self.args.host = 'claude'
        self.args.source = ['missing']
        self.assertEqual(self.execute()['reason'], 'level_excluded')
        self.invoke.assert_not_called()

    def test_wrong_stem_language_phase_and_host_never_launch(self):
        path = self.root / self.plans[1]
        original = path.read_text()
        for content in (original.replace('test', 'other'),
                        original.replace('ko', 'en'), '```\n' + original + '```\n'):
            with self.subTest(content=content):
                path.write_text(content)
                self.assertEqual(self.execute()['status'], 'INVALID_INPUT')
        path.write_text(original)
        self.args.plan = self.plans[:2]
        self.assertEqual(self.execute()['status'], 'INVALID_INPUT')
        self.args.plan = self.plans
        self.args.host = 'claude'
        self.assertEqual(self.execute()['reason'], 'host_mismatch')
        self.invoke.assert_not_called()

    def test_bad_sources_and_limits_do_not_launch(self):
        for source in ('https://example.invalid/data', '.', 'missing.txt'):
            self.args.source = [source]
            self.assertEqual(self.execute()['status'], 'INVALID_INPUT')
        binary = self.root / 'binary'
        binary.write_bytes(b'a\x00b')
        self.args.source = ['binary']
        self.assertEqual(self.execute()['status'], 'INVALID_INPUT')
        self.args.source = []
        self.args.max_input_bytes = 4096
        (self.root / self.plans[1]).write_text('x' * 5000)
        self.assertEqual(self.execute()['status'], 'INVALID_INPUT')
        self.invoke.assert_not_called()

    def test_sources_deduplicate_by_realpath_and_allow_explicit_external_file(self):
        with tempfile.TemporaryDirectory() as ext:
            source = Path(ext) / 'source.txt'
            source.write_text('external explicit source')
            alias = self.root / 'alias'
            try:
                alias.symlink_to(source)
            except OSError:
                self.skipTest('symlink unavailable')
            self.args.source = [str(source), str(alias), self.plans[0]]
            result = self.execute()
            self.assertEqual(result['status'], 'COMPLETE')
            self.assertEqual(len(result['inputs']), 4)
            self.assertEqual(result['inputs'][0]['roles'], ['plan', 'source'])

    def test_plan_must_be_in_repository(self):
        with tempfile.TemporaryDirectory() as ext:
            p = Path(ext) / 'test.md'
            p.write_text((self.root / self.plans[0]).read_text())
            self.args.plan = [str(p)] + self.plans[1:]
            self.assertEqual(self.execute()['status'], 'INVALID_INPUT')
        self.invoke.assert_not_called()

    def test_stale_preserves_original_snapshot_and_review(self):
        original = (self.root / self.plans[0]).read_bytes()
        def change(*a, **kw):
            (self.root / self.plans[0]).write_text('changed')
            return PeerRun('codex', ok=True, review='findings', controls='full')
        self.invoke.side_effect = change
        result = self.execute()
        self.assertEqual(result['status'], 'STALE')
        self.assertEqual(result['inputs'][0]['sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(result['review_text'], 'findings')
        self.assertTrue(result['source_changed'])

    def test_failure_partial_control_warning_and_missing_usage(self):
        for peer, expected in [
            (PeerRun('codex', reason='cli_missing'), 'FAILED'),
            (PeerRun('codex', reason='timeout', partial='FINDING: P1'), 'PARTIAL'),
            (PeerRun('codex', reason='controls_unsupported'), 'UNSUPPORTED'),
            (PeerRun('codex', ok=True, review='text', controls='none'), 'PARTIAL'),
        ]:
            with self.subTest(expected=expected):
                self.invoke.return_value = peer
                self.assertEqual(self.execute()['status'], expected)
        peer = PeerRun('codex', ok=True, review='text', controls='full')
        peer.warnings = ['test command observed']
        self.invoke.return_value = peer
        self.assertEqual(self.execute()['status'], 'PARTIAL')

    def test_existing_output_and_symlink_output_rejected_before_launch(self):
        target = self.root / '.sage/plan-reviews/already.json'
        target.parent.mkdir(parents=True)
        target.write_text('keep')
        self.args.output = str(target)
        self.assertEqual(self.execute()['status'], 'INVALID_INPUT')
        self.assertEqual(target.read_text(), 'keep')
        self.args.output = str(self.root / 'out.json')
        self.assertEqual(self.execute()['status'], 'INVALID_INPUT')
        self.invoke.assert_not_called()

    def test_output_failure_retains_review_with_non_success_status(self):
        with mock.patch.object(PR, 'save_result', side_effect=OSError('disk unavailable')):
            result = self.execute()
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['reason'], 'output_write_failed')
        self.assertEqual(result['execution_status'], 'COMPLETE')
        self.assertIn('FINDINGS', result['review_text'])

    def test_fast_composite_before_open_uses_actual_risk(self):
        p = self.root / self.plans[0]
        p.write_text('Cycle-Stem: test\nDocument-Language: ko\nRisk Level: L3\n'
                     'Cycle-Mode: FAST\nFast-Audit-Run: pending\nFast-Review-Level: L2\n'
                     + ''.join(f'## Phase {n}\n계획\n' for n in ('00','01','02','03','04')))
        self.args.plan = [self.plans[0]]
        result = self.execute()
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['risk'], 'L3')
        self.assertEqual(result['mode'], 'fast')
        self.assertFalse((self.root / '.sage/fast_cycle.jsonl').exists())

    def test_old_cli_control_guard_runs_before_process_and_default_is_unchanged(self):
        with mock.patch('sage.peer_process.shutil.which', return_value='/fake/codex'), \
             mock.patch('sage.peer_process.cli_version', return_value=(0, 100, 0)), \
             mock.patch('sage.peer_process.run_process', return_value=(0, '', '', False, 0)) as process:
            self.assertEqual(run_peer('codex', 'packet', 30, require_controls=True).reason,
                             'controls_unsupported')
            process.assert_not_called()
            run_peer('codex', 'packet', 30)
            process.assert_called_once()

    @unittest.skipIf(os.name == 'nt', 'POSIX executable fixture; Windows process coverage is separate')
    def test_both_native_cli_streams_get_packet_only_contract_and_clean_environment(self):
        bindir = self.root / 'bin'
        bindir.mkdir()
        script = '''#!{python}
import json, os, sys
from pathlib import Path
host = Path(sys.argv[0]).name
if '--version' in sys.argv:
    print('0.169.0' if host == 'codex' else '2.1.325'); sys.exit(0)
Path(os.environ['PLAN_REVIEW_PROBE']).write_text(json.dumps(dict(
    prompt=sys.stdin.read(), argv=sys.argv, cwd=os.getcwd(),
    host=os.environ.get('SAGE_HOST'), parent=os.environ.get('CLAUDECODE'))))
text = 'FINDINGS: none\\nREVIEWED: packet\\nUNVERIFIED: implementation'
if host == 'codex':
    print(json.dumps(dict(type='item.completed', item=dict(type='agent_message', text=text))))
    print(json.dumps(dict(type='turn.completed', usage=dict(input_tokens=100, cached_input_tokens=20, output_tokens=10))))
else:
    print(json.dumps(dict(type='result', result=text, is_error=False, num_turns=1,
                         usage=dict(input_tokens=80, cache_read_input_tokens=20, output_tokens=10))))
'''.format(python=sys.executable)
        for host in ('claude', 'codex'):
            binary = bindir / host
            binary.write_text(script)
            binary.chmod(0o755)
        for host in ('claude', 'codex'):
            with self.subTest(host=host):
                probe = self.root / 'probe.json'
                self.args.host = host
                with mock.patch.object(PR, 'detect_current_host', return_value=host), \
                     mock.patch.object(PR, 'run_peer', run_peer), \
                     mock.patch.dict(os.environ, {'PATH': str(bindir) + os.pathsep + os.environ['PATH'],
                         'PLAN_REVIEW_PROBE': str(probe), 'CLAUDECODE': '1',
                         'CODEX_HOME': str(self.root / 'fake-codex-home')}):
                    result = self.execute()
                self.assertEqual(result['status'], 'COMPLETE', result)
                sent = json.loads(probe.read_text())
                self.assertNotEqual(sent['cwd'], str(self.root))
                self.assertEqual(sent['host'], host)
                self.assertIsNone(sent['parent'])
                self.assertIn('Do not read any additional files', sent['prompt'])
                self.assertNotIn('Exploration budget', sent['prompt'])
                self.assertNotIn('--add-dir', sent['argv'])
                self.assertEqual(result['usage']['output'], 10)
                self.assertTrue(Path(result['output_path']).is_file())

    def test_final_prompt_overhead_counts_toward_cap_and_bom_is_accepted(self):
        p = self.root / self.plans[0]
        p.write_bytes(b'\xef\xbb\xbf' + p.read_bytes())
        self.assertEqual(self.execute()['status'], 'COMPLETE')
        self.invoke.reset_mock()
        source = self.root / 'source.txt'
        source.write_text('a' * 2800)
        self.args.source = ['source.txt']
        self.args.max_input_bytes = 4096
        result = self.execute()
        self.assertEqual((result['status'], result['reason']), ('INVALID_INPUT', 'input_too_large'))
        self.invoke.assert_not_called()

    def test_output_symlink_parent_and_creation_race_never_overwrite(self):
        link = self.root / '.sage'
        outside = self.root / 'outside'
        outside.mkdir()
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('symlink unavailable')
        self.assertEqual(self.execute()['status'], 'INVALID_INPUT')
        self.invoke.assert_not_called()
        link.unlink()
        target = self.root / '.sage/plan-reviews/race.json'
        self.args.output = str(target)
        def race(*a, **kw):
            target.write_text('other writer')
            return PeerRun('codex', ok=True, review='findings', controls='full')
        self.invoke.side_effect = race
        result = self.execute()
        self.assertEqual(result['reason'], 'output_write_failed')
        self.assertEqual(target.read_text(), 'other writer')

    def _native_result(self, host, events):
        stream = '\n'.join(json.dumps(e) for e in events)
        with mock.patch.object(PR, 'detect_current_host', return_value=host), \
             mock.patch.object(PR, 'run_peer', run_peer), \
             mock.patch.object(peer_process.shutil, 'which', return_value='/fake/' + host), \
             mock.patch.object(peer_process, 'cli_version', return_value=(999, 0, 0)), \
             mock.patch.object(peer_process, 'run_process', return_value=(0, stream, '', False, 0)):
            self.args.host = host
            return self.execute()

    def test_observed_codex_tools_cannot_complete_packet_review(self):
        for kind in ('mcp_tool_call', 'web_search', 'file_change', 'todo_list'):
            with self.subTest(kind=kind):
                result = self._native_result('codex', [
                    {'type': 'item.started', 'item': {'id': 'tool-1', 'type': kind}},
                    {'type': 'item.completed', 'item': {'id': 'tool-1', 'type': kind}},
                    {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'review'}}])
                self.assertEqual(result['status'], 'PARTIAL')
                self.assertEqual(result['audit']['tool_calls'], 1)
                self.assertEqual(result['reason'], 'control_violation')

    def test_missing_or_malformed_tool_ids_are_reported_without_crashing(self):
        for identity in (None, ['malformed'], ''):
            with self.subTest(identity=identity):
                events = [{'type': phase, 'item': {'id': identity, 'type': 'mcp_tool_call'}}
                          for phase in ('item.started', 'item.completed')]
                events.append({'type': 'item.completed',
                               'item': {'type': 'agent_message', 'text': 'review'}})
                result = self._native_result('codex', events)
                self.assertEqual(result['status'], 'PARTIAL')
                self.assertTrue(any('tool_identity_unavailable' in w for w in result['warnings']))

    def test_absent_native_usage_object_stays_unknown(self):
        for host, event in [('codex', {'type': 'item.completed',
                                     'item': {'type': 'agent_message', 'text': 'review'}}),
                            ('claude', {'type': 'result', 'result': 'review', 'is_error': False})]:
            with self.subTest(host=host):
                self.assertIsNone(self._native_result(host, [event])['usage'])

    def test_missing_native_usage_stays_unknown_and_measured_zero_survives(self):
        for usage, expected in [({}, None),
                               ({'input_tokens': 10}, {'new_input': None, 'cached_input': None, 'output': None}),
                               ({'input_tokens': 10, 'cached_input_tokens': 0},
                                {'new_input': 10, 'cached_input': 0, 'output': None}),
                               ({'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0},
                                {'new_input': 0, 'cached_input': 0, 'output': 0})]:
            with self.subTest(usage=usage):
                result = self._native_result('codex', [
                    {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'review'}},
                    {'type': 'turn.completed', 'usage': usage}])
                self.assertEqual(result['usage'], expected)
        legacy = peer_process.summarize_codex_stream(json.dumps({'type': 'turn.completed', 'usage': {}}))
        self.assertEqual(legacy['usage']['output'], 0)

    def test_observed_claude_model_is_preserved_and_absent_model_stays_null(self):
        for model in ('observed-model', None):
            with self.subTest(model=model):
                events = [{'type': 'result', 'result': 'review', 'is_error': False}]
                if model:
                    events.insert(0, {'type': 'system', 'subtype': 'init', 'model': 'requested-alias'})
                    events.insert(1, {'type': 'assistant', 'message': {'model': model}})
                result = self._native_result('claude', events)
                self.assertEqual(result['model_observed'], model)
        result = self._native_result('claude', [
            {'type': 'system', 'subtype': 'init', 'model': 'header-reported-name'},
            {'type': 'result', 'result': 'review', 'is_error': False}])
        self.assertEqual(result['model_observed'], 'header-reported-name')

    def test_partial_claude_usage_does_not_fabricate_output_zero(self):
        result = self._native_result('claude', [{'type': 'result', 'result': 'review', 'is_error': False,
            'usage': {'input_tokens': 20, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}}])
        self.assertEqual(result['usage']['new_input'], 20)
        self.assertIsNone(result['usage']['output'])

    def test_known_native_usage_keeps_observed_child_session_totals(self):
        def account(run, *args):
            run.usage = {'new_input': 30, 'cached_input': 4, 'output': 7}
        with mock.patch.object(peer_process, '_account_codex_sessions', side_effect=account):
            result = self._native_result('codex', [
                {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'review'}},
                {'type': 'turn.completed', 'usage': {'input_tokens': 10, 'cached_input_tokens': 0,
                                                  'output_tokens': 2}}])
        self.assertEqual(result['usage'], {'new_input': 30, 'cached_input': 4, 'output': 7})

    def test_surrogate_review_round_trips_through_saved_and_stdout_json(self):
        text = 'native response ' + chr(0xd800)
        self.invoke.return_value = PeerRun('codex', ok=True, review=text, controls='full')
        result = self.execute()
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(json.loads(Path(result['output_path']).read_text())['review_text'], text)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(PR.run(self.args), 0)
        self.assertEqual(json.loads(output.getvalue().encode('utf-8'))['review_text'], text)


if __name__ == '__main__':
    unittest.main()
