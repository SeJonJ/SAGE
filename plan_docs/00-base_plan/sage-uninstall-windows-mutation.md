# [기본 계획] Windows 실제 제거 — handle 결속 mutation backend

Cycle-Stem: `sage-uninstall-windows-mutation`
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 6
Status: REWORK 6 — Phase 05 재검토 BLOCKED(2026-09-04) 지적 반영

## 이 사이클의 성격

`sage-uninstall` 사이클은 2026-08-31에 Phase 05 `APPROVED`로 닫혔고, 그 사이클이 남긴 확정 잔여 위험이 EH-30이다. 이 사이클은 그 잔여 위험 하나를 닫는다. 새 명령을 만들지 않고, 이미 승인된 제거 계약을 **Windows에서도 실행할 수 있게** 한다.

되돌릴 수 없는 쪽으로 틀리는 명령을 지금까지 막고 있던 것은 `_PINNING` 하나다. 그 값을 참으로 만드는 것이 목표가 아니라, POSIX가 `dir_fd`로 얻던 **같은 결속**을 Windows에서 얻는 것이 목표다. 결속 없이 값만 참이 되면 이 사이클은 EH-30을 닫는 것이 아니라 EH-30이 막고 있던 사고를 여는 것이다.

## 0. 사전 지식

| 구분 | 근거 | 핵심 내용 |
|---|---|---|
| 승인 설계 | Obsidian `SAGE - Windows uninstall 안전한 실제 제거 설계 (EH-30, 26.08.31)` | 영구 SSOT. repo 사본은 `docs/superpowers/specs/2026-08-31-sage-uninstall-windows-safe-mutation-design.md`이며 둘이 다르면 Obsidian이 우선한다. |
| 사용자 결정 | 2026-08-31 설계 승인 | 대중적인 Windows 환경을 우선 지원하고, 검증하기 어려운 파일시스템·네트워크 환경으로 범위를 넓히지 않는다. |
| 사용자 결정 | 2026-08-31 설계 승인 | 자동 제거가 불가능하거나 실패하면 사용자가 직접 정리할 수 있도록 남은 대상의 위치와 처리 종류를 빠짐없이 제공한다. |
| 선행 잔여 위험 | `plan_docs/enhancement-backlog.md` EH-30 | Windows는 `dir_fd` 부재로 mutation을 거부한다. 재검토 조건 둘(실제 race 주입 검사 + POSIX와 같은 계약)이 이 사이클의 수용 기준으로 들어온다. |
| 현재 거부 지점 실측 | `sage/uninstall_executor.py:99` `_pinning_support` · `:490` | `os.O_DIRECTORY`·`os.O_NOFOLLOW`·`os.supports_dir_fd`·`os.supports_fd`를 묻고, 하나라도 없으면 `execute()` 첫 줄에서 `uninstall.unsafe_platform`이다. |
| 결속 구현 실측 | `sage/uninstall_executor.py:140-346` | `_open_dir_chain`·`_rmtree_at`·`_fingerprint_at`·`_tree_fingerprint_at`·`_PinnedTransaction`·`_read_bytes_nofollow`·`_write_new_file`가 전부 `dir_fd` 전용이다. 총 7개 함수 + 1개 클래스. |
| journal seam 실측 | `sage/install_transaction.py:415-441` | `_PinnedTransaction`이 덮어쓰는 것은 `_probe`·`_measure`·`_replace`·`_remove`와 `read_bytes`·`write_new`·`listdir` 7개다. 이 7개가 backend 경계의 실제 넓이다. |
| 지문 정본 실측 | `sage/install_transaction.py:54` `path_fingerprint` | `(kind, S_IMODE, st_dev, st_ino[, size, sha256])`. baseline은 `os.lstat` 기반으로 계획 층이 뜬다. backend가 만드는 값이 이것과 **같아야** 단계별 재검증이 성립한다. |
| 거부 검사 실측 | `scripts/sage_harness/hooks/tests/test_uninstall.py:1804` | 현재 Windows 계약을 지키는 검사는 `unsafe_platform` 하나뿐이다. |
| CI 실측 | `.github/workflows/ci.yml:75-102` `uninstall_matrix` | 3 OS × 3 Python = 9 job. Windows 3 job은 "계획 성공 + 안전 거부"만 확인한다고 주석이 명시한다. |
| 소비자 smoke 실측 | `scripts/ci/uninstall_smoke.py` | Linux·macOS는 실제 설치·제거, Windows는 계획·거부. 이 파일이 Windows 실제 제거 증거의 유일한 원격 자리다. |
| 진단 어휘 실측 | `sage/diagnostic_contract.py:236-256` | uninstall BLOCK code 21개가 이미 있다. 이 사이클은 새 code를 만들지 않고 기존 어휘로 수렴한다. |
| 검증 환경 한계 | 개발 머신 = macOS (darwin 25.6.0) | Windows 실제 실행 증거는 **로컬에서 만들 수 없다.** GitHub Actions `windows-latest`가 유일한 증거 생산 장소다. |
| 작업공간 정책 | 사용자 지시 | worktree·임시 소비 프로젝트·fixture는 `/Users/sejon/project/sage_project_worktree/` 아래에만 만든다. |

