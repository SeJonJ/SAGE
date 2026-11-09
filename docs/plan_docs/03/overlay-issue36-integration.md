# 통합 구현 기록

Cycle-Stem: overlay-issue36-integration
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Status: VERIFIED_LOCAL

## 소유·체크리스트

root가 #36 변경10경로와 통합 회귀·문서만 소유하며 별도 범위 확대를 하지 않는다. Codex 실행은 순차로 수행한다. #36 원본 worktree는 읽기 전용으로 보존한다.

- [x] 통합 전 stash push -u / bytes·mode / apply 후 일치 확인
- [x] 공통 파일 3-way 병합, 양쪽 test class 보존
- [x] legacy dual-host overlay 통합 수용·실패 복구 회귀
- [x] 전체 회귀 및 clean consumer

증거 디렉터리: /Users/sejon/project/sage_project_worktree/overlay-issue36-integration-20261107
stash: bcb1711da4a7d386d14220bf3ce3c13f24353354
고정 ref: refs/sage-backups/overlay-before-issue36-20261107

## 통합 검증 결과

제품 추가수리는 필요하지 않았다. #36 전체 변경을 유지하고 기존 overlay와 병합했으며 통합 회귀3개를 추가했다. 양쪽 기존 테스트 AST가 보존됐다. 전체 회귀 Ran 합계4149항목(13 skip포함), 실패·오류0/exit0. fresh wheel 및217logical source 동등, 실제v1.0 installer→설치wheel3조합/양hook/strictvalidate/reapply/global후반실패복구 PASS. 최종sdist build+리소스검사 PASS.

원본 실패는 보존했다. 최초 unittest 실행은 runner의 PYTHONPATH 조건 누락으로 validator_unavailable이었고 같은 환경을 맞춘89upgrade/53layout은PASS. 새fixture의 primary선정 전제와 모든 파일mtime 불변이라는 과도한 단언을 바로잡은 통합3개는PASS. rollback은 전체 bytes/mode, overlay원문mtime를 검증하며 임의managed파일mtime불변을 주장하지 않는다. 실제v1.0의 첫 harness는 --id 누락으로 hook미등록이었으며 원본을 남기고 올바른 등록v2를 별도 실행했다.
