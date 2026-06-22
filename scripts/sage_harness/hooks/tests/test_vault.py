#!/usr/bin/env python3
"""S5 Obsidian 옵션 단위 — _vault 헬퍼 + review-loop show --vault 대시보드 + retro --vault human-gate.

마스터 게이트 = knowledge_capture.vault_path (비면 vault 출력 전부 OFF). 스키마 키 추가 없음.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, REPO)
from sage.commands import _vault  # noqa: E402


class TestVaultHelper(unittest.TestCase):
    def test_target_disabled_when_no_vault_path(self):
        self.assertEqual(_vault.vault_target({}), (None, None))
        self.assertEqual(_vault.vault_target({"knowledge_capture": {"vault_path": ""}}), (None, None))

    def test_target_from_profile(self):
        prof = {"knowledge_capture": {"vault_path": "/v", "note_convention": {"folder": "notes"}}}
        self.assertEqual(_vault.vault_target(prof), ("/v", "notes"))

    def test_target_default_folder_wiki(self):
        self.assertEqual(_vault.vault_target({"knowledge_capture": {"vault_path": "/v"}}), ("/v", "wiki"))

    def test_override_beats_profile(self):
        prof = {"knowledge_capture": {"vault_path": "/profile"}}
        self.assertEqual(_vault.vault_target(prof, override="/cli")[0], "/cli")

    def test_fm_value_types(self):
        self.assertEqual(_vault._fm_value(False), "false")
        self.assertEqual(_vault._fm_value(True), "true")
        self.assertEqual(_vault._fm_value(3), "3")
        self.assertEqual(_vault._fm_value(["a", "b"]), '["a", "b"]')   # 요소 quote(일반 YAML-safe)
        self.assertEqual(_vault._fm_value("x"), '"x"')

    def test_write_note(self):
        tmp = tempfile.mkdtemp()
        path = _vault.write_note(tmp, "wiki", "n.md", {"approved": False, "tags": ["sage"]}, "body here")
        self.assertTrue(path.endswith(os.path.join("wiki", "n.md")))
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("approved: false", txt)
        self.assertIn('tags: ["sage"]', txt)
        self.assertTrue(txt.rstrip().endswith("body here"))

    def test_safe_rel_folder_escape(self):
        # codex S5 P1: 절대경로/.. 폴더는 vault 안 상대경로로 정규화.
        self.assertEqual(_vault._safe_rel("../../outside"), "outside")
        self.assertEqual(_vault._safe_rel("/tmp/evil"), os.path.join("tmp", "evil"))
        self.assertEqual(_vault._safe_rel(""), "wiki")
        self.assertEqual(_vault._safe_rel("../.."), "wiki")

    def test_write_note_folder_containment(self):
        # 악성 folder(절대경로)라도 vault 밖으로 나가지 않음(컨테인먼트 방어선).
        tmp = tempfile.mkdtemp()
        outside = tempfile.mkdtemp()
        # vault_target 가 정규화하지만, write_note 에 직접 escape folder 를 줘도 갇혀야 함.
        path = _vault.write_note(tmp, os.path.join("..", os.path.basename(outside)), "n.md", {}, "x")
        self.assertTrue(os.path.realpath(path).startswith(os.path.realpath(tmp)))

    def test_write_note_leaf_symlink_not_followed(self):
        # codex S5: leaf 파일이 외부를 가리키는 심링크여도 그 target 에 쓰지 않는다(링크만 제거 후 실제 파일).
        vault = tempfile.mkdtemp()
        outside = tempfile.mkdtemp()
        target = os.path.join(outside, "secret.txt")
        with open(target, "w", encoding="utf-8") as f:
            f.write("ORIGINAL")
        os.makedirs(os.path.join(vault, "wiki"), exist_ok=True)
        leaf = os.path.join(vault, "wiki", "n.md")
        try:
            os.symlink(target, leaf)
        except (OSError, NotImplementedError):
            self.skipTest("symlink 미지원 환경")
        _vault.write_note(vault, "wiki", "n.md", {}, "new content")
        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), "ORIGINAL")   # 외부 target 불변
        self.assertFalse(os.path.islink(leaf))        # 심링크는 실제 파일로 대체됨

    def test_write_note_key_injection_neutralized(self):
        import yaml
        tmp = tempfile.mkdtemp()
        # 악성 키(개행/콜론 주입 시도) → 안전 식별자로 정규화, frontmatter 구조 안 깨짐.
        path = _vault.write_note(tmp, "wiki", "n.md",
                                 {"ok": 1, "ev\nil: injected": 2}, "body")
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        fm = txt.split("---")[1]
        parsed = yaml.safe_load(fm)   # 깨지지 않고 파싱돼야
        self.assertIn("ok", parsed)
        self.assertNotIn("injected", str(parsed.get("ok")))   # 값 오염 없음

    def test_write_note_symlink_escape_contained(self):
        # codex S5: realpath containment — vault 안 심링크가 밖을 가리켜도 write 가 vault 밖으로 안 나감.
        vault = tempfile.mkdtemp()
        outside = tempfile.mkdtemp()
        link = os.path.join(vault, "esc")
        try:
            os.symlink(outside, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlink 미지원 환경")
        path = _vault.write_note(vault, "esc", "n.md", {}, "x")
        # realpath 기준 vault 밖이면 vault 루트로 폴백 → outside 에 안 씀
        self.assertFalse(os.path.exists(os.path.join(outside, "n.md")))
        self.assertTrue(os.path.realpath(path).startswith(os.path.realpath(vault)))

    def test_write_note_filename_basename_only(self):
        tmp = tempfile.mkdtemp()
        path = _vault.write_note(tmp, "wiki", "../../evil.md", {}, "x")
        self.assertEqual(os.path.basename(path), "evil.md")
        self.assertTrue(os.path.realpath(path).startswith(os.path.realpath(os.path.join(tmp, "wiki"))))

    def test_write_note_create_only_preserves(self):
        tmp = tempfile.mkdtemp()
        p1 = _vault.write_note(tmp, "wiki", "n.md", {"approved": True}, "human edited")
        p2 = _vault.write_note(tmp, "wiki", "n.md", {"approved": False}, "regenerated", create_only=True)
        self.assertIsNone(p2)   # 기존 보존, 덮지 않음
        with open(p1, encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("approved: true", txt)        # 사람 상태 보존
        self.assertIn("human edited", txt)

    def test_fm_value_list_yaml_safe(self):
        # 일반 YAML-safe: ]·,·:·# 포함 요소도 frontmatter 가 정확히 round-trip(codex S5 P3).
        import yaml
        for val in (["a]b", "c,d", "k: v", "#x", "normal"], ["sage", "retro"], []):
            rendered = "x: " + _vault._fm_value(val)
            self.assertEqual(yaml.safe_load(rendered)["x"], val)

    def test_fm_value_scalar_yaml_safe(self):
        import yaml
        for val in ("plain", "has: colon", "#hash", 'q"uote', "line\nbreak"):
            parsed = yaml.safe_load("x: " + _vault._fm_value(val))["x"]
            # 개행은 공백으로 평탄화되므로 그 경우만 예외 처리, 나머지는 정확 일치.
            self.assertEqual(parsed, val.replace("\n", " "))


def _profile(tmp, vault):
    os.makedirs(os.path.join(tmp, "sage"), exist_ok=True)
    with open(os.path.join(tmp, "sage", "project-profile.yaml"), "w", encoding="utf-8") as f:
        f.write("pdca:\n  approve_phase: \"05\"\n  phases:\n"
                "    - { id: \"05\", glob: \"plan_docs/05-expert-review/**/*.md\" }\n"
                "  review_loop: { enabled: true, lenses: [security], refuters: 2 }\n")
        if vault:
            f.write(f"knowledge_capture:\n  vault_path: \"{vault}\"\n  note_convention: {{ folder: wiki }}\n")


def _sage(*args, root):
    return subprocess.run([sys.executable, "-m", "sage", *args, "--root", root],
                          cwd=REPO, capture_output=True, text=True)


def _run_loop(tmp):
    r = _sage("review-loop", "open", "--risk", "L3", root=tmp)
    rid = r.stdout.strip().splitlines()[0]
    _sage("review-loop", "round", "--run-id", rid, "--iteration", "1", "--found", "7",
          "--survived", "3", "--accepted", "3", "--tokens", "48000", root=tmp)
    _sage("review-loop", "close", "--run-id", rid, "--result", "APPROVED", "--reason", "DRY",
          "--iterations", "1", root=tmp)
    return rid


class TestVaultDashboard(unittest.TestCase):
    def test_show_vault_writes_dashboard(self):
        tmp, vault = tempfile.mkdtemp(), tempfile.mkdtemp()
        _profile(tmp, vault)
        rid = _run_loop(tmp)
        r = _sage("review-loop", "show", "--vault", root=tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        dash = os.path.join(vault, "wiki", "SAGE-loop-audit.md")
        self.assertTrue(os.path.exists(dash))
        with open(dash, encoding="utf-8") as f:
            txt = f.read()
        self.assertIn(rid, txt)
        self.assertIn("| run_id |", txt)        # plain 테이블(플러그인 무관)
        self.assertIn("APPROVED/DRY", txt)

    def test_show_vault_disabled_graceful(self):
        tmp = tempfile.mkdtemp()
        _profile(tmp, None)   # vault_path 없음
        _run_loop(tmp)
        r = _sage("review-loop", "show", "--vault", root=tmp)
        self.assertEqual(r.returncode, 0)
        self.assertIn("vault 비활성", r.stderr)

    def test_show_vault_override_path(self):
        tmp, vault = tempfile.mkdtemp(), tempfile.mkdtemp()
        _profile(tmp, None)   # profile 엔 vault 없음, --vault 로 오버라이드
        _run_loop(tmp)
        r = _sage("review-loop", "show", "--vault", vault, root=tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(os.path.exists(os.path.join(vault, "wiki", "SAGE-loop-audit.md")))


class TestVaultRetro(unittest.TestCase):
    def _add_05(self, tmp, stem="loop-engineering"):
        d = os.path.join(tmp, "plan_docs", "05-expert-review")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{stem}-review.md"), "w", encoding="utf-8") as f:
            f.write("## Phase-05 Review\n")

    def test_retro_vault_human_gate_note(self):
        tmp, vault = tempfile.mkdtemp(), tempfile.mkdtemp()
        _profile(tmp, vault)
        rid = _run_loop(tmp)
        self._add_05(tmp)
        r = _sage("retro", "--feature", "loop-engineering", "--vault", root=tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        notes = [f for f in os.listdir(os.path.join(vault, "wiki")) if f.startswith("sage-retro-")]
        self.assertEqual(len(notes), 1)
        with open(os.path.join(vault, "wiki", notes[0]), encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("approved: false", txt)        # human gate
        self.assertIn("pending-review", txt)
        self.assertIn(rid, txt)
        self.assertIn("distiller", txt)              # 증거+프롬프트 포함

    def test_retro_vault_disabled_graceful(self):
        tmp = tempfile.mkdtemp()
        _profile(tmp, None)
        _run_loop(tmp)
        self._add_05(tmp)
        r = _sage("retro", "--vault", root=tmp)
        self.assertEqual(r.returncode, 0)
        self.assertIn("vault 비활성", r.stderr)

    def test_retro_vault_rerun_preserves_human_state(self):
        # codex S5 P2: 같은 날 재실행이 사람이 approved:true 로 바꾼 노트를 덮지 않는다.
        tmp, vault = tempfile.mkdtemp(), tempfile.mkdtemp()
        _profile(tmp, vault)
        self._run_loop_local(tmp)
        self._add_05(tmp)
        _sage("retro", "--feature", "loop-engineering", "--vault", root=tmp)
        note = os.path.join(vault, "wiki",
                            [f for f in os.listdir(os.path.join(vault, "wiki")) if f.startswith("sage-retro-")][0])
        # 사람이 승인 표시
        with open(note, encoding="utf-8") as f:
            txt = f.read().replace("approved: false", "approved: true")
        with open(note, "w", encoding="utf-8") as f:
            f.write(txt + "\n사람 메모\n")
        # 재실행 → 보존
        r = _sage("retro", "--feature", "loop-engineering", "--vault", root=tmp)
        self.assertIn("보존", r.stderr)
        with open(note, encoding="utf-8") as f:
            txt2 = f.read()
        self.assertIn("approved: true", txt2)
        self.assertIn("사람 메모", txt2)

    def _run_loop_local(self, tmp):
        return _run_loop(tmp)

    def test_retro_vault_feature_path_traversal_sanitized(self):
        # --feature 가 파일명 stem 이 되므로 경로 탈출 방지: 노트는 vault/wiki 안에만, 밖으로 안 샘.
        tmp, vault = tempfile.mkdtemp(), tempfile.mkdtemp()
        _profile(tmp, vault)
        _run_loop(tmp)
        self._add_05(tmp)
        _sage("retro", "--feature", "../../etc/evil", "--vault", root=tmp)
        # vault/wiki 안에 sage-retro-*.md 생성, vault 밖(상위)엔 evil 파일 없음
        wiki = os.path.join(vault, "wiki")
        notes = [f for f in os.listdir(wiki) if f.startswith("sage-retro-")] if os.path.isdir(wiki) else []
        self.assertTrue(notes and all("/" not in n and ".." not in n for n in notes))
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(vault), "etc", "evil")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
