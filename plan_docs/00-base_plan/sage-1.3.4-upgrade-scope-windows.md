# [기본 계획] upgrade 스냅샷 범위 · Windows 설치 잠금 · Windows context 읽기 (1.3.4)

Cycle-Stem: `sage-1.3.4-upgrade-scope-windows`
Document-Language: ko
Risk Level: L3
Status: DONE — 05 codex cross-review 1차 APPROVED(P2 1, 미룸). Windows 실기 W1~W3 PASS(10-24). 06 작성
Done-Criteria-Revision: 1

## Phase 00 — 기본 계획

### 배경

- 1.3.3 배포 직후 Windows 전체 회귀 시험 확인(#28)에서 제품 결함 두 건, 같은 날 실제 사용 중 `sage upgrade --apply` 가 끝나지 않는 결함(#29)이 보고됐다.
- 설계 정본은 위키 「SAGE - 1.3.4 upgrade 스냅샷·Windows 제품 결함 판정과 설계 (26.10.23)」의 **「확정 설계 — 축소안 1」** 절이다. v5 설계(26~36시간, 자체 리뷰 3회·codex 3회) 뒤 사용자가 개발 최소화를 요청했고, 축소안 두 개를 codex 리뷰 2회씩 받아 안 1(C 함께 수정)로 확정했다.
- 판정 원칙(사용자 지시): 「원래 있던 결함인가」는 기준이 아니다. 결함마다 중요도·위험도·재현도로 판정해, 중요도가 아주 낮거나 위험도가 낮으면 미루고, 중요도·위험도가 높아도 재현도가 낮으면 미룬다. 미룬 항목은 근거와 재검토 조건을 남긴다.
- 엔진 저장소에는 SAGE 를 설치하지 않으므로 이 문서 절차를 손으로 따르고, 05 는 codex cross-review 로 한다.

### 판정 요약

| 항목 | 중요도 | 위험도 | 재현도 | 판정 |
|---|---|---|---|---|
| A. upgrade apply 가 루트 전체를 메모리 스냅샷 (#29) | 높음 | 높음(apply 미완료, 실패 시 범위 밖 파일 삭제·덮어쓰기) | 높음(실보고 + macOS 재현) | 고침 |
| B. Windows 관리자 최초 생성 잠금 폴더 → 일반 권한 명령 전부 실패 (#28-1) | 중간 | 중간(손실 없음, 일반 사용자가 스스로 못 풂) | 중간 | 고침 |
| C. Windows context snapshot·restore 항상 실패 (#28-2) | 중간 | 낮음(보이는 실패) | 높음(항상) | 고침(근본 원인만, 사용자 결정) |
| 읽기 실패 파일 복원 시 삭제 + 성공 보고 · leaf 링크 렌더 소실 · 복원 중 조상 교체 경쟁(EH-21) · codex global 롤백 구멍 · user-owned 동시 작업 손실 · 스냅샷 예외 시 잠금 미해제 · 잠금 파일 링크 거부 · `acceptance_waiver` mode · 잠금 파일 누적 | 항목별(정본 표) | 항목별 | 낮음~매우 낮음(대부분) | 미룸 — 정본 「알려진 한계와 재검토 조건」 |

### 범위

- 포함: A(고정 목록 범위·걷기 경계·시험), B(Windows mode 제거·폴더 이름 변경·잠금 오류 진단, 호출부 install·upgrade·uninstall), C(Windows 경로 열기 + identity 대조 + 읽은 뒤 재확인, junction 판정, Windows mode, 보고 줄), 문서(troubleshooting ko/en, release-readiness 933 → 592).
- 제외: 정본의 「미룸」 항목 전부, #28 시험 이식성(다음 사이클), 버전 올리기(릴리즈 단계).

### Done Criteria
- [x] 큰 무관 폴더(git 무시 빌드 산출물·중첩 worktree·`.claude/worktrees/`·`.codex/.tmp/`·`.sage/` 증거 폴더)가 스냅샷에 들어가지 않는다
- [x] 시험 fixture 7종에서 관측한 롤백 구간의 프로젝트 내부 쓰기가 모두 스냅샷 범위 안이다
- [x] 각 위임 단계 뒤 실패와 백업 정리 실패 뒤 실패에서 범위 안은 시작 전 바이트로 돌아오고 범위 밖 동시 작업은 남는다
- [x] 고정 경로의 시작점·상위가 링크면 그 경로를 담지 않고 밖을 읽지 않는다
- [x] user-owned 보호·기존 롤백 시험이 그대로 통과한다
- [x] 잠금 준비·획득 실패를 install·upgrade·uninstall 이 트레이스백 없이 원인·경로로 안내하고, 진짜 실행 중은 그대로 실행 중으로 안내한다
- [x] Windows 분기가 POSIX 와 같은 context 계약(조상·leaf 교체 거부, 한도, 변경 감지)을 지키고, POSIX 동작·시험은 바뀌지 않는다
- [x] troubleshooting ko/en·release-readiness 갱신, 미러 해시 일치
- [x] 전체 스위트 통과
- [x] codex cross-review APPROVED
- [ ] Windows 11 실기: 관리자 생성 잠금 폴더가 남은 상태에서 일반 권한 install·upgrade·generate·uninstall, context snapshot·restore(host 전환 포함), Windows 묶음 시험

## Phase 01 — 요구사항

### Acceptance Matrix

| ID | 내용 | 증거 | 필수 |
|---|---|---|---|
| A1 | 무관 폴더 8종이 스냅샷 키에 없고, SAGE 관리 파일(profile·host 설정·framework 문서·`.gitignore`·manifest)은 있다 | 단위 시험 | yes |
| A2 | 실제 apply 의 롤백 구간(`_finalize_layout` 진입 전) 동안 감사 hook 으로 본 쓰기와 전후 트리 차이가 모두 범위 안이다 — claude · codex project-local · 두 host · cycle schema v1 · 은퇴 skill · 등록 hook(누락 adapter·shim) · 구 레이아웃 이행 | 통합 시험 7건 | yes |
| A3 | core-assets·hooks·overlays·validate 각 단계 뒤 실패: 범위 안 bytes·mode 가 시작 전과 같고, apply 도중 범위 밖에서 고친·만든 파일은 그대로 | 통합 시험 | yes |
| A4 | install 백업 정리 실패(잔여 백업 이름 존재를 확인) 뒤 실패: 트리 전체가 시작 전과 같다 | 통합 시험 | yes |
| A5 | 시작점 링크(`.claude/skills`)·조상 링크(`.codex`)·정확한 파일 링크(`.claude/settings.json`)에서 링크 너머를 읽지 않는다 | 단위 시험 | yes |
| A6 | 기존 user-owned 보호·롤백·멱등 시험 통과 | 기존 시험 | yes |
| A7 | 범위 상수에서 항목 하나를 빼면 A2 가 실패한다(검출력) | 변이 확인 기록 | yes |
| B1 | Windows 에서 잠금 폴더를 mode 없이 만들고, POSIX 는 0o700 그대로 | 단위 시험 | yes |
| B2 | Windows 잠금 폴더 이름은 `sage-install-locks-v2`, POSIX 는 `sage-install-locks-<uid>` 그대로 | 단위 시험 | yes |
| B3 | 잠금 폴더 생성·잠금 파일 열기 실패는 `install.lock_unavailable`(경로·원인), 잡힌 잠금은 `install.destination_busy` 그대로 | 단위 시험 | yes |
| B4 | install 은 rc 1 + 경로·원인 안내, 아무것도 쓰지 않음 | 시험 | yes |
| B5 | upgrade 는 잠금 실패를 `lock_failed` 로 끝내고 트리를 바꾸지 않음 | 시험 | yes |
| B6 | uninstall 은 잠금 자리 실패를 `uninstall.lock_unavailable` 로, 실행 중은 `uninstall.lock_busy` 그대로 | 시험 | yes |
| C1 | Windows 분기를 강제해 기존 context 시험 전체를 다시 돌려 통과(`dir_fd` 주입 2건은 건너뜀) | 시험 | yes |
| C2 | Windows 분기: `lstat` 뒤 열기 전 leaf 일반 파일 교체 → `changed during secure open`(주입 발동 확인) | 시험 | yes |
| C3 | Windows 분기: 읽는 동안 조상이 링크로 바뀐 채 남음 → 읽은 뒤 재확인이 거부 | 시험 | yes |
| C4 | Windows 분기: 읽는 중 변경 → `changed while being read` | 시험 | yes |
| C5 | Windows 실패 보고 줄에 OS·Python·단계·오류·상대 경로가 있고 절대 경로가 없다 | 시험 | yes |
| C6 | Windows 에서 `.sage/context/` 폴더를 0o700 으로 만들지 않는다 | 시험 | yes |
| C7 | POSIX 분기 동작·기존 시험 불변, 기존 교체 시험 2건에 주입 발동 확인 추가 | 시험 | yes |
| C8 | identity 대조·읽은 뒤 재확인을 빼면 C2·C3 이 실패한다(검출력) | 변이 확인 기록 | yes |
| L1 | troubleshooting ko/en 세 절, release-readiness ko/en 의 Windows 실패 수 정정, 미러 해시 | 문서 시험 | yes |
| W1 | Windows 11: 관리자 소유 구 잠금 폴더가 남은 상태에서 일반 권한 install·upgrade --apply·generate --write·uninstall --check 성공(1.3.3 대조 실패) | 실기 기록 | yes |
| W2 | Windows 11: context snapshot·restore 성공, Claude snapshot → Codex restore, junction 조상·symlink leaf 거부 | 실기 기록 | yes |
| W3 | Windows 11: `test_upgrade`·`test_install_transaction`·`test_install`·`test_context`·`test_uninstall` (실행·통과·skip 수 분리) | 실기 기록 | yes |

## Phase 02 — 설계

정본 「확정 설계 — 축소안 1」이 설계 본문이다. 여기는 구현에서 정한 것만 적는다.

### A. 스냅샷 범위 (`sage/commands/upgrade.py`)
- 상수 넷: `_SCOPE_TREES`(재귀), `_SCOPE_FILES`(정확한 파일), `_SCOPE_USER_OWNED_PARENTS`(바로 아래에서 `_is_user_owned` 참), `_SCOPE_TEMP_PARENTS`(바로 아래 SAGE 임시 이름, 폴더면 재귀). 경로는 `asset_paths` 상수를 쓴다.
- 임시 이름 `_is_sage_temp`: `.sage-` 로 시작(install 백업·overlay·draft·manifest·context), `.sage-tmp` 로 끝남(generate), 선언 쓰기 `.<이름>.<8자>.tmp`.
- `_scope_entries(root)` 가 (상대 경로, 재귀 여부) 를 낸다. 시작점까지 가는 길에 링크(symlink·junction)가 있으면 담지 않는다(`_passes_link`).
- `_snapshot_tree(root)` 는 범위만 걷는다. `_restore_tree`·`_restore_user_owned` 는 지금처럼 `_snapshot_tree` 를 부르므로 같은 범위가 적용된다.
- 링크 판정은 새 `asset_paths.points_elsewhere`(reparse tag 의 name-surrogate 비트 = symlink·junction). `is_reparse` 를 쓰지 않는 이유는 아래 「설계와 달라진 점」.

### B. 잠금 (`sage/install_transaction.py`)
- 이름: uid 있으면 `-<uid>`, 없고 Windows 면 `-v2`, 그 밖은 그대로.
- `_prepare_lock_root`: Windows 는 `os.mkdir(path)`, POSIX 는 `os.mkdir(path, 0o700)`. `mkdir`·`lstat` 의 OS 오류 → `_unavailable(exc)`.
- `_acquire_one`: `os.open` 실패 → `_unavailable(exc)`. 잠금 경합(`msvcrt`·`flock`)은 지금처럼 `destination_busy`.
- `_unavailable`: `InstallBusyError(Diagnostic("install.lock_unavailable", path=lock_root, error="<예외>: <strerror>"))`. catalog `cli.install.lock_unavailable`·`hook.install.lock_unavailable`(ko/en).
- 호출부: install 은 이미 `InstallBusyError` 를 잡는다(변경 없음). upgrade `_apply` 는 `acquire()` 를 `InstallBusyError`·`InstallDriftError` 처리 안으로(생성자 `try` 는 죽은 코드라 제거). uninstall `_acquire_all` 은 진단 code 가 `install.lock_unavailable` 이거나 일반 `OSError` 면 `uninstall.lock_unavailable`, 그 밖은 `uninstall.lock_busy`. CLI 는 `uninstall.*` 를 그대로 내므로 경계 변경 없음. `diagnostic_contract` 에 BLOCK·recovery 등록, catalog 추가.

### C. Windows context 읽기 (`sage/context_packet.py`)
- `_read_regular` 를 열기(플랫폼별)와 공통 검사·제한 읽기로 나눈다. 분기는 모듈 상수 `_WINDOWS_OPEN`(시험이 패치).
- POSIX `_open_by_parent_fd`: 지금 코드 그대로(부모 fd 를 함수 안에서 닫는 것만 다르다 — leaf fd 는 독립).
- Windows `_open_by_path`: `lstat`(링크·일반 파일 아님·한도 거부) → `os.open(path, O_RDONLY|O_BINARY|O_NOINHERIT)`(상수는 `getattr`). 공통부가 `fstat` identity 대조·제한 읽기·전후 대조를 하고, Windows 는 읽은 뒤 `_assert_confined` 를 한 번 더.
- `_is_link` = `is_symlink() or points_elsewhere()` 를 `_assert_confined`·`_ensure_directory` 에서 쓴다. `_ensure_directory` 는 Windows 에서 mode 없이 `mkdir`.
- Windows 의 OS 오류 문장 끝에 `[report: os=… python=… stage=open|read|recheck error=… errno=… path=<상대>]`. 기존 문장 앞부분의 절대 경로는 그대로(정본에서 미룸).

## Phase 03 — 구현

- [x] File ownership assigned before source edits
- [x] Acceptance IDs mapped to implementation tasks
- [x] Verification command plan recorded

### 소유 파일 (단독 작업)
- `sage/commands/upgrade.py`, `sage/asset_paths.py`(`points_elsewhere` 추가)
- `sage/install_transaction.py`, `sage/uninstall_executor.py`, `sage/diagnostic_contract.py`
- `sage/context_packet.py`
- `sage/i18n/ko.py`·`en.py`, `scripts/sage_harness/hooks/runtime/i18n/ko.py`·`en.py`
- `docs/troubleshooting.md`·`.en.md`, `docs/release-readiness.md`·`.en.md`
- 시험: `test_upgrade.py`, `test_install_transaction.py`, `test_install.py`, `test_uninstall.py`, `test_context.py`

### 작업 ↔ acceptance

| 작업 | Acceptance |
|---|---|
| 범위 상수·`_scope_entries`·`_snapshot_tree` | A1, A5, A6 |
| 쓰기 관측기(`_WriteRecorder`)와 fixture 7종 | A2, A7 |
| 단계별·정리 실패 주입 | A3, A4 |
| 잠금 이름·mode·`_unavailable` | B1~B3 |
| 호출부 install·upgrade·uninstall | B4~B6 |
| context 열기 분기·`_is_link`·mode·보고 줄 | C1~C8 |
| 문서 | L1 |
| Windows 실기 | W1~W3 |

### 검증 명령
- 관련 시험: `PYTHONPATH=$PWD python3 scripts/sage_harness/hooks/tests/<file>.py`
- 전체 스위트 로컬 1회: `bash scripts/sage_harness/hooks/tests/run-all.sh`
- 검출력: 범위 상수 항목 하나씩 제거 → A2 실패 확인, context identity 대조·재확인 제거 → C2·C3 실패 확인
- Windows 11(`ssh win11`): 05 뒤. 작업본 tar → venv, 일반 권한(작업 스케줄러)·새 TEMP·인코딩 강제 없음

## Phase 04 — 분석

Status: DONE — 로컬 구현·검증, Windows 실기 W1~W3 완료

### Acceptance Evidence

| ID | Status | Evidence |
|---|---|---|
| A1 | PASS | `TestSnapshotScope.test_unrelated_large_folders_stay_out_of_the_snapshot` |
| A2 | PASS | `TestSnapshotScope` 7건(claude·codex project-local·두 host·cycle schema v1·은퇴 skill·등록 hook·구 레이아웃 이행). 각 fixture 에서 쓰기가 실제로 있었는지 확인, 위치를 확정하지 못한 쓰기 0 |
| A3 | PASS | `TestRollbackStaysInScope.test_each_step_failure_restores_scope_and_keeps_outside_work`(네 단계, 주입 발동 확인) |
| A4 | PASS | `test_backup_cleanup_failure_then_a_later_failure_still_restores`(잔여 백업 존재 확인 뒤 실패) |
| A5 | PASS | `TestScopeWalkBoundary.test_links_on_the_way_to_a_scope_path_are_not_followed` |
| A6 | PASS | 기존 `test_upgrade` 47건 전부 통과(`x.txt` 삭제 실패 시험은 범위 안 이름 `AGENT_GUIDE.md` 로 옮김) |
| A7 | PASS | 변이 4종 — `.claude/hooks` 트리·`.codex/hooks.json`·`verification-protocol.md` 제거: A2 7건 실패, 임시 이름 부모 `.sage` 제거: cycle schema v1 실패 |
| B1 | PASS | `TestLockRootPermissions.test_windows_creates_the_lock_root_without_a_mode`·`test_posix_keeps_the_private_mode` |
| B2 | PASS | `test_windows_uses_a_new_lock_folder_name`, 기존 `test_lock_root_symlink_is_rejected`(이름을 잠금 객체에서 읽도록 수정) |
| B3 | PASS | `test_a_lock_root_that_cannot_be_created_is_a_diagnostic`·`test_a_lock_file_that_cannot_be_opened_is_not_reported_as_busy`·`test_a_held_lock_is_still_reported_as_busy` |
| B4 | PASS | `test_install.test_an_unavailable_lock_is_explained_not_a_traceback` |
| B5 | PASS | `TestLockFailureIsReported.test_an_unavailable_lock_ends_with_lock_failed`(unavailable·busy 둘 다, 트리 불변) |
| B6 | PASS | `test_uninstall.test_a_lock_that_cannot_be_opened_is_not_reported_as_busy`(진단·일반 `OSError`), 기존 `lock_busy` 시험 2건 |
| C1 | PASS | `TestContextPacketWindowsOpen`(기존 16건 상속, `dir_fd` 주입 2건 skip) |
| C2 | PASS | `test_windows_open_rejects_a_leaf_replaced_between_check_and_open` |
| C3 | PASS | `test_windows_open_rejects_an_ancestor_left_as_a_link_after_reading` |
| C4 | PASS | `test_windows_open_detects_a_change_while_reading` |
| C5 | PASS | `test_windows_failure_carries_a_report_line_without_absolute_paths` |
| C6 | PASS | `test_windows_creates_context_folders_without_a_private_mode` |
| C7 | PASS | `TestContextPacket` 16건, 기존 교체 시험 2건에 발동 확인 추가 |
| C8 | PASS | 변이: identity 대조 제거 → C2 와 POSIX 교체 시험 실패, 재확인 제거 → C3 실패 |
| L1 | PASS | `test_documentation`(미러 해시·오류 예시) |
| W1 | PASS | 아래 「Windows 11 실기」 W1 — 1.3.3 은 첫 install 부터 `PermissionError` 트레이스백, 1.3.4 는 install(claude·codex)·generate --write·upgrade --apply 성공. 잠금 폴더를 못 열게 만들면 네 명령 모두 안내로 끝남 |
| W2 | PASS | 1.3.3 snapshot 항상 실패, 1.3.4 snapshot·Claude→Codex restore 성공, junction 조상·symlink leaf 거부, 읽기 오류에 상대 경로 report 줄 |
| W3 | PASS | 다섯 파일에서 1.3.4 실패 ⊆ 1.3.3 실패(시험 이식성). 새 시험은 Windows 에서 통과 또는 근거 있는 skip. 실기에서 드러난 시험 쪽 문제 3건을 고친 뒤의 결과 |

### 검증 결과

- 전체 스위트(`run-all.sh`, 로컬 Python 3.14 한 버전): **3,966건 통과, 실패 0**(1.3.3 의 3,925 + 새 시험 41).
- 새 시험 41건: `test_upgrade` 11(범위 제외 1·관측 7·단계별 실패 1·정리 실패 1·링크 경계 1) + 잠금 실패 1, `test_install_transaction` 6, `test_install` 1, `test_uninstall` 1, `test_context` 21(Windows 분기로 다시 돈 기존 16·skip 2 포함, 새 5).
- `python -m sage validate --check --schema`: WARN(exit 0), main 과 같음.

### Windows 11 실기 (10-24)

조건: Windows 11(10.0.26200), Python 3.12.10, 작업본 tar → venv 두 개(1.3.3 = `c77b771`, 1.3.4 = 작업본). 작업 스케줄러로 **일반 권한** 실행, 인코딩 강제 없음(cp949). 관리자로 만든 1.3.3 잠금 폴더(`sage-install-locks`, 사용자 권한 없음)가 그대로 남은 상태.

**W1 — 잠금**
| 명령 | 1.3.3 (기본 TEMP) | 1.3.4 (기본 TEMP) |
|---|---|---|
| install claude / codex project-local | rc=1, `PermissionError` 트레이스백 | rc=0 (`sage-install-locks-v2` 를 일반 권한으로 생성) |
| generate --kind hook --write | 설치 실패로 진행 불가 | rc=0 |
| upgrade --apply | 설치 실패로 진행 불가 | rc=0 |
| uninstall --check / --yes | 설치 실패로 진행 불가 | 잠금 통과, PARTIAL(아래 「새로 드러난 결함」) |

- 1.3.3 도 새 TEMP 에서는 같은 흐름이 성공한다 → 1.3.3 실패 원인은 잠금 폴더뿐이다.
- 관리자가 `mkdir(..., 0o700)` 로 만든 `-v2` 폴더를 두고 일반 권한으로 돌리면, install·generate·upgrade·uninstall 모두 트레이스백 없이 「권한·경로 문제」 안내와 폴더 경로로 끝난다.

**W2 — context**
- 1.3.3: snapshot 이 profile 읽기에서 `[Errno 13]`(폴더 열기)로 항상 실패.
- 1.3.4: snapshot → profile `active_host` 를 codex 로 바꾼 뒤 restore 성공(`host=claude->codex next_phase=03`, briefing 에 결정 문장 포함).
- junction 조상(`mklink /J plan_docs\02-design`): `uses a symlink path` 로 거부.
- symlink leaf: 일반 권한은 만들 수 없어(1314) 관리자 세션에서 fixture 를 만들어 확인 — 거부.
- 읽기 거부 ACL 을 건 phase 문서: `[report: os=Windows 10.0.26200; python=3.12.10 AMD64; stage=open; error=PermissionError errno=13; path=plan_docs/01-plan/sandbox-cycle.md]` — 상대 경로만.

**W3 — 시험 (일반 권한·새 TEMP)**
| 파일 | 1.3.3 실행/실패·오류/skip | 1.3.4 실행/실패·오류/skip | 1.3.4 에만 있는 실패 |
|---|---|---|---|
| `test_upgrade` (출력 UTF-8) | 45 / 0·6 / 1 | 57 / 0·6 / 2 | 없음 |
| `test_upgrade` (cp949) | 45 / 6·19 / 1 | 57 / 6·31 / 2 | 새 시험 12건 — 직접 호출의 이모지 출력이 cp949 에서 `UnicodeEncodeError`(기존 시험과 같은 이식성 문제) |
| `test_install_transaction` | 20 / 1·4 / 0 | 26 / 1·4 / 1 | 없음 |
| `test_install` | 141 / 34·10 / 1 | 142 / 34·10 / 1 | 없음 |
| `test_context` | 16 / 5·8 / 0 | 37 / 0·2 / 5 | 없음 (1.3.3 의 13건은 #28-2 로 실패하던 것) |
| `test_uninstall` | 335 / 10·10 / 1 | 336 / 10·10 / 1 | 없음 |

- 남은 실패는 전부 #28 의 시험 이식성 분류다: 일반 권한 symlink 생성(1314), cp949 직접 호출 출력, POSIX 전용 API·mode, git tag 부재 등. 다음 사이클 범위.
- 「출력 UTF-8」 줄은 이식성 문제를 걷어 내고 새 시험의 내용을 보려고 `PYTHONIOENCODING=utf-8` 만 더한 비교 실행이다.

**실기에서 드러나 고친 시험 쪽 문제 (제품 코드 변경 없음)**
- `TestSnapshotScope` 7건: 하위 프로세스의 `DEVNULL` 이 Windows 에서 `nul` 이라 쓰기 관측기가 「위치를 확정할 수 없는 쓰기」로 셌다. `os.devnull` 은 프로젝트 쓰기에서 뺀다.
- `test_a_held_lock_is_still_reported_as_busy`: 잡은 잠금을 임시 폴더 삭제 뒤에 놓아 Windows 에서 정리 오류(WinError 32). 판정 뒤 바로 놓는다.
- `test_windows_open_rejects_an_ancestor_left_as_a_link_after_reading`: 실제 Windows 는 열린 파일의 조상 이름 변경을 막는다(WinError 5) — 이 경쟁은 Windows 에서 성립하지 않으므로 실제 Windows 에서는 skip, POSIX 에서 Windows 분기를 강제로 돌릴 때 검사한다.
- 셋 다 로컬 재실행 통과(`test_upgrade` 59, `test_install_transaction`, `test_context`).

**새로 드러난 결함 (이번 변경과 무관, 1.3.3 에도 있음)**
- Windows `uninstall --yes` 가 요청한 제거는 끝내지만 자기 임시 보관소(`.sage-install-backup-*`)를 남기고 PARTIAL·rc=1 로 끝난다. 화면에는 「직접 지워도 된다」는 경로 안내가 나온다.
- 원인: Windows backend 의 보관소 정리(`remove_tree`)가 부모 결속이 풀린 항목에서 `InstallDriftError("unpinned parent")` 를 내고, `commit` 은 `OSError` 만 모으므로 루프가 첫 항목에서 멈춘다.
- 세 축: 중요도 낮음~중간(제거는 끝남, 잔여물·rc=1), 위험도 낮음(손실 없음, 안내 있음), 재현도 높음(Windows 실행 3/3).  잔여물이 남은 프로젝트에 다시 install·generate·upgrade 해도 모두 rc=0(실기 확인). **미룸(사용자 결정, 10-24) — #30.**

**OneDrive:** 사용자 클라우드로 동기화되는 폴더라 실기하지 않았다. `points_elsewhere` 의 OneDrive 판단은 계속 알려진 한계.

### 설계와 달라진 점

- **링크 판정을 `is_reparse` 가 아니라 새 `points_elsewhere` 로.** `is_reparse` 는 reparse 속성만 보므로 OneDrive 클라우드 파일처럼 다른 곳을 가리키지 않는 reparse point 도 링크로 본다. 스냅샷에 쓰면 OneDrive 안 프로젝트에서 담을 파일이 통째로 빠져(롤백 근거 없음) 이번 변경이 새 구멍을 만든다. 1.3.3 까지 스냅샷은 `islink` 만 봤다. name-surrogate 비트(symlink 0xA000000C·junction 0xA0000003)만 링크로 본다. OneDrive 동작은 Windows 실기에서 확인하지 못하면 알려진 한계로 둔다. `is_reparse` 를 쓰는 다른 자리(install·uninstall)는 이번 범위가 아니다.
- **선언 쓰기 임시 이름을 좁혔다.** 처음 규칙(`.` 으로 시작하고 `.tmp` 로 끝남)이 host 캐시 폴더 `.codex/.tmp` 를 통째로 범위에 넣었다(A1 이 잡음). 실제 사용 중인 프로젝트에서는 이 폴더가 수십 MB 였다. `_atomic_write` 의 `mkstemp` 형태(`.<이름>.<8자>.tmp`)만 받는다.
- **쓰기 관측기의 `dir_fd` 복원.** 은퇴 skill 정리가 부모 handle 기준으로 지운다. 감사 이벤트의 `dir_fd` 를 macOS `F_GETPATH`·Linux `/proc/self/fd` 로 경로로 바꾼다. 바꾸지 못하면 미확정으로 실패시킨다. 감사 이벤트는 `dir_fd` 가 없을 때 -1 을 싣는다.
- **upgrade 잠금 생성자의 `try` 제거.** `DestinationLock()` 생성자는 `InstallBusyError` 를 내지 않아 그 `try` 는 죽은 코드였다. 실패하는 자리인 `acquire()` 를 감쌌다.
- 관측 범위는 롤백 구간(`_finalize_layout` 진입 전)이다. 이행 마무리는 설계상 롤백하지 않으므로 관측에서 뺐다.

### 05 1차 지적 처리

| 지적 | 독립 확인 | 판단 | 조치 |
|---|---|---|---|
| [P2] junction 을 지나는 범위 경로를 담지 않는데 install 가드는 `S_ISLNK` 만 보므로 junction 아래 쓰기가 가능 — 단계 실패 시 되돌아가지 않음(이번 변경의 회귀) | 코드 확인: `install.py` 854·`install_transaction.py` 331 의 조상 검사가 `S_ISLNK` 만 본다. 시험 `_in_scope` 는 상수 접두사만 봐 이 경우를 놓친다 | 세 축: 중요도 높음·위험도 중간·재현도 낮음(Windows junction 구성 + 단계 실패) → 사용자 원칙으로 **미룸** | 「링크를 지나는 경로에는 위임 단계도 쓰지 않는다」 주석을 symlink·junction 으로 나눠 정정. 알려진 한계·정본 표에 재검토 조건(junction 사용 보고, 또는 install 가드를 junction 까지 넓힐 때)과 함께 기록 |

### 판정 요청 (05 에)

- A: 고정 목록이 위임 단계(install core-assets·generate hooks·sync-overlays·validate)의 롤백 구간 쓰기를 빠뜨리는가. `_is_sage_temp` 가 무관한 큰 것을 끌어들이는가. 시작점·조상 링크 처리.
- B: 잠금 이름·mode 변경이 POSIX 동작을 바꾸지 않는가. `lock_unavailable` 과 `destination_busy` 의 경계, uninstall 의 code 선택.
- C: Windows 분기가 POSIX 계약(조상·leaf 교체 거부, 한도, 변경 감지)과 같은 뜻인가, 남는 틈이 정본에 적은 것(조상 확인과 `lstat` 사이에 바꿨다가 재확인 전에 되돌림)뿐인가. `points_elsewhere` 판정.

## Phase 05 — 교차 리뷰 (codex)

`plan_docs/05-expert-review/sage-1.3.4-upgrade-scope-windows.md` — 1차 APPROVED(P2 1, 미룸).

## Phase 06

`plan_docs/06-report/sage-1.3.4-upgrade-scope-windows.md` — 잔여 위험과 다음 결정(커밋·릴리즈).

## 알려진 한계

정본 「확정 설계 — 축소안 1」 → 「알려진 한계와 재검토 조건」 표가 기준이다. 이 사이클에서 더한 것:
- **junction 아래 SAGE 경로(이번 변경의 회귀, 05 P2):** 범위는 junction 을 지나는 경로를 담지 않지만 install 가드는 junction 을 막지 않는다. 그 아래에 쓴 뒤 다음 단계가 실패하면 그 쓰기는 남고 롤백은 성공으로 보고된다. 재현도 낮음으로 미룸. 재검토: junction 구성 사용 보고, 또는 install 조상 가드를 junction 까지 넓힐 때(그때 upgrade 도 첫 쓰기 전 거부로).
- `points_elsewhere` 의 OneDrive 판단은 Python 의 Windows `lstat` 동작(name-surrogate 가 아닌 reparse point 는 따라감)과 문서에 근거한 것이고 실기하지 않았다(사용자 결정, 10-24).
- Windows `uninstall --yes` 보관소 잔여(#30): 1.3.3 부터 있던 결함. 위험도 낮음으로 미룸(사용자 결정, 10-24), troubleshooting 에 안내.
