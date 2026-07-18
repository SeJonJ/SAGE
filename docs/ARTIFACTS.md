# SAGE 산출물 지도

SAGE를 돌리면 여러 리소스가 **서로 다른 목적으로 서로 다른 위치**에 생성됩니다.
이 문서는 그 산출물이 **어디에** 생기고, **무슨 역할**이며, **누가(어느 명령·hook·스킬이) 쓰는지**를
단일 참조점으로 모읍니다. 각 항목은 실제 생성 코드(파일:라인)를 근거로 답합니다.

관통 원칙은 세 가지입니다.

- **판단은 AI(host), 배치·게이트는 결정론 코드** — 산출물의 *위치*는 CLI/hook이 결정론으로 정합니다.
- **vault 단일 쓰기경로** — Obsidian 노트/log/index는 오직 `sage knowledge write-back`(및 그 계열)만 씁니다.
- **Obsidian 미사용 시 `.sage`, 사용 시 vault** — `knowledge_capture.vault_path`가 비면 지식노트는 vault 대신 `.sage/` 흔적으로만 남습니다.

---

## 한눈에 보기

| 위치 | 성격 | 대표 산출물 | 생성 주체 |
|---|---|---|---|
| `<root>/.sage/` | PDCA 실행 정본 (커밋 대상) | `plan_interview.md` · `knowledge_scan.md` · `loop_audit.jsonl` · `acceptance-waivers.jsonl` · `override.jsonl` | CLI · 스킬 · hook |
| `<root>/<host>/logs/` | 세션 단위 hook 기록 | `session-<date>.jsonl` · `compliance-<date>.md` · `declared-risk-<sid>.json` | hook 어댑터 |
| Obsidian vault (`vault_path`/folder) | 최종 지식노트 | write-back TECH 노트 · loop audit 대시보드 · retro 노트 · `log.md` | `sage knowledge` · `review-loop` · `retro` |
| `<root>/sage/asset_overrides/` | CORE 오버레이 (커밋 대상, install 미배포) | `agents/<id>.md` · `skills/<id>.md` | 사람 작성 (absorb 안내) |
| `<root>/<host>/…` + `docs/sage_harness/.manifest.json` | spec 생성물 + 무결성 스탬프 | hook/agent/skill/mcp 설정 파일 · manifest | `sage generate` |

`<host>` = claude host면 `.claude`, codex host면 `.codex` (`scripts/sage_harness/hooks/runtime/io_claude.py:14`, `io_codex.py:15`).

---

## 1. `<root>/.sage/` — PDCA 실행 정본

PDCA를 돌리는 동안 남는 정본 데이터입니다. 프로젝트 루트(서브디렉토리에서 실행해도 동일 루트)를 기준으로
`.sage/` 아래에 생기며, 재현·감사를 위해 **커밋 대상**입니다.

| 파일 | 역할 | 생성 코드 |
|---|---|---|
| `.sage/plan_interview.md` | 기획 인터뷰 결과. `sage-plan`/`sage-cycle`의 첫 프로세스에서 leader가 사용자와의 인터뷰(플랫폼·기능·데이터/API·제약·완료기준)를 정리해 남기고, 이를 근거로 PDCA 00(CONTEXT)/01(CONTENT)을 작성 | 출력 규약 `templates/core/framework/docs/agent/plan-interview.md`, 사용처 `sage-plan/SKILL.md` |
| `.sage/knowledge_scan.md` | 개발 착수 전 Obsidian vault에서 관련 선행지식을 조회한 스캔 리포트. PDCA 00의 prior-knowledge 입력 | `sage/commands/knowledge.py:228` `_write_scan_report(root, …)` |
| `.sage/loop_audit.jsonl` | Loop A(적대적 Phase 05 리뷰) 라운드 감사의 **정본**. open/round/close가 append되고 시퀀스 무결성을 검증. vault 대시보드는 이 파일의 파생 뷰 | `sage/commands/review_loop.py:8`, `:472` |
| `.sage/retro_audit.jsonl` | Loop C(`sage retro --check`) 성공 증거의 append-only 감사(9-C v1). `sage retro --check`가 통과할 때마다 `{run_id, note_path, digest, ts}`를 기록 — Stop 훅(`retro_gate` 정책)이 세션 종료 시 이 기록으로 "이 사이클이 실제로 check를 통과했는지" 사후 확인한다. `pdca.retro.report_gate_enforce`가 off면 기록만 남고 아무것도 검사하지 않는다 | `sage/commands/retro.py::_check_note` → `scripts/sage_harness/hooks/runtime/retro_audit.py` |
| `.sage/override.jsonl` | 게이트 임시 우회(`sage override`)의 append-only 감사 로그. 사유·TTL과 함께 사후 추적, 만료 시 자동 회수 | `sage/commands/override.py:6` |
| `.sage/acceptance-waivers.jsonl` | exact L3 cycle/required acceptance ID의 명시적 `NOT TESTED` 유예. grant/use/revoke와 reason/scope/remaining evidence/confirmed_by를 append-only로 기록하며 malformed/중복/충돌은 fail-closed | `sage/commands/acceptance_waiver.py` → `scripts/sage_harness/hooks/runtime/acceptance_waiver.py` |
| `.sage/context/snapshots/<stem>/*.json` | 완료 phase의 profile/manifest/exact Cycle-Stem 문서 경로·hash를 결속한 cross-session 정본 packet. 문서 본문은 포함하지 않음 | `sage context snapshot` |
| `.sage/context/restored/*.md` | packet과 현재 source를 모두 검증한 뒤 생성되는 resume briefing. 재생성 가능한 파생물 | `sage context restore` |

