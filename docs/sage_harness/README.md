# docs/sage_harness — 자산 intent SSOT

SAGE 자산(hook/agent/skill)의 **의도(intent) 단일 진실원**. `.claude/.codex` 산출물은 여기서
생성되는 generated artifact이며 **직접수정 금지(write guard로 block)**.
예외: hand-shipped CORE 부트스트랩 렌더는 spec→generate 산출물이 아니라 write guard 면제 — 직접편집 허용.
host 택1이라 호스트별 위치가 다름: claude=repo `.claude/skills/{sage-init,sage-pdca-start,sage-team,sage-review,sage-asset,sage-profile-modify}` +
`.claude/agents/{CORE 6인}`; codex=전역 `$CODEX_HOME/skills/{...}`(repo 아님, 가드 무관) + repo
`.codex/agents/{CORE 6인}`(by-name 면제). (AGENT_GUIDE.md 부트스트랩 절 참조.)

> [!important] 프레임워크 ↔ 인스턴스 경계 (제약 #2: SAGE 독립)
> **이 레포는 프레임워크(엔진 + CORE)만 담는다 — 특정 소비 프로젝트 인스턴스는 두지 않는다.**
> 그래서 `agents/`·`skills/` 는 프레임워크 레포에선 비어 있고(`.gitkeep`), `hooks/` 만 CORE 6종 spec 을 담는다.
> - **프레임워크(재사용)**: `sage/` CLI, `scripts/sage_harness/*.py`(엔진: reverse_extract_agent, conformance),
>   hook `*_core.py` + adapters(정본) + `strategies/**`·`policies/**`, `schema/`, `templates/`(CORE 중립 roster/framework/hook spec).
>   엔진은 도메인값 0(검증: config 없으면 owned_paths 0 / 설치 트리 스택 토큰 0).
> - **인스턴스(소비 프로젝트)**: `sage install` 로 CORE 를 받은 뒤 자기 `project-profile.yaml` + `ExtractConfig` 로
>   agents/skills/claims 를 채운다. 인스턴스 자산은 **소비 프로젝트 레포에** 산다(이 프레임워크 레포엔 없음).
> - **예시**: 실제 매핑 worked example 은 루트 `README.md` 참조. 테스트/문서용 generic 예시는
>   `scripts/sage_harness/extract_config_example.py` + `fixtures/**/example.profile.json`.
> - **브랜드/접두**: `project.prefix`(기본 `sage`) — `sage install --prefix <brand>` 로 설정.

## 레이아웃

```
docs/sage_harness/
├── .manifest.json          # spec_hash / render_hash(target별) / claims_hash / conformance 추적
├── hooks/{id}.md           # hook 정책·등록·테스트 명세 (알고리즘: core_adapter={id}_core.py / native={id}.sh)
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
