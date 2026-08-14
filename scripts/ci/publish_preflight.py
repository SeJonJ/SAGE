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
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
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
    """인벤토리는 최신이어야 하고 미이관 사용자 표시 literal은 0건이어야 한다."""
    generator = REPO / "scripts" / "ci" / "build_localization_inventory.py"
    done = subprocess.run([sys.executable, str(generator), "--root", str(REPO), "--check"],
                          capture_output=True, text=True)
    if done.returncode != 0:
        return [Finding("inventory", "코드와 어긋남 — 재생성이 필요하다")]
    try:
        document = json.loads(
            (REPO / "docs" / "sage_harness" / "localization-inventory.json").read_text(
                encoding="utf-8"))
        entries = document.get("entries") if isinstance(document, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [Finding("inventory", f"인벤토리를 읽지 못했다: {type(exc).__name__}")]
    return _inventory_completion_findings(entries)


def _inventory_completion_findings(entries):
    """최신성과 독립된 완료 조건. 합성 결손으로 gate의 실패 동작을 검증할 수 있게 분리한다."""
    if not isinstance(entries, list):
        return [Finding("inventory", "entries가 리스트가 아니다")]
    pending = [item for item in entries
               if not isinstance(item, dict) or not isinstance(item.get("key"), str)
               or not item["key"].strip()]
    if pending:
        hook_reachable = sum(
            1 for item in pending if isinstance(item, dict) and item.get("hook_reachable") is True)
        return [Finding(
            "inventory",
            f"catalog 미이관 사용자 표시 literal {len(pending)}건"
            f" (hook-reachable {hook_reachable}건) — 영어 출력 완료 전 publish 차단",
        )]
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
    """upgrade 계약이 실행망에 있고 실제 지원 하한에서 managed 자산까지 이행하는가.

    명령과 단위 테스트 이름만 있으면 scalar 두 개만 바꾸는 구현도 완료로 오인할 수 있다. 실제
    v0.9.84 소비자 형태를 임시 디렉터리에 만들고 현재 source의 신규 managed policy와 receipt가
    함께 배포되는지 확인한다. 저장소는 읽기만 하고 임시 소비자만 변경한다.
    """
    findings = []
    if not (REPO / "sage" / "commands" / "upgrade.py").is_file():
        findings.append(Finding("upgrade", "sage/commands/upgrade.py 가 없다"))
    runner = REPO / "scripts" / "sage_harness" / "hooks" / "tests" / "run-all.sh"
    if runner.is_file() and "test_upgrade.py" not in runner.read_text(encoding="utf-8"):
        findings.append(Finding("upgrade", "test_upgrade.py 가 run-all.sh 에 등록되지 않았다"))
    if findings:
        return findings

    profile = subprocess.run(
        ["git", "-C", str(REPO), "show", "v0.9.84:templates/project-profile.yaml"],
        capture_output=True, text=True,
    )
    manifest = subprocess.run(
        ["git", "-C", str(REPO), "show", "v0.9.84:docs/sage_harness/.manifest.json"],
        capture_output=True, text=True,
    )
    if profile.returncode != 0 or manifest.returncode != 0:
        return [Finding("upgrade", "지원 하한 v0.9.84 실제 fixture를 읽지 못했다")]

    with tempfile.TemporaryDirectory(prefix="sage-upgrade-preflight-") as temporary:
        root = Path(temporary)
        (root / "sage").mkdir()
        (root / "docs" / "sage_harness").mkdir(parents=True)
        # v0.9.84 **소비자**는 `/sage-init` 를 마친 상태다. 템플릿 원본은 부트스트랩 이전이라
        # 그대로 쓰면 CORE 배포 경로를 아예 타지 않고, 검사가 실제 upgrade 를 못 본다.
        (root / "sage" / "project-profile.yaml").write_text(
            profile.stdout
            + '\nproject:\n  name: "preflight-consumer"\n  prefix: "preflight"\n'
              'components:\n  - { id: core, paths: ["src/**"] }\n'
              'risk:\n  l2_path_globs: ["src/**"]\n',
            encoding="utf-8")
        (root / "docs" / "sage_harness" / ".manifest.json").write_text(
            manifest.stdout, encoding="utf-8")
        try:
            from sage.commands import upgrade
            args = SimpleNamespace(check=False, apply=True, root=str(root), force=True)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = upgrade.run(args)
        except Exception as exc:
            return [Finding("upgrade", f"v0.9.84 fixture 적용 중 예외: {type(exc).__name__}")]

        policy = root / "docs" / "agent" / "language-policy.md"
        try:
            upgraded_manifest = json.loads(
                (root / "docs" / "sage_harness" / ".manifest.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            upgraded_manifest = {}
        receipt = ((upgraded_manifest.get("core_renders") or {}).get(
            "shared/framework-doc/docs/agent/language-policy")
            if isinstance(upgraded_manifest, dict) else None)
        findings.extend(_managed_upgrade_findings(result, policy.is_file(), receipt))
    return findings


def _managed_upgrade_findings(result, policy_exists, receipt):
    """지원 하한 apply의 최소 managed 자산 계약을 현재 구현 상태와 독립해 검증한다."""
    if result == 0 and policy_exists and isinstance(receipt, dict):
        return []
    return [Finding(
        "upgrade",
        "v0.9.84 적용 후 managed language-policy 파일과 receipt가 함께 배포되지 않았다",
    )]


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
