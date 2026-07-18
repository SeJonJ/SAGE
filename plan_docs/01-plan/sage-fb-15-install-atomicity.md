# [Plan] SAGE-FB-15 install preflight-first와 실패 원자성

Cycle-Stem: `sage-fb-15-install-atomicity`
Risk Level: L3

## 1. Acceptance Matrix

| ID | Requirement | Required? |
|---|---|:---:|
| FB15-AC1 | overlay filename/eligibility/relaxation 및 domain contract 오류가 모든 일반 install mutation 전에 rc=1을 반환한다. | yes |
| FB15-AC2 | first install preflight 실패는 profile/framework/CORE/manifest/global skill/legacy prune를 생성·변경하지 않는다. | yes |
| FB15-AC3 | reinstall apply 중 주입된 write 오류는 기존 파일 bytes/type/mode와 manifest를 복구하고 신규 파일을 제거한다. | yes |
| FB15-AC4 | `--force` apply 실패도 교체된 CORE와 legacy skill prune를 복구한다. | yes |
| FB15-AC5 | Codex global CORE skill 변경도 이후 project apply 실패 시 rollback된다. | yes |
| FB15-AC6 | 동일 destination의 두 install은 lock을 공유하며 두 번째 non-blocking 실행은 명시적으로 차단된다. | yes |
| FB15-AC7 | preflight 이후 profile/manifest/overlay/CORE render 또는 안전 ancestor drift는 commit 전에 감지되어 rollback된다. | yes |
| FB15-AC8 | 성공 경로는 first/reinstall/force와 양 host의 기존 동작 및 manifest anchor 검증을 유지한다. | yes |
| FB15-AC9 | FB-12 blocked managed-block cleanup 예외는 exact marker만 제거하고 base/manifest를 보존한다. | yes |
| FB15-AC10 | independent review 3회와 finding triage를 완료한다. | yes |

## 2. Failure Contract

- Preflight는 project/global install 산출물과 legacy path를 쓰거나 삭제하지 않는다.
- Transaction은 mutation 전에 journal entry와 예상 출력을 먼저 기록하고, 원본 filesystem object를 같은
  parent의 private backup으로 원자 이동한 뒤 새 값을 쓴다. logical commit 이후 backup 제거는 post-commit
  GC이며, rollback은 commit 전 새 값을 제거한 뒤 원본 object를 복귀시킨다.
- catch 가능한 Python 예외가 apply 중 발생하면 rollback한다. SIGKILL/전원 중단처럼 Python rollback이
  실행되지 않는 process crash는 보장하지 않는다.
- rollback 시 install output이 외부에서 바뀌었으면 현재 값과 원본 backup을 모두 보존하고 rc=1로 충돌을
  보고한다. 외부 값을 삭제해 원본을 강제 복귀시키지 않는다.
- 신규 파일 rollback 뒤 transaction이 만든 빈 parent directory도 제거한다.
- rollback 자체가 실패하면 원래 오류와 복구 실패 경로를 모두 출력하고 rc=1을 유지한다.
- global skill write의 기존 비치명적 정책은 유지하되, 실제로 변경된 global skill은 project transaction과
  같은 journal에 결속한다.

## 3. Concurrency Contract

- 절대 destination을 해시한 process lock을 project 밖 임시 경로에 둔다.
- 동일 SAGE installer끼리는 destination 단위로 직렬화한다.
- profile, manifest, overlay inventory/content, CORE render와 안전 ancestor의 preflight fingerprint를 apply 직전
  및 commit 직전에 비교한다.
- 같은 권한의 비협조 프로세스가 commit 뒤 다시 변경하는 것은 로컬 installer가 제공할 수 있는 권위 경계가
  아니며 `validate`/서버 attestation 범위다.

## 4. Compatibility

- `_write`, `_copy_*`, global skill helper는 transaction 인자를 선택적으로 받아 기존 단위 테스트 호출을 유지한다.
- non-force create-only와 `--force` overwrite, project-local verify script 보존 정책은 유지한다.
- FB-12 cleanup은 일반 transaction 앞의 제한된 보안 정리로 남고 별도 출력으로 식별한다.
