---
id: pre-implementation-gate
kind: hook
runtime_bindings:
  claude: { event: PreToolUse, matcher: "Write|Edit|MultiEdit", timeout: 10 }
  codex: { event: PreToolUse, matcher: "apply_patch", timeout: 10 }
---
## intent
소스/설정 변경 전 위험도(L0~L3)를 분류해 게이트를 적용한다. 동기화 산출물/금지 경로 직접수정 하드블록,
L3(profile.risk 고위험 도메인) + plan 없음 하드블록, L3 review 확인, L2 plan 확인.

## runtime_bindings
- claude: { event: PreToolUse, matcher: "Write|Edit|MultiEdit", input: file_path + content/new_string/edits }
- codex:  { event: PreToolUse, matcher: "apply_patch", input: command 본문 다중파일+content }
- output: block=메시지+exit2 (claude stdout / codex stderr), warn·ok=exit0 (codex hookSpecificOutput)

## canonical (부분추출 — IO-bound gate, 2단계 pure core)
scripts/sage_harness/hooks/pre_implementation_gate_core.py
- `classify_risk(event, profile) -> {risk, reason, is_l3_filename, declared_l3, file_short}`
- `decide(event, profile, snapshot, strategy_result) -> {status, exit_code, risk, message_key, safety_degraded?}`
- core 는 fs/time 의존 0. plan 후보 내용은 snapshot, L3 review 매칭은 strategy_result(주입).

## algorithm_delta — 전략 슬롯 (사람 결정 완료 2026-06-13)
"L3 review doc 매칭"이 런타임마다 다른 알고리즘 → 둘 다 보존:
- scripts/sage_harness/hooks/strategies/pre_implementation_gate/claude_grep_first.py (grep-first)
- scripts/sage_harness/hooks/strategies/pre_implementation_gate/codex_feature_signal.py (토큰 스코어링)
- **find_l3_review(signals, snapshot) -> {found, path}** 공통 인터페이스.
- **canonical 결정: `codex_feature_signal`** (정교한 feature-signal 스코어링 채택, 사람 결정).
  profile.risk.l3_review_strategy 로 주입(독립 — 엔진 하드코딩 아님). adapter 가 CORE_DIR 의 전략 모듈 로드·실행.
  → L3 + plan 있음 + review 매칭 시 GATE OK, 매칭 실패 시 WARN. plan 없음은 여전히 hard block.
- 미선택(profile 에 strategy 없음) 시 = BLOCK + override-required + safety_degraded(안전 바닥, 다른 프로젝트 기본값).

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
  · **의도적 drift(audit P2)**: case-insensitive 는 원본보다 더 많은 L3 포착(안전 방향). 단 일반 문서/테스트에
    섞인 L3 키워드 문자열도 L3 로 올릴 수 있음. L0 문서(plan_docs/docs/*.md) pass 가 선행이라 문서 오탐은 제한됨.

## tests
scripts/sage_harness/hooks/tests/test_pre_implementation_gate.py (16 PASS)
- classify(L0~L3/escalation/desktop/declared/case-insensitive) + decide(8분기) + 전략 후보 2종 + adapter(L3 block·L1 pass)
