# SAGE — System for Agentic Governance & Engineering

ChatForYou의 AI 하네스(PDCA 워크플로우, 팀 오케스트레이션, hook, cross-model 검토)를
**런타임 선택형(claude | codex) 재사용 프레임워크**로 추출한 standalone 프로젝트.

> 설계 SSOT: Obsidian vault `TECH - SAGE 통합 마스터 설계` + `TECH - SAGE 자산관리 사이클 최종검증 (2026-06-12)`
> + `TECH - SAGE CORE/OPTION 설치 리소스 카탈로그`. 본 레포는 그 설계의 **구현체**다.

## 핵심 모델 (요약)

- **host_runtime**: 설치 시 `claude` 또는 `codex` 택1. Claude 특권화 금지.
- **CORE(항상) + OPTION(opt-in)**: cross_model / codegraph / obsidian.
- **spec-SSOT**: `docs/sage_harness/{hooks,agents,skills}/{id}.md`가 의도(intent) SSOT.
  `.claude/.codex` 산출물은 generated artifact (직접수정 block).
- **hook 단일소스**: spec md(정책/등록/테스트) + 정본 알고리즘. 형태(form) 2종:
  `core_adapter`(`{id}_core.py` pure core + 런타임 adapter — 대부분의 hook) / `native`(단일 `{id}.sh` — write-guard).
- **자동도출 claims**: `{id}.claims.yml`(reverse_extract 자동). 사람 수기 최소 = `intent + advisory_scope`.
- **승인 UX**: `auto_approve_safe_default` — conformance/hash PASS면 자동, 사람은 예외만.

## 디렉토리

```
sage/                      # sage CLI (Python)
docs/sage_harness/         # 자산 intent SSOT (사람이 쓰는 원천) + .manifest.json
scripts/sage_harness/hooks # hook 정본 알고리즘 (canonical executable)
templates/                 # profile/spec/claims 템플릿
schema/                    # manifest 등 JSON Schema
```

## CLI (골격 — v1 진행 중)

```
sage install               # host 택1 + 빈 스키마 profile + framework 배치
sage generate --kind {hook|agent|skill} --id X [--write]   # 산출물 생성
sage validate [--check]    # 스키마 · drift · staleness 검사
sage absorb --kind X --id Y [--from-blocked-diff]          # 직접수정 → spec patch 제안
sage doctor                # 옵션 의존성 확인 + degrade 안내
sage change "자연어 의도"   # (v1.1) 최소 라우터
```

## v1 구현 순서 (최종검증 §5)

1. ~~문구 정리~~ (설계 wiki 반영 완료)
2. **`.manifest.json` 스키마 확정** ← 현재 스캐폴드 단계
3. generated-artifact write guard
4. hook 5종 reverse_extract (spec + canonical + adapter 분리)
5. hook validate 폐루프
6. agent/skill reverse_extract (claims 자동도출)
7. agent/skill render + conformance lint
8. 승인 UX (safe 자동승인 / 예외만 사람)
9. `sage change` 최소 라우터
10. codex-host opposite reviewer (fallback으로 닫기)

## 상태 (v1 10/10 steps 완료)

- **구현됨**: `validate`(staleness+regression), `review`(auto_approve_safe_default), `change`(라우터), `doctor`(옵션의존성+reviewer fallback).
  hook 5종 reverse_extract(core+adapter), agent claims 자동도출(backend-expert 파일럿), conformance lint, write-guard.
- **stub(미구현)**: `install`, `generate`(render는 interpretive=런타임 AI 영역), `absorb`. 호출 시 exit 2 + 예정동작 안내.
- 검증: 전체 테스트 PASS (Codex 다회 감사 반영). 자세한 진척: vault `TECH - SAGE 구현 진행 로그`.
