---
id: stop-compliance-report
kind: hook
runtime_bindings:
  claude: { event: Stop, matcher: "", timeout: 15 }
  codex: { event: Stop, matcher: "", timeout: 15 }
---
## intent
세션 종료(Stop) 시 session-{today}.jsonl 을 집계해 compliance 리포트(compliance-{today}.md)를 생성한다.
활동요약 + gate compliance(백엔드+plan / L3 패턴 / convention 안내) + 수정파일 목록. 항상 exit 0(차단 안 함).

## runtime_bindings
- claude: { event: Stop, input: .claude/logs/session-{today}.jsonl, output: 파일쓰기 + report path(plain) }
- codex:  { event: Stop, input: .codex/logs/session-{today}.jsonl, output: 파일쓰기 + hookSpecificOutput }
- exit_code: 항상 0

## canonical (부분추출 — 공유 집계만)
scripts/sage_harness/hooks/stop_compliance_report_core.py
- `decide(event, profile, snapshot) -> report_model`  (pure)
- `render_markdown(report_model) -> str`               (pure)
- snapshot = { entries[], today, branch, runtime } (adapter 가 JSONL 읽어 주입)
- report_model.sections = { header, activity_summary, gate_compliance{issues[]}, modified_files[], policy_results[] }
- 공유 gate 3종: backend_without_plan(WARN) / l3_pattern_detected(NOTICE) / backend_convention_reminder(INFO)

## ⚠️ policy_delta — 병합 금지 (정책 모듈 보존)
Codex-only 정책 2개. canonical core 에 자동병합 안 함 → policies/ 보존, policy_results 확장슬롯에만 주입 가능:
- policies/output_contract_check.py: **Codex-only**(transcript 결합). manifest.unresolved "promote_output_contract_semantics?"
- policies/knowledge_capture.py: **OPTION(knowledge_capture, obsidian)**. vault_path 비면 N/A. CORE 아님.

## profile_bound
- L3 패턴 단일소스 = **profile.risk.l3_filename_globs 재사용**('*' strip + lower substring). pre-impl-gate 와 동일 소스(drift 방지),
  단 의미 다름(pre-impl=사전차단 / stop=사후감사). severity/behavior 는 비공유.

## reverse_extract 분류
- 공유 core: JSONL 집계, activity_summary, gate 3종, report_model, markdown 렌더
- token_adapter: 로그경로(.claude↔.codex)
- output_adapter: report path 출력 채널(plain vs hookSpecificOutput)
- profile_bound: L3 패턴(공유 소스)
- **policy_delta**: output_contract(Codex-only) + knowledge_capture(OPTION) — 보존만, 미병합

## tests
scripts/sage_harness/hooks/tests/test_stop_compliance_report.py (10 PASS)
- core(gate 3종/집계/빈로그/render) + 정책모듈 보존(output_contract/knowledge_capture) + adapter e2e(claude·codex)