`context/snapshots`는 세션/host handoff를 위해 보존·커밋할 수 있는 정본이고,
`context/restored`는 언제든 다시 만들 수 있는 파생물이라 저장소 정책에 따라 ignore해도 됩니다.

서버 권위 attestation은 로컬 `.sage/` 정본이 아니다. 보호된 CI가 `sage authority attest`의 stdout을 짧은
수명의 job artifact로 전달하고, 같은 base/head/diff/cycle/risk 결속을 `sage authority gate`에서 검증한다.
프로젝트 로컬 override/waiver audit은 이 판정의 입력에서 제외된다.

> `.sage/tmp/grants.jsonl` 등 실행 보조 파일도 같은 트리에 생길 수 있습니다(런타임 grant 추적).

---

## 2. `<root>/<host>/logs/` — 세션 단위 hook 기록

hook 어댑터가 세션 실행 중 남기는 기록입니다. host 디렉토리(`.claude` 또는 `.codex`) 아래 `logs/`에 모입니다
(`scripts/sage_harness/hooks/runtime/hook_runtime.py:220-221, 261-262`).

| 파일 | 역할 | 생성 코드 |
|---|---|---|
| `session-<date>.jsonl` | `post-tool-logger`가 도구 실행마다 변경 분류(파일·op)를 append. 컴플라이언스 리포트의 원천 데이터 | `hook_runtime.py:250-275`, 분류 코어 `scripts/sage_harness/hooks/post_tool_logger_core.py:67` |
| `compliance-<date>.md` | `stop-compliance-report`가 세션 종료 시 그날 session JSONL을 집계해 만든 컴플라이언스 리포트 | `hook_runtime.py:354-...`, `report = os.path.join(log_dir, f"compliance-{today}.md")` |
| `declared-risk-<sid>.json` | `capture-declared-risk`가 유저 선언 작업 위험레벨을 세션별로 포착. pre-implementation-gate가 판정에 참조 | `scripts/sage_harness/hooks/runtime/io_claude.py:33` / `io_codex.py:40` |

이 파일들은 **세션 범위의 실행 기록**으로, `.sage/` 정본과 달리 매 세션·일자마다 갱신됩니다.

---

## 3. Obsidian vault — 최종 지식노트

`knowledge_capture.vault_path`(+ `note_convention.folder`, 기본 `wiki`)로 결정된 vault에 최종 지식노트를 남깁니다
(`sage/commands/knowledge.py:92` `_vault.vault_target`). **오직 write-back 계열만** vault에 쓰는 단일 쓰기경로이며,
`vault_path`가 비면(`:94`) 이 단계는 skip됩니다.

