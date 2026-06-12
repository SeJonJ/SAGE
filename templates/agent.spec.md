---
id: ""            # 예: backend
kind: agent
---
## intent
한 문장으로 이 에이전트가 무엇을 책임지는지. (사람이 쓰는 핵심 — 최소 수기 단위)

## advisory_scope
- owns: 담당 경로
- role_boundary: 담당하지 않는 것 / 인계 대상
- uses_skills: []
- convention_doc: 준수 문서

## runtime_bindings
- model: opus | sonnet
# claims / runtime_delta_allowlist 는 reverse_extract가 {id}.claims.yml 로 자동 도출.

## drift_checks
- conformance: required/forbidden claim presence (머신체크, LLM judge 금지)
