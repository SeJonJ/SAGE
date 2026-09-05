# [기본 계획] Windows 실제 제거 — handle 결속 mutation backend

Cycle-Stem: `sage-uninstall-windows-mutation`
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 14
Status: REWORK 15 — 증거 커밋 계약 정정(merge 커밋은 참고값, head.sha 대조 fail-closed) — 유일 blocker 는 A7 (self-hosted 실행 로그 대기)

## 이 사이클의 성격

`sage-uninstall` 사이클은 2026-08-31에 Phase 05 `APPROVED`로 닫혔고, 그 사이클이 남긴 확정 잔여 위험이 EH-30이다. 이 사이클은 그 잔여 위험 하나를 닫는다. 새 명령을 만들지 않고, 이미 승인된 제거 계약을 **Windows에서도 실행할 수 있게** 한다.

되돌릴 수 없는 쪽으로 틀리는 명령을 지금까지 막고 있던 것은 `_PINNING` 하나다. 그 값을 참으로 만드는 것이 목표가 아니라, POSIX가 `dir_fd`로 얻던 **같은 결속**을 Windows에서 얻는 것이 목표다. 결속 없이 값만 참이 되면 이 사이클은 EH-30을 닫는 것이 아니라 EH-30이 막고 있던 사고를 여는 것이다.

## 0. 사전 지식

| 구분 | 근거 | 핵심 내용 |
|---|---|---|
| 승인 설계 | Obsidian `SAGE - Windows uninstall 안전한 실제 제거 설계 (EH-30, 26.08.31)` | 영구 SSOT. repo 사본은 `docs/superpowers/specs/2026-08-31-sage-uninstall-windows-safe-mutation-design.md`이며 둘이 다르면 Obsidian이 우선한다. |
| 사용자 결정 | 2026-08-31 설계 승인 | 대중적인 Windows 환경을 우선 지원하고, 검증하기 어려운 파일시스템·네트워크 환경으로 범위를 넓히지 않는다. |
| 사용자 결정 | 2026-08-31 설계 승인 | 자동 제거가 불가능하거나 실패하면 사용자가 직접 정리할 수 있도록 남은 대상의 위치와 처리 종류를 빠짐없이 제공한다. |
| 사용자 결정 | 2026-09-05 지원 범위 확정 | 정식 자동 제거는 **Windows 11 데스크톱 로컬 NTFS** 다. Windows 10 데스크톱은 자동 제거를 후속 개발로 이관하고, 지금 설치된 상태에서 손으로 정리할 실제 파일과 처리 방법을 안내한다. |
| 사용자 결정 | 2026-09-05 Windows CI 재구성 | 정식 자동 제거는 **Windows 11 데스크톱 workstation · x64 · 64-bit Python · 로컬 NTFS** 다. Windows 10 자동 제거·Server/DC·32-bit Python·**ARM64** 는 이번 지원 범위에서 제외한다. Windows 검증은 hosted matrix 에서 빼고 **self-hosted 전용 job** 으로 옮기며, Ubuntu·macOS CI 는 바꾸지 않는다. |
| 선행 잔여 위험 | `plan_docs/enhancement-backlog.md` EH-30 | Windows는 `dir_fd` 부재로 mutation을 거부한다. 재검토 조건 둘(실제 race 주입 검사 + POSIX와 같은 계약)이 이 사이클의 수용 기준으로 들어온다. |
| 현재 거부 지점 실측 | `sage/uninstall_executor.py:99` `_pinning_support` · `:490` | `os.O_DIRECTORY`·`os.O_NOFOLLOW`·`os.supports_dir_fd`·`os.supports_fd`를 묻고, 하나라도 없으면 `execute()` 첫 줄에서 `uninstall.unsafe_platform`이다. |
| 결속 구현 실측 | `sage/uninstall_executor.py:140-346` | `_open_dir_chain`·`_rmtree_at`·`_fingerprint_at`·`_tree_fingerprint_at`·`_PinnedTransaction`·`_read_bytes_nofollow`·`_write_new_file`가 전부 `dir_fd` 전용이다. 총 7개 함수 + 1개 클래스. |
| journal seam 실측 | `sage/install_transaction.py:415-441` | `_PinnedTransaction`이 덮어쓰는 것은 `_probe`·`_measure`·`_replace`·`_remove`와 `read_bytes`·`write_new`·`listdir` 7개다. 이 7개가 backend 경계의 실제 넓이다. |
| 지문 정본 실측 | `sage/install_transaction.py:54` `path_fingerprint` | `(kind, S_IMODE, st_dev, st_ino[, size, sha256])`. baseline은 `os.lstat` 기반으로 계획 층이 뜬다. backend가 만드는 값이 이것과 **같아야** 단계별 재검증이 성립한다. |
| 거부 검사 실측 | `scripts/sage_harness/hooks/tests/test_uninstall.py:1804` | 현재 Windows 계약을 지키는 검사는 `unsafe_platform` 하나뿐이다. |
| CI 실측 (rework 12 이후) | `.github/workflows/ci.yml` `uninstall_matrix` · `windows11_uninstall` | hosted matrix 는 **ubuntu·macOS 2 OS × 3 Python = 6 job** 이다. Windows 는 hosted 에서 빠지고 self-hosted 전용 job 하나로 옮겼다 — GitHub-hosted Windows 는 Server 2025 이고 범위 밖 러너의 초록은 데스크톱 증거가 아닌데 로그에서는 같은 초록으로 보이기 때문이다. |
| 소비자 smoke 실측 | `scripts/ci/uninstall_smoke.py` | 갈림의 기준은 OS 이름이 아니라 제품이 스스로 내리는 판정이다. 지원 범위에서는 실제 설치·제거, 범위 밖에서는 거부 계약을 검사한다. `SAGE_UNINSTALL_REQUIRE_PRODUCT_SUPPORT=1` 엄격 모드에서는 **거부로 갈음하는 것 자체가 실패**다. |
| 진단 어휘 실측 | `sage/diagnostic_contract.py:236-256` | uninstall BLOCK code 21개가 이미 있다. 이 사이클은 기존 어휘로 수렴하되 **하나를 더한다** — `uninstall.windows_10_manual_only`. 지원 범위 결정(아래)이 "고칠 수 없는 환경 한계" 와 "검증 범위 밖" 을 다른 화면으로 요구하기 때문이다. |
| 검증 환경 한계 | 개발 머신 = macOS (darwin 25.6.0) | Windows 실제 실행 증거는 **로컬에서 만들 수 없다.** 그리고 GitHub-hosted `windows-latest` 로도 만들 수 없다 — 그 실체는 Server 2025 다. A7·A19 증거를 만들 수 있는 자리는 **Windows 11 데스크톱 self-hosted 러너 하나뿐**이고, 그 러너가 없으면 두 항목은 `NOT TESTED` 로 남는다. |
| 작업공간 정책 | 사용자 지시 | worktree·임시 소비 프로젝트·fixture는 `/Users/sejon/project/sage_project_worktree/` 아래에만 만든다. |

