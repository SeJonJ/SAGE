# Overlay 오류 복구·적용 전 검사·host 검증 완료 보고

Cycle-Stem: overlay-recovery-boundary
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Status: DEVELOPMENT_COMPLETED
Cycle-Status: CLOSED
Source-05: docs/plan_docs/05/overlay-recovery-boundary.md
Phase05-SHA256: f46bb6cd853651a2615caea3bab5cb2291b07ffd8dd3d0097ee5a794855d8bcf
Review-Run: external-reset-20261112-rounds-1-to-3
Cycle-Control: external (non-self-dogfooding)
Machine-Cycle-Declaration: absent (engine installation not created)
Knowledge-Writeback: external manual update to existing Obsidian SSOT
Retro: external advisory recorded; no asset proposal applied
Completion-Date: 2026-11-15
Depth-Self-Review: performed

## 완료 판정과 사용자 승인

세 묶음 M1 세션 봉쇄 해소·M2 적용 전 검사 일치·M3 실제 설치 host별 검증을 완료했다.
[00 완료 조건](../00/overlay-recovery-boundary.md) C1–C6는 모두 실행 근거로 충족했고,
[05](../05/overlay-recovery-boundary.md)의 종합 판정은 APPROVED다. 원문 자동 이전·축약·분할,
전달 용량 확대·새 DB/프로토콜/복구 CLI는 추가하지 않았다.

2026-11-15 사용자는 Phase06/사이클 종료, 관련 MD 정리, 커밋·푸시·머지·릴리즈와 위키 갱신을
명시 승인했다. 이 문서는 개발 사이클 완료 보고다. 작성 시점의 PR/CI·게시를 성공 실적으로
미리 세지 않으며, 실제 통합·출하 결과는 해당 commit checks와 v1.3.7 Release/PyPI에 결속한다.

## 근본 원인과 수정 이유

입력 검사가 부적합한 overlay를 발견하는 것은 정상이다. 그 오류를 일반 프롬프트와 모든 도구의
공통 선행 조건으로 연결해 읽기·진단·사용자 수리까지 막은 결합이 세션 봉쇄의 원인이었다.
적용 전에 shared/personal·host 조건을 동일하게 확인하지 못한 것과, Codex-only 경로에
Claude 전달 한도가 유입된 것은 연결된 적용/검증 문제였다.

복구 가능한 입력 실패는 본문 없는 현재 무효 상태를 공급해 과거/부분 지침을 대체하고,
영향받는 SAGE 작업만 보류한다. 기존 독립 규칙이 허용하는 읽기·진단·원문 수리는 유지한다.
사용자는 파일·원인·관측치·한도·단위를 보고 원문을 직접 조정한다. 다음 유효 경계가 새 지침을
공급한다. profile/runtime 무결성·risk/phase gate·생성물 쓰기 보호는 계속 검사한다.

## 변경 내역과 최소 보완

- `sage/overlay_delivery.py:preflight_delivery`와 `delivery_hosts`가 적용할 profile/manifest와
  실제 host를 기준으로 입력/한도를 검사한다. install·sync·upgrade·generate·validate에 연결했다.
- `sage/commands/validate.py:run`은 heuristic lint의 WARN/strict 정책과 전달 검사를 분리한다.
  개인 lint·후속 크기 오류를 놓치지 않으며 전체 routing 무결성 FAIL은 유지한다.
- `sage/commands/upgrade.py:_managed_steps`는 CORE skill scope와 설치 hook host를 나눠
  Codex global/disabled를 포함한 dual-host hook을 재생성한다. force host 정규화도 맞췄다.
- `overlay_context.py:merge_current_output`과 hook orchestrator는 reentry/submit 병합 크기를
  재검사한다. bounded unavailable 대체도 다시 검사하고, risk commit 전에 실패를 돌려준다.
- `unavailable`, `_ensure_session_06_snapshot`, `run_session_start_snapshot`의 malformed/nonmapping
  입력·baseline/no-claim·startup 필터 경계를 보완했다. 공통 parser 정책은 넓히지 않았다.
- CORE root7종에 현재 무효 상태를 처리하는 지침을 정렬했다. 정상 standard2/Fast4 출처 순서,
  root/role/checkout 경계와 사용자 원문 비저장은 유지한다.
- Windows 실행 중 발견한 POSIX 고정 기대 경로는 시험 단언1줄만 `os.path.join`으로 보완했다.
  해당 변경 이후 제품 코드는 그대로이며 Mac 관련91·Windows 관련 시험을 재검증했다.

## 검증과 수용 근거

| 항목 | 실행 결과 | 범위·한계 |
|---|---|---|
| C1 | 입력 오류 중 prompt/Read/진단/허용 source 수리, 생성물 쓰기 차단과 외부 수리 후 재공급 | 설치 hook/CLI와 회귀; 임의 Bash 쓰기까지 모두 보호한다고 주장하지 않음 |
| C2 | 실제 Claude Code `claude-opus-5-5`·Codex `gpt-6.1-sol`, 같은 세션 정상A→무효→외부수리 정상B PASS | root Fast의 standard/shared/personal 4출처; 재선택 없이 새 generation 적용. 모든 child·checkout·장기 세션을 일반화하지 않음 |
| C3/C4 | 적용 전 shared/personal·host 검사, force 보존 host와 profile 복구, dual-host upgrade PASS | 독립 routing/무결성 정책 유지; Codex-only8KB와 Claude 추가 거부 구분 |
| C5 | 전체115요약·4,175 Ran(15skip 포함)·실패/오류0, 후속 시험1줄 뒤 Mac 관련91 PASS | 중복 실행·skip을 고유 PASS 수로 합산하지 않음 |
| C6 | Windows11 Pro x64, Python3.10.11/3.11.9/3.12.10 | 각 일반88PASS/링크fixture3skip·동일3관리자PASS, native84·platform10 PASS; 설치package358파일 동일wheel 확인 |

