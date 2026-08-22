# SAGE CLI 레퍼런스

[English](cli-reference.en.md) | [문서 인덱스](README.md) | 실행 환경의 정확한 옵션은 `sage <command> --help`

## 설치와 생성

| 명령 | 역할 |
|---|---|
| `sage install --host claude` | Claude Code framework, CORE hook, agent, skill 설치 |
| `sage install --host codex --skill-scope project-local` | Codex 자산과 저장소 로컬 CORE skill 설치 |
| `sage install --host codex --skill-scope global` | Codex 자산과 사용자 전역 CORE skill 설치 |
| `sage generate --kind hook --write --target HOST` | hook spec에서 host 등록, adapter, manifest stamp 생성 |
| `sage generate --kind mcp --write --target HOST` | MCP spec에서 host 설정 생성 |
| `sage generate --kind {agent,skill} --write` | 두 host render에서 spec과 claims를 역추출하고 정합화 |
| `sage generate --kind roster` | `profile.components`에서 implementer spec 생성 |
| `sage generate --kind roster --from-existing ID` | 기존 implementer 합성 렌더를 새 component identity로 승격 |

`generate`는 `--write`가 없으면 미리보기입니다. hook/MCP는
`--target claude|codex|both`로 host를 지정합니다. agent/skill은 항상 두 host render를 요구하는
render-first 흐름이므로 `--target`으로 범위를 줄이지 않습니다.

신규 project hook은 `docs/sage_harness/hooks/<id>.md`와
`scripts/sage_harness/hooks/<id>_core.py`만 먼저 작성한 뒤 다음 명령으로 등록합니다.

```bash
sage generate --kind hook --id <id> --write --target both
```

최초 등록은 양 host binding과 `CONTRACT_VERSION`을 검증하고 manifest, canonical adapter,
host 설정, shim을 하나의 트랜잭션으로 기록합니다. 신규 ID의 단일 host 등록은 허용되지 않습니다.

등록된 project hook은 profile 사용 여부와 무관하게 최신 `sage/project-profile.json`을 요구합니다.
YAML/compiled profile이 없거나 서로 다르면 편집을 exit 2로 차단하므로, 등록 또는 profile 변경 뒤에는
`sage generate --kind hook --write --target both`를 실행해야 합니다.

project core의 `decide(event, profile, snapshot)`에서 `event`는 `hook_id`, `hook_event_name`
(`PreToolUse`), `runtime`, `session_id`, `changes`를 제공합니다. `changes`는 host 입력에서 추출한
`{path, op}` 목록이며 비어 있을 수 있습니다. `op`는 claude에서 `write`, codex에서 `add`·`update`·`move`이며
`move`는 `apply_patch`의 파일 이동 **목적지만** 담습니다 — 이동 원본은 문서가 생기는 경로가 아니므로
포함되지 않습니다. 파일 삭제도 포함되지 않습니다.
선택적 `plan_reads()`가 반환한 glob은 project root 안의 regular file만 읽습니다. `snapshot`은
`plan_reads()` 선언 여부와 무관하게 항상 `{glob_results, files}` 형태이며, 선언하지 않으면 둘 다 비어
있습니다. `plan_reads()`는 정확히 `{'globs': [...]}`를 반환해야 하고 `globs` 키가 없으면 계약 오류입니다. 재귀 glob이 매치한 디렉터리는
건너뛰지만 symlink ancestor를 포함한 root 이탈, symlink leaf match, 그 밖의 비정규 파일은 계약 오류로
차단합니다.

## 검증과 진단

| 명령 | 역할 |
|---|---|
| `sage validate` | 기본 `hook` 범위의 hash, staleness, regression, profile 의미 검사 |
| `sage validate --kind all` | hook, agent, skill, MCP 전체 자산 검사 |
| `sage validate --check` | 회귀 명령을 실행하지 않는 빠른 정합성 검사 |
| `sage validate --schema` | manifest와 profile JSON Schema 검사 |
| `sage validate --strict` | bootstrap/schema/overlay/profile drift 등 지정된 advisory check를 실패로 승격 |
| `sage doctor` | Python, hook entry, host, reviewer, profile, optional capability 진단 |
| `sage models --host HOST` | 로컬에서 확인 가능한 model 후보와 검증 수준 표시 |
| `sage asset-check --gate` | 자산 변경의 auto-approve 가능 여부를 CI exit code로 반환 |

## 자산 유지보수

