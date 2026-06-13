"""서브커맨드 공통 헬퍼."""

import sys

# stub(미구현) 명령만 not_implemented 가 참조. validate/review/change/doctor 는 구현됨(여기 미포함).
STEP = {
    "install": "부트스트랩(host 택1 + 빈 스키마 배치) — v1 stub",
    "generate": "spec → 산출물 렌더. agent/skill render 는 interpretive(런타임 AI) — v1 stub",
    "absorb": "직접수정 diff → spec patch 제안 (§5 M3) — v1 stub",
}


def not_implemented(command: str, detail: str = "") -> int:
    """아직 로직이 없는 명령을 정직하게 알린다 (조용한 실패 금지)."""
    print(f"[sage {command}] 스캐폴드 단계 — 아직 미구현입니다.", file=sys.stderr)
    print(f"  진행 단계: {STEP.get(command, 'N/A')}", file=sys.stderr)
    if detail:
        print(f"  예정 동작: {detail}", file=sys.stderr)
    return 2
