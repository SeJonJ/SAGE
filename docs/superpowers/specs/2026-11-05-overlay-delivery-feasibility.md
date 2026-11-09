# Overlay 통합 수정 — 설계 확정 전 실현성 점검

> 후속 [대상별 문맥 묶음 권고안](2026-11-05-overlay-context-catalog-design.md)과 [추가 관측·검토 기록](2026-11-05-overlay-catalog-review.md)이 작성됐다. 아래 반례는 기존의 “훅이 현재 대상을 먼저 식별하는 방식”에 대한 결과다. 모든 대안이 불가능하다는 결론이나 최신 설계의 최종 상태로 읽지 않는다.

- 점검일: 2026-11-05
- 소스: v1.3.6 / `8e17a88c08f12fc8ea1a5fe5672270c62d13a5ef`
- 로컬 호스트: Claude Code 2.1.318 / Codex CLI 0.166.0
- 상태: **현재 전달 알고리즘은 확정 불가. 제품 구현 미착수.**
- 사용자 승인: 확인이 끝나고 구현 가능한 설계를 확정하면 개발을 바로 시작한다. 확인을 생략하거나 지원 범위를 줄이는 승인이 아니다.

## 1. 결론과 증거의 범위

세 가지 문제를 한 번에 수정한다는 요구와 Fast의 표준+Fast 상속 의미는 유지한다. 그러나 기존 생명주기 훅에서 선택 대상을 알아내 필요한 본문만 전달하는 안에는 실제 반례가 있다. 이를 해결하지 않고 03 구현을 시작하면 개인 자동 전달과 정상/Fast 구분이 없는 상태에서 시작하게 된다.

설치된 실제 CLI를 **합성 프로젝트·로컬 HTTP 모의 모델**에 연결했다. 호스트가 보낸 요청 본문, 훅 stdin, 훅 실행 당시 transcript, 요청 건수를 관측했다. 실제 모델의 지침 준수, 실제 수동/자동 압축, 재개 후 복구는 이 결과로 검증하지 않았다. 모의 모델의 고정 답변은 행동 smoke가 아니다.

전역 사용자 설정·실제 프로젝트 overlay·제품 코드를 변경하지 않았다. Codex 훅 신뢰는 점검 전용 임시 home 안에서만 설정했으며 실제 사용자 환경에 적용하지 않았다. 요청 헤더·인증 토큰은 저장하지 않았다. 기존 사용자 환경에서 제공되는 기본 호스트 지침/스킬 목록은 요청에 포함될 수 있으므로 raw request는 로컬 점검 자료로만 취급한다.

## 2. D1 — 대상 식별 및 오류 중단

### Codex 선택 UI의 구조화 입력

실제 `codex app-server`에 두 개의 새 thread를 만들었다. cwd와 Text 입력은 동일하게 두고 `UserInput::Skill`만 달리했다.

| 입력 | 첫 요청의 실제 스킬 본문 | UserPromptSubmit의 prompt | 선택 id/path 필드 |
|---|---|---|---|
| 표준 probe 스킬 선택 | 표준 marker 있음, Fast marker 없음 | `Reply with the probe marker.` | 없음 |
| Fast probe 스킬 선택 | Fast marker 있음, 표준 marker 없음 | 위와 같음 | 없음 |

SessionStart에도 선택 필드가 없었다. 두 훅이 실행된 시점의 transcript에는 두 스킬의 **목록 정보는 모두 있지만**, 선택된 본문 marker나 현재 선택을 식별할 기록은 없었다. 목록의 경로를 발견했다는 사실은 해당 스킬을 선택했다는 증거가 아니다.

설치 버전에 대응하는 공개 소스도 같은 경로를 보인다.

- `codex-rs/protocol/src/items.rs:545`: `UserMessageItem::message()`는 Text 외 항목을 빈 문자열로 만든다.
- `codex-rs/core/src/hook_runtime.rs:714`: UserPromptSubmit에는 그 문자열을 넘긴다.
- `codex-rs/hooks/src/schema.rs:500,568`: 두 훅의 입력에 선택 스킬 필드가 없다.
- `codex-rs/core/src/session/turn.rs:330`: 첫 턴의 스킬 본문 로딩은 대기 중 SessionStart 실행보다 앞선다. SessionStart에서 파일을 갱신해 첫 로딩을 고치는 가정도 채택할 수 없다.
- `codex-rs/core/src/skills.rs:123`: 내부 `on_skill_invocation` contributor는 있지만, SAGE가 사용자 설정으로 설치할 수 있는 외부 훅이라는 근거는 없다.

