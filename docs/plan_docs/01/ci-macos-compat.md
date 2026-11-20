# CI 실행 요구사항

Cycle-Stem: ci-macos-compat
Document-Language: ko
Done-Criteria-Revision: 1

## 인수 기준

| ID | 요구 |
| --- | --- |
| C01 | 기존 테스트 파일을 삭제하지 않고 test/platform/packaging/release_evidence 및 Windows job의 실행·승인 계약 유지 |
| C02 | 일반 제거 검증의 유효 조합은 Ubuntu3.10/3.11/3.12와 macOS3.12, 정확히4개 |
| C03 | 별도 workflow_dispatch에서 macOS3.10/3.11의2개만 실행; smoke/race/core 검사와 실패 동작 유지 |
| C04 | 입력은40자리 소문자 commit SHA; 잘못된 입력은 checkout 전 거부; 테스트 전 HEAD==입력 검증; contents:read, publish 권한/단계 없음 |
| C05 | 실제 검증 스크립트가 잘못된 SHA·다른 HEAD를 거부하고 두 Python에서 제거·race·core가 동작; 전체 회귀·YAML 검사 통과 |
| C06 | main 반영 후 수동 버튼 사용, 검사 SHA와 배포 SHA의 일치 및 기존 publish가 이 결과를 자동 강제하지 않는 운영 절차 안내 |
