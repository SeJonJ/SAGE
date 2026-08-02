# [Base Plan] SAGE 10-i 소비자 생성·확장 계약 통합 하드닝

Cycle-Stem: `sage-consumer-generation-extension-contract-hardening`
Risk Level: L3
Status: IMPLEMENTED / INDEPENDENT REVIEW FINDINGS ADDRESSED (2026-08-02, 미커밋·로컬 재검증 완료)

## 1. Context

ChatForYou에 SAGE 0.9.76을 역적용하는 과정에서 두 결함군이 확인됐다.

1. 생성 온보딩 문서가 Markdown hard break용 줄 끝 공백을 내보내 host/scope 전환 시
   `git diff --check`를 실패시킨다. 또한 `checklist_scan_targets`는 schema가 배열만 요구하지만
   Phase 04 runtime은 각 원소를 `{label, glob, is_impl?}` 객체로 가정한다. 잘못된 profile이
   strict validation과 generate를 통과한 뒤 실제 gate에서 exit 1 traceback 또는 무음 무동작으로 나타난다.
2. `$sage-asset`이 안내하는 project-authored hook의 `spec + pure core` 저작 흐름은 신규 hook을
   등록할 수 없다. generate는 manifest 선등록과 양 host adapter를 요구하고, runtime은 고정 CORE ID만
   dispatch하므로 설정을 손으로 추가해도 unknown ID가 exit 0으로 통과한다.

첫 구현 시도는 두 결함을 한 diff에서 처리했지만 project hook 등록용 별도 rollback을 추가하면서
snapshot 시점, 부분쓰기, chmod 실패, 동시 변경, manifest 복구 등 실패면이 반복해서 발견됐다.
이번 설계는 10-i-1과 10-i-2를 **한 번에 개발·검증**하되, 새 트랜잭션을 만들지 않고 이미 install에서
검증된 destination lock과 filesystem journal을 generate 전체에 적용한다.

## 2. Goal

- `checklist_scan_targets`의 authored YAML, compiled JSON, schema, validator, runtime 의미론을 일치시킨다.
- 모든 지원 hook 진입점이 profile/contract 손상을 actionable exit 2로 동일하게 차단한다.
- 유효한 project hook `spec + core`를 manifest 직접 편집 없이 양 host에 create-only 등록한다.
- 등록된 project hook을 안전하게 동적 dispatch하고, 등록 손상이나 core 손상은 fail-closed한다.
- `sage generate --kind hook --write`가 기록하는 모든 파일을 하나의 failure-atomic 명령으로 만든다.
- install force-upgrade, source checkout, wheel 설치본, POSIX/Windows, Claude/Codex에서 같은 계약을 유지한다.

## 3. Non-Goals

- backend/frontend 이름, 컴포넌트 문서 개수, REQUIRED/N/A 판정 같은 ChatForYou 고유 정책
- CORE `pre-phase4-checklist-gate`의 체크박스·suffix·block/warn/ok 의미론 변경
- project hook이 CORE hook을 덮거나 완화하는 overlay 기능
- Codex global/project-local 중복 사본 자동 삭제
- project hook 단일 host 등록. 신규 project hook은 양 host 등록만 지원한다.
- 적대적 사용자가 manifest와 core를 함께 재작성하는 경우의 외부 신뢰 앵커
- adapter/shim 직접 실행 시의 YAML↔compiled JSON freshness 검사. 그 검사는 `sage-hook`에만 있고 CORE hook도
  같으며, host 등록 command는 `sage-hook`이다(§5.4 경계)

## 4. Global Invariants

### G1. Command-wide all-or-nothing

`sage generate --kind hook --write`는 다음 write set 전체를 하나의 트랜잭션으로 취급한다.

- `sage/project-profile.json`
- `docs/sage_harness/.manifest.json`
- 신규 project hook의 양 host canonical adapter
- `.claude/settings.json`과 `.codex/hooks.json`
- `.claude/hooks/*.sh`와 `.codex/hooks/*.sh`

성공하면 모두 반영되고, 실패하면 실행 전 bytes, mode, symlink/regular-file 종류, 부재 상태로 복구한다.
profile 검증이 성공했더라도 이후 hook 등록이나 stamp가 실패하면 compiled profile도 복구한다.

