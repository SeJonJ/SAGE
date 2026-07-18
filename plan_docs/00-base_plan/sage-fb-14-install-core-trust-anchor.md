# [Base Plan] SAGE-FB-14 최초 install CORE base 신뢰 앵커 검증

Cycle-Stem: `sage-fb-14-install-core-trust-anchor`
Risk Level: L3
Status: COMPLETE

## 1. Context

첫 non-force install은 이미 존재하는 CORE 렌더를 create-only 정책으로 skip한다. 이후
`overlay_materialize.materialize`가 그 기존 파일의 base 해시를 `manifest.core_renders`에 기록하므로,
배포 템플릿과 무관한 사용자 파일이나 변조 파일이 정본 base로 축복될 수 있다.

## 2. Goal

- install이 쓰기 전에 기존 CORE 렌더와 현재 배포 template/render를 대조한다.
- 신뢰 앵커가 없고 base가 다르면 설치를 차단하고 manifest anchor를 기록하지 않는다.
- 기존 앵커가 있어도 anchor drift나 현재 배포 base와의 불일치를 재축복하지 않는다.
- 동일한 배포 base와 명시적 `--force` 경로는 유지한다.

## 3. Scope

In scope:

- host별 `overlay_materialize.render_targets` CORE 렌더 trust preflight
- framework/agent/Claude local skill과 profile 기반 agent render 비교
- 충돌 inventory, expected/actual hash, migration/absorb/force 안내
- 첫 install 및 기존 manifest/두 번째 host의 unanchored render 회귀 테스트
- 세 번의 independent headless review-rework

Out of scope:

- overlay/domain preflight 전체를 install 최상단으로 옮기는 FB-15
- install 전체 파일의 transaction/rollback
- 새 migration/absorb CLI 구현
- Codex global skill scope 정책(FB-05)

## 4. Impact

- 기존 프로젝트에 SAGE를 도입할 때 이름이 겹친 파일을 자동 신뢰하지 않는다.
- 동일 배포본 재실행은 계속 멱등 동작한다.
- 충돌이 있으면 사용자가 기존 내용을 inventory 후 overlay/absorb/migration하거나 `--force`를 명시한다.

## 5. Done Criteria

1. unanchored existing CORE base mismatch blocks before any project write.
2. byte/base-equivalent bundled render is eligible for a new anchor.
3. existing anchor drift and current bundle mismatch cannot be re-anchored by non-force install.
4. conflict output identifies host/kind/id/path and expected/actual hashes.
5. blocked install preserves existing project files and manifest state.
6. explicit force remains the overwrite path.
7. Claude review or user-authorized headless fallback completes three independent rounds.
