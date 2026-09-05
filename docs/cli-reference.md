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

### `sage uninstall [--global|--all]`

설치한 SAGE 자산을 되돌립니다. **패키지 자체는 지우지 않습니다** — CLI 는 `pipx uninstall
sage-harness` 로 따로 제거합니다.

| 범위 | 대상 |
|---|---|
| `sage uninstall [--dest PATH]` | 현재(또는 지정) 프로젝트의 SAGE 자산 |
| `sage uninstall --global` | `$CODEX_HOME/skills/` 의 Codex 전역 SAGE CORE skill |
| `sage uninstall --all [--dest PATH]` | 둘을 하나의 transaction 으로 |

순서가 계약입니다 — 불변 계획 출력(기준 확보) → 확인 또는 `--yes` → 정렬 lock → 지문 대조 →
경계 재확인 → backup → 실행 → 검증 → commit → cleanup → unlock. `--check` 는 첫 단계 뒤 끝나고
아무것도 바꾸지 않습니다 — lock 도 잡지 않습니다. 취소하면 byte 하나 바뀌지 않고 `CANCELLED(0)`
입니다.

**기준은 계획을 보여 준 그 시점의 것입니다.** 확인 질문이 떠 있는 동안 대상 파일을 고치면 지우지
않고 `BLOCKED(2)` 로 멈춥니다 — 사용자가 보고 동의한 상태와 지금 디스크가 다르기 때문입니다.
디렉터리는 안에 있는 파일까지 봅니다.

같은 위치에서 다른 SAGE 명령이 실행 중이면 차단됩니다. `install`·`generate` 와 **같은 lock** 을
쓰므로, 한쪽이 배치하는 동안 다른 쪽이 지우는 일이 생기지 않습니다. lock 은 프로세스가 끝나면
자동으로 풀리므로 손으로 치울 파일이 남지 않습니다.

뒷정리(cleanup)가 실패해도 **명령은 성공입니다.** 요청한 제거는 이미 끝났고, 치우지 못한 임시
보관소 경로만 알려 드립니다.

**실제 제거의 지원 범위는 POSIX 와 Windows 11 데스크톱 workstation · x64 · 64-bit Python · 로컬 NTFS 입니다.**
이 명령의 안전성은 첫 변경 전에 대상의 부모 디렉터리를 열어 붙드는 데서 나옵니다 — 그 뒤에는
상위 경로 이름이 어떻게 바뀌어도 작업이 원래 디렉터리로 갑니다. 그 결속을 만들 수 없는 환경
(네트워크·UNC 경로, NTFS 가 아닌 볼륨, 필요한 native 기능 부재, **32-bit Python**,
**x64 가 아닌 아키텍처**)에서는 **첫 변경 전에** `uninstall.unsafe_platform` 으로 거부합니다.

32-bit Python 이 여기 있는 이유는 이 명령의 native 구조체 배치가 Win64 ABI 하나로 계산되기
때문입니다. 32-bit 프로세스에서는 그 배치가 달라지고, **검증하지 않은 ABI 배치라 native 호출의
결과를 신뢰할 수 없습니다.** 실제 수요가 생기면 후속 개발로 다룹니다.

**native ARM64 Python 프로세스는 자동 제거를 거부합니다.** 폭도 SKU 도 build 도 조건을
만족하므로 폭만 보는 관문은 그것을 그대로 통과시킵니다. 그러나 이 명령이 실제로 돈 적이 있는
아키텍처는 x64 하나뿐이고, 되돌릴 수 없는 명령에서 "아마 될 것이다" 는 실행할 이유가 되지
않습니다. 실제 수요가 생기면 별도 후속 개발에서 검증합니다.

**ARM64 Windows 에서 x64 에뮬레이션으로 실행하는 구성은 다르게 갈릴 수 있습니다.** 그 경우
아키텍처 보고 결과는 Python 버전과 실행 환경에 따라 달라질 수 있어 여기서 단정하지 않습니다.
그 구성이 x64 프로세스 ABI 관문을 통과할 수는 있지만, 통과가 **ARM64 하드웨어 지원을 보장한다는
뜻은 아닙니다.** 정식 지원 범위에도 검증 증거 범위에도 포함하지 않습니다.

**범위 밖은 두 종류이고, 화면이 다릅니다.** 하나로 접으면 고칠 수 있는 것과 고칠 수 없는 것이
같은 화면에 남습니다.

