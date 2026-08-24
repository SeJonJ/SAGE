# SAGE 문제 해결

[English](troubleshooting.en.md) | [문서 인덱스](README.md)

## `sage: command not found`

```bash
pipx install "sage-harness[schema]"
pipx ensurepath
```

새 터미널을 연 뒤 `sage --version`을 확인합니다. pip user 설치를 사용했다면
`python3 -m sage --help` 또는 Windows의 `py -m sage --help`로 실행할 수 있습니다.

## Windows에서 hook이 실행되지 않음

설치 hook은 bash가 아니라 `sage-hook.exe`를 사용합니다.

```powershell
where sage-hook
sage doctor
```

진입점이 없으면 같은 Python 환경에 `sage-harness`를 다시 설치합니다. 선택적 `.sh` 개발자 회귀를
실행할 때만 `SAGE_BASH`에 Git Bash의 절대경로를 지정합니다. WSL launcher를 암묵적으로 선택하지 않습니다.

## `--host`, `--kind`, `--skill-scope` 누락

```bash
sage install --host claude
sage install --host codex --skill-scope project-local
sage generate --kind hook --write
```

`install`의 host와 Codex skill scope, `generate`의 kind는 명시적으로 선택합니다.

## `sage validate`가 STALE

STALE은 spec, core, adapter, runtime hash가 manifest stamp와 다르다는 뜻입니다.

```bash
sage generate --kind hook --write
sage validate
```

설치 직후에는 CORE hook이 미스탬프 상태일 수 있으므로 generate를 한 번 실행합니다. 파일을 직접 수정해
hash만 맞추지 마세요.

## Write guard가 편집을 차단

`.claude/`·`.codex/` 생성물, `.mcp.json`, CORE framework 문서는 직접 편집 대상이 아닙니다.

```bash
sage absorb --kind agent --id my-agent
sage generate --kind agent --write
```

지원되는 CORE 자산 커스터마이즈는 `sage-asset-override`를 사용합니다. 프로젝트 정책은
`sage/project-profile.yaml`이나 project-owned governance 문서에 둡니다.

## 세션 위험도 선언이 잘못 잡혀 편집이 막힘

게이트가 Phase 00보다 높은 위험도를 요구하는데 그 위험도가 **이번 세션 선언**에서 왔다면,
Phase 00을 올리지 마세요 — 실제보다 높은 위험도를 기록하게 됩니다. 선언을 지우면 됩니다.

```
위험도 선언 해제
```

프롬프트로 그대로 입력하면 이번 세션의 선언이 삭제되고, 이후 판정은 경로·내용 계산만 씁니다.
차단 메시지가 선언 출처를 알려주므로 어느 쪽인지는 안내를 보고 판단하면 됩니다.

선언은 레벨 하나를 평서문으로 적을 때만 잡히고, 잡히지 않은 경우에는 그 사실을 알려줍니다.
쓰이지 않은 선언은 2일 뒤 만료됩니다.

## 문서가 다 있는데 "의무 PDCA phase 미작성"으로 막힘

phase 문서를 고칠 때 게이트는 파일명에서 사이클을 알아냅니다. 소스 편집에는 그런 단서가 없어서
**git 브랜치 이름의 마지막 조각**에서 추론합니다. 사이클마다 브랜치를 따면 맞고, 브랜치 하나로 여러
사이클을 돌면 영영 맞지 않습니다 — 00~03을 다 써도 "미작성"으로 막힙니다.

브랜치 이름을 바꾸지 말고 사이클을 선언하세요.

```bash
sage cycle set <phase-문서-파일명>   # 기존 Phase 00이 있을 때
sage cycle set <새-stem> --create --risk L2  # Phase 00이 없을 때
sage cycle show                      # 무엇이 선언됐고 어디서 읽었는지
```

게이트가 약해지는 것이 아닙니다 — 추론하지 못한 사이클 정체를 알려줄 뿐이고, phase·리뷰·acceptance
요구는 그 stem에 그대로 적용됩니다. 세션의 첫 사용은 `.sage/override.jsonl`에 기록됩니다.

`sage cycle set`은 자기가 쓴 절대경로와 git 무시 여부, 게이트가 읽는 profile 쌍의 존재를 함께
출력합니다. 선언했는데 안 먹는다면 그 출력부터 보세요.
기존 Phase 00과 충돌하면 아무것도 덮지 않고 충돌 경로와 사용 가능한 stem 후보 3개를 출력합니다.
커스텀 Phase 00 glob 때문에 위치를 유도할 수 없을 때만 root 상대 디렉터리를 `--path DIR`로 지정하세요.

