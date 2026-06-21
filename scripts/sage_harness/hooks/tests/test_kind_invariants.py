#!/usr/bin/env python3
"""test_kind_invariants — "고친 결함을 불변식으로 박제" 메타 회귀 (2차 외부검토 N-R2).

배경: 1차 하드닝(R3 계약버전·R4 AssetPaths 경로단일화)이 hook 에는 적용됐으나 *인스턴스*로만
적용돼, 가장 최근 추가된 표면(MCP)이 같은 결함 클래스를 재현했다(죽은 계약버전·경로 손조립).
이 테스트는 그 교훈을 *패턴*으로 강제 — 다음에 5번째 kind 가 추가돼도 자동으로 규약을 적용받는다.

박제 대상:
1. generate/validate 가 mcps spec 경로를 손조립하지 않는다(AssetPaths 경유 강제).
2. 모든 MCP manifest 엔트리가 계약버전(adapter_contract_version)을 스탬프한다(hook 3b 와 대칭).
3. 계약버전 불일치는 validate STALE 로 적발된다(teeth).
4. 스키마의 mcp 섹션이 닫혀 있다(additionalProperties:false — risk/pdca/output_contract 와 동등).
"""
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, REPO)
from sage.commands import generate as G, validate as V  # noqa: E402
from sage import mcp_common as M  # noqa: E402

# mcps 경로 손조립 패턴(os.path.join 의 "sage_harness","mcps" 인접). 메시지 문자열의 슬래시형
# (docs/sage_harness/mcps/...)은 일부러 매치하지 않는다 — 그건 경로 조립이 아니라 사용자 안내다.
_ASSEMBLY = re.compile(r"""["']sage_harness["']\s*,\s*["']mcps["']""")


class GArgs:
    def __init__(self, dest, target="both", write=True, id=None):
        self.dest = dest; self.kind = "mcp"; self.target = target
        self.write = write; self.id = id; self.root = dest


class VArgs:
    def __init__(self, dest, kind="mcp"):
        self.dest = dest; self.kind = kind; self.root = dest; self.check = False
        self.schema = False; self.id = None


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


def _inst(tmp):
    os.makedirs(os.path.join(tmp, "docs", "sage_harness", "mcps"), exist_ok=True)
    with open(os.path.join(tmp, "docs", "sage_harness", ".manifest.json"), "w") as f:
        f.write('{"sage_version":"0.1.0","host_runtime":"claude","assets":{}}')
    with open(os.path.join(tmp, "docs", "sage_harness", "mcps", "codegraph.md"), "w", encoding="utf-8") as f:
        f.write(_CODEGRAPH)
    return tmp


class TestNoDirectPathAssembly(unittest.TestCase):
    def test_generate_validate_no_mcps_handassembly(self):
        # AssetPaths 경유 강제 — 새 kind 가 경로 규약을 우회할 수 없게.
        for rel in ("sage/commands/generate.py", "sage/commands/validate.py"):
            src = open(os.path.join(REPO, rel), encoding="utf-8").read()
            self.assertIsNone(_ASSEMBLY.search(src),
                              f"{rel} 가 mcps 경로를 손조립함 → AssetPaths(root,'mcp',id).spec 사용할 것")


class TestContractVersionStamped(unittest.TestCase):
    def test_generated_mcp_entry_has_contract_version(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t)
            self.assertEqual(G.run(GArgs(t)), 0)
            manifest = json.loads(open(os.path.join(t, "docs", "sage_harness", ".manifest.json")).read())
            mcp_entries = {k: v for k, v in manifest["assets"].items() if k.startswith("mcps/")}
            self.assertTrue(mcp_entries, "생성된 mcps 엔트리가 없음")
            for key, entry in mcp_entries.items():
                self.assertEqual(entry.get("adapter_contract_version"), M.CONTRACT_VERSION,
                                 f"{key} 에 계약버전 스탬프 누락")

    def test_contract_version_mismatch_is_stale(self):
        with tempfile.TemporaryDirectory() as t:
            _inst(t)
            G.run(GArgs(t))
            mp = os.path.join(t, "docs", "sage_harness", ".manifest.json")
            manifest = json.loads(open(mp).read())
            manifest["assets"]["mcps/codegraph"]["adapter_contract_version"] = "999"   # 계약 드리프트 주입
            open(mp, "w").write(json.dumps(manifest))
            self.assertEqual(V.run(VArgs(t)), 3)   # STALE

    def test_legacy_unstamped_contract_is_stale(self):
        # codex R1: spec/render 는 있으나 계약버전이 없는 legacy 엔트리도 재스탬프 강제(STALE).
        # 없으면 죽은 계약버전이 기존 엔트리에서 영원히 살아남는다.
        with tempfile.TemporaryDirectory() as t:
            _inst(t)
            G.run(GArgs(t))
            mp = os.path.join(t, "docs", "sage_harness", ".manifest.json")
            manifest = json.loads(open(mp).read())
            del manifest["assets"]["mcps/codegraph"]["adapter_contract_version"]   # legacy 시뮬레이션
            open(mp, "w").write(json.dumps(manifest))
            self.assertEqual(V.run(VArgs(t)), 3)   # STALE


class TestSchemaSectionsClosed(unittest.TestCase):
    def test_mcp_section_additional_properties_false(self):
        schema = json.loads(open(os.path.join(REPO, "schema", "profile.schema.json"), encoding="utf-8").read())
        props = schema.get("properties") or {}
        # mcp 도 risk/pdca/output_contract 와 동등하게 닫혀 있어야(오타 키 방어 대칭).
        for sec in ("risk", "pdca", "output_contract", "mcp"):
            self.assertIs(props.get(sec, {}).get("additionalProperties"), False,
                          f"schema.{sec} 가 닫혀있지 않음(additionalProperties:false 필요)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
