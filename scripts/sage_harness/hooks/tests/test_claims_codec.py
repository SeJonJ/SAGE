#!/usr/bin/env python3
"""claims.yml 단일 코덱 round-trip (외부검토 P2-7 — YAML 처리 단일화).

핵심: claims_to_yaml(emit) ↔ load_claims_yaml(parse) 가 round-trip 하고, pyyaml 유무와 무관하게
동일 결과를 낸다(claims.yml 은 기계생성 고정 flow-style → 결정론 폴백 파싱 가능). 이전엔 absorb 가
lossy 정규식 파서를, validate 가 pyyaml 을 따로 써서 같은 파일을 두 방식으로 읽었다(3-way 스멜).
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HARNESS)
import reverse_extract_common as rc  # noqa: E402

_CLAIMS = {
    "required_claims": [
        {"type": "owned_paths", "value": "src/foo/**", "confidence": "high"},
        {"type": "convention_doc", "value": "docs/backend.md", "confidence": "source_supported"},
    ],
    "forbidden_claims": [
        {"type": "forbidden", "value": "forbidden:git commit/push", "confidence": "high"},
    ],
    "runtime_delta_allowlist": [
        {"type": "tool_or_skill_ref", "value": "skill:test-runner", "confidence": "runtime_allowed"},
    ],
    "unresolved": ["role_boundary:애매한 경계", "x"],
}


def _write(text):
    fd, p = tempfile.mkstemp(suffix=".claims.yml")
    os.close(fd)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def _vals(d, key):
    return sorted(c["value"] for c in d.get(key, []) if "value" in c)


class TestRoundTrip(unittest.TestCase):
    def test_emit_then_load_preserves_values(self):
        p = _write(rc.claims_to_yaml(_CLAIMS, kind="agent"))
        try:
            d = rc.load_claims_yaml(p)
            self.assertEqual(_vals(d, "required_claims"), ["docs/backend.md", "src/foo/**"])
            self.assertEqual(_vals(d, "forbidden_claims"), ["forbidden:git commit/push"])
            self.assertEqual(_vals(d, "runtime_delta_allowlist"), ["skill:test-runner"])
            self.assertEqual(sorted(d["unresolved"]), ["role_boundary:애매한 경계", "x"])
        finally:
            os.unlink(p)

    def test_special_chars_in_value_roundtrip(self):
        # 따옴표/역슬래시/콤마/중괄호가 든 value 도 깨지지 않고 round-trip 해야 한다(이스케이프).
        tricky = 'weird "quoted", back\\slash, {brace}, 줄바꿈\nและ유니코드 ✓'
        c = {"required_claims": [{"type": "owned_paths", "value": tricky, "confidence": "high"}],
             "forbidden_claims": [], "runtime_delta_allowlist": [], "unresolved": []}
        p = _write(rc.claims_to_yaml(c))
        try:
            with_yaml = rc.load_claims_yaml(p)
            with mock.patch.dict(sys.modules, {"yaml": None}):   # 폴백 파서도 동일하게 복원해야
                fallback = rc.load_claims_yaml(p)
            self.assertEqual(_vals(with_yaml, "required_claims"), [tricky])
            self.assertEqual(_vals(fallback, "required_claims"), [tricky])
        finally:
            os.unlink(p)

    def test_confidence_and_type_preserved(self):
        p = _write(rc.claims_to_yaml(_CLAIMS))
        try:
            d = rc.load_claims_yaml(p)
            req = {c["value"]: c for c in d["required_claims"]}
            self.assertEqual(req["src/foo/**"]["type"], "owned_paths")
            self.assertEqual(req["src/foo/**"]["confidence"], "high")
        finally:
            os.unlink(p)

    def test_fallback_matches_pyyaml(self):
        # pyyaml 차단(import 실패 유도) → 결정론 폴백. pyyaml 경로와 동일 value 집합이어야 통일 성립.
        p = _write(rc.claims_to_yaml(_CLAIMS, kind="skill"))
        try:
            with_yaml = rc.load_claims_yaml(p)
            with mock.patch.dict(sys.modules, {"yaml": None}):   # import yaml → ImportError → 폴백
                fallback = rc.load_claims_yaml(p)
            for key in ("required_claims", "forbidden_claims", "runtime_delta_allowlist"):
                self.assertEqual(_vals(fallback, key), _vals(with_yaml, key), key)
            self.assertEqual(sorted(fallback["unresolved"]), sorted(with_yaml["unresolved"]))
        finally:
            os.unlink(p)

    def test_missing_file_returns_skeleton(self):
        d = rc.load_claims_yaml("/nonexistent/x.claims.yml")
        self.assertEqual(d, {"required_claims": [], "forbidden_claims": [],
                             "runtime_delta_allowlist": [], "unresolved": []})

    def test_empty_section_normalized_to_list(self):
        # pyyaml 은 빈 섹션(`forbidden_claims:`)을 None 으로 파싱 → list 로 정규화해야 소비자(absorb)가 순회 가능.
        p = _write("required_claims:\n"
                   '  - { type: owned_paths, value: "a/**", confidence: high }\n'
                   "forbidden_claims:\n"
                   "runtime_delta_allowlist:\n"
                   "unresolved: []\n")
        try:
            d = rc.load_claims_yaml(p)
            for key in ("required_claims", "forbidden_claims", "runtime_delta_allowlist", "unresolved"):
                self.assertIsInstance(d[key], list, key)
            self.assertEqual(_vals(d, "required_claims"), ["a/**"])
        finally:
            os.unlink(p)

    def test_inherited_forbidden_entry_tolerated(self):
        # claims_to_yaml 은 inherited_forbidden_claims 엔트리(value 없음)도 직렬화 → 로더가 죽지 않아야.
        c = dict(_CLAIMS)
        c["forbidden_claims"] = c["forbidden_claims"] + [{"inherited_forbidden_claims": "base.md"}]
        p = _write(rc.claims_to_yaml(c))
        try:
            d = rc.load_claims_yaml(p)
            self.assertEqual(_vals(d, "forbidden_claims"), ["forbidden:git commit/push"])  # value 있는 것만
            self.assertTrue(any("inherited_forbidden_claims" in e for e in d["forbidden_claims"]))
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
