#!/usr/bin/env python3
"""Pure catalog development checks; no native/model acceptance or engine approval."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
FIXTURES = Path(os.environ.get('SAGE_TEST_TMPDIR', str(REPO.parent / '.sage-fixtures')))
FIXTURES.mkdir(parents=True, exist_ok=True)
IDS = ('sage-cycle', 'sage-plan', 'sage-team', 'sage-review',
       'sage-cycle-fast', 'sage-plan-fast', 'sage-team-fast')


class OverlayDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('sage.overlay_delivery'),
                             'pure overlay catalog collector is not implemented')
        from sage import overlay_delivery
        self.delivery = overlay_delivery
        self.tmp = tempfile.TemporaryDirectory(prefix='overlay-delivery-', dir=FIXTURES)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'sage').mkdir()
        self.profile = self.root / 'sage/project-profile.yaml'
        self.profile.write_text('{}\n', encoding='utf-8')

    def put(self, aid='sage-plan', body='Concrete guidance.\n', scope='shared', kind='skills'):
        path = self.root / 'sage' / ('asset_overrides' if scope == 'shared'
                                     else 'asset_overrides.local') / kind / (aid + '.md')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body.encode('utf-8'))
        return path

    def collect(self, role='root'):
        return self.delivery.collect_catalog(str(self.root), role)

    def test_empty_and_whitespace_catalog_explicitly_replace_previous_generation(self):
        empty = self.collect()
        self.assertEqual((empty['schema_version'], empty['root'], empty['role']),
                         (2, str(self.root.resolve()), 'root'))
        self.assertEqual((empty['sources'], empty['targets']), ({}, {}))
        path = self.put(body='First generation\n')
        active = self.collect()
        self.assertNotEqual(empty['generation'], active['generation'])
        path.write_text(' \n\t', encoding='utf-8')
        self.assertEqual(self.collect(), empty)
        path.unlink()
        self.assertEqual(self.collect(), empty)

    def test_fourteen_unique_sources_and_seven_views_have_exact_inheritance_order(self):
        for aid in IDS:
            for scope in ('shared', 'personal'):
                self.put(aid, body=aid + ' ' + scope + '\n', scope=scope)
        catalog = self.collect()
        self.assertEqual(len(catalog['sources']), 14)
        self.assertEqual(set(catalog['targets']), set(IDS))
        self.assertEqual(catalog['targets']['sage-plan'],
                         ['skills/sage-plan/shared', 'skills/sage-plan/personal'])
        self.assertEqual(catalog['targets']['sage-plan-fast'],
                         ['skills/sage-plan/shared', 'skills/sage-plan-fast/shared',
                          'skills/sage-plan/personal', 'skills/sage-plan-fast/personal'])
        self.assertNotIn('sage-review-fast', catalog['targets'])

    def test_standard_only_also_reaches_fast_without_reverse_inheritance(self):
        self.put('sage-plan', 'standard\n')
        catalog = self.collect()
        self.assertEqual(catalog['targets']['sage-plan-fast'], ['skills/sage-plan/shared'])
        self.put('sage-team-fast', 'fast only\n')
        catalog = self.collect()
        self.assertNotIn('sage-team', catalog['targets'])
        self.assertEqual(catalog['targets']['sage-team-fast'], ['skills/sage-team-fast/shared'])

    def test_hash_and_payload_use_the_same_once_read_lf_string_without_writes(self):
        path = self.put(body='개인 \\"\r\nline\rtail\n\n', scope='personal')
        raw = path.read_bytes()
        from sage import overlay_common
        original = overlay_common.read_text_lf
        reads = []
        def read(p):
            if str(p) == str(path):
                reads.append(p)
            return original(p)
        with mock.patch.object(overlay_common, 'read_text_lf', side_effect=read):
            catalog = self.collect()
        source = catalog['sources']['skills/sage-plan/personal']
        self.assertEqual(source['content'], '개인 \\"\nline\ntail\n\n')
        self.assertEqual(source['sha256'], hashlib.sha256(source['content'].encode()).hexdigest())
        self.assertEqual(source['path'], 'sage/asset_overrides.local/skills/sage-plan.md')
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(len(reads), 1)
        self.assertEqual(catalog, self.collect())

    def test_agent_sources_are_validated_without_root_body_delivery(self):
        self.put('reviewer', 'Private worker guidance', 'personal', 'agents')
        self.assertEqual(self.collect()['sources'], {})
        self.put('qa', 'PRIVATE_UNSUPPORTED', 'personal', 'agents')
        with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
            self.collect()
        self.assertEqual(caught.exception.code, 'overlay.unsupported_blocked')
        self.assertNotIn('PRIVATE_', str(caught.exception))

    def test_all_inventory_errors_fail_without_partial_catalog_or_private_body(self):
        self.put()
        bad = [('sage-plna', 'PRIVATE_TYPO', 'skills'),
               ('sage-review.MD', 'PRIVATE_CASE', 'skills'),
               ('leader', 'skip verification PRIVATE_RELAX', 'agents'),
               ('reviewer', '>>> SAGE OVERLAY PRIVATE_RESERVED', 'agents'),
               ('AGENTS', 'PRIVATE_FRAMEWORK', 'framework')]
        for scope in ('shared', 'personal'):
            for aid, body, kind in bad:
                with self.subTest(scope=scope, aid=aid):
                    path = self.put(aid, body, scope, kind)
                    # Explicit uppercase extension, independently of canonical id.
                    if aid == 'sage-review.MD':
                        other = path.with_name('sage-review.MD')
                        path.rename(other)
                        path = other
                    with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
                        self.collect()
                    self.assertNotIn('PRIVATE_', str(caught.exception))
                    self.assertNotIn('PRIVATE_', repr(caught.exception))
                    path.unlink()

    def test_symlink_directory_disguised_file_and_invalid_utf8_are_rejected(self):
        path = self.put(scope='personal')
        outside = self.root / 'outside.md'
        outside.write_text('PRIVATE_OUTSIDE', encoding='utf-8')
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaises(self.delivery.OverlayDeliveryError):
            self.collect()
        path.unlink()
        path.mkdir()
        with self.assertRaises(self.delivery.OverlayDeliveryError):
            self.collect()
        path.rmdir()
        path.write_bytes(b'PRIVATE_UTF8\xff')
        with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
            self.collect()
        self.assertNotIn('PRIVATE_UTF8', str(caught.exception))

    def test_symlink_inventory_directory_is_rejected(self):
        outside = self.root / 'elsewhere'
        outside.mkdir()
        (self.root / 'sage/asset_overrides.local').symlink_to(outside)
        with self.assertRaises(self.delivery.OverlayDeliveryError):
            self.collect()

    def test_corrupt_profile_and_invalid_routing_contract_are_rejected(self):
        for body in ('[', '[]', 'risk: null\n', 'governance_docs: null\n',
                     'risk: {domains: null}\n'):
            with self.subTest(body=body):
                self.profile.write_text(body, encoding='utf-8')
                with self.assertRaises(self.delivery.OverlayDeliveryError):
                    self.collect()

    def test_profile_yaml_json_mismatch_is_rejected(self):
        (self.root / 'sage/project-profile.json').write_text('{"different": true}', encoding='utf-8')
        with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
            self.collect()
        self.assertEqual(caught.exception.code, 'materialize.profile_yaml_json_mismatch')

    def test_explicit_other_root_never_reads_parent_personal_guidance(self):
        self.put(body='PRIVATE_PARENT', scope='personal')
        child = self.root / 'child'
        (child / 'sage').mkdir(parents=True)
        (child / 'sage/project-profile.yaml').write_text('{}', encoding='utf-8')
        catalog = self.delivery.collect_catalog(str(child))
        self.assertEqual(catalog['sources'], {})
        self.assertEqual(catalog['root'], str(child.resolve()))

    def test_nonroot_role_suppresses_root_sources_but_does_not_skip_validation(self):
        self.put(body='PRIVATE_ROOT')
        catalog = self.collect('reviewer')
        self.assertEqual(catalog['role'], 'reviewer')
        self.assertEqual((catalog['sources'], catalog['targets']), ({}, {}))
        self.put('qa', 'PRIVATE_INVALID', kind='agents')
        with self.assertRaises(self.delivery.OverlayDeliveryError):
            self.collect('reviewer')

    def test_blocked_fast_target_cannot_inherit_a_standard_source(self):
        self.put()
        from sage import overlay_classify
        original = overlay_classify.classify
        with mock.patch.object(overlay_classify, 'classify', side_effect=lambda kind, aid:
                               'blocked' if aid == 'sage-plan-fast' else original(kind, aid)):
            with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
                self.collect()
        self.assertEqual(caught.exception.code, 'overlay.unsupported_blocked')

    def test_changed_content_is_retried_from_fresh_snapshot_once(self):
        path = self.put(body='before\n')
        from sage import overlay_local
        original = overlay_local._read
        changed = False
        def read(*args):
            nonlocal changed
            text = original(*args)
            if not changed:
                changed = True
                path.write_text('after changed\n', encoding='utf-8')
            return text
        with mock.patch.object(overlay_local, '_read', side_effect=read):
            catalog = self.collect()
        self.assertEqual(catalog['sources']['skills/sage-plan/shared']['content'], 'after changed\n')

    def test_changed_inventory_is_retried_and_includes_new_source(self):
        self.put()
        from sage import overlay_local
        original = overlay_local._read
        changed = False
        def read(*args):
            nonlocal changed
            text = original(*args)
            if not changed:
                changed = True
                self.put('sage-review', 'new file\n', 'personal')
            return text
        with mock.patch.object(overlay_local, '_read', side_effect=read):
            catalog = self.collect()
        self.assertIn('skills/sage-review/personal', catalog['sources'])

    def test_continuously_changing_input_fails_after_one_retry(self):
        path = self.put()
        from sage import overlay_local
        original = overlay_local._read
        changes = []
        def read(*args):
            text = original(*args)
            changes.append(1)
            path.write_text('changed ' + 'x' * len(changes), encoding='utf-8')
            return text
        with mock.patch.object(overlay_local, '_read', side_effect=read):
            with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
                self.collect()
        self.assertEqual(caught.exception.code, 'overlay_delivery.unstable_snapshot')
        self.assertEqual(len(changes), 2)

    def _snapshot_acquisition_race(self, *, boundary, replacement=False, persistent=False):
        """Rename real input exactly after stat and before the requested listdir."""
        path = self.put(body='PRIVATE_VALID_RACE_SOURCE', scope='personal')
        directory = path.parent
        original_listdir = os.listdir
        visits, races = [], []
        def listdir(current):
            if Path(current) != directory:
                return original_listdir(current)
            visits.append(1)
            if len(visits) < boundary or (races and not persistent):
                return original_listdir(current)
            parked = self.root / ('parked-skills-' + str(len(races)))
            directory.rename(parked)
            races.append(1)
            if replacement:
                directory.write_text('PRIVATE_TRANSIENT_NOT_DIRECTORY', encoding='utf-8')
            try:
                return original_listdir(current)
            finally:
                if replacement:
                    directory.unlink()
                if replacement or persistent:
                    directory.mkdir()
                if persistent:
                    (directory / 'sage-plan.md').write_text('PRIVATE_VALID_RETRY_SOURCE',
                                                           encoding='utf-8')
        return listdir, races

    def test_first_snapshot_disappearance_or_replacement_retries_to_stable_empty(self):
        for replacement in (False, True):
            with self.subTest(replacement=replacement):
                listdir, races = self._snapshot_acquisition_race(
                    boundary=1, replacement=replacement)
                with mock.patch.object(self.delivery.os, 'listdir', side_effect=listdir):
                    try:
                        catalog = self.collect()
                    except self.delivery.OverlayDeliveryError as exc:
                        self.fail('stable retry was not collected: ' + exc.code)
                self.assertEqual((catalog['sources'], catalog['targets']), ({}, {}))
                self.assertEqual(len(races), 1)
                for parked in self.root.glob('parked-skills-*'):
                    for path in parked.iterdir():
                        path.unlink()
                    parked.rmdir()

    def test_final_snapshot_disappearance_or_replacement_discards_partial_and_retries(self):
        for replacement in (False, True):
            with self.subTest(replacement=replacement):
                listdir, races = self._snapshot_acquisition_race(
                    boundary=2, replacement=replacement)
                with mock.patch.object(self.delivery.os, 'listdir', side_effect=listdir):
                    try:
                        catalog = self.collect()
                    except self.delivery.OverlayDeliveryError as exc:
                        self.fail('stable retry was not collected: ' + exc.code)
                self.assertEqual((catalog['sources'], catalog['targets']), ({}, {}))
                self.assertEqual(len(races), 1)
                for parked in self.root.glob('parked-skills-*'):
                    for path in parked.iterdir():
                        path.unlink()
                    parked.rmdir()

    def test_persistent_snapshot_acquisition_race_stops_after_two_attempts(self):
        for boundary in (1, 2):
            for replacement in (False, True):
                with self.subTest(boundary=boundary, replacement=replacement):
                    listdir, races = self._snapshot_acquisition_race(
                        boundary=boundary, replacement=replacement, persistent=True)
                    with mock.patch.object(self.delivery.os, 'listdir', side_effect=listdir):
                        with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
                            self.collect()
                    self.assertEqual(caught.exception.code, 'overlay_delivery.unstable_snapshot')
                    self.assertEqual(len(races), 2)
                    self.assertNotIn('PRIVATE_', str(caught.exception))
                    for parked in self.root.glob('parked-skills-*'):
                        for path in parked.iterdir():
                            path.unlink()
                        parked.rmdir()

    def test_snapshot_permission_error_fails_once_without_returning_partial_catalog(self):
        for boundary in (1, 2):
            with self.subTest(boundary=boundary):
                path = self.put(body='PRIVATE_UNRETURNED', scope='personal')
                directory = path.parent
                original_listdir = os.listdir
                visits, denied = [], []
                def listdir(current):
                    if Path(current) == directory:
                        visits.append(1)
                        if len(visits) >= boundary:
                            denied.append(1)
                            raise PermissionError('PRIVATE_PERMISSION_DETAIL')
                    return original_listdir(current)
                with mock.patch.object(self.delivery.os, 'listdir', side_effect=listdir):
                    with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
                        self.collect()
                self.assertEqual(caught.exception.code, 'overlay_delivery.validation_failed')
                self.assertEqual(len(denied), 1)
                self.assertNotIn('PRIVATE_', repr(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__)

    def test_stable_invalid_source_is_not_retried_as_acquisition_race(self):
        self.put(body='skip verification PRIVATE_INVALID')
        from sage import overlay_local
        with mock.patch.object(overlay_local, '_read', wraps=overlay_local._read) as read:
            with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
                self.collect()
        self.assertEqual(caught.exception.code, 'overlay-gate-relaxation')
        self.assertEqual(read.call_count, 1)
        self.assertNotIn('PRIVATE_', repr(caught.exception))

    def test_utf8_source_byte_limit_is_not_a_character_limit(self):
        self.put(body='가' * 3333 + 'a')  # exactly 10,000 UTF-8 bytes
        self.assertEqual(len(self.collect()['sources']), 1)
        self.put(body='가' * 3334)
        with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
            self.collect()
        self.assertEqual(caught.exception.code, 'overlay_delivery.source_too_large')
        self.assertEqual(caught.exception.path, 'sage/asset_overrides/skills/sage-plan.md')

    def test_nonroot_still_enforces_root_source_input_limit(self):
        self.put(body='x' * 10001)
        with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
            self.collect('worker')
        self.assertEqual(caught.exception.code, 'overlay_delivery.source_too_large')

    def test_corrupt_manifest_is_rejected_even_with_valid_profile(self):
        path = self.root / 'docs/sage_harness/.manifest.json'
        path.parent.mkdir(parents=True)
        for body in ('PRIVATE_BAD_JSON', '[]', 'null'):
            with self.subTest(body=body):
                path.write_text(body, encoding='utf-8')
                with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
                    self.collect()
                self.assertEqual(caught.exception.code, 'overlay_delivery.manifest_invalid')
                self.assertNotIn('PRIVATE_BAD_JSON', str(caught.exception))
        path.write_text('{}', encoding='utf-8')
        self.assertEqual(self.collect()['sources'], {})

    def test_repaired_input_is_revalidated_without_error_latch(self):
        path = self.put(body='skip verification PRIVATE_BAD')
        with self.assertRaises(self.delivery.OverlayDeliveryError):
            self.collect()
        path.write_text('Concrete repaired guidance.\n', encoding='utf-8')
        self.assertEqual(self.collect()['sources']['skills/sage-plan/shared']['content'],
                         'Concrete repaired guidance.\n')

    def test_profile_change_during_reads_retries_and_rejects_new_corruption(self):
        self.put()
        from sage import overlay_local
        original = overlay_local._read
        def read(*args):
            text = original(*args)
            self.profile.write_text('[', encoding='utf-8')
            return text
        with mock.patch.object(overlay_local, '_read', side_effect=read):
            with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
                self.collect()
        self.assertEqual(caught.exception.code, 'materialize.profile_load_failed')

    def test_final_render_counts_json_escapes_and_wrapper_toward_total_budget(self):
        # Each source fits; escape expansion makes the final catalog exceed 49,152 bytes.
        for aid in ('sage-cycle', 'sage-plan', 'sage-team'):
            self.put(aid, body='"' * 9000)
        with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
            self.collect()
        self.assertEqual(caught.exception.code, 'overlay_delivery.catalog_too_large')

    def test_render_is_deterministic_json_with_scope_contract_and_no_truncation(self):
        self.put(body='끝 \\"\n')
        catalog = self.collect()
        rendered = self.delivery.render_catalog(catalog)
        self.assertEqual(rendered, self.delivery.render_catalog(catalog))
        self.assertIn('SAGE_OVERLAY_CATALOG_V2', rendered)
        self.assertIn('targets', rendered)
        self.assertIn('root', rendered)
        # JSON remains parseable within the stable wrapper.
        start = rendered.index('{')
        decoded, _ = json.JSONDecoder().raw_decode(rendered[start:])
        self.assertEqual(decoded, catalog)
        self.assertLessEqual(len(rendered.encode('utf-8')), 49152)

    def test_unexpected_validator_error_is_body_free_and_has_no_private_cause(self):
        self.put()
        from sage import overlay_local
        with mock.patch.object(overlay_local, '_read', side_effect=RuntimeError('PRIVATE_BODY')):
            with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
                self.collect()
        self.assertNotIn('PRIVATE_BODY', repr(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)


class HostBudgetTests(unittest.TestCase):
    def setUp(self):
        from sage import overlay_delivery
        self.delivery = overlay_delivery

    def test_utf16_counts_astral_characters_as_two_units(self):
        self.assertTrue(callable(getattr(self.delivery, 'utf16_code_units', None)),
                        'host budget measurement is not implemented')
        self.assertEqual(self.delivery.utf16_code_units('A한🚀'), 4)

    def test_claude_catalog_exact_7500_units_fits_but_next_unit_fails(self):
        self.assertTrue(callable(getattr(self.delivery, 'check_host_context', None)),
                        'host catalog budget is not implemented')
        text = '🚀' * 3750
        self.delivery.check_host_context(text, 'claude', catalog=True)
        with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
            self.delivery.check_host_context(text + 'x', 'claude', catalog=True)
        error = caught.exception
        self.assertEqual((error.code, error.observed, error.limit, error.unit),
                         ('overlay_delivery.host_catalog_too_large', 7501, 7500, 'utf16_code_units'))
        self.assertNotIn('🚀', str(error))

    def test_claude_merged_event_exact_10000_units_fits_next_unit_fails(self):
        self.assertTrue(callable(getattr(self.delivery, 'check_host_context', None)),
                        'host event budget is not implemented')
        text = '🚀' * 5000
        self.delivery.check_host_context(text, 'claude')
        with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
            self.delivery.check_host_context(text + 'x', 'claude')
        self.assertEqual((caught.exception.code, caught.exception.observed, caught.exception.limit),
                         ('overlay_delivery.host_context_too_large', 10001, 10000))
        self.delivery.check_host_context(text + 'x', 'codex')

    def test_host_render_counts_wrapper_and_json_escaping_without_lowering_common_cap(self):
        import inspect
        self.assertIn('runtime', inspect.signature(self.delivery.render_catalog).parameters,
                      'render host budget is not implemented')
        catalog = {'note': ''}
        overhead = len(self.delivery.render_catalog(catalog).encode('utf-16-le')) // 2
        catalog['note'] = 'x' * (7500 - overhead)
        rendered = self.delivery.render_catalog(catalog, runtime='claude')
        self.assertEqual(len(rendered.encode('utf-16-le')) // 2, 7500)
        catalog['note'] += '"'
        with self.assertRaises(self.delivery.OverlayDeliveryError) as caught:
            self.delivery.render_catalog(catalog, runtime='claude')
        self.assertEqual(caught.exception.observed, 7502)
        self.assertEqual(self.delivery.render_catalog(catalog),
                         self.delivery.render_catalog(catalog, runtime='codex'))


if __name__ == '__main__':
    unittest.main()
