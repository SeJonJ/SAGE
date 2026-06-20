#!/usr/bin/env python3
"""sage generate/validate --kind mcp 단위 (MCP = 4번째 거버넌스 자산 kind).

설계 plan_docs/mcp-asset-kind-plan.md (codex R1/R2 반영). 검증 매트릭스(§1.6):
정상 PASS · 시크릿 거부(FAIL/WARN) · staleness · 미지원 transport · managed-block 보존/소유권 ·
단일-target currentness · orphan · placeholder · TOML 유효성.
"""
import json
import os
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import generate as G, validate as V, review as R  # noqa: E402
from sage import mcp_common as M  # noqa: E402


class GArgs:
    def __init__(self, dest, target="both", write=True, id=None):
        self.dest = dest; self.kind = "mcp"; self.target = target
        self.write = write; self.id = id; self.root = dest


class VArgs:
    def __init__(self, dest, kind="mcp"):
        self.dest = dest; self.kind = kind; self.root = dest; self.check = False
        self.schema = False; self.id = None


class RArgs:
    def __init__(self, dest, kind="mcp"):
        self.dest = dest; self.kind = kind; self.root = dest; self.batch = False; self.gate = False


def _inst(tmp):
    os.makedirs(os.path.join(tmp, "docs", "sage_harness", "mcps"), exist_ok=True)
    with open(os.path.join(tmp, "docs", "sage_harness", ".manifest.json"), "w") as f:
        f.write('{"sage_version":"0.1.0","host_runtime":"claude","assets":{}}')
    return tmp


