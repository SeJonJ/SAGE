# SAGE — System for Agentic Governance & Engineering

[![CI](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml/badge.svg)](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sage-harness)](https://pypi.org/project/sage-harness/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/sage-harness/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **개발 중인 프로젝트입니다.** PyPI 패키지와 기본 CLI는 사용할 수 있지만, profile 대화형 작성 흐름과 일부 cross-runtime 자동화는 아직 개선 중입니다. README의 명령과 지원 범위를 확인하고 적용하세요.

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
sage install --host codex   # 또는 --host claude
                            # hook·에이전트 spec·AGENT_GUIDE·manifest 자동 배치

# AI 에이전트와 대화해서 sage/project-profile.yaml 값을 채웁니다.
# 자세한 절차: docs/agent/bootstrap-authoring.md

sage generate --kind hook --write
                      # spec md → .claude/.codex 산출물 + manifest 스탬프
sage validate         # drift · staleness · conformance 검사 (읽기 전용)
```

끝입니다. 이제 AI 에이전트는 강제력 있는 규칙 위에서 동작합니다.

---

## 설치

SAGE는 `sage` 명령을 제공하는 CLI 도구이므로 `pipx` 설치를 권장합니다. `pipx`는 패키지를 독립 가상환경에 설치하고 `sage` 실행 파일만 PATH에 노출합니다.

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

### Windows happy-path

SAGE의 hook 어댑터는 `bash` + `python3`로 실행됩니다. Windows 네이티브 cmd/PowerShell에는 둘 다 없을 수 있으므로:

1. **Git Bash 또는 WSL에서 실행** — `bash`가 PATH에 있어야 어댑터(.sh)가 구동됩니다.
2. **`python3` 별칭** — Windows는 보통 `python`만 있고 `python3`가 없습니다. 어댑터는 `python3`가 없으면 자동으로 `python`으로 폴백하지만(`${SAGE_PYTHON:-python3}` → `python`), 명시적으로 지정하려면:
   ```bash
   export SAGE_PYTHON=python      # Git Bash/WSL
   ```
3. **점검**: `sage doctor`가 OS·`bash`·`python` 가용성을 보고합니다. `bash : NOT FOUND`면 Git Bash/WSL에서 다시 실행하세요.

```bash
# Git Bash 예시
pipx install sage-harness
export SAGE_PYTHON=python
sage doctor          # bash/python 확인
sage install --host claude
```

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

## 위협 모델 / 신뢰 경계

SAGE가 막는 것과 막지 않는 것을 분명히 합니다.

**핵심 신뢰 경계 — 결정론 게이트 vs 판단(interpretive):**

| SAGE 소유 (결정론, LLM 0) | 런타임(host AI) 실행 (판단) |
|---|---|
| hash · `CONTRACT_VERSION` · write-guard · report←approve(06←05) · 위험분류 게이트 · 루프 감사 스키마/무결성 · profile 설정검증 | 코드 작성, 리뷰 finding, 반박, rework, **루프 종료 판단**, 회고 분석 |

> 루프 종료(수렴/dry/예산/iter)의 *판단*은 현재 host 가 `sage-review` 스킬의 문서화된 규칙으로 수행하고(advisory-first), SAGE 는 그 결과를 감사로 기록·무결성 검증합니다. 하드 backstop은 report←approve(05 미승인 시 06 BLOCK)로 결정론입니다. 종료 조건의 결정론 *집행*(SAGE가 예산/수렴을 직접 계산)은 후속 단계.

판단은 비결정적이라 틀릴 수 있습니다. SAGE는 그 위에 **결정론 경계**를 둬서 — 빠진 plan/phase는 BLOCK, spec↔산출물 드리프트는 validate FAIL, 직접수정은 write-guard, 05 미승인 시 06 BLOCK — *판단이 틀려도 게이트는 안 무너지게* 합니다. AI를 더 똑똑하게 만드는 게 아니라, AI가 틀릴 것을 전제하고 경계를 박는 것이 SAGE입니다.

**SAGE가 방어하는 것:**
- 의도(spec)와 산출물의 **드리프트** — generate↔validate 폐루프
- **거버넌스 침묵 비활성** — profile 오타(`l3_filename_globs`→단수)가 게이트를 조용히 끄는 것을 fail-closed로 적발 (jsonschema 없이도)
- **ungoverned 직접수정** — write-guard가 spec으로 redirect
- **단일 모델 편향** — cross-model 리뷰(상대 런타임이 반박자). 단, `options.cross_model` on + 상대 런타임 도달 가능할 때만; 불가하면 same-runtime clean-context로 degrade(차단 아님, `sage doctor`가 degraded 표시)

**SAGE가 방어하지 않는 것 (범위 밖):**
- 완전히 탈취된 host 런타임, 또는 repo/profile 쓰기 권한을 가진 악의적 작성자 (그 시점엔 게이트 자체를 고칠 수 있음)
- OS 수준 동시성 공격 (예: 자산 쓰기 TOCTOU) — 단일 사용자 로컬 워크플로 전제
- 판단 품질 자체 — SAGE는 리뷰가 *돌게* 보장하지만 리뷰어가 모든 결함을 찾는다고 보장하진 않음 (그래서 미수렴은 BLOCKED로 사람에게)

---

## 적대적 리뷰 루프 (Loop A) + 회고 (Loop C)

Phase 05 리뷰를 *단발*이 아니라 **수렴할 때까지 도는 루프**로 운영할 수 있습니다 (`profile.pdca.review_loop.enabled`, L2/L3).

```
찾기(병렬 렌즈 + cross-model) → 반박(false-positive 필터) → 분류(아키텍처 변경은 사람) → 수정 → 종료(수렴/dry/예산)
```

- **`sage-review` 스킬**이 루프 본문(찾기/반박/수정)과 **종료 판단**을 host에서 문서화된 규칙대로 수행하고(advisory-first), **`sage review-loop`** CLI가 라운드별 감사를 `.sage/loop_audit.jsonl`에 기록하며 결과/사유 어휘·run_id 무결성을 검증합니다. 종료 backstop은 기존 report←approve(06←05 APPROVED) 그대로 — 루프는 절대 이를 우회하지 않습니다.
- **`sage retro`** (Loop C)는 사이클이 끝난 뒤 *리뷰가 잡은 것 = host가 체계적으로 놓친 것*을 모아, 기계적 누락은 hook/profile·의미적 누락은 agent/skill 개선으로 **제안**합니다 (자동 반영 없음, `absorb` 철학).
- Obsidian을 쓰면 `--vault`로 루프 대시보드와 회고 human-gate 노트를 vault에 남길 수 있습니다 (아래 선택 기능).

판단(찾기/반박/수정/종료결정)은 런타임에서, 감사 기록·무결성·설정검증과 report←approve backstop은 SAGE에서 — 위 신뢰 경계가 루프에도 그대로 적용됩니다.

---

## 자산 종류 4종

| kind | 생성 성격 | SSOT | 산출물 |
|---|---|---|---|
| `hook` | 결정론 (순수 함수) | `docs/sage_harness/hooks/{id}.md` + `{id}_core.py` | `settings.json` / `hooks.json` + 런타임 shim |
| `agent` | interpretive (AI 렌더) | `docs/sage_harness/agents/{id}.md` + `{id}.claims.yml` | `.claude/agents/` / `.codex/agents/` |
| `skill` | interpretive (AI 렌더) | `docs/sage_harness/skills/{id}.md` + `{id}.claims.yml` | `.claude/skills/` / `.codex/skills/` |
| `mcp` | 결정론 (선언 데이터 직렬화) | `docs/sage_harness/mcps/{id}.md` (frontmatter payload) | `.mcp.json` (claude) · `.codex/config.toml` managed-block (codex) |

> **MCP 거버넌스**: 시크릿은 env 변수명만 허용 (`${VAR}` placeholder). 리터럴 시크릿 값이 spec에 있으면 generate 전 FAIL (fail-closed). `.mcp.json`은 SAGE 소유(write-guard), `config.toml`의 비-MCP 설정은 보존합니다.

> **위 산출물 경로는 프로젝트 자산(generate/extract)** 기준입니다. **CORE 부트스트랩 자산**(hand-shipped: `sage-init`/`sage-cycle`/`sage-plan`/`sage-team`/`sage-review`/`sage-asset`/`sage-profile-modify` skill, CORE 로스터 6인 agent)은 별도이며, `sage install` 은 host 택1(claude **또는** codex)이라 호스트별로 다른 위치에 설치됩니다 — **claude host**: skill → repo `.claude/skills/`, agent → repo `.claude/agents/`. **codex host**: skill → 전역 `$CODEX_HOME/skills/`(codex 는 repo-스코프 skill 미자동발견), agent → repo `.codex/agents/`. 이들은 generated artifact 가 아니라 write-guard 면제입니다(`AGENT_GUIDE.md` 부트스트랩 절).

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

전체 도움말은 `sage --help`, 서브커맨드별 도움말은 `sage <command> --help`로 확인할 수 있습니다.

| 명령 | 필수 옵션 | 주요 옵션 | 역할 / 예시 |
|---|---|---|---|
| `sage install` | `--host {claude,codex}` 필수 | `--prefix PREFIX` 선택, 기본값 `sage`; `--dest DEST` 선택, 기본값 현재 디렉토리 `.`; `--force` 선택, 기본값 skip | 현재 프로젝트에 SAGE 기본 파일을 설치합니다. 예: `sage install --host codex --dest .` |
| `sage generate` | `--kind {hook,agent,skill,roster,mcp}` | `--id ID`, `--write`, `--target {claude,codex,both}`, `--dest DEST`, `--root ROOT` | spec 파일을 읽어 Claude/Codex용 설정 파일을 생성합니다. `--write`가 없으면 파일을 쓰지 않고 미리보기만 합니다. 예: `sage generate --kind agent --id backend-expert --target codex --write` |
| `sage generate --kind roster` | `--kind roster` | `--write`, `--dest DEST`, `--root ROOT` | 프로젝트 컴포넌트 목록을 보고 기본 구현 담당 agent spec을 만듭니다. |
| `sage generate --kind mcp` | `--kind mcp` | `--id ID`, `--write`, `--target {claude,codex,both}` | MCP spec을 읽어 Claude 또는 Codex가 사용할 MCP 설정 파일을 생성합니다. |
| `sage validate` | 없음 | `--check`, `--schema`, `--kind {hook,agent,skill,mcp,all}`, `--id ID`, `--root ROOT` | spec과 생성 파일이 서로 어긋났는지 검사합니다. 빠른 검사: `sage validate --check`; schema 검사: `sage validate --schema`. |
| `sage asset-check` | 없음 | `--kind {hook,agent,skill,mcp,all}`, `--batch`, `--gate`, `--root ROOT` | 프레임워크 자산 중 자동 통과 가능/사람 확인 필요를 나눕니다(구 `sage review`). CI에서 실패시키려면 `sage asset-check --gate`. |
| `sage review` | 없음 | `--root ROOT` | Phase 05 same-runtime 리뷰(cross_model=false 경로). `REVIEWER_ACTUAL: same_runtime` 출력. **⚠️ 이름 변경(0.x breaking): 구 `sage review`(자산분류)는 `sage asset-check` 로 이전.** 구 플래그(`--kind/--batch/--gate`)로 호출 시 친절히 안내. |
| `sage cross-check` | 없음 | `--packet-file F`(필수), `--timeout SEC`, `--strict`, `--root ROOT` | Phase 05 cross-model 리뷰 — 반대 런타임 CLI(`codex exec`/`claude -p`)를 직접 비대화 호출해 독립 리뷰 획득. peer 미도달 시 `REVIEWER_ACTUAL: same_runtime` 표면화(`--strict`면 exit 3). |
| `sage absorb` | `--kind {hook,agent,skill}`, `--id ID` | `--from-blocked-diff`, `--claude PATH`, `--codex PATH`, `--guide PATH`, `--config CONFIG`, `--root ROOT` | 직접 고친 생성 파일을 spec 수정안으로 되돌려 제안합니다. 자동 반영은 하지 않습니다. |
| `sage review-loop` | `<action> {open,round,close,show}` | open: `--risk {L2,L3}`; round: `--found/--survived/--accepted` 등; close: `--result/--reason/--iterations`; show: `--vault [PATH]` | Loop A(Phase 05 적대적 review-rework) 라운드 감사를 기록·조회합니다(sage-review 스킬이 호출). `show --vault`는 Obsidian 대시보드도 작성. 예: `sage review-loop open --risk L3` |
| `sage retro` | 없음 | `--run-id ID`, `--feature STEM`, `--vault [PATH]`, `--root ROOT` | Loop C(Act→Plan): 리뷰 사이클 학습(loop_audit + 05 문서)을 모아 개선 제안용 distiller 프롬프트를 제시합니다. 자동 반영 없음(absorb 철학). `--vault`로 Obsidian human-gate 노트 작성. |
| `sage knowledge` | `<action> {scan,write-back}` | scan: `--query/--query-file`, `--vault [PATH]`; write-back: `--title`, `--summary/--summary-file`, `--append-log` | Obsidian 지식 캡처를 PDCA 경계에서 실행합니다. `scan`은 `.sage/knowledge_scan.md`를 항상 새로 쓰고, `write-back`은 vault 노트와 `wiki/log.md`를 갱신합니다. |
| `sage doctor` | 없음 | `--profile PROFILE` | SAGE 실행에 필요한 도구와 리뷰 설정을 점검합니다. Codex host에서는 전역 CORE skill(`$CODEX_HOME/skills/sage-init` 등) stale도 표시합니다. 예: `sage doctor --profile sage/project-profile.yaml`. |
| `sage change` | `intent` | `--root ROOT` | 하고 싶은 변경을 어떤 SAGE 명령으로 처리할지 안내합니다. 예: `sage change "backend-expert agent 고쳐줘"`. |
| `sage override` | grant 시 `--reason REASON` | `--ttl TTL`, `--gate GATE`, `--list`, `--root ROOT` | 막힌 작업을 사유와 시간 제한을 남기고 임시로 허용합니다. 예: `sage override --reason "hotfix" --ttl 30m --gate pre-implementation-gate`. |

### CLI 오류 메시지 해설

SAGE CLI는 위험한 추측을 피하기 위해 일부 값을 필수 옵션으로 요구합니다. 아래 오류는 설치 실패가 아니라, 필요한 인자를 빠뜨렸다는 뜻입니다.

#### `sage install`: `--host` 누락

```text
usage: sage install --host {claude,codex} [--prefix PREFIX] [--dest DEST] [--force] [--help]
sage install: error: the following arguments are required: --host
```

원인: SAGE는 Claude와 Codex 중 어느 런타임을 주 실행 환경으로 쓸지 자동으로 추측하지 않습니다.

해결:

```bash
sage install --host codex
# 또는
sage install --host claude
```

주의: `-h`는 host의 단축어가 아닙니다. 도움말은 `sage install --help`로 확인합니다.

다른 프로젝트 경로에 설치하려면:

```bash
sage install --host codex --dest /path/to/your-project
```

이미 파일이 있을 때 덮어쓰려면:

```bash
sage install --host codex --force
```

#### `sage generate`: `--kind` 누락

```text
usage: sage generate [-h] --kind {hook,agent,skill,roster,mcp} [--id ID] [--write] [--target {claude,codex,both}] [--dest DEST] [--root ROOT]
sage generate: error: the following arguments are required: --kind
```

원인: 어떤 종류의 spec을 생성할지 지정하지 않았습니다.

해결:

```bash
sage generate --kind hook --write                              # --target claude|codex|both
sage generate --kind agent --id backend-expert --write          # 양 런타임 렌더(.claude+.codex)에서 추출+등록
sage generate --kind skill --id backend-convention --write      # 〃 (codex 발견 필요 시 --deploy-codex 추가)
sage generate --kind roster --write
sage generate --kind mcp --id codegraph --target codex --write
```

> `agent`/`skill` 의 렌더는 interpretive(런타임 AI 저작) 입니다. `.claude/...` 와 `.codex/...` 양쪽 렌더를 저작한 뒤 `sage generate --kind <agent|skill> --id <id> --write` 로 spec+claims 추출 + manifest 등록(양 render_hash)합니다. codex 는 repo-스코프 skill 을 자동발견하지 않으므로, codex-host 에서 skill 을 호출하려면 `--deploy-codex` 로 전역 `$CODEX_HOME/skills/<prefix>-<id>` 에 배포합니다(정본은 repo, 전역은 발견용 캐시). 대화형으로는 `/sage-asset` 스킬이 이 흐름 전체를 안내합니다.

주의: `--write`를 빼면 파일을 쓰지 않고 dry-run 미리보기만 수행합니다.

#### `sage absorb`: `--kind`, `--id` 누락

```text
usage: sage absorb [-h] --kind {hook,agent,skill} --id ID [--from-blocked-diff] [--claude CLAUDE] [--codex CODEX] [--guide GUIDE] [--config CONFIG] [--root ROOT]
sage absorb: error: the following arguments are required: --kind, --id
```

원인: 어떤 런타임 산출물을 어떤 spec으로 되돌려 흡수할지 지정하지 않았습니다.

해결:

```bash
sage absorb --kind agent --id backend-expert --codex .codex/agents/backend-expert.md
sage absorb --kind skill --id backend-convention --claude .claude/skills/backend-convention.md
sage absorb --kind hook --id pre-implementation-gate --from-blocked-diff
```

`absorb`는 spec patch 후보만 제안합니다. 보안을 위해 자동 반영하지 않습니다.

#### `sage override`: `--reason`, `--ttl` 누락

```text
[sage override] grant 에는 --reason 과 --ttl 둘 다 필요 (또는 --list)
```

원인: 게이트 우회는 감사 대상이므로 사유와 유효기간이 반드시 필요합니다.

해결:

```bash
sage override --reason "urgent production hotfix" --ttl 30m --gate pre-implementation-gate
sage override --reason "manual reviewer approved" --ttl 2h --gate all
sage override --list
```

`--ttl`은 `90s`, `30m`, `2h`, `1d`, 또는 초 단위 숫자를 사용할 수 있습니다.

#### `sage: command not found`

```text
zsh: command not found: sage
```

원인: 패키지는 설치됐지만 `sage` 실행 파일이 있는 Python user script 경로가 PATH에 없을 수 있습니다. 특히 `pip install --user` 또는 권한 문제로 user install이 된 macOS/Linux에서 자주 발생합니다.

권장 해결:

```bash
pipx install sage-harness
sage --help
```

`pip`로 설치했다면 fallback으로 실행할 수 있습니다:

```bash
python3 -m sage --help
python3 -m sage install --host codex
```

macOS/Linux에서 PATH를 직접 추가하려면:

```bash
export PATH="$(python3 -m site --user-base)/bin:$PATH"
```

Windows PowerShell에서는:

```powershell
py -m sage --help
```

---

## Profile 작성 방식

`sage/project-profile.yaml`은 사람이 처음부터 손으로 완성하는 파일이 아닙니다. `sage install`은 빈 스키마와 기본값을 배치하고, 그 다음 **AI 에이전트와 대화하면서 프로젝트 값만 채우는 것**이 의도된 사용 방식입니다.

설치된 프로젝트 안의 `docs/agent/bootstrap-authoring.md`가 이 절차의 기준입니다:

1. 사용자가 프로젝트 구조, 사용 런타임, 위험 도메인, 검증 명령, 선택 기능을 설명합니다.
2. AI 에이전트가 `sage/project-profile.yaml`의 기존 키에 값을 채웁니다.
3. 사용자가 중요한 선택을 승인합니다.
4. `sage generate`와 `sage validate`가 생성물과 drift를 결정론적으로 확인합니다.

주의: profile의 스키마 키를 새로 invent하지 않습니다. 고정된 키는 유지하고 값만 채웁니다.

### 선택 기능: CodeGraph / Obsidian / MCP

`options.codegraph`, `options.obsidian`은 “이 프로젝트에서 해당 기능을 쓰고 싶다”는 의도 표시입니다.

```yaml
options:
  codegraph: optional
  obsidian: optional
```

실제 MCP 서버 생성 대상은 `mcp.enabled`로 선택합니다. 이 값은 `docs/sage_harness/mcps/{id}.md` spec 중 어떤 MCP를 생성할지 고릅니다.

```yaml
mcp:
  enabled: [codegraph, obsidian]
```

필요한 spec 파일:

```text
docs/sage_harness/mcps/codegraph.md
docs/sage_harness/mcps/obsidian.md
```

생성 예시:

```bash
sage generate --kind mcp --target codex --write
sage generate --kind mcp --target both --write
sage generate --kind mcp --id codegraph --target codex --write
```

Obsidian 지식 캡처는 MCP 선택과 별개로 vault 경로가 있어야 활성화됩니다.

```yaml
knowledge_capture:
  vault_path: "/path/to/obsidian/vault"
  provider: obsidian
  scan_before_dev: true
  update_after_dev: true
  note_convention: { folder: "wiki" }   # vault 내 노트 폴더(기본 wiki)
```

`vault_path`가 비어 있으면 Obsidian 기능은 OFF/N/A로 처리됩니다(마스터 게이트).

`scan_before_dev`와 `update_after_dev`가 켜져 있으면 CORE skill 체인이 다음 명령을 명시적으로 호출합니다:

```bash
python -m sage knowledge scan --query-file .sage/knowledge_query.txt
python -m sage knowledge write-back --title "<cycle-stem>" --summary-file .sage/knowledge_writeback_summary.md --append-log
```

`scan`은 vault가 비활성/N/A/오류여도 `.sage/knowledge_scan.md`를 새로 써서 이전 사이클의 조회 결과를 잘못 재사용하지 않게 합니다. `write-back`은 노트 파일명을 deterministic하게 만들고, `wiki/log.md`에는 같은 wikilink를 중복 추가하지 않습니다.

`vault_path`가 설정되면 루프 엔지니어링 출력도 vault로 갈 수 있습니다:

```bash
sage review-loop show --vault   # <vault>/<folder>/SAGE-loop-audit.md (Loop A 대시보드, plain 테이블)
sage retro --feature loop-engineering --vault   # <vault>/<folder>/sage-retro-<stem>-<date>.md (Loop C 회고, approved:false human-gate)
```

회고 노트는 `approved: false`로 생성되며 사람이 Obsidian에서 검토·승인합니다. 같은 노트는 재실행해도 덮어쓰지 않아(create-only) 사람 승인 상태가 보존됩니다. `--vault PATH`로 경로를 직접 지정하면 profile 설정과 무관하게 그 경로에 씁니다(명시적 opt-in).

### Cross-Model Review 설정

host runtime은 SAGE PDCA를 주로 실행하는 AI 도구입니다.

```yaml
runtime:
  host: codex
  external_reviewer: opposite_runtime
```

Codex를 host로 두고 Phase 05 리뷰를 Claude로 보내고 싶다면:

```yaml
options:
  cross_model: true

runtime:
  host: codex
  external_reviewer: opposite_runtime

cross_model:
  peer: opposite_runtime
  invocation:
    codex_host: "$claude consult"
  on_unavailable: clean_context_same_runtime

capabilities:
  claude: true
```

검증:

```bash
sage doctor --profile sage/project-profile.yaml
```

현재 v1에서 `sage doctor`는 cross-model reviewer가 실제로 가능한지 판정하고, 불가능하면 `clean_context_same_runtime` fallback을 표시합니다. 특히 `host=codex`에서 Claude 호출은 `cross_model.invocation.codex_host`와, Claude 가용성 신호(`PATH` 의 실제 `claude` 실행파일 또는 `capabilities.claude: true`)가 필요합니다.

> **기대치 안내(v1):** Claude를 host로 두고 Codex에 리뷰를 보내는 경로는 1급으로 검증돼 있습니다. 반대 방향(host=codex → Claude 호출)은 **호출 레시피를 SAGE가 기본 제공하지 않습니다** — 위 `cross_model.invocation.codex_host`에 본인 환경의 Claude 실행 명령을 직접 채워야 동작하고, 비워 두면 `sage doctor`가 이를 감지해 `clean_context_same_runtime`으로 fallback합니다. 즉 cross-model은 현재 claude-host가 1급 시민이고, codex-host opposite는 사용자가 레시피를 제공해야 하는 상태입니다.

### Profile 예시

```yaml
# sage/project-profile.yaml — 도메인 값은 전부 여기, 엔진에는 0개
project:
  name: "weatherapp"
  prefix: "weatherapp"

options:
  cross_model: true
  codegraph: optional
  obsidian: optional

runtime:
  host: codex
  external_reviewer: opposite_runtime

cross_model:
  peer: opposite_runtime
  invocation:
    codex_host: "$claude consult"
  on_unavailable: clean_context_same_runtime

capabilities:
  claude: true

mcp:
  enabled: [codegraph]

knowledge_capture:
  vault_path: ""
  provider: obsidian

risk:
  l1_path_globs: ["*frontend/*.js"]           # 저위험 (UI)
  l2_path_globs: ["*backend/*.java"]          # 소스 (build+test+lint 필요)
  l3_filename_globs: ["*payment*", "*auth*"]  # 고위험 (plan + 리뷰 필수)
  l3_content_keywords: ["encrypt", "PrivateKey", "chargeCard"]
  plan_glob: "plan_docs/**/*.md"

components:
  - { id: backend, paths: ["backend/**"], model: opus }
  - { id: frontend, paths: ["frontend/**"], model: opus }

verification:
  commands:
    build: "npm run build"
    test: "npm test"
    lint: "npm run lint"
```

Profile 작성 후 권장 확인:

```bash
sage doctor --profile sage/project-profile.yaml
sage generate --kind hook --write --target codex
sage generate --kind mcp --target codex --write
sage validate --kind all --check
```

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

## 관련 프로젝트

SAGE의 선택 기능이 연동하는 외부 도구들입니다.

- **[Obsidian LLM Wiki (Local)](https://github.com/kytmanov/obsidian-llm-wiki-local)** — 로컬 LLM 기반 Obsidian vault. SAGE의 지식 캡처(`options.obsidian` 의도 플래그 + `knowledge_capture.vault_path` 활성화)가 PDCA 산출 지식을 적재하는 대상입니다.
- **[CodeGraph](https://github.com/colbymchenry/codegraph)** — 심볼·호출 관계를 인덱싱하는 코드 지식 그래프. SAGE에서는 `options.codegraph` 의도 플래그로 표시하고 `mcp.enabled` 에 codegraph를 넣어 MCP 자산으로 통치합니다.
- **[gstack](https://github.com/garrytan/gstack)** — Cross-Model Review에 쓰이는 Claude Code 스킬 팩. claude-host에서 `/codex consult` 기능을 제공합니다. 실제 호출 문자열은 `cross_model.invocation.claude_host` 에 두고, `capabilities.gstack` 은 가용성 신호로만 씁니다(`sage doctor` 가 `PATH` 의 `gstack` 또는 이 플래그로 판정).

---

## 라이선스

MIT — [LICENSE](LICENSE) 참조.
