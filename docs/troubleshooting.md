# SAGE 문제 해결

[문서 인덱스](README.md)

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

## `sage absorb` 또는 `sage override` 인자 누락

```bash
sage absorb --kind agent --id my-agent
sage override --reason "hotfix" --ttl 30m
```

Override는 사유와 만료시간이 필수이며 감사 로그에 기록됩니다. 일부 무결성·risk 계약 block은 generic
override로 우회할 수 없습니다.

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
