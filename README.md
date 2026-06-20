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
pipx install sage-harness

cd your-project
sage install --host codex   # 또는 --host claude
                            # hook·에이전트 spec·AGENT_GUIDE·manifest 자동 배치

sage generate --kind hook --write
                      # spec md → .claude/.codex 산출물 + manifest 스탬프
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

전체 도움말은 `sage --help`, 서브커맨드별 도움말은 `sage <command> --help`로 확인할 수 있습니다.

| 명령 | 필수 옵션 | 주요 옵션 | 역할 / 예시 |
|---|---|---|---|
| `sage install` | `--host {claude,codex}` | `--prefix PREFIX`, `--dest DEST`, `--force` | 대상 프로젝트에 CORE 하네스를 설치합니다. 예: `sage install --host codex --dest .` |
| `sage generate` | `--kind {hook,agent,skill,roster,mcp}` | `--id ID`, `--write`, `--target {claude,codex,both}`, `--dest DEST`, `--root ROOT` | spec md를 런타임 산출물과 manifest 스탬프로 변환합니다. `--write`가 없으면 dry-run입니다. 예: `sage generate --kind agent --id backend-expert --target codex --write` |
| `sage generate --kind roster` | `--kind roster` | `--write`, `--dest DEST`, `--root ROOT` | `profile.components` 기반으로 `implementer-<component>` 에이전트 spec을 결정론적으로 scaffold합니다. |
| `sage generate --kind mcp` | `--kind mcp` | `--id ID`, `--write`, `--target {claude,codex,both}` | `docs/sage_harness/mcps/{id}.md`를 Claude `.mcp.json` 또는 Codex `config.toml` managed-block으로 생성합니다. |
| `sage validate` | 없음 | `--check`, `--schema`, `--kind {hook,agent,skill,mcp,all}`, `--id ID`, `--root ROOT` | drift, staleness, conformance, regression을 읽기 전용으로 검사합니다. 빠른 검사: `sage validate --check`; schema 검사: `sage validate --schema`. |
| `sage review` | 없음 | `--kind {hook,agent,skill,mcp,all}`, `--batch`, `--gate`, `--root ROOT` | `auto_approve_safe_default` 기준으로 자동승인과 사람검토 대상을 분류합니다. CI 게이트: `sage review --gate`. |
| `sage absorb` | `--kind {hook,agent,skill}`, `--id ID` | `--from-blocked-diff`, `--claude PATH`, `--codex PATH`, `--guide PATH`, `--config CONFIG`, `--root ROOT` | 직접 수정된 런타임 산출물이나 write-guard에 막힌 diff를 spec patch 후보로 역추출합니다. 자동 반영은 하지 않습니다. |
| `sage doctor` | 없음 | `--profile PROFILE` | 옵션 의존성, 실행 환경, reviewer fallback 설정을 진단합니다. 예: `sage doctor --profile sage/project-profile.yaml`. |
| `sage change` | `intent` | `--root ROOT` | 자연어 의도를 `generate` 또는 `absorb` 흐름으로 라우팅합니다. 예: `sage change "backend-expert agent 고쳐줘"`. |
| `sage override` | grant 시 `--reason REASON` | `--ttl TTL`, `--gate GATE`, `--list`, `--root ROOT` | 게이트 BLOCK을 시한부로 우회하고 `.sage/override.jsonl`에 append-only 감사 로그를 남깁니다. 예: `sage override --reason "hotfix" --ttl 30m --gate pre-implementation-gate`. |

### CLI 오류 메시지 해설

SAGE CLI는 위험한 추측을 피하기 위해 일부 값을 필수 옵션으로 요구합니다. 아래 오류는 설치 실패가 아니라, 필요한 인자를 빠뜨렸다는 뜻입니다.

#### `sage install`: `--host` 누락

```text
usage: sage install [-h] --host {claude,codex} [--prefix PREFIX] [--dest DEST] [--force]
sage install: error: the following arguments are required: --host
```

원인: SAGE는 Claude와 Codex 중 어느 런타임을 주 실행 환경으로 쓸지 자동으로 추측하지 않습니다.

해결:

```bash
sage install --host codex
# 또는
sage install --host claude
```

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
sage generate --kind hook --write
sage generate --kind agent --id backend-expert --target codex --write
sage generate --kind skill --id backend-convention --target both --write
sage generate --kind roster --write
sage generate --kind mcp --id codegraph --target codex --write
```

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