## 1. 요약 (목표와 범위)

`sage uninstall`의 실제 mutation을 Windows 11 데스크톱(64-bit Python) 로컬 NTFS에서 지원한다. POSIX가 `dir_fd`로 얻던 부모 결속을 Windows에서는 `NtCreateFile`의 `RootDirectory` 핸들로 얻는다. 정책·journal·roster·표시 경로는 하나도 새로 만들지 않고, **OS별 파일 조작만** 새 경계 뒤로 내린다.

범위 안:

- 부모 결속을 backend 경계로 추출하고 POSIX 구현을 동작 무변경으로 옮긴다.
- Windows handle backend를 `ctypes`만으로 구현한다.
- capability probe가 실패하면 mutation 전에 `uninstall.unsafe_platform`으로 거부한다.
- 자동 제거가 불가능하거나 실패했을 때 수동 정리 안내를 text와 `--json`에 같은 근거로 낸다.
- Windows CI를 "계획·거부 확인"에서 "실제 제거 + 공격성 race 차단"으로 바꾸고, 그 실행 자리를 **Windows 11 데스크톱 self-hosted job** 으로 옮긴다.

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
- **문서(`docs/cli-reference*.md`·`docs/troubleshooting*.md`)**: "Windows는 계획만" 이라는 현재 서술이 거짓이 된다. 지원 범위를 Windows 11 데스크톱 64-bit Python 로컬 NTFS로 **좁혀서** 적고, Windows 10 데스크톱은 "자동 제거 없음 + 수동 정리 안내", server·domain controller는 "자동 제거 제외"로 나눠 적는다.

영향 없음을 확인해야 하는 곳: `install`·`generate`·`upgrade`는 같은 `DestinationLock`과 `InstallTransaction`을 쓴다. seam을 건드리면 이쪽이 먼저 깨진다.

## 3. 기술과 리스크

핵심 기술 판단은 설계 §4가 이미 내렸다 — 경로 기반 Win32 API + 직전 재검사(대안 A)는 TOCTOU 창을 남기므로 기각, 네이티브 helper(대안 C)는 패키징 비용이 커서 보류, `NtCreateFile` `RootDirectory` 핸들(권장안 B) 채택.

이 사이클이 새로 지는 리스크는 셋이다.

**T1. `ctypes` ABI.** 구조체 offset·access mask·UTF-16 길이가 틀리면 정상 경로는 통과하고 특정 입력에서만 실패한다. 개발 머신이 macOS라 **로컬에서는 한 줄도 실행되지 않는다.** 완화: 구조체 offset을 상수로 쓰지 않고 `ctypes`가 계산한 값을 쓰고, offset·크기 자체를 검사 대상으로 만들고, Windows runner의 primitive spike를 구현 진입 조건으로 둔다.

**T2. 지문 동치.** backend의 `measure`가 만드는 값이 계획 층 `os.lstat` baseline과 다르면 단계별 재검증이 항상 "바뀌었다"가 되거나, 더 나쁘게는 **다른 기준으로 통과**한다. Windows에서 `os.lstat`의 `st_dev`/`st_ino`가 어떤 Win32 호출로 만들어지는지는 CPython 버전을 탄다 — 이것을 추측으로 맞추면 T1과 같은 종류의 조용한 실패다. 완화: 추측을 검사로 바꾼다. root를 고정하는 순간 handle 기준 identity와 `os.lstat` identity를 **실제로 대조**하고, 어긋나면 mutation 전에 `unsafe_platform`으로 거부한다.