def _spec(tmp, sid, body):
    p = os.path.join(tmp, "docs", "sage_harness", "mcps", f"{sid}.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return p


_CODEGRAPH = """---
id: codegraph
kind: mcp
transport: stdio
runtime_targets: [claude, codex]
server_binding:
  command: codegraph
  args: ["serve", "--mcp"]
  env: [CODEGRAPH_TOKEN]
---
## intent
Code intelligence knowledge graph.
"""


class TestParse(unittest.TestCase):
    def test_parse_ok(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); p = _spec(t, "codegraph", _CODEGRAPH)
            m = M.parse_mcp_spec(p)
            self.assertEqual(m["id"], "codegraph")
            self.assertEqual(m["transport"], "stdio")
            self.assertEqual(m["runtime_targets"], ["claude", "codex"])
            self.assertEqual(m["server_binding"]["env"], ["CODEGRAPH_TOKEN"])

    def test_unsupported_transport(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); p = _spec(t, "x", "---\nid: x\nkind: mcp\ntransport: ws\nruntime_targets: [claude]\nserver_binding: { command: x }\n---\n")
            self.assertRaises(M.MCPSpecError, M.parse_mcp_spec, p)

    def test_stdio_requires_command(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); p = _spec(t, "x", "---\nid: x\nkind: mcp\ntransport: stdio\nruntime_targets: [claude]\nserver_binding: {}\n---\n")
            self.assertRaises(M.MCPSpecError, M.parse_mcp_spec, p)

    def test_remote_requires_url(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); p = _spec(t, "x", "---\nid: x\nkind: mcp\ntransport: http\nruntime_targets: [claude]\nserver_binding: {}\n---\n")
            self.assertRaises(M.MCPSpecError, M.parse_mcp_spec, p)


class TestSecrets(unittest.TestCase):
    def _model(self, binding, transport="stdio", targets=("claude",)):
        return {"id": "x", "transport": transport, "runtime_targets": list(targets), "server_binding": binding}

    def test_inline_secret_in_args_fail(self):
        issues = M.check_secrets(self._model({"command": "x", "args": ["--api-key=sk_live_abcd1234efgh5678ijkl"]}))
        self.assertTrue(any(s == "FAIL" for s, _ in issues))

    def test_literal_env_value_fail(self):
        issues = M.check_secrets(self._model({"command": "x", "env": ["TOKEN=secret"]}))
        self.assertTrue(any(s == "FAIL" for s, _ in issues))

    def test_bare_env_name_ok(self):
        issues = M.check_secrets(self._model({"command": "x", "env": ["CODEGRAPH_TOKEN"]}))
        self.assertEqual([s for s, _ in issues if s == "FAIL"], [])

    def test_url_token_query_fail(self):
        issues = M.check_secrets(self._model({"url": "https://h/mcp?token=abcd1234efgh5678ij"}, transport="http"))
        self.assertTrue(any(s == "FAIL" for s, _ in issues))

    def test_url_userinfo_fail(self):
        issues = M.check_secrets(self._model({"url": "https://user:pass@h/mcp"}, transport="http"))
        self.assertTrue(any(s == "FAIL" for s, _ in issues))

    def test_hi_entropy_standalone_is_warn_not_fail(self):
        # 고엔트로피 단독(컨텍스트 없음) → WARN (base64-ish 정상값 오탐 방지, codex R2 P1)
        issues = M.check_secrets(self._model({"command": "x", "args": ["YWJjZGVmZ2hpamtsbW5vcDEyMzQ1"]}))
        self.assertTrue(any(s == "WARN" for s, _ in issues))
        self.assertEqual([s for s, _ in issues if s == "FAIL"], [])

    def test_home_path_is_warn(self):
        issues = M.check_secrets(self._model({"command": "/Users/alice/bin/srv"}))
        self.assertTrue(any(s == "WARN" for s, _ in issues))


class TestGenerate(unittest.TestCase):
    def test_generate_both_targets(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "codegraph", _CODEGRAPH)
            self.assertEqual(G.run(GArgs(t)), 0)
            doc = json.loads(open(os.path.join(t, ".mcp.json")).read())
            self.assertIn("codegraph", doc["mcpServers"])
            self.assertEqual(doc["mcpServers"]["codegraph"]["env"]["CODEGRAPH_TOKEN"], "${CODEGRAPH_TOKEN}")
            cfg = open(os.path.join(t, ".codex", "config.toml")).read()
            self.assertIn("[mcp_servers.codegraph]", cfg)
            self.assertIn(M.CODEX_BLOCK_START, cfg)

    def test_managed_block_preserves_non_mcp(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "codegraph", _CODEGRAPH)
            os.makedirs(os.path.join(t, ".codex"))
            open(os.path.join(t, ".codex", "config.toml"), "w").write('model = "gpt-5"\n\n[history]\npersistence = "save-all"\n')
            G.run(GArgs(t))
            cfg = open(os.path.join(t, ".codex", "config.toml")).read()
            self.assertIn('model = "gpt-5"', cfg)
            self.assertIn("[history]", cfg)
            self.assertIn("[mcp_servers.codegraph]", cfg)

    def test_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "codegraph", _CODEGRAPH)
            G.run(GArgs(t))
            a = open(os.path.join(t, ".codex", "config.toml")).read()
            G.run(GArgs(t))
            b = open(os.path.join(t, ".codex", "config.toml")).read()
            self.assertEqual(a, b)

    def test_secret_fail_aborts_before_write(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t)
            _spec(t, "bad", "---\nid: bad\nkind: mcp\ntransport: stdio\nruntime_targets: [claude]\nserver_binding:\n  command: x\n  args: [\"--token=abcd1234efgh5678ijkl\"]\n---\n")
            self.assertEqual(G.run(GArgs(t)), 1)
            self.assertFalse(os.path.exists(os.path.join(t, ".mcp.json")))   # fail-closed: 산출 안 함

    def test_ownership_collision_outside_block_fail(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "cg", "---\nid: cg\nkind: mcp\ntransport: stdio\nruntime_targets: [codex]\nserver_binding: { command: codegraph }\n---\n")
            os.makedirs(os.path.join(t, ".codex"))
            open(os.path.join(t, ".codex", "config.toml"), "w").write('[mcp_servers.cg]\ncommand = "other"\n')
            self.assertEqual(G.run(GArgs(t)), 1)

    def test_enabled_toggle_narrows(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "codegraph", _CODEGRAPH)
            _spec(t, "obsidian", "---\nid: obsidian\nkind: mcp\ntransport: stdio\nruntime_targets: [claude]\nserver_binding: { command: npx }\n---\n")
            os.makedirs(os.path.join(t, "sage"))
            open(os.path.join(t, "sage", "project-profile.yaml"), "w").write("mcp:\n  enabled: [codegraph]\n")
            G.run(GArgs(t, target="claude"))
            doc = json.loads(open(os.path.join(t, ".mcp.json")).read())
            self.assertEqual(sorted(doc["mcpServers"].keys()), ["codegraph"])   # obsidian 제외

    def test_enabled_unknown_spec_fail(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "codegraph", _CODEGRAPH)
            os.makedirs(os.path.join(t, "sage"))
            open(os.path.join(t, "sage", "project-profile.yaml"), "w").write("mcp:\n  enabled: [nonexistent]\n")
            self.assertEqual(G.run(GArgs(t)), 1)


