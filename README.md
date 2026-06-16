# SAGE — System for Agentic Governance & Engineering

PDCA 워크플로우 · 팀 오케스트레이션 · hook 게이트 · cross-model 검토를
**런타임 선택형(claude | codex) 재사용 AI 하네스 프레임워크**로 제공하는 standalone 프로젝트.
(실제 운영 프로젝트의 손관리 `.claude/.codex` 자산에서 추출·일반화한 spec-SSOT 자산관리 사이클.)

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

## CLI

```
sage install               # host 택1 + CORE 하네스 배치(framework + CORE hook 정본/spec/어댑터 + roster agent + manifest)
sage generate --kind {hook|agent|skill} --id X [--write]   # hook 등록 산출물 + {host}/hooks shim + profile 컴파일 + manifest 스탬프
sage validate [--check]    # 스키마 · drift · staleness 검사
sage absorb --kind X --id Y [--from-blocked-diff]          # 직접수정 → spec patch 제안
sage doctor                # 옵션 의존성 확인 + degrade 안내
sage change "자연어 의도"   # (v1.1) 최소 라우터
```

## 브랜드 설정 (configurable, 기본 `sage`)

자산/문서 정체성 접두는 `project.prefix` — 기본값 `sage`, 설치 시 변경 가능:

```
sage install --host claude --prefix acme    # project.prefix = acme
```

`project.prefix` 는 `sage/project-profile.yaml` 에 기록되어 문서 제목·knowledge-capture 파일명 등에 쓰인다.
CORE roster agent 는 역할 기반 무접두(leader/implementer-a/implementer-b/qa/reviewer/convention-checker)로 **브랜드·스택 중립**이다(implementer-a/b 가 맡을 컴포넌트는 profile.team.core.*.owns 로 매핑).

## 예시: 프로젝트 적용 (worked example)

가상의 `backend/ + frontend/` 웹앱(고위험 도메인 = 결제/암호)에 SAGE 를 적용한다고 하자. 엔진은 이 도메인값을
전혀 모르며, 전부 profile/spec 에서 온다 — 다른 스택이면 profile 만 바꾸면 같은 엔진이 동작한다(독립).

1) `sage/project-profile.yaml` (발췌):

```yaml
project: { name: "acme", prefix: "acme" }
risk:
  l1_path_globs: ["*frontend/*.js", "*frontend/*.css"]      # 저위험(UI)
  l2_path_globs: ["*backend/*.java", "*backend/*.gradle"]   # 소스/설정(build+test+lint)
  l3_filename_globs: ["*payment*", "*crypto*", "*auth*"]    # 고위험 도메인(plan+리뷰 필수)
  l3_content_keywords: ["encrypt", "PrivateKey", "chargeCard"]
  desktop_block_glob: "*generated/*"                        # 동기화 산출물 직접수정 차단
  plan_glob: "plan_docs/**/*.md"
  l3_review_strategy: "codex_feature_signal"
file_type_map:
  - { glob: "backend/src/main/*", type: backend-main }
  - { glob: "frontend/static/*",  type: frontend-js }
verification:
  commands: { build: "./gradlew build", test: "./gradlew test", lint: "ktlint" }
```

2) agent spec — CORE 기본은 중립(`docs/sage_harness/agents/implementer-a.md`), 인스턴스가 컴포넌트(예: core) 할당 후 채운 예:

```markdown
---
id: implementer-a
kind: agent
---
## intent
할당된 컴포넌트(core)의 설계·구현·컴포넌트 단위테스트.
## advisory_scope
- owns: src/core
- role_boundary: 통합/HTTP/경계값 테스트는 qa 영역
- convention_doc: docs/core-conventions.md
```

3) `sage generate` 후 자동도출 `implementer-a.claims.yml` (발췌, reverse_extract):

```yaml
required_claims:
  - { type: owned_paths,    value: "src/core", confidence: high }
  - { type: convention_doc, value: "docs/core-conventions.md",  confidence: high }
forbidden_claims:
  - { type: safety_forbid,  value: "forbid:integration/http/boundary tests", confidence: high }
  - { inherited_forbidden_claims: "AGENT_GUIDE.non_negotiable_boundaries" }
```

