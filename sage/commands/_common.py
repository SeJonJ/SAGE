"""서브커맨드 공통 헬퍼."""

import sys

# v1 구현 순서 (최종검증 §5) — stub이 어느 단계인지 표시
STEP = {
    "install": "10단계 외 (부트스트랩) — 미구현",
    "generate": "§5-3~7 (write guard 후) — 미구현",
    "validate": "§5-2/5 (manifest staleness) — 일부 구현 예정",
    "absorb": "§5 M3 (직접수정 흡수) — 미구현",
    "doctor": "§5 옵션 의존성 — 미구현",
    "change": "§5-9 (v1.1 라우터) — 미구현",
}


def not_implemented(command: str, detail: str = "") -> int:
    """아직 로직이 없는 명령을 정직하게 알린다 (조용한 실패 금지)."""
    print(f"[sage {command}] 스캐폴드 단계 — 아직 미구현입니다.", file=sys.stderr)
    print(f"  진행 단계: {STEP.get(command, 'N/A')}", file=sys.stderr)
    if detail:
        print(f"  예정 동작: {detail}", file=sys.stderr)
    return 2