**T3. 범위 과장.** NTFS runner 하나의 성공이 "Windows 지원"으로 읽히면, 검증하지 않은 파일시스템의 첫 사용자가 검사자가 된다. 완화: CLI·문서·릴리스 노트 모두 Windows 11 데스크톱 64-bit Python 로컬 NTFS로 한정해 적고, 범위 밖은 계획을 보여 주되 mutation은 거부한다. 거부 이유는 **축마다 다른 진단**으로 낸다 — Windows 10은 `windows_10_manual_only`, server·domain controller는 `windows_sku_not_supported`, 결속 수단·볼륨·포인터 폭이 어긋나면 `unsafe_platform`이다. 하나로 접으면 사실이 아닌 원인 설명이 나간다.

이미 알고 있는 리스크(설계 §12 R2 sharing violation, R3 cloud reparse point, R4 수동 안내 오사용)는 설계가 정한 대로 안전 우선으로 처리하고, 새 판단을 만들지 않는다.

**검증 가능성이 이 사이클의 지배적 제약이다.** 검증할 수 없는 플랫폼 전용 코드는 막으려는 위험보다 나쁘다 — 그것이 지난 사이클이 EH-30을 넣지 않은 이유였다. 그래서 이번에도 "Windows 원격 증거 없이는 완료를 선언하지 않는다"가 리스크 대응이 아니라 완료 조건이다.

## 4. 최종 결론 및 UX 가이드

Windows 사용자는 `sage uninstall`을 다른 OS와 **같은 문장**으로 쓴다. 성공하면 같은 요약이 나오고, 실패하면 같은 진단 code가 나온다. Windows 전용 플래그도 전용 출력 형식도 만들지 않는다.

달라지는 것은 두 가지다.

첫째, 지원 범위 밖(네트워크 드라이브·FAT·capability 부족)에서는 지금처럼 `BLOCKED(2)`로 끝나되, **무엇을 손으로 정리해야 하는지 전부 보여 준다.** 지금은 "안전하게 실행할 수 없습니다"에서 끝나고 사용자는 다음에 무엇을 할지 모른 채 남는다.

둘째, 수동 정리 안내는 계획의 네 의미를 그대로 유지한다. `STRIP` 대상은 "파일 전체 삭제 금지, SAGE 부분만"으로 `DELETE`와 시각적으로 분리하고, `PRESERVE`·`BLOCK`은 삭제 가능 목록에 절대 오르지 않는다. 파괴적 shell 명령(`rm`·`rmdir`·PowerShell recursive delete·wildcard)은 어떤 경우에도 만들어 주지 않는다.

실행이 실패한 뒤의 목록은 **의도했던 계획이 아니라 다시 읽은 실제 상태**다. 다시 읽을 수 없으면 그 항목은 `unknown`이고, 삭제 가능으로 승격하지 않는다. 사용자에게 "지워도 된다"고 말하는 것은 되돌릴 수 없는 조언이라 확인 없이는 하지 않는다.

## 4-9. 현재 지원 계약 (정본)

이 표가 CLI 문장·문서·CI 주석이 말해야 하는 전부다. 갈라지면 A19 가 열린다.

| 환경 | 자동 제거 | 판정 축 | 거부 진단 | `--check` | 수동 정리 안내 |
|---|---|---|---|---|---|
| Windows 11 데스크톱 workstation · x64 · 64-bit Python · 로컬 NTFS | **한다** | — | — | 계획 | 실패·거부 시 |
| Windows 10 데스크톱 | 하지 않음 (후순위) | 정책 | `uninstall.windows_10_manual_only` | **BLOCKED(2)** | **제공** |
| Windows Server · 도메인 컨트롤러 | 하지 않음 (범위 제외) | 정책 | `uninstall.windows_sku_not_supported` | **BLOCKED(2)** | **제공** |
| 32-bit Python · **ARM64** · 비 NTFS · 네트워크 · native 기능 부재 | 하지 않음 (범위 제외) | capability | `uninstall.unsafe_platform` | 계획 | 실패·거부 시 |

**두 축은 화면이 다르다.** 정책은 SKU·build 만 보고 계획 단계에서 결론이 나므로 `--check` 도 `BLOCKED` 다 — 자동 제거가 결코 일어나지 않는 환경에서 계획만 보여 주면 돌 것처럼 보이는 화면이 된다. capability 는 볼륨·native 기능·포인터 폭을 실제로 재고, 그 조건은 볼륨을 바꾸거나 다른 root 를 고르면 참이 될 수 있다 — 그래서 계획은 그대로 보여 주고 **mutation 요청에만** 거부한다. 계획까지 막으면 고칠 수 있는 것을 고칠 수 없는 것처럼 보여 주게 된다.

**정책 진단은 capability 를 어느 쪽으로도 단정하지 않는다.** 그 자리에서 아는 것은 SKU 와 build 뿐이다 — "기능이 없다" 도 "기능은 있다" 도 재 본 적 없는 말이다. 낼 수 있는 사실은 하나다: 지원 정책의 범위 밖이고, capability 는 이 단계에서 판정하지 않았다.

**Server·32-bit·ARM64 는 명시적 미지원 범위다.** 그 환경을 위한 native 구현을 더하지 않는다 — 검증할 수 없는 플랫폼 전용 코드는 막으려는 위험보다 나쁘다는 것이 이 사이클의 전제다. 32-bit 와 ARM64 는 실제 수요가 생기면 후속 개발로 다룬다.