**판정:** 현재 관측한 훅 입력에 제한된 parser를 더하는 것만으로 선택 UI의 대상을 복원할 수 없다. session/turn id는 구별되지만 선택한 스킬과 연결할 관측이 없다는 문제다. 모든 미래 호스트 API와 모든 가능한 adapter가 불가능하다는 주장은 아니다.

### Codex 직접 언급과 암묵 읽기

- 직접 `$sage-overlay-probe` 호출은 실제 요청에 스킬 본문이 들어갔다. 훅에는 텍스트 prompt가 오므로 명시 문자열 경로의 후보는 남는다. 이것을 선택 UI까지 덮는 근거로 쓰지 않는다.
- 암묵 경로는 모의 모델이 합성 `SKILL.md`를 `cat`하도록 요청했다. 실제 `PreToolUse`는 `tool_name=Bash`, `tool_input.command`에 해당 파일 경로를 제공했다. 다음 요청에는 읽은 본문이 들어갔다.
- 따라서 셸 읽기 경로는 일부 관측 가능하다. 모든 셸 구문·다른 읽기 도구·선택 UI·중첩 복귀를 덮었다는 증거는 아니다. 암묵 전달 전체를 불가능하다고 판정하지 않는다.
- Codex는 합성 스킬 안의 Claude 동적 명령 문자열을 그대로 전달했다. 이 결과를 Claude의 `!` 명령 실행이 Codex에서도 지원된다는 근거로 쓸 수 없다.

### 실제 요청 중단 비교

| 호스트 / 이벤트 / 출력 | 훅 실행 관측 | 모델 HTTP 요청 | 판정 |
|---|---:|---:|---|
| Claude SessionStart 정상 context | 있음 | 1 | 대조군 |
| Claude SessionStart `continue:false` | 있음 | 1 | 이 출력으로 시작 요청을 중단하지 못함 |
| Claude UserPromptSubmit `decision:block` | 있음 | 0 | 해당 입력 경계의 중단 확인 |
| Codex SessionStart 정상 context | 있음 | 1 | 대조군 |
| Codex SessionStart `continue:false` | 있음 | 0 | startup 경계의 중단 확인 |

Claude에 필요한 대안 후보는 SessionStart 오류 결과를 session/root에 결속하고 기존 UserPromptSubmit과 PreToolUse에서 검사하는 방식이다. 아직 구현·압축·자식 문맥을 검증하지 않았다. 특히 자동 압축 직후에는 새 UserPromptSubmit 없이 모델 요청이 이어질 수 있으므로 **모델 요청 자체 0건**과 **제품 도구 실행 0건**을 같은 보장으로 표현하면 안 된다. latch 쓰기 실패가 정상으로 간주되지 않도록 독립 재검사도 설계해야 한다.

Codex startup 결과를 compact/resume/fork 경계의 중단 검증으로 대신하지 않는다.

## 3. D2 — 큰 본문 전달

네 개의 합성 슬롯에 각각 시작·끝 marker를 넣고 그 사이에 고정 문자열을 반복했다. 합친 본문은 47,700자/47,700 UTF-8 bytes다. 이 본문은 원래 사용자의 개인 overlay가 아니다. SessionStart와 UserPromptSubmit 각각 같은 큰 본문을 내보낸 출력 계약 시험이다. 중복 전달을 최종 제품 설계로 채택한 시험이 아니다.

| 설정 | 실제 HTTP 요청에서 네 슬롯 시작/끝 marker 모두 존재 |
|---|---|
| Codex handler 기본 한도 | 아니오. 중간 슬롯/marker 유실 |
| 각 handler `additionalContextLimit=20000` | 예 |

**판정:** 기본 spill이 전체 전달을 보장하지 않는다는 반례와, 명시 한도 설정으로 해당 합성 입력을 전달할 수 있다는 가능성만 확인했다. 20000은 시험값이며 최종 제품 상한이 아니다. 최소 한도·wrapper/재진입 합산·실제 token 수·지연·수동/자동 압축 뒤 복구·과거 Fast 사본 격리는 미확인이다.

선택 대상 채널이 성립하지 않은 상태에서 거부된 방식의 전체 압축/예산 matrix를 수행해 D2 PASS로 표시하지 않는다. 새 전달 방식이 정해지면 그 방식의 입력으로 재검증한다.

## 4. D3 — Fast 안전 경계

