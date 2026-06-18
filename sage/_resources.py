"""SAGE 번들 리소스 경로 해석 — repo 레이아웃 + 설치/재배치 시나리오(env override).

install 이 대상 프로젝트로 복사하는 번들 리소스(templates/, schema/, scripts/sage_harness/hooks)의
루트를 단일 지점에서 해석한다(이전엔 install.py 가 repo-relative 경로를 직접 계산 → 재배치/설치 시 취약).

해석 우선순위:
1. 환경변수 $SAGE_RESOURCE_ROOT (설치/배포/재배치 override — 디렉토리면 사용)
2. 번들 sage/_bundle/ (순수 wheel — setup.py BundleResources 가 빌드 시 복사. 마커=_bundle/templates)
3. 레포 루트 (이 파일 기준 ../.. — git clone / editable install / sdist 레이아웃)

배포 모델: git clone / `pip install -e .`(editable) 는 레포 fallback(3), 순수 PyPI wheel 은 번들(2)로 동작한다.
wheel 은 빌드 시 install/validate 가 읽는 트리(templates·schema·scripts/sage_harness·docs/sage_harness)를
sage/_bundle/ 로 번들하므로 단독 배포 가능(소스 트리는 불변 — dual-use scripts/sage_harness 이전 회피).
"""
import os


def sage_root() -> str:
    env = os.environ.get("SAGE_RESOURCE_ROOT")
    if env and os.path.isdir(env):
        return os.path.abspath(env)
    here = os.path.dirname(os.path.abspath(__file__))   # .../sage
    bundle = os.path.join(here, "_bundle")              # wheel 번들(setup.py 가 빌드 시 생성)
    if os.path.isdir(os.path.join(bundle, "templates")):
        return bundle
    # repo / editable / sdist: 레포 루트 = ../.. (이 파일이 sage/ 바로 아래이므로 dirname 2회)
    return os.path.dirname(here)


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