**ARM64 는 제품이 막는다 (rework 13).** rework 12 까지 ARM64 를 막는 것은 CI 게이트뿐이었다 — 폭도 SKU 도 build 도 조건을 만족하므로 제품은 실제로 제거를 수행했다. 그것은 **판정 권위를 제품과 CI 로 갈라놓는 상태**였고, 갈린 뒤에는 어느 쪽이 옳은지 물을 자리가 없다. 지금은 `native_floor()` 가 폭 다음에 아키텍처를 보고 x64 가 아니면 첫 mutation 전에 거부한다. CI 게이트는 자기 비교를 들지 않고 그 결과(`native_floor` · `capability.supported`)를 읽는다.

**정확히 무엇을 거부하는가 (rework 14 에서 좁힘).** `native ARM64 Python 프로세스`는 거부한다. 반면 **ARM64 Windows 에서 x64 에뮬레이션으로 실행되는 구성**은 아키텍처 보고 결과가 `platform.machine()` 의 Windows 판정 경로에 달려 있고 그 경로는 Python 버전과 실행 환경에 따라 달라질 수 있으므로, 어느 쪽이라고 단정하지 않는다. 그 구성이 x64 프로세스 ABI 관문을 통과할 수는 있지만 **통과가 ARM64 하드웨어 지원을 보장한다는 뜻은 아니다.** 정식 자동 제거 지원 범위에도 acceptance 증거 범위에도 넣지 않으며, 실제 수요가 생기면 별도 후속 개발에서 검증한다.

하드웨어를 따로 묻는 native 호출을 더하지 않는 이유는, 그 호출 자체가 이 사이클이 늘리지 않기로 한 검증 불가능한 플랫폼 전용 코드이기 때문이다.

## 5. Done Criteria

- [ ] Windows 11 **데스크톱 workstation · x64 · 64-bit Python** 로컬 NTFS에서 project·global·all 실제 제거가 통과한다 (현재 증거는 Windows Server 2025 build 26100 뿐이다 — 같은 커널 계열이지만 SKU 가 다르고, 제품이 말하는 범위는 데스크톱이다. 증거는 `windows11_uninstall` self-hosted job 의 세 로그이고 edition·build·product type·filesystem·**process bitness** 와 **실제 removal 수·policy refusal 수**, 그리고 **그 증거를 만든 커밋**을 함께 기록해야 닫힌다 — 검증 대상은 승인 당시의 `pull_request.head.sha` 하나이고, 증거 단계가 `git rev-parse HEAD` 와 그 값의 일치를 확인해 어긋나면 실패한다. `GITHUB_SHA` 는 `pull_request` 에서 merge 커밋일 수 있으므로 참고값으로만 남기고 일치를 요구하지 않는다)
- [x] 상위 경로 교체를 요구한 모든 지점에서 **실제 교체가 일어났거나, 두 독립 rename 경로가 OS 에 의해 사전 차단**되었고, 어느 쪽이든 프로젝트·global root 밖 변경이 0건이다 (차단은 실제 교체로 세지 않는다)
- [x] backend 경계 추출 이후 POSIX uninstall 결과와 rollback 계약에 회귀가 없다
- [x] capability·파일시스템·root identity 중 하나라도 확정되지 않으면 첫 mutation 전에 `uninstall.unsafe_platform`이다
- [x] Windows backend에 경로 기반 write fallback이 존재하지 않는다(소스 검사로 단언)
- [x] 자동 제거 불가·실패 시 수동 정리 목록이 text와 `--json`에서 같은 근거·같은 표시 경로로 나온다
- [x] `STRIP`·`PRESERVE`·`BLOCK` 항목이 삭제 가능 목록에 오르지 않는다
- [x] rollback 실패 상태에서 삭제 가능 주장이 나오지 않는다
- [x] Windows 핵심 안전 검사의 skip이 0건이다
- [ ] CLI·문서·CI 주석이 **직접 검증한 범위**와 일치한다 (문구는 Windows 11 데스크톱 workstation · x64 · 64-bit Python · 로컬 NTFS 로 좁혔고 hosted matrix 에서 Windows 를 뺐다. 그 SKU 의 실제 제거 증거가 서면 닫힌다 — Server 2025 증거는 backend 회귀이지 데스크톱 증거가 아니다)
- [x] 자동 제거 지원 판정이 **Windows 11 workstation 여부와 최소 build** 로 갈리고, 기존 로컬 NTFS·native primitive·root handle capability 검사가 그 위에 그대로 적용된다
- [x] Windows 10 데스크톱은 capability 실패와 **다른 진단**(`uninstall.windows_10_manual_only`)으로 구분되고, 제거 대상이 있으면 **확인 prompt 이전에** 막히며 mutation 0건이다
- [x] Windows 10 의 `--check` 와 `--yes` 가 `DELETE`·`STRIP`·`PRESERVE`·`BLOCK` 네 목록을 하나도 접지 않고 같은 진단·같은 경로로 내고, `manual_cleanup` 에 근거와 처리 순서를 싣는다 (text·`--json` 동일)
- [x] Windows 10 에 제거 대상이 있으면 `BLOCKED`(2) 다. `COMPLETE`(0) 은 **action 도 보존 잔재도 없는 완전히 깨끗한 상태**에서만 나오고, 안전 항목을 손으로 치운 뒤 보존 잔재만 남은 재실행은 `PARTIAL`(1) 로 경로·사유를 다시 내며 영수증과 손상 파일 bytes·mode 를 유지한다
- [x] 포인터 폭이나 **아키텍처**가 Win64 계약과 다르면 **첫 mutation 전에 fail-closed** 이고, 그 판정은 production 한 곳(`native_floor`)에 있으며 CI 는 그 결과를 소비한다. 진단과 CI 로그가 process bitness 와 아키텍처를 낸다
- [x] 정책 거부(Windows 10·server)가 **capability 를 어느 쪽으로도 단정하지 않는** 자기 진단을 쓰고, 검증된 계획 기반 수동 목록을 함께 낸다
- [x] `--check` 계약이 두 축으로 갈린다 — 정책 거부는 `--check` 도 `BLOCKED`, capability 제한은 `--check` 가 계획을 그대로 내고 mutation 요청에만 거부한다
- [x] 01 문서의 요구사항 ID 중복이 게이트에서 fail-closed 로 잡힌다
- [x] build 19045 와 22000 이상을 가르는 판정이 **어느 OS 에서나 도는 검사**로 고정돼 있고, 관문을 낮추거나 SKU 판정을 빼면 실패한다
- [x] **lock 뒤 `open_roots()` 가 검증한 동일 handle 을 mutation·rollback 종료까지 유지한다** (capability probe 의 handle 은 조사용이며 닫힌다)
- [x] 지원 범위 판정이 **확정 실패에서도 거부** 쪽이다 — 최종 경로·드라이브 종류를 확정하지 못하면 로컬로 세지 않는다
- [x] `recheck` 부터 `unlock` 까지 **write root 아래 절대 경로 filesystem 판정이 없다** — mutation·결과 검증·rollback·cleanup 을 전부 포함한다. 예외는 단 하나, cleanup 에서 journal 이 만든 backup 경로에 대한 읽기 전용 `os.path.lexists` 다
- [x] native 실패가 계약된 진단 code 로 CLI text·`--json` 까지 도달한다
- [x] 실행 실패 뒤의 목록은 다시 읽은 상태이며, 다시 읽지 못하면 실행 가능한 순서를 비운다
- [x] 전역 잔여 경로가 `$CODEX_HOME/...` 로 표시된다
- [x] Windows job 이 실제 mutation 0건이면 **실패한다** — self-hosted 전용 job 의 엄격 모드에서는 정책 거부로 갈음하는 것도 실패이고, 세 scope 중 하나라도 실제로 돌지 않으면 실패다
- [x] root 가 여럿일 때 identity 유도는 **모든 root 에 공통인 것**만 고른다. 공통이 없으면 거부한다
- [x] 설계가 요구한 주입 자리 목록과 실행 목록이 **한 권위**로 대조된다
- [x] 열기 이후의 어떤 실패에서도 native handle 을 놓치지 않는다
- [x] commit 후 뒷정리가 실패하면 무엇을 치울지 text·`--json` 이 같은 근거·같은 경로로 말한다
- [x] Windows 에서 핵심 계약 검사가 돌고 skip 이 0건이다 (실행 자리는 `windows11_uninstall` self-hosted job 이고, 그 job 은 **커밋 단위 승인 사건**에서만 열린다 — 라벨이 남아 있다는 이유로 새 커밋이 자동 실행되지 않는다)
- [x] Windows 에서 반드시 돌아야 하는 검사 목록이 **줄어들면 실패한다** — 요구 정본과 실행 목록을 다른 파일에 두고 이름으로 대조한다

