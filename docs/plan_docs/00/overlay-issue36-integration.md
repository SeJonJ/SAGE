# Overlay와 #36 통합 계획

Cycle-Stem: overlay-issue36-integration
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Status: BLOCKED_REVIEW_BUDGET

## 사용자 결정과 범위

2026-11-07 사용자가 #36 변경을 현재 fix/overlay-context-delivery에 통합하고 하나의 PR/릴리즈 후보로 검증하는 진행을 승인했다. 통합 전 include-untracked stash를 만들고 복구를 준비한다. 원본 #36 worktree와 기존 overlay 00~06/승인 증거는 보존한다. git commit은 별도 명시 승인 전 실행하지 않는다. 실제 main merge/release는 최종 후보 CI·리뷰 및 커밋 승인 후 진행한다.

SAGE 개발 절차를 외부에서 사용하며 개발 중인 엔진 gate/review-loop로 스스로 승인하지 않는다. 제품 CLI 검증은 격리 consumer에서만 실행한다. 기존 기능 설계 확대 없이 #36의 migration deferral/global rollback과 overlay의 dual-local staging/context delivery를 결합한다. 코드 충돌이 아닌 결합 반례가 확인되면 기존 계약 내 최소 수리를 한다.

## 5. Done Criteria

- [x] I1: 현재 변경 전체 stash 및 파일별 해시·mode 복원 검증, #36 원본 보존과 안전한 rollback 경로 기록.
- [x] I2: #36 전체 변경과 overlay 기존 변경 보존, 양쪽 테스트·문서 병합 및 원문 해시 정합.
- [x] I3: 구 레이아웃+project hook+공유/개인 overlay에서 Claude/Codex 두 local host 업그레이드, hook 유지, 표준/Fast 전달, 재적용 확인.
- [x] I4: global 및 dual-local 갱신 후반 실패 시 기존 사용자/overlay/global 복구 회귀 유지.
- [x] I5: 통합 전체 회귀와 fresh installed wheel consumer·패키징 검증, 미실행 OS/원격 CI 구분.
- [ ] I6: 정확한 통합 delta와 변경 함수·연결 경계에 독립 L3 검토, 미해결 finding 없음.

## 6. Done Criteria Revision Log

Revision1 — 기존 두 후보를 합친 새 통합 후보의 추가 수용 기준이다. 기존 overlay A1~A8/원본 승인 hash를 수정하거나 새 후보 승인으로 재사용하지 않는다. #36 원격 CI 대기는 실제 최종 후보 CI 전 해소됐다고 표시하지 않는다.

## 현재 중단 상태

코드통합·I1~I5로컬검증완료. I6은Claude유효결과와반박미완료, 누적신규IO1,953,432/1,800,000 초과로BLOCKED. 원장·오류원문을05에보존하고추가모델호출·06·릴리즈를하지않는다. 원래기준을줄이거나면제하지않았다.
