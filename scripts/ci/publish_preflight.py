#!/usr/bin/env python3
"""publish preflight — 릴리스 직전에 **증거들이 서로 같은 것을 가리키는지** 결정론으로 확인한다.

publish 는 되돌릴 수 없다. PyPI 는 같은 버전을 다시 올릴 수 없고, tag 는 남의 clone 으로 이미
퍼진다. 그래서 이 검사는 "빌드가 되는가"가 아니라 **"이 아티팩트가 주장하는 것과 저장소가
주장하는 것이 같은가"** 를 본다. 둘이 다른 채로 올라가면 사용자는 자기가 뭘 설치했는지 알 수
없고, 그건 되돌릴 수 없는 상태다.

각 검사는 독립이고 전부 돈다 — 첫 실패에서 멈추면 두 번째 문제를 다음 실행에서야 발견하고,
publish 준비가 한 번에 한 개씩만 진행된다.

이 스크립트는 **아무것도 바꾸지 않는다.** version 을 올리거나 tag 를 만들지 않는다. 그건 사용자
결정이고(FR-R05), 검사 도구가 대신 하면 승인 경계가 사라진다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class Finding:
    __slots__ = ("check", "detail")

    def __init__(self, check, detail):
        self.check, self.detail = check, detail

    def __str__(self):
        return f"[{self.check}] {self.detail}"


def _engine_version():
    text = (REPO / "sage" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    return match.group(1) if match else None


def check_tag_matches_version(tag):
    """tag 와 패키지 version 이 같은가. 다르면 사용자가 설치한 것과 tag 가 가리키는 것이 다르다."""
    version = _engine_version()
    if version is None:
        return [Finding("tag-version", "sage/__init__.py 에서 __version__ 을 읽지 못했다")]
    if tag is None:
        return []
    normalized = tag[1:] if tag.startswith("v") else tag
    if normalized != version:
        return [Finding("tag-version", f"tag {tag!r} 와 __version__ {version!r} 가 다르다")]
    return []


def check_catalog_parity():
    """두 catalog 의 key 집합과 placeholder 가 같은가.

    한쪽에만 있는 key 는 런타임 fallback 으로 조용히 넘어간다 — 그 상태로 릴리스하면 사용자가
    빈틈을 대신 발견한다. build 시점에 실패로 바꾸는 것이 이 검사의 목적이다.
    """
    sys.path.insert(0, str(REPO))
    findings = []
    try:
        from sage.i18n import CATALOGS
    except Exception as exc:
        return [Finding("catalog", f"catalog 를 import 하지 못했다: {type(exc).__name__}: {exc}")]

    ko, en = CATALOGS["ko"], CATALOGS["en"]
    for missing in sorted(set(ko) - set(en)):
        findings.append(Finding("catalog", f"en 에 없는 key: {missing}"))
    for extra in sorted(set(en) - set(ko)):
        findings.append(Finding("catalog", f"ko 에 없는 key: {extra}"))
    for key in sorted(set(ko) & set(en)):
        left = set(re.findall(r"\{(\w+)\}", ko[key]))
        right = set(re.findall(r"\{(\w+)\}", en[key]))
        if left != right:
            findings.append(Finding("catalog", f"{key}: placeholder 불일치 {sorted(left ^ right)}"))
    return findings


def check_document_pairs():
    """한국어 사용자 문서마다 영어 짝이 있는가. 한쪽만 갱신된 채 릴리스되면 두 문서가 갈린다."""
    findings = []
    for korean in sorted((REPO / "docs").glob("*.md")) + [REPO / "README.md"]:
        if korean.name.endswith(".en.md") or not korean.is_file():
            continue
        english = korean.parent / (korean.stem + ".en.md")
        if not english.is_file():
            findings.append(Finding("docs-pair", f"영어 짝 없음: {english.relative_to(REPO)}"))
    return findings


def check_inventory_is_current():
    """인벤토리가 코드와 어긋나면 남은 규모가 사실이 아니다 — 릴리스 판단의 근거가 무너진다."""
    generator = REPO / "scripts" / "ci" / "build_localization_inventory.py"
    done = subprocess.run([sys.executable, str(generator), "--root", str(REPO), "--check"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        return [Finding("inventory", "코드와 어긋남 — 재생성이 필요하다")]
    return []


def check_no_release_mutation(before_ref=None):
    """저장소가 릴리스 준비 과정에서 바뀌지 않았는가 (FR-R03).

    후보는 임시 source copy 에서만 만든다. 저장소 자체가 `1.0.0` 으로 stamp 되면 그건 승인 없이
    version 을 올린 것이고, 되돌리기 전까지 모든 후속 판정이 그 값을 사실로 읽는다.
    """
    done = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        return [Finding("mutation", "git status 를 읽지 못했다")]
    dirty = [line for line in done.stdout.splitlines()
             if line and not line.endswith("/") and "??" not in line[:2]]
    if dirty:
        return [Finding("mutation", f"작업 트리에 추적 변경이 있다: {len(dirty)}건")]
    return []


def check_upgrade_evidence():
    """upgrade 계약이 실제로 존재하고 테스트가 실행망에 물려 있는가.

    명령만 있고 실행망에 없으면 회귀가 아무 때나 들어온다 — 그 상태의 릴리스는 계약을 주장할
    근거가 없다. 파일 존재가 아니라 **실행 등록**을 본다.
    """
    findings = []
    if not (REPO / "sage" / "commands" / "upgrade.py").is_file():
        findings.append(Finding("upgrade", "sage/commands/upgrade.py 가 없다"))
    runner = REPO / "scripts" / "sage_harness" / "hooks" / "tests" / "run-all.sh"
    if runner.is_file() and "test_upgrade.py" not in runner.read_text(encoding="utf-8"):
        findings.append(Finding("upgrade", "test_upgrade.py 가 run-all.sh 에 등록되지 않았다"))
    return findings


def check_version_is_not_a_placeholder():
    """`0.0.0` 류의 자리표시자로 publish 하지 않는다."""
    version = _engine_version()
    if version in (None, "", "0.0.0"):
        return [Finding("version", f"자리표시자 version: {version!r}")]
    return []


CHECKS = (
    ("tag-version", lambda tag: check_tag_matches_version(tag)),
    ("version", lambda tag: check_version_is_not_a_placeholder()),
    ("catalog", lambda tag: check_catalog_parity()),
    ("docs-pair", lambda tag: check_document_pairs()),
    ("inventory", lambda tag: check_inventory_is_current()),
    ("upgrade", lambda tag: check_upgrade_evidence()),
    ("mutation", lambda tag: check_no_release_mutation()),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME") or None,
                        help="검증할 release tag (없으면 tag 대조를 생략한다)")
    parser.add_argument("--skip", action="append", default=[],
                        help="이 실행에서 제외할 검사 이름 (사유는 호출부가 남긴다)")
    args = parser.parse_args()

    print("== publish preflight ==")
    print(f"   version: {_engine_version()}   tag: {args.tag or '(없음)'}")

    findings = []
    for name, run in CHECKS:
        if name in args.skip:
            print(f"   SKIP {name} (명시적 제외)")
            continue
        result = run(args.tag)
        findings.extend(result)
        print(f"   {'FAIL' if result else 'OK  '} {name}")

    if findings:
        print("\n차단 사유:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print("\npublish 는 되돌릴 수 없다 — 위 항목을 해소한 뒤 다시 실행하세요.", file=sys.stderr)
        return 1
    print("\n모든 증거가 일치한다. publish 를 진행할 수 있다(사용자 승인은 별개).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