### G2. No mutation before complete preflight

destination lock을 획득한 뒤 모든 입력을 읽고 최종 산출물을 메모리에서 계산한다. profile, manifest,
spec, core, runtime, host 설정 중 하나라도 읽거나 검증할 수 없으면 첫 파일을 쓰기 전에 실패한다.
manifest는 등록용 중간 entry를 먼저 기록하지 않는다. 신규 entry와 hash/stamp를 포함한 최종 문서를
메모리에서 완성한 뒤 한 번만 쓴다.

### G3. Existing transaction primitive only

`sage.install_transaction.DestinationLock`과 `InstallTransaction`의 검증된 동작을 재사용한다.
project hook 전용 snapshot/rollback 클래스는 만들지 않는다. generate와 install이 같은 destination lock
identity를 사용해 서로 동시에 쓸 수 없게 한다.

모든 write는 다음 순서를 지킨다.

1. `stage_write(path)`
2. `declare_file_output(path, expected_bytes, expected_mode)`
3. 같은 디렉터리 temp에 완결 기록 및 mode 적용
4. `os.replace`
5. `record_output(path)`

write 성공 뒤에 journal ownership을 기록하지 않는다. 그래야 부분쓰기나 chmod 실패 이전에도 rollback이
대상을 안다. mode는 temp에 적용한 뒤 replace하므로 완성 파일 노출 후 chmod 실패 경로를 만들지 않는다.

### G4. Concurrent change preservation

SAGE 명령끼리는 destination lock으로 직렬화한다. 수동 편집이나 lock을 따르지 않는 프로세스가 preflight
이후 입력을 바꾸면 fingerprint drift로 첫 write 전에 차단한다. SAGE가 쓴 뒤 rollback 전에 파일이 외부에서
변경되면 그 파일을 삭제하거나 덮지 않고 보존하며 rollback incomplete를 명확히 보고한다.

이 규칙은 host 출력뿐 아니라 manifest와 canonical adapter에도 동일하게 적용한다. 디렉터리 차집합으로
새 파일을 지우지 않으며, transaction이 정확히 stage한 경로만 건드린다.

### G5. Deterministic permissions

- compiled profile: 신규/교체 모두 `0600`
- canonical adapter와 host shim: `0755`
- 기존 manifest/host JSON: 기존 mode 보존
- 신규 manifest/host JSON: `0644`

프로세스 umask를 읽거나 바꾸지 않는다. rollback은 mode까지 복구한다.
기존 release가 만든 compiled profile이 `0644`여도 다음 generate에서 `0600`으로 강화된다. hook을 다른 UID로
실행하는 CI/컨테이너에는 호환성 영향이 있으므로 release note와 profile reference에 migration 계약을 명시한다.

## 5. Architecture

### 5.1 GeneratePlan

hook generate를 read/validate/render와 apply로 분리한다.

```text
acquire destination lock
  -> read and fingerprint all inputs
  -> compile profile in memory
  -> validate profile contract in memory
  -> discover/validate optional project-hook registration
  -> render final manifest and every host output in memory
  -> create InstallTransaction(expected fingerprints, write_roots=[dest])
  -> apply declared writes atomically
  -> verify every output fingerprint
  -> commit journal
```

계획 객체는 최소한 다음을 가진다.

```text
GeneratePlan
  writes: ordered[path -> {bytes, mode}]
  final_manifest: object
  registered_hook_id: string | null
  diagnostics: ordered messages
```

dry-run은 같은 plan builder를 실행하되 transaction apply만 하지 않는다. dry-run과 write가 다른 validator나
renderer를 타지 않는다.

### 5.2 Profile contract SSOT

`validate_checklist_scan_targets(value, *, present)` 같은 순수 validator를 둔다. 반환은 구조화된 issue 목록이며
schema 오류 문자열 파싱에 의존하지 않는다.

```text
key absent                         PASS, effective []
explicit []                        PASS
null/string/number/object          FAIL
item                               non-empty object required
required keys                      label, glob
optional key                       is_impl (bool only, default false)
unknown/non-string item key        FAIL
```

