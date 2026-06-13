"""SAGE 번들 리소스 경로 해석 — repo 레이아웃 + 설치/재배치 시나리오(env override).

install 이 대상 프로젝트로 복사하는 번들 리소스(templates/, schema/, scripts/sage_harness/hooks)의
루트를 단일 지점에서 해석한다(이전엔 install.py 가 repo-relative 경로를 직접 계산 → 재배치/설치 시 취약).

해석 우선순위:
1. 환경변수 $SAGE_RESOURCE_ROOT (설치/배포/재배치 override — 디렉토리면 사용)
2. 레포 루트 (이 파일 기준 ../.. — git clone / editable install / sdist 레이아웃)

배포 모델(정직): 현재는 git clone / `pip install -e .`(editable) / sdist(레포 레이아웃 보존) 기준이며,
어느 경우든 위 해석이 동작한다. 순수 PyPI wheel 단독 배포는 dual-use 인 scripts/sage_harness 를
sage 패키지로 이전(importlib.resources)해야 완전해진다 — 공개 전 과제(README/진행로그 참조).
그때까지 재배치 설치는 $SAGE_RESOURCE_ROOT 로 명시 가능.
"""
import os


def sage_root() -> str:
    env = os.environ.get("SAGE_RESOURCE_ROOT")
    if env and os.path.isdir(env):
        return os.path.abspath(env)
    # sage/_resources.py → 레포 루트 = ../.. (이 파일이 sage/ 바로 아래이므로 dirname 2회)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def templates_dir() -> str:
    return os.path.join(sage_root(), "templates")


def core_dir() -> str:
    return os.path.join(sage_root(), "templates", "core")


def schema_dir() -> str:
    return os.path.join(sage_root(), "schema")


def hooks_src_dir() -> str:
    return os.path.join(sage_root(), "scripts", "sage_harness", "hooks")


def hook_specs_dir() -> str:
    return os.path.join(sage_root(), "docs", "sage_harness", "hooks")