## 6. Done Criteria Revision Log

Initial revision 1. No replanning record.

### Revision 14
- Changed-At: Phase 05
- Reason: 재검토가 rework 14 의 증거 문구에 P2 하나를 냈다. `ci.yml` 의 증거 단계 주석이 "`GITHUB_SHA` 와 `head.sha` 가 갈리면 어떤 트리를 검증했는지 알 수 없다" 고 적었는데, `pull_request` 이벤트에서 `GITHUB_SHA` 는 base 와 합친 **merge 커밋**을 가리킬 수 있고 이 job 은 승인한 `head.sha` 를 **일부러** checkout 한다 — 즉 두 값은 정상적으로 다르다. 정상 차이를 결함처럼 설명한 것이고, 로그를 읽는 사람이 그것을 결함으로 읽는다. 더구나 검사는 세 문자열이 출력되는지만 봤으므로, 찍기만 하고 넘어가는 단계도 통과했다 — 어긋난 트리에서 만든 로그가 증거라고 말하면서 초록으로 끝날 수 있었다.
- Affected-Phases: 01, 03, 04
- Summary: 증거 계약을 정정한다. `GITHUB_SHA` 는 merge 커밋일 수 있으므로 **참고값으로만** 출력하고 일치를 요구하지 않는다. 검증 대상은 승인 당시의 `pull_request.head.sha` 하나이고, 증거 단계가 `git rev-parse HEAD` 와 그 값을 대조해 어긋나면 **non-zero 로 실패**한다. 회귀 검사는 문자열 존재가 아니라 구조를 읽는다 — 트리를 실제로 읽었는가 · 승인된 head 와 대조했는가 · 어긋나면 실패하는가 · `GITHUB_SHA` 일치를 요구하지 않는가. 그 읽기 자체가 무언가를 지키는지는 mutation 4종(대조 제거 · 실패 제거 · 비교 뒤집기 · 트리를 읽지 않음)으로 확인한다. 제품 코드·ARM64 판정·Win10 수동 안내·Server/32-bit 지원 범위는 바꾸지 않는다.