## 1. 요약 (목표와 범위)

`sage uninstall`의 실제 mutation을 Windows 10/11 로컬 NTFS에서 지원한다. POSIX가 `dir_fd`로 얻던 부모 결속을 Windows에서는 `NtCreateFile`의 `RootDirectory` 핸들로 얻는다. 정책·journal·roster·표시 경로는 하나도 새로 만들지 않고, **OS별 파일 조작만** 새 경계 뒤로 내린다.

범위 안:

- 부모 결속을 backend 경계로 추출하고 POSIX 구현을 동작 무변경으로 옮긴다.
- Windows handle backend를 `ctypes`만으로 구현한다.
- capability probe가 실패하면 mutation 전에 `uninstall.unsafe_platform`으로 거부한다.
- 자동 제거가 불가능하거나 실패했을 때 수동 정리 안내를 text와 `--json`에 같은 근거로 낸다.
- Windows CI를 "계획·거부 확인"에서 "실제 제거 + 공격성 race 차단"으로 바꾼다.

범위 밖:

- Windows 7/8·Server 구버전, FAT 계열·ReFS, UNC·네트워크 드라이브의 실제 제거
- 권한 상승·UAC, `--force`, 새 CLI 플래그
- `pywin32`·네이티브 helper 도입
- POSIX 안전 경계를 낮추는 어떤 변경
- 엔진 저장소 자기 도그푸딩

## 2. 영향도 분석 (중요)

- **`sage/uninstall_executor.py`**: 가장 크게 바뀐다. `dir_fd` 전용 함수 7개와 `_PinnedTransaction`이 backend 경계 뒤로 내려가고, 이 파일에는 단계 순서·rollback·검증만 남는다. OS 분기가 이 파일에 남으면 경계를 만든 의미가 없다.
- **`sage/uninstall_fs.py` (신규)**: backend protocol과 선택 함수. 어떤 자산을 처리할지는 판단하지 않는다.
- **`sage/uninstall_posix_fs.py` (신규)**: 현재 POSIX 구현의 이사. **동작을 바꾸지 않는다** — 이 사이클에서 POSIX 결과가 달라지면 그건 이사가 아니라 새 버그다.
- **`sage/uninstall_windows_fs.py` (신규)**: `ctypes` 구조체·핸들 수명·capability probe. 이 파일만 Windows를 안다.
- **`sage/uninstall_plan.py`**: 수동 정리 안내의 근거를 계획에서 뽑는다. action 의미(DELETE/STRIP/PRESERVE/BLOCK)는 그대로 두고 **읽는 순서와 신뢰도**만 더한다.
- **`sage/commands/uninstall.py`**: text와 `--json`에 수동 정리 안내를 낸다. 두 출력이 같은 dict를 소비하는 현재 규칙을 유지한다.
- **`sage/install_transaction.py`**: 변경 없음이 목표다. seam이 부족하면 최소로 넓히되 install 동작은 바뀌지 않는다.
- **`sage/i18n/ko.py`·`en.py`**: 수동 정리 안내 문구. 한 쌍으로 움직인다.
- **`scripts/ci/uninstall_smoke.py`**: Windows 분기가 계획 확인에서 실제 제거로 바뀐다. 거부 계약 검사는 범위 밖 fixture로 따로 남는다.
- **`.github/workflows/ci.yml`**: `uninstall_matrix` 주석이 사실과 달라지므로 함께 고친다. 주석이 검사보다 오래 살면 그 주석이 다음 사람을 속인다.
- **`scripts/sage_harness/hooks/tests/test_uninstall.py`**: 거부 하나였던 Windows 계약이 backend contract·구조체·validator·수동 안내 분류로 늘어난다.
- **문서(`docs/cli-reference*.md`·`docs/troubleshooting*.md`)**: "Windows는 계획만" 이라는 현재 서술이 거짓이 된다. 지원 범위를 Windows 10/11 로컬 NTFS로 **좁혀서** 적는다.