**(1) 지원 정책의 범위 밖** — 이 판정은 SKU 와 build 만 봅니다. 볼륨·native 기능 같은
capability 는 이 단계에서 **판정하지 않습니다.**

| 환경 | 진단 |
|---|---|
| Windows 10 데스크톱 | `uninstall.windows_10_manual_only` (자동 제거는 후순위) |
| Windows Server · 도메인 컨트롤러 | `uninstall.windows_sku_not_supported` |

지울 것이 남아 있으면 `--check` 든 `--yes` 든 **파일 하나 바꾸기 전에** `BLOCKED`(2) 로
멈추고, 확인 prompt 조차 뜨지 않습니다. 자동 제거가 이 환경에서 결코 일어나지 않으므로 계획만
보여 주면 돌 것처럼 보이는 화면이 되기 때문입니다. 그 화면은 삭제·부분 제거·보존·차단 네
목록을 하나도 접지 않고 그대로 보여 주고 손으로 정리하는 순서를 함께 냅니다 — 그 목록을 따라
하면 자동 제거와 같은 결과가 됩니다.

**(2) capability 제한** — 네트워크·UNC, 비 NTFS 볼륨, 32-bit Python, ARM64, native 기능 부재.
`uninstall.unsafe_platform` 입니다. 이쪽은 **`--check` 가 계획을 그대로 보여 줍니다.** 볼륨을
바꾸거나 다른 root 를 고르면 참이 될 수 있는 조건이라, 계획까지 막으면 고칠 수 있는 것을 고칠
수 없는 것처럼 보여 주게 됩니다. 거부는 실제 mutation 요청에만 걸립니다.

`COMPLETE`(0) 은 **지울 것도 보존 잔재도 없는 완전히 깨끗한 상태**에서만 나옵니다. 안내대로 손
으로 정리한 뒤 손상된 host 설정 같은 보존 항목만 남아 있으면 그다음 실행은 `PARTIAL`(1) 이고,
남은 경로와 사유를 다시 냅니다 — 남은 것이 있는데 0 으로 끝나면 그 사실이 화면에서 사라집니다.

거부하거나 실패했을 때는 **무엇을 손으로 정리해야 하는지** 함께 냅니다. 순서는 부분 제거 →
삭제 → 보존이고, 부분 제거 대상은 파일 전체를 지우는 대상이 아닙니다. 되돌리기까지 실패해
남은 상태를 확정하지 못했으면 어떤 경로도 "지워도 된다" 고 안내하지 않습니다. 파괴적 shell
명령은 어떤 경우에도 만들어 주지 않습니다.

**소유권을 추측하지 않습니다.** SAGE 전용 디렉터리와 manifest 가 배치를 기록한 자산만 지웁니다.
`AGENTS.md`·`CLAUDE.md`·`CODEX.md`·`AGENT_GUIDE.md` 는 설치 전에 있었는지 증명할 수 없어 **언제나
보존**하고 경로와 사유를 보고합니다. 전역 사본이 프로젝트 렌더와 다르면 손댔다는 뜻이라 지우지
않습니다. `--force` 나 소유권 우회 옵션은 없습니다.

공유 파일은 SAGE 부분만 건드립니다. `.gitignore` 의 managed block 과 host JSON 의 SAGE hook 등록만
제거하고, marker 가 정상 쌍이 아니거나 JSON 을 읽을 수 없으면 **파일 전체를 보존**합니다 — 손상을
추측해 고치면 사용자 내용이 조용히 사라집니다.

host 설정 파일은 **등록이 있다 · 없다 · 알 수 없다** 셋으로 나뉩니다. 문법이 깨졌거나 UTF-8 이
아니거나 읽을 권한이 없으면 "없다" 가 아니라 **"알 수 없다"** 입니다 — 읽지 못한 것을 없는 것으로
접으면 부재가 곧 통과가 되고, 통과는 삭제로 이어집니다. 알 수 없는 파일이라도 manifest 의
`installed_hosts` 가 그 host 설치를 증명하면 보존 대상으로 보고합니다.

