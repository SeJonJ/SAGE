# [Plan] SAGE-FB-14 최초 install CORE base 신뢰 앵커 검증

Cycle-Stem: `sage-fb-14-install-core-trust-anchor`

## 1. Acceptance Matrix

| Acceptance ID | Requirement | Required |
|---|---|:---:|
| FB14-AC1 | unanchored existing CORE render가 현재 배포 base와 다르면 non-force install은 쓰기 전에 exit 1 한다. | yes |
| FB14-AC2 | unanchored existing CORE render가 현재 배포 base와 같으면 install과 anchor 기록을 허용한다. | yes |
| FB14-AC3 | 기존 anchor와 불일치하거나 current bundle과 다른 base는 non-force 재설치로 재축복되지 않는다. | yes |
| FB14-AC4 | 충돌 inventory는 host/kind/id/path와 expected/actual SHA-256, 해결 경로를 출력한다. | yes |
| FB14-AC5 | blocked preflight는 profile/framework/CORE/manifest를 새로 쓰거나 기존 manifest를 변경하지 않는다. | yes |
| FB14-AC6 | `--force`는 충돌을 명시적으로 덮어쓰고 배포 base anchor를 기록한다. | yes |
| FB14-AC7 | Claude/Codex 및 profile 기반 Claude agent render 비교가 같은 trust 규칙을 따른다. | yes |
| FB14-AC8 | Claude review 또는 Claude 오류 시 fresh headless fallback review를 3회 수행하고 findings를 선별 반영한다. | yes |

## 2. Compatibility

- 대상 파일이 없으면 기존 설치 흐름과 동일하다.
- 관리 overlay block은 base 비교에서 제외하며 malformed marker는 충돌로 처리한다.
- non-force는 동일 current bundle base만 새 anchor 대상으로 인정한다.
- force는 기존 명시적 destructive 선택이며 preflight trust block을 우회한다.

## 3. Failure Contract

- trust preflight는 pure read-only이며 project-local `_write`, global skill install, prune, materialize 전에 실행한다.
- 한 건이라도 충돌이면 모든 충돌을 정렬 출력하고 rc=1을 반환한다.
- symlink/non-UTF-8/malformed overlay marker도 자동 신뢰하지 않는다.
- manifest가 없던 경우 생성하지 않고, 있던 경우 bytes를 보존한다.
- 같은 권한의 concurrent process가 install 도중 경로를 교체하는 공격의 완전 봉쇄는 directory-FD 기반
  전체 transaction이 필요한 FB-15 범위다. FB-14는 materialization이 읽은 base가 arbitrary anchor로
  기록되지 않도록 expected hash에 결속한다.
