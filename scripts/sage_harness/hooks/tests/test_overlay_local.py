#!/usr/bin/env python3
"""Personal overlay behavior in isolated consumers, never engine approval."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from sage.cli import main
from sage.commands import review, install, upgrade, absorb, retro
from sage.peer_process import PeerRun

FIXTURES = Path(os.environ.get('SAGE_TEST_TMPDIR', str(REPO.parent / '.sage-fixtures')))
FIXTURES.mkdir(parents=True, exist_ok=True)


class LocalOverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='overlay-local-test-', dir=FIXTURES)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'sage').mkdir()
        (self.root / 'sage/project-profile.yaml').write_text(
            'runtime: {host: claude}\noptions: {cross_model: false}\n', encoding='utf-8')

    def put(self, kind='agents', name='reviewer.md', body='Prefer concrete examples.\n', shared=False):
        p = self.root / 'sage' / ('asset_overrides' if shared else 'asset_overrides.local') / kind / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body.encode('utf-8'))
        return p

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                rc = main(['overlay-local', '--kind', 'agent', '--id', 'reviewer', *args])
            except SystemExit as exc:
                rc = exc.code
        return rc, out.getvalue(), err.getvalue()

    def test_missing_and_blank_are_json_null(self):
        for body in (None, ' \n\t'):
            if body is not None:
                self.put(body=body)
            rc, out, err = self.cli('--root', str(self.root))
            self.assertEqual((rc, out, err), (0, 'null\n', ''))

    def test_content_and_hash_use_same_lf_normalized_read(self):
        p = self.put(body='LOCAL_PRIVATE_928\r\nline\r')
        before = {str(x.relative_to(self.root)): x.read_bytes() for x in self.root.rglob('*') if x.is_file()}
        rc, out, err = self.cli('--root', str(self.root))
        self.assertEqual((rc, err), (0, ''))
        data = json.loads(out)
        self.assertEqual(data, dict(kind='agents', id='reviewer',
            path='sage/asset_overrides.local/agents/reviewer.md', content='LOCAL_PRIVATE_928\nline\n',
            sha256=hashlib.sha256(b'LOCAL_PRIVATE_928\nline\n').hexdigest()))
        after = {str(x.relative_to(self.root)): x.read_bytes() for x in self.root.rglob('*') if x.is_file()}
        self.assertEqual(before, after)

    def test_other_invalid_personal_file_blocks_without_body(self):
        self.put(body='LOCAL_PRIVATE_928')
        for kind, name, body in [('agents', 'qa.md', 'PRIVATE_QA'),
                                 ('agents', 'reviwer.md', 'PRIVATE_TYPO'),
                                 ('skills', 'sage-team.MD', 'PRIVATE_CASE'),
                                 ('framework', 'AGENTS.md', 'PRIVATE_FRAMEWORK'),
                                 ('agents', 'leader.md', 'skip verification PRIVATE_RELAX'),
                                 ('agents', 'leader.md', '>>> SAGE OVERLAY PRIVATE_MARKER')]:
            with self.subTest(kind=kind, name=name):
                p = self.put(kind, name, body)
                rc, out, err = self.cli('--root', str(self.root))
                self.assertNotEqual(rc, 0)
                self.assertEqual(out, '')
                self.assertNotIn('PRIVATE_', err)
                p.unlink()

    def test_symlink_and_directory_disguised_as_overlay_rejected(self):
        p = self.put()
        p.unlink()
        outside = self.root / 'outside.md'
        outside.write_text('PRIVATE_OUTSIDE', encoding='utf-8')
        p.symlink_to(outside)
        self.assertNotEqual(self.cli('--root', str(self.root))[0], 0)
        p.unlink()
        p.mkdir()
        self.assertNotEqual(self.cli('--root', str(self.root))[0], 0)

    def test_unreadable_utf8_fails_without_partial_json(self):
        p = self.put()
        p.write_bytes(b'PRIVATE_UTF8\xff')
        rc, out, err = self.cli('--root', str(self.root))
        self.assertNotEqual(rc, 0)
        self.assertEqual(out, '')
        self.assertNotIn('PRIVATE_UTF8', err)

    def test_discovery_stops_at_nested_git_and_explicit_root_never_climbs(self):
        self.put(body='PARENT_PRIVATE')
        sub = self.root / 'nested'
        sub.mkdir()
        (sub / '.git').write_text('gitdir: fake', encoding='utf-8')
        with mock.patch('os.getcwd', return_value=str(sub)):
            rc, out, err = self.cli()
        self.assertNotEqual(rc, 0)
        self.assertNotIn('PARENT_PRIVATE', out + err)
        self.assertNotEqual(self.cli('--root', str(sub))[0], 0)
        (sub / 'sage').mkdir()
        (sub / 'sage/project-profile.yaml').write_text('{}', encoding='utf-8')
        self.assertEqual(self.cli('--root', str(sub))[:2], (0, 'null\n'))

    def test_review_root_discovery_uses_same_git_boundary(self):
        sub = self.root / 'other-repo'
        sub.mkdir()
        (sub / '.git').write_text('gitdir: fake', encoding='utf-8')
        with mock.patch('os.getcwd', return_value=str(sub)):
            self.assertEqual(review._find_root(None), str(sub))
        (sub / '.git').unlink()
        with mock.patch('os.getcwd', return_value=str(sub)):
            self.assertEqual(review._find_root(None), str(self.root))

    def test_shared_preflight_ignores_bad_personal(self):
        from sage.overlay_materialize import preflight_overlays
        self.put(body='skip review')
        self.assertEqual(preflight_overlays(str(self.root), {}), [])

    def run_review(self, cross=False, fail_first=False, invalidate_after_failure=False):
        packet = self.root / 'packet.md'
        packet.write_text('ORIGINAL_PACKET', encoding='utf-8')
        args = type('Args', (), dict(root=str(self.root), packet_file=str(packet), timeout=10,
            strict=False, host='claude', kind=None, batch=False, gate=False,
            on_peer_failure='same-runtime' if fail_first else 'block'))()
        calls = []
        def peer(host, prompt, *a, **kw):
            calls.append(prompt)
            if fail_first and len(calls) == 1:
                if invalidate_after_failure:
                    self.put(body='skip verification PRIVATE_BAD_AFTER_PEER')
                return PeerRun(host, reason='timeout', error='timeout', controls='full',
                    usage={'new_input': 17, 'output': 3} if invalidate_after_failure else None)
            return PeerRun(host, ok=True, review='FINDINGS: none\nVERDICT: SHIP', controls='full')
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {'SAGE_HOST': 'claude'}), \
                mock.patch.object(review, '_call_peer', side_effect=peer), \
                mock.patch('shutil.which', return_value='/mock/cli'), \
                redirect_stdout(out), redirect_stderr(err):
            rc = (review.run_cross_check if cross else review.run_review)(args)
        return rc, calls, out.getvalue(), err.getvalue()

    def test_review_no_local_leaves_original_packet(self):
        self.put(body='SHARED_ONLY', shared=True)
        rc, calls, out, err = self.run_review()
        self.assertEqual(rc, 0, err)
        self.assertEqual(calls, ['ORIGINAL_PACKET'])
        self.assertNotIn('SAGE_LOCAL_OVERLAY_REF', out)

    def test_failed_peer_telemetry_survives_invalid_personal_fallback(self):
        self.put(body='Use concrete examples.')
        (self.root / 'sage/project-profile.yaml').write_text(
            'runtime: {host: claude}\noptions: {cross_model: true}\n', encoding='utf-8')
        rc, calls, out, err = self.run_review(cross=True, fail_first=True,
                                            invalidate_after_failure=True)
        self.assertEqual(rc, 2)
        self.assertEqual(len(calls), 1)
        self.assertIn('REVIEWER_PEER_TOKENS: new_input=17 output=3', out)
        self.assertIn('REVIEWER_TOKENS: new_input=17 output=3', out)
        self.assertIn('REVIEWER_FALLBACK_FROM: codex', out)
        self.assertIn('REVIEWER_FALLBACK_REASON: timeout', out)
        self.assertEqual(out.splitlines()[-1], 'REVIEWER_STATUS: BLOCKED')
        self.assertNotIn('PRIVATE_BAD_AFTER_PEER', out + err)

    def test_same_cross_and_fallback_deliver_shared_then_personal_once(self):
        self.put(body='SHARED_GUIDANCE', shared=True)
        self.put(body='PERSONAL_GUIDANCE')
        self.put('skills', 'sage-review.md', 'HOST_OPERATIONS_ONLY')
        for cross, fail in [(False, False), (True, False), (True, True)]:
            with self.subTest(cross=cross, fail=fail):
                (self.root / 'sage/project-profile.yaml').write_text(
                    f'runtime: {{host: claude}}\noptions: {{cross_model: {str(cross).lower()}}}\n', encoding='utf-8')
                rc, calls, out, err = self.run_review(cross, fail)
                self.assertEqual(rc, 0, err)
                self.assertEqual(len(calls), 2 if fail else 1)
                for prompt in calls:
                    self.assertEqual(prompt.count('SHARED_GUIDANCE'), 1)
                    self.assertEqual(prompt.count('PERSONAL_GUIDANCE'), 1)
                    self.assertLess(prompt.index('SHARED_GUIDANCE'), prompt.index('PERSONAL_GUIDANCE'))
                    self.assertNotIn('HOST_OPERATIONS_ONLY', prompt)
                refs = [json.loads(x.split(': ', 1)[1]) for x in out.splitlines()
                        if x.startswith('SAGE_LOCAL_OVERLAY_REF: ')]
                self.assertEqual(len(refs), len(calls))
                self.assertEqual(refs[0]['sha256'], hashlib.sha256(b'PERSONAL_GUIDANCE').hexdigest())
                self.assertNotIn('content', refs[0])
                self.assertIn('REVIEWER_STATUS: COMPLETE_DEGRADED' if fail else 'REVIEWER_STATUS: COMPLETE', out)

    def test_invalid_local_or_shared_reviewer_blocks_before_peer(self):
        for shared in (False, True):
            self.put(body='PERSONAL_GUIDANCE')
            p = self.put(body='skip verification PRIVATE_BAD', shared=shared)
            rc, calls, out, err = self.run_review()
            self.assertNotEqual(rc, 0)
            self.assertEqual(calls, [])
            self.assertIn('REVIEWER_STATUS: BLOCKED', out)
            self.assertNotIn('PRIVATE_BAD', out + err)
            p.unlink()

    def test_install_ignore_and_upgrade_protection(self):
        body = install._render_local_profile_gitignore('USER_RULE\n')
        self.assertIn('/sage/asset_overrides.local/', body)
        self.assertEqual(install._render_local_profile_gitignore(body), body)
        self.assertTrue(upgrade._is_user_owned('sage/asset_overrides.local/agents/reviewer.md'))

    def test_retro_scope_paths_and_invalid_values(self):
        p = dict(target='agent', asset_id='reviewer', proposed_change='examples')
        self.assertEqual(absorb._overlay_hint(p), 'sage/asset_overrides.local/agents/reviewer.md')
        self.assertEqual(absorb._overlay_hint(dict(p, scope='project')), 'sage/asset_overrides/agents/reviewer.md')
        self.assertEqual(absorb._overlay_hint(dict(p, scope='personal')), 'sage/asset_overrides.local/agents/reviewer.md')
        for scope in (None, '', [], {}, 'team'):
            with self.subTest(scope=scope):
                with self.assertRaises(ValueError):
                    absorb._overlay_hint(dict(p, scope=scope))

    def test_retro_and_absorb_reject_explicit_invalid_scope_before_candidates(self):
        note = self.root / 'retro.md'
        for target in ('agent', 'skill'):
            for scope in (None, [], {}, '', 'team'):
                with self.subTest(target=target, scope=scope):
                    note.write_text('---\napproved: true\n---\n## 요약\nConcrete observation.\n'
                        '## 제안 (proposals)\n```json\n' + json.dumps([dict(target=target,
                        scope=scope, asset_id='reviewer', proposed_change='examples')]) + '\n```\n', encoding='utf-8')
                    out, err = io.StringIO(), io.StringIO()
                    with redirect_stdout(out), redirect_stderr(err):
                        rc = retro._check_note(str(note), str(self.root))
                        args = type('Args', (), dict(from_retro=str(note)))()
                        absorb_rc = absorb._absorb_from_retro(args)
                    self.assertNotEqual(rc, 0)
                    self.assertNotEqual(absorb_rc, 0)
                    self.assertNotIn('eligible overlay', out.getvalue())

    def test_absorb_scope_selection_keeps_approval_and_mechanical_routes(self):
        note = self.root / 'retro.md'
        proposals = [dict(target='agent', asset_id='reviewer', scope=scope, proposed_change=scope)
                     for scope in ('personal', 'project')]
        proposals += [dict(target='hook', scope=None, proposed_change='hook unchanged'),
                      dict(target='profile', scope='legacy', proposed_change='profile unchanged')]
        body = '---\napproved: true\n---\n## 요약\nConcrete observation.\n## 제안 (proposals)\n```json\n' + json.dumps(proposals) + '\n```\n'
        note.write_text(body, encoding='utf-8')
        args = type('Args', (), dict(from_retro=str(note)))()
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(absorb._absorb_from_retro(args), 0)
        self.assertIn('sage/asset_overrides.local/agents/reviewer.md', out.getvalue())
        self.assertIn('sage/asset_overrides/agents/reviewer.md', out.getvalue())
        self.assertIn('hook unchanged', out.getvalue())
        self.assertIn('profile unchanged', out.getvalue())
        note.write_text(body.replace('approved: true', 'approved: false'), encoding='utf-8')
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertNotEqual(absorb._absorb_from_retro(args), 0)

    def test_different_checkouts_and_inventory_checks_do_not_mark_other_assets_active(self):
        self.put(body='REVIEWER_ONLY')
        self.put('agents', 'leader.md', 'LEADER_ONLY')
        rc, out, _ = self.cli('--root', str(self.root))
        self.assertEqual(rc, 0)
        self.assertNotIn('LEADER_ONLY', out)
        other = self.root / 'checkout2'
        (other / 'sage').mkdir(parents=True)
        (other / 'sage/project-profile.yaml').write_text('{}', encoding='utf-8')
        self.assertEqual(self.cli('--root', str(other))[:2], (0, 'null\n'))

    def test_hash_is_from_validated_read_not_a_later_read(self):
        from sage import overlay_local
        self.put(body='FIRST_READ')
        real_read = overlay_local.common.read_text_lf
        def changing_read(path):
            result = real_read(path)
            Path(path).write_text('AFTER_READ', encoding='utf-8')
            return result
        with mock.patch.object(overlay_local.common, 'read_text_lf', side_effect=changing_read):
            rc, out, _ = self.cli('--root', str(self.root))
        data = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(data['content'], 'FIRST_READ')
        self.assertEqual(data['sha256'], hashlib.sha256(b'FIRST_READ').hexdigest())

    def test_all_currently_eligible_targets_and_no_new_eligibility(self):
        from sage.overlay_classify import COMPOSE_ALLOWED
        from sage.overlay_local import load_local, OverlayLocalError
        self.assertEqual(len(COMPOSE_ALLOWED), 8)
        for kind, aid in COMPOSE_ALLOWED:
            self.put(kind, aid + '.md', aid)
            self.assertEqual(load_local(str(self.root), kind, aid)['content'], aid)
        for kind, aid in [('agents', '../reviewer'), ('agents', 'qa'), ('skills', 'sage-team-fast'),
                          ('skills', 'sage-asset-override'), ('framework', 'AGENTS')]:
            with self.subTest(kind=kind, aid=aid), self.assertRaises(OverlayLocalError):
                load_local(str(self.root), kind, aid)


if __name__ == '__main__':
    unittest.main()