`label`은 비어 있지 않은 1..80자 문자열이어야 하며 CR/LF/NUL과 출력 제어문자를 거부한다.
`glob`은 비어 있지 않은 project-relative 문자열이어야 한다. 다음은 거부한다.

- POSIX absolute path
- Windows drive absolute, UNC, rooted path
- Windows drive-relative path (`C:private/*.md`)
- `..` path segment
- CR/LF/NUL 및 제어문자

schema는 같은 형태를 독립적으로 표현한다. 테스트는 `jsonschema`를 직접 호출해 schema 자체를 검증하고,
수동 validator와 공통 sample corpus의 판정이 같은지 대조한다. jsonschema 미설치 환경에서는 수동 validator가
동일하게 fail-closed한다.

compile 순서는 YAML parse -> materialize in memory -> validate in memory -> transaction plan이다. 검증 실패 시
기존 compiled JSON의 bytes, mode, mtime이 모두 불변이다.

### 5.3 Runtime path confinement

정적 glob 검증만 신뢰하지 않는다. 실제 match마다 `realpath`를 계산하고 project root realpath 안에 있는
regular file만 snapshot에 포함한다. symlink leaf/ancestor로 root 밖으로 나가면 gate contract 오류로 차단한다.
저장소 밖 내용은 decision evidence가 될 수 없다.
`**`가 매치한 디렉터리는 evidence가 아니므로 건너뛴다. symlink ancestor를 포함한 root 이탈,
symlink leaf match, FIFO/device 등 그 밖의 비정규 경로는 서로 다른 actionable 원인으로 차단한다.

### 5.4 Entrypoint SSOT

`sage-hook`, Claude thin adapter, Codex thin adapter는 같은 guarded dispatch를 호출한다. fail-closed hook 목록,
profile tri-state, project-hook entry tri-state, 예상 가능한 contract 오류와 예상 밖 internal 오류의 exit 정책은
runtime 한 곳이 소유한다.

- profile absent: 기존 hook별 정책 유지
- profile malformed/unreadable: gate hook exit 2, logger 등 advisory hook은 기존 fail-open 유지
- contract invalid: actionable message + gate exit 2
- expected project resolution/load error: actionable message + exit 2
- unexpected gate exception: internal dispatch failure로 표면화 + exit 2
- unexpected advisory exception: stderr 진단 + 기존 exit 0

catch-all을 profile 오류로 가장하지 않는다. contract validator 오류와 internal exception 메시지를 구분한다.
Stop retry의 기존 `stop_hook_active` 탈출 계약은 보존한다.

#### 경계 — profile freshness는 entrypoint SSOT가 아니다

위 tri-state는 **주어진 compiled profile이 유효한가**만 다룬다. **그 compiled profile이 현재 YAML과 같은
세대인가**(`materialize_profile(yaml) == json`)는 별개 검사이며 `sage-hook`(`hook_entry._prepare_gate_profile`)
한 곳에만 있다. adapter와 shim은 `SAGE_PROFILE`을 직접 주입한 뒤 `run_hook.py`를 exec하므로 이 비교를 거치지
않는다. CORE hook과 project hook에 동일하게 적용되는 기존 성질이며, 이번 범위에서 바꾸지 않는다.

- host가 등록하는 command는 `sage-hook`이다(`settings.json` / `hooks.json`). 따라서 소비자 실행 경로에서는
  stale profile이 정책을 통과시키지 못한다.
- `.claude/hooks/*.sh` shim과 `scripts/sage_harness/hooks/adapters/**`를 **직접** 실행하면 freshness 검사 없이
  디스크의 compiled JSON을 그대로 쓴다. 테스트·디버깅용 직접 호출이 여기 해당한다.
- 확인된 동작: YAML만 의미 있게 바꾸고 재생성하지 않은 상태에서 CORE·project hook 모두 adapter/shim은 통과,
  `sage-hook`은 "project-profile.yaml과 project-profile.json이 다릅니다"로 exit 2.
- 닫으려면 adapter가 `sage-hook`을 경유해야 하는데 이는 CORE adapter 전체의 실행 계약 변경이다. 별도 항목으로
  다루고, 이 문서의 §5.4 tri-state 요구사항(AC4의 "invalid profile")과 혼동하지 않는다 — stale은 invalid가 아니다.