### Revision 13
- Changed-At: Phase 05
- Reason: 재검토가 rework 13 에 P1 하나와 P2 하나를 냈다. (1) `windows11_uninstall` 조건이 라벨을 **지속 상태**로 봤다 — 검토한 커밋에 라벨을 붙여 한 번 돌린 뒤 새 커밋을 밀면 라벨이 남아 있으므로 `synchronize` 에서 **검토하지 않은 코드가 self-hosted 머신에서 자동 실행된다.** 한 번의 승인이 무기한 재사용되는 것이고, 더 나쁘게는 그 동작을 검사(`test_both_labelling_and_pushing_to_a_labelled_pull_request_run_it`)가 계약으로 고정하고 있었다. (2) ARM64 x64 에뮬레이션 설명이 "그 프로세스는 `AMD64` 로 보고한다" 고 단정했는데, `platform.machine()` 의 Windows 판정 경로는 Python 버전과 실행 환경에 따라 달라질 수 있다 — 재 보지 않은 것을 단정한 것으로, 이 사이클이 반복해서 막아 온 모양이다.
- Affected-Phases: 01, 03, 04
- Summary: 라벨을 **승인 사건**으로 바꾼다 — `github.event.action == 'labeled'` 와 `github.event.label.name == 'run-win11-uninstall'` 을 함께 요구하고, 저장소 대조는 유지한다. 라벨이 남아 있어도 `synchronize`·`opened`·`reopened` 는 실행하지 않으며, 현재 커밋을 검증하려면 라벨을 떼었다 다시 붙인다. self-hosted job 에 `permissions: contents: read` 를 두고, checkout 을 `ref: head.sha` 로 고정하며 `persist-credentials: false` 로 자격증명을 남기지 않는다. 증거 로그에 `GITHUB_SHA` 와 `head.sha` 를 찍어 **어느 커밋에서 만든 증거인지** 식별할 수 있게 한다. 필수 회귀 8건(라벨 사건만 실행 · 지속 라벨 재사용 차단 · opened/reopened 차단 · fork 차단 · 재부착 실행 · action 검사 제거 mutation · `contains(labels)` 회귀 mutation · 저장소 대조 제거 mutation)을 붙인다. ARM64 문구는 **native ARM64 프로세스 거부**와 **에뮬레이션 구성은 단정하지 않음(정식 지원·acceptance 증거 범위 제외)** 으로 좁히고 문서·소스 주석·백로그를 같은 뜻으로 동기화한다. 하드웨어 판정 native 코드는 더하지 않는다.

### Revision 12
- Changed-At: Phase 05
- Reason: 재검토가 rework 12 에 P1 하나와 P2 하나를 냈다. (1) 정식 지원 범위는 x64 인데 **production 은 ARM64 를 막지 않았다** — `support_policy` 는 SKU·build 만 보고 `native_floor` 는 폭만 보므로, ARM64 Windows 11 workstation · 64-bit Python · 로컬 NTFS 에서 실제 mutation 이 가능했다. 막는 것은 CI 게이트뿐이었고, 그것은 **제품과 CI 의 판정 권위를 갈라놓은 상태**다. 더구나 워크플로가 rename probe 와 capability report 를 게이트보다 먼저 돌렸는데, 그 report 는 내부에서 `real_run()` 으로 실제 install·uninstall 을 수행한다 — 잘못 배정된 ARM64 러너에서 **게이트 전에 native mutation 이 일어날 수 있었다.** (2) `windows_capability_report.py` 의 `REPO` 가 `dirname` 두 번이라 저장소가 아니라 `<repo>/scripts` 로 계산됐고, 그래서 게이트가 재는 fixture base(`<repo>/.sage-fixtures`)와 smoke 가 쓰는 자리(`<repo-parent>/.sage-fixtures`)가 어긋났다. 게이트가 저장소·temp 까지 함께 재는 것도 실제 mutation root 와 맞지 않았다.
- Affected-Phases: 01, 03, 04
- Summary: 아키텍처 판정을 **production `native_floor()` 한 곳**으로 옮긴다 — `WIN64_ARCHITECTURE = "AMD64"` 와 `process_architecture()` 를 두고, 폭 다음에 아키텍처를 보며 읽지 못한 경우도 거부 쪽이다. native 구현은 더하지 않는다. ARM64 에서는 `--check` 가 계획을 그대로 내고 `--yes` 만 `unsafe_platform`(2) 으로 거부하며 mutation·backup 이 0건임을 소비자 검사로 고정하고, 관문 제거 mutation 검사를 붙인다. CI 게이트는 자기 아키텍처 비교를 버리고 `native_floor` · `capability.supported` 를 소비한다. 워크플로에서 **게이트를 맨 앞으로** 옮기고, 그와 별개로 `real_run()` 이 지원 범위 밖에서 빠져나가게 한다(두 겹). `REPO` 계산을 고치고 게이트 root 를 `uninstall_smoke.fixture_base()` **한 권위**로 통일한다 — 저장소·temp 는 재지 않는다. 게이트 root 와 smoke fixture base 가 정확히 같은지, 그리고 지적된 옛 계산을 되살리면 갈리는지를 검사로 고정한다. §4-9 의 ARM64 행은 "제품이 판정하지 않는다" 에서 capability 축 거부로 바뀐다.