`--create`는 Phase 00만 만듭니다. profile이 01~03을 요구하면 작성 전까지 소스 편집은 계속
차단됩니다. 긴급 작업에서 면제 가능한 phase 결핍만 열려면
`sage override --reason "hotfix" --ttl 1h`처럼 짧게 발급하세요. Phase 00의 risk 선언·정합 차단은
override로 면제되지 않습니다.

`sage-cycle` 우산은 직접 `set`/`clear`하지 않습니다. `sage-plan`이 stem 검증 뒤 선언하고,
`sage-team`이 재개 시 `show`로 대조한 뒤 write-back·retro·snapshot과 종료 게이트까지 완료하면
해제합니다. `BLOCKED`/`FAIL`에서는 재개를 위해 선언을 남깁니다.
`set B`는 포인터만 바꾸므로 A의 문서·증거·감사는 그대로 남고, `set A`로 돌아가면 판정도 복원됩니다.

## Done Criteria 또는 stale Phase 05 승인으로 차단됨

같은 stem의 Phase 00만 먼저 수정하세요. 정확한 `## 5. Done Criteria`, 양의
`Done-Criteria-Revision`, `[ ]`·`[x]`·사유 있는 `[~]` 형식을 복구합니다. 기준 문구나 범위가
바뀌었다면 revision을 올리고 Changed-At·Reason·Affected-Phases·Summary를 기록한 뒤 영향 phase를
순서대로 재실행합니다. 기존 Phase 05 승인은 재사용하지 말고 새 review loop를 `--cycle-stem`과
함께 수행한 뒤, APPROVED close가 출력한 `Phase00-Hash`와 새 `Loop-Run`을 Phase 05에 기록하세요.
Phase 00과 후속 phase를 한 번에 수정하면 pre-write 상태를 검증할 수 없어 차단되므로 나눠서 씁니다.

## 사이클을 끝냈는데 다음 작업이 "이미 완결된 사이클"로 막힘

선언은 셸을 넘겨 살아남습니다. 끝난 사이클의 선언이 남아 있으면 새 작업이 거기 결속되고, 게이트가
그걸 막습니다.

```bash
sage cycle clear                     # 파일 선언 해제
unset SAGE_CYCLE_STEM                # env로 선언했다면
```

차단 메시지가 결속을 **선언된**으로 읽었는지 **브랜치에서 추론한**으로 읽었는지 알려주므로, 어느 쪽을
지워야 하는지는 안내를 보고 판단하면 됩니다.

## `sage install`이 "SAGE source resources changed"로 실패

설치 도중 SAGE 엔진 소스가 바뀌면 반쯤 섞인 산출물이 나오므로 install이 스스로 중단하고 롤백합니다.
검사는 정상 동작이고, 대부분 원인은 **테스트나 리뷰 도구가 저장소 파일을 잠깐 고쳤다 되돌리는 것**입니다.

메시지가 어떤 논리경로가 달라졌는지 함께 알려줍니다.

```
❌ sage install apply 실패: InstallDriftError: SAGE source resources changed during install
   — 변경 2건: hooks/runtime/messages.py, engine/commands/install.py
```

경로를 보고 무엇이 건드렸는지 특정한 뒤 그 작업을 끝내고 다시 설치하세요. 변이 테스트나 독립 리뷰를
**전체 스위트와 동시에 돌리지 마세요** — 둘 다 저장소 소스를 일시 변경하므로 install 계열이 정당하게
실패합니다.

## `sage fast-cycle open`이 rejected로 거부됨

```
⛔ [sage fast-cycle] open rejected: pdca.fast_cycle.enabled=true is required
⛔ [sage fast-cycle] open rejected: lens-count must be at least 2 for L2
⛔ [sage fast-cycle] open rejected: lens-count exceeds configured candidates (3)
```

Fast Cycle은 시작 시점에 공유 정책이 허용한 최소 조건을 전부 채워야 합니다. `enabled=true` 오류는
`sage/project-profile.yaml`의 `pdca.fast_cycle.enabled`가 꺼져 있다는 뜻이고, `lens-count` 오류는
`--lens-count`가 해당 risk level의 `minimum_lenses`보다 적거나 `lenses` 후보 수보다 많다는 뜻입니다.
사유(`--reason`)가 비어 있거나 형식이 안 맞아도 같은 방식으로 거부됩니다.

