# [기본 계획] 설치 소유권 경계 확정 — 소비측 `sage_harness/` 트리

Cycle-Stem: `sage-install-ownership-boundary`
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 4
Status: COMPLETE — 구현·검증 완료. 회귀 3629 · Windows smoke 9/9 · 실패 주입 6/6 · wheel 13/13

## 이 사이클의 성격

`1.0.0` 배포 뒤 들어온 피드백 넷을 한 사이클로 묶는다. 넷 다 **"SAGE 가 소유한 것과 프로젝트가
소유한 것의 경계가 흐리다"** 는 같은 뿌리에서 나왔다 — hook 런타임이 엔진 패키지를 import 해
소비 프로젝트에서 게이트가 크래시하고, 실행 자산이 프로젝트의 `scripts/`·`schema/` 와 섞이며,
그 결과 충돌 안내가 무엇이 누구 것인지 말하지 못한다.

새 기능을 만들지 않는다. **이미 있는 자산의 소유 경계를 한 트리로 확정하고, 그 경계를 말할 수
있게 한다.**

## 0. 사전 지식

| 구분 | 근거 | 핵심 내용 |
|---|---|---|
| 요구사항 정본 | Obsidian `SAGE - 설치 소유권 경계 확정 요구사항 (26.09.11)` | 영구 SSOT. repo phase 문서와 다르면 Obsidian 이 우선한다. |
| 사용자 결정 | 2026-09-11 설계 승인 | 소비측에 `sage_harness/` 를 신설한다. **엔진 저장소의 소스 트리는 유지한다** — 소스 경로와 설치 경로가 다른 것은 정상적인 배포 매핑이다. |
| 사용자 결정 | 2026-09-12 이행 재개 | 자동 이행을 범위에서 뺐던 판정을 되돌린다. 사용자가 원한 것은 **옮기는 것**이었고, 그것을 안 하면 1.0 사용자가 새 자산을 받지 못한다. |
| 사용자 결정 | 2026-09-12 설계 전환 | 파일을 옮기지 않는다. **신 경로에 다시 만들고, 거기를 바라본 뒤, 구 자산을 지운다.** 옮기는 설계가 요구하던 rename·staging·receipt 가 전부 사라진다. |
| 사용자 결정 | 2026-09-13 범위 축소 | `sage generate --unregister` 를 이번 릴리즈에서 제거한다. 사용자 확장 자산의 자동 이행은 후속 사이클이다. |
| 선행 계약 | `sage/uninstall_fs.py` | 부모 핸들 결속 mutation backend(POSIX `dir_fd` · Windows `NtSetInformationFile`). 이 사이클은 **쓰기만 하고 고치지 않는다.** |
| 선행 계약 | `sage/install_transaction.py` | `DestinationLock`·journal·`_guard_path`(root 소속 + 조상 symlink). manifest 를 쓰는 모든 경로가 이 경계 안이어야 한다. |
| 배포 사실 | `v1.0.0` 태그 (`433bb82`) | 이행의 대상은 이 태그가 설치한 레이아웃이다. 실증도 이 태그로 한다. |
| 실기 환경 | 위키 `TECH - Windows 11 원격 검증 환경 (실기 SSH 러너)` | Windows 11 Pro build 26200 · AMD64 · D: 로컬 NTFS · Python 3.12.10. 상설 러너. |
| 작업공간 정책 | 사용자 지시 | worktree·임시 소비 프로젝트·fixture 는 `sage_project_worktree/` 아래에만 만든다. |
| 검증 예산 | 사용자 지시 | 로컬 스위트는 **한 파이썬 버전**만 돈다. 매트릭스·무거운 E2E 는 CI 와 마지막 1회. |

## 1. 요약 (목표와 범위)

소비 프로젝트의 SAGE 실행 자산·schema·검증 스크립트를 `sage_harness/` 한 트리로 모으고, 기존
1.0 설치본을 자동 이행한다. hook 트리는 엔진 패키지 없이 단독 실행된다.

범위 안:

- 신규 설치는 `sage_harness/{hooks,schema,verify-changes.sh}` 에만 배치한다. 소비 프로젝트의
  `scripts/`·`schema/` 에 SAGE 가 만드는 파일이 0개다.