| 명령 | 역할 |
|---|---|
| `sage absorb --kind K --id ID` | 직접 수정 diff를 spec patch 후보로 변환 |
| `sage sync-overlays` | CORE overlay와 governance routing 관리 블록 재수렴 |
| `sage change "설명"` | 변경 의도에 맞는 generate/absorb 경로 안내 |
| `sage feedback` | `sage-feedback ::` 마커 조회 |
| `sage feedback --release-gate` | 미해결 blocking feedback으로 릴리즈 차단 |
| `sage override --reason R --ttl T` | 허용된 gate의 기간 제한 우회와 감사 기록 |
| `sage acceptance-waiver {grant,list,revoke}` | exact L3 acceptance 운영 유예 관리 |
| `sage cycle set STEM` | 기존 Phase 00의 사이클을 게이트에 선언 (장수 브랜치 필수) |
| `sage cycle set STEM --create --risk L1\|L2\|L3 [--path DIR]` | Phase 00 뼈대 하나를 만든 뒤 선언 (`DIR`은 root 상대 디렉터리) |
| `sage cycle show` | 현재 선언과 그 출처(env / `.sage/cycle.json`) 조회 |
| `sage cycle clear` | 파일 선언 해제 — 정상 완료 뒤 실행; env 선언은 별도 `unset` 필요 |
| `sage fast-cycle open --stem S --level L2\|L3 --lens-count N --reason R` | composite 00 검증 후 Fast 감사 run 시작 |
| `sage fast-cycle convert --stem S --current-phase 00\|01\|02\|03\|04 --level L2\|L3 --lens-count N --reason R --confirmed-by W --confirm FAST-CONVERTED` | 진행 중인 Standard Cycle을 Fast 계약으로 전환 (문서 미변경) |
| `sage fast-cycle review --run-id F --loop-run-id L` | APPROVED Loop Audit의 stem·라운드·렌즈 영수증을 Fast run에 결속 |
| `sage fast-cycle close --run-id F` | 최신 00 hash와 05/06 결속을 검증하고 정상 종료 |
| `sage fast-cycle abort --run-id F --reason R` | 사유를 남기고 활성 Fast run 중단 |
| `sage fast-cycle show [--run-id F] [--vault [PATH]]` | 감사 요약 표시 및 선택적 Obsidian dashboard 생성 |

`sage-cycle` 우산은 `set`/`clear`를 직접 실행하지 않습니다. `sage-plan`이 검증된 stem을 선언하고,
`sage-team`이 재개 시 `show`로 대조하며 write-back·retro·snapshot과 종료 게이트를 마친 뒤 해제합니다.
`BLOCKED`/`FAIL`에서는 선언을 유지합니다. 현재 출처와 밀린 파일 선언은 `sage cycle show`로 확인하고,
env가 이기면 `unset SAGE_CYCLE_STEM`으로 해제합니다.

`set B`는 포인터만 전환하며 A의 phase 문서·증거·감사를 수정하지 않습니다. `set A`로 돌아가면
A의 판정이 복원됩니다. `--create`는 Phase 00만 만들므로 profile이 01~03을 요구하면 해당 문서를
작성해야 합니다. 긴급하게 면제 가능한 phase 결핍을 열 때는 `sage override --reason R --ttl 1h`처럼
짧은 TTL을 사용하세요. Phase 00의 risk 선언·정합 차단은 override로 면제되지 않습니다.

`convert`는 `pdca.fast_cycle.standard_transition.enabled: true`가 추가로 필요합니다. Phase 00을
이미 지난 사이클이 composite 계획을 새로 쓰지 않고 Fast 계약으로 넘어가는 경로입니다. 전환은
**문서를 한 바이트도 쓰지 않습니다** — 기존 00~04를 지우거나 옮기거나 합치거나 고쳐 쓰지 않고,
전환 metadata를 문서에 넣지도 않습니다. 정본은 `.sage/fast_cycle.jsonl`의 `fast_convert` 레코드
하나이고, 거기에 전환 시점까지 존재하던 phase 목록이 남습니다. 전환된 run은 **그 목록이 담고 있는
pre-implementation phase만** 면제받습니다 — Phase 00에서 전환하면 01~03은 여전히 소스 편집 전에
필요합니다. `--confirm FAST-CONVERTED`·`--reason`·`--confirmed-by` 셋 중 하나라도 없으면 아무것도
기록하지 않고 종료합니다. 전환된 run은 문서에 `Fast-Audit-Run` 줄을 갖지 않고 stem으로 결속합니다.

