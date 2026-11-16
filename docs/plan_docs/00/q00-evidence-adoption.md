Cycle-Stem: q00-evidence-adoption
Document-Language: ko
Issue: https://github.com/SeJonJ/SAGE/issues/40

# 목표·범위

Q00/Ouroboros의 요구 출처·승인 계약 기반 QA·실행 근거 원칙을 기존 SAGE 흐름에 제한 적용한다. 다른 agent runtime 통합, 새 DB/schema/CLI/gate, 입력 encoding 정책, 자동 repair loop는 포함하지 않는다.

00~06 구조를 사용하되 엔진이 자기 변경을 승인하지 않도록 사용자 결정·일반 테스트·별도 리뷰를 근거로 삼았다. 이 기록은 SAGE 자체 loop audit의 APPROVED가 아니다.

## 완료 기준
- 요구 출처가 인터뷰→Phase01→QA에 유지된다.
- QA 기대값을 현재 오답 구현에서 복제하지 않는다.
- 0개 실행을 PASS라고 표시하지 않으며 기존 exit를 보존한다.
- Standard/Fast/rework 소비처와 기존 acceptance 어휘를 유지한다.
- 양 host의 설치와 개인 runner 보존을 확인한다.
- Windows에서 발견된 지원 경로 구분자 소유권 결함을 수정한다.
- 독립 검토·검증 범위·잔여를 기록한다.