```bash
sage fast-cycle open --stem <stem> --level L2 --lens-count 2 --reason "짧은 사유"
```

`reason_required`는 profile에서 완화할 수 없으므로, 값을 채워 다시 시도하는 것 외에 우회 경로는 없습니다.

## `sage fast-cycle convert`가 거부됨

```
⛔ [sage fast-cycle] convert failed: pdca.fast_cycle.standard_transition.enabled=true is required
⛔ [sage fast-cycle] convert failed: --confirm must be exactly FAST-CONVERTED
⛔ [sage fast-cycle] convert failed: Fast audit integrity failed: ...
```

전환은 두 옵트인(`fast_cycle.enabled`, `fast_cycle.standard_transition.enabled`)이 모두 켜져 있어야
열립니다. 확인 토큰·사유·승인자 중 하나라도 없으면 **아무것도 기록하지 않고** 종료합니다 — 감사도
문서도 그대로입니다. 무결성 오류는 `.sage/fast_cycle.jsonl`의 기존 레코드가 손상됐다는 뜻이고,
손상된 감사 위에 새 run을 얹지 않습니다.

```bash
sage fast-cycle convert --stem <stem> --current-phase 04 --level L2 \
  --lens-count 2 --reason "짧은 사유" --confirmed-by <승인자> --confirm FAST-CONVERTED
```

전환한 뒤에도 소스 편집이 `block_phase_incomplete`로 막힌다면, 전환 시점에 존재하던 phase 목록이
그 위험도의 `pre_implementation_required`를 다 담지 못한 것입니다. 전환은 **가진 것만** 면제하므로
Phase 00에서 전환했다면 01~03을 그대로 작성해야 합니다. 전환된 run은 문서에 `Fast-Audit-Run` 줄을
갖지 않는 것이 정상이며, 그 줄이 없다고 손으로 추가하면 안 됩니다.

## 조기 종료(`USER_AUTHORIZED_EARLY`)가 거부됨

```
[sage review-loop] early completion refused: pdca.review_loop.early_completion.enabled=true is required
[sage review-loop] --survived-by-severity invalid: severity total 2 does not equal survived 3
```

조기 종료는 `pdca.review_loop.early_completion.enabled: true`가 필요하고, `sage review-loop next`가
아직 `CONTINUE`를 권고할 때만 의미가 있습니다. 이미 `STOP`/`CONVERGED`면 정상 close를 쓰십시오.
영수증 합계 오류는 `--survived-by-severity`의 합이 그 라운드의 `--survived`와 다르다는 뜻입니다 —
`P0=0`만 적어 차단 finding을 숨기는 것을 막는 검사라 우회 경로가 없습니다.

승인으로도 엔진 차단을 통과하지 않는 것들이 있습니다: 라운드 0건, `severity_block` 심각도의 미해결
finding, architecture escalation, Done Criteria 미해결, acceptance `FAIL`, 감사 손상.
이 중 하나로 막혔다면 그 원인을 실제로 해소해야 합니다.

필수 build/test/lint 실패도 조기 완료해서는 안 되지만, 그 결과는 Phase 03 산문에만 있어 엔진이 직접
읽지 못합니다. 이 항목은 에이전트가 사용자에게 그대로 알리고 close를 진행하지 않아야 하는 의무입니다.

## Phase 05가 "보증 저하 표기" 때문에 막힘

```
조기 완료로 닫히지 않은 run 인데 보증 저하를 자칭함: [...]
Review-Assurance 선언은 fence 밖에 정확히 1개여야 함(found 0)
```

기준은 표기의 존재가 아니라 **값**입니다. `Review-Assurance: REDUCED_BY_USER_AUTHORIZATION` 또는
`Review-Close-Reason: USER_AUTHORIZED_EARLY` 중 하나라도 적으면 보증 저하를 자칭한 것입니다. 자칭
했거나 감사가 조기 종료로 닫혔다면 네 표기(`Review-Assurance`, `Review-Close-Reason`,
`Review-Rounds`, `Residual-Findings`)를 모두 적고 값이 감사 레코드와 일치해야 합니다. 정상 수렴한
run이라면 그 두 값을 적지 않습니다. `Review-Rounds: 3` 같은 중립 표기만 있는 것은 막지 않습니다.
`Review-Rounds`의 `(configured max: <max>)`도 감사와 같아야 합니다. 상한이 없는 프로젝트는 감사와
같은 낱말인 `unbounded`를 적습니다.

