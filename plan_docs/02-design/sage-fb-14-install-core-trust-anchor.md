# [Design] SAGE-FB-14 최초 install CORE base 신뢰 앵커 검증

Cycle-Stem: `sage-fb-14-install-core-trust-anchor`

## 1. Expected Render Resolver

`install`이 실제 배치에 쓰는 동일 리소스와 `render_core_agent` 함수를 사용해 host/kind/id별 expected
base를 계산한다.

```text
framework -> core/framework/{AGENT_GUIDE,CLAUDE,CODEX,AGENTS}.md
agents    -> core/framework/.claude/agents/<id>.md
             claude host만 installed profile의 model/effort를 render_core_agent로 주입
skills    -> core/framework/.claude/skills/<id>/SKILL.md (claude local targets)
```

대상 열거는 `overlay_materialize.render_targets`를 그대로 사용해 anchor 대상과 preflight 대상이 어긋나지
않게 한다.

## 2. Trust Decision

각 existing target의 관리 block을 `overlay_common.base_of`로 제거하고 canonical base SHA-256을 계산한다.

1. non-force의 leaf symlink, 모든 ancestor symlink, non-regular target, read/malformed marker -> conflict.
2. 기존 host anchor가 있으면 actual base hash가 anchor와 일치해야 한다.
3. anchor 유무와 관계없이 actual base가 현재 expected base와 같아야 한다.
4. 두 조건을 통과한 파일만 materialization/새 manifest receipt 대상으로 허용한다.

이 규칙은 첫 install의 arbitrary blessing뿐 아니라 기존 anchor drift와 구버전 base의 non-force 재축복도
막는다. 업그레이드나 의도적 교체는 `--force`가 소유한다. 단 `--force`도 ancestor symlink와
non-regular target은 우회하지 않으며, leaf symlink만 외부 target을 따라 쓰지 않고 링크 자체를 교체한다.

`plan_materialize`가 실제 파일에서 계산한 base anchor를 expected render hash와 다시 대조한 후에만
계획을 적용하고 manifest에 기록한다. 따라서 preflight 뒤 파일이 바뀌어도 그 snapshot이 현재 bundle과
다르면 정본으로 기록되지 않는다. CORE 파일 교체는 같은 디렉터리 임시 파일과 `os.replace`를 사용해
symlink와 hard-link 외부 inode를 직접 truncate하지 않는다.

두 host가 같은 물리 파일을 쓰는 `AGENT_GUIDE.md` receipt는 현재 materialization 결과로 함께 갱신한다.
기존 manifest 경로가 손상되었으면 non-force는 등록 자산과 host history 유실을 막기 위해 차단하고,
명시적 `--force`만 recovery를 허용한다. JSON object여도 필수 필드, host history, asset entries,
CORE receipts의 핵심 형식이 손상되면 같은 규칙으로 차단한다. materialization atomic replace는 기존
regular file mode를 보존한다.

force recovery는 손상된 mapping-shaped asset/receipt를 다시 보존하지 않고 제거하며, primary
`host_runtime`을 `installed_hosts`에 복구한 뒤 shared `AGENT_GUIDE` receipt를 모든 설치 host에 갱신한다.

## 3. Execution Order

```text
load/validate installed profile
  -> load existing manifest read-only
  -> non-force CORE trust preflight
     -> conflict: inventory + rc1, no write
  -> existing install copy/prune/materialize/manifest flow
```

FB-15는 overlay/domain 계약을 포함한 전체 destructive install preflight와 실패 원자성을 별도로 다룬다.

## 4. Conflict Inventory

각 항목은 `host/kind/id`, repo-relative path, reason, expected SHA-256, actual SHA-256을 포함한다. 후속 선택은:

- 기존 파일을 백업/이동한 뒤 재설치
- 프로젝트 지침을 `sage/asset_overrides` 또는 absorb/migration 흐름으로 이전
- 내용을 버리기로 명시한 경우 `sage install ... --force`

자동 migration이나 implicit trust는 제공하지 않는다.
