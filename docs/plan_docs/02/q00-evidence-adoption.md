Cycle-Stem: q00-evidence-adoption
Document-Language: ko
Issue: https://github.com/SeJonJ/SAGE/issues/40

# 설계

- 인터뷰/01/QA는 기존 본문·셀의 출처와 승인 계약을 연결한다. 새 데이터 구조를 추가하지 않는다.
- bundled runner는 명령 선택/순서와 실패 뒤 후속 실행을 유지하고 실행/생략 목록·개수를 출력한다.
- 0개 실행·profile 부재는 NO_EVIDENCE, 실제 실패는 FAIL. 성공/skip exit0, 실패1, 기존 profile에서 invalid level2를 유지한다.
- 필수 근거가 없는 ID는 기존 NOT TESTED, 원문 NO_EVIDENCE/UNKNOWN은 evidence/notes에 둔다.
- NO_EVIDENCE 단독은 명령 실패·자동 rework retry 이유·required PASS가 아니다. 기존 승인/waiver를 유지한다.
- Windows 설치 소유권은 current/legacy 경로의 정확한 native/portable 표기만 인정한다. 임의 path 정규화나 삭제 허용 목록 확대는 하지 않는다.