**손대지 못한 host 설정이 남아 있는 동안에는 설치 기록(`docs/sage_harness`)도 함께 보존합니다.**
영수증을 먼저 버리면 다음 실행은 그 파일이 왜 거기 있는지 증명할 방법을 잃습니다. 그 상태의 매
실행은 아무것도 바꾸지 않는 `PARTIAL(1)` 이고 같은 경로를 다시 보고합니다. 사용자가 그 파일을
고쳐서 SAGE 등록을 뺄 수 있게 됐을 때에만 설치 기록이 **마지막 자산으로** 제거됩니다. 잔재가
남은 동안 CLI 패키지를 먼저 지우면 host 가 없는 실행 파일을 부르므로, 그 순서를 함께 안내합니다.

손상은 문장 하나로 뭉개지 않고 **좌표**로 보고합니다 — JSON pointer 위치와 기대·실제 타입, 문법
오류의 행·열, UTF-8 오류의 바이트 오프셋, 읽기 실패의 errno 이름. 설정값·command 원문·주변 JSON·
OS 예외 원문은 싣지 않습니다. 그 내용은 사용자의 것이고 로그와 CI 출력으로 흘러갑니다. 식별자
모양이 아닌 JSON key 는 pointer 에서 가려집니다 — 좌표를 잃는 손해보다 값을 흘리는 손해가 큽니다.

기본(project) 범위는 `$CODEX_HOME` 을 **읽지도 쓰지도 않습니다.** 그래서 전역에 무엇이 남았는지
주장하지 않고, 검사하지 않았다는 사실과 `--all` 을 안내합니다.

| 상태 | exit | 뜻 |
|---|---:|---|
| `COMPLETE` | 0 | 계획한 제거가 끝났고 수동 확인 경로가 없음 |
| `PARTIAL` | 1 | 안전한 삭제는 끝났지만 보존·수동 확인 경로가 남음 |
| `BLOCKED` | 2 | 안전한 계획을 만들 수 없거나 실행 실패 후 rollback |
| `CANCELLED` | 0 | mutation 전에 사용자가 취소 |

`PARTIAL(1)` 은 **실패가 아닙니다.** 최상위 공유 문서를 보존하는 정상 결과가 대부분 여기 해당합니다.
자동화가 이 구별을 읽어야 하면 `--json` 을 쓰세요 — exit code 를 바꾸는 `--allow-partial` 류는
제공하지 않습니다. `0` 을 내주면 "일부만 지워졌다" 가 성공과 구별되지 않고, 그 구별이 이 명령의
핵심입니다. host 설정은 표준 JSON 으로만 읽습니다. 같은 object 안의 중복 key 와 `NaN`·`Infinity` 는 손상으로
판정합니다 — 관대하게 읽으면 우리가 읽은 문서와 host 가 읽는 문서가 달라지고, 지우는 명령에서 그
차이는 곧 "지운다고 말한 것과 지운 것이 다르다" 가 됩니다.

hook handler 는 **종류마다 계약이 다릅니다.** `type` 을 먼저 확정한 뒤 `command` 는 `command`,
`http` 는 `url`, `mcp_tool` 은 `server`·`tool`, `prompt`·`agent` 는 `prompt` 를 요구합니다.

**event 마다 받는 종류도 다릅니다.** host 공식 계약을 그대로 따릅니다 — 다섯 종류를 모두 받는
event, `prompt`·`agent` 를 받지 않는 event, 그리고 `SessionStart`·`Setup` 처럼 `command`·
`mcp_tool` 만 받는 event 가 있습니다. 그 event 가 받지 않는 handler 가 있으면 우리가 이해하지
못하는 문서이므로 SAGE 등록이 보여도 파일을 다시 쓰지 않고 보존합니다. 계약표를 옮겨 둔 host(현재 Claude)에서
우리 표에 없는 event 를 만나면 "전부 허용" 으로 추정하지 않고 보존합니다 — 모르는 것은 모른다고
말하는 편이 낫습니다. Codex 는 그 표를 공유하지 않고 별도 계약으로 관리하므로, 표를 옮기기
전까지 종류를 제한하지 않습니다.
SAGE 소유권 비교와 제거는 **`command` 종류에만** 적용되므로, 같은 자리에 둔 정상 `prompt`·
`agent`·`http`·`mcp_tool` hook 은 손상으로 보고되지 않고 그대로 남습니다. 다른 종류가 우연히
`command` 라는 property 를 갖고 그 값이 SAGE 것과 같아도 제거 대상이 아닙니다. 모르는 종류와
종류별 필수 필드 누락은 파일을 다시 쓰지 않고 보존합니다.