| 산출물 | 역할 | 생성 코드 |
|---|---|---|
| write-back TECH 노트 | PDCA 완료 후 산출 지식을 vault에 적재. 태그는 vault 작성가이드(AGENT_GUIDE/CLAUDE/GEMINI.md)를 읽어 결정하고 CLI `--tags`로 덮어쓸 수 있음(하드코딩 아님) | `sage/commands/knowledge.py:301` `_note_path` |
| `TECH - <name> loop audit.md` | Loop A 대시보드. 프로젝트당 1페이지로 close마다 갱신되며 `.sage/loop_audit.jsonl`의 파생 뷰. run별 retro 링크 열 포함 | `sage/commands/review_loop.py:485, :492` |
| `TECH - <name> retro <stem> <date>.md` | Loop C 회고 human-gate 노트. `approved:false`로 생성 — 사람이 승인(`approved:true`)하기 전엔 absorb되지 않으며 자동 반영되지 않음. 관련 loop audit로의 역링크 포함. `<stem>`은 `--feature` > 유일한 05 문서명 > run_id 순으로 정해짐. 같은 날 같은 stem의 **다른 run**이 회고를 남기면 뒤 노트는 `… <date> <run_id>.md`로 분리 생성(앞 run의 노트를 재사용해 완료 게이트를 통과하는 것을 막음). 대시보드 링크는 파일명이 아니라 frontmatter `run_id` 기준 | `sage/commands/retro.py` `_write_vault_note` |
| `log.md` · index 링크 | 노트 생성 시 vault의 history-hub `log.md`와 index에 `- <date> [[note]] - title` 한 줄을 멱등 append | `sage/commands/knowledge.py:278` `_append_log_once` |

파일명은 `note_convention`을, 태그는 vault 작성가이드를 따르므로 vault마다 관례가 달라도 그에 맞춰 생성됩니다.

---

## 4. `<root>/sage/asset_overrides/` — CORE 오버레이

CORE 부트스트랩 자산(6 에이전트·9 스킬)은 `sage install`이 손으로 배포하고 `--force`가 덮어씁니다.
그 CORE 렌더를 **직접 고치는 대신** 프로젝트 로컬 오버레이로 커스터마이즈하는 자리입니다.

| 산출물 | 역할 | 생성 코드 |
|---|---|---|
| `sage/asset_overrides/agents/<id>.md` | 특정 CORE 에이전트에 프로젝트 지침을 덧대는 오버레이. CORE 렌더가 존재 시 먼저 적용하되 AGENT_GUIDE·phase·리뷰·검증 게이트를 완화할 수 없음 | 경로 안내 `sage/commands/absorb.py:171` |
| `sage/asset_overrides/skills/<id>.md` | 특정 CORE 스킬에 대한 동일 성격 오버레이 | 동일 |

핵심 성질:

- **install이 ship하지 않음** → `sage install --force`가 CORE를 덮어써도 오버레이는 **보존**됩니다.
- **absorb가 후보를 안내** — retro/loop 산출로 에이전트·스킬 개선이 필요하면 CORE 직접수정 대신 이 경로를 제시합니다. 단 hook은 결정론이라 오버레이 파일만으로 실행 동작이 바뀌지 않습니다(hook 변경은 spec 경유).

기존 `sage/conventions/*.md` + convention-checker 패턴을 자산 전반으로 일반화한 것입니다.

---

## 5. spec 생성물 + manifest — `sage generate`

`sage generate`가 spec(SSOT) → 런타임 설정 파일을 배치하고, 무결성 스탬프를 남깁니다.
어떤 kind가 어디로 가는지는 자산 종류에 따라 갈립니다.

| kind | 산출물 위치 |
|---|---|
| `hook` | `settings.json` / `hooks.json` + 런타임 shim |
| `agent` | `.claude/agents/` · `.codex/agents/` |
| `skill` | `.claude/skills/` · `.codex/skills/` |
| `mcp` | `.mcp.json`(claude) · `.codex/config.toml`(codex) |

- **`docs/sage_harness/.manifest.json`** — 생성 산출물의 hash 스탬프 정본. `sage validate`가 이 스탬프와 실제 파일을 대조해 drift·staleness를 적발하고, write-guard가 직접수정을 차단하는 근거 (`sage/commands/generate.py:305, :412`).

이 경로들은 **spec→생성→검증→차단 폐루프**의 산출측이며, spec 자체(`docs/sage_harness/{hooks,agents,skills,mcps}/{id}.md`)는 생성물이 아니라 사람이 쓰는 SSOT입니다. 자세한 게이트·신뢰 경계는 [ARCHITECTURE.md](ARCHITECTURE.md) 참조.
