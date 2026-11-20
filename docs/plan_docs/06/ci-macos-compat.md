# CI macOS 호환성 검사 분리 완료

Cycle-Stem: ci-macos-compat
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Cycle-Status: CLOSED
Source-05: ../05/ci-macos-compat.md

## 완료 판정

2026-11-20 [00](../00/ci-macos-compat.md)의 C01~C06을 모두 충족했고 [04](../04/ci-macos-compat.md)의 검증과 [05](../05/ci-macos-compat.md)의 독립 검토 조건 해소를 근거로 개발 cycle을 종료한다. 사용자 지시대로 EGM 기능·문서의 커밋/푸시와 분리한다. 엔진 자체 승인 gate나 waiver는 사용하지 않았다.

## 변경과 검증

- 일반 PR/main 제거 검사는 Ubuntu Python3.10/3.11/3.12와 macOS3.12의4조합이다.
- macOS3.10/3.11은 별도 수동 workflow에서 같은 후보40자리 SHA에 결속해 기존 smoke/race/core를 실행한다.
- 기존 테스트·나머지 CI job·Windows 승인 조건·publish workflow를 유지한다. 후보 입력은 checkout 전에 검증하고 실제 HEAD를 설치/검사 전에 대조한다.
- 신규 요구 검사6건, stdin guard 보정, 최종 전체117 suites/4,219건 중4,204통과·skip15·실패0·exit0을 확인했다. 실제 로컬 macOS3.10/3.11에서 각3명령도 통과했다.
- 한영 배포 안내와 CHANGELOG를 갱신했다. 구현·테스트·운영 안내6파일은 독립 검토한 hash를 유지한다.

## 통합 인계

CI 브랜치는 EGM 마감 commit0081e58을 기반으로 분리했다. 실제 커밋/푸시 여부는 Git 기록으로 확인한다. main 병합·PR 생성·tag·릴리스·PyPI 게시를 이 문서로 미리 완료 처리하지 않는다.

새 수동 버튼은 workflow가 main에 반영된 뒤 사용할 수 있다. GitHub-hosted 검사는 아직 실행하지 않았으며 로컬 성공으로 대체하지 않았다. 배포 전 일반 CI와 수동2조합의 같은 후보 SHA 성공을 확인하는 운영 절차를 유지한다. 자동 publish gate 신설과 runner 용량 문제 해결을 주장하지 않는다.