`--global` 자산은 두 가족(CORE id 이름 · `<prefix>-<aid>` 렌더)이 있어 설정에 따라 **같은 경로**를
가리킬 수 있습니다. 그때는 어느 한쪽을 고르지 않고 `uninstall.action_conflict` 로 계획 전체를
`BLOCKED(2)` 로 끝냅니다 — 두 근거가 같은 파일에 다른 결론을 냈다는 것은 그 파일을 무엇으로
아는지 우리가 모른다는 뜻이고, 모르는 상태에서 되돌릴 수 없는 삭제를 고르지 않습니다.

손상된 manifest 의 key·host 이름처럼 **사용자가 쓴 문자열**은 진단에 원문으로 싣지 않습니다.
식별자꼴 이름만 그대로 나오고, 나머지는 가린 뒤 몇 번째 항목인지(`index`)로 위치를 대신합니다.

manifest 의 자산 key 는 `<kind>s/<id>` 형식만 허용합니다. 이 값은 전역 skill 경로에 그대로 붙는
**경로 조각**이라, `skills/../../../x` 같은 key 하나로 계획이 프로젝트 밖을 가리키게 됩니다.

`--json` 은 사람이 읽는 화면과 같은 계획을 소비하므로 두 표현이 다른 판정을 낼 수 없고,
ko·en 어느 언어에서도 byte 동일합니다. 실행형 `--json` 에는 `--yes` 가 필요합니다 — 확인 질문과
JSON 을 같은 출력에 섞지 않습니다.

경로 표기는 화면과 `--json` 이 **같은 함수**를 지납니다. project 자산은 저장소 기준 상대 경로,
전역 자산은 `$CODEX_HOME/skills/...` 로 나오고, 파일 이름의 제어문자·개행은 escape 됩니다 —
그대로 찍으면 목록 한 줄이 두 줄이 되어 사용자가 지은 이름이 우리 화면에 줄을 끼워 넣습니다.
write root 밖을 가리키는 경로는 `<outside-project>` 로만 나옵니다 — 그 문자열은 우리가 만든 것이
아니라 탈출을 시도한 쪽이 정한 값입니다. `path` 가 그 표기이고, 절대 경로에 상대 경로를 덧붙이던
`project_path` 필드는 없습니다. 각
항목은 그 밖에 사유 code(`reason`), 구조화된 손상 사실(`detail`), 등록 상태
(`registration_state`)를 싣습니다.

설치 기록(manifest)은 **소유권 증거로 쓸 수 있는 모양인지** 먼저 확인합니다. 필수 필드·타입·
`installed_hosts`·`assets` 항목·`core_renders` receipt·skill receipt 를 install 과 **같은 계약**
으로 **끝까지** 보고, 어긋나면 확인 전에 `BLOCKED(2)` 로 끝냅니다 — 빈 receipt 는 "무엇을
배치했는지 모른다" 는 뜻이고, 모르는 상태의 삭제는 남의 파일을 지우는 일입니다 — 빈 manifest 를 정상으로 읽으면 "설치는 증명됐고 배치 기록은
없다" 가 되어, 증거를 먼저 지우고 나서 할 일이 없다고 말하게 됩니다. 대상 경로가 filesystem
root 나 그 직계 자식(`/usr`·`/opt`·`/Users`)이면 역시 계획 단계에서 `BLOCKED(2)` 이고 쓰기
대상은 하나도 만들지 않습니다. 계획을 세우다 읽을 수 없는 입력을 만나도 traceback 대신
`BLOCKED(2)` JSON 이 나옵니다 — 어떤 입력에서도 결과는 네 상태 중 하나입니다.

부모 결속을 만들 수 없는 환경에서는 위에 적은 대로 **실행을 거부**합니다 — 판정 기준은 OS
이름이 아니라 그 환경에서 결속이 실제로 성립하는가입니다. 그냥 실행하면 프로젝트 밖 파일을
만들 수 있고, 되돌릴 수 없는 명령에서 그 위험은 안내문으로 대신할 수 없습니다.

`--global` + `--all`, `--check` + `--yes`, `--global` + `--dest` 는 usage error `2` 입니다.

## 검증과 진단