## 6. Project-Authored Hook Contract

### 6.1 Authored inputs

신규 hook 저작자는 다음 두 파일만 작성한다.

```text
docs/sage_harness/hooks/<id>.md
scripts/sage_harness/hooks/<id>_core.py
```

등록 명령은 정확히 다음 형태다.

```text
sage generate --kind hook --id <id> --write --target both
```

신규 ID에서 `--target claude` 또는 `--target codex`는 첫 write 전에 exit 2로 거부한다. 기존 등록 hook의
단일-target 재생성은 기존 CLI 호환을 위해 유지한다.

### 6.2 ID and spec

- ID는 lowercase kebab-case만 허용한다.
- CORE hook ID와 충돌할 수 없다.
- spec frontmatter의 `id`는 파일명과 같고 `kind`는 `hook`이어야 한다.
- frontmatter는 PyYAML structured parsing을 사용한다.
- duplicate key, non-string key, unknown top-level runtime, unknown binding field를 거부한다.

runtime binding은 양 host 모두 필수다.

```text
event                           PreToolUse exactly
claude matcher                  non-empty subset of Write|Edit|MultiEdit
codex matcher                   apply_patch exactly
timeout                         optional int 1..600; bool rejected
matcher whitespace/empty/dup    rejected, not normalized
```

검증한 원본 값을 host 설정에 그대로 기록한다. 검증 시 strip하고 기록 시 원문을 쓰는 이중 표현을 만들지 않는다.
배포 `hook.spec.md` 템플릿은 machine-readable binding을 frontmatter에 포함한다.

### 6.3 Core and decision

core는 모듈 최상단 `CONTRACT_VERSION`과 `decide(event, profile, snapshot)`을 제공한다.
`plan_reads(event, profile)`은 선택이다. manifest의 `adapter_contract_version`과 core 값은 양쪽 모두 존재하고
일치해야 한다. 어느 한쪽이 없으면 대조를 생략하지 않고 차단한다.

등록된 project hook은 core가 profile을 읽지 않아도 freshness가 확인된 compiled profile을 필수로 요구한다.
없거나 YAML과 다르면 exit 2다. `event`와 `snapshot`의 공개 계약은 다음과 같다.

```text
event.hook_id                  registered project hook id
event.hook_event_name          PreToolUse
event.runtime                  claude | codex
event.session_id               string, 없으면 ""
event.changes                  host 입력에서 추출한 [{path, op}], 없으면 []
snapshot.glob_results          plan_reads glob별 project-relative regular-file 목록
snapshot.files                 project-relative path -> UTF-8 text
```

decision은 다음 계약을 만족해야 한다.

```text
status=block                   exit_code=2
status=ok|warn|skip            exit_code=0
message                        string
unknown status/field/type      exit 2
```

### 6.4 Canonical adapter and manifest

generator는 ID만으로 결정되는 양 host canonical adapter를 create-only scaffold한다. adapter가 이미 있으면
바이트를 덮지 않고 기대 canonical 내용과 계약을 검증한다. 신규 manifest entry는 `origin: project`,
`form: core_adapter`를 명시한다. manifest schema와 install preserve allowlist가 이 필드를 이해해야 한다.

`sage install --force`는 project-origin entry/spec/core/adapter를 보존한다. 등록 후 origin/form/contract stamp가
손상되면 validate가 FAIL한다. 자동 복구는 generator가 결정론적으로 소유한 stamp 필드에만 허용하며,
canonical form 변경처럼 의미가 달라지는 손상은 자동 변환하지 않는다.

### 6.5 Runtime tri-state and safe loading

manifest와 entry는 다음 상태를 구분한다.

```text
manifest absent + unknown id                  unregistered version-skew, exit 0
manifest unreadable/non-object                exit 2
entry absent                                  unregistered version-skew, exit 0
entry malformed/not project/core_adapter      exit 2
registered project core missing/broken        exit 2
registered project contract drift             exit 2
registered project valid                      safe dispatch
```

