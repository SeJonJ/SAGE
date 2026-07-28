#!/usr/bin/env python3
"""override_audit + _maybe_override 배선 단위 (외부검토 P1-5 — 게이트 BLOCK 합법 우회 + 감사).

핵심 teeth:
- 활성(미만료) override 가 있으면 hook_runtime._maybe_override 가 BLOCK decision 을 통과시키고
  bypass 를 .sage/override.jsonl 에 기록한다. 만료/게이트 불일치/override 부재면 우회 안 함(원래 BLOCK).
- TTL 만료 = 권한 자동 회수(상시 우회 방지). gate 스코프 = grant.gate ∈ {요청 gate, 'all'}.
- 감사로그는 append-only(grant + bypass 누적).
"""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.join(os.path.dirname(HERE), "runtime")
sys.path.insert(0, RUNTIME)
import override_audit as ov          # noqa: E402
import hook_runtime as hr            # noqa: E402

GATE = "pre-implementation-gate"
BLOCK = {"status": "block", "exit_code": 2, "message_key": "block_l3_strategy_unresolved"}
OK = {"status": "ok", "exit_code": 0, "message_key": None}
CHANGES = [{"path": "src/foo.py"}, {"path": "src/bar.py"}]


# 권한 캐시는 이제 저장소 밖 상태 디렉터리에 산다. 격리하지 않으면 테스트가 개발자의 실제
# ~/.local/state/sage 를 오염시킨다(구현 중 실제로 발생). 파일 전체에 강제한다.
_STATE_TMP = None


def setUpModule():
    global _STATE_TMP
    _STATE_TMP = tempfile.TemporaryDirectory()
    os.environ[ov.STATE_HOME_ENV] = _STATE_TMP.name


def tearDownModule():
    os.environ.pop(ov.STATE_HOME_ENV, None)
    _STATE_TMP.cleanup()


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
        # 주의: 이 테스트는 "권한 캐시가 커밋되지 않았다"를 가정하고 그 뒤를 검증한다. 가정 자체는
        # 아래 TestGrantStoreIsolation 이 실제 git 으로 검증한다(가정을 결론으로 쓰지 않기 위해).
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            ov.grant(src, "원격 우회", 50000, gate=GATE, now=1000)
            os.makedirs(os.path.dirname(ov.audit_path(dst)), exist_ok=True)
            with open(ov.audit_path(dst), "w", encoding="utf-8") as f:
                f.write(open(ov.audit_path(src), encoding="utf-8").read())
            # 감사 이력은 보이지만(추적 가능)
            self.assertTrue(any(r["event"] == "grant" for r in ov.read_records(dst)))
            # 활성 권한은 전파되지 않는다
            self.assertFalse(ov.is_override_active(dst, GATE, now=1500))


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True,
                   capture_output=True, text=True)