| 명령 | 역할 |
|---|---|
| `sage validate` | 기본 `hook` 범위의 hash, staleness, regression, profile 의미 검사 |
| `sage validate --kind all` | hook, agent, skill, MCP 전체 자산 검사 |
| `sage validate --check` | 회귀 명령을 실행하지 않는 빠른 정합성 검사 |
| `sage validate --schema` | manifest와 profile JSON Schema 검사 |
| `sage validate --strict` | bootstrap/schema/overlay/profile drift 등 지정된 advisory check를 실패로 승격 |
| `sage status` | 지금 이 프로젝트에서 SAGE 를 쓸 수 있는지 1~2초 안에 읽기 전용으로 요약 |
| `sage status --json` | 같은 결과를 기계가 읽는 schema v1 JSON 으로 출력 (locale 무관) |
| `sage explain --path PATH` | 그 경로의 위험도 하한·매칭 규칙·결속 cycle·빠진 phase 문서를 설명 |
| `sage audit show` | 여섯 감사 출처를 한 화면에서 읽기 전용으로 조회 (기본은 공유 4종) |
| `sage audit show --include-local` | 로컬 출처(`retro`·`feedback`)까지 함께 조회 |
| `sage audit show --json` | 같은 결과를 기계가 읽는 schema v1 JSON 으로 출력 (locale 무관) |
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

## 어느 명령을 언제 쓰는가

같은 질문에 두 명령이 답하지 않는다. 각 명령은 자기 질문 하나만 소유한다.

| 질문 | 명령 |
|---|---|
| 지금 SAGE 를 쓸 수 있는가? | `sage status` |
| 이 경로는 왜 이런 요구를 받는가? | `sage explain --path ...` |
| 무슨 일이 있었는가 — 누가 무엇을 우회·유예·리뷰했는가? | `sage audit show` |
| 설치 도구·peer model·optional capability 가 준비됐는가? | `sage doctor` |
| 전체 자산·schema·hash 가 정확한가? | `sage validate --kind all --check --schema` |
| 다른 SAGE 버전으로 안전하게 이동할 수 있는가? | `sage upgrade --check` |

`sage status` 는 문제를 발견하면 위 상세 명령으로 **연결**하고, 그 명령의 결과를 대신
만들어내지 않는다. `status` 와 `explain` 은 읽기 전용이라 파일과 `.sage` 감사 기록을 바꾸지
않으며, 복구 명령을 자동으로 실행하지도 않는다. 감사도 락을 잡지 않고 읽으므로 진행 중인
Fast 전이를 기다리거나 방해하지 않는다.

`status` 가 보는 영역은 일곱이다 — project, version, runtime API, profile, host, cycle,
그리고 구현 전 요구 phase 의 준비 상태. 사이클 mode 를 판정할 수 없으면(감사가 손상됐거나
읽는 도중 기록이 늘어난 경우) `STANDARD` 로 낮추지 않고 `UNKNOWN` 으로 표시한다 — 모르는
것을 정상으로 접으면 손상된 감사가 일반 사이클처럼 보인다.

`status` 와 `explain` 은 존재하지 않는 `--root` 를 정상 프로젝트처럼 설명하지 않는다. 둘 다
exit `2` 로 거부한다.

상태 토큰은 `READY`·`ATTENTION`·`BLOCKED`·`ERROR` 넷이다. `BLOCKED` 는 프로젝트 상태가 실제로
막힌 것이고, `ERROR` 는 SAGE 가 자기 일을 못 한 것이다 — 둘을 구분하는 이유는 전자만 고칠
대상이 있기 때문이다.

`sage explain --path` 는 경로와 현재 저장소 상태만 본다. 실제 write 는 새 내용, 세션 risk
선언, 한 번에 변경하는 다른 파일에 따라 더 엄격해질 수 있으므로 이 명령은 허용을 보증하지
않는다 — 그래서 결과에 `ALLOW` 가 없다.

### `sage audit show` — 보증의 차이를 감추지 않는다

여섯 출처의 무결성 보증은 서로 다르다. 화면은 그 차이를 `method` 와 `status` 두 축으로 낸다.

| 출처 | `method` | 뜻 |
|---|---|---|
| `review`·`fast` | `strict_chain` | append 순 hash chain 을 검증한다 |
| `acceptance` | `semantic` | 레코드 간 의미 규칙만 검증한다. 위변조 내성은 없다 |
| `retro` | `structural` | 구조 파싱만 한다 |
| `override`·`feedback` | `none` | 아무 검증도 없다 |