project core 경로는 strict ID에서만 계산하고 expected hook root의 exact filename만 허용한다. `realpath` containment,
regular-file 검사, symlink escape 차단을 import 전에 수행한다. 임의 module name이나 sys.path 검색으로 core를 찾지 않는다.

## 7. Failure Matrix and Required Regression Teeth

### 7.1 Profile and schema

- string/null/number/object/empty item/missing key/unknown key/wrong bool을 raw YAML, compiled JSON,
  direct validator, direct jsonschema에서 대조한다.
- POSIX absolute, Windows absolute/UNC/rooted/drive-relative, `..`, control character를 거부한다.
- symlink match가 root 밖 파일을 읽지 못하고 gate exit 2를 낸다.
- invalid generate 뒤 compiled JSON bytes/mode/mtime과 모든 다른 write target이 불변이다.
- onboarding host/scope 전환과 반복 install 뒤 `git diff --check`가 통과한다.

### 7.2 Entrypoints

- `sage-hook`, Claude adapter, Codex adapter를 실제 subprocess로 실행한다.
- malformed profile과 checklist contract 오류가 모두 exit 2이고 traceback 없이 actionable해야 한다.
- core import 실패와 unexpected gate exception도 exit 2이며 profile 오류로 잘못 설명하지 않는다.
- advisory hook의 기존 fail-open과 Stop retry를 회귀로 보존한다.

### 7.3 Registration lifecycle

- valid orphan spec+core가 hand-edited manifest 없이 등록된다.
- missing/malformed spec, missing/broken core, CORE collision, bad ID, bad binding, bad decision을 거부한다.
- 신규 단일-target 등록을 거부하고 양 host 설정이 같은 core를 실행한다.
- 전체 기존 hook registration을 보존한다.
- malformed manifest file과 malformed project entry를 unregistered로 오인하지 않는다.
- `--id` 없는 전체 generate도 authored spec+core를 strict project contract로 검사하며 CORE 간이 파서로 우회하지 않는다.
- `install --force` 후 project entry와 authored files가 남고 재생성·validate가 통과한다.
- 배포된 `hook.spec.md`로 실제 신규 hook을 만들 수 있다.

### 7.4 Transaction fault injection

각 단계 바로 전과 바로 후에 예외를 주입한다.

- input fingerprint/snapshot
- compiled profile write
- first/second canonical adapter write
- manifest write
- Claude/Codex host JSON write
- first/middle/last shim write
- output verification
- commit backup cleanup

부분 write, temp write, mode 적용, replace, fsync/close, output record 실패를 포함한다. 모든 실패에서 전체 tree
snapshot이 실행 전과 같아야 한다. 예외는 traceback 대신 rc=1/2 계약에 맞게 표면화한다.

### 7.5 Concurrency

- install vs generate, generate vs generate lock 경합은 두 번째 명령이 첫 write 전에 busy로 실패한다.
- preflight 후 input 변경은 drift로 실패한다.
- rollback 전 manifest/adapter/host output 외부 변경은 보존하고 rollback incomplete를 보고한다.
- 실행 중 생긴 무관 파일은 삭제하지 않는다.
- path bytes가 같아도 mode가 바뀐 외부 변경을 감지한다.

### 7.6 Mutation requirements

다음을 제거하거나 되돌리면 최소 한 테스트가 정확한 이유로 실패해야 한다.

- schema items/pattern 또는 수동 validator 호출
- drive-relative/root containment 검사
- entrypoint guarded dispatch
- core와 manifest 양쪽 contract version 요구
- matcher/event/timeout/non-string/duplicate-key 검사
- 신규 `--target both` 강제
- transaction stage-before-write, declared output, atomic writer, output verification
- manifest single-write plan
- lock 획득
- concurrent-change preserve guard
- template frontmatter binding
- wheel bundle의 신규 runtime/contract 파일

mutation은 단순 rc만 단언하지 않고 실패 사유까지 확인한다. 다른 결함 때문에 우연히 같은 rc가 나온 테스트는
방어선으로 인정하지 않는다.

## 8. Documentation and Packaging

