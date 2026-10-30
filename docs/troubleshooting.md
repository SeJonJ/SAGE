# SAGE 문제 해결

[English](troubleshooting.en.md) | [문서 인덱스](README.md)

## 개인 지침이 공동 개발자에게도 적용됩니다

개인 절이 공유 `sage/asset_overrides/`에 남아 있으면 기존대로 팀에 적용됩니다.
upgrade는 자동으로 옮기지 않습니다. 사람이 개인 절을 `sage/asset_overrides.local/`의 같은
kind/id 파일로 옮기고 공유 원문에서 제거한 뒤 `sage sync-overlays`를 실행하세요.
개인 파일은 `sage overlay-local --kind agent|skill --id <id> --root <project-root>`로 검사합니다.
읽기 실패는 raw 파일로 우회하지 않습니다. [개인 overlay 계약](cli-reference.md#개인-overlay)을 참고하세요.

개인 디렉터리의 실제 이름도 소문자 `sage/asset_overrides.local/`을 사용하세요. 대소문자를
구분하지 않는 파일시스템에서 다른 철자를 사용하고 Git의 `core.ignorecase=false`를 설정한
경우에는 기본 ignore에서 빠질 수 있습니다. `git check-ignore -v -- <실제-개인-파일-경로>`로
제외 여부를 확인하고, 필요하면 해당 실제 경로의 사용자 ignore 규칙을 직접 추가하세요.

`upgrade --apply` 전에는 개인 파일 편집을 마치고 저장·백업하세요. 기존 실패 rollback은
시작 전 snapshot으로 복구하므로, 실행 중 동시 저장·생성·삭제한 개인 변경이 되돌아갈 수
있습니다. 성공 upgrade의 개인 변경 보존을 실패 rollback의 동시 편집 보장으로 해석하지 마세요.

## 기존 `CLAUDE.md` · `AGENTS.md` 와 충돌해 설치가 멈춤

```
❌ 설치를 멈췄습니다 — 이 프로젝트에 이미 있는 파일을 SAGE 가 덮어쓰게 됩니다.
```

SAGE는 `CLAUDE.md`·`AGENTS.md`·`CODEX.md`·`AGENT_GUIDE.md`를 **자기가 통째로 생성하는 자산**으로
다룹니다. 기존 내용과 병합하지 않기 때문에, 같은 이름의 파일이 이미 있으면 덮어쓰기 전에
멈춥니다. 이 시점에 프로젝트 파일과 manifest는 하나도 변경되지 않습니다.

### framework 문서인 경우

```bash
mkdir -p docs
mv CLAUDE.md docs/project-conventions.md   # 쓰고 있던 규칙을 다른 이름으로
sage install --host claude --dest .        # 같은 명령을 다시
```

설치 후 `/sage-init`(Codex는 `$sage-init`)로 profile을 채울 때 방금 옮긴 문서를 **convention
문서로 등록**하세요. 에이전트가 세션 시작마다 그 문서를 읽으므로 기존 규칙이 그대로 살아납니다.

SAGE가 배치하는 `CLAUDE.md`는 얇은 라우터이고, 프로젝트 지침이 들어갈 자리는
`sage/project-profile.yaml`과 convention 문서입니다. framework 문서에는 overlay 합성을 쓸 수
없으므로 `sage/asset_overrides/`로 옮기려 하지 마세요 — 넣을 자리가 없습니다.

### 에이전트·스킬 렌더인 경우

`.claude/agents/leader.md` 처럼 CORE 에이전트·스킬 렌더가 충돌했다면 답이 다릅니다.

```bash
mv .claude/agents/leader.md .claude/agents/leader.md.bak
sage install --host claude --dest .
# 백업의 프로젝트 지침을 sage/asset_overrides/agents/leader.md 로 옮긴다
```

overlay는 CORE 렌더 **위에 덧대어** 합성되고 `sage install --force`가 지우지 않습니다. 다만
AGENT_GUIDE·phase·리뷰·검증 게이트를 완화할 수는 없습니다.

어느 경로인지는 **오류 메시지가 자산마다 갈라서** 알려주므로, 화면에 나온 안내를 그대로 따르면
됩니다.

### 이미 SAGE가 설치된 파일을 직접 고친 경우

```
❌ 설치를 멈췄습니다 — SAGE 가 관리하는 파일이 설치 이후 변경됐습니다.
```

그 파일은 SAGE가 생성·갱신하므로 직접 수정하면 다음 설치 때 덮어써집니다. 수정 내용이 필요
없으면 `--force`, 살리려면 그 부분을 convention 문서나 overlay로 옮긴 뒤 `--force`입니다.

### 판본이 올라간 경우

```
❌ 설치를 멈췄습니다 — 설치본이 현재 패키지 판본과 다릅니다.
```

사고가 아닙니다. `--force` 또는 `sage upgrade`로 새 판본을 받으세요. `sage upgrade`는 자산·hook·
검증까지 한 단위로 맞춥니다.

기존 내용을 버려도 된다면 어느 경우든 `--force`를 쓸 수 있습니다. 되돌릴 수 없습니다.

## 1.0 에서 설치한 프로젝트 — `sage upgrade` 로 새 레이아웃에 전환합니다

1.0 은 SAGE 파일을 `scripts/sage_harness/`·`schema/`·`scripts/verify-changes.sh` 에 두었습니다.
그 뒤 판본은 `sage_harness/` 한 곳으로 모읍니다.

```bash
sage upgrade --check    # 무엇이 바뀌는지 먼저 봅니다 (아무것도 바꾸지 않습니다)
sage upgrade --apply    # 이행
```

차단 사유가 없는 설치본은 한 번에 끝납니다. 자동 이행이 시작된 뒤 중단되면 다시 실행해 남은
정리를 이어갑니다.

### 무엇을 지우고 무엇을 남기나

파일을 **옮기지 않습니다.** SAGE 가 배포한 자산은 새 위치에 다시 만들고, 새 위치가 실제로
동작하는 것을 확인한 뒤, 옛 위치에서 **SAGE 소유임을 증명할 수 있는 것만** 지웁니다.

| | |
|---|---|
| SAGE 가 배포한 파일 | 새 위치에 다시 만들고 옛 것을 지웁니다 |
| 그 폴더에 직접 넣은 파일 | **그대로 둡니다.** 무엇을 남겼는지 알려 드립니다 |
| 고친 `verify-changes.sh` | 그대로 둡니다 — 수정본인지 구버전인지 구별할 수 없습니다 |
| `scripts/`·`schema/` | **남을 수 있습니다.** 비어도 자동으로 지우지 않으며, 안전하게 확인된 빈 구 디렉터리만 결과에 표시합니다 |

### 이행이 멈추는 경우

```
자동 이행을 멈췄습니다 — 사용 중인 project hook 이 있습니다: hooks/my-guard
```

직접 작성한 project hook 이나 review strategy 가 있으면 **첫 변경 전에 멈춥니다.** 그 코드는
프로젝트가 쓴 것이라 패키지가 다시 만들 수 없고, 어느 자리로 가야 하는지도 도구가 정하지
않습니다. 자동으로 옮기지도, 조용히 끄지도 않습니다.

**이 릴리즈는 사용자 확장 자산의 자동 이행을 지원하지 않습니다.** 해당 설치본은 **구 위치에서
그대로 계속 동작합니다** — 게이트도, 등록도, 검증도 이전과 같습니다. 손수 옮기실 필요는 없고,
권하지도 않습니다(아래). **옮겨도 등록이 남아 있는 한 이행은 계속 멈추고, 등록을 해제하는 명령은
없습니다.** 이미 옮겼다면 코드를 구 위치(`scripts/sage_harness/hooks/`)로 되돌리세요. 사용자 확장의
자동 이행은 후속 릴리즈의 범위입니다.

### 직접 옮기지 마세요

`mv scripts/sage_harness sage_harness` 로 손수 옮기는 것은 **권하지 않습니다.** 옮겨야 하는
것이 hook 폴더만이 아니기 때문입니다 — schema, verify 스크립트, adapter 가 가리키는 경로,
설치 영수증이 함께 맞아야 합니다. 일부만 옮기면 구·신이 공존하고, 그 상태에서는 어느 쪽 hook
이 도는지 도구가 정할 수 없어 `sage install` 이 멈춥니다.

### 이행 전까지는 그대로 동작합니다

옛 위치에 그대로 두어도 hook 실행·검증 모두 됩니다. 자동 이행이 시작된 뒤 중단된 경우에도
**옛 코드가 계속 게이트로 섭니다** — 새 위치가 검증되기 전까지 정본은 옛 위치입니다.

## `sage generate` 가 "project hook adapter 손상/비정본" 으로 멈춤

```
[sage generate] TOOL ERROR: project hook adapter 손상/비정본: .../adapters/claude/<hook-id>.sh
```

**1.1.0 에서 구 레이아웃(`scripts/sage_harness/`) 설치본의 project hook 이 있으면** 이렇게 멈췄습니다.
1.1.0 이 adapter 본문에 레이아웃과 무관하게 신 경로를 적었기 때문이고, **1.1.1 에서 고쳤습니다.**
1.0 이 만든 adapter 는 1.1.1 로 올리면 그대로 정본으로 인정됩니다.

다음 경우에는 1.1.0 이 이미 잘못된 adapter 를 만들었으므로 한 번 직접 정리해야 합니다.

- 1.1.0 에서 **구 레이아웃** 프로젝트에 project hook 을 **새로** 등록한 경우 — hook 실행이
  `run_hook.py` 를 찾지 못하고 실패합니다
- 1.1.0 으로 **Windows** 에 새로 설치하고 project hook 을 등록한 경우 — 1.1.1 에서 이 메시지로 멈춥니다

```bash
# 해당 hook 의 adapter 두 개를 지운 뒤 다시 등록합니다 (hook 트리는 설치 레이아웃에 따라 다릅니다)
rm <hook 트리>/adapters/claude/<hook-id>.sh <hook 트리>/adapters/codex/<hook-id>.sh
sage generate --kind hook --write --target both
```

직접 고친 adapter 라면 지우기 전에 내용을 확인하세요. adapter 는 생성물이라 `sage generate` 가
다시 만듭니다.

## `sage acceptance-waiver` 가 "런타임을 불러오지 못해" 로 끝남

```
[sage acceptance-waiver] acceptance waiver 런타임을 불러오지 못해 waiver 발급·조회·회수를 할 수 없습니다. ...: ModuleNotFoundError: ...
```

1.1.0 이하의 **Windows** 에서는 대장 모듈이 POSIX 전용 `fcntl` 을 불러와 항상 이렇게 끝났습니다
(1.1.0 이하에서는 traceback 으로 보였습니다). **1.1.1 부터 Windows 에서 발급·조회·회수가 동작합니다.**
그 밖의 환경에서 이 메시지가 보이면 설치가 손상된 것이므로 `sage install --force` 로 다시 설치하세요.
대장을 읽지 못하는 동안에도 acceptance 게이트는 계속 차단합니다 — 승인이 없는 것으로도, 있는
것으로도 치지 않습니다.

## `sage: command not found`

```bash
pipx install "sage-harness[schema]"
pipx ensurepath
```

새 터미널을 연 뒤 `sage --version`을 확인합니다. pip user 설치를 사용했다면 `python3 -m sage --help`
또는 Windows의 `py -m sage --help`로 실행할 수 있습니다.

## Windows에서 hook이 실행되지 않음

설치 hook은 bash가 아니라 `sage-hook.exe`를 사용합니다.

```powershell
where sage-hook
sage doctor
```

진입점이 없으면 같은 Python 환경에 `sage-harness`를 다시 설치합니다. 선택적 `.sh` 개발자 회귀를
실행할 때만 `SAGE_BASH`에 Git Bash의 절대경로를 지정합니다. WSL launcher를 암묵적으로 선택하지
않습니다.


## `sage upgrade --apply` 가 큰 저장소에서 끝나지 않음, 또는 실패 뒤 SAGE 와 무관한 파일이 되돌아감

1.3.3 까지 `upgrade --apply` 는 실패에 대비해 **프로젝트 전체 파일의 내용**을 메모리에 담았다가, 실패하면
그 상태로 되돌렸습니다. 빌드 산출물·프로젝트 안 worktree·host 캐시가 크면 끝나지 않았고, 실패하면
apply 도중 IDE·다른 세션이 만든·고친 파일까지 되돌리거나 지울 수 있었습니다.

1.3.4 부터는 **SAGE 가 관리하는 경로만** 담고 되돌립니다 — `sage/`·`sage_harness/`·`docs/sage_harness/`·
`docs/agent/`·`plan_docs/`, `.claude/`·`.codex/` 아래의 `agents/`·`skills/`·`hooks/` 와 host 설정 파일,
루트 framework 문서(`AGENT_GUIDE.md` 등)·`.gitignore`, `.sage/` 의 사이클 선언·감사 기록 파일. 그 밖의 파일은
실패해도 손대지 않습니다.

- apply 중에는 `plan_docs/` 문서나 `.sage/` 감사 기록을 다른 세션에서 고치지 마세요. 이 둘은 되돌림 대상이라
  실패하면 apply 시작 시점으로 돌아갑니다.
- 범위 안 경로나 그 상위 폴더가 링크(symlink·junction)면 그 경로는 담지 않습니다. SAGE 는 링크를 지나는
  자리에 쓰지 않습니다.

## Windows에서 install·upgrade·generate·uninstall 이 잠금 폴더 권한으로 실패

1.3.3 까지는 **관리자 권한 터미널**에서 SAGE 명령을 처음 실행하면 임시 폴더의 잠금 폴더
(`%TEMP%\sage-install-locks`)가 관리자만 쓸 수 있게 만들어져, 그 뒤 같은 사용자의 일반 권한 명령이
`PermissionError` 로 실패했습니다. 1.3.4 부터는 다른 이름(`sage-install-locks-v2`)의 폴더를 권한 지정 없이
만들므로 그 상태에서도 동작합니다. 예전 폴더는 더 쓰지 않으니 관리자 권한으로 지워도 됩니다.

잠금 폴더를 준비하거나 열 수 없으면 「다른 명령이 실행 중」이 아니라 「권한·경로 문제」로 안내하고 폴더
경로와 원인을 함께 보여 줍니다. 그 폴더의 소유자와 권한을 확인하세요.

## Windows에서 `sage context snapshot`·`restore` 가 거부됨

1.3.3 까지는 Windows 에서 두 명령이 항상 `secure read failed ... Permission denied` 로 거부됐습니다. 1.3.4 부터는
Windows 에서도 동작합니다. 그래도 거부되면 오류 끝에 `[report: os=… python=… stage=… error=… path=…]` 한 줄이
붙습니다. 이슈를 올릴 때 이 줄을 함께 붙여 주세요 — 이 줄에는 프로젝트 기준 상대 경로만 들어갑니다. 오류
문장의 앞부분에는 절대 경로가 들어 있으니 공개 이슈에 붙이기 전에 지우세요. 기능을 잠시 끄려면 profile 의
`context_management.compaction.enabled: false` 로 둡니다. host 전환(Claude↔Codex)은 단계 문서(Cycle-Stem)로
계속 이어집니다.

## Windows에서 `sage uninstall --yes` 가 `.sage-install-backup-*` 를 남기고 PARTIAL 로 끝남

Windows 에서는 요청한 제거가 모두 끝난 뒤에도 uninstall 이 만든 임시 보관소(`.sage-install-backup-<token>-*`)가
프로젝트 루트와 `.claude\`·`.codex\` 아래에 남고, 결과가 `PARTIAL`, 종료 코드가 1 로 나올 수 있습니다(알려진 결함,
[#30](https://github.com/SeJonJ/SAGE/issues/30)). 화면의 「직접 지워도 됩니다」 목록에 나온 경로는 지운 파일의 사본이라
직접 지워도 됩니다. 남아 있어도 다시 `sage install`·`upgrade` 하는 데는 영향이 없습니다. 스크립트에서 uninstall 의 종료
코드로 성공을 판단한다면 이 경우를 감안하세요.

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

설치 직후에는 CORE hook이 미스탬프 상태일 수 있으므로 generate를 한 번 실행합니다. 파일을 직접
수정해 hash만 맞추지 마세요.

## Write guard가 편집을 차단

`.claude/`·`.codex/` 생성물, `.mcp.json`, CORE framework 문서는 직접 편집 대상이 아닙니다.

```bash
sage absorb --kind agent --id my-agent
sage generate --kind agent --write
```

지원되는 CORE 자산 커스터마이즈는 `sage-asset-override`를 사용합니다. 프로젝트 정책은
`sage/project-profile.yaml`이나 project-owned governance 문서에 둡니다.

## 세션 위험도 선언이 잘못 잡혀 편집이 막힘

게이트가 Phase 00보다 높은 위험도를 요구하는데 그 위험도가 **이번 세션 선언**에서 왔다면, Phase 00을
올리지 마세요 — 실제보다 높은 위험도를 기록하게 됩니다. 선언을 지우면 됩니다.

```
위험도 선언 해제
```

프롬프트로 그대로 입력하면 이번 세션의 선언이 삭제되고, 이후 판정은 경로·내용 계산만 씁니다. 차단
메시지가 선언 출처를 알려주므로 어느 쪽인지는 안내를 보고 판단하면 됩니다. 선언 때문에만 막힌 경우에는
메시지에 「이번 세션의 L3 선언 때문에 이 검사를 받았습니다」가 붙습니다 — 실제 그 레벨 작업이면 해제하지
말고 위의 안내(사이클 지정·Phase 00 작성)를 따르세요.

선언은 레벨 하나를 평서문으로 적을 때만 잡히고, 잡히지 않은 경우에는 그 사실을 알려줍니다. 말 대신
정확히 지정하려면 메시지 맨 위에 한 줄을 그대로 적습니다(첫 코드 블록보다 앞, 줄 전체). 해제는 `SAGE-RISK: clear`
한 줄입니다. 코드 블록 뒤에 적으면 적용하지 않고 위치만 알려 줍니다 — 그 메시지로는 선언이 바뀌지 않습니다.

```
SAGE-RISK: L3
```

서브에이전트가 돌려준 보고처럼 호스트가 넣은 메시지는 선언·해제로 보지 않습니다. 쓰이지 않은 선언은
2일 뒤 만료됩니다.

선언은 이 세션의 **작업**에 대한 것이라, 다음 쓰기에는 선언을 얹지 않습니다 — 선언하지 않은 세션과
같은 판정을 받습니다.

- 프로젝트 밖으로 확인된 파일(홈 폴더 메모 등). 별칭·대소문자 변형·링크로 프로젝트를 가리킬 수 있는
  경로는 확인되지 않은 것으로 보고 지금처럼 선언을 얹습니다.
- 06 뒤 스킬이 쓰는 마무리 요약 `.sage/knowledge_writeback_summary.md`.

## 「확실히 밖인지 확인하지 못한 경로」 경고가 남

게이트는 경로를 글자로 프로젝트 루트와 비교합니다. 그래서 링크·대소문자 변형·Windows 짧은 이름
(`PROJEC~1`)으로 쓴 프로젝트 파일은 프로젝트 밖으로 보이고, 위험 규칙(`src/**` 등)과 사이클 검사를
받지 않습니다. 이런 경로를 만나면 게이트가 경고합니다. 편집은 막지 않습니다.

- 프로젝트 파일이면 프로젝트 루트 기준 경로로 다시 쓰세요. 경고는 위험 규칙이 적용되지 않았다는
  알림이라, 무시하면 그 편집은 검사 없이 지나갑니다.
- 모든 편집에서 경고가 나면 프로젝트 경로 설정 자체가 링크·다른 표기일 수 있습니다. 도구가 쓰는
  실제 경로와 맞추세요.
- 하드 링크 파일, 대소문자만 다른 별도 폴더처럼 진짜 밖인데 확인할 수 없는 경로도 경고합니다.
  그 경우는 그대로 진행해도 됩니다.

다른 경고·차단과 함께 나면 그 메시지 아래에 경로 한 줄이 붙습니다. override 로 차단을 우회한
호출에서도 같은 경고가 나옵니다.

## `sage validate` 가 `pre_implementation_required` 등급 순서를 경고

높은 등급이 낮은 등급보다 적은 phase 를 요구하면(예: L2=`[00, 01]`, L3=`[00]`) 경고합니다. 생략한
등급은 빈 목록으로 봅니다. 이런 profile 에서는 `L3 로 진행`처럼 높은 등급을 선언하면, L2 선언에서는
막히던 소스 편집이 통과할 수 있습니다. 높은 등급의 목록에 낮은 등급의 phase 를 모두 넣으세요
(L1 ⊆ L2 ⊆ L3). `pdca.enabled: false` 면 묻지 않습니다.

순서를 지킨 profile(기본 템플릿 포함)에서도 남는 차이가 하나 있습니다. 게이트는 그 등급이 요구하는
phase 문서를 쓰는 편집을 결핍 검사에서 빼 줍니다(01 을 쓰려는데 02·03 이 없어 막히는 교착을 풀기
위함). 그래서 높은 등급을 선언하면, 그 등급에서 **새로 필수가 되는 phase 문서**는 순서와 상관없이 쓸
수 있습니다 — 낮은 등급 선언에서는 경고·차단이 나는 쓰기입니다. 소스 편집은 해당하지 않고, 어느
경우도 선언하지 않은 세션보다 느슨하지는 않습니다.

## 문서가 다 있는데 "의무 PDCA phase 미작성"으로 막힘

phase 문서를 고칠 때 게이트는 파일명에서 사이클을 알아냅니다. 소스 편집에는 그런 단서가 없어서 **git
브랜치 이름의 마지막 조각**에서 추론합니다. 사이클마다 브랜치를 따면 맞고, 브랜치 하나로 여러
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
출력합니다. 선언했는데 안 먹는다면 그 출력부터 보세요. 기존 Phase 00과 충돌하면 아무것도 덮지 않고
충돌 경로와 사용 가능한 stem 후보 3개를 출력합니다. 커스텀 Phase 00 glob 때문에 위치를 유도할 수
없을 때만 root 상대 디렉터리를 `--path DIR`로 지정하세요.

`--create`는 Phase 00만 만듭니다. profile이 01~03을 요구하면 작성 전까지 소스 편집은 계속
차단됩니다. 긴급 작업에서 면제 가능한 phase 결핍만 열려면
`sage override --reason "hotfix" --ttl 1h`처럼 짧게 발급하세요. Phase 00의 risk 선언·정합 차단은
override로 면제되지 않습니다.

`sage-cycle` 우산은 직접 `set`/`clear`하지 않습니다. `sage-plan`이 stem 검증 뒤 선언하고,
`sage-team`이 재개 시 `show`로 대조한 뒤 write-back·retro·snapshot과 종료 게이트까지 완료하면
해제합니다. `BLOCKED`/`FAIL`에서는 재개를 위해 선언을 남깁니다. `set B`는 포인터만 바꾸므로 A의
문서·증거·감사는 그대로 남고, `set A`로 돌아가면 판정도 복원됩니다.

## Done Criteria 또는 stale Phase 05 승인으로 차단됨

같은 stem의 Phase 00만 먼저 수정하세요. 정확한 `## 5. Done Criteria`, 양의 `Done-Criteria-Revision`,
`[ ]`·`[x]`·사유 있는 `[~]` 형식을 복구합니다. 기준 문구나 범위가 바뀌었다면 revision을 올리고
Changed-At·Reason·Affected-Phases·Summary를 기록한 뒤 영향 phase를 순서대로 재실행합니다. 기존 Phase
05 승인은 재사용하지 말고 새 review loop를 `--cycle-stem`과 함께 수행한 뒤, APPROVED close가 출력한
`Phase00-Hash`와 새 `Loop-Run`을 Phase 05에 기록하세요. Phase 00과 후속 phase를 한 번에 수정하면
pre-write 상태를 검증할 수 없어 차단되므로 나눠서 씁니다.

## 코드 블록 안 예시가 선언·승인으로 읽힘, 또는 업그레이드 뒤 문서 판정이 바뀜

사이클 문서의 `Cycle-Stem`·`Final Status`·Done Criteria·Fast 증거 줄은 코드 블록 밖에서만 읽습니다.
코드 블록을 닫는 줄은 펜스(```` ``` ```` 또는 `~~~`) 뒤에 공백·탭만 올 수 있습니다(CommonMark). 블록 안의
```` ```python ```` 이나 ```` ``` 끝 ```` 은 블록을 닫지 않고 내용으로 남습니다.

1.3.2 까지는 이런 줄이 블록을 닫아, 그 뒤의 예시를 진짜 선언으로 읽었습니다 — 예시 `Cycle-Stem` 때문에
「선언이 2개」로 막히거나, 예시 `Final Status: APPROVED` 를 승인으로 읽었습니다. 1.3.3 부터는 GitHub 에서
코드로 보이는 줄을 SAGE 도 코드로 봅니다. 그래서 업그레이드 뒤 판정이 바뀔 수 있습니다. 예시만 있고
진짜 승인 줄이 없던 05 는 06 작성이 막히고, 예시 때문에 중복으로 막히던 문서는 통과합니다. 막히면 블록
밖에 진짜 선언 줄을 한 번 적으세요.

## 사이클을 끝냈는데 다음 작업이 "이미 완결된 사이클"로 막힘

선언은 셸을 넘겨 살아남습니다. 끝난 사이클의 선언이 남아 있으면 새 작업이 거기 결속되고, 게이트가
그걸 막습니다.

```bash
sage cycle clear                     # 파일 선언 해제
unset SAGE_CYCLE_STEM                # env로 선언했다면
```

차단 메시지가 결속을 **선언된**으로 읽었는지 **브랜치에서 추론한**으로 읽었는지 알려주므로, 어느
쪽을 지워야 하는지는 안내를 보고 판단하면 됩니다.

## `sage install`이 "SAGE source resources changed"로 실패

설치 도중 SAGE 엔진 소스가 바뀌면 반쯤 섞인 산출물이 나오므로 install이 스스로 중단하고 롤백합니다.
검사는 정상 동작이고, 대부분 원인은 **테스트나 리뷰 도구가 저장소 파일을 잠깐 고쳤다 되돌리는
것**입니다.

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

`reason_required`는 profile에서 완화할 수 없으므로, 값을 채워 다시 시도하는 것 외에 우회 경로는
없습니다.

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

전환한 뒤에도 소스 편집이 `block_phase_incomplete`로 막힌다면, 전환 시점에 존재하던 phase 목록이 그
위험도의 `pre_implementation_required`를 다 담지 못한 것입니다. 전환은 **가진 것만** 면제하므로
Phase 00에서 전환했다면 01~03을 그대로 작성해야 합니다. 전환된 run은 문서에 `Fast-Audit-Run` 줄을
갖지 않는 것이 정상이며, 그 줄이 없다고 손으로 추가하면 안 됩니다.

## 조기 종료(`USER_AUTHORIZED_EARLY`)가 거부됨

```
[sage review-loop] early completion refused: pdca.review_loop.early_completion.enabled=true is required
[sage review-loop] --survived-by-severity invalid: severity total 2 does not equal survived 3
```

조기 종료는 `pdca.review_loop.early_completion.enabled: true`가 필요하고, `sage review-loop next`가
`CONTINUE`를 권고하거나 사용자가 정할 상한(`STOP BUDGET_ITER`, `ASK CYCLE_CAP`)에서 멈췄을 때 쓸 수
있습니다. `CONVERGED`면 정상 close를 쓰고, `BUDGET_TOK`·`BLOCKED_ARCH`는 승인으로 닫을 수 없습니다.
영수증 합계 오류는 `--survived-by-severity`의 합이 그 라운드의 `--survived`와 다르다는 뜻입니다 —
`P0=0`만 적어 차단 finding을 숨기는 것을 막는 검사라 우회 경로가 없습니다.

승인으로도 엔진 차단을 통과하지 않는 것들이 있습니다: 라운드 0건, `severity_block` 심각도의 미해결
finding, architecture escalation, Done Criteria 미해결, acceptance `FAIL`, 감사 손상. 이 중 하나로
막혔다면 그 원인을 실제로 해소해야 합니다.

필수 build/test/lint 실패도 조기 완료해서는 안 되지만, 그 결과는 Phase 03 산문에만 있어 엔진이 직접
읽지 못합니다. 이 항목은 에이전트가 사용자에게 그대로 알리고 close를 진행하지 않아야 하는
의무입니다.

## review loop 가 열리지 않거나 라운드가 거부됨 (사이클 결속·상한)

```
[sage review-loop] 사이클을 정할 수 없습니다 — `sage cycle set <stem>` 으로 선언하거나 --cycle-stem 을 주세요. ...
[sage review-loop] decide refused: cycle demo has not reached its round cap (2/3); nothing to decide
```

run 은 항상 사이클에 묶입니다. 라운드 상한(`pdca.review_loop.max_cycle_rounds`, 기본 L3 5 · L2 3)을
같은 사이클의 모든 run 을 합쳐 세기 때문입니다. `sage cycle set <stem>` 으로 사이클을 선언하거나
`open --cycle-stem <stem>` 을 주십시오. 1.3.0 부터 생긴 거부입니다.

- `<stem>` 은 이 사이클 Phase 00 문서의 `Cycle-Stem:` 값을 그대로 씁니다. 최근 문서나 비슷한 이름으로
  짐작하지 마십시오. 거부는 풀리지만 run 이 다른 사이클에 묶여, 상한을 그 사이클의 라운드와 합쳐 세고
  경고도 나오지 않습니다. 후보가 여럿이거나 확실하지 않으면 에이전트는 고르지 말고 사용자에게 묻습니다.
- 환경변수 `SAGE_CYCLE_STEM` 은 선언 파일보다 우선합니다. 다른 사이클을 가리키면 `unset SAGE_CYCLE_STEM`
  뒤 다시 선언하십시오. `sage cycle show` 가 어느 쪽 값을 쓰는지 보여 줍니다.
- 패키지만 올리고(`pipx upgrade`) 프로젝트 자산을 갱신하지 않으면 스킬이 이전 버전 그대로라, 에이전트가
  이 규칙을 모른 채 거부를 만납니다. 업그레이드 뒤 `sage upgrade --apply` 로 자산까지 갱신하십시오.

`next` 가 `NEXT: ASK kind=CYCLE_CAP` 을 내면 사이클이 상한에 닿은 것이고, 사용자가 정하기 전에는
`round` 가 거부됩니다. 계속하려면 `sage review-loop decide --run-id <id> --cycle continue --extend <N>
--reason <사유> --decided-by <이름>`, 남은 비차단 지적을 인수하려면 조기 종료, 멈추려면
`close --result BLOCKED --reason CYCLE_CAP` 입니다. `decide` 는 상한에 닿은 뒤에만 받습니다 — 미리 늘려
두면 「상한에서 묻는다」는 계약이 사라지기 때문입니다. 업그레이드 전에 사이클 없이 열린 run 은 상한을
소급 적용하지 않고 `show` 에 따로 표시합니다.

## 크리티컬 P2 결정 전이라 라운드·종료가 거부됨 (`converge_on: blocking`)

```
[sage review-loop] run rl-… 의 크리티컬 P2(F3)가 개발자 결정을 기다립니다. ...
[sage review-loop] decide refused: F2 is not a critical P2 awaiting a decision (pending: F3)
```

`converge_on: blocking` 으로 연 run 은 크리티컬 P2 를 자동으로 고치지 않습니다. `next` 가 `NEXT: ASK
kind=CRITICAL_P2 findings=…` 를 내면 지적마다 개발자에게 보고하고 `sage review-loop decide --run-id <id>
--finding <id> --claim <hash> --fix|--accept --reason <사유> --decided-by <이름>` 으로 기록하십시오. 그 전에는 라운드도,
`BLOCKED_ARCH`·`BUDGET_TOK` 외의 종료도 거부됩니다. 결정은 그 라운드의 지적 내용에 묶여서, 다음 라운드에
같은 크리티컬이 다시 살아남으면 다시 묻습니다.

`round` 가 `converge_on: blocking 규칙을 어깁니다` 로 거부되면 사이드카를 고치십시오 — `critical` 은 P2
에만, 분류는 `critical_p2` 목록 안에서, P0·P1·크리티컬 지적을 `out_of_scope_preexisting` 으로 버리려면
`preexisting: true` 와 `exposure: unchanged` 가 있어야 합니다(이번 변경이 그 결함을 건드렸거나 노출을
바꿨으면 버릴 수 없습니다).

`next` 가 잔여만 남았는데도 `CONTINUE` 를 내면 근거 줄을 보십시오. 마지막 라운드가 사이드카 없이
기록됐거나(크리티컬 0 을 증명할 수 없음), 미결 반박·미탐색 렌즈가 남았거나, Fast run 의 최소 라운드에
아직 못 미친 것입니다.

## Phase 05가 "보증 저하 표기" 때문에 막힘

```
잔여를 안고 닫히지 않은 run 인데 보증 저하를 자칭함: [...]
Review-Assurance 선언은 fence 밖에 정확히 1개여야 함(found 0)
```

기준은 표기의 존재가 아니라 **값**입니다. `Review-Assurance` 에 `REDUCED_BY_USER_AUTHORIZATION`·
`REDUCED_BY_POLICY`, 또는 `Review-Close-Reason` 에 `USER_AUTHORIZED_EARLY`·`CONVERGED_RESIDUAL` 중 하나라도
적으면 보증 저하를 자칭한 것입니다. 자칭했거나 감사가 그 사유(조기 종료·잔여 승인)로 닫혔다면 네 표기(`Review-Assurance`, `Review-Close-Reason`,
`Review-Rounds`, `Residual-Findings`)를 모두 적고 값이 감사 레코드와 일치해야 합니다 — 조기 종료는
`REDUCED_BY_USER_AUTHORIZATION`, 잔여 승인은 `REDUCED_BY_POLICY` 입니다. 정상 수렴한
run이라면 그 두 값을 적지 않습니다. `Review-Rounds: 3` 같은 중립 표기만 있는 것은 막지 않습니다.
`Review-Rounds`의 `(configured max: <max>)`도 감사와 같아야 합니다. 상한이 없는 프로젝트는 감사와
같은 낱말인 `unbounded`를 적습니다.

표기를 올바르게 적었는데 `found 0`으로 막힌다면 fence 안에 들어갔는지 확인하십시오 — 코드블록 안의
줄은 세지 않습니다.

## 조기 완료가 `unresolved acceptance`로 거부됨

선택된 Phase 04에 acceptance `FAIL`이나 exact waiver 없는 필수 `NOT TESTED`가 남아 있습니다. 조기
완료는 리뷰가 남긴 finding을 인수하는 절차이지 미검증 요구사항을 넘기는 절차가 아니라, 이 상태는
사용자 확인으로도 통과하지 않습니다. 04 증거를 `PASS`로 채우거나, L3에서
`sage acceptance-waiver grant`로 해당 ID를 명시 승인한 뒤 다시 실행하십시오. 판정은 Phase 06 리포트
게이트와 같은 정책을 쓰므로, 여기서 통과시켜도 06에서 같은 이유로 막힙니다.

## `sage cycle clear`가 활성 Fast run 때문에 막힘

Fast 감사가 열린 상태에서 선언부터 지우면 이후 증거가 다른 stem에 결속될 수 있어 fail-closed로
막습니다.

```bash
sage fast-cycle show
# 정상 완료
sage fast-cycle close --run-id <fc-id>
sage cycle clear
# 또는 의도적 중단
sage fast-cycle abort --run-id <fc-id> --reason "중단 사유"
sage cycle clear
```

`close`가 거부되면 00이 최신 Fast review 뒤 바뀌었는지, 05/06의
`Fast-Run`·`Loop-Run`·`Final Status: APPROVED`가 같은 run을 가리키는지 확인합니다. 감사 원문이
손상됐으면 임의 삭제하거나 새 run으로 덮지 말고 복구 가능한 Git 이력과 `.sage/fast_cycle.jsonl`을
함께 검토해야 합니다.

## Fast run이 끝난 사이클에서 편집이 막힘 (`cycle.fast_terminal`)

00의 `Fast-Audit-Run`이 가리키는 run이 이미 close 또는 abort된 사이클입니다. 감사 기록은 정상이고,
그 사이클에서 새 작업을 하려 했다는 뜻입니다.

- APPROVED로 close되고 05 승인·06이 있는 완결 사이클이면 phase 문서와 write-back 요약 수정은
  통과합니다. 소스 수정은 `block_cycle_closed`로 막힙니다.
- abort된 사이클, 05 승인이 없는 사이클, 문서가 아닌 수정은 이 차단을 받습니다. override로 열지
  않습니다 — abort된 사이클은 완결이 아니어서 열면 소스 수정까지 열립니다.

```bash
sage cycle show
sage cycle clear
# 새 작업은 새 사이클로
```

감사 파일 손상이나 plan과 다른 run을 가리키는 경우는 이 차단이 아니라 `cycle.fast_audit_missing`입니다.

## 선언 파일을 편집 도구로 쓰려다 write guard에 막힘

`.sage/cycle.json`은 게이트가 "이 편집이 어느 사이클인가"를 읽는 자리입니다. 직접 쓰면 완결된
사이클을 지목해 게이트를 통과시킬 수 있어서 차단합니다. `sage cycle set|show|clear`를 쓰세요 — CLI는
편집 도구를 거치지 않으므로 가드에 걸리지 않습니다.

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

프로젝트에 설치된 hook 은 그 저장소에 설치된 SAGE 가 만들었고, 그걸 실행하는 `sage-hook`은 머신에
설치된 package 가 준다. 둘의 나이가 다르면 새 hook 이 아직 없는 module 을 import 하고, 그 실패는
host 에 따라 그냥 "hook 이 죽었다" 로 처리된다 — 정책을 실행해야 할 게이트가 조용히 빠지는 경로다.
그래서 이 판정은 **project core 를 import 하기 전에** 정수 비교 하나로 닫는다.

화면의 `Next:` 순서를 그대로 따르면 된다. package 를 먼저 올리고, 설치 자산을 재생성한 뒤,
`sage status`로 확인한다.

`runtime_api marker 가 없습니다`로 막혔다면 manifest 가 1.0 형식인데 marker 만 없는 상태다. 이때
**marker 부재는 "1.0 이전 설치" 로 인정되지 않는다.** 인정하면 marker 와 version 을 함께 지운
downgrade 가 통과하기 때문이다. `sage install --host <host> --force --dest .`로 다시 스탬프한다.

## 차단 메시지에 `Next:`가 없음

SAGE 가 내는 모든 사용자 노출 차단에는 최소 한 줄의 `Next:`가 있고, 그중 최소 하나는 그대로 붙여넣어
실행할 수 있는 명령이다. 사람이 직접 해야 하는 일은 `Next:`가 아니라 `Action:`으로 나온다 — 붙여넣을
수 없는 문장을 `Next:`로 내면 그 토큰이 "다음에 칠 것" 이라는 뜻을 잃는다.

`Next:`와 `Action:` 토큰은 한국어·영어에서 동일하다. 화면에서 검색하거나 로그에서 모아야 하기
때문이다. 대괄호 안의 진단 code(`[gate.phase_incomplete]`)도 같은 이유로 번역하지 않는다.

`Next:`가 하나도 없는 차단을 만났다면 그건 결함이다. 그 code 와 함께 보고하면 된다. 직접 만든
project hook 이 낸 메시지에는 SAGE 가 복구 명령을 추측해 붙이지 않으며, 대신 `Next: sage status`만
보장한다.

## `sage uninstall`이 자동 제거를 하지 않고 목록만 보여 줌

지원 범위 밖입니다. **화면은 두 종류이고 뜻이 다릅니다.**

| 진단 code | 뜻 | `--check` | `--yes` |
|---|---|---|---|
| `uninstall.windows_10_manual_only` | Windows 10 데스크톱 — 자동 제거 후순위 | `BLOCKED`(2) | `BLOCKED`(2) |
| `uninstall.windows_sku_not_supported` | Windows Server·도메인 컨트롤러 | `BLOCKED`(2) | `BLOCKED`(2) |
| `uninstall.unsafe_platform` | 32-bit Python·native ARM64·비 NTFS·네트워크/UNC | 계획의 상태 그대로 | `BLOCKED`(2) |

앞의 둘은 **지원 정책**이 SKU와 build만 보고 내리는 판정이라 계획 단계에서 결론이 납니다. 그래서
`--check`도 `BLOCKED`입니다 — 자동 제거가 이 환경에서 결코 일어나지 않는데 계획만 보여 주면 곧
실행될 것처럼 읽히기 때문입니다. 이 판정은 볼륨이나 native 기능을 **재지 않으므로**, 이 환경이
기술적으로 가능한지 여부는 말하지 않습니다.

마지막 하나는 **capability**를 실제로 잰 결과입니다. 볼륨을 바꾸거나 다른 root를 고르면 참이 될 수
있는 조건이라 계획은 그대로 보여 주고, 거부는 실제 mutation 요청에만 걸립니다.

이때 `--check`는 **capability를 재지 않습니다.** 계획을 세워 그 상태를 그대로 낼 뿐이라, 종료 코드는
계획이 어떻게 나왔는지에 달려 있습니다 — 대개 `COMPLETE`(0)이나 `PARTIAL`(1)이지만, manifest
손상처럼 **계획 자체가 막히는 사유**가 있으면 `--check`도 `BLOCKED`(2)입니다(예:
`uninstall.plan_failed`). `unsafe_platform`은 그 경우의 사유가 아닙니다.

어느 쪽이든 **파일은 하나도 바뀌지 않습니다.** 화면이 주는 네 목록을 그대로 따르면 자동 제거와 같은
결과가 됩니다.

```bash
sage uninstall --check --json
```

`STRIP`은 공유 파일에서 SAGE 등록만 빼라는 뜻입니다 — 파일 전체를 지우면 host 설정을 잃습니다.
`DELETE`는 통째로 지워도 되는 항목입니다. `PRESERVE`와 `BLOCK`은 **지우지 마세요**: 소유권이
불명하거나 손상된 항목이라 SAGE가 판단을 보류한 자리입니다. 처리 순서는 `STRIP` → `DELETE`이고
`manual_cleanup.order`에 같은 값이 실려 나옵니다.

## `sage uninstall`이 `PARTIAL`(1)로 끝나고 같은 목록을 다시 냄

정상입니다. `COMPLETE`(0)은 **지울 것도 보존 잔재도 없는 완전히 깨끗한 상태**에서만 나옵니다.

손으로 정리한 뒤 손상된 host 설정 같은 보존 항목만 남아 있으면 그다음 실행은 `PARTIAL`(1)이고 남은
경로와 사유를 다시 보고합니다. 남은 것이 있는데 0으로 끝나면 그 사실이 화면에서 사라지므로 그렇게
하지 않습니다. 그 실행도 아무것도 바꾸지 않고 보관소를 만들지 않습니다.

## `sage uninstall`이 확인 prompt 뒤에 `BLOCKED`(2)로 멈춤

계획을 보여 준 시점과 지금의 디스크가 다릅니다. 기준선은 **계획을 화면에 낸 순간**의 상태이고,
prompt가 열려 있는 동안 대상 파일을 고치면 합의한 상태와 실제가 어긋납니다. 디렉터리는 그 안의
파일까지 비교합니다.

다시 `sage uninstall --check`로 현재 계획을 확인한 뒤 실행하세요. 다른 SAGE 명령이 같은 위치에서
작업 중이어도 막힙니다 — `install`·`generate`와 **같은 lock**을 쓰므로 한쪽이 파일을 놓는 동안 다른
쪽이 지우는 일이 없습니다. lock은 프로세스가 끝나면 풀리며 치울 lock 파일은 없습니다.

## `sage uninstall` 뒤에 임시 보관소가 남음

**명령은 성공입니다.** 요청한 제거는 이미 끝났고, 치우지 못한 `.sage-install-backup-` 경로만 알려
드립니다. 그 목록은 text와 `--json`이 같은 근거로 냅니다. 지우려면 알려 준 경로만 지우세요.

## Cross-model 리뷰가 BLOCKED

`sage cross-check` 출력의 `REVIEWER_BLOCK_REASON`이 원인을 알려 줍니다.

| 사유 | 할 일 |
|---|---|
| `cli_missing` | `sage doctor`로 반대 runtime CLI 설치를 확인합니다 |
| `flags_rejected` | 리뷰어 CLI가 SAGE의 통제 플래그를 모릅니다. CLI를 최신으로 올립니다(claude 2.1.275·codex 0.155.1 이상) |
| `startup_failed` | 리뷰어가 시작하지 못했습니다. 반대 runtime에서 로그인·인증 상태를 확인합니다 |
| `usage_limit` | 반대 runtime의 사용 한도가 소진됐습니다. 리셋 뒤 다시 실행하거나, required가 아닌 정책에서 해당 호출에 `--on-peer-failure same-runtime`을 명시해 폴백을 시도합니다(재실행도 peer부터 호출) |
| `timeout` | 제한 시간을 넘겼습니다. 이미 나온 finding은 `PARTIAL`로 남습니다. 패킷을 줄이거나(명제·컨텍스트 지도 중심) `--timeout`을 늘립니다 |
| `exit_nonzero` | 리뷰 도중 비정상 종료했습니다. stderr 요약을 확인하고 다시 실행합니다 |
| `parse_failed` | 리뷰어는 답했지만 결과를 읽지 못했습니다. 폴백으로 덮지 말고 출력 형식을 확인합니다 |

required 정책에서는 peer runtime에 도달하지 못한 상태를 same-runtime 성공으로 낮추지 않고, 폴백도 하지
않습니다. 사유별 동작은 [교차 리뷰](cross-review.md)에 있습니다.

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
