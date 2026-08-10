# 9.5 — F-5 게이트 강화: 06←05 가 loop_audit 증거도 검사

## 배경 (F-5)

4차 weatherapp 평가: Phase 05 가 단발 리뷰로 돌고 `.sage/loop_audit.jsonl` 이 한 줄도 안 찍혔는데도
06 작성이 통과했다. 원인 — `pre_implementation_gate_core._report_gate` 는 **05 문서의 `APPROVED`
마커만** 검사한다(`pre_implementation_gate_core.py:171-195`). 적대적 루프가 실제로 돌았는지(audit
기록)는 안 본다. `/sage-team`(9단계)은 절차로 강제하지만 SOFT-ENFORCED — host 가 `/sage-team` 을
안 쓰고 손으로 05+APPROVED 를 쓰면 여전히 통과. 9.5 는 이 결정론 백스톱을 만든다.

## 목표

06←05 게이트가 `APPROVED` 마커 **AND** "리뷰 루프가 실제로 돌아 수렴했다"는 audit 증거를 함께 검사.
**advisory-first**: 기본은 WARN(측정), profile 로 enforce(BLOCK) 전환. 7.8 `termination_enforce` 와 동일 롤아웃.

## 2층 불변식 준수 (핵심 제약)

`pre_implementation_gate_core` 는 **fs/time 의존 0**(순수 core, 주입만). 따라서:
- **adapter**(`runtime/hook_runtime.py` + `io_*`)가 `.sage/loop_audit.jsonl` 을 `loop_audit.py` 로 읽어
  요약을 `snapshot["loop_audit"]` 로 **주입**한다(phase_docs·strategy_result 와 동일 패턴).
- **core** 는 주입된 요약만으로 결정론 판정. core 에서 파일/시계 접근 금지.

**run_id 바인딩**(codex 설계 R1-P1): 프로젝트-전역 검사(아무 APPROVED run 하나면 통과)는 stale run 으로
오통과하고, 전역 open/integrity 블로커는 무관 cycle 을 오차단한다. 대신 **이 cycle 의 05 문서가 자기 loop
run_id 를 적고**, 게이트는 **그 run_id 만** 검사한다. 주입은 run_id→상태 맵(전역 블로커 아님):
```
snapshot["loop_audit"] = {
  "runs": { "<run_id>": {"closed": bool, "result": "APPROVED"|"BLOCKED"|...|None} },
  "has_any_records": bool,        # 진단용 — "audit 자체가 없음" vs "run 이 미닫힘/비승인" 구분
}
```
(`loop_audit.py` 에 `audit_summary(root)` 헬퍼 — `runs`/`close_of` 재사용. 전역 integrity 는 블로커가
아니라 진단 보조로만; 판정은 named run 상태로만.)

**05 문서 ↔ run 결합**: `/sage-review` 가 05 문서에 `Loop-Run: <run_id>` 라인을 기록한다(이미 resume
상태머신이 05 의 run_id 를 요구 — 9단계 `/sage-team` 와 동일 가정). 9.5 는 그 마커 포맷을 확정하고
sage-review/sage-team 스킬에 명시한다.

## 게이트 규칙 (advisory-first, run_id 바인딩)

새 flag: `pdca.review_loop.report_gate_enforce: off | advisory | enforce` (기본 `advisory`).
(codex R1-P2: 06 report 게이트 규칙이므로 review_loop 하위에 둔다 — "05 승인 규칙"으로 오해될 이름 회피.)
`_report_gate` 가 06 작성을 감지했을 때, 기존 마커 검사에 더해:

- **off** → 현행 동작(마커만). 하위호환.
- **review_loop.enabled == false** → 루프 미기대 → audit 검사 skip(마커만). 루프 안 켠 프로젝트 오차단 방지.
- **review_loop.enabled == true** 이고 flag ∈ {advisory, enforce}:
  - **단일 cycle 05 문서 선택**(codex R2-P1 — 리스트에서 아무 05 가 아니라 cycle-관련 하나만):
    기존 `_doc_match(approve_phase docs, event)`(ticket→recent) 규칙으로 06 write 이벤트에 대응하는
    05 문서 1개를 고른다. **APPROVED 마커와 `Loop-Run` 을 반드시 그 동일 문서에서** 읽는다(서로 다른
    05 문서에서 긁어 모으지 않음 — stale 결합 차단).
  - 그 문서에서 `Loop-Run: <run_id>` 추출 → `runs[run_id]` 검사.
  - 통과 조건: cycle 05 문서가 선택되고, 거기 APPROVED 마커 존재, `Loop-Run` 추출되고
    `runs[run_id].closed AND result == "APPROVED"`.
  - 위반 분기(진단 메시지 구분): ⓪ cycle 05 문서 미선택(`_doc_match` 빈값) ⓞ **선택된 그 05 문서에
    APPROVED 마커 없음**(다른 05 에만 있어도 cycle-bound 검사는 fail — codex R3-P1) ① 그 문서에 run_id 없음
    ② run_id 가 audit 에 없음 ③ run open(미닫힘) ④ closed 인데 result ≠ APPROVED. `has_any_records`
    로 "audit 전무" 구분. **구현 주의: APPROVED 와 Loop-Run 을 반드시 selected 05 문서 한 곳에서 함께
    읽고 둘 중 하나라도 없으면 fail — `any-doc marker + selected-doc run_id` 로 느슨하게 짜지 말 것.**
  - `advisory` → **WARN(exit 0, 진행)**; `enforce` → **BLOCK(exit 2)**.
  - 마커(APPROVED) 단독 검사는 항상 별개로 유지(기존 `any` 검사). 마커 전무면 현행대로 BLOCK(flag 무관).
    9.5 audit 검사는 그 위에 cycle-bound 요건을 더한다.

## 바인딩 한계 (run_id 결합 후 — 축소됨)

run_id 결합으로 "stale 무관 run 오통과"는 해소(05 가 적은 그 run 만 봄). 남은 한계: review_loop.enabled=true
인데 어떤 cycle 이 L1-only 라 루프가 정당히 안 돌고 05 가 단발(run_id 없음)이면 enforce 가 그 cycle 의 06 을
막을 수 있음.
- 대응: **기본 advisory**(측정·관찰 후 enforce). enforce 는 "모든 05 가 Loop A 를 도는 프로젝트"에서만
  권장 — flag 주석 + `sage validate`/`doctor` 경고로 명시(codex R1-P2/Q5): "enforce 는 모든 Phase 05 가
  루프를 돌 때만 안전".

## 테스트 증거 검사 — 범위 밖(후속)

"테스트 실제 통과" 증거 검사는 게이트가 verify 결과를 결정론적으로 확인할 방법이 모호(03 문서 파싱은
취약)하여 9.5 범위 밖. 9.5 는 loop_audit 증거에 집중(4차의 핵심 누락). 테스트 증거는 별도 단계.

## 산출물

- `loop_audit.py`: `audit_summary(root)` 헬퍼 — `{runs: {run_id: {closed, result}}, has_any_records}`.
- adapter(`hook_runtime.build_snapshot`): pre-implementation-gate 처리 시 loop_audit summary 를 snapshot 에
  주입(io_* 아닌 공유 build_snapshot — codex R1-Q1).
- `pre_implementation_gate_core.py`: `_report_gate`(또는 인접 함수)에 run_id 추출 + named-run 검사 + 새
  message_key(`block_report_without_audit` / `warn_report_without_audit`, 4개 위반 분기 사유).
- profile/schema/template: `pdca.review_loop.report_gate_enforce: off|advisory|enforce`(기본 advisory) 추가.
  `profile_validate.py` `_review_loop_issues` 에 enum 검증(+ enforce 시 "모든 05 가 루프 돌 때만 안전" 경고).
- `/sage-review` + `/sage-team` 스킬: 05 문서에 `Loop-Run: <run_id>` 기록 명시.
- output adapter(io_claude/io_codex): 새 message_key 메시지.
- 테스트: core decide 분기(off/advisory/enforce × 통과/4개 위반/루프비활성/마커없음) + audit_summary 헬퍼
  + adapter 주입 + profile_validate enum + e2e.

## codex 설계 리뷰 질문

1. 2층 불변식 준수 맞나 — audit 읽기를 adapter 주입으로, core 는 순수 유지하는 구조가 옳은가?
2. 주입 요약 3필드로 충분한가, 더 필요한가(예: 마지막 close 의 reason)?
3. 바인딩 한계(프로젝트 단위 검사 + advisory 기본)가 수용 가능한가, 아니면 cycle 바인딩을 v1 에 넣어야 하나?
4. flag 위치/이름 `pdca.approve_requires_audit` 가 적절한가(vs review_loop 하위)?
5. enforce 오차단 위험(L1-only + enabled=true) 완화가 advisory 기본으로 충분한가?