Windows는 일반 권한 skip9회를 그대로 남기고 같은 링크fixture 시험9회를 관리자 권한에서
별도로 통과시켰다. 관리자 결과를 일반 권한 PASS로 바꾸지 않는다. 설치 CLI/native252항목과
platform30항목은 일반 권한이다. Windows 전체4,175회귀·Windows 실제LLM을 실행했다고 하지 않는다.

초기/중간 실패는 보존했다. Windows 경로 단언, symlink 생성 권한, -I의 UTF8 환경변수 무시,
정상 ACP 출력을 UTF8로 가정한 수집기, PowerShell의 native stderr 처리를 제품 결함과 구분했다.
세부 원문은 04/05와 위키 SSOT의 artifact manifest에서 추적한다. 공개 재현 요약과 원자료 digest는
[검증 영수증](../04/overlay-recovery-boundary.validation.json)에 보존한다.

## 독립 리뷰·대상 결속·비용

활성 reset 원장에 완료 라운드3회를 보존한다. 최종3라운드는 사용자 선택 fresh same-runtime
Codex5관점·Codex peer·반박2명이며, 새 코드 지적/필수수정0건이다. 문맥 보충 후 G5/G6 closure를
모두 확인했고 G1/G3/G8은 이전 라운드와 명령 코드 bytes 동일 근거를 이어간다. 이전 cross-model
이력과 사용량을 same-runtime 결과로 바꾸지 않았다.

고정 review source는 `dc1384334831540522c3c9450f81ce2567517e2ddc9e778a9fe0877cdb23bebd`,
review patch는 `1a7e24566ddfcef06dec18f0bf7a46cad8c577a9acd1c41382e0d3dbf858a151`이다.
이후 변경은 실행 증거 문서와 시험 경로 단언1줄이며 제품 실행 소스는 불변이다. 원래 모델 응답의
BLOCKED는 당시 C2/C6 미실행을 보존하고, 후속 실제 근거를 합산한 종합 판정을 05에 따로 기록했다.

리뷰 신규 입력(캐시 제외)+출력은790,356/800,000·잔여9,644, cache read183,424다.
별도 C2 실제 모델 검증은29,813/cache87,089이며 리뷰+수용검증 합계는820,169다. 과거 제외
리뷰850,390은 별도 보존했다. 진행자 준비/실행 비용은 미계량이며0으로 세지 않는다.
식별자 오류·응답 디코딩·역할 설명 echo와 예산 예약 실패를 원문·무효 상태·비용과 함께 남겼다.
사용자 승인 없는 초기화/증액·새 모델 리뷰는 이번 완료/배포 단계에서 수행하지 않는다.

## 잔여 후보와 회고

child 공급 비대칭(G2), integrity 분류(G4), transaction 입력 경쟁(G9), 별도 목적지 후보는
추가 실행 근거가 필요한 상태다. cleanup 요약(G7)·동시 유지보수(G10)는 낮은 실질 영향/재현
근거로 자동 수정에 넣지 않았다. 기존 결함 여부나 P0/P1 이름만으로 처분하지 않고 중요도·실질
위험·재현도와 최소 변경을 기준으로 분리했다. 보류는 사용자 잔여위험 수용이나 해소 선언이 아니다.

외부 회고는 입력 복구와 무결성 실패를 나누는 경계, 호출 전 남은 모든 역할의 예산 예약,
원문/대상/사용량 보존, fixture 권한·인코딩과 제품 동작의 구분을 남긴다. 개선 제안은 advisory며
별도 자산 수정·리뷰 runner 재개발로 적용하지 않는다. 엔진에 consumer profile·cycle.json을
만들거나 자기 review-loop/waiver/knowledge CLI로 승인하지 않았다. 외부 문서의 CLOSED가 종료 기록이다.

## 산출물과 배포 인계

- 실행 문서: 같은 stem의 00–06 `overlay-recovery-boundary.md`, 검증 인덱스 `docs/plan_docs/README.md`.
- 사용자 문서: README 한영, CLI·Architecture·troubleshooting·release-readiness 한영, 문서 인덱스.
- 제품/시험: 위 수정 파일·`test_overlay_recovery.py`·관련 runtime/collector 회귀·run-all 등록.
- 위키 정본: `SAGE - overlay 오류 복구·적용 전 검사·호스트 검증 수정 정본 (26.11.12)`와 로드맵/index/log.
- 원문: 노트북(macOS)의 `overlay-recovery-rework-20261113`, `overlay-c2-native-model-20261113`,
  `overlay-recovery-windows-20261114` 및 위키의 `artifacts/sage-overlay-repair-20261112`.
- 통합/출하: 1.3.7은 문서 작성 시점 미게시다. 사용자 승인에 따라 PR CI→merge→정확한SHA의
  tag/publish→GitHub/PyPI 확인·신규 설치 순서로 진행하며 각 단계의 실제 결과를 위키에 후속 기록한다.