- `docs/profile-reference.md`와 `.en.md`에 checklist target 계약과 migration 오류를 동형으로 추가한다.
- `templates/hook.spec.md`, 양 host `sage-asset` skill, bootstrap authoring 문서를 실제 CLI 계약과 맞춘다.
- 사용자-facing README를 수정한다면 한글/영문을 같은 변경에서 갱신한다.
- 새 runtime/contract 모듈은 source distribution과 wheel bundle, `hook_runtime_hash`에 포함한다.
- wheel smoke는 clean venv에서 install -> profile compile -> project hook register -> 양 host dispatch -> validate를 실행한다.

## 9. Acceptance

- `sage generate --kind hook --id <new> --write --target both` 한 번으로 profile compile과 project hook 양 host
  등록이 완료되며, manifest나 adapter를 손으로 편집하지 않는다.
- 어느 write 단계가 실패해도 외부 동시 변경이 없는 한 실행 전 filesystem snapshot과 동일하다.
- 외부 동시 변경이 있으면 그 변경을 파괴하지 않고 명시적인 incomplete rollback으로 실패한다.
- 저장소 밖 파일, malformed profile, malformed manifest/entry, missing/broken core가 gate 증거 또는 exit 0/1로 통과하지 않는다.
- Claude와 Codex가 같은 project core decision을 실행한다.
- none/Claude/Codex official hook suite, direct schema parity, source tests, wheel smoke, POSIX/Windows tests,
  `sage validate --kind hook --check --schema`, `git diff --check`, mutation suite가 모두 통과한다.
- 독립 리뷰가 코드 읽기만이 아니라 fault injection과 소비자 wheel lifecycle을 재현해 승인한다.

## 10. Implementation Boundary

10-i-1과 10-i-2를 별도 릴리즈나 별도 완료 판정으로 나누지 않는다. 한 워킹트리, 한 통합 design,
한 acceptance matrix로 개발하고 최종 검증도 한 번에 수행한다. 내부 모듈은 profile contract,
project-hook contract/runtime, generate plan/transaction으로 분리해 책임과 테스트 격리를 유지한다.

## 11. Implementation Result (2026-08-01)

- checklist schema/manual/runtime 계약과 realpath confinement를 구현하고 공통 corpus 18건의 판정을 대조했다.
- project hook의 strict spec/core 계약, create-only 양 host 등록, safe generic dispatch와 validate/install 보존을 구현했다.
- generate는 manifest 첫 읽기 전에 destination lock을 잡고 compiled profile, manifest, adapters, host JSON,
  shims를 기존 `InstallTransaction` 하나로 기록한다. 최소 fixture의 출력 12곳과 output record/verify 실패를
  주입해 외부 변경이 없을 때 전체 tree가 원복되는지 확인했다. 독립 검증은 전체 설치 소비자의 CORE+project
  shim을 포함한 출력 22곳을 각각 실패시켜 원복 실패 0건을 확인했다.
- clean wheel Python 3.14에서 template -> register -> Claude/Codex adapter -> validate 수명주기를 실행했다.
  이 검증에서 source import 순서가 숨긴 `importlib.util` 명시 import 누락을 발견해 수정·회귀화했다.
- none/Claude/Codex 공식 hook suite는 모두 `ALL HOOK TESTS PASS`, wheel smoke와 manifest/schema validate도 PASS다.

2026-08-02 독립 검증에서 확인된 세 항목을 재현 후 반영했다. recursive `**`가 매치한 디렉터리는 snapshot에서
건너뛰고, `--id` 없는 전체 generate도 authored project hook을 strict parser로 검증하며, install/generate의
manifest 직렬화는 재귀 key 정렬로 통일했다. compiled profile `0600`, project hook profile 필수,
`event.changes`/snapshot 구조를 release-facing 문서에 명시했다.
재검증 후 production 호출이 없는 구 `_stamp_manifest` 비정렬 writer도 제거하고, 해당 테스트를 실제
`gen.run()` transaction 경로의 version stamp와 manifest write failure 검증으로 이전했다.

수정 후 none/Claude/Codex 공식 suite, 25건 project lifecycle, clean wheel, all-kind schema validate,
compileall, diff check를 재검증했다. 독립 재리뷰, commit, release는 아직 수행하지 않았다.
사용자 명시 없이 commit하지 않는다.
