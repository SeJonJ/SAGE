# [Fast 기본 계획] write guard × /sage-asset 렌더 저작 순환 수정 (#19)

Cycle-Stem: `sage-1.3.1-asset-drafts`
Cycle-Mode: FAST
Document-Language: ko
Risk Level: L3
Fast-Review-Level: L3
Fast-Minimum-Rounds: 1
Fast-Lens-Count: 4
Fast-Lenses: correctness, security, data_integrity, concurrency
Fast-Reason: 두 이슈(#18·#19) 모두 긴급하고 크리티컬해 빠른 반영이 필요하지만, 수정 범위가 좁고 단순해 Fast 사이클로 진행
Fast-Audit-Run: pending
Status: COMPLETED — 05 codex cross-review 4차 APPROVED, 06 작성(2026-10-12). 커밋은 사용자 결정
Done-Criteria-Revision: 1

## Phase 00 — 기본 계획

### 배경

- 이슈: https://github.com/SeJonJ/SAGE/issues/19
- 판정·범위 정본: 위키 「SAGE - 1.3.0 버그 대응 (26.10.12)」
- 엔진 저장소에는 SAGE 를 설치하지 않는다. Fast 문서 절차를 손으로 따르고 감사 run 은 열지 않는다(`Fast-Audit-Run: pending`). 05 는 codex cross-review.
- #18(`sage-1.3.1-fast-residual-close`)에 이어 1.3.1 패치로 함께 배포한다.

### 문제

`/sage-asset` 은 agent·skill 렌더를 `.claude|.codex/{agents,skills}/` 에 직접 쓰라고 하지만, write guard 는 그 경로를 신규·기존 구분 없이 막는다. guard 안내(「정본 spec 을 고쳐라」 → `sage generate`)를 따르면 generate 는 렌더 → spec 방향뿐이라 「렌더 누락」으로 실패하고 다시 `/sage-asset` 을 안내한다. 편집 도구만으로는 새 project skill·agent 를 만들거나 고칠 길이 없다. 설계 초기부터의 모순이다(1.3.0 회귀 아님).

### 범위

- 포함: `sage generate --from-drafts [--replace]`, guard 의 agent·skill 렌더 전용 code·복구 안내, `sage explain` 대응, `/sage-asset` 스킬·spec, CLAUDE.md/CODEX.md 템플릿 안내, bootstrap-authoring §5, guard spec, cli-reference(ko/en), i18n(ko/en), 회귀 시험.
- 제외: guard 가 manifest 에 없는 새 id 를 통과시키는 안(guard 순수 함수 계약 변경, modify 는 여전히 막힘), hook 생성 흐름(이미 spec → 산출물 방향이라 영향 없음), CORE 렌더·overlay 경로.

### 설계 결정

- 초안 위치: `sage/asset_drafts/<kind>s/<id>/claude-render.md`, `sage/asset_drafts/<kind>s/<id>/codex-render.md`. guard 매칭 밖이다. 파일명을 `claude.md`·`codex.md` 로 두면 guard 의 framework 문서 basename 검사(`CLAUDE.md`·`CODEX.md`, 대소문자 무시)에 걸린다 — 설계 확인에서 codex 가 찾았다.
- codex host: workspace-write sandbox 는 작업 공간의 기존 `.codex/` 를 읽기 전용으로 보호한다. 셸에서 실행한 `sage generate` 도 sandbox 를 상속하므로, codex 에서 배치 명령은 sandbox 밖 실행 승인(on-request) 또는 사용자 터미널 실행이 필요하다. `--deploy-codex` 의 `$CODEX_HOME` 쓰기도 같다. 이 제약은 이 수정이 만든 것이 아니라 `.codex/` 에 쓰는 모든 CLI 에 해당하며, 스킬 절차에 명시한다.
- 배치는 CLI 가 한다. CLI 는 편집 도구를 거치지 않으므로 guard 를 느슨하게 하지 않는다(guard spec 「CLI 는 예외가 필요 없다」와 같은 원리).
- 초안은 배치 뒤에도 지우지 않는다(05 2차에서 변경). 처음에는 남은 초안이 두 번째 정본처럼 보이는 것을 막으려 자동 삭제했지만, 비교와 삭제 사이에 고친 초안을 지울 수 있고 그 손실은 되돌릴 수 없다. 대신 「렌더가 정본이 됐으니 확인 뒤 지워도 된다」고 알린다. 수정은 렌더를 다시 초안으로 복사해 시작하므로 남은 초안은 그때 덮인다.

### Done Criteria
- [x] 초안 두 벌 → `generate --kind skill|agent --id <id> --from-drafts --write` 로 렌더 배치·spec·claims·manifest 등록까지 되고 `validate` 가 통과한다
- [x] 기존 렌더는 `--replace` 없이 덮이지 않고, `--replace` 로 교체하면 render_hash 가 갱신된다
- [x] 초안 한쪽 누락·추출 실패·CORE 이름·잘못된 id 는 아무것도 배치하지 않고 실패한다
- [x] guard 가 project agent·skill 렌더 차단 시 `--from-drafts` 경로를 안내하고, hook·CORE·framework 문서 안내는 바뀌지 않는다
- [x] `/sage-asset` 스킬·spec·템플릿 안내·문서가 초안 → `--from-drafts` 흐름과 맞는다
- [x] codex host 에서도 이 흐름이 동작하는지 codex 확인을 받는다
- [x] 관련 회귀 스위트가 통과한다
- [x] codex cross-review 가 APPROVED 다

### Document Mapping (Checklist)
- [x] Phase 00 context complete
- [x] Phase 01 requirements and acceptance matrix embedded
- [x] Phase 02 design and failure handling embedded
- [x] Phase 03 ownership, implementation checklist, and verification plan ready

## Phase 01 — 요구사항

### Acceptance Matrix

| ID | User Requirement | Required Evidence | Owner | Required? |
|---|---|---|---|---|
| B1 | 새 skill: 초안 두 벌 → `--from-drafts --write` 로 두 렌더 배치, spec·claims 작성, manifest 등록, 초안은 남김, `validate` 통과 | 회귀 시험 | dev | yes |
| B2 | 새 agent: B1 과 같은 흐름 | 회귀 시험 | dev | yes |
| B3 | 대상 렌더가 하나라도 있으면 `--replace` 없이는 거부되고 아무것도 바뀌지 않는다 | 회귀 시험 | dev | yes |
| B4 | 수정: 기존 렌더 → 초안 → `--from-drafts --replace --write` 로 교체되고 manifest render_hash 가 새 내용과 맞는다 | 회귀 시험 | dev | yes |
| B5 | CORE 이름·잘못된 id·`--id` 없음·kind 가 hook 등이면 복사 전에 거부된다 | 회귀 시험 | dev | yes |
| B6 | 초안 한쪽 누락·초안 추출 실패면 렌더·spec·manifest·초안이 그대로다 | 회귀 시험 | dev | yes |
| B7 | `--write` 없는 실행은 배치 계획만 보이고 아무것도 쓰지 않는다 | 회귀 시험 | dev | yes |
| B8 | 초안이 symlink 이거나 프로젝트 밖을 가리키면 거부된다 | 회귀 시험 | dev | yes |
| B9 | guard: project agent·skill 렌더 차단 메시지는 새 code 와 `--from-drafts` 명령을 싣고, hook 렌더·CORE·framework 문서 메시지는 그대로다. `sage explain` 도 같은 code 를 낸다 | 회귀 시험 | dev | yes |
| B10 | `/sage-asset` 스킬·spec, CLAUDE.md/CODEX.md 템플릿, bootstrap-authoring §5, guard spec, cli-reference(ko/en)가 새 흐름과 맞는다 | 문서 diff + 문서 시험 | dev | yes |
| B11 | codex host 에서 초안 쓰기(apply_patch)가 guard 를 통과하고, CLI 배치의 sandbox 조건이 절차에 적혀 있다는 codex 확인 | codex 응답 기록 | dev | yes |
| B12 | 초안 경로(`sage/asset_drafts/<kind>s/<id>/{claude,codex}-render.md`)는 guard 가 막지 않는다(편집 도구·apply_patch 모두) | 회귀 시험 | dev | yes |
| B13 | 실제 codex host 세션에서 `$sage-asset` → 초안 → 승인된 배치 → 발견까지 실행 | 실기 기록 | dev | no |

## Phase 02 — 설계

### `generate --from-drafts`

- 인자: `--from-drafts`(flag), `--replace`(flag, `--from-drafts` 와만 의미). `--from-drafts` 는 `--kind agent|skill` 과 `--id` 를 요구한다. 아니면 즉시 거부.
- 순서(아무것도 쓰기 전에 모두 검사):
  1. id 형식·CORE 이름 검사(기존 검사 재사용, 순서를 앞으로).
  2. 초안 두 벌이 있고, 일반 파일이며 symlink 가 아니고, realpath 가 프로젝트 안인지.
  3. 대상 렌더 둘 중 하나라도 있으면 `--replace` 필요.
  4. 초안 경로로 `drv.extract()` 를 먼저 돌려 추출 실패를 배치 전에 잡는다.
- `--write` 가 없으면 「어디에 무엇을 놓을지(신규/교체)」만 출력하고 기존 dry-run 출력으로 이어 간다.
- `--write` 면 두 렌더를 같은 디렉터리 임시 파일에 먼저 쓰고 `os.replace` 로 교체한다. 두 번째 교체가 실패하면 첫 번째를 원래 내용(없었으면 삭제)으로 되돌리고 실패로 끝낸다. 그 뒤 기존 흐름(spec·claims 쓰기, manifest upsert, `--deploy-codex`)을 그대로 탄다. (05 재작업으로 바뀐 실제 구현은 Phase 04 「재작업」 절.)
- `--from-drafts` 없이 실행하면 기존 동작 그대로다. `msg70` 안내는 「초안을 쓰고 `--from-drafts` 로 실행」으로 바꾼다.

### guard

- `block_reason()` 에 분기 추가: framework 문서·CORE overlay·CORE blocked 판정 뒤, host 자산 kind 가 `agents`·`skills` 이면 `guard.interpretive_render`(인자: `path`, `kind`=agent|skill, `id`). `hooks` 는 지금처럼 `guard.generated_asset`.
- 복구(`runtime/recovery.py` 와 엔진 `diagnostic_contract.py` 양쪽): `WRITE_DRAFTS`(사람/에이전트 작업: 초안 두 벌), `PLACE_DRAFTS`(`sage generate --kind <kind> --id <id> --from-drafts --write`, 수정이면 `--replace`), `VALIDATE`.
- 판정(차단 여부)은 바꾸지 않는다. 메시지·복구만 갈린다.
- `sage explain --path` 도 같은 판정으로 code 를 고른다.

### 실패 처리

- 모든 검사 실패: 비영(1) 종료, 파일 변화 없음.
- 교체 중 실패: 되돌린 뒤 실패. 되돌리기마저 실패하면 남은 경로를 출력한다(조용히 넘어가지 않음).
- 초안은 지우지 않는다(05 2차에서 변경 — 「설계 결정」 참고). 배치 뒤 「확인 뒤 지워도 된다」만 알린다.

## Phase 03 — 구현

- [x] File ownership assigned before source edits
- [x] Acceptance IDs mapped to implementation tasks
- [x] Verification command plan recorded

### 소유 파일 (단독 작업)

- `sage/commands/generate.py`, `sage/commands/explain.py`, `sage/diagnostic_contract.py`, `sage/i18n/ko.py`, `sage/i18n/en.py`
- `scripts/sage_harness/hooks/generated_artifact_write_guard_core.py`, `scripts/sage_harness/hooks/runtime/recovery.py`, `scripts/sage_harness/hooks/runtime/i18n/ko.py`, `scripts/sage_harness/hooks/runtime/i18n/en.py`
- `templates/core/framework/.claude/skills/sage-asset/SKILL.md`, `templates/core/skills/sage-asset.md`, `templates/core/framework/CLAUDE.md`, `templates/core/framework/CODEX.md`, `templates/core/framework/docs/agent/bootstrap-authoring.md`
- `docs/sage_harness/hooks/generated-artifact-write-guard.md`, `docs/cli-reference.md`, `docs/cli-reference.en.md`
- 시험: `test_generate.py`, `test_generated_artifact_write_guard.py`, 필요 시 `test_operability_rework.py`
- `docs/sage_harness/.manifest.json` (hook 런타임·spec 해시 재계산)

### 작업 ↔ acceptance

| 작업 | Acceptance |
|---|---|
| `--from-drafts`·`--replace` 인자와 검사 | B5, B6, B8 |
| 배치(임시 파일·교체·되돌리기)·초안 정리 | B1, B2, B3, B4, B6 |
| dry-run 배치 계획 | B7 |
| guard code·복구·explain·i18n·진단 계약 | B9 |
| 스킬·spec·템플릿·문서 | B10 |
| codex 동작 확인 | B11 |
| guard 의 초안 경로 통과 시험 | B12 |
| codex host 실기(필수 아님, 릴리즈 전 사용자 결정) | B13 |

### 검증 명령

- 관련 시험: `PYTHONPATH=$PWD python3 scripts/sage_harness/hooks/tests/<file>.py` (`test_generate`·`test_generated_artifact_write_guard`·`test_operability_rework`·`test_documentation`·`test_hook_locale` 등)
- 전체 스위트 로컬 1회: `bash scripts/sage_harness/hooks/tests/run-all.sh`
- `python -m sage validate --check --schema`
- 파이썬 버전 매트릭스·플랫폼 스모크는 CI.

## Phase 04 — 분석

Status: COMPLETE — 구현·로컬 검증 완료, 05 4차 APPROVED

### Acceptance Evidence

| ID | Status | Evidence |
|---|---|---|
| B1 | PASS | `TestGenerateFromDrafts.test_a_new_skill_is_placed_and_registered_and_its_drafts_are_left` — 렌더 두 벌 배치, spec·claims, manifest render_hash 일치, 초안 유지, `validate` 의 interpretive 검사 PASS/WARN |
| B2 | PASS | `test_a_new_agent_follows_the_same_path` — interpretive 검사 포함 |
| B3 | PASS | `test_existing_renders_are_not_overwritten_without_replace` — 프로젝트 전체 파일 스냅샷 불변 |
| B4 | PASS | `test_replace_swaps_the_renders_and_refreshes_the_hash` |
| B5 | PASS | `test_core_names_and_unsafe_ids_are_refused_before_any_copy`·`test_a_case_alias_of_a_core_name_is_refused`·`test_usage_is_checked_before_anything_else` |
| B6 | PASS | `test_a_missing_or_unextractable_draft_changes_nothing`·`test_a_failed_second_replace_restores_the_first_render`·`test_a_registration_failure_restores_everything`(신규·수정)·`test_a_failed_temp_write_leaves_no_temp_file`·`test_a_render_created_after_the_check_is_not_overwritten`·`test_rollback_leaves_a_render_someone_else_changed` |
| B7 | PASS | `test_without_write_only_the_plan_is_shown` |
| B8 | PASS | `test_linked_drafts_are_refused`·`test_a_linked_render_or_render_directory_is_refused` — 초안·렌더 양쪽 링크 거부, 밖의 파일 불변 |
| B9 | PASS | `TestInterpretiveRenderExit` 4건(새 code·`--from-drafts` 명령, 원래 id 철자, 다른 경로 안내 불변) · `test_explain_points_a_project_skill_render_to_the_drafts_exit` |
| B10 | PASS | sage-asset 렌더·spec, CLAUDE.md/CODEX.md 템플릿, bootstrap-authoring §5, guard spec 새 절, cli-reference ko/en(+미러 해시) |
| B11 | PASS | codex 설계 확인(session `01a13038-cb16-7ff2-9a8a-00cacfadc7eb`): 초안 이름·sandbox 두 조건 반영 뒤 조건부 성립. 이 행은 설계 확인만 증명한다 — 실제 host 실행은 B13 |
| B12 | PASS | `test_the_drafts_the_guidance_points_to_are_writable` — 편집 도구 경로·apply_patch 모두 통과, `claude.md` 이름은 차단 확인 |
| B13 | NOT TESTED | 실제 codex host 실행은 하지 않았다. 필수 아님 — 06 잔여 위험과 릴리즈 전 사용자 결정 |

### 검증 결과

- 새 시험 14건(`TestGenerateFromDrafts` 10, `TestInterpretiveRenderExit` 3, explain 1). 소스만 되돌리면 generate 11건(subTest 포함)·guard 4건이 실패한다.
- 관련 묶음 통과: `test_generate`·`test_generated_artifact_write_guard`·`test_operability_rework`·`test_hook_locale`·`test_documentation`·`test_language_context`·`test_localization_inventory`.
- 1차 전체 스위트에서 2건 실패 → 수정: `--from-drafts` 도움말의 `{claude,codex}` 중괄호가 format 에 걸림(이중 중괄호로), localization 인벤토리 행 번호 재생성.
- 전체 스위트(`run-all.sh`, 로컬 Python 3 한 버전, #18 머지 뒤 main 기준): 1차 구현 3,839건 → 최종 소스(05 4차 반영 뒤) 3,851건, 모두 실패 0.
- `python -m sage validate --check --schema`: WARN(exit 0, main 과 같음). guard spec·core 해시와 `hook_runtime_hash.shared` 재계산(#18 머지 뒤 main 기준으로 다시 계산).

### 설계와 달라진 점

- 초안 파일명: `claude.md`·`codex.md` → `claude-render.md`·`codex-render.md`. codex 설계 확인에서 guard 의 framework 문서 basename 검사에 걸리는 것을 찾았다.
- codex host 의 sandbox(`.codex/` 읽기 전용) 조건을 스킬·템플릿·문서·guard 복구 안내에 넣었다. 엔진 동작은 바꾸지 않는다.
- 추출은 초안을 읽어 둔 사본(임시 디렉터리)으로 하고, 배치도 같은 바이트를 쓴다. (1차 재작업에서는 초안을 「읽은 뒤 바뀌지 않았을 때만」 지웠으나, 2차에서 자동 삭제 자체를 없앴다.)
- `--from-drafts` 와 CORE 이름이 만나면 기존처럼 건너뛰지 않고 실패한다.
- explain 텍스트 출력이 판정 인자(kind·id)로 복구 명령을 채운다(JSON 은 다른 code 와 같이 템플릿 그대로).
- 같은 문장에 있던 오래된 안내 두 곳을 함께 고쳤다: CLAUDE.md·CODEX.md 의 「CORE 렌더는 write-guard 예외」(실제로는 차단된다).

### 05 1차 FAIL 뒤 재작업

- 배치를 `_RenderTransaction` 으로 바꿨다: 임시 파일은 `mkstemp`(예측 불가·배타 생성)로 만들고 파일 핸들로 기록, 신규 배치는 대상 자리를 `O_EXCL` 로 먼저 잡아 검사 뒤 생긴 렌더를 덮지 않음, 렌더가 링크면 거부. 배치부터 spec·claims·manifest 기록까지 한 범위로 묶어 어디서 실패해도 되돌린다.
- CORE 이름은 대소문자를 무시하고 거부한다(`--from-drafts` 한정 — 쓰기 경로).
- 초안 정리는 옆 이름으로 원자적으로 옮긴 뒤 비교하고, 다르면 되돌려 놓는다.
- guard 복구 명령의 id 는 원래 철자를 쓴다.
- 실패 메시지를 「모두 되돌림」과 「되돌리지 못한 경로」로 나눴다.
- B1·B2·B4 시험에 validate 의 interpretive 검사를 붙였고, B11 은 설계 확인만 증명하도록 고치고 실제 host 실행을 B13(필수 아님, NOT TESTED)으로 분리했다.

### 05 2차 FAIL 뒤 재작업

| 2차 지적 | 판단 | 처리 |
|---|---|---|
| N1 P1 되돌리기가 남이 바꾼 파일을 지우거나 링크 너머를 덮음 | 수용 | 되돌리기 전에 「우리가 쓴 그대로·일반 파일」인지 확인하고, 아니면 손대지 않고 되돌리지 못한 경로로 보고 |
| N2 P1 `O_EXCL` 자리 잡기 뒤 `os.replace` 가 그 사이 바뀐 내용을 덮음 | 수용 | 신규 렌더는 `os.link` 로 덮어쓰기 없이 게시(대상이 있으면 원자적으로 실패). 하드 링크를 못 만드는 파일시스템만 자리 잡기 방식 |
| N3 P1 초안 비교·삭제 사이 수정 유실 | 수용(설계 변경) | 초안 자동 삭제를 없앴다. 지우지 않으면 잃을 것이 없다 |
| N4 P1 경로 검사 뒤 디렉터리를 링크로 바꿔치기 | 거부(기록) | 같은 작업 공간의 다른 writer 가 검사와 쓰기 사이에 디렉터리를 바꿔야 한다. 이식 가능한 descriptor-bound I/O 가 없고(Windows), 같은 종류의 EH-27 이 보류 중이다. 정적 링크는 막는다 |
| N5 P1 spec·claims 부모 링크 미검사 | 거부(기록) — 변경 전 결함 | 기존 generate 흐름의 결함. 이번 범위 밖, 06 후속으로 |
| N6 P1 서로 다른 자산 동시 등록 시 manifest 유실 | 부분 수용 | `--from-drafts --write` 경로는 hook generate·install 과 같은 `DestinationLock` 으로 직렬화. 잠금 없는 기존 generate 경로는 변경 전 결함 — 06 후속으로 |
| N7 P2 추출 사본 기록 실패 시 임시 디렉터리 잔존 | 수용 | `TemporaryDirectory` 로 |

### 05 3차 FAIL 뒤 재작업

3차는 2차 거부(N4·N5·N6 기존 경로)를 타당하다고 판정했고, 2차 재작업이 만든 결함 셋과 문서 하나를 지적했다. 새 장치를 더하지 않고 막는다.

| 3차 지적 | 처리 |
|---|---|
| F1 P1 하드 링크 대체 경로에서 `os.replace` 실패 시 빈 렌더가 남고 「모두 되돌림」으로 보고 | 빈 자리를 만든 직후 실패하면 그 자리에서 치우고, 게시가 끝난 순간에만 되돌림 기록에 올린다 |
| F2 P1 spec·claims 를 제자리에 쓰다 실패하면 원본이 잘린 채 남고 되돌림이 「남이 바꾼 파일」로 보아 거부 | spec·claims 도 임시 파일에 다 쓴 뒤 교체 |
| F3 P1 마지막 manifest 스탬프가 잠금 밖 | 잠금을 `run()` 으로 올려 `_gen_interpretive` 와 스탬프를 함께 감쌈(`--from-drafts --write` 한정, 기존 경로 불변) |
| F4 P3 사이클 문서에 자동 삭제 설명 잔존 | 고침 |

### 05 4차 APPROVED 뒤 반영

- R1(P2): 교체가 실패해 그대로 남은 원본을 「되돌리지 못한 경로」로 보고하던 것 — 되돌림 기록을 교체가 끝난 뒤로 옮김(렌더·spec 공통). 시험은 언어 중립 표지로 바꾸고 회귀 1건 추가.

### 판정 요청 (05 에)

- 배치(임시 파일 → `os.replace` → 실패 시 되돌림)가 부분 배치를 남기지 않는가. 되돌리기 실패 시 보고가 충분한가.
- 경로 검사(`_contained_real`)가 초안·렌더 양쪽의 링크·탈출을 막는가(Windows 포함).
- codex host 절차(sandbox 밖 실행 승인 또는 사용자 터미널) 안내가 실제 동작과 맞는가.