class TestValidate(unittest.TestCase):
    def test_validate_pass(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "codegraph", _CODEGRAPH)
            G.run(GArgs(t))
            self.assertEqual(V.run(VArgs(t)), 0)

    def test_staleness_on_spec_edit(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); p = _spec(t, "cg", "---\nid: cg\nkind: mcp\ntransport: stdio\nruntime_targets: [claude]\nserver_binding: { command: codegraph, args: [\"serve\"] }\n---\n")
            G.run(GArgs(t))
            open(p, "w").write("---\nid: cg\nkind: mcp\ntransport: stdio\nruntime_targets: [claude]\nserver_binding: { command: codegraph, args: [\"serve\", \"--mcp\"] }\n---\n")
            self.assertEqual(V.run(VArgs(t)), 3)   # STALE

    def test_ownership_conflict_validate_fail(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "cg", "---\nid: cg\nkind: mcp\ntransport: stdio\nruntime_targets: [codex]\nserver_binding: { command: codegraph }\n---\n")
            G.run(GArgs(t))
            cfg = os.path.join(t, ".codex", "config.toml")
            generated = open(cfg).read()   # read 먼저(truncate 전) — managed-block 보존
            open(cfg, "w").write('[mcp_servers.cg]\ncommand = "rogue"\n\n' + generated)
            self.assertEqual(V.run(VArgs(t)), 1)   # FAIL 소유권 충돌(블록 밖 중복)

    def test_orphan_spec_warn(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "codegraph", _CODEGRAPH)   # generate 안 함 → manifest 미등록
            rc = V.run(VArgs(t))
            self.assertEqual(rc, 0)   # WARN = exit 0

    def test_mcp_json_extra_unmanaged_warn(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "codegraph", _CODEGRAPH)
            G.run(GArgs(t))
            doc = json.loads(open(os.path.join(t, ".mcp.json")).read())
            doc["mcpServers"]["rogue"] = {"command": "x"}
            open(os.path.join(t, ".mcp.json"), "w").write(json.dumps(doc))
            self.assertEqual(V.run(VArgs(t)), 0)   # WARN(비게이팅)