영향 없음을 확인해야 하는 곳: `install`·`generate`·`upgrade`는 같은 `DestinationLock`과 `InstallTransaction`을 쓴다. seam을 건드리면 이쪽이 먼저 깨진다.

## 3. 기술과 리스크

핵심 기술 판단은 설계 §4가 이미 내렸다 — 경로 기반 Win32 API + 직전 재검사(대안 A)는 TOCTOU 창을 남기므로 기각, 네이티브 helper(대안 C)는 패키징 비용이 커서 보류, `NtCreateFile` `RootDirectory` 핸들(권장안 B) 채택.

이 사이클이 새로 지는 리스크는 셋이다.

**T1. `ctypes` ABI.** 구조체 offset·access mask·UTF-16 길이가 틀리면 정상 경로는 통과하고 특정 입력에서만 실패한다. 개발 머신이 macOS라 **로컬에서는 한 줄도 실행되지 않는다.** 완화: 구조체 offset을 상수로 쓰지 않고 `ctypes`가 계산한 값을 쓰고, offset·크기 자체를 검사 대상으로 만들고, Windows runner의 primitive spike를 구현 진입 조건으로 둔다.

**T2. 지문 동치.** backend의 `measure`가 만드는 값이 계획 층 `os.lstat` baseline과 다르면 단계별 재검증이 항상 "바뀌었다"가 되거나, 더 나쁘게는 **다른 기준으로 통과**한다. Windows에서 `os.lstat`의 `st_dev`/`st_ino`가 어떤 Win32 호출로 만들어지는지는 CPython 버전을 탄다 — 이것을 추측으로 맞추면 T1과 같은 종류의 조용한 실패다. 완화: 추측을 검사로 바꾼다. root를 고정하는 순간 handle 기준 identity와 `os.lstat` identity를 **실제로 대조**하고, 어긋나면 mutation 전에 `unsafe_platform`으로 거부한다.

**T3. 범위 과장.** NTFS runner 하나의 성공이 "Windows 지원"으로 읽히면, 검증하지 않은 파일시스템의 첫 사용자가 검사자가 된다. 완화: CLI·문서·릴리스 노트 모두 Windows 10/11 로컬 NTFS로 한정해 적고, 범위 밖은 계획을 보여 주되 mutation은 거부한다.

이미 알고 있는 리스크(설계 §12 R2 sharing violation, R3 cloud reparse point, R4 수동 안내 오사용)는 설계가 정한 대로 안전 우선으로 처리하고, 새 판단을 만들지 않는다.

**검증 가능성이 이 사이클의 지배적 제약이다.** 검증할 수 없는 플랫폼 전용 코드는 막으려는 위험보다 나쁘다 — 그것이 지난 사이클이 EH-30을 넣지 않은 이유였다. 그래서 이번에도 "Windows 원격 증거 없이는 완료를 선언하지 않는다"가 리스크 대응이 아니라 완료 조건이다.

## 4. 최종 결론 및 UX 가이드

Windows 사용자는 `sage uninstall`을 다른 OS와 **같은 문장**으로 쓴다. 성공하면 같은 요약이 나오고, 실패하면 같은 진단 code가 나온다. Windows 전용 플래그도 전용 출력 형식도 만들지 않는다.

달라지는 것은 두 가지다.

첫째, 지원 범위 밖(네트워크 드라이브·FAT·capability 부족)에서는 지금처럼 `BLOCKED(2)`로 끝나되, **무엇을 손으로 정리해야 하는지 전부 보여 준다.** 지금은 "안전하게 실행할 수 없습니다"에서 끝나고 사용자는 다음에 무엇을 할지 모른 채 남는다.

