#!/usr/bin/env python3
"""플랫폼 smoke — Linux/macOS/Windows 에서 같은 계약이 성립하는지 확인한다.

**bash 를 쓰지 않는다.** Windows 러너에는 bash 가 없을 수 있고, 설치된 hook 도 Python 진입점으로
돈다. smoke 가 bash 를 요구하면 정작 bash 없는 환경에서 못 도는 것을 검사하지 못한다 — 검사
도구가 검사 대상보다 요구사항이 많으면 그 환경은 영원히 미검증으로 남는다.

여기서 보는 것은 기능의 정확성이 아니라 **환경 의존성**이다. 판정 로직은 hook 회귀 스위트가
이미 본다. 이 스크립트는 "다른 OS·다른 인코딩에서도 같은 통로가 열려 있는가"만 본다.

실패는 항상 어느 검사가 왜 실패했는지와 함께 non-zero 로 끝난다. 조용한 skip 은 통과로 세어져
플랫폼 하나가 미검증인 채 릴리스에 실린다.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _harden_own_output():
    """이 스크립트 자신의 출력 경로를 UTF-8 로 고정한다.

    Windows 러너의 기본 stdout 은 cp1252 라, 검사 7건이 전부 `OK` 를 찍은 **뒤** 마지막 한국어
    요약 줄에서 UnicodeEncodeError 로 죽었다. 검사는 모두 통과했는데 결과 보고가 실패해서
    플랫폼 전체가 빨간불이 되는 상태다.

    `encoding` 검사가 있는데도 이걸 놓친 이유는 그 검사가 **설치본의 출력**만 보기 때문이다 —
    검사 도구 자신의 출력 경로는 아무도 보지 않았다. 여기서 실패하면 실패 원인조차 못 찍으므로
    조용히 넘어가되(except), 정상 경로에서는 인코딩을 먼저 세운다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_harden_own_output()

PROFILE = """project:
  name: "smoke"
  prefix: "smoke"
components:
  - { id: core, paths: ["src/**"] }
risk:
  l0_pass_globs: ["*.md"]
  l2_path_globs: ["src/**"]
  plan_glob: "plan_docs/00-base_plan/**/*.md"
pdca:
  enabled: true
  phases:
    - { id: "00", glob: "plan_docs/00-base_plan/**/*.md" }
"""


class SmokeFailure(RuntimeError):
    pass