class TestR3Hardening(unittest.TestCase):
    """codex R3 적발 수정 회귀 가드 (P0 산출물 드리프트 / P1 타입·split시크릿·원자성 / P2 CRLF)."""

    def test_artifact_drift_mcp_json_stale(self):
        # P0: .mcp.json 직접편집(command 변조) → spec 과 불일치 → STALE
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "cg", "---\nid: cg\nkind: mcp\ntransport: stdio\nruntime_targets: [claude]\nserver_binding: { command: codegraph }\n---\n")
            G.run(GArgs(t, target="claude"))
            mj = os.path.join(t, ".mcp.json")
            doc = json.loads(open(mj).read())
            doc["mcpServers"]["cg"]["command"] = "rogue"
            open(mj, "w").write(json.dumps(doc))
            self.assertEqual(V.run(VArgs(t)), 3)   # STALE

    def test_artifact_drift_codex_block_stale(self):
        # P0: .codex managed-block 직접편집(가드 없음) → spec 조각 사라짐 → STALE
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "cg", "---\nid: cg\nkind: mcp\ntransport: stdio\nruntime_targets: [codex]\nserver_binding: { command: codegraph }\n---\n")
            G.run(GArgs(t, target="codex"))
            cfg = os.path.join(t, ".codex", "config.toml")
            edited = open(cfg).read().replace("codegraph", "rogue")   # read 먼저(truncate 전)
            open(cfg, "w").write(edited)
            self.assertEqual(V.run(VArgs(t)), 3)   # STALE

    def test_split_arg_secret_fail(self):
        # P1: ["--token", "<hi-entropy>"] split 형태 → FAIL (단독 WARN 아님)
        issues = M.check_secrets({"id": "x", "transport": "stdio", "runtime_targets": ["claude"],
                                  "server_binding": {"command": "x", "args": ["--token", "abcd1234efgh5678ijkl"]}})
        self.assertTrue(any(s == "FAIL" for s, _ in issues))

    def test_args_string_rejected(self):
        # P1: args 가 문자열이면 문자분해 직렬화되므로 MCPSpecError
        with tempfile.TemporaryDirectory() as t:
            _inst(t); p = _spec(t, "x", "---\nid: x\nkind: mcp\ntransport: stdio\nruntime_targets: [claude]\nserver_binding:\n  command: x\n  args: \"--mcp\"\n---\n")
            self.assertRaises(M.MCPSpecError, M.parse_mcp_spec, p)

    def test_id_with_dot_rejected(self):
        # P1: id 에 점 → TOML 중첩테이블 오인 → MCPSpecError
        with tempfile.TemporaryDirectory() as t:
            _inst(t); p = _spec(t, "bad", "---\nid: foo.bar\nkind: mcp\ntransport: stdio\nruntime_targets: [claude]\nserver_binding: { command: x }\n---\n")
            self.assertRaises(M.MCPSpecError, M.parse_mcp_spec, p)

    def test_generate_atomic_no_partial_on_codex_fail(self):
        # P1: codex 충돌로 FAIL 시 .mcp.json(claude) 도 안 써져야 함(원자성)
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "cg", "---\nid: cg\nkind: mcp\ntransport: stdio\nruntime_targets: [claude, codex]\nserver_binding: { command: codegraph }\n---\n")
            os.makedirs(os.path.join(t, ".codex"))
            open(os.path.join(t, ".codex", "config.toml"), "w").write('[mcp_servers.cg]\ncommand = "other"\n')
            self.assertEqual(G.run(GArgs(t, target="both")), 1)
            self.assertFalse(os.path.exists(os.path.join(t, ".mcp.json")))   # 부분상태 없음

    def test_crlf_frontmatter_parses(self):
        # P2: CRLF 줄바꿈 spec 파싱
        with tempfile.TemporaryDirectory() as t:
            _inst(t); p = os.path.join(t, "docs", "sage_harness", "mcps", "cr.md")
            open(p, "wb").write(b"---\r\nid: cr\r\nkind: mcp\r\ntransport: stdio\r\nruntime_targets: [claude]\r\nserver_binding: { command: x }\r\n---\r\nbody\r\n")
            m = M.parse_mcp_spec(p)
            self.assertEqual(m["id"], "cr")


class TestR4Hardening(unittest.TestCase):
    """codex R4 적발 수정 회귀 가드 (P0 codex substring 우회 / P1 oauth 오탐)."""

    def test_codex_drift_multiline_evasion_caught(self):
        # P0: managed-block 안 multiline 문자열에 기대 조각을 숨기고 실제 서버는 rogue → 구조비교로 STALE
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "cg", "---\nid: cg\nkind: mcp\ntransport: stdio\nruntime_targets: [codex]\nserver_binding: { command: codegraph }\n---\n")
            G.run(GArgs(t, target="codex"))
            cfg = os.path.join(t, ".codex", "config.toml")
            evasion = (f'{M.CODEX_BLOCK_START}\n'
                       'note = """\n[mcp_servers.cg]\ncommand = "codegraph"\n"""\n'
                       '[mcp_servers.cg]\ncommand = "rogue"\n'
                       f'{M.CODEX_BLOCK_END}\n')
            open(cfg, "w").write(evasion)
            self.assertEqual(V.run(VArgs(t)), 3)   # STALE (substring 이면 우회됐을 것)

    def test_codex_block_match_via_toml(self):
        # 정상 블록은 일치(false-positive 없음)
        mdl = {"id": "cg", "transport": "stdio", "runtime_targets": ["codex"], "server_binding": {"command": "codegraph", "args": ["serve"]}}
        block = M.serialize_codex_block([mdl])
        self.assertTrue(M.codex_block_has_server(block, mdl))

    def test_oauth_positional_not_fail(self):
        # P1: 'oauth' 위치인자(플래그 아님) 뒤 고엔트로피 → FAIL 아님(오탐 차단). 단독 WARN 은 허용.
        issues = M.check_secrets({"id": "x", "transport": "stdio", "runtime_targets": ["claude"],
                                  "server_binding": {"command": "x", "args": ["oauth", "abcd1234efgh5678ijkl"]}})
        self.assertEqual([s for s, _ in issues if s == "FAIL"], [])

    def test_token_flag_still_fails(self):
        # --token 뒤 고엔트로피 는 여전히 FAIL(앵커 후에도 정상 동작)
        issues = M.check_secrets({"id": "x", "transport": "stdio", "runtime_targets": ["claude"],
                                  "server_binding": {"command": "x", "args": ["--token", "abcd1234efgh5678ijkl"]}})
        self.assertTrue(any(s == "FAIL" for s, _ in issues))

    def test_injected_server_inside_managed_block_fail(self):
        # R5 P1: managed-block '안'에 미선언 [mcp_servers.rogue] 주입 → FAIL (SAGE 소유 영역 변조)
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "cg", "---\nid: cg\nkind: mcp\ntransport: stdio\nruntime_targets: [codex]\nserver_binding: { command: codegraph }\n---\n")
            G.run(GArgs(t, target="codex"))
            cfg = os.path.join(t, ".codex", "config.toml")
            injected = (f'{M.CODEX_BLOCK_START}\n[mcp_servers.cg]\ncommand = "codegraph"\n\n'
                        '[mcp_servers.rogue]\ncommand = "evil"\n'
                        f'{M.CODEX_BLOCK_END}\n')
            open(cfg, "w").write(injected)
            self.assertEqual(V.run(VArgs(t)), 1)   # FAIL

    def test_inside_block_servers_listed(self):
        block = (f'{M.CODEX_BLOCK_START}\n[mcp_servers.a]\ncommand = "x"\n[mcp_servers.a.env]\nK = "${{K}}"\n\n'
                 f'[mcp_servers.b]\ncommand = "y"\n{M.CODEX_BLOCK_END}\n')
        self.assertEqual(M.codex_servers_inside_block(block), ["a", "b"])   # env 서브테이블 오인 없음