둘째, 수동 정리 안내는 계획의 네 의미를 그대로 유지한다. `STRIP` 대상은 "파일 전체 삭제 금지, SAGE 부분만"으로 `DELETE`와 시각적으로 분리하고, `PRESERVE`·`BLOCK`은 삭제 가능 목록에 절대 오르지 않는다. 파괴적 shell 명령(`rm`·`rmdir`·PowerShell recursive delete·wildcard)은 어떤 경우에도 만들어 주지 않는다.

실행이 실패한 뒤의 목록은 **의도했던 계획이 아니라 다시 읽은 실제 상태**다. 다시 읽을 수 없으면 그 항목은 `unknown`이고, 삭제 가능으로 승격하지 않는다. 사용자에게 "지워도 된다"고 말하는 것은 되돌릴 수 없는 조언이라 확인 없이는 하지 않는다.

## 5. Done Criteria

- [ ] Windows 10/11 로컬 NTFS에서 project·global·all 실제 제거가 원격 runner에서 통과한다
- [ ] 상위 경로 교체를 요구한 모든 지점에서 **실제 교체가 일어났거나, 두 독립 rename 경로가 OS 에 의해 사전 차단**되었고, 어느 쪽이든 프로젝트·global root 밖 변경이 0건이다 (차단은 실제 교체로 세지 않는다)
- [x] backend 경계 추출 이후 POSIX uninstall 결과와 rollback 계약에 회귀가 없다
- [x] capability·파일시스템·root identity 중 하나라도 확정되지 않으면 첫 mutation 전에 `uninstall.unsafe_platform`이다
- [x] Windows backend에 경로 기반 write fallback이 존재하지 않는다(소스 검사로 단언)
- [x] 자동 제거 불가·실패 시 수동 정리 목록이 text와 `--json`에서 같은 근거·같은 표시 경로로 나온다
- [x] `STRIP`·`PRESERVE`·`BLOCK` 항목이 삭제 가능 목록에 오르지 않는다
- [x] rollback 실패 상태에서 삭제 가능 주장이 나오지 않는다
- [ ] Windows 핵심 안전 검사의 skip이 0건이다
- [x] CLI·문서·CI 주석이 실제 지원 범위(Windows 10/11 로컬 NTFS)와 일치한다
- [x] **lock 뒤 `open_roots()` 가 검증한 동일 handle 을 mutation·rollback 종료까지 유지한다** (capability probe 의 handle 은 조사용이며 닫힌다)
- [x] 지원 범위 판정이 **확정 실패에서도 거부** 쪽이다 — 최종 경로·드라이브 종류를 확정하지 못하면 로컬로 세지 않는다
- [x] `recheck` 부터 `unlock` 까지 **write root 아래 절대 경로 filesystem 판정이 없다** — mutation·결과 검증·rollback·cleanup 을 전부 포함한다. 예외는 단 하나, cleanup 에서 journal 이 만든 backup 경로에 대한 읽기 전용 `os.path.lexists` 다
- [x] native 실패가 계약된 진단 code 로 CLI text·`--json` 까지 도달한다
- [x] 실행 실패 뒤의 목록은 다시 읽은 상태이며, 다시 읽지 못하면 실행 가능한 순서를 비운다
- [x] 전역 잔여 경로가 `$CODEX_HOME/...` 로 표시된다
- [ ] Windows job 이 실제 mutation 0건이면 **실패한다**
- [x] root 가 여럿일 때 identity 유도는 **모든 root 에 공통인 것**만 고른다. 공통이 없으면 거부한다
- [x] 설계가 요구한 주입 자리 목록과 실행 목록이 **한 권위**로 대조된다
- [x] 열기 이후의 어떤 실패에서도 native handle 을 놓치지 않는다
- [x] commit 후 뒷정리가 실패하면 무엇을 치울지 text·`--json` 이 같은 근거·같은 경로로 말한다
- [ ] Windows matrix 에서 핵심 계약 검사가 돌고 skip 이 0건이다
- [x] Windows 에서 반드시 돌아야 하는 검사 목록이 **줄어들면 실패한다** — 요구 정본과 실행 목록을 다른 파일에 두고 이름으로 대조한다

## 6. Done Criteria Revision Log

Initial revision 1. No replanning record.

