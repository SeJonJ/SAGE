# 통합 설계와 소유 경계

Cycle-Stem: overlay-issue36-integration
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Status: PLANNED

현재 기준 commit 8e17a88은 양쪽 동일하다. 실제 branch merge 대신 미커밋 변경의 3-way 병합을 한다. current branch·HEAD·index를 유지하고 원본 #36을 수정하지 않는다.

동일7파일 중 실행2(install/upgrade), 번역2, 문서2, 테스트1이다. 제품/번역에서 같은 기존 줄 수정은0이다. test_upgrade 충돌은 빈 base의 양쪽 독립 class 추가를 모두 보존하고, 영문 문서 원문 digest는 병합 후 재계산한다. 새 upgrade_transaction.py와 layout migration 회귀도 포함한다.

검토는 기존 overlay 승인본→통합후보 전체 delta와 변경 함수/의존 경계를 대상으로 한다. 기존 승인본은 역사적 고정 증거다. 현재 source를 과거 승인 hash로 표시하지 않는다. 보수적으로 기존 cycle 완료3/5를 계승해 남은 최대2라운드 안에서 진행한다. 리뷰 신규IO 누적1,511,409/1,800,000을 계승하며 reset/증액하지 않는다. 예산 확보 불가 또는 미해결은 BLOCKED로 남긴다.