class TestReview(unittest.TestCase):
    def test_single_target_is_auto(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "co", "---\nid: co\nkind: mcp\ntransport: stdio\nruntime_targets: [claude]\nserver_binding: { command: x }\n---\n")
            G.run(GArgs(t, target="claude"))
            # review 가 단일-target 을 'render 미최신' 으로 오분류하지 않아야 함
            self.assertEqual(R.run(RArgs(t)), 0)

    def test_review_gate_blocks_injected_block_server(self):
        # R6: review(--gate)도 managed-block 주입을 잡아 auto-approve 하지 않아야 함(end-to-end)
        with tempfile.TemporaryDirectory() as t:
            _inst(t); _spec(t, "cg", "---\nid: cg\nkind: mcp\ntransport: stdio\nruntime_targets: [codex]\nserver_binding: { command: codegraph }\n---\n")
            G.run(GArgs(t, target="codex"))
            cfg = os.path.join(t, ".codex", "config.toml")
            open(cfg, "w").write(f'{M.CODEX_BLOCK_START}\n[mcp_servers.cg]\ncommand = "codegraph"\n\n[mcp_servers.rogue]\ncommand = "evil"\n{M.CODEX_BLOCK_END}\n')
            ra = RArgs(t); ra.gate = True
            self.assertEqual(R.run(ra), 1)   # review --gate exit 1 (auto 아님)


class TestSerializeDeterminism(unittest.TestCase):
    def test_codex_block_byte_stable(self):
        m = {"id": "x", "transport": "stdio", "runtime_targets": ["codex"],
             "server_binding": {"command": "c", "args": ["a", "b"], "env": ["E1", "E2"]}}
        self.assertEqual(M.serialize_codex_block([m]), M.serialize_codex_block([m]))

    def test_block_replace_roundtrip(self):
        block1 = M.serialize_codex_block([{"id": "a", "transport": "stdio", "runtime_targets": ["codex"], "server_binding": {"command": "a"}}])
        txt = 'model = "x"\n\n' + block1
        block2 = M.serialize_codex_block([{"id": "a", "transport": "stdio", "runtime_targets": ["codex"], "server_binding": {"command": "b"}}])
        new, err = M.replace_codex_block(txt, block2)
        self.assertIsNone(err)
        self.assertIn('command = "b"', new)
        self.assertNotIn('command = "a"', new)
        self.assertIn('model = "x"', new)   # 블록 밖 보존
        self.assertEqual(new.count(M.CODEX_BLOCK_START), 1)   # 마커 1쌍 유지


if __name__ == "__main__":
    unittest.main(verbosity=2)
