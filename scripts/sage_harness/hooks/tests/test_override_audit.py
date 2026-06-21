#!/usr/bin/env python3
"""override_audit + _maybe_override 배선 단위 (외부검토 P1-5 — 게이트 BLOCK 합법 우회 + 감사).

핵심 teeth:
- 활성(미만료) override 가 있으면 hook_runtime._maybe_override 가 BLOCK decision 을 통과시키고
  bypass 를 .sage/override.jsonl 에 기록한다. 만료/게이트 불일치/override 부재면 우회 안 함(원래 BLOCK).
- TTL 만료 = 권한 자동 회수(상시 우회 방지). gate 스코프 = grant.gate ∈ {요청 gate, 'all'}.
- 감사로그는 append-only(grant + bypass 누적).
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.join(os.path.dirname(HERE), "runtime")
sys.path.insert(0, RUNTIME)
import override_audit as ov          # noqa: E402
import hook_runtime as hr            # noqa: E402

GATE = "pre-implementation-gate"
BLOCK = {"status": "block", "exit_code": 2, "message_key": "block_l3_strategy_unresolved"}
OK = {"status": "ok", "exit_code": 0, "message_key": None}
CHANGES = [{"path": "src/foo.py"}, {"path": "src/bar.py"}]


class TestParseTtl(unittest.TestCase):
    def test_units(self):
        self.assertEqual(ov.parse_ttl("90s"), 90)
        self.assertEqual(ov.parse_ttl("30m"), 1800)
        self.assertEqual(ov.parse_ttl("2h"), 7200)
        self.assertEqual(ov.parse_ttl("1d"), 86400)
        self.assertEqual(ov.parse_ttl("1800"), 1800)   # 단위 없으면 초

    def test_invalid_is_none(self):
        for bad in ("", "abc", "-5m", "0", "0s"):
            self.assertIsNone(ov.parse_ttl(bad), bad)


class TestTtlCap(unittest.TestCase):
    """N-R3: TTL 상한 — '시한부' 우회가 임의로 길어지면 사실상 상시 우회다."""

    def test_parse_does_not_cap(self):
        # parse 는 정책이 아니라 파싱만 — 큰 값도 그대로 반환(거부는 grant 에서).
        self.assertEqual(ov.parse_ttl("3650d"), 3650 * 86400)

    def test_grant_over_cap_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                ov.grant(tmp, "10년 우회 시도", ov.MAX_TTL_SECONDS + 1, gate=GATE, now=1000)
            self.assertEqual(ov.read_records(tmp), [])   # 거부 → 기록 없음

    def test_grant_at_cap_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = ov.grant(tmp, "상한 정확히", ov.MAX_TTL_SECONDS, gate=GATE, now=1000)
            self.assertEqual(rec["ttl_seconds"], ov.MAX_TTL_SECONDS)


class TestActiveGrants(unittest.TestCase):
    def test_unexpired_is_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r", 1000, gate=GATE, now=1000)
            self.assertTrue(ov.is_override_active(tmp, GATE, now=1500))   # 1500 < 1000+1000

    def test_expired_auto_revoked(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r", 100, gate=GATE, now=1000)
            self.assertFalse(ov.is_override_active(tmp, GATE, now=1101))  # 1101 > 1000+100

    def test_gate_scope_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r", 1000, gate="pre-phase4-checklist-gate", now=1000)
            self.assertFalse(ov.is_override_active(tmp, GATE, now=1100))

    def test_gate_all_matches_any(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r", 1000, gate="all", now=1000)
            self.assertTrue(ov.is_override_active(tmp, GATE, now=1100))
            self.assertTrue(ov.is_override_active(tmp, "pre-phase4-checklist-gate", now=1100))

    def test_no_log_not_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(ov.is_override_active(tmp, GATE))


class TestAuditPermissionSplit(unittest.TestCase):
    """감사 로그(커밋)와 권한 캐시(로컬)를 분리 — clone 시 권한 비전파, 감사는 추적 가능."""

    def test_grant_writes_both_audit_and_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r", 1000, gate=GATE, now=1000)
            self.assertTrue(os.path.exists(ov.audit_path(tmp)))    # 커밋용
            self.assertTrue(os.path.exists(ov.grants_path(tmp)))   # 로컬 집행용

    def test_bypass_only_in_audit_not_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = ov.grant(tmp, "r", 10000, gate=GATE)
            ov.record_bypass(tmp, GATE, ["src/x.py"], "block_l3_strategy_unresolved", g)
            local = ov._read_jsonl(ov.grants_path(tmp))
            self.assertEqual([r["event"] for r in local], ["grant"])   # bypass 는 권한 캐시에 없음
            audit = ov.read_records(tmp)
            self.assertEqual(sorted(r["event"] for r in audit), ["bypass", "grant"])

    def test_clone_inherits_audit_not_active_permission(self):
        # clone 모사: 감사 로그만 새 트리에 복사(.sage/tmp 권한 캐시는 비커밋이라 안 옴).
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            ov.grant(src, "원격 우회", 50000, gate=GATE, now=1000)
            os.makedirs(os.path.dirname(ov.audit_path(dst)), exist_ok=True)
            with open(ov.audit_path(dst), "w", encoding="utf-8") as f:
                f.write(open(ov.audit_path(src), encoding="utf-8").read())
            # 감사 이력은 보이지만(추적 가능)
            self.assertTrue(any(r["event"] == "grant" for r in ov.read_records(dst)))
            # 활성 권한은 전파되지 않는다
            self.assertFalse(ov.is_override_active(dst, GATE, now=1500))


class TestRevoke(unittest.TestCase):
    """만료 전 회수 — 오발급한 우회 권한을 즉시 무효화."""

    def test_revoke_deactivates_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = ov.grant(tmp, "실수 발급", 10000, gate=GATE, now=1000)
            self.assertTrue(ov.is_override_active(tmp, GATE, now=1100))
            rec = ov.revoke(tmp, g["grant_id"], reason="회수", now=1200)
            self.assertIsNotNone(rec)
            self.assertFalse(ov.is_override_active(tmp, GATE, now=1300))   # 만료(11000) 한참 전인데 비활성

    def test_revoke_unknown_id_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r", 10000, gate=GATE, now=1000)
            self.assertIsNone(ov.revoke(tmp, "nonexistent", now=1100))

    def test_revoke_recorded_in_audit_append_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = ov.grant(tmp, "r", 10000, gate=GATE, now=1000)
            ov.revoke(tmp, g["grant_id"], reason="오발급 회수", now=1200)
            events = [r["event"] for r in ov.read_records(tmp)]
            self.assertEqual(sorted(events), ["grant", "revoke"])   # grant 삭제 없이 revoke 추가

    def test_double_revoke_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = ov.grant(tmp, "r", 10000, gate=GATE, now=1000)
            self.assertIsNotNone(ov.revoke(tmp, g["grant_id"], now=1100))
            self.assertIsNone(ov.revoke(tmp, g["grant_id"], now=1200))   # 이미 회수 → 대상 없음

    def test_revoke_writes_enforcement_before_audit(self):
        # 회수는 집행 캐시를 먼저 써야 한다 — 감사부터 쓰면 감사 append 실패 시
        # "감사엔 회수, 집행엔 활성"인 무력화 상태가 생긴다. audit append 가 깨져도
        # 권한은 이미 비활성이어야 함을 보장.
        import unittest.mock as mock
        with tempfile.TemporaryDirectory() as tmp:
            g = ov.grant(tmp, "r", 10000, gate=GATE, now=1000)
            orig = ov._append
            audit = ov.audit_path(tmp)

            def flaky(path, record):
                if path == audit and record.get("event") == "revoke":
                    raise OSError("감사 디스크 실패 모사")
                return orig(path, record)

            with mock.patch.object(ov, "_append", flaky):
                with self.assertRaises(OSError):
                    ov.revoke(tmp, g["grant_id"], now=1100)
            # 감사 기록은 실패했어도 집행 캐시엔 회수가 반영돼 권한이 죽어 있어야 한다(fail-closed).
            self.assertFalse(ov.is_override_active(tmp, GATE, now=1200))


class TestMaybeOverrideWiring(unittest.TestCase):
    def test_block_with_active_override_passes_and_audits(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "긴급 우회", 10000, gate=GATE)   # 실시간 — 충분히 김
            passed = hr._maybe_override(GATE, tmp, BLOCK, CHANGES)
            self.assertTrue(passed)
            recs = ov.read_records(tmp)
            byp = [r for r in recs if r.get("event") == "bypass"]
            self.assertEqual(len(byp), 1)
            self.assertEqual(byp[0]["message_key"], "block_l3_strategy_unresolved")
            self.assertEqual(sorted(byp[0]["files"]), ["src/bar.py", "src/foo.py"])

    def test_block_without_override_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(hr._maybe_override(GATE, tmp, BLOCK, CHANGES))
            self.assertEqual(ov.read_records(tmp), [])   # bypass 기록 없음

    def test_non_block_never_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r", 10000, gate=GATE)
            self.assertFalse(hr._maybe_override(GATE, tmp, OK, CHANGES))   # ok → 우회 대상 아님

    def test_expired_override_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r", 1, gate=GATE, now=1000)   # 즉시 만료(실시간 now >> 1001)
            self.assertFalse(hr._maybe_override(GATE, tmp, BLOCK, CHANGES))

    def test_append_only_accumulates(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r1", 10000, gate=GATE)
            ov.grant(tmp, "r2", 10000, gate="all")
            hr._maybe_override(GATE, tmp, BLOCK, CHANGES)
            recs = ov.read_records(tmp)
            self.assertEqual(sum(1 for r in recs if r["event"] == "grant"), 2)
            self.assertEqual(sum(1 for r in recs if r["event"] == "bypass"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