검증이 없는 출처는 어떤 경로로도 `valid` 로 표시되지 않는다. `.sage/override.jsonl` 은
**추적 사본**이고 집행 정본은 로컬 상태 홈에 있다 — 둘의 불일치는 이 명령이 검출하지 않으며,
그 사실이 조회할 때마다 함께 표시된다.

보증 필드가 없는 과거 기록은 `legacy` 이고 exit `0` 이다. 손상이 아니라 그 기록에 보증이
없다는 뜻이라, 실패로 올리면 과거 run 을 가진 저장소가 전부 붉어진다.

읽기 전용이며 **lock 을 만들지도 획득하지도 않는다.** 그래서 진행 중인 append 중간을 볼 수
있는데, 그 상태는 감춰지지 않고 `audit.source.concurrent_change` 로 표면화된다 — 부분 결과를
정상으로 표시하는 경로가 없다.

절대경로·HOME·vault 경로는 어떤 출력에도 나오지 않는다. 경로 필드뿐 아니라 `reason` 같은
자유 문자열까지 값 기준으로 검사해 `<redacted-path>` 로 바꾸고, 바꿨다는 사실을 진단으로
남긴다.

`--json` 의 최상위 key 는 열둘로 고정이다 — `schema_version`·`ok`·`status`·`exit_code`·
`ordering`·`selection`·`sources`·`events`·`returned`·`omitted`·`truncated`·`diagnostics`.
`ok` 는 `exit_code == 0`, `returned` 는 실린 이벤트 수, `omitted` 는 `--limit` 으로 생략된 수,
`truncated` 는 `omitted > 0` boolean 이다. `truncated` 를 건수로 겸하지 않는 이유는 `0` 이
"거짓" 과 "0건 생략" 을 동시에 뜻하게 되기 때문이다.

진단의 정본은 `diagnostics` **하나**이고 어느 출처의 문제인지는 `evidence.source` 로 결속한다.
`sources` 에 사본을 두지 않는다 — 같은 사실이 두 자리에 있으면 갈렸을 때 어느 쪽이 옳은지
판정할 근거가 없다.

`--limit` 은 기본 100 이고 범위는 1~10000 이다. 범위 밖 값은 조용히 끌어당기지 않고 exit `2`
로 거절한다 — `0` 은 무제한이 아니다. 끌어당기면 요청한 값과 받은 값이 달라지고, 화면 어디에도
그 사실이 남지 않는다.

retro 의 노트 경로는 저장소 상대경로로 정상이어도 출력하지 않는다. 조회는 노트가 있었는지
(`vault_note_present`)와 digest 가 남았는지(`digest_present`)만 답한다 — 가려야 할 이유가
"경로가 이탈했다" 가 아니라 "그 값 자체" 인 자리이기 때문이다.

출처 상태에는 `policy`(`shared`·`local`)와 `tracking`(실제 Git 상태)이 함께 나온다. 하나로
접으면 "공유 대상인데 커밋되지 않음" 과 "원래 개인 기록" 이 같은 값이 된다.

출처의 `present` 는 **세 상태**다. 있음·없음 말고, 도구가 그 출처를 읽지 못해 **판정하지
못한** 상태가 따로 있다. text 는 `present=unknown`, JSON 은 `null` 로 낸다. 둘로 접으면 도구
실패가 "기록 없음" 으로 읽힌다.

로컬 출처로 가는 관문은 `--include-local` **하나**다. `--source retro` 를 그 관문 없이 주면
빈 결과가 아니라 exit `2` 다 — 빈 결과는 "그 출처에 기록이 없다" 로 읽힌다.

교차 출처 시간 정렬은 **표시 순서일 뿐** 인과나 권위 순서가 아니며, 출력이 그 사실을 함께
낸다. 조회 결과는 어떤 게이트의 입력도 되지 않는다.

## 공통 종료코드

명령별 세부 계약은 `--help`와 출력이 우선합니다. 일반적으로 `0`은 PASS, `1`은 검증 FAIL,
`2`는 도구·게이트 오류 또는 BLOCK, `3`은 STALE을 의미합니다. Hook에서는 `0`이 통과,
`2`가 차단입니다.
