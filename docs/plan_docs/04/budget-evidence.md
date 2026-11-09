# Phase04 A8 — 호스트 문자열 예산 재작업

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Status: IMPLEMENTED_SCOPED_VERIFIED — 최종 native boundary 검증은 parent 통합 기록 참조

## 관측과 범위

기존 개발 ceiling을 실제 호스트 지원 한도로 확정하는 과정에서 Claude Code 2.1.318이 전체
catalog를 모델 요청에 넣지 않고 파일 경로와 preview로 바꾸는 반례가 나왔다. 관측 원자료는
[large-exact-instrumented](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-claude-ze06d_f3/large-exact-instrumented)이다.
helper는 이를 읽어 본문 없이 크기·hash와 preview 표지 존재만 다시 계측했다.

- hook의 원래 단일 additionalContext: UTF-8 49,152 bytes, UTF-16 43,552 code units.
- 모델 요청에 `Preview`와 `first 2KB` 표지가 있었다. 이것을 전체 전달 성공으로 세지 않는다.
- hooks SHA256: `0a9d96598abc7c393a41b856d86c49b8d94be4f42ac324d9d612fbac65ee981f`.
- requests SHA256: `10525ab317b4be11bc19204e5fabf13722f2424d5e1f912b05611f75d8b68f16`.
- [독립 재계측 JSON](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-budget/native-spill-metrics.json).