- 소비측 경로 규약을 `asset_paths` 한 곳이 소유한다. 다른 모듈이 경로를 직접 조립하지 않는다.
- `sage upgrade` 가 기존 설치본을 이행한다 — **재생성 → 검증 → 소유 증명된 구 자산 제거.**
- hook 런타임이 `import sage` 없이 로드·판정한다.
- 충돌·차단 안내가 무엇이 누구 소유인지 말한다.

범위 밖(의식적으로 남긴 것):

- 엔진 저장소 소스 트리 이동, 엔진측 경로 리터럴 통합
- 사용자 확장 자산(project hook·custom strategy)의 자동 이행
- 교차 부모 rename·staging 트리·receipt·`rmdir_empty` primitive
- 빈 부모 디렉터리 재귀 정리
- 소비 프로젝트의 `sage/` 디렉터리 이름 변경

## 2. 영향도 분석 (중요)

**게이트 코드가 바뀌는 변경이다.** 어느 트리의 `run_hook.py` 가 도는지가 곧 어느 정책이 강제되는지
이므로, 이행 중 판정이 흔들리면 사용자가 켜 둔 줄 아는 게이트가 실제로는 꺼져 있거나 다른 코드로
바뀐다. 그래서 활성 전환점을 **파일 하나(구 sentinel `runtime/run_hook.py`)의 제거**로 고정하고,
`hook_entry` 와 `detect_layout` 이 **같은 파일을 같은 방식으로** 보게 한다.

**되돌릴 수 없는 삭제를 포함한다.** 구 자산 제거는 rollback 대상이 아니다 — 전환 뒤에 스냅샷
복원이 돌면 구 파일이 되살아나 방금 없앤 공존을 다시 만든다. 따라서 삭제는 파이프라인의 **마지막**
이고 복원 경계 밖이며, 실패는 되돌리지 않고 재실행으로 수렴시킨다.

**1.0 사용자 전원이 대상이다.** 이행하지 않으면 새 자산을 받지 못하고, 이행이 데이터를 지우면
그 피해도 전원에게 간다. 그래서 "무엇을 지워도 되는가" 를 이름으로 증명하고, 증명되지 않은 것은
지우지도 옮기지도 않는다.

## 3. 기술과 리스크

| 리스크 | 대응 |
|---|---|
| 경로 기반 삭제가 프로젝트 밖에 닿는다 | 계획 단계에서 root 부터의 조상 전체 검사, 실행은 부모 핸들 결속 backend 경유. 결속을 못 얻으면 아무것도 지우지 않는다 |
| 사용자가 `sage_harness/` 를 이미 쓰고 있다 | 첫 mutation 전 점유 검사. **파일명 무관 전면 차단** — 이름이 안 겹친다고 허용하면 그 파일은 uninstall 날에 사라진다 |
| 구·신 공존 상태에서 어느 쪽이 정본인지 모른다 | 공존은 판정하지 않고 `CONFLICT` 로 fail-closed. 이행을 아는 `upgrade` 만 그 상태를 다룬다 |
| 이행 중단 후 반쪽 상태 | sentinel 제거 실패 시 **다른 구 자산을 하나도 지우지 않는다.** 전환 후 잔재는 되돌리지 않고 재실행이 수렴시킨다 |
| 사용자가 쓴 hook 코드 | 첫 mutation 전에 차단한다. 재생성할 수 없고 어느 자리로 가야 하는지도 도구가 정할 문제가 아니다 |
| Windows 가 POSIX 와 다르게 동작한다 | 실기 검증을 인수에 넣는다. `os.path.islink()` 는 junction 에 거짓을 내므로 판정이 `st_file_attributes` 를 함께 본다 |
| 엔진 소스·wheel 번들·소비자 경로가 서로 다르다 | checkout 검증만으로는 packaging 누락을 못 잡는다. candidate wheel E2E 를 인수에 넣는다 |

## 4. 최종 결론 및 UX 가이드

사용자가 보는 것은 `sage upgrade --apply` 한 번이다. 그 한 번이 —

- 무엇이 바뀌는지 `--check` 로 먼저 보여 준다.
- 패키지 자산을 새 위치에 다시 만들고, 동작을 확인한 뒤, 옛 위치에서 **SAGE 소유임을 증명할 수
  있는 것만** 지운다.