### Revision 11
- Changed-At: Phase 05
- Reason: 사용자가 Windows CI 를 재구성하기로 결정했다(2026-09-05). 직전 rework 까지 Windows 증거는 GitHub-hosted `windows-latest` 에서 나왔는데 그 실체는 **Server 2025** 이고, 그 러너의 초록은 backend 회귀 증거일 뿐 데스크톱 증거가 아니다. 그런데 로그에서는 두 초록이 구별되지 않아 실제로 한 번 그것을 데스크톱 증거로 읽을 뻔했다 — 착각의 자리를 남겨 둔 채 주석으로만 막고 있었던 셈이다. 또 `SAGE_UNINSTALL_REQUIRE_MUTATION` 은 정책이 막는 환경에서 **거부 계약 단언으로 갈음**하는 것을 허용하는데, A7 증거를 만들려는 job 에서는 그 갈음이 곧 "실제 제거를 한 번도 하지 않은 채 증거를 만들었다" 가 된다.
- Affected-Phases: 01, 03, 04
- Summary: hosted matrix(`platform`·`uninstall_matrix`)에서 `windows-latest` 를 빼고 Ubuntu·macOS 만 남긴다 — 기존 두 OS 의 검증 범위는 그대로다. Windows 검증은 `windows11_uninstall` self-hosted 전용 job 으로 옮긴다(`[self-hosted, windows, x64, win11, sage-uninstall]`, 같은 저장소 PR + `run-win11-uninstall` 라벨에서만 실행, fork PR 금지). 제거를 시작하기 전에 `windows_capability_report.py --require-product-support` 가 제품의 `support_policy()`·`capability()` 를 직접 소비해 fail-closed 로 막는다 — CI 전용 버전·build·filesystem 판정표를 새로 만들지 않는다. 그 job 의 제거 검사는 `SAGE_UNINSTALL_REQUIRE_PRODUCT_SUPPORT=1` 엄격 모드로 돌며, 정책 거부 1건·실제 제거 0건·미실행 scope 하나·core check skip·필수 selector 누락 중 하나라도 있으면 non-zero 다. 판정은 검사 스크립트가 자기 실행 결과로 내리고 workflow 는 stdout 을 grep 하지 않는다. 지원 범위 표기에 workstation·x64 를 결속하고 **ARM64 를 명시적 미지원**으로 기록한다 — 다만 ARM64 는 제품이 막지 않고 CI 게이트만 막는 "검증하지 않은 환경" 임을 §4-9 에 명시한다. Windows 10 수동 정리 계약은 **확장하지 않는다.** A7·A19 는 self-hosted 실제 실행 로그가 서기 전까지 `NOT TESTED` 다.

### Revision 10
- Changed-At: Phase 05
- Reason: 사용자가 지원 범위를 최종 확정했다 — Windows 11 데스크톱 · 64-bit Python · 로컬 NTFS 만 정식 지원, Windows 10 은 수동 안내로 수용, **Server·32-bit 는 명시적 미지원 범위이며 추가 native 구현을 하지 않는다.** 그리고 재검토가 rework 10 의 문구 결함을 지적했다: server 진단이 "필요한 native 기능은 이 환경에도 있습니다" 라고 **재 본 적 없는 것을 단정**했다. 정책 관문이 아는 것은 SKU 와 build 뿐이고 capability 는 그 뒤에 재는데, 앞선 층이 뒤의 결론을 미리 말한 것이다 — 이 사이클이 반복해서 막아 온 모양이 방향만 바뀌어 다시 났다(직전 rework 는 반대 방향으로 틀렸다). 또 정책 관문이 `unsafe_platform` 을 내던 분기가 남아 있어, capability 제한 환경의 `--check` 까지 `BLOCKED` 로 접힐 수 있었다.
- Affected-Phases: 01, 02, 03, 04
- Summary: 정책 관문에서 `unsafe_platform` 반환을 걷어낸다 — 정책은 두 정책 code 또는 `None` 만 낸다. 그 결과 `--check` 계약이 둘로 갈린다: 정책 거부는 `--check`·`--yes` 모두 `BLOCKED` + 수동 목록, capability 제한은 `--check` 가 계획을 그대로 내고 mutation 요청만 거부한다. 정책 진단 문구에서 capability 단정을 양방향 모두 제거하고 "범위 밖이며 capability 는 이 단계에서 판정하지 않았다" 로 좁힌다. 지원 범위 표기를 `Windows 11 데스크톱 · 64-bit Python · 로컬 NTFS` 로 통일하고, Server·32-bit 를 명시적 미지원으로 기록한다. Win64 설명에서 "커널이 인접 메모리를 침범한다" 는 증명하지 않은 단정을 "검증되지 않은 ABI 배치라 native 결과를 신뢰할 수 없다" 로 좁힌다 — 관문과 mutation 검사는 유지한다. Windows 10 수동 정리 기능은 **확장하지 않는다.** A7 이 유일한 blocker다.