2026-11-05 직접 조회한 [Claude 공식 JSON output 문서](https://code.claude.com/docs/en/hooks#json-output)는
각 문자열 필드별 10,000자 상한, 초과 시 파일/최대 2,000자 preview 대체, 상한을 올리는 설정 부재,
모델에 파일 읽기를 자동 요청하지 않는 동작을 설명한다. 서로 다른 hook 전체를 합한 상한이라는 뜻은
아니다. SAGE는 한 handler에서 합성하는 단일 additionalContext를 검사한다. UTF-16 units는
JavaScript 문자열 길이와 맞추는 제품의 보수적 측정 단위이며 bytes/token/Python `len`과 다르다.

## 지원 예산과 변경 의미

| 경계 | 단위와 한도 | 근거/의미 |
|---|---|---|
| 공통 source | UTF-8 10,000 bytes | 기존 ceiling 유지 |
| 공통 catalog | wrapper/JSON escape 후 UTF-8 49,152 bytes | 기존 ceiling 유지 |
| Claude catalog | wrapper/JSON escape 후 UTF-16 7,500 code units | host 문자열 상한 안에서 나머지 context 2,500 units 확보 |
| Claude 최종 병합 문자열 | UTF-16 10,000 code units | 실제 출력할 한 문자열의 방어 검사 |
| Codex | 공통 ceiling 및 native `additionalContextLimit=60000` | 기존 설정 유지 |

7,500은 공식 호스트 한도 자체가 아니라 SAGE의 catalog 배분이다. reentry·declared-risk가 예약량보다
커지면 최종 병합 guard가 별도로 거부한다. 이 수리는 새로운 chunk 프로토콜·DB·원문 축약이나
preview/모델 자발 fetch fallback을 추가하지 않는다. 임의로 전체 입력을 줄여 A8을 통과했다고
처리하는 것이 아니라, 실측으로 드러난 물리 제약을 지원 계약에 반영한다. 기존 source ceiling을
만족하는 단일 10,000-byte ASCII 본문도 wrapper/참조표를 포함한 Claude catalog에서는 거부될 수
있다. 이는 기존 입력에 대한 새 지원 제한이며 이를 문서와 doctor에 명시했다.

## 구현 계약과 소유

- `sage/overlay_delivery.py`: `utf16_code_units(text)->int`,
  `check_host_context(text, runtime, *, catalog=False)->None`,
  `render_catalog(catalog, *, runtime=None)->str`를 제공한다.
- runtime 없는 render/collector는 공통 입력 계약을 유지한다. host 인자를 넘긴 render는 같은 최종
  직렬화 문자열에 추가 host catalog 검사를 수행한다. 새로운 승인 validator를 만들지 않는다.
- Claude cap 오류는 `overlay_delivery.host_catalog_too_large` 또는
  `overlay_delivery.host_context_too_large`이며 code, observed, limit, unit, runtime만 표시한다.
  `.observed/.limit/.unit/.runtime` 속성도 제공한다. 본문이나 preview를 진단에 넣지 않는다.
- `sage/commands/doctor.py`: `catalog_input=VALID`와 호스트별
  `catalog_budget=SUPPORTED|EXCEEDED`를 분리하고 측정치·한도·단위를 명시한다.
  `merged_event=UNVERIFIED`, native/trust 미검증을 예산 충족으로 대체하지 않는다.
- 관련 collector/doctor tests와 한영 architecture/troubleshooting/CLI 예산 문단을 수정했다.
- parent가 runtime의 host 인자 연결과 최종 병합 문자열 guard·native 차단을 소유한다.
  이 담당자는 runtime/CORE render를 직접 수정하지 않았다.

## 실제 consumer의 metrics-only 확인

`/Users/sejon/project/ChatForYou_v2`의 현재 공유 source 두 파일을 읽어 본문을 출력하지 않고
정규화 UTF-8/UTF-16 길이와 SHA256만 계산했다. 파일을 변경하거나 consumer 명령을 실행하지 않았다.

| source | UTF-8 bytes | UTF-16 units |
|---|---:|---:|
| `skills/sage-plan.md` | 3,676 | 1,787 |
| `skills/sage-review.md` | 4,784 | 2,465 |
| 합계 본문 | 8,460 | 4,252 |
| 현재 root/경로/hash/참조표/wrapper/JSON 포함 catalog | 9,971 | 5,763 |

현재 입력은 Claude catalog 7,500 한도 안에 있으며 1,737 units 여유다. 임의 future 입력이나 다른 root
길이까지 보장하지 않는다. `catalog_sha256=702ac567a83d1078924a4f3c0de58384dfb1f2bebf2a968b3c0e5ea6fe6fa6a3`.
[metrics JSON](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-budget/consumer-metrics.json)에
파일 hash를 함께 보존했다. 이 계산은 native 설치·실제 모델 적용 성공을 의미하지 않는다.

## RED/GREEN 및 미실행

Python은 `/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python`이다.

1. 제품 코드 변경 전:
   `python -m unittest scripts.sage_harness.hooks.tests.test_overlay_delivery.HostBudgetTests scripts.sage_harness.hooks.tests.test_doctor.TestOverlayDeliveryDoctor.test_byte_valid_catalog_is_reported_exceeded_for_claude_only`.
   5 tests, failures5, exit1. UTF-16 측정/host guard/runtime render 인자 부재와 doctor의 host 구분 부재가
   실패 원인이었다.
2. 같은 명령을 구현 후 실행해 5 tests, OK, exit0, 0.042s를 확인했다. emoji 3,750개=7,500 units 및
   5,000개=10,000 units 경계의 성공, +1 unit 실패, wrapper/JSON escape 포함, Codex 공통 한도 유지,
   doctor의 Claude 초과/Codex 충족 및 개인 본문 비출력을 검사했다.
3. 해당 overlay_delivery/doctor module 전체를 실행해 exit0를 확인했다. 이후 한영 문서와 최종
   scoped 로그 보존을 위해 documentation 검사를 포함한 88개를 실행했다. 첫 실행은 source hash
   marker가 낡은 번역 세 짝을 두 documentation test가 발견해 failures2/errors0/skipped0, exit1이었다.
   실제 변경한 한영 budget 문단의 대응을 확인하고 해당 세 English source marker를 갱신했다.
   [첫 실패 로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-budget/r1-budget-scoped-tests.log)를 보존했다.
   동일 88개 재실행은 failures0/errors0/skipped0, exit0, 3.866s였다. 상세 결과는
   [로그](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-budget/budget-scoped-tests.log),
   [명령 대상·개수·제품 hash 집계](/Users/sejon/project/sage_project_worktree/overlay-context-phase04-budget/budget-scoped-summary.json)를 따른다.
4. `git diff --check` exit0. 수정 Python 네 파일의 `ast.parse` 통과.

이 담당 범위 제품 hash는 `sage/overlay_delivery.py=350df71a554a3a31206df44b108b5aa4925b1a637b09edc08c6dd52658383aad`,
`sage/commands/doctor.py=74173106bea7441bfa5efac43b1e03582719dbe08b204ceef94abb158b8a570b`이다.

전체 공식 runner·최종 wheel·Claude/Codex 실제 native 최대 경계는 parent가 통합 source를 고정한 뒤
검증한다. 이 기록은 그 검증을 대신하지 않으며 A8 전체 충족이나 canonical reviewer verdict를
부여하지 않는다. 최신 사용자 지시는 04까지만 마무리하고 중지이며 05/06은 진행하지 않는다.
