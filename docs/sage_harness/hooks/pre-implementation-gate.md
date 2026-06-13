---
id: pre-implementation-gate
kind: hook
---
## intent
소스/설정 변경 전 위험도(L0~L3)를 분류해 게이트를 적용한다. Desktop 직접수정 하드블록,
L3(WebRTC/Kurento) + plan 없음 하드블록, L3 review 확인, L2 plan 확인.

## runtime_bindings
- claude: { event: PreToolUse, matcher: "Write|Edit|MultiEdit", input: file_path + content/new_string/edits }
- codex:  { event: PreToolUse, matcher: "apply_patch", input: command 본문 다중파일+content }
- output: block=메시지+exit2 (claude stdout / codex stderr), warn·ok=exit0 (codex hookSpecificOutput)

## canonical (부분추출 — IO-bound gate, 2단계 pure core)
scripts/sage_harness/hooks/pre_implementation_gate_core.py
- `classify_risk(event, profile) -> {risk, reason, is_l3_filename, declared_l3, file_short}`
- `decide(event, profile, snapshot, strategy_result) -> {status, exit_code, risk, message_key, safety_degraded?}`
- core 는 fs/time 의존 0. plan 후보 내용은 snapshot, L3 review 매칭은 strategy_result(주입).

## ⚠️ algorithm_delta — 병합 금지 (unresolved 전략 슬롯)
"L3 review doc 매칭"이 런타임마다 다른 알고리즘 → **둘 다 보존, canonical 미선택**:
- scripts/sage_harness/hooks/strategies/pre_implementation_gate/claude_grep_first.py (grep-first)
- scripts/sage_harness/hooks/strategies/pre_implementation_gate/codex_feature_signal.py (토큰 스코어링)
- **find_l3_review(signals, snapshot) -> {found, path}** 공통 인터페이스. v1 미선택(strategy_result=None).
- 안전 합의(G1): 미선택 시 L3 review 확인 불가 → **BLOCK + override-required + safety_degraded:true**
  (WARN degrade 안 함 — drift 안 가리고 안전 바닥 유지). 사람이 canonical 선택하면 원본 동작(found→ok/notfound→warn) 복원.

## profile_bound (risk trigger = 프로젝트 선언값, §7 I2~I7)
profile.risk: { desktop_block_glob, l0_pass_globs, l3_filename_globs, l2_path_globs, l1_path_globs,
                l3_content_keywords, l2_content_keywords, plan_glob }
- canonical 매칭 = **case-insensitive**(G2, 더 많은 L3 포착 = 안전). 키워드/파일패턴 lower 비교.

## reverse_extract 분류
- 공유 core: 위험분류(경로/내용/declared), Desktop 블록, plan 존재 게이트, L2/L3 판정 구조
- structural_io_adapter: file_path vs apply_patch 다중파일+content
- output_adapter: 채널/메시지
- profile_bound: risk trigger 전부
- **algorithm_delta**: L3 review 매칭 (전략 슬롯, 병합금지)
- minor drift: content keyword case (Claude 고정대소문자 vs Codex (?i)) → canonical case-insensitive

## tests
scripts/sage_harness/hooks/tests/test_pre_implementation_gate.py (16 PASS)
- classify(L0~L3/escalation/desktop/declared/case-insensitive) + decide(8분기) + 전략 후보 2종 + adapter(L3 block·L1 pass)