표기를 올바르게 적었는데 `found 0`으로 막힌다면 fence 안에 들어갔는지 확인하십시오 — 코드블록 안의
줄은 세지 않습니다.

## 조기 완료가 `unresolved acceptance`로 거부됨

선택된 Phase 04에 acceptance `FAIL`이나 exact waiver 없는 필수 `NOT TESTED`가 남아 있습니다. 조기
완료는 리뷰가 남긴 finding을 인수하는 절차이지 미검증 요구사항을 넘기는 절차가 아니라, 이 상태는
사용자 확인으로도 통과하지 않습니다. 04 증거를 `PASS`로 채우거나, L3에서 `sage acceptance-waiver
grant`로 해당 ID를 명시 승인한 뒤 다시 실행하십시오. 판정은 Phase 06 리포트 게이트와 같은 정책을
쓰므로, 여기서 통과시켜도 06에서 같은 이유로 막힙니다.

## `sage cycle clear`가 활성 Fast run 때문에 막힘

Fast 감사가 열린 상태에서 선언부터 지우면 이후 증거가 다른 stem에 결속될 수 있어 fail-closed로 막습니다.

```bash
sage fast-cycle show
# 정상 완료
sage fast-cycle close --run-id <fc-id>
sage cycle clear
# 또는 의도적 중단
sage fast-cycle abort --run-id <fc-id> --reason "중단 사유"
sage cycle clear
```

`close`가 거부되면 00이 최신 Fast review 뒤 바뀌었는지, 05/06의 `Fast-Run`·`Loop-Run`·
`Final Status: APPROVED`가 같은 run을 가리키는지 확인합니다. 감사 원문이 손상됐으면 임의 삭제하거나
새 run으로 덮지 말고 복구 가능한 Git 이력과 `.sage/fast_cycle.jsonl`을 함께 검토해야 합니다.

## 선언 파일을 편집 도구로 쓰려다 write guard에 막힘

`.sage/cycle.json`은 게이트가 "이 편집이 어느 사이클인가"를 읽는 자리입니다. 직접 쓰면 완결된 사이클을
지목해 게이트를 통과시킬 수 있어서 차단합니다. `sage cycle set|show|clear`를 쓰세요 — CLI는 편집 도구를
거치지 않으므로 가드에 걸리지 않습니다.

`[사이클 선언 무시됨]` 알림이 뜬다면 파일이 있는데 읽지 못한 것입니다. 게이트는 선언 없음으로
진행하니 `sage cycle set <stem>`으로 다시 쓰거나 `sage cycle clear`로 지우세요.

## `sage absorb` 또는 `sage override` 인자 누락

```bash
sage absorb --kind agent --id my-agent
sage override --reason "hotfix" --ttl 30m
```

Override는 사유와 만료시간이 필수이며 감사 로그에 기록됩니다. 일부 무결성·risk 계약 block은 generic
override로 우회할 수 없습니다.

## `sage override`가 권한 캐시 위치를 거부

```
⛔ [sage override] 권한 캐시 위치가 저장소 안입니다(...) — SAGE_STATE_HOME 를 저장소 밖으로 지정하세요
⛔ [sage override] 권한 캐시 위치를 정할 수 없습니다(절대경로 아님: ...)
```

활성 우회 **권한**은 저장소 밖 머신 로컬 상태 디렉터리에 삽니다. 저장소 안에 두면 커밋돼서 다른
사람의 clone에서 우회가 활성화되기 때문입니다. 위치를 확신할 수 없으면 권한을 만들지 않습니다.

- 저장소 안을 가리키는 `SAGE_STATE_HOME`/`XDG_STATE_HOME`/`HOME`을 저장소 밖으로 바꾸세요.
- `HOME`이 없는 컨테이너라면 `SAGE_STATE_HOME`을 절대경로로 지정하세요.
- 현재 위치는 `sage override --list`가 출력합니다. `.sage/tmp/`를 지워도 리셋되지 않습니다.

`저장소 경계를 확정할 수 없습니다` 메시지는 `.git`이 있는데 해석되지 않는 경우입니다(손상된 포인터
파일, 사라진 gitdir). 저장소 정체성을 확정하지 못한 채 발급하면 다른 저장소의 권한과 뒤섞이므로
차단합니다. `.git` 상태를 복구한 뒤 재시도하세요. 자세한 위치 규칙은 [Artifacts](ARTIFACTS.md) §1.1.