### Revision 6
- Changed-At: Phase 05
- Reason: race runner 가 **"돌았다" 를 잘못 세고 있었다.** case 가 아무 상태도 바꾸지 못하고 반환해도 실행으로 셌고, 그래서 Windows 커널이 상위 교체를 막았는데도 `14 injections executed` 가 찍혔다 — 막힌 것과 해낸 것이 같은 숫자에 들어갔다. 그리고 요구 목록이 이름 11개라 root 교체 세 scope 중 하나가 빠져도 나머지가 그 이름을 채웠다. 첫 backup 뒤의 상위 교체는 Windows 에서 **일어날 수 없다** — 우리가 그 디렉터리를 붙들고 있으면 일반 rename 도 handle 기반 rename 도 `ACCESS_DENIED` 다. 그 자리에서 "실제 교체" 를 요구하면 OS 가 먼저 막아 준 상황을 실패로 세게 된다.
- Affected-Phases: 01, 03, 04
- Summary: 각 반례가 `REAL`·`PREVENTED_BY_OS`·`SYNTHETIC`·`FAILED` 중 하나를 말하게 하고, 요구 목록을 scope 포함 고유 id 14건으로 바꿔 성격까지 대조한다. 상위 교체 계약을 "실제 교체" 에서 **"실제 교체 또는 두 독립 rename 경로의 OS 사전 차단"** 으로 넓히되, 차단은 실행으로 세지 않는다. 차단은 계약한 `ACCESS_DENIED` 두 표기로만 인정하고, 차단 뒤에도 정상 완료·사용자 bytes/mode 보존·등록 제거·보관소 0·외부 무변경을 각각 단언한다. 공격은 제품 helper 를 쓰지 않는 별도 프로세스에서 한다.

### Revision 5
- Changed-At: Phase 05
- Reason: rework 6 의 지목 목록(`CORE_SELECTORS`)이 **줄어드는 방향으로 fail-open** 이었다. 빈 tuple 은 `selectors=0`, 필수 한 건 삭제는 `selectors=3` 으로 둘 다 exit 0 이다 — 남은 지목은 전부 해석되고 나머지는 초록이라, 요구가 줄어든 사실이 화면 어디에도 나타나지 않는다. 이 사이클이 반복해서 만난 "없는 것과 통과한 것이 같은 화면" 이 목록 자체에서 한 번 더 났다. 그리고 Phase 00 기준과 Phase 01 FR-W19·A24 는 아직 rework 4 의 문장(`recheck`~rollback 종료)이라, rework 5 에서 실제로 넓힌 계약(`recheck`~`unlock`, write root 전체, backup `lexists` 단일 예외)과 달랐다.
- Affected-Phases: 01, 03, 04
- Summary: 요구 목록의 정본(`A24_REQUIRED_SELECTORS`)을 실행 목록과 **다른 파일**에 두고 runner 가 둘을 이름으로 대조한다. 빈 목록·필수 삭제·정상 검사로의 치환·정본 소실을 전부 exit 1 로 만들고, 해석된 네 이름을 CI 로그에 찍는다. 그 반례들은 `CoreSelectorContract` 로 상시 회귀에 고정했다. Phase 00 기준과 Phase 01 FR-W19·A24 를 현재 계약 문장으로 통일하고, A24 의 요구 증거에 cleanup allowlist 반례와 commit 전 backup probe 반례를 넣었다.

