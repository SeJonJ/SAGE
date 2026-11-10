# Overlay·구 레이아웃 업그레이드·Windows 경로 수정 완료 보고

Cycle-Stem: overlay-issue36-integration
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Status: DEVELOPMENT_COMPLETED
Source-05: docs/plan_docs/05/overlay-issue36-integration.md
Loop-Run: external-20261110-overlay-delta-resume
Completion-Date: 2026-11-11

## 완료 판정과 승인 범위

기존 overlay 3가지 문제와 #36 구 레이아웃 업그레이드의 통합 개발을 완료했다.
통합 I1~I6은 [00](../00/overlay-issue36-integration.md)과
[05 독립 검토](../05/overlay-issue36-integration.md)의 근거로 충족했다.
그 뒤 별도 PR #38에서 수정한 Windows P1은 아래 사용자 결정으로 승인했다.
독립 검토의 수행 범위와 사용자 승인 범위를 합쳐 하나의 독립 검토 통과로 표현하지 않는다.

| 대상 | 고정 대상과 근거 | 처리 |
|---|---|---|
| Overlay 3가지 문제 | [기존 06](overlay-context-delivery.md), 원래 A1~A8의 근거·한계 보존 | 개발·독립 검토 완료 |
| #36 결합과 최소 연결 수리 | 검토 source `2e79f7736df6d724b0438f8e43cee9e37ce38300`, 문서 head `8497527816377cdad26a224e90210269c7071c9b`, [PR #37](https://github.com/SeJonJ/SAGE/pull/37) | 외부 독립 검토 APPROVED / CONVERGED |
| Windows `WIN-PHASE4-01` | 코드·테스트 `e025e87176af8739304ff29fbdd5d4d33147221b`, [PR #38 사용자 승인](https://github.com/SeJonJ/SAGE/pull/38) | PASS / USER_APPROVED, 별도 독립 리뷰 NOT_RUN |
| 이번 보고·배포 준비 | 위 대상 이후 완료 보고·문서 인덱스·패키지/엔진/기본 프로필의 1.3.7 버전 세 곳만 변경 | 코드 검토를 새로 수행한 것으로 세지 않음 |

2026-11-11 사용자 결정 원문:

> 해당 수정분의 독립리뷰는 따로 할 필요없다고생각해. 내가 승인할테니 pass 로 진행해줘
> 아니 그리고 애초에 저 부분이 많이 수정된게 아닌데 굳이 리뷰가 더필요해?

이어 사용자는 다음과 같이 Phase06·머지·릴리스를 명시 승인했다.

> 그러면 phase 06 까지 완료한 후
> 머지 및 릴리즈까지 진행해줘

이번 예외는 PR #38의 해당 수정분에만 적용한다. 기존 독립 검토 기록·비용 원장과
일반 소비자 프로젝트의 리뷰 정책·엔진 gate를 변경하지 않았다. 개발 중인 SAGE의
review-loop·waiver·자기승인 도구를 승인 권위로 실행하지 않았다.

## 무엇을 어떻게 고쳤는가

1. 공유 overlay가 압축·재개 뒤 문맥에서 사라지던 경계를 공통 catalog 수집과 재전달로 연결했다.
2. 개인 overlay도 별도 CLI fetch에 의존하지 않고 같은 수집·전달 계약에 포함했다.
3. Fast에서는 공유 표준 → 공유 Fast → 개인 표준 → 개인 Fast를 적용한다.
   표준 모드는 자기 표준 출처만 사용하며 다른 대상이나 Fast를 임의로 선택하지 않는다.
4. #36의 구 레이아웃 project hook·migration deferral·global rollback을 통합했다.
   두 local host의 CORE 갱신 순서와 사용자 원본 보존은 기존 transaction 안에서 수리했다.
5. 업그레이드 계획 중 Python 컴파일의 RecursionError·MemoryError를 기존 차단 진단으로 처리했다.
6. Windows checklist 수집에서 비교 키의 구분자를 정규화하고 실제 읽기는 원래 경로로 한다.
   미완료 문서는 block/2, 완료 문서는 ok/0이며 실제 문서 미존재는 기존 warn/0을 유지한다.
   서로 다른 파일의 정규화 키 충돌은 차단하고 동일 파일의 glob 중복은 허용한다.

새 상태 DB·의존성·프록시·인증 체계를 만들지 않았다. 원본 #36 worktree와 통합 전 안전
stash `bcb1711da4a7d386d14220bf3ce3c13f24353354`, 복구 ref
`refs/sage-backups/overlay-before-issue36-20261107`를 보존한다.

## 검증 근거

| 구분 | 확인한 결과 | 범위 |
|---|---|---|
| Mac 전체 회귀 | 114개 스크립트, 4,155 Ran, 15 skip, 실패·오류0 | Windows 수정 후 source, 반복·skip을 고유 PASS 수로 바꾸지 않음 |
| Mac 관련 회귀 | 20개 통과 | 경로·실제 읽기·충돌·glob 중복 |
| Windows 11 실기기 | Python3.10·3.11·3.12, 관련 회귀60 Ran/6 POSIX 전용 skip/실패·오류0 | POSIX 전용 시험은 Mac에서 실행 |
| Windows 수정 전 대조 | native/Git Bash36사례 중 미완료12사례의 잘못된 warn/0 재현 | 이전 동작 확인 |
| Windows 수정 후 | native/Git Bash36 + 설치 wheel hook18 = 54사례 PASS | Claude·Codex hook, 미완료·완료·문서 미존재 |
| 격리 wheel consumer | build·설치·bundle 무결성·정상 validate0·고의 변조 validate3 PASS | 엔진 checkout의 자기승인 아님 |
| 통합 검토 source CI | [42659320255](https://github.com/SeJonJ/SAGE/actions/runs/42659320255), 13 success/1 skip/0 failure | 검토 source `2e79f77` |
| PR #37 문서 head CI | [42813471796](https://github.com/SeJonJ/SAGE/actions/runs/42813471796), 13 success/1 skip/0 failure | `8497527` |
| PR #38 코드 head CI | [42837721166](https://github.com/SeJonJ/SAGE/actions/runs/42837721166), 13 success/1 skip/0 failure | `e025e87` |
| 최초 1.3.7 격리 후보 | wheel consumer PASS·엔진 sentinel 불변, 패키지 비교356파일 동일/엔진 버전 파일1개 차이 | 최초 후보 이력이며 기본 프로필 버전 누락은 아래에서 정정 |
| 설치 후보 언어·플랫폼 검사 | 12항목·21 CLI 호출 PASS | 한영 help·local 언어·영문00 skeleton·encoding·양 host CORE7종·양 언어 bootstrap 차단·legacy migration·project hook adapter |
| 완료 보고 문서 검사 | 18개 PASS, diff 공백 검사 PASS | 보고·인덱스·버전 갱신 |

[Windows 원문·SHA](../04/windows-phase4-paths.validation.json)와
[플랫폼 범위](../04/platform-validation.md)를 함께 보존한다. 실기기에서 실행한 snapshot의
코드·테스트 SHA와 `e025e87`의 동일성을 확인했다. 문서·버전 변경을 포함한 새 commit 전체를
실기기에서 다시 실행했다고 주장하지 않는다. 최종 보고 이후 CI·릴리스 결과는 각 PR checks와
GitHub Release의 정확한 SHA·태그에서 확인하며, 아래 계획을 완료 실적으로 미리 세지 않는다.

## 독립 검토와 비용

### 릴리즈 버전 동기화 정정

최초 배포 준비 commit `41d7bf9`는 패키지/엔진 버전만1.3.7로 바꾸고
`templates/project-profile.yaml`의 required_version을1.3.6으로 남겼다.
CI `42849879272`의 기존 `test_bundled_profile_template_matches_package_version`이 이를
검출했다. 동일 단일 테스트를 로컬에서도 실패 재현한 뒤 템플릿 버전1줄을1.3.7로 맞췄다.
이 실패를 기존 후보의 전체 회귀 성공으로 덮지 않는다. 최종 wheel·설치 검사와 CI를 새로
실행하며, Windows 경로·overlay 동작 로직은 그대로 보존한다.
로컬 설치145개·문서18개와 재빌드 wheel consumer가 통과했다. 최종 후보는 이전 Windows
검증 wheel과 dist-info 외355파일 동일, 엔진/기본 프로필 버전2파일만 다르다.
설치한 최종 후보의 언어·플랫폼12항목/21 CLI 호출도 다시 통과했다.

통합 독립 검토는 Codex5관점·Claude peer·라운드별 반박2명이며 완료5/상한5,
최종 필수 미해결 finding0이다. 새 원장365,312/400,000, 이전 원장1,953,432/1,800,000과
그 초과를 그대로 보존했다. Windows 후속 수정에는 추가 모델 리뷰 호출·비용을 쓰지 않았다.
사용자 승인은 독립 리뷰의 실제 수행 이력이나 라운드 수를 늘리지 않는다.

## 배포 인계와 남은 범위

개발 완료와 사용자 출시 승인을 확보했다. 보고 작성 시점에는 머지·태그·PyPI 배포가 아직
실행되지 않았다. 1.3.7 후보를 격리 설치해 검사한 뒤 PR #37을 먼저 머지하고,
PR #38의 base를 main으로 바꿔 최종 CI를 확인해 머지한다. 병합 후 main CI 성공을 확인하고
`v1.3.7` 태그로 저장소의 publish workflow를 실행한다. GitHub Release·PyPI 게시와
게시 wheel의 신규 설치를 확인한 뒤에만 배포 완료로 보고한다.

Windows 전체 회귀 성공·모든 기존 Windows 결함 해결을 주장하지 않는다. Python3.14,
기존 WinError5 및 #28/#30 이식성·제거 잔여, 실제 Claude/Codex 앱의 새 전체 모델 세션은
이번 후속 수정에서 검증하지 않았다. 전역 설치 갱신도 릴리스와 별개다.
물리적으로 root에 공급되는 여러 overlay 원문은 대상 선택 계약으로 구분하며 물리 격리는 아니다.
추가 기능은 이번 릴리스 범위에 넣지 않는다.
