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

## Windows 문제와 후속 검증

### WIN-PHASE4-01 — 기존 게이트 결함

2026-11-07에는 미완료 03 문서가 존재해도 경로 구분자 비교가 어긋나 Phase 04 게이트가 경고 후
통과했습니다. 기존 버전·당시 후보 소스와 설치 wheel, 양 host에서 재현했고 원래 overlay·#36
통합 범위에는 편입하지 않았습니다. 위 원본 실패 수치는 당시 관찰로 보존합니다.

2026-11-10 후속 수정은 비교 키를 `/` 형식으로 통일하고 실제 파일은 원래 경로로 읽습니다.
정규화된 키가 서로 다른 파일과 충돌하면 기존 계약 오류 경로로 차단합니다. 별도 Windows 11 Pro
실기기(Build 26200, x64)에서 Python 3.10·3.11·3.12와 Claude·Codex hook을 확인했습니다.

| 후속 검증 | 결과 |
|---|---|
| 관련 회귀 | 세 Python 합계60 Ran, POSIX 전용6 skip, 실패·오류0 |
| 수정 전 대조 | native/Git Bash36사례. 미완료 문서가 있는12사례의 warn/exit0 재현 |
| 수정 후 소스 | native/Git Bash36사례 PASS. 미완료는 block/2, 완료는 ok/0, 문서 미존재는 warn/0 |
| 설치 wheel | 양 host 합계18사례 PASS. 소스 경로 주입 없이 설치된 hook 진입점 확인 |
| Mac 회귀·패키지 |114스크립트·4155 Ran·15 skip·실패/오류0, 격리 wheel consumer PASS |

Windows의6 skip은 실제 파일명에 역슬래시를 쓸 수 없는 환경을 제외하는 POSIX 전용2테스트×3버전이며,
해당 테스트는 Mac에서 실행했습니다. 수정 후 hook54사례에는 skip이 없습니다. 전체 Windows 스위트와
실제 모델 앱 세션은 다시 실행하지 않았고, 장비에 있는 Python3.14는 이번 행렬에 포함하지 않았습니다.
검증 wheel SHA256은 `434c08c07f31120836f82f6a27052c0d8ec911b7cc6a5f98c46dc85fdc44b0fe`이며,
[원문 결과와 코드·테스트 SHA](windows-phase4-paths.validation.json)를 보존합니다. Windows 실행은
커밋 전 파일 snapshot에 결속되며 후속 문서 변경은 이 코드·테스트 바이트를 바꾸지 않았습니다.
[사용자 안내](../../troubleshooting.md)는 수정이 포함된 패키지와 hook의 적용 여부를 구분합니다.

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

당시 통합 독립 리뷰는 예산 초과로 중단됐지만, 이후 `2e79f77`에 대한
[통합 독립 리뷰](../05/overlay-issue36-integration.md)를 완료하고 `8497527`에 기록했습니다.
그 승인은 이번 Windows P1 후속 코드에 자동 상속되지 않습니다. 이 문서는 플랫폼 검증 근거이며
새 코드의 독립 승인이나 Phase06·머지·릴리스를 대신하지 않습니다.
