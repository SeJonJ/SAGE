# SAGE — System for Agentic Governance & Engineering

[![CI](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml/badge.svg)](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sage-harness)](https://pypi.org/project/sage-harness/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/sage-harness/)
[![License: CC BY-NC-SA 4.0](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey.svg)](LICENSE)

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
pipx install sage-harness

cd your-project
sage install --host codex --skill-scope project-local   # 또는 --skill-scope global
# Claude: sage install --host claude

# 최초 설정은 sage-init으로 공유 정책과 현재 머신의 로컬 capability를 작성합니다.
# 이미 공유 설정이 끝난 저장소의 팀원은 sage-init-local만 실행합니다.
# 자세한 절차: docs/agent/bootstrap-authoring.md

sage generate --kind hook --write   # spec → 설정 파일 생성 + manifest 스탬프
sage validate                       # drift · staleness · conformance 검사
```

끝입니다. 이제 AI 에이전트는 강제력 있는 규칙 위에서 동작합니다.

---

## 설치

SAGE는 `sage` 명령을 제공하는 CLI 도구이므로 `pipx` 설치를 권장합니다.

**PyPI CLI 설치 (권장):**

```bash
pipx install sage-harness
sage --help
```

`pipx`가 없다면 먼저 설치합니다:

| OS | pipx 설치 |
|---|---|
| macOS | `brew install pipx && pipx ensurepath` |
| Linux | `python3 -m pip install --user pipx && python3 -m pipx ensurepath` |
| Windows | `py -m pip install --user pipx` 후 `py -m pipx ensurepath` |

`ensurepath` 이후 새 터미널을 열거나 shell 설정을 다시 로드하세요.

**pip fallback:**

```bash
python3 -m pip install --user sage-harness
python3 -m sage --help
```

**JSON Schema 검증 포함:**

```bash
pipx install "sage-harness[schema]"
```

**소스에서 설치 (editable):**

```bash
git clone https://github.com/SeJonJ/SAGE.git
cd SAGE
python3 -m pip install -e .
```

요구사항: Python 3.10+, bash, git.

### Windows 사용 시

SAGE hook 어댑터는 `bash` + `python3`로 실행됩니다. **Git Bash 또는 WSL에서 실행**을 권장합니다.

```bash
# Git Bash 예시
pipx install sage-harness
export SAGE_PYTHON=python   # Windows는 python3 대신 python
sage doctor                 # bash/python 환경 확인
sage install --host claude
```

`sage doctor`에서 `bash : NOT FOUND`가 뜨면 Git Bash/WSL에서 다시 실행하세요.

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

**spec → 생성 → 검증 → 차단**이 폐루프입니다. 엔진에는 도메인 값이 0개입니다. 공유 스택·경로·규칙은 `sage/project-profile.yaml`, 개인 host/model/vault capability는 Git에서 제외되는 `sage/project-profile.local.yaml`에서 주입됩니다.

---

## SAGE가 막는 것

| SAGE 소유 (결정론) | 런타임 AI 실행 (판단) |
|---|---|
| hash 검증 · write-guard · 06←05 BLOCK · 루프 감사 무결성 · profile 설정 검증 | 코드 작성, 리뷰, 반박, rework, 루프 종료 판단, 회고 분석 |

- **드리프트 방어** — spec↔산출물 불일치는 `validate`가 잡습니다
- **직접수정 차단** — write-guard가 산출물 직접 수정을 막고 spec으로 redirect합니다
- **단일 모델 편향 방지** — cross-model 리뷰로 반대 런타임이 독립 리뷰합니다
- **침묵 비활성 방지** — profile 오타가 게이트를 조용히 끄는 것을 `sage validate`가 fail-closed로 적발합니다
- **도메인별 L0 예외** — 일반 이미지/문서는 L0로 두면서 `risk.domains[].path_globs`에 속한 자산은 해당 L1–L3 위험도로 승격합니다

판단(리뷰·분석)은 AI가, 경계(게이트·무결성)는 SAGE가 결정론으로 — 판단이 틀려도 게이트는 무너지지 않습니다. 2층 불변식·실패 정책(fail-open/closed)·신뢰 경계(막지 않는 것 포함)는 [ARCHITECTURE.md](docs/ARCHITECTURE.md)에 정리돼 있습니다.

---

## 리뷰 루프 (Loop A) + 회고 (Loop C)

Phase 05 리뷰를 수렴할 때까지 반복 실행하는 루프입니다 (`profile.pdca.review_loop.enabled`).

```
찾기(병렬 렌즈 + cross-model) → 반박(false-positive 필터) → 분류 → 수정 → 종료(수렴/dry/예산)
```

- **`sage-review` 스킬**이 루프 진행과 종료 판단을 담당하고, **`sage review-loop`** CLI가 라운드별 결과를 `.sage/loop_audit.jsonl`에 기록하며 시퀀스 무결성을 검증합니다. 이 검사는 수기 기록·순서 뒤바뀜·누락 같은 게으른 우회를 잡는 sanity 검사이지 위변조 내성(해시체인)이 아닙니다 — 신뢰 경계는 [ARCHITECTURE.md](docs/ARCHITECTURE.md) 참조.
- cross-model reviewer에 도달하지 못하면 Phase 05는 `BLOCKED`로 표면화됩니다.
- 루프 종료 backstop은 report←approve(06←05 APPROVED) — 루프는 이를 우회하지 않습니다.
- **`sage retro`** (Loop C)는 사이클 완료 후 놓친 패턴의 증거를 모아 distiller 프롬프트와 함께 제시합니다 (자동 반영 없음). 노트 본문을 채우는 것은 host AI 의 몫이라 빈 템플릿으로 나가며, `sage retro --check <노트>` 가 실제로 채워졌는지 결정론적으로 검산합니다.

Obsidian을 쓰면 `--vault`로 루프 대시보드와 회고 노트를 vault에 남길 수 있습니다.

---

## 자산 종류 4종

| kind | SSOT | 산출물 |
|---|---|---|
| `hook` | `docs/sage_harness/hooks/{id}.md` | `settings.json` / `hooks.json` + 런타임 shim |
| `agent` | `docs/sage_harness/agents/{id}.md` | `.claude/agents/` / `.codex/agents/` |
| `skill` | `docs/sage_harness/skills/{id}.md` | `.claude/skills/` / `.codex/skills/` |
| `mcp` | `docs/sage_harness/mcps/{id}.md` | `.mcp.json` (claude) · `.codex/config.toml` (codex) |

MCP 자산에서 시크릿은 `${VAR}` 형식(환경변수명)만 허용합니다. 실제 값이 spec에 있으면 생성 전 오류가 납니다.

> **CORE 부트스트랩 자산** (`sage install`이 배포하는 스킬·에이전트)은 위 경로와 별개입니다. Claude는 repo `.claude/`에 설치하고, Codex CORE skill은 `--skill-scope global|project-local`로 `$CODEX_HOME/skills` 또는 repo `.codex/skills`를 명시적으로 선택합니다. 저장소 내부 CORE render는 write-guard와 drift anchor 대상입니다.

---

## 산출물이 생성되는 위치

SAGE를 돌리면 리소스가 목적에 따라 서로 다른 위치에 생깁니다. 전체 지도는 [ARTIFACTS.md](docs/ARTIFACTS.md) — 아래는 요약입니다.

| 위치 | 성격 | 대표 산출물 |
|---|---|---|
| `<root>/.sage/` | PDCA 실행 정본 (커밋 대상) | `plan_interview.md`(기획 인터뷰) · `knowledge_scan.md` · `loop_audit.jsonl` · `override.jsonl` |
| `<root>/<host>/logs/` | 세션 단위 hook 기록 | `session-<date>.jsonl` · `compliance-<date>.md` · `declared-risk-<sid>.json` |
| Obsidian vault (`vault_path`/folder) | 최종 지식노트 | write-back TECH 노트 · `TECH - <name> loop audit` · `TECH - <name> retro …` · `log.md` |
| `<root>/sage/asset_overrides/` | CORE 오버레이 (커밋 대상, `install --force`가 덮지 않음) | `agents/<id>.md` · `skills/<id>.md` |
| `<root>/<host>/…` + `docs/sage_harness/.manifest.json` | spec 생성물 + 무결성 스탬프 | hook/agent/skill/mcp 설정 파일 · manifest |

- **vault 단일 쓰기경로** — Obsidian 노트/log/index는 오직 `sage knowledge write-back` 계열만 씁니다. `vault_path`가 비면 지식노트는 vault 대신 `.sage/` 흔적으로만 남습니다.
- **CORE 오버레이** — loop/retro로 CORE 자산 개선이 필요하면 렌더를 직접 고치는 대신 `sage/asset_overrides/`에 덧대 `install --force`에도 살아남게 합니다.

---

## Hook 7종 (무엇을 강제하나)

| hook | 역할 |
|---|---|
| `pre-implementation-gate` | 위험도 분류 · plan 문서 · PDCA phase 강제 (미충족 시 BLOCK) |
| `pre-phase4-checklist-gate` | PDCA 03→04 전환 전 체크리스트 완료 강제 |
| `capture-declared-risk` | 유저 선언 작업 위험레벨 포착 |
| `post-tool-logger` | 변경 분류를 세션 JSONL에 기록 |
| `session-start-snapshot` | 세션 시작 시 06 문서 baseline 스냅샷 (작성 도구 무관 06 변경 감지) |
| `stop-compliance-report` | 세션 종료 시 컴플라이언스 리포트 생성 |
| `generated-artifact-write-guard` | 생성 산출물 직접수정 차단 → spec으로 redirect |

Hook은 정책 판정(`{id}_core.py`)과 런타임 I/O(어댑터)가 분리되어, 같은 정책이 Claude/Codex 양쪽에서 동일하게 동작합니다.

---

## CORE 스킬 (대화형 워크플로)

`sage install`이 설치하는 부트스트랩 스킬입니다. `/sage-cycle`이 전체 우산이고, 기획(`/sage-plan`)과 개발(`/sage-team`)로 나뉩니다.

| 스킬 | 역할 |
|---|---|
| `sage-init` | 최초 설치 후 공유 `project-profile.yaml`과 현재 머신의 local profile 작성 |
| `sage-init-local` | 이미 설정된 프로젝트에서 현재 머신의 local profile만 작성·갱신 |
| `sage-cycle` | PDCA 00–06 전체 구동 (우산) |
| `sage-plan` | 기획 00–02: 인터뷰(`.sage/plan_interview.md`) → plan 문서 + 파일 소유권 |
| `sage-team` | 개발 03–06: 구현 → 검증 → QA → 리뷰 → 완료 |
| `sage-review` | Phase 05 리뷰 + 적대적 루프 |
| `sage-asset` | 자산 추가·수정 (대화 → `sage generate`) |
| `sage-profile-modify` | profile 값 대화형 수정 |

---

## CLI 참조

전체 도움말은 `sage --help`, 서브커맨드별 도움말은 `sage <command> --help`로 확인합니다.

### 설치 · 생성

| 명령 | 역할 |
|---|---|
| `sage install --host claude` / `sage install --host codex --skill-scope {global,project-local}` | 현재 프로젝트에 SAGE 기본 파일과 명시적 CORE skill scope 설치 |
| `sage generate --kind {hook,agent,skill,roster,mcp}` | spec → 설정 파일 생성 (`--write` 없으면 미리보기만) |

### 검증 · 관리

| 명령 | 역할 |
|---|---|
| `sage validate` | spec↔산출물 drift · staleness · conformance 검사 |
| `sage asset-check` | 자산 auto-approve 가능 여부 분류 (CI gate: `--gate`) |
| `sage absorb --kind K --id ID` | 직접 수정된 파일을 spec 수정 후보로 제안 |
| `sage doctor` | 실행 환경 · 리뷰 설정 · cross-model 가용성 점검 |
| `sage models --host HOST` | host 모델 후보와 출처/검증 수준 표시(네트워크 probe 없음) |
| `sage change "설명"` | 변경 의도에 맞는 SAGE 명령 안내 |
| `sage override --reason R --ttl T` | 게이트 임시 우회 (사유+기간 필수, 감사 기록) |
| `sage acceptance-waiver {grant,list,revoke}` | exact L3 acceptance ID의 운영 검증 유예와 grant/use/revoke 감사 |
| `sage authority {inspect,attest,gate}` | 보호된 CI의 base/head 최고 위험도, exact PDCA 증거, attestation 권위 게이트 |
| `sage context snapshot --cycle-stem STEM --phase ID` | 완료 phase의 profile/manifest/문서 hash 결속 packet 저장 |
| `sage context restore --snapshot PATH` | packet과 현재 source를 검증하고 재개 briefing 생성 |

Double-host projects install Claude and Codex surfaces in separate `sage install --host ...` runs. The profile keeps
`runtime.installed_hosts` (desired surfaces) separate from one `runtime.active_host`; SAGE does not execute both hosts
or switch phases automatically. Resume manually from committed exact-Cycle-Stem phase documents, and keep
`options.cross_model: true` so Phase 05 selects the runtime opposite the active host.

Context compaction is explicit rather than host magic. With
`context_management.compaction.enabled: true`, CORE skills snapshot completed phase
boundaries under `.sage/context/snapshots/`; a later session/host verifies one packet
and reads the derived `.sage/context/restored/` briefing. SAGE does not restore hidden
model memory or automatically launch/switch hosts.

### 리뷰

| 명령 | 역할 |
|---|---|
| `sage review` | Phase 05 same-runtime 리뷰 |
| `sage cross-check --packet-file F` | Phase 05 cross-model 리뷰 (반대 런타임 직접 호출) |
| `sage review-loop {open,round,close,show,next}` | Loop A 라운드 감사 기록·조회 (`next`=계속/종료 결정론 권고) |
| `sage retro [--feature STEM]` | Loop C 회고 — 누락 패턴 분석 + 개선 제안 (`--feature`=노트 제목의 사이클 식별자) |
| `sage retro --check NOTE` | 회고 노트가 실제로 채워졌는지 검사 (빈 템플릿·무효 제안 → non-zero) |

### 지식 캡처

| 명령 | 역할 |
|---|---|
| `sage knowledge scan` | PDCA 시작 전 Obsidian vault 조회 → `.sage/knowledge_scan.md` |
| `sage knowledge write-back` | PDCA 완료 후 vault 노트 + `wiki/log.md` 갱신 (태그는 vault 작성가이드 기반, `--tags`로 override) |

write-back 노트의 깊이는 이 사이클의 risk tier(00 base plan `Risk Level: Lx`)에 따라 스킬이 결정합니다 — L1은 짧게, L2/L3는 vault의 손저작 노트 수준으로 심층 작성(배경·설계결정·변경내역·검증·재발방지 등)합니다. `note_convention.required_structure`(PREFIX별 필수 마커)를 설정하면 신규 노트가 그 골격을 갖췄는지 advisory로 확인합니다(마커 존재만 결정론 확인, 누락 시 WARN·비차단 — 내용 깊이는 게이트 밖). L1 노트나 기획 인터뷰 캡처처럼 골격 대상이 아니면 `--skip-structure-check`로 검사를 끕니다.

### 자주 겪는 오류

**`sage: command not found`**

`pipx install sage-harness`로 설치했는지 확인합니다. `pip --user`로 설치했다면:

```bash
python3 -m sage --help
# 또는 PATH에 추가
export PATH="$(python3 -m site --user-base)/bin:$PATH"
```

**`--host` / `--kind` 누락 오류**

`install`에 `--host`, `generate`에 `--kind`는 필수입니다. `-h`는 단축 옵션이 아닙니다.

```bash
sage install --host claude
sage generate --kind hook --write
```

**`sage absorb` / `sage override` 인자 누락**

```bash
sage absorb --kind agent --id my-agent        # --kind, --id 필수
sage override --reason "hotfix" --ttl 30m    # --reason, --ttl 필수
```

---

## Profile 설정

`sage/project-profile.yaml`은 저장소에 공유할 정책입니다. 최초 설정에서는 `sage-init`이 공유 파일과 현재 머신의 `project-profile.local.yaml`을 함께 작성합니다. 이미 공유 프로필이 설정된 저장소에서는 각 팀원이 `sage-init-local`로 로컬 파일만 작성합니다. 로컬 파일은 설치가 관리하는 `.gitignore` 규칙으로 Git에서 제외됩니다.

### 선택 기능

```yaml
options:
  cross_model: true    # Phase 05 리뷰를 반대 런타임에서 독립 실행
  obsidian: optional   # Obsidian vault 지식 캡처
  codegraph: optional  # CodeGraph MCP 연동
```

### Cross-Model 리뷰

host runtime이 PDCA를 실행하고, Phase 05에서 반대 런타임이 독립 리뷰합니다.

```yaml
options:
  cross_model: true

runtime:
  host: claude
  external_reviewer: opposite_runtime

cross_model:
  reviewer: { host: codex, model: gpt-5.6-terra }
  effort: xhigh        # 선택. peer 에게 넘길 reasoning effort. 미설정 → high
```

`sage doctor`로 리뷰어 가용성을 확인하세요. cross-model이 활성화된 상태에서 반대 런타임에 도달할 수 없거나
호출에 실패하면 Phase 05는 `BLOCKED`로 종료됩니다. same-runtime 실행은 `policy: off` 또는
`policy: recommended`의 명시적 local opt-out 경로에서만 정상 완료로 인정됩니다.

`cross_model.effort`는 `options.cross_model: true`일 때만 유효하며, peer마다 어휘가 다릅니다 — peer가 `codex`면 `minimal|low|medium|high|xhigh`, `claude`면 `low|medium|high|xhigh|max`. 미설정 시 SAGE는 `high`를 넘깁니다. `cross_model.reviewer`를 설정하면 host는 active host의 반대여야 하고 model은 peer CLI에 명시 전달됩니다. 생략하면 하위호환으로 peer CLI default model을 사용합니다.

`sage models --host codex`는 Codex 로컬 cache의 visible 후보를 `cache-confirmed`로 표시합니다. Claude CLI에는 안정적인 계정 모델 목록 명령이 없으므로 `sage models --host claude`의 alias는 `syntax-only/account-unverified`입니다. SAGE는 모델 확인을 위해 유료 요청을 자동 실행하지 않습니다.

### 에이전트 모델 / effort (claude host)

CORE 에이전트 각각에 실행 모델과 reasoning effort를 지정할 수 있습니다.

```yaml
team:
  core:
    leader:   { enabled: true, runtime: { model: opus, effort: xhigh } }
    reviewer: { enabled: true, runtime: { model: opus } }
```

`model`은 `opus | sonnet | haiku | fable | inherit` 또는 전체 모델 id로, **미설정 시 host CLI가 고른 모델**을 그대로 씁니다. `effort`는 `low | medium | high | xhigh | max` 또는 양의 정수로, **미설정 시 `high`** 입니다.

이 값들은 `.claude/agents/<id>.md` frontmatter로 주입되므로 **claude host에서만** 동작합니다(codex는 `.codex/agents/*.md`를 model/effort로 해석하는 기전이 없어 주입하지 않고, `sage validate`가 무동작 경고). 값을 바꾼 뒤에는 `sage install --force`로 렌더를 재배포하세요 — 재배포 전까지 `sage doctor`가 해당 에이전트를 `stale`로 표시합니다.

### Obsidian 지식 캡처

```yaml
knowledge_capture:
  vault_path: "/path/to/obsidian/vault"
  provider: obsidian
  scan_before_dev: true    # 개발 시작 전 vault 조회
  update_after_dev: true   # 완료 후 vault 업데이트
  note_convention:
    folder: "wiki"
    required_structure: {}   # PREFIX → 필수 마커 목록. 비면(기본) advisory 검사 OFF
```

`vault_path`가 비어 있으면 Obsidian 기능은 비활성입니다.

### Profile 예시

```yaml
# sage/project-profile.yaml
project:
  name: "weatherapp"
  prefix: "weatherapp"

options:
  cross_model: true
  obsidian: optional
  codegraph: optional

runtime:
  host: claude
  external_reviewer: opposite_runtime

mcp:
  enabled: [codegraph]

knowledge_capture:
  vault_path: ""
  provider: obsidian

risk:
  l1_path_globs: ["*frontend/*.js"]
  l2_path_globs: ["*backend/*.java"]
  l3_filename_globs: ["*payment*", "*auth*"]
  l3_content_keywords: ["encrypt", "PrivateKey", "chargeCard"]
  plan_glob: "plan_docs/**/*.md"

components:
  - { id: backend, paths: ["backend/**"], model: opus,
      runtime_models: { claude: opus, codex: gpt-5.6-terra } }
  - { id: frontend, paths: ["frontend/**"], model: opus,
      runtime_models: { claude: sonnet, codex: gpt-5.6-sol } }

verification:
  commands:
    build: "npm run build"
    test: "npm test"
    lint: "npm run lint"
```

설정 후 권장 확인:

```bash
sage doctor --profile sage/project-profile.yaml
sage generate --kind hook --write
sage validate
```

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

## 관련 프로젝트

- **[llm_wiki](https://github.com/nashsu/llm_wiki)** — 로컬 LLM 기반 Obsidian vault. SAGE의 지식 캡처가 PDCA 산출 지식을 적재하는 대상입니다.
- **[LLM OS (Karpathy)](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)** — AI 에이전트를 OS처럼 운영하는 접근법. SAGE의 거버넌스 개념과 맞닿아 있습니다.
- **[CodeGraph](https://github.com/colbymchenry/codegraph)** — 코드 지식 그래프. SAGE에서 `mcp.enabled`에 추가해 MCP 자산으로 관리합니다.

---

## 라이선스

CC BY-NC-SA 4.0 — [LICENSE](LICENSE) 참조.

비상업적 사용 및 동일 조건 재배포 허용. 상업적 이용은 저작권자와 별도 협의.