class TestGrantStoreIsolation(unittest.TestCase):
    """권한 캐시는 저장소가 실어나를 수 없어야 한다 — 손으로 고른 파일이 아니라 실제 git 으로 검증한다.

    teeth: 발급자가 `git add -A` 로 커밋해도(설치 프로젝트 기본값이 '추적'이라 정상 동작이다)
    다른 clone 에서 권한이 활성화되면 안 된다. 파일을 복사하지 않는 방식으로 모사하면 증명해야 할
    전제를 가정하게 되므로, 여기서는 git 이 실제로 옮기는 것만 옮기게 둔다.
    """

    def _repo(self, path):
        os.makedirs(path, exist_ok=True)
        _git(path, "init", "-q", ".")
        _git(path, "config", "user.email", "t@example.com")
        _git(path, "config", "user.name", "t")
        return path

    def test_committed_grant_does_not_activate_in_another_clone(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._repo(os.path.join(tmp, "src"))
            ov.grant(src, "긴급 배포", 50000, gate=GATE, user="alice", now=1000)
            self.assertTrue(ov.is_override_active(src, GATE, now=1500),
                            "발급자 본인에게는 활성이어야 한다")
            _git(src, "add", "-A")
            _git(src, "commit", "-q", "-m", "work")

            dst = os.path.join(tmp, "clone")
            subprocess.run(["git", "clone", "-q", src, dst], check=True,
                           capture_output=True, text=True)
            self.assertFalse(
                ov.is_override_active(dst, GATE, now=1500),
                "다른 clone 에서 남이 발급한 우회 권한이 활성화되면 안 된다")

    def test_gate_does_not_open_in_another_clone(self):
        """단위 판정뿐 아니라 실제 게이트 배선까지 닫혔는지 확인한다."""
        with tempfile.TemporaryDirectory() as tmp:
            src = self._repo(os.path.join(tmp, "src"))
            ov.grant(src, "긴급 배포", 50000, gate="all", user="alice")
            _git(src, "add", "-A")
            _git(src, "commit", "-q", "-m", "work")

            dst = os.path.join(tmp, "clone")
            subprocess.run(["git", "clone", "-q", src, dst], check=True,
                           capture_output=True, text=True)
            self.assertFalse(hr._maybe_override(GATE, dst, dict(BLOCK), CHANGES),
                             "clone 에서 BLOCK 이 열리면 안 된다")

    def test_audit_history_still_travels_with_the_repository(self):
        """권한은 막되 감사는 계속 공유돼야 한다 — 둘을 함께 막으면 추적성이 사라진다."""
        with tempfile.TemporaryDirectory() as tmp:
            src = self._repo(os.path.join(tmp, "src"))
            ov.grant(src, "긴급 배포", 50000, gate=GATE, user="alice")
            _git(src, "add", "-A")
            _git(src, "commit", "-q", "-m", "work")

            dst = os.path.join(tmp, "clone")
            subprocess.run(["git", "clone", "-q", src, dst], check=True,
                           capture_output=True, text=True)
            events = [r["event"] for r in ov.read_records(dst)]
            self.assertIn("grant", events, "감사 이력은 clone 에 따라와야 한다")


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

    def test_acceptance_and_fail_closed_blocks_are_not_overridable(self):
        protected = (
            "block_cycle_risk_declaration",
            "block_cycle_risk_reconciliation",
            "block_report_without_acceptance",
            "block_report_waiver_audit_failure",
            "block_gate_runtime_error",
            "block_cycle_stem_audit_failure",
        )
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "generic emergency override", 10000, gate="all")
            for message_key in protected:
                with self.subTest(message_key=message_key):
                    decision = {"status": "block", "exit_code": 2,
                                "message_key": message_key}
                    self.assertFalse(hr._maybe_override(GATE, tmp, decision, CHANGES))
            bypasses = [record for record in ov.read_records(tmp)
                        if record.get("event") == "bypass"]
            self.assertEqual(bypasses, [])

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