## `sage-hook`이 runtime API 불일치로 차단

```text
⛔ BLOCK [runtime.api_too_old]
이 프로젝트의 hook 은 SAGE runtime API 2 를 요구하지만, 이 sage-hook 은 API 1 를 제공합니다.
Next: sage upgrade --check
Next: pipx upgrade sage-harness
```

프로젝트에 설치된 hook 은 그 저장소에 설치된 SAGE 가 만들었고, 그걸 실행하는 `sage-hook` 은
머신에 설치된 package 가 준다. 둘의 나이가 다르면 새 hook 이 아직 없는 module 을 import 하고,
그 실패는 host 에 따라 그냥 "hook 이 죽었다" 로 처리된다 — 정책을 실행해야 할 게이트가 조용히
빠지는 경로다. 그래서 이 판정은 **project core 를 import 하기 전에** 정수 비교 하나로 닫는다.

화면의 `Next:` 순서를 그대로 따르면 된다. package 를 먼저 올리고, 설치 자산을 재생성한 뒤,
`sage status` 로 확인한다.

`runtime_api marker 가 없습니다` 로 막혔다면 manifest 가 1.0 형식인데 marker 만 없는 상태다.
이때 **marker 부재는 "1.0 이전 설치" 로 인정되지 않는다.** 인정하면 marker 와 version 을 함께
지운 downgrade 가 통과하기 때문이다. `sage install --host <host> --force --dest .` 로 다시
스탬프한다.

## 차단 메시지에 `Next:`가 없음

SAGE 가 내는 모든 사용자 노출 차단에는 최소 한 줄의 `Next:` 가 있고, 그중 최소 하나는 그대로
붙여넣어 실행할 수 있는 명령이다. 사람이 직접 해야 하는 일은 `Next:` 가 아니라 `Action:` 으로
나온다 — 붙여넣을 수 없는 문장을 `Next:` 로 내면 그 토큰이 "다음에 칠 것" 이라는 뜻을 잃는다.

`Next:` 와 `Action:` 토큰은 한국어·영어에서 동일하다. 화면에서 검색하거나 로그에서 모아야
하기 때문이다. 대괄호 안의 진단 code(`[gate.phase_incomplete]`)도 같은 이유로 번역하지 않는다.

`Next:` 가 하나도 없는 차단을 만났다면 그건 결함이다. 그 code 와 함께 보고하면 된다.
직접 만든 project hook 이 낸 메시지에는 SAGE 가 복구 명령을 추측해 붙이지 않으며, 대신
`Next: sage status` 만 보장한다.

## Cross-model 리뷰가 BLOCKED

`sage doctor`로 반대 runtime CLI와 model 설정을 확인합니다. required 정책에서는 peer runtime에
도달하지 못한 상태를 same-runtime 성공으로 낮추지 않습니다.

## Schema 검증이 WARN

```bash
pipx inject sage-harness jsonschema
# 또는
pipx install --force "sage-harness[schema]"
```

`jsonschema`가 없으면 hash와 내장 의미 검사는 계속되지만 JSON Schema 검사는 WARN으로 건너뜁니다.

## `--lang en`을 붙였는데 출력이 그대로 한국어

전역 `--lang`은 **하위 명령 앞**에만 옵니다. `sage doctor --lang en`은 지원하는 형태가 아닙니다.

```bash
sage --lang en doctor        # 이 자리가 맞습니다
```

Hook 출력은 `--lang`을 아예 받지 않습니다. Hook이 영어로 나와야 한다면 대상 프로젝트의
`sage/project-profile.local.yaml`에 설정합니다.

```yaml
interface:
  language: en
```

그래도 한국어가 나온다면 확인할 것이 셋입니다. local profile이 **hook이 검사하는 그 프로젝트
루트**에 있는지, 값이 `ko`나 `en`인지(다른 값은 `ko`로 되돌아가며 `sage validate`가 설정 실패로
보고합니다), 그리고 남은 한국어가 **인용된 원문**인지 — 파일에서 읽어 근거로 되돌려주는 조각은
번역하지 않습니다. 그건 결함이 아니라 증거입니다.

Phase 00~06 문서가 한국어로 쓰이는 것은 이 설정과 무관합니다. 문서 언어는 사이클마다
`Document-Language:`로 따로 고정하며, 진행 중인 사이클은 `--lang`으로 바뀌지 않습니다.
