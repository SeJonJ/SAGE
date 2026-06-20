# SAGE — System for Agentic Governance & Engineering

[![CI](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml/badge.svg)](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sage-harness)](https://pypi.org/project/sage-harness/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/sage-harness/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**AI 코딩 에이전트를 위한 거버넌스 하네스.** 자산마다 spec 파일 하나 — SAGE가 런타임 설정을 생성하고, drift를 검증하고, hook이 실행 시점에 위반을 차단합니다. Claude Code와 Codex 양쪽에서 동작합니다.

---

## 왜 SAGE인가

AI 에이전트는 빠르지만 규칙을 조용히 어깁니다:

- plan 문서 없이 고위험 파일을 수정한다
- PDCA 단계를 건너뛴다
- 생성된 산출물을 손으로 덮어쓴다
- 자기 코드를 자기 모델로 리뷰한다 (단일 모델 편향)

보통은 사람이 매번 잔소리하거나, 프로젝트마다 `.claude/`·`.codex/` 설정을 손으로 관리합니다. SAGE는 그 두 가지를 **spec-SSOT 폐루프**로 대체합니다.

---

## 빠른 시작 (30초)

```bash
pip install sage-harness

cd your-project
sage install          # 런타임 선택: claude 또는 codex
                      # hook·에이전트 spec·AGENT_GUIDE·manifest 자동 배치

sage generate         # spec md → .claude/.codex 산출물 + manifest 스탬프
sage validate         # drift · staleness · conformance 검사 (읽기 전용)
```

끝입니다. 이제 AI 에이전트는 강제력 있는 규칙 위에서 동작합니다.

---

## 동작 원리

```
사람이 의도를 쓴다        generate           런타임에 배치           validate / hook 게이트
docs/.../hooks/{id}.md  ──────────►  .claude/hooks/  ──────────►  위반 시 BLOCK
docs/.../agents/{id}.md             .codex/agents/               drift 시 validate FAIL
docs/.../mcps/{id}.md               .mcp.json                           │
        ▲                           manifest 스탬프                      │
        └──────────────  absorb (직접수정 → spec patch 제안) ─────────────┘
```

핵심은 **폐루프**입니다 — spec에서 산출물을 만들고(generate), 산출물이 spec과 어긋나면 잡아냅니다(validate), 산출물을 직접 수정하면 차단하고(write-guard), 비상 수정분은 다시 spec으로 흡수 제안합니다(absorb).

엔진 자체에는 **도메인 값이 0개**입니다 — 스택·위험 경로·PDCA 키워드는 전부 `sage/project-profile.yaml`에서 주입됩니다. 프로필만 바꾸면 같은 엔진이 다른 스택을 거버넌스합니다.

---

## 자산 종류 4종

| kind | 생성 성격 | SSOT | 산출물 |
|---|---|---|---|
| `hook` | 결정론 (순수 함수) | `docs/sage_harness/hooks/{id}.md` + `{id}_core.py` | `settings.json` / `hooks.json` + 런타임 shim |
| `agent` | interpretive (AI 렌더) | `docs/sage_harness/agents/{id}.md` + `{id}.claims.yml` | `.claude/agents/` / `.codex/agents/` |
| `skill` | interpretive (AI 렌더) | `docs/sage_harness/skills/{id}.md` + `{id}.claims.yml` | `.claude/skills/` / `.codex/skills/` |
| `mcp` | 결정론 (선언 데이터 직렬화) | `docs/sage_harness/mcps/{id}.md` (frontmatter payload) | `.mcp.json` (claude) · `.codex/config.toml` managed-block (codex) |

> **MCP 거버넌스**: 시크릿은 env 변수명만 허용 (`${VAR}` placeholder). 리터럴 시크릿 값이 spec에 있으면 generate 전 FAIL (fail-closed). `.mcp.json`은 SAGE 소유(write-guard), `config.toml`의 비-MCP 설정은 보존합니다.

---

## Hook 6종 (무엇을 강제하나)

| hook | 실행 시점 | 역할 |
|---|---|---|
| `pre-implementation-gate` | 파일 수정 전 (PreToolUse) | 위험도 L0–L3 분류 · plan 문서 · PDCA phase 강제. 미충족 시 BLOCK |
| `pre-phase4-checklist-gate` | 단계 전환 전 | PDCA 03→04 전환 시 체크리스트 완료 강제 |
| `capture-declared-risk` | 프롬프트 제출 (UserPromptSubmit) | 유저가 선언한 작업 위험레벨 포착 |
| `post-tool-logger` | 도구 실행 후 (PostToolUse) | 변경 분류를 세션 JSONL에 기록 |
| `stop-compliance-report` | 세션 종료 (Stop) | 컴플라이언스 리포트 생성 |
| `generated-artifact-write-guard` | 파일 수정 전 (native) | 생성 산출물 직접수정 차단 → spec으로 redirect |

Hook은 **순수 코어 + 어댑터** 구조입니다 — 정책 판정(`{id}_core.py`)은 I/O가 없는 순수 함수이고, 런타임별 I/O는 얇은 어댑터가 담당합니다. 같은 정책, 런타임 간 동일한 동작.

---

## CLI 참조

| 명령 | 역할 |
|---|---|
| `sage install` | 런타임 선택 (claude/codex) · CORE 하네스 배치 (hook·에이전트 spec·AGENT_GUIDE·manifest) |
| `sage generate` | spec md → 등록 산출물 + `{host}/hooks` shim + profile 컴파일 + manifest 스탬프 |
| `sage generate --kind roster` | `profile.components` → `implementer-<comp>` 에이전트 spec 결정론 scaffold |
| `sage generate --kind mcp` | `docs/sage_harness/mcps/{id}.md` → `.mcp.json` (claude) / `config.toml` managed-block (codex) |
| `sage validate` | drift · staleness · conformance · regression 검사. `--check` (빠름) / `--schema` (JSON Schema) |
| `sage review` | `auto_approve_safe_default` — 통과는 자동승인, 사람은 예외만 검토 |
| `sage absorb` | 직접수정 diff → spec patch 제안 (자동 반영 없음) |
| `sage doctor` | 옵션 의존성 점검 · 실행 환경 진단 · cross-model reviewer fallback 노출 |
| `sage change` | 자연어 의도 → generate/absorb 라우팅 안내 (v1) |
| `sage override` | 게이트 BLOCK 시한부 합법 우회 + append-only 감사 로그 (`.sage/override.jsonl`) |

---

## 프로필 예시

```yaml
# sage/project-profile.yaml — 도메인 값은 전부 여기, 엔진에는 0개
project: { name: "acme", prefix: "acme" }
risk:
  l1_path_globs: ["*frontend/*.js"]           # 저위험 (UI)
  l2_path_globs: ["*backend/*.java"]          # 소스 (build+test+lint 필요)
  l3_filename_globs: ["*payment*", "*auth*"]  # 고위험 (plan + 리뷰 필수)
  l3_content_keywords: ["encrypt", "PrivateKey", "chargeCard"]
  plan_glob: "plan_docs/**/*.md"
components: [backend, frontend]               # → sage generate --kind roster
cross_model:
  enabled: true
  opposite_runtime: codex                     # phase-05 리뷰를 codex로 실행
```

`cross_model.opposite_runtime: codex` 설정 시, 단일 모델이 놓친 P1 이슈를 codex가 실제로 적발한 사례가 있습니다 (weatherapp Tier 2 검증).

---

## 설치

**PyPI (권장):**

```bash
pip install sage-harness
```

**JSON Schema 검증 포함:**

```bash
pip install "sage-harness[schema]"
```

**소스에서 설치 (editable):**

```bash
git clone https://github.com/SeJonJ/SAGE.git
cd SAGE
pip install -e .
```

요구사항: Python 3.10+, bash, git.

---

## 새 버전 배포

태그를 push하면 [publish workflow](.github/workflows/publish.yml)가 PyPI에 자동 배포합니다:

```bash
git tag v0.2.0
git push origin v0.2.0
```

> 선행 조건: PyPI에서 [Trusted Publisher](https://docs.pypi.org/trusted-publishers/) 등록 (Repository: `SeJonJ/SAGE`, Workflow: `publish.yml`, Environment: `release`).

---

## 이런 분께 맞습니다

**아래에 해당하면 SAGE가 맞습니다:**

- Claude Code 또는 Codex로 실무 작업 중이고, 에이전트가 규칙을 지키도록 강제하고 싶다
- 프로젝트마다 `.claude/`·`.codex/` 설정을 손으로 다시 쓰는 게 지쳤다
- Claude + Codex 교차 리뷰(cross-model review) 구조를 갖추고 싶다
- CI에서 검증 가능한 spec 기반 하네스가 필요하다

**아래에 해당하면 맞지 않습니다:**

- 간단한 프롬프트 팁이 필요한 경우 — SAGE는 프레임워크이지 스니펫이 아닙니다

---

## 라이선스

MIT — [LICENSE](LICENSE) 참조.
