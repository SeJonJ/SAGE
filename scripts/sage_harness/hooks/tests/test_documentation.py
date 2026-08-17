#!/usr/bin/env python3
"""Documentation structure, bilingual pairs, and source-hash regression tests."""
import hashlib
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LOCAL_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SOURCE_MARKER = re.compile(
    r"^<!-- sage-doc-source: (?P<source>[^ ]+) sha256:(?P<digest>[0-9a-f]{64}) -->$",
    re.MULTILINE,
)
REFERENCE_PAIRS = (
    ("docs/cli-reference.md", "docs/cli-reference.en.md"),
    ("docs/profile-reference.md", "docs/profile-reference.en.md"),
    ("docs/troubleshooting.md", "docs/troubleshooting.en.md"),
    ("docs/ARTIFACTS.md", "docs/ARTIFACTS.en.md"),
    ("docs/ARCHITECTURE.md", "docs/ARCHITECTURE.en.md"),
)


def _source_digest(path):
    """Hash UTF-8 Markdown with canonical LF line endings across hosts."""
    text = path.read_bytes().decode("utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# hash gate 가 소유하는 전체 짝. `REFERENCE_PAIRS` 만 소유하면 README·quickstart·
# release-readiness mirror 는 한국어만 고쳐도 아무 신호 없이 낡은 채 릴리스된다 — 짝이
# 존재한다는 사실은 동기화됐다는 뜻이 아니다.
MIRRORED_PAIRS = REFERENCE_PAIRS + (
    ("docs/quickstart.md", "docs/quickstart.en.md"),
    ("docs/README.md", "docs/README.en.md"),
    ("docs/release-readiness.md", "docs/release-readiness.en.md"),
    ("README.md", "README.en.md"),
)


def _reference_stale_issues(root, pairs=MIRRORED_PAIRS):
    issues = []
    for korean, english in pairs:
        source = root / korean
        mirror = root / english
        if not source.is_file() or not mirror.is_file():
            continue
        expected = (
            f"<!-- sage-doc-source: {source.name} "
            f"sha256:{_source_digest(source)} -->"
        )
        mirror_text = mirror.read_text(encoding="utf-8")
        first_line = mirror_text.splitlines()[0] if mirror_text else ""
        marker = SOURCE_MARKER.fullmatch(first_line)
        if mirror_text.count("<!-- sage-doc-source:") != 1 or marker is None:
            issues.append(
                f"{english}: expected exactly one source marker on line 1; use {expected}"
            )
            continue
        if (marker.group("source") != source.name
                or marker.group("digest") != _source_digest(source)):
            issues.append(f"{english}: STALE source; replace marker with {expected}")
    return issues


class TestDocumentationStructure(unittest.TestCase):
    def test_bilingual_readme_index_and_quickstart_pairs_exist(self):
        pairs = [
            ("README.md", "README.en.md"),
            ("docs/README.md", "docs/README.en.md"),
            ("docs/quickstart.md", "docs/quickstart.en.md"),
        ]
        for korean, english in pairs:
            with self.subTest(korean=korean, english=english):
                ko_text = (ROOT / korean).read_text(encoding="utf-8")
                en_text = (ROOT / english).read_text(encoding="utf-8")
                self.assertIn(Path(english).name, ko_text)
                self.assertIn(Path(korean).name, en_text)

    def test_root_readmes_stay_focused(self):
        for relative in ("README.md", "README.en.md"):
            with self.subTest(relative=relative):
                lines = (ROOT / relative).read_text(encoding="utf-8").splitlines()
                self.assertLessEqual(len(lines), 200)

    def test_reference_document_pairs_exist_and_are_mutually_linked(self):
        for korean, english in REFERENCE_PAIRS:
            with self.subTest(korean=korean, english=english):
                ko_path = ROOT / korean
                en_path = ROOT / english
                self.assertTrue(ko_path.is_file(), korean)
                self.assertTrue(en_path.is_file(), english)
                ko_text = ko_path.read_text(encoding="utf-8")
                en_text = en_path.read_text(encoding="utf-8")
                self.assertIn(f"]({en_path.name})", ko_text)
                self.assertIn(f"]({ko_path.name})", en_text)

    def test_reference_mirrors_match_normalized_source_hashes(self):
        issues = _reference_stale_issues(ROOT)
        self.assertEqual(issues, [], "\n".join(issues))

    def test_every_bilingual_pair_is_owned_by_the_hash_gate(self):
        """짝이 있는데 gate 밖에 있으면, 그 mirror 는 조용히 낡는다."""
        pairs = {korean for korean, _english in MIRRORED_PAIRS}
        for korean in sorted((ROOT / "docs").glob("*.md")) + [ROOT / "README.md"]:
            if korean.name.endswith(".en.md"):
                continue
            if not (korean.parent / (korean.stem + ".en.md")).is_file():
                continue
            relative = korean.relative_to(ROOT).as_posix()
            with self.subTest(document=relative):
                self.assertIn(relative, pairs)

    def test_the_release_gate_reports_a_stale_mirror(self):
        """하네스만 알고 preflight 가 모르면, 릴리스 시점에는 그 검사가 없는 것과 같다."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "publish_preflight", ROOT / "scripts" / "ci" / "publish_preflight.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        names = [finding.check for finding in module.check_document_pairs()]
        self.assertEqual(names, [], "작업 트리의 mirror 가 이미 낡았다")
        # 실제로 낡은 상태를 잡는지 확인한다 — 짝을 어긋나게 물리면 marker 의 source 가 맞지 않는다.
        issues = module._mirror_stale_issues(ROOT / "docs" / "quickstart.md",
                                             ROOT / "docs" / "cli-reference.en.md")
        self.assertEqual(len(issues), 1, issues)
        self.assertIn("quickstart.md", issues[0])

    def test_source_only_change_reports_target_and_replacement_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            docs.mkdir()
            source = docs / "sample.md"
            mirror = docs / "sample.en.md"
            source.write_bytes(b"# Source\r\n")
            digest = _source_digest(source)
            mirror.write_text(
                f"<!-- sage-doc-source: sample.md sha256:{digest} -->\n"
                "# Mirror\n",
                encoding="utf-8",
            )
            pairs = (("docs/sample.md", "docs/sample.en.md"),)
            self.assertEqual(_reference_stale_issues(root, pairs), [])

            source.write_text("# Source changed\n", encoding="utf-8")
            issues = _reference_stale_issues(root, pairs)
            self.assertEqual(len(issues), 1)
            self.assertIn("docs/sample.en.md: STALE source", issues[0])
            self.assertIn(_source_digest(source), issues[0])

    def test_source_marker_must_be_first_and_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = root / "docs"
            docs.mkdir()
            source = docs / "sample.md"
            mirror = docs / "sample.en.md"
            source.write_text("# Source\n", encoding="utf-8")
            marker = (
                f"<!-- sage-doc-source: sample.md "
                f"sha256:{_source_digest(source)} -->"
            )
            pairs = (("docs/sample.md", "docs/sample.en.md"),)

            mirror.write_text(f"# Mirror\n{marker}\n", encoding="utf-8")
            self.assertEqual(len(_reference_stale_issues(root, pairs)), 1)

            mirror.write_text(
                f"{marker}\n<!-- sage-doc-source: malformed -->\n# Mirror\n",
                encoding="utf-8",
            )
            self.assertEqual(len(_reference_stale_issues(root, pairs)), 1)

    def test_english_indexes_reach_english_reference_documents(self):
        root_index = (ROOT / "README.en.md").read_text(encoding="utf-8")
        docs_index = (ROOT / "docs" / "README.en.md").read_text(encoding="utf-8")
        for _korean, english in REFERENCE_PAIRS:
            relative = Path(english)
            with self.subTest(english=english):
                self.assertIn(f"](docs/{relative.name})", root_index)
                self.assertIn(f"]({relative.name})", docs_index)

    def test_agent_framework_paths_distinguish_source_from_installed_render(self):
        korean = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        english = (ROOT / "docs" / "README.en.md").read_text(encoding="utf-8")
        for text in (korean, english):
            self.assertIn("templates/core/framework/docs/agent/", text)
            self.assertIn("`docs/agent/`", text)

    def test_source_distribution_includes_bilingual_docs(self):
        manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        self.assertIn("include README.md", manifest)
        self.assertIn("include README.en.md", manifest)
        self.assertIn("recursive-include docs ", manifest)

    LANGUAGE_DOCS = ("docs/quickstart.md", "docs/quickstart.en.md",
                     "docs/cli-reference.md", "docs/cli-reference.en.md",
                     "docs/profile-reference.md", "docs/profile-reference.en.md",
                     "docs/troubleshooting.md", "docs/troubleshooting.en.md")

    def test_user_documents_explain_how_to_choose_the_language(self):
        """AC34 — 기능이 있어도 문서에 없으면 사용자는 그것을 발견할 수 없다.
        전역 `--lang` 의 **위치**(하위 명령 앞)와 영구 설정 두 가지가 다 나와야 한다."""
        for relative in self.LANGUAGE_DOCS:
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(document=relative):
                self.assertIn("--lang", text)
                self.assertIn("interface", text)

    def test_the_cli_reference_shows_the_flag_position(self):
        """`sage doctor --lang en` 은 지원 형태가 아니다 — 순서를 틀리면 그대로 실패한다."""
        for relative in ("docs/cli-reference.md", "docs/cli-reference.en.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(document=relative):
                self.assertIn("sage [--lang {ko,en}] <command>", text)

    def test_release_readiness_lists_every_preflight_gate(self):
        """AC34 — 표에서 빠진 검사는 사용자에게 존재하지 않는 검사다. 표를 실제 등록부에
        묶어 두면 게이트가 늘 때 문서가 자동으로 red 가 된다."""
        source = (ROOT / "scripts" / "ci" / "publish_preflight.py").read_text(encoding="utf-8")
        block = source.split("CHECKS = (", 1)[1].split(")\n\n", 1)[0]
        names = re.findall(r'\("([a-z-]+)",', block)
        self.assertIn("localization-debt", names)      # 등록부 자체가 비어버리면 무의미하다
        for relative in ("docs/release-readiness.md", "docs/release-readiness.en.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            for name in names:
                with self.subTest(document=relative, gate=name):
                    self.assertIn(f"| `{name}` |", text)

    def test_release_readiness_names_korean_as_the_authoring_source(self):
        """한국어가 authoring source 이고 영어가 mirror 다. 방향이 뒤집혀 적히면 다음 편집이
        영어부터 시작해 hash marker 가 가리키는 방향과 정반대로 갈린다."""
        korean = (ROOT / "docs" / "release-readiness.md").read_text(encoding="utf-8")
        english = (ROOT / "docs" / "release-readiness.en.md").read_text(encoding="utf-8")
        self.assertNotIn("영어 정본", korean)
        self.assertIn("한국어", korean.split("\n\n")[2])
        self.assertIn("Korean authoring source", english)

    def test_local_markdown_links_resolve(self):
        documents = [
            ROOT / "README.md",
            ROOT / "README.en.md",
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "README.en.md",
            ROOT / "docs" / "quickstart.md",
            ROOT / "docs" / "quickstart.en.md",
        ]
        documents.extend(ROOT / relative for pair in REFERENCE_PAIRS for relative in pair)
        for document in documents:
            if not document.is_file():
                continue
            for target in LOCAL_LINK.findall(document.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                clean = target.split("#", 1)[0]
                with self.subTest(document=document.name, target=target):
                    self.assertTrue((document.parent / clean).resolve().exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
