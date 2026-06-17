#!/usr/bin/env python3
"""sdist 번들 리소스 회귀 가드 (외부검토 P2-10 — 패키징).

`python -m build --sdist` 산출물(dist/*.tar.gz)이 install 이 대상 프로젝트로 복사하는 엔진 리소스
(templates/·schema/·scripts/sage_harness/·docs/sage_harness/)를 실제로 담는지 검증한다. MANIFEST.in
패턴이 조용히 누락되면(예: 디렉토리 리네임 후 갱신 누락) 설치가 런타임에야 깨지는데, 이를 빌드 단계에서 잡는다.

주: 순수 PyPI wheel 단독 배포(scripts/sage_harness 패키지 이전 + importlib.resources)는 별도 추적 과제.
본 가드는 현 지원 배포 경로(sdist / editable / clone + $SAGE_RESOURCE_ROOT)의 리소스 보존을 강제한다.

exit: 0=모든 대표 리소스 존재 / 1=누락(어떤 게 빠졌는지 출력) / 2=sdist 없음.
"""
import glob
import os
import sys
import tarfile

# 각 트리의 "있어야 하는" 대표 파일 술어 — 트리 통째 누락을 잡는 최소 표본.
_CHECKS = {
    "templates 스펙": lambda r: r == "templates/hook.spec.md",
    "templates/core 프레임워크": lambda r: r.endswith("templates/core/framework/AGENT_GUIDE.md"),
    "schema JSON": lambda r: r.startswith("schema/") and r.endswith(".json"),
    "hook core(.py)": lambda r: r.endswith("_core.py") and r.startswith("scripts/sage_harness/hooks/"),
    "hook adapter(.sh)": lambda r: "scripts/sage_harness/hooks/adapters/" in r and r.endswith(".sh"),
    "hook runtime(.py)": lambda r: r.startswith("scripts/sage_harness/hooks/runtime/") and r.endswith(".py"),
    "docs/sage_harness 스펙(.md)": lambda r: r.startswith("docs/sage_harness/") and r.endswith(".md"),
}


def main():
    dist = sys.argv[1] if len(sys.argv) > 1 else "dist"
    tarballs = sorted(glob.glob(os.path.join(dist, "*.tar.gz")))
    if not tarballs:
        print(f"❌ sdist 없음: {dist}/*.tar.gz (먼저 `python -m build --sdist`)", file=sys.stderr)
        return 2
    tb = tarballs[-1]
    with tarfile.open(tb) as t:
        # sdist 최상위는 'sage_harness-<ver>/' 래퍼 — 첫 컴포넌트 제거 후 상대경로 비교.
        rel = sorted(n.split("/", 1)[1] for n in t.getnames() if "/" in n)

    missing = [label for label, pred in _CHECKS.items() if not any(pred(r) for r in rel)]
    print(f"== sdist 리소스 검증: {os.path.basename(tb)} ({len(rel)} files) ==")
    for label in _CHECKS:
        print(f"  {'❌' if label in missing else '✅'} {label}")
    if missing:
        print(f"❌ 번들 누락 {len(missing)}건 — MANIFEST.in 확인 필요: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("✅ 모든 대표 엔진 리소스가 sdist 에 포함됨")
    return 0


if __name__ == "__main__":
    sys.exit(main())