### Revision 4
- Changed-At: Phase 05
- Reason: rework 3 의 여섯 지적은 닫혔지만, A24 의 근거가 실제보다 넓게 적혀 있었다. Phase 04 는 실행 중 가로채기가 `os.makedirs` 까지 감시한다고 기록했는데 검사는 `os.mkdir`·`os.makedirs` 어느 쪽도 걸지 않았고, `_ensure_parents()` 가 실제로 쓰는 primitive 는 `os.mkdir` 이다. 만드는 자리가 감시 밖이면 그 자리는 읽기 감시가 우연히 먼저 걸릴 때만 잡힌다. 창의 경계도 문서와 코드가 달랐다 — 문서는 "commit 까지" 였고 되돌리는 구간은 아무도 보고 있지 않았다.
- Affected-Phases: 01, 02, 03, 04
- Summary: 가로채기 대상에 `os.mkdir`·`os.makedirs` 를 더하고, 창을 `recheck` 부터 **`unlock`** 까지로 넓혀 mutation·결과 검증·rollback 종료와 cleanup 을 전부 덮는다. 감시 범위는 승인된 write root 아래 전부여서 대상의 형제인 backup 경로도 포함한다. commit 뒤 `_cleanup()` 의 예외는 단계가 아니라 **호출 하나** — journal 이 만든 backup 경로에 대한 읽기 전용 `os.path.lexists` — 로 좁혔고, 다른 primitive·다른 경로는 위반으로 센다. 그 경계가 실제로 서는지는 허용되지 않은 조회를 넣어 확인한다. 되돌리기 구간 검사와 `mkdir` seam 직접 검사를 더했다. A24 는 revision 3 의 근거를 **철회하고** 새 검사와 mutation 증거로만 세운다.

### Revision 3
- Changed-At: Phase 05
- Reason: Phase 05 재검토가 다시 `BLOCKED` 였다. P0(root 결속)는 닫혔지만, revision 2 가 "붙든 뒤 경로로 묻지 않는다" 를 참으로 표시한 근거가 **직접 호출만 본 소스 검사**였다 — `_guard_path` 처럼 상속으로 들어오는 판정은 실행 층에 이름이 없어 그 검사를 통과한 채 남아 있었다. 같은 성격으로 multi-root identity 가 첫 root 의 참을 이월했고, `_open_child` 는 열기 뒤 실패에서 handle 을 놓쳤고, commit 후 잔여 안내는 `available:false` 였다. 그리고 Windows 증거 요건 자체가 부족했다 — 설계가 요구한 주입 목록의 일부만 돌았고, 거부 fixture 는 실제 판정 경로를 우회했으며, matrix 는 skip 을 세지 않았다.
- Affected-Phases: 01, 02, 03, 04
- Summary: 소속 판정(문자열)과 경계 판정(파일시스템)을 분리하고, 붙든 뒤의 경계 판정을 전부 결속 seam 으로 옮겼다. 그것이 실제로 사라졌는지는 실행 중 호출 가로채기로 증명한다. identity 유도는 root 별 집합의 교집합으로 고르고, 공통이 없으면 거부한다. 설계 §9.2 의 주입 목록을 코드의 단일 권위로 두고 14개 반례로 채웠다. 거부 fixture 는 최상위가 아니라 가장 아래 primitive 를 갈아 끼워 실제 판정 경로를 돌린다. Windows matrix 에 핵심 계약 검사와 skip 0 단언을 더했다. revision 2 에서 참으로 표시했던 A12·A24·A29 는 근거 부족으로 **철회했고**, 이번 rework 의 새 근거로 다시 세웠다. Phase 04 의 "9 job 통과 시 8건 동시 PASS" 문장은 철회했다.

### Revision 2
- Changed-At: Phase 05
- Reason: Phase 05 가 `BLOCKED` 로 판정하며 P0 하나와 P1 일곱을 냈다. 핵심은 **승인된 계획이 root 결속을 요구하지 않았다**는 것이다 — capability probe 가 연 root handle 과 실제 변경에 쓰는 handle 이 다른 채로도 revision 1 의 Done Criteria 를 전부 만족할 수 있었다. 지원 범위 판정의 fail-open, 붙든 뒤의 절대 경로 재조회, 쓰이지 않는 오류 변환, 실패 후 목록의 근거, 전역 경로 표기, CI 가 실제 mutation 0건으로 초록이 되는 것도 같은 성격이다 — 전부 "검사가 통과했는데 계약은 서지 않은" 자리다.
- Affected-Phases: 01, 02, 03, 04
- Summary: Done Criteria 에 root 결속·fail-closed 판정·결속된 판정·오류 표면·실패 후 근거·전역 표기·CI 강제 일곱을 더했다. Phase 01 에 FR-W16~FR-W22 와 인수 A21~A29 를 더했고, Phase 02 에 root 결속 시퀀스와 오류 단일 경계를 명시했다. Phase 03·04 는 그 항목들의 구현과 증거로 다시 썼다. Windows 실제 증거가 필요한 인수는 POSIX 증거로 대체하지 않고 `NOT TESTED` 로 되돌렸다.