`show`와 dashboard는 각 run을 `entry=` 한 값으로 구분합니다. 어느 계약으로 열렸는지가 이후 판정을
가르기 때문입니다.

| `entry` | 뜻 | 어디서 왔나 |
|---|---|---|
| `FAST` | `open`으로 연 fresh Fast run | composite Phase 00 한 장이 계획 정본 |
| `FAST-CONVERTED` | `convert`로 넘어온 전환 run | 기존 00~04가 그대로 정본, 문서에 `Fast-Audit-Run` 없음 |
| `UNKNOWN` | opener 레코드를 읽을 수 없는 run | 감사 손상·수기 편집·옛 기록. 증거로 쓰지 말고 `sage validate`로 진단 |

`UNKNOWN`은 "Fast가 아님"이 아니라 **판별 불가**입니다. 그 run의 증거로 게이트를 통과시키려 하지
말고, 감사 무결성을 먼저 확인하십시오.

Fast 명령은 `pdca.fast_cycle.enabled: true`인 L2/L3에만 열립니다. 실제 Risk Level은 별도로 유지되고,
`--level`은 적용할 Fast 리뷰 계약입니다. `open`은 필수 입력 셋을 모두 검증한 뒤에만 00과 감사를 쓰며,
활성 Fast run이 있으면 `sage cycle clear`와 다른 stem 전환을 막습니다. 정상 순서는
`fast-cycle close` 뒤 `cycle clear`이고, 중단은 `fast-cycle abort` 뒤 `cycle clear`입니다.

## 리뷰와 루프

| 명령 | 역할 |
|---|---|
| `sage review` | 새 same-runtime headless reviewer 실행 |
| `sage cross-check --packet-file FILE` | 반대 runtime의 cross-model reviewer 실행 |
| `sage review-loop open [--cycle-stem S --lenses CSV]` | review loop 시작; Fast는 stem·렌즈를 exact 결속 |
| `sage review-loop round [... --lens-receipts CSV] [--survived-by-severity P0=N,P1=N,P2=N,P3=N]` | finding, 반박, 수정 결과와 Fast 렌즈 수행 영수증, 심각도별 잔여 영수증 기록 |
| `sage review-loop next` | 결정론적 계속/종료 권고 |
| `sage review-loop close` | `--result APPROVED|BLOCKED`로 loop 종료 |
| `sage review-loop close --reason USER_AUTHORIZED_EARLY --authorization-reason R --confirmed-by W --confirm USER_AUTHORIZED_EARLY` | 사용자 승인으로 수렴 전 종료 (보증 저하 표기 필수) |
| `sage retro --feature STEM` | 완료 사이클 회고 노트와 distillation 입력 생성 |
| `sage retro --check NOTE` | 회고 노트가 빈 템플릿이 아닌지 검사 |

조기 종료는 `pdca.review_loop.early_completion.enabled: true`가 필요하고, `sage review-loop next`가
아직 `CONTINUE`를 권고하는 상태에서만 의미가 있습니다. 반복 횟수 면제가 아니라 **잔여 비차단 위험을
사용자가 명시적으로 인수**하는 것이라, 다음은 승인으로도 통과하지 않습니다 — 라운드 0건 또는
`minimum_completed_rounds` 미만, `severity_block` 심각도의 미해결 finding, architecture escalation과
`BLOCKED_ARCH`, Done Criteria 미해결과 revision 재실행 누락, acceptance `FAIL`,
waiver 없는 필수 `NOT TESTED`, 감사 손상과 chain/seq 실패, 결속 불일치.

