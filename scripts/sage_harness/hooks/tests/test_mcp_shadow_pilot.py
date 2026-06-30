#!/usr/bin/env python3
"""MCP shadow pilot — ChatForYou 선반영(Enhancement 축) 실물 산출 (codex R1 P0-2).

ChatForYou 의 실제 ungoverned MCP 서버(codegraph stdio + obsidian filesystem)를 SAGE fixture 로
가져와, 샌드박스 인스턴스에서 spec→.mcp.json(claude)+.codex/config.toml managed-block(codex) 생성→
validate PASS 까지 폐루프를 증명한다. **라이브 ChatForYou config 무변경**(전 작업이 tempdir 한정).

한계(plan §0.4, codex R1 P1-7): ChatForYou 실제 claude MCP 는 전역 ~/.claude.json 에 있고 본 파일럿은
프로젝트 .mcp.json 으로 직렬화 → codex 측은 실 리허설, claude 측은 test-data 수준. 과대해석 금지.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, REPO)
from sage.commands import generate as G, validate as V, asset_check as R  # noqa: E402

_FIXTURE = os.path.join(HERE, "fixtures", "mcp_chatforyou")


class GArgs:
    def __init__(self, dest, target="both"):
        self.dest = dest; self.kind = "mcp"; self.target = target
        self.write = True; self.id = None; self.root = dest


class VArgs:
    def __init__(self, dest):
        self.dest = dest; self.kind = "mcp"; self.root = dest
        self.check = False; self.schema = True; self.id = None


class RArgs:
    def __init__(self, dest):
        self.dest = dest; self.kind = "mcp"; self.root = dest; self.batch = False; self.gate = False


def _instance(tmp):
    """fixture spec 들을 샌드박스 인스턴스로 복사 + 빈 manifest + 기존 비-MCP codex 설정."""
    shutil.copytree(os.path.join(_FIXTURE, "docs"), os.path.join(tmp, "docs"))
    with open(os.path.join(tmp, "docs", "sage_harness", ".manifest.json"), "w") as f:
        f.write('{"sage_version":"0.1.0","host_runtime":"claude","assets":{}}')
    os.makedirs(os.path.join(tmp, ".codex"))
    # 기존 사용자 설정(비-MCP) — managed-block 이 보존하는지 증명
    with open(os.path.join(tmp, ".codex", "config.toml"), "w") as f:
        f.write('model = "gpt-5-codex"\napproval_policy = "on-request"\n')


class TestShadowPilot(unittest.TestCase):
    def test_chatforyou_servers_generate_and_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp)
            self.assertEqual(G.run(GArgs(tmp)), 0)

            # claude .mcp.json: 두 서버 결정론 직렬화
            doc = json.loads(open(os.path.join(tmp, ".mcp.json")).read())
            self.assertEqual(sorted(doc["mcpServers"].keys()), ["codegraph", "obsidian"])
            self.assertEqual(doc["mcpServers"]["codegraph"]["args"], ["serve", "--mcp"])

            # codex managed-block: 두 서버 + 기존 비-MCP 설정 보존
            cfg = open(os.path.join(tmp, ".codex", "config.toml")).read()
            self.assertIn('model = "gpt-5-codex"', cfg)          # 사용자 설정 보존
            self.assertIn('approval_policy = "on-request"', cfg)
            self.assertIn("[mcp_servers.codegraph]", cfg)
            self.assertIn("[mcp_servers.obsidian]", cfg)

            # validate PASS (+schema)
            self.assertEqual(V.run(VArgs(tmp)), 0)
            # review: 양 자산 auto-approved (deterministic, render current)
            self.assertEqual(R.run(RArgs(tmp)), 0)

    def test_no_live_mutation(self):
        """라이브 ChatForYou config 무변경 증명 — 모든 산출이 tempdir 안에만 존재."""
        with tempfile.TemporaryDirectory() as tmp:
            _instance(tmp)
            G.run(GArgs(tmp))
            # 산출물은 tempdir 하위에만
            self.assertTrue(os.path.exists(os.path.join(tmp, ".mcp.json")))
            self.assertTrue(os.path.realpath(os.path.join(tmp, ".mcp.json")).startswith(os.path.realpath(tmp)))
            # 실제 사용자 홈/프로젝트 경로는 손대지 않음(구조적 — generate 는 --dest 한정)
            self.assertFalse(os.path.exists(os.path.join(tmp, "..", ".mcp.json")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
