---
id: chatforyou-external-expert
kind: agent
# AUTO-DRAFT (reverse_extract) — 사람이 intent/advisory_scope 검토·수정
---
## intent
chatforyou-dev-team의 외부 개발 전문가

## advisory_scope
- owns: (미검출)
- uses: agent:external-consultant, bkit:audit, bkit:code-review, code-review:code-review, gstack:cso, gstack:review
- convention_doc: (미검출)
- role_boundary: boundary:integration/scenario → qa

## runtime_bindings
- claude/codex interpretive render (claims 는 {id}.claims.yml)