class TestListSurfacesEveryPassRoute(unittest.TestCase):
    """감사 뷰어가 모든 통과 축을 보여주는지. 로그에만 쌓이고 안 보이면 기록한 의미가 없다."""

    def test_cycle_stem_declarations_appear_in_list(self):
        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))))
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r", 10000, gate=GATE)
            ov.record_cycle_stem_declaration(tmp, GATE, "some_cycle", "sess-1", status="ok")
            proc = subprocess.run([sys.executable, "-m", "sage", "override", "--list",
                                   "--root", tmp], cwd=repo, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("cycle stem 선언 1건", proc.stdout)
        self.assertIn("some_cycle", proc.stdout)




class TestStateHomeResolution(unittest.TestCase):
    """권한 캐시 위치 해석 — 저장소 밖 + symlink 정규화 + 명시 지정 우선순위."""

    def test_store_lives_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.realpath(ov.grants_path(tmp))
            self.assertFalse(store.startswith(os.path.realpath(tmp) + os.sep),
                             f"권한 캐시가 저장소 트리 안에 있으면 git 이 실어나를 수 있다: {store}")

    def test_symlinked_root_resolves_to_the_same_store(self):
        # realpath 정규화가 없으면 같은 저장소가 두 키로 갈려, 한쪽에서 발급한 grant 가
        # 다른 쪽에서 안 보인다(운영자는 "발급했는데 왜 안 먹지"를 겪는다).
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.join(tmp, "real")
            os.makedirs(real)
            link = os.path.join(tmp, "link")
            os.symlink(real, link)
            self.assertEqual(ov.grants_path(real), ov.grants_path(link))

    def test_distinct_repositories_get_distinct_stores(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertNotEqual(ov.grants_path(a), ov.grants_path(b))

    def test_explicit_state_home_wins_over_xdg(self):
        env = {ov.STATE_HOME_ENV: "/explicit", "XDG_STATE_HOME": "/xdg"}
        self.assertEqual(ov.state_home(env), "/explicit")

    def test_xdg_state_home_is_namespaced(self):
        self.assertEqual(ov.state_home({"XDG_STATE_HOME": "/xdg"}),
                         os.path.join("/xdg", "sage"))

    def test_unresolvable_home_never_yields_a_relative_path(self):
        # HOME 미설정 + pwd 항목 부재면 expanduser 가 "~" 를 그대로 돌려준다. 상대경로가 되면
        # grants 가 CWD(보통 저장소 루트) 아래 생겨 이 사이클이 막은 전파가 되살아난다.
        with mock.patch.object(os.path, "expanduser", lambda p: p):
            home = ov.state_home({})
            self.assertTrue(os.path.isabs(home), f"상대경로로 떨어지면 안 된다: {home}")
            self.assertTrue(os.path.isabs(ov.grants_path("/some/repo", {})))

    def test_windows_prefers_localappdata(self):
        env = {"LOCALAPPDATA": r"C:\\Users\\x\\AppData\\Local"}
        with mock.patch.object(os, "name", "nt"):
            self.assertTrue(ov._candidate_state_home(env).startswith(env["LOCALAPPDATA"]))

    def test_xdg_still_wins_over_localappdata(self):
        env = {"XDG_STATE_HOME": "/xdg", "LOCALAPPDATA": r"C:\\Local"}
        with mock.patch.object(os, "name", "nt"):
            self.assertEqual(ov._candidate_state_home(env), os.path.join("/xdg", "sage"))

    def test_default_is_local_state(self):
        home = os.path.expanduser("~")
        self.assertEqual(ov.state_home({}),
                         os.path.join(home, ".local", "state", "sage"))

    def test_module_isolation_is_active(self):
        # 이 파일의 setUpModule 이 실제 상태 디렉터리를 가리지 못하면 테스트가 개발자 홈을
        # 오염시킨다. 격리 자체를 회귀로 고정한다.
        self.assertTrue(os.environ.get(ov.STATE_HOME_ENV),
                        "setUpModule 이 SAGE_STATE_HOME 을 설정해야 한다")
        self.assertNotIn(os.path.expanduser("~/.local/state/sage"),
                         ov.grants_path("/tmp/whatever"))


class TestBypassActor(unittest.TestCase):
    """우회를 '소비한' 주체를 남긴다 — 발급자와 사용자가 갈리면 감사가 엉뚱한 사람을 지목한다."""

    def test_bypass_records_the_consuming_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = ov.grant(tmp, "긴급 배포", 10000, gate=GATE, user="alice")
            ov.record_bypass(tmp, GATE, ["src/x.py"], "block_l3_strategy_unresolved",
                             g, user="bob")
            rec = [r for r in ov.read_records(tmp) if r["event"] == "bypass"][0]
            self.assertEqual(rec["user"], "bob")           # 소비자
            self.assertEqual(rec["grant_user"], "alice")   # 발급자
            self.assertNotEqual(rec["user"], rec["grant_user"])

    def test_bypass_falls_back_to_environment_user(self):
        with tempfile.TemporaryDirectory() as tmp:
            g = ov.grant(tmp, "r", 10000, gate=GATE, user="alice")
            ov.record_bypass(tmp, GATE, ["src/x.py"], "k", g)
            rec = [r for r in ov.read_records(tmp) if r["event"] == "bypass"][0]
            self.assertEqual(rec["user"], os.environ.get("USER") or "unknown")

    def test_gate_wiring_records_the_actor(self):
        with tempfile.TemporaryDirectory() as tmp:
            ov.grant(tmp, "r", 10000, gate=GATE, user="alice")
            self.assertTrue(hr._maybe_override(GATE, tmp, dict(BLOCK), CHANGES))
            rec = [r for r in ov.read_records(tmp) if r["event"] == "bypass"][0]
            self.assertTrue(rec.get("user"), "게이트 배선도 행위자를 남겨야 한다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
