# [Base Plan] SAGE-FB-15 install preflight-first와 실패 원자성

Cycle-Stem: `sage-fb-15-install-atomicity`
Risk Level: L3
Status: COMPLETE

## 1. Context

현재 `sage install`은 profile과 CORE trust만 먼저 검사한 뒤 framework, CORE hook/spec/render,
Codex global skill, legacy prune를 순차 적용한다. Overlay/domain contract는 이 변경 뒤에 검사되므로
오류가 나면 manifest만 갱신되지 않을 뿐 신규/기존 파일은 부분 변경된다. apply 도중 파일 시스템
예외가 발생해도 앞서 적용한 변경을 되돌리는 transaction이 없다.

FB-14에서 남긴 preflight/apply 사이 CORE render 교체와 ancestor 변경도 같은 transaction 경계가 필요하다.

## 2. Goal

- overlay/domain/profile/manifest/CORE trust 검사를 모든 일반 copy/global write/prune보다 먼저 수행한다.
- install이 apply 단계에서 실패하면 project CORE와 manifest, 이 실행이 변경한 global CORE skill 및 legacy
  prune를 이전 상태로 복구한다.
- 동일 destination의 동시 SAGE install을 직렬화하고, preflight가 읽은 핵심 입력이 apply 전에 바뀌면 차단한다.
- `--force` 업그레이드도 같은 rollback 계약을 따른다.

## 3. Scope

In scope:

- read-only install preflight와 deterministic failure inventory
- project/global 파일 write 및 legacy prune rollback journal
- destination-scoped install lock
- profile, manifest, overlay, CORE render/ancestor snapshot의 optimistic CAS 재검증
- normal, force, Claude, Codex, first-install, reinstall 회귀 테스트
- 세 번의 independent headless review-rework

Out of scope:

- install scope global/local 선택 정책(SAGE-FB-05)
- 패키지 외부 프로세스가 commit 이후 같은 OS 권한으로 파일을 다시 바꾸는 행위의 방지
- SIGKILL, `os._exit`, 커널/전원 중단 뒤의 durable journal recovery. 이번 계약은 catch 가능한 Python
  예외(`Exception`, `KeyboardInterrupt`, `SystemExit`)의 rollback이며 process-crash atomicity는 아니다.
- 원격 attestation/서버측 권위(SAGE-FB-08)

## 4. Security Cleanup Exception

FB-12 이전에 blocked 자산에 남은 정확한 SAGE managed block 제거는 일반 CORE base 변경이 아니라 실행
중인 위험 지침을 폐기하는 fail-closed 보안 정리다. 이 exact block cleanup은 다른 preflight 오류가 있어도
유지할 수 있으며 base와 manifest receipt는 변경하지 않는다. 이 예외 외 install mutation은 모두 transaction
성공 시에만 commit한다.

## 5. Impact

- Backend/Frontend/Desktop: N/A. SAGE installer와 테스트만 변경한다.
- DevOps: 설치 실패 후 수동 파일 복구 필요성을 줄이고 CI/온보딩의 재현성을 높인다.
- Compatibility: 성공 설치 결과와 create-only/force 의미는 유지한다.

## 6. Done Criteria

1. overlay/domain 오류는 일반 copy, global write, prune, manifest write 전에 차단된다.
2. apply 중 예외는 existing bytes/type/mode와 pruned directory를 복구하고 신규 파일을 제거한다.
3. `--force`도 부분 업그레이드 상태를 남기지 않는다.
4. 동시 SAGE install은 동일 destination에서 직렬화된다.
5. preflight 이후 핵심 입력 drift는 manifest 축복 전에 감지되고 rollback된다.
6. FB-12 exact blocked-block cleanup만 명시적 실패 원자성 예외로 남는다.
7. Claude 또는 사용자 지정 fresh headless fallback 리뷰를 3회 수행하고 findings를 선별 반영한다.