def _sage(args, cwd, env=None):
    merged = dict(os.environ, PYTHONPATH=str(REPO))
    merged.update(env or {})
    return subprocess.run([sys.executable, "-m", "sage", *args], cwd=str(cwd), env=merged,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def _require(done, label):
    if done.returncode != 0:
        raise SmokeFailure(f"{label}: exit {done.returncode}\n{done.stdout}\n{done.stderr}")
    return done.stdout + done.stderr


def check_install(root):
    """설치가 이 플랫폼에서 성립하는가. 경로 구분자·권한 모델이 먼저 걸리는 자리다."""
    _require(_sage(["install", "--host", "claude", "--prefix", "smoke", "--dest", str(root)],
                   cwd=REPO), "install")
    marker = root / "docs" / "sage_harness" / ".manifest.json"
    if not marker.is_file():
        raise SmokeFailure(f"install 후 manifest 없음: {marker}")
    return "install"


def check_bilingual_help(root):
    """같은 명령이 두 언어로 나오는가. 어느 하나라도 비면 언어 선택이 화면에서 거짓이다."""
    korean = _require(_sage(["--help"], cwd=root), "help ko")
    english = _require(_sage(["--lang", "en", "--help"], cwd=root), "help en")
    if not korean.strip() or not english.strip():
        raise SmokeFailure("help 출력이 비었다")
    if korean == english:
        raise SmokeFailure("--lang en 이 한국어와 같은 화면을 냈다")
    return "bilingual-help"


def check_local_preference(root):
    """local profile 의 언어 설정이 실제로 화면을 바꾸는가."""
    local = root / "sage" / "project-profile.local.yaml"
    local.parent.mkdir(parents=True, exist_ok=True)
    original = local.read_text(encoding="utf-8") if local.is_file() else None
    try:
        local.write_text("interface:\n  language: en\n", encoding="utf-8")
        english = _require(_sage(["--help"], cwd=root), "help via local preference")
        local.write_text("interface:\n  language: ko\n", encoding="utf-8")
        korean = _require(_sage(["--help"], cwd=root), "help via local preference (ko)")
        if english == korean:
            raise SmokeFailure("local profile 의 language 가 화면을 바꾸지 못했다")
    finally:
        if original is None:
            local.unlink(missing_ok=True)
        else:
            local.write_text(original, encoding="utf-8")
    return "local-preference"


def check_document_language(root):
    """사이클 문서 언어가 이 플랫폼에서도 선언·기록되는가."""
    (root / "sage" / "project-profile.yaml").write_text(PROFILE, encoding="utf-8")
    _require(_sage(["cycle", "set", "smoke-cycle", "--create", "--risk", "L2",
                    "--document-language", "en", "--root", str(root)], cwd=root),
             "cycle set --create")
    declaration = json.loads((root / ".sage" / "cycle.json").read_text(encoding="utf-8"))
    if declaration.get("document_language") != "en":
        raise SmokeFailure(f"선언에 문서 언어가 실리지 않았다: {declaration}")
    phase00 = next((root / "plan_docs").rglob("smoke-cycle.md"), None)
    if phase00 is None:
        raise SmokeFailure("Phase 00 이 생성되지 않았다")
    if "Document-Language: en" not in phase00.read_text(encoding="utf-8"):
        raise SmokeFailure("Phase 00 에 마커가 기록되지 않았다")
    return "document-language"


def check_validate(root):
    """validate 가 이 플랫폼에서 **판정까지 도달하는가**.

    갓 설치한 트리는 `sage generate` 전이라 STALE(3)이 정상이다. 여기서 보는 것은 결과값이
    아니라 도구가 판정을 내렸다는 사실이므로, 문서화된 코드 집합에 드는지만 본다.
    2(도구 오류)와 그 밖의 값은 판정에 도달하지 못한 것이라 실패다.
    """
    done = _sage(["validate", "--check"], cwd=root)
    documented = {0: "PASS/WARN", 1: "FAIL", 3: "STALE"}
    if done.returncode not in documented:
        raise SmokeFailure(
            f"validate 가 판정에 도달하지 못했다 (exit {done.returncode}; "
            f"문서화된 값 {sorted(documented)})\n{done.stdout}\n{done.stderr}")
    return f"validate({documented[done.returncode]})"


def check_native_hook_entry(root):
    """설치된 hook 이 bash 없이 Python 진입점으로 서는가 — Windows 계약의 핵심."""
    done = _sage(["doctor"], cwd=root)
    text = _require(done, "doctor")
    if "sage-hook" not in text:
        raise SmokeFailure("doctor 가 hook 진입점을 보고하지 않았다")
    return "native-hook-entry"


def check_encoding(root):
    """비 UTF-8 로케일에서 한글 출력이 스택트레이스로 터지지 않는가.

    `PYTHONIOENCODING=ascii` 는 실제로 사용자가 만나는 환경이다. 여기서 UnicodeEncodeError 가
    나면 게이트 메시지가 아니라 파이썬 오류가 화면을 채우고, 사용자는 무엇이 막혔는지 못 읽는다.
    """
    done = _sage(["--help"], cwd=root, env={"PYTHONIOENCODING": "ascii"})
    if done.returncode != 0:
        raise SmokeFailure(f"ascii 인코딩에서 help 실패: exit {done.returncode}\n{done.stderr}")
    if "UnicodeEncodeError" in (done.stdout + done.stderr):
        raise SmokeFailure("ascii 인코딩에서 UnicodeEncodeError 노출")
    return "encoding"


CHECKS = (check_install, check_bilingual_help, check_local_preference,
          check_document_language, check_validate, check_native_hook_entry, check_encoding)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="실패 진단용으로 임시 트리를 남긴다")
    args = parser.parse_args()

    workspace = Path(tempfile.mkdtemp(prefix="sage-smoke-"))
    root = workspace / "consumer"
    root.mkdir()
    print(f"== platform smoke == {platform.system()} / python {platform.python_version()}")
    print(f"   workspace: {workspace}")

    passed, failed = [], []
    try:
        for check in CHECKS:
            try:
                passed.append(check(root))
                print(f"   OK   {passed[-1]}")
            except SmokeFailure as exc:
                failed.append((check.__name__, str(exc)))
                print(f"   FAIL {check.__name__}: {exc}", file=sys.stderr)
    finally:
        if not args.keep and not failed:
            shutil.rmtree(workspace, ignore_errors=True)

    print(f"\n통과 {len(passed)} / 실패 {len(failed)}")
    if failed:
        # 조용한 skip 을 만들지 않는다 — 실패한 플랫폼은 미검증이 아니라 실패로 남아야 한다.
        print("실패한 검사는 이 플랫폼이 계약을 만족하지 못한다는 뜻이다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