기존 테스트 fixture의 임시 프로젝트에서 실제 CLI를 실행했다. 실제 사용자 확인 절차는 수행하지 않고 합성 값만 제공했다.

| 명령 | 결과 | 관측 |
|---|---|---|
| `fast-cycle open` | exit 0 | 실제 위험 L3를 유지하면서 Fast 리뷰 수준 L2로 개방. 확인자 입력 필드 없음 |
| `fast-cycle convert` | exit 0 | 고정 확인 token과 합성 `--confirmed-by SYNTHETIC-NO-HUMAN-CONFIRMATION`으로 전환. 합성 확인자 문자열이 감사에 기록됨 |

이는 **기존 CLI가 인자/형식 검증과 실제 사람의 선택 출처를 구분하지 못한다**는 재현이다. 임의 명령 실행이 가능한 모델에 대해 확인자 문자열만으로 사람의 동의를 독립 보증할 수 없다. 기존 Fast 기능 전체가 새 overlay 때문에 생긴 버그라고 해석하지 않는다.

현재 Fast overlay는 차단되어 있으므로 실제 네 슬롯의 악성 본문을 Fast에 제공한 뒤 모델 행동까지 비교하는 시험은 수행하지 않았다. 전달 경로가 없는데 그 시험을 통과했다고 하지 않는다. 다만 Fast 자격을 열기 위한 기준에는 독립 floor 부재 자체가 차단 조건이므로 **확인 문자열 하나를 추가하는 정도로 Fast 자격을 개방해서는 안 된다.** X3는 최소 보완 또는 기존 격리 유지가 필요한 설계 항목으로 승격한다. 신뢰 가능한 사용자 선택과 연결하는 구체 수단은 미확정이다. 전반적인 승인 시스템 개편을 승인한 것은 아니다.

별도로 현재 소스에서 다음 회귀 검사를 실행했다.

| 검사 | 결과 |
|---|---:|
| `test_overlay_reclassification_backing.py` | 13 PASS |
| `test_fast_cycle.py` | 27 PASS |
| `test_fast_convert.py` | 52 PASS |
| 합계 | 92 PASS, 실패/오류 0 |

실행 interpreter: `/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python`. 이는 기존 제품 기준선이며 수정 완료·새 Fast 자격·정식 L3 승인 근거가 아니다.

## 5. 추가 Claude 실현성 검토와 처분

- 원래 설계 적대적 리뷰 3회와 구분하는 **실측 결과 기반 추가 검토 1회**다.
- session: `9c03d858-7e4c-4895-b0ab-c269adc54a93`
- 응답: success / is_error=false / num_turns=1, 실제 모델 `claude-opus-5-5`.
- [검토 원문](/Users/sejon/project/sage_project_worktree/overlay-design-preflight-k73xh3f3/feasibility-challenge-review.txt)

현재 선택 대상 훅 안을 확정할 수 없다는 핵심 지적은 채택했다. 단, 이 검토에도 확인 범위를 넘는 제안이 있어 그대로 설계로 승계하지 않는다.

검토 입력에는 큰 합성 본문 길이를 47,704자로 잘못 적었다. 실제 emitter 기준 47,700자로 정정한다. 요청의 marker 존재/부재를 대조한 관측에는 영향이 없다.

| 제안/지적 | 처분 |
|---|---|
| Codex 구조화 선택 정보가 훅에서 소실됨 | 채택. 실측 및 소스 일치 |
| Claude SessionStart 단독 native 중단 전제 폐기 | 채택. 실측 반례 있음 |
| Codex 암묵/도구 훅은 전혀 확인되지 않았음 | 최신 관측으로 보완. 실제 Bash PreToolUse 경로 1개를 확인했으나 전체 지원은 미확인 |
| Codex 전역 overlay 지원 제외 | 채택하지 않음. 지원 범위를 줄여 기존 DC4를 통과한 것으로 만들지 않음 |
| 개인 내용을 로컬 일시 렌더에 물리 반영 | 후보로만 보류. 기존 공유/개인 소유·정상본·설치·개인 비노출 계약을 바꾸며 전역 직접 선택의 문제를 해결하지 못함 |
| 압축 뒤 정지하고 사용자가 다시 호출 | 정상 복구 해법으로 채택하지 않음. 요청된 자동 복구를 수동 절차로 대체함 |
| D3에 독립 선택 출처가 필요 | 결함 범위를 한정하여 채택. 기존 구조 floor와 사용자 선택 출처를 분리하고 최소 보완 수단은 재설계 |

## 6. L3 및 sage-cycle 기반 개발 방식