- 그 폴더에 직접 넣은 파일은 그대로 두고 **무엇을 남겼는지 알려 준다.**
- 빈 `scripts/`·`schema/` 는 지우지 않는다. 안전하게 확인된 것만 참고로 표시한다.
- 직접 작성한 project hook 이나 review strategy 가 있으면 **첫 변경 전에 멈추고**, 그 설치본은
  옛 위치에서 계속 동작한다.
- 도중에 멈춰도 다시 실행하면 남은 정리를 이어간다.

**직접 `mv` 로 옮기는 절차는 안내하지 않는다.** 옮겨야 하는 것이 hook 폴더만이 아니라서, 일부만
옮기면 이 설계가 금지한 공존·정본 불명 상태가 된다.

## 5. Done Criteria

- [x] 신규 설치가 `sage_harness/` 아래에만 배치하고, 소비 프로젝트의 `scripts/`·`schema/` 에 SAGE 가 만드는 파일이 0개다
- [x] `verify-changes.sh` 가 `sage_harness/verify-changes.sh` 에 놓이고 profile 의 verification 명령이 그 경로를 가리킨다
- [x] 엔진 저장소의 소스 트리(`scripts/sage_harness/`·`schema/`)는 이동하지 않는다
- [x] 소비측 경로 규약을 `asset_paths` 단일 지점이 소유한다 — 다른 모듈이 `sage_harness` 문자열을 직접 조립하지 않는다
- [x] `sage upgrade --apply` 가 기존 1.0 설치본을 이행한다. 구 파일을 복사·rename 하지 않고 현재 패키지 자산을 신 경로에 **재생성**하며, `validate` 와 **엔진 비의존 runtime load** 를 통과한 뒤에만 구 자산을 정리한다
- [x] 구 경로에서는 **SAGE 소유가 증명된 파일만** 제거한다 — hook 트리는 `install` 이 배치하는 닫힌 목록, 공유 낱개 파일은 번들 바이트 일치 또는 배포본 SHA allowlist. 증명되지 않으면 보존·보고한다
- [x] 빈 `scripts/`·`schema/` 를 자동 삭제하지 않는다. 안전하게 확인된 것만 참고 정보로 보고하며, **보고하지 못한 것이 이행 실패를 만들지 않는다**
- [x] 활성 전환점은 구 sentinel 제거 하나다. 그 전까지 hook 은 구 경로로 돌고, 전환에 실패하면 다른 구 자산을 하나도 지우지 않으며, 전환 후 잔재는 재실행이 수렴시킨다
- [x] 등록된 project hook 또는 custom review strategy 가 있으면 **첫 mutation 전에 차단**하고, 그 설치본은 구 레이아웃에서 계속 정상 동작한다. 자동 복사·이동·재등록도, 수동 `mv` 안내도 하지 않는다
- [x] 어떤 명령도 구·신 공존을 새로 만들지 않는다 — `install` 은 구 레이아웃을 제자리에서 갱신한다
- [x] 이행의 삭제가 부모 핸들 결속 backend 를 지난다. 결속을 얻을 수 없으면 아무것도 지우지 않고, 계획이 프로젝트 밖에 닿으면 첫 mutation 전에 차단한다 (`uninstall_*_fs` 3파일 미수정)
- [x] `sage_harness/` 에 우리 것이 아닌 내용이 있으면 **파일명과 무관하게** 차단한다. 그 검사는 **lock 획득 뒤**에 선다
- [x] hook 트리 전 모듈이 엔진 없이 import 되고, 엔진 없는 소비 프로젝트에서 게이트가 **exit 2(BLOCK)** 를 낸다 — 크래시로 인한 exit 1 통과가 아니다
- [x] 레이아웃 판정과 hook 진입점이 **같은 파일을 같은 방식으로** 본다. 둘 다 root 부터의 조상 전체를 검사해 프로젝트 밖 트리를 게이트로 세우지 않는다
- [x] 이행 실패 뒤에도 재실행이 가능하다 — 우리가 만든 부산물이 다음 실행을 영구 차단하지 않는다
- [x] hook 회귀 전체가 통과한다 (105 스위트 · 3629 테스트 · 실패 0)
- [x] `validate --check --schema` drift 0, 한·영 문서 쌍과 catalog 개행 동수
- [x] **Windows 11 데스크톱 실환경**에서 이행이 수행된다 — smoke 9/9 · 실패 주입 6/6. `backend-is-windows` 가 먼저 통과해 나머지가 실제 Windows backend 위의 결과임이 증명된다
- [x] **candidate wheel 단독 배포**에서 구→신 이행이 돌고, 이행한 트리에서 게이트가 실제로 exit 2 를 내며 traceback 이 0건이다 (엔진 체크아웃·`PYTHONPATH` 없음)
- [x] 위 Windows·wheel 증거가 **커밋 SHA 에 결속된다** — checkout 의 `git rev-parse HEAD` 일치와 `git status --porcelain --untracked-files=all` 공백을 실행 전후로 확인한다
- [x] 릴리즈 본문이 태그 **전에** 확정된다 (Phase 05 §6, 2026-09-13 승인)