### Revision 9
- Changed-At: Phase 05
- Reason: 재검토가 P2 4건을 냈다. (1) 구조체는 Win64 ABI 하나를 전제하는데 공개 문구는 "Windows 11 데스크톱" 전체를 말했다 — 32-bit Python 에서 `RootDirectory`·`ObjectName` 이 다른 자리로 가고 그 배치는 검증한 적이 없다. (2) server SKU 거부가 `unsafe_platform` 을 써서 "상위 교체를 막을 수단이 없다" 고 설명했는데, **Server 2025 CI 에서 capability 도 race 계약도 실제로 통과했다** — 사실이 아닌 원인 설명이 대상이 있는 모든 실행에서 나갔다. (3) Phase 00 의 요약·영향도·T3 에 이전 범위가 남았고, rework 8 이 기존 번호를 다시 써서 `FR-W20`·`FR-W21`·`FR-W22` 가 각각 두 번 존재했다 — acceptance parser 는 A-ID 만 보므로 잡히지 않았다. (4) 보존 잔재만 남은 재실행의 계약이 문서에 "지울 것이 없으면 COMPLETE" 로만 적혀 있었다.
- Affected-Phases: 01, 02, 03, 04
- Summary: 지원 범위에 **64-bit Python** 을 결속하고 포인터 폭을 `native_floor` 에서 fail-closed 로 막는다(`ULONG_PTR` 도 하드코딩 64 에서 포인터 폭으로 고친다). server·domain controller 는 `uninstall.windows_sku_not_supported` 로 분리하고 native 기능 부재를 주장하지 않으며, **검증된 계획 기반 수동 목록은 제공한다**(명시 결정, 검사로 고정). Phase 00 의 세 자리를 현재 계약으로 통일하고 정본 표를 §4-9 로 세운다. 새 요구사항을 `FR-W28`~`FR-W32` 로 재번호화하고, 게이트에 **요구사항 ID 중복 fail-closed 검사**를 추가한다. 보존 잔재만 남은 재실행은 `PARTIAL`(1) 임을 문서·unit·소비자 smoke 에 고정한다 — 코드 의미는 바꾸지 않는다(정책 관문 조건은 `plan.write_targets()` 그대로).

### Revision 8
- Changed-At: Phase 05
- Reason: 사용자가 지원 범위를 확정했다 — 정식 자동 제거는 **Windows 11 데스크톱 로컬 NTFS**, Windows 10 데스크톱은 후속 개발이되 **지금 손으로 무엇을 어떻게 치울지는 안내**한다. 그런데 `_windows_10_or_later()` 는 build 10240 부터 자동 제거를 허용했다 — 즉 제품이 말하려는 범위보다 넓게 실행하고 있었고, 그 넓이는 어떤 검사도 막지 않았다. 그리고 Windows 10 을 `unsafe_platform` 으로 접으면 "이 환경에 native 기능이 없다" 로 읽혀 사용자가 없는 원인을 찾아 나선다 — 실제로 없는 것은 기능이 아니라 그 SKU 의 증거다. 두 사실이 같은 code 를 쓰는 한, 고칠 수 있는 것과 고칠 수 없는 것이 한 화면에 남는다.
- Affected-Phases: 01, 02, 03, 04
- Summary: OS 버전 판정을 **정책(`support_policy`)과 기술 바닥(`native_floor`) 두 축**으로 나눈다. 정책은 Windows 11 workstation·build 22000 이상만 통과시키고 CLI 가 첫 mutation 전에 건다. capability 는 기술 판정만 유지해 Server runner 의 backend 회귀 증거가 살아 있게 한다. Windows 10 데스크톱은 `uninstall.windows_10_manual_only` 로 `--check`·`--yes` 모두에서 확인 prompt 이전에 멈추고, 네 목록과 처리 순서를 접지 않고 낸다. 대상이 없으면 `COMPLETE`(0) 이다. 지원 범위 문구를 Windows 11 데스크톱으로 좁히고, Windows 10 자동 제거는 후속 항목으로 분리한다. A7·A19 는 `NOT TESTED` 를 유지한다 — 좁힌 범위의 데스크톱 증거는 아직 없다.

### Revision 7
- Changed-At: Phase 05
- Reason: `run 33881276239` 의 Windows 증거는 유효하지만 **runner 의 실체가 Windows Server 2025 build 26100** 이다. 제품이 공개적으로 말하는 범위는 "Windows 10/11 로컬 NTFS" 이고 그것은 데스크톱 SKU 를 가리킨다. 커널 계약(handle 결속, rename 거부)이 같은 계열이라는 것과 그 SKU 에서 실제로 돌았다는 것은 다른 말이며, 후자를 증거 없이 참으로 두면 이 사이클이 반복해서 막아 온 모양 — "돌지 않은 것과 통과한 것이 같은 화면" — 이 문구 층에서 한 번 더 난다.
- Affected-Phases: 01, 03, 04
- Summary: 원격 로그로 증명된 네 기준(상위 교체 계약, 핵심 검사 skip 0, mutation 0 실패, matrix 계약 검사)을 닫았다. 실제 제거 기준은 **데스크톱 증거 전까지 열어 두고**, 무엇이 있어야 닫히는지(edition·build·filesystem 기록)를 그 자리에 적었다. 지원 범위 문구 기준은 "직접 검증한 범위와 일치한다" 로 다시 열었다 — Windows 10 증거가 없으면 범위를 Windows 11 로 좁히고 Windows 10 을 후속 항목으로 분리한다. A7·A19 는 `NOT TESTED` 로 되돌린다.

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