사용자 선언을 받아 이번 변경을 **L3**로 관리한다. 변경 규모보다 양 호스트의 전달/실패 처리, 개인 지침 격리, Fast gate와 설치 수명주기에 걸친 영향이 근거다.

`sage-cycle`의 00 목표 → 01 요구 → 02 설계 → 03 구현 → 04 검증 → 05 독립 리뷰 → 06 보고 순서는 사용한다. 이 저장소에는 일반 소비자용 루트 `AGENT_GUIDE.md`, `sage/project-profile.yaml`이 없고, 소비자용 문서/스킬은 `templates/core/` 아래 있다. 프로필을 새로 설치해 자기 진행·승인 권위를 SAGE에 주지 않는다.

이것은 기존 [엔진 PDCA 권위 경계](</Users/sejon/project/obsidian/sejon_second_brain/wiki/SAGE - 엔진 개발 비도그푸딩 공통 에이전트 가이드 요구사항 (26.08.26).md:139>)와 일치한다. SAGE CLI/hook는 격리 consumer에서 제품 시험으로 실행할 수 있다. 05는 독립 세션의 렌즈별 finding·반박·처분·수정 확인을 남기고, 일반 테스트와 필요한 CI 증거로 판단한다. 앞선 설계 리뷰 3회와 이번 실현성 검토를 구현 후 L3 리뷰로 재집계하지 않는다.

현재 위치는 **02 설계 전 실현성 점검**이다. 00~06 정식 문서를 작성/통과시켰거나 03에 진입했다고 주장하지 않는다.

## 7. 설계 확정 및 착수 조건

1. Codex 선택 UI를 포함한 기존 필수 호출 경로에서 실제 선택 자산과 본문 전달을 결합할 수단을 확보한다. 기존 훅 입력만으로 복원하는 안은 폐기한다.
2. 그 수단에 따라 최초 호출·중첩·압축·재개·root 변경의 최소 상태와 수명을 다시 정한다. 내부 contributor가 외부 설치 가능하다는 가정이나 자발적 영수증 명령으로 대체하지 않는다.
3. Claude의 실패 처리 보장을 실제 지원하는 경계로 고친다. 오류 후 제품 동작 차단과 요청 송신 차단의 차이를 명시하고 검증한다.
4. Fast 자격을 열기 위한 최소 독립 floor와 선택 출처를 정하고 네 슬롯에 대해 적대적으로 검증한다.
5. 선택된 새 전달 방식의 실제 압축/예산/격리 시험을 실행한 뒤 설계와 공수를 확정한다.

기존 호출을 유지하려면 추가 호스트 연동 수단의 근거가 필요하다. 별도 런처/프록시/호스트 수정은 사용법·운영 부담·수정 범위를 크게 바꾸므로 기존의 8~14인일 추정에 임의로 포함하지 않는다. 전역 지원 제외·개인 물리 렌더·수동 재호출을 사용자 결정 없이 채택하지 않는다.

**착수 조건이 아직 충족되지 않아 제품 코드는 변경하지 않았다.** 기존 8~14인일은 현 방식이 최소 연결로 성립한다는 조건부 추정이었으며, 현재 결과 이후의 개발 약속이나 확정 공수로 사용하지 않는다.

## 8. 원자료

- [probe 요약 JSON](/Users/sejon/project/sage_project_worktree/overlay-design-preflight-k73xh3f3/probe-summary.json)
- [점검 스크립트](/Users/sejon/project/sage_project_worktree/overlay-design-preflight-k73xh3f3/probe.py)
- [Codex 선택 UI 훅 입력](/Users/sejon/project/sage_project_worktree/overlay-design-preflight-k73xh3f3/codex-ui-structured/hooks.jsonl)
- [Codex 선택 UI app-server 이벤트](/Users/sejon/project/sage_project_worktree/overlay-design-preflight-k73xh3f3/codex-ui-structured/app-events.json)
- [Fast 선택 출처 점검 결과](/Users/sejon/project/sage_project_worktree/overlay-design-preflight-k73xh3f3/fast-provenance-result.json)
- [원자료 SHA-256 목록](/Users/sejon/project/sage_project_worktree/overlay-design-preflight-k73xh3f3/sha256-manifest.json)

공식 참고 문서는 [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Claude hooks](https://code.claude.com/docs/en/hooks), [Claude skill 수명주기](https://code.claude.com/docs/en/skills#skill-content-lifecycle)다. 문서상의 기능 설명과 위 로컬 버전의 관측 결과를 분리한다.
