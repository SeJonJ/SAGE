# 통합 후보 Windows·Mac 플랫폼 검증

실행일: 2026-11-07 KST. 문서 정리일: 2026-11-09.
제품 hash: `205ba39f9b2f587573fb44c31f313a2f3c7975a2dabc1e2d6b9941785282ae70`.
제품 파일 217개는 소스·설치본에서 일치했으며 플랫폼 검증 중 제품 코드는 수정하지 않았습니다.
이후 PR 문서 정리는 실행 제품 변경과 구분합니다.

## 실행 결과

| 대상 | 관찰 | 판정의 한계 |
|---|---|---|
| Windows 11 Pro x64·로컬 NTFS, Python 3.12 | 등록된 Python 명령 114개, unittest Ran 합계 4,149, skip 61. 스크립트 94개 exit 0, 20개 nonzero | 전체 PASS 아님. Bash runner 자체나 원격 CI를 실행한 결과가 아님 |
| Windows Python 3.10·3.11 | 각각 핵심 8개 묶음, Ran 합계 333, skip 3 | 원본 materialize 경로 assertion 실패 보존. 3.11 layout의 준비 단계 오류는 아래 별도 기록 |
| Windows 설치 wheel | 세 Python 버전 각각 smoke 10/10 및 실제 v1.0.0 소비자 3조합 PASS | 최종 wheel도 별도 3.12 venv에서 smoke 10/10, 구버전 3조합 재확인 |
| Mac Python 3.11.6 | 114개 스크립트, Ran 합계 4,150, PASS 4,135, skip 15, 실패·오류 0, exit 0 | 원래 skip 13개 외 Windows 전용 사례 1개, venv user-site 비활성 사례 1개 포함 |
| Mac 보충·설치 wheel | user-site 사례를 global Python에서 별도 1건 실행해 PASS. 설치 smoke 10/10, 실제 v1.0.0 소비자 3조합 PASS | 전체 원본의 skip 15개 수치를 덮어쓰지 않음 |

구버전 소비자 3조합은 Claude primary+Codex project-local, Codex project-local primary+Claude,
Codex global primary+Claude입니다. 사용자 hook·공유/개인 원문 보존, 표준 2개/Fast 4개 출처,
양 host의 설치된 `hook_entry`, 재적용, global 후반 실패 시 프로젝트·전역 복구를 확인했습니다.
실제 Claude/Codex 앱에서 새 모델 대화를 실행한 결과로 해석하지 않습니다.

## 원본 Windows 실패와 테스트 수정

3.12 원본의 실패 이벤트 112건 중 104건은 기존 `8e17a88` 소스에서 38개 대조 명령으로 재현됐습니다.
나머지 8건은 신규 테스트의 Windows 가정이 잘못된 것으로 확인해 다음 세 파일만 고쳤습니다.

- `test_gate_followups.py`: 정상 해석되는 8.3 별칭과 의도적으로 해석을 실패시킨 별칭을 구분합니다.
- `test_install.py`: 진단 경로의 native 구분자를 비교합니다.
- `test_overlay_materialize.py`: 경로 목록을 문자열 대신 `Path` 의미로 비교합니다.

해당 사례는 세 Python 버전에서 재검증했습니다. 전체 R2와 기존 버전 전체 114개 baseline은
반복하지 않았습니다. 112는 하위 테스트 중복을 포함한 실패 이벤트 수이며 독립 기능 결함 수가 아닙니다.
최초 외부 소비자 fixture의 CP949 읽기 오류도 보존했고 명시적 UTF-8 fixture로 따로 실행했습니다.

## 남은 Windows 문제

### WIN-PHASE4-01 — 기존 게이트 결함

미완료 03 문서가 존재해도 경로 구분자 비교가 어긋나 Phase 04 체크리스트 게이트가 경고 후 통과합니다.
기존 버전·후보 소스와 설치 wheel, 양 host에서 재현했습니다. 이번 overlay·#36 수정 범위에
편입하지 않았고 해결된 것으로 기록하지 않습니다. [사용자 안내](../../troubleshooting.md)를 따릅니다.

### Windows 3.11 fixture의 간헐 WinError 5

최초 layout 53개 실행에서 테스트 준비 폴더 `os.rename`이 접근 거부로 실패했습니다. 제품 판정
전 단계입니다. 현재 단독 2회, 기존 버전 단독 1회, 현재 전체 53개 재실행은 PASS였습니다.
원인과 고정 재현 조건은 미확인입니다. 최초 오류를 보존하며 재실행 성공으로 해결 처리하지 않습니다.

## 산출물 결속과 독립 승인

당시 최종 wheel SHA256은 `64d7a8a5577228aaeb81d6d8dbff6a889dd8afe8c266653afa1cf61ba08c7cfd`입니다.
이전 테스트 wheel과 동봉 테스트 4개·RECORD만 달랐고 실행 제품 entry는 모두 동일했습니다.
원본 Windows 근거 322개와 146개 원본 명령 로그의 SHA를 검산했습니다. 원자료 식별자는
`overlay-issue36-platform-20261107`의 `platform-summary.json`, `windows-evidence.zip`,
`mac-stage-reviewed.json`, `final-wheel-bridge.json`입니다. 새 문서·PR commit에 대한 CI 산출물과는 별개입니다.

리뷰 예산 초과로 [통합 독립 리뷰](../05/overlay-issue36-integration.md)는 `BLOCKED`입니다.
이 플랫폼 결과나 새 PR의 CI 성공이 그 판정을 대신하지 않습니다. 통합 Phase06과 릴리스는 별도입니다.
