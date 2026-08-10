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

## 사이클을 끝냈는데 다음 작업이 "이미 완결된 사이클"로 막힘

선언은 셸을 넘겨 살아남습니다. 끝난 사이클의 선언이 남아 있으면 새 작업이 거기 결속되고, 게이트가
그걸 막습니다.

```bash
sage cycle clear                     # 파일 선언 해제
unset SAGE_CYCLE_STEM                # env로 선언했다면
```

차단 메시지가 결속을 **선언된**으로 읽었는지 **브랜치에서 추론한**으로 읽었는지 알려주므로, 어느 쪽을
지워야 하는지는 안내를 보고 판단하면 됩니다.

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
