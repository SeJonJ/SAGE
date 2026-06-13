# docs/sage_harness — 자산 intent SSOT

SAGE 자산(hook/agent/skill)의 **의도(intent) 단일 진실원**. `.claude/.codex` 산출물은 여기서
생성되는 generated artifact이며 **직접수정 금지(write guard로 block)**.

## 레이아웃

```
docs/sage_harness/
├── .manifest.json          # spec_hash / render_hash(target별) / claims_hash / conformance 추적
├── hooks/{id}.md           # hook 정책·등록·테스트 명세 (알고리즘은 scripts/sage_harness/hooks/{id}.sh)
├── agents/{id}.md          # agent intent + advisory_scope (사람 수기 최소 단위)
├── agents/{id}.claims.yml  # 자동도출 claims (reverse_extract 생성 — 사람 intent와 분리)
└── skills/{id}.md          # skill intent + when_to_use + procedure
```

## 원칙 (최종검증 노트)

- 사람 수기 최소 = `intent + advisory_scope`. claims/manifest는 자동.
- hook 단일소스 = spec md(정책/등록/테스트) + 정본 알고리즘. form=`core_adapter`(대부분: `{id}_core.py` pure core
  + `adapters/{claude,codex}/{id}.sh`) / `native`(write-guard: 단일 `{id}.sh`).
- enforcement는 hook 전용. agent/skill은 advisory_scope만.
- 수정은 항상 여기(spec)부터 → `sage generate`. 산출물 직접수정은 block → `sage absorb`.
- 승인은 `auto_approve_safe_default`(conformance/hash PASS면 자동, 예외만 사람).

## claims (자동도출)

`.claude`/`.codex` 두 산출물의 **typed claim 교집합** = required, 명시 부정문 + AGENT_GUIDE 경계
참조 = forbidden, 차집합 분류 = runtime_delta_allowlist.
confidence: `high`(양쪽) / `source_supported`(권위출처) / `runtime_allowed`(allowlist) / `unresolved`(사람).
conformance PASS/FAIL은 deterministic checker만 (LLM judge 금지).
