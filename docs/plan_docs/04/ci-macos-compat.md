# CI 인수 검증 근거

Cycle-Stem: ci-macos-compat
Document-Language: ko
Done-Criteria-Revision: 1

## 인수 검증 근거

| ID | 상태 | 근거 |
| --- | --- | --- |
| C01 | PASS | release-readiness 기존61개 메서드의 AST 보존·기존 파일 삭제0, Windows와 나머지 CI job·publish.yml·제거 검사 steps의 baseline semantic/byte 동등성 확인 |
| C02 | PASS | 기본 유효 조합4개에 대한 실패→통과 테스트 |
| C03 | PASS | manual2개와 기본4개가 중복 없이 원래6조합을 복원하고 기존 세 제거 검사/실패 계약 유지 |
| C04 | PASS | YAML의 실제 Bash 검사에 정상1/잘못된입력8, 실제HEAD일치/불일치 실행. readonly 권한/checkout 전후 순서 확인 |
| C05 | PASS | 기존61 baseline·신규6 GREEN, 공식 actionlint 통과. 실제 macOS Python3.10.9/3.11.6의 smoke/race/core 각3명령 exit0. 최종 전체117 suites/4,219건 중4,204통과·skip15·실패0·exit0 |
| C06 | PASS | 한영 release-readiness에 main 반영 후 수동 버튼·동일 후보SHA·자동 게시 gate 미추가를 명시 |

GitHub-hosted 실행과 새 버튼 활성화는 main 반영 전 미실행이며 로컬 성공으로 바꾸지 않는다. actionlint1.7.12는 기존 self-hosted label(win11/sage-uninstall)을 명시한 검사 설정으로 실행했다. 최초 label 미등록 경고도 보존하며 일반 rule-ignore는 사용하지 않았다.

최초 전체 실행은 신규 Bash 테스트 호출2곳의 stdin 상속을 기존 adapter-stdin guard가 적발해 실패했다. 두 호출에 DEVNULL을 명시했으며 기존 guard3건과 신규6건의 독립 재실행을 통과했다. 실패 로그를 보존하고 전체를 다시 실행하여 위 최종 통과를 확인했다. 테스트나 guard를 삭제·완화하지 않았다.

두 실제 Python 검사는 각각11회 실제 제거,14개 필수 경쟁 사례,core103건·skip0을 확인했다. 격리된 테스트 프로젝트에서 실행했으며 실제 사용자 프로젝트나 전역 설치에 적용한 증거가 아니다. 전체 회귀의 skip15는 기존 macOS 실행과 같은 수이고 PASS로 더하지 않았다.