## 6. Done Criteria Revision Log

Initial revision 1 (2026-09-11).

### Revision 2
- Changed-At: Phase 02
- Reason: 이행 설계가 "구 위치의 파일을 신 위치로 옮긴다" 로 세워졌고, 그 전제에서 교차 부모 rename·staging·receipt 가 줄줄이 따라왔다. 교차 검토가 낸 블로커 넷이 전부 **옮기는 과정의 안전성**에 관한 것이었고, 그 넷을 닫는 비용이 사이클 예산을 넘었다.
- Affected-Phases: 01, 02
- Summary: 자동 이행을 범위에서 뺀다. 신규 설치만 `sage_harness/` 로 가고, 기존 설치본은 구 레이아웃에서 계속 동작하며 이행은 후속 사이클로 넘긴다.

### Revision 3
- Changed-At: Phase 02
- Reason: 사용자가 **원래 요구가 이행이었다**고 지적했다. 이행을 빼면 1.0 사용자가 이 사이클의 수정을 받지 못하고, 그러면 사이클의 목적 자체가 성립하지 않는다. 이어서 사용자가 전제를 바꿨다 — 옮길 필요 없이 **신 경로에 자산을 만들고 거기를 바라본 뒤 구 자산을 지우면 된다.**
- Affected-Phases: 01, 02, 03, 04
- Summary: 이행을 다시 넣되 옮기지 않는다. `install_core` 가 신 경로를 만들고, 재생성·검증 뒤 구 sentinel 을 지우는 것이 활성 전환이며, 소유가 증명된 구 자산만 제거한다. rename·staging·receipt·backend 변경이 전부 사라진다. A5~A7 을 이 계약으로 재작성하고, 사용자 확장 차단(A7b)을 신설한다. 빈 부모는 자동 삭제 대신 보고로 내린다.

### Revision 4
- Changed-At: Phase 05
- Reason: 차단된 사용자에게 출구를 주려고 넣은 `sage generate --unregister` 가 **경로 조작이 프로젝트 밖에 닿는 결함을 세 번** 냈다(adapter leaf · 그 조상 · manifest). 세 번째에 원인이 드러났다 — manifest 를 쓰는 경로 중 `InstallTransaction` 을 지나지 않는 것이 이 명령 하나뿐이었다. 완결은 가능했지만, 일반 1.0 설치본의 자동 이행에 필요하지 않은 **새 생명주기 기능**을 이 릴리즈가 사야 하는지가 판단의 핵심이었다. 같은 판정이 이행 밖에서 결함 셋을 더 냈다.
- Affected-Phases: 01, 02, 03, 04, 05
- Summary: `--unregister` 를 제거한다(CLI·구현·catalog·테스트·문서). 사용자 확장 계약은 "차단하고 구 레이아웃에서 계속 동작한다" 하나로 줄고, 자동 이행은 후속 사이클이 소유한다. 필수 결함 셋을 재현하고 고친다 — `hook_entry` 가 조상을 보지 않아 판정이 거부한 트리를 골랐고, 엔진 비의존 검사가 공유 temp 의 고정 이름을 써 프로젝트 밖 파일을 덮었으며, install 점유 검사가 lock 밖에만 있어 그 사이에 만들어진 사용자 파일이 기계 소유 트리에 남았다. 빈 부모 보고를 `apply()` 밖으로 빼 그 실패가 이행 실패로 읽히지 않게 한다. Windows·wheel 증거의 **커밋 SHA 결속**과 릴리즈 본문 사전 확정을 Done Criteria 에 넣는다.