판정 토큰은 호환을 위해 `APPROVED`를 유지하므로, Phase 05 문서가 어떻게 도달했는지를 적습니다.
차단 여부를 정하는 것은 표기의 **존재가 아니라 값**입니다. `Review-Assurance:
REDUCED_BY_USER_AUTHORIZATION` 또는 `Review-Close-Reason: USER_AUTHORIZED_EARLY` 중 하나라도 적혀
있으면 보증 저하를 자칭한 것으로 봅니다. 자칭했거나 감사가 실제로 조기 종료로 닫혔다면, 네
표기(`Review-Assurance`, `Review-Close-Reason`, `Review-Rounds`, `Residual-Findings`)가 fence 밖에
정확히 하나씩 있어야 하고 값이 감사 레코드와 일치해야 합니다. 정상 종료한 run이 보증 저하를
자칭하면 차단되고, 반대로 조기 종료한 run이 표기를 빠뜨려도 차단됩니다 — 후자는 서버 권위도
같은 기준으로 봅니다. `Review-Rounds: 3` 같은 중립 표기 한 줄만 있는 것은 막지 않습니다.
`Review-Rounds`의 `(configured max: <max>)`도 대조 대상입니다 — 그 값이 "몇 번 중 몇 번"의 분모라,
부풀리거나 낮춰 적으면 얼마나 건너뛴 리뷰인지가 다르게 읽힙니다. 상한을 설정하지 않은 프로젝트는
감사와 같은 낱말인 `unbounded`를 적습니다. `--survived-by-severity`의 합계는 `--survived`와
정확히 같아야 합니다 — `P0=0`만 적어 차단 finding을 숨기는 것을 막습니다.

조기 완료가 인수하는 것은 리뷰가 남긴 finding이지 미검증 요구사항이 아닙니다. 선택된 Phase 04에
acceptance `FAIL`이나 exact waiver 없는 필수 `NOT TESTED`가 남아 있으면 조기 완료가 거부되고 감사
append는 0건입니다. 판정은 Phase 06 리포트 게이트와 **같은 정책·같은 파서**를 씁니다 — `verification.
acceptance`를 쓰지 않는 프로젝트에는 없던 검사가 새로 켜지지 않습니다. 다만 build/test/lint 결과는
Phase 03 산문에만 있어 어떤 게이트도 읽지 못합니다. 필수 검증이 실패한 상태의 조기 완료는 엔진이
막지 못하니 사람이 막아야 합니다.

## 지식과 컨텍스트

| 명령 | 역할 |
|---|---|
| `sage knowledge scan` | 개발 전 Obsidian vault 검색 결과를 `.sage/knowledge_scan.md`에 기록 |
| `sage knowledge write-back --append-log` | 완료 지식을 vault 노트와 `wiki/log.md`에 반영 |
| `sage context snapshot --cycle-stem STEM --phase ID` | 완료 phase의 profile, manifest, 문서 hash packet 저장 |
| `sage context restore --snapshot PATH` | snapshot과 현재 source를 검증하고 재개 briefing 생성 |

## CI 권위

| 명령 | 역할 |
|---|---|
| `sage authority inspect` | base/head 변경과 최고 위험도 검사 |
| `sage authority attest` | exact PDCA evidence attestation 생성 |
| `sage authority gate` | 보호된 CI에서 attestation과 현재 변경을 결속해 판정 |

## 표시 언어

전역 `--lang` 은 **하위 명령 앞**에 옵니다. 이 자리를 지키지 않으면 그대로 실패합니다 —
`sage doctor --lang en` 은 지원하는 형태가 아닙니다.

```text
sage [--lang {ko,en}] <command> [command options]
```

```bash
sage --lang en doctor        # 이 실행에만 적용
```

매번 붙이지 않으려면 Git이 추적하지 않는 `sage/project-profile.local.yaml` 에 적어 둡니다.

```yaml
interface:
  language: en      # 없으면 ko
```

우선순위는 `--lang` → local profile → `ko` 입니다. Hook은 `--lang` 을 받지 않으므로 local
profile과 기본값만 따릅니다. 이 설정은 공유 profile·`project-profile.json`·manifest·profile
hash 어디에도 들어가지 않습니다 — 언어는 키보드 앞에 앉은 사람의 속성이지 프로젝트 거버넌스가
아닙니다. **표시 언어는 판정을 바꾸지 않습니다**: 같은 입력이면 `ko` 와 `en` 의 상태·종료코드·
`message_key` 가 같고, 사람이 읽는 문장만 달라집니다.

Phase 00~06 문서를 쓰는 언어는 이것과 **별개 결정**이며 사이클마다 `Document-Language:` 로
한 번 고정합니다. 자세한 규칙은 `templates/core/framework/docs/agent/language-policy.md` 에
있습니다.

## 공통 종료코드

명령별 세부 계약은 `--help`와 출력이 우선합니다. 일반적으로 `0`은 PASS, `1`은 검증 FAIL,
`2`는 도구·게이트 오류 또는 BLOCK, `3`은 STALE을 의미합니다. Hook에서는 `0`이 통과,
`2`가 차단입니다.