> 테스트/문서용 generic 예시 config 는 `scripts/sage_harness/extract_config_example.py` +
> `fixtures/**/example.profile.json` 에 있다(프레임워크 레포엔 실제 인스턴스를 두지 않음).

## v1 구현 순서 (최종검증 §5 — 1~10 전부 완료 + install/generate 동작화)

1. ~~문구 정리~~ (설계 wiki 반영 완료)
2. ~~`.manifest.json` 스키마 확정~~ (jsonschema valid)
3. generated-artifact write guard
4. hook 5종 reverse_extract (spec + canonical + adapter 분리)
5. hook validate 폐루프
6. agent/skill reverse_extract (claims 자동도출)
7. agent/skill render + conformance lint
8. 승인 UX (safe 자동승인 / 예외만 사람)
9. `sage change` 최소 라우터
10. codex-host opposite reviewer (fallback으로 닫기)

## 상태 (CLI 7종 구현 + install→generate 동작 하네스)

- **CLI 7종 구현**: `install`(CORE 하네스 부트스트랩) · `generate`(hook 등록 + `{host}/hooks` shim + profile YAML→JSON + manifest 스탬프) ·
  `validate`(staleness+regression+conformance+`--schema`, 미스탬프=STALE) · `review`(auto_approve_safe_default, hook+agent+skill) ·
  `change`(자연어 라우터) · `doctor`(옵션의존성 + profile 로드 실패 구분) · `absorb`(직접수정→spec patch / hook 정본 divergence).
- **결정론 경계(정직)**: `generate` 의 **hook 만 결정론 생성**(등록+shim+profile 컴파일+스탬프). **agent/skill 은 interpretive**
  — spec+claims 는 `reverse_extract` 로 도출(결정론)하되 런타임 산출물(`.{claude,codex}/agents·skills/*.md`)은
  **런타임 AI 가 렌더**(generate 가 결정론 생성하지 않음, v1 의도적 제외). "완전 자동 자산 생성기" 아님.
- **install→generate 동작 검증(e2e)**: 빈 신규 프로젝트에 install → generate → hook 실행까지 확인.
  profile 없음=통과 / L2 WARN / L3·금지경로 BLOCK / 잘못된 YAML→generate fail-closed / 신규 install→validate STALE.
- **독립성(제약 #2)**: 레포 = 엔진 + CORE 만(특정 프로젝트 인스턴스 없음). 설치 트리 **특정 스택 토큰 0**(회귀 가드 테스트).
  소비 프로젝트 패턴은 `project-profile.yaml` + `ExtractConfig` 로만 주입. 테스트/문서용 generic 예시 =
  `extract_config_example.py`·`fixtures/**/example.profile.json`. 전략은 profile 확장형(`signals[generic_tokens/review_patterns]`).
- **검증**: writable 환경 전체 테스트 PASS, `validate --kind all --check` 종합 PASS, manifest 구조검증 `sage validate --schema`(jsonschema 설치 시 `pip install 'sage-harness[schema]'`) PASS, manifest unresolved 0(사람 결정 완료).
  Codex 다라운드 + 자가 다회 감사 반영(전문가 피드백으로 install/generate P0 2건 발견·수정 — 상세 vault `TECH - SAGE 구현 진행 로그`).
- **배포(정직)**: 현재 git clone / `pip install -e .`(editable) / sdist(레포 레이아웃) 기준. 리소스 경로는 `sage/_resources.py`
  (`$SAGE_RESOURCE_ROOT` override + repo fallback)로 해석. 순수 PyPI wheel 단독 배포는 dual-use 인 `scripts/sage_harness` 의
  패키지 이전(importlib.resources)이 필요 — **공개 전 과제**. `pyyaml` 은 generate(빌드) 의존성(hook 런타임은 의존성 0=JSON).
- **남은 범위**: Tier 2(2번째 프로젝트 실적용) / Tier 4(전체 SAGE Phase A~H) / Tier 5(원본 프로젝트 역적용).

## License

This project is licensed under the **Creative Commons Attribution‑NonCommercial 4.0 International (CC BY‑NC 4.0)**.

You may **share** and **adapt** the material for **non‑commercial** purposes only, provided you give appropriate credit, indicate if changes were made, and distribute any derivative works under the same non‑commercial license.

For the full license text, see: https://creativecommons.org/licenses/by-nc/4.0/

