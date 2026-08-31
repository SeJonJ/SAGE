# [기본 계획] 프로젝트·전역 SAGE 자산 제거

Cycle-Stem: `sage-uninstall`
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 10
Status: READY
Phase03-Entry: READY (Phase 02 §10.7 — UD-1~UD-6 확정·R1~R7 대조 완료, 2026-08-27)

## 이 문서의 잠정성 — 선행 미완 착수와 rebase 재확인 계약

이 사이클은 `sage-operability-diagnostics`가 main에 병합되기 전에 착수했다. 선행은 착수 시점에 Phase 04까지만 진행됐고 독립 리뷰와 보고를 받지 않았다. 따라서 00~02는 **잠정 문서**다.

`uninstall`은 앞선 `sage-audit-visibility-no-vault`보다 선행 의존이 크다. 저 사이클은 읽기 전용이라 본체가 진단 계약과 무관했지만, 이 사이클은 **`BLOCKED(2)`라는 BLOCK 표면 자체가 기능 본체**다. 선행의 복구 완전성 오라클이 확정되기 전에 BLOCK 문구를 쓰면 병합 시점에 전부 오라클 위반으로 걸린다.

- 00~02의 일부 내용은 rebase 시점에 **변경될 수 있다**. 특히 BLOCK·진단 표면과 `install.py` 추출 경계가 그렇다.
- 이 사이클은 문서 00~02까지만 선행 착수한다. Phase 03과 코드는 rebase 이후에 연다.

**rebase 완료 (2026-08-27, `31b1a52`).** 선행 둘(`sage-operability-diagnostics`·`sage-audit-visibility-no-vault`)이 모두 main에 병합된 뒤 이 브랜치를 맞췄고, 아래 재확인 목록을 실제로 대조했다. 결과는 각 행에 적었다.

### rebase 이후 재확인 목록

Phase 03을 열기 전에 00~02를 다시 읽고 아래를 대조한다. 대조 없이 "읽었다"로 넘어가지 않는다. 불일치는 해당 문서를 고친 뒤 진행하며 Done Criteria Revision Log에 남긴다.

| # | 대조 대상 | 실측 결과 (2026-08-27) | 조치 |
|:-:|---|---|---|
| R1 | 복구 완전성 oracle의 판정 범위 | 예상대로. `recovery_issues()`가 BLOCK code 의 recovery 누락·금지 명령·mutation 국면 섞임을 검사한다 | 없음 |
| R2 | "복구에 파괴적 명령 금지" 규칙과 uninstall 의 상호작용 | **규칙 둘이 함께 걸린다.** `FORBIDDEN_COMMAND` 가 `rm`·`rmdir`·`shred`·`truncate`·`git reset --hard`·`git clean`·`sage override` 를 막고, 동시에 모든 BLOCK 은 실행 가능한 명령을 최소 하나 가져야 한다. `sage uninstall` 자체는 금지 목록에 없다 | 02 §7.2 를 세 단계 복구로 확정 (UD-4). 규칙 예외는 만들지 않는다 |
| R3 | `sage/commands/install.py` 최종 형태 | **1,665줄 — 변동 없음.** 예상했던 +5줄은 실현되지 않았다 | 01 §6 추출 경계 무변경 확인 |
| R4 | `hook_runtime_files()` 목록 | **shared 20 + claude 1 + codex 1 = 22개.** `path_risk.py`·`recovery.py` 둘 다 실재 | 01 §6 삭제 인벤토리에 반영 |
| R5 | manifest schema property 수 | **14개**, required 3개, `runtime_api` 존재 — 예상대로 | §0 실측 표를 13 → 14 로 정정 |
| R6 | CLI 서브커맨드 수 | **25개** (문서 21). 선행 둘이 `status`·`explain`·`audit`·`upgrade` 등을 더했다 | 00 §3·01 §5 문구를 25 로 정정 |
| R7 | `overlay_classify.CORE_IDS`·`install._CORE_*` 무변경 | **무변경 확인.** `CORE_IDS` 3개, `_CORE_AGENTS`·`_CORE_SKILLS`·`_CORE_BOOTSTRAP_SKILLS`·`_CORE_HOOKS` 그대로 | 삭제 인벤토리 전제 유지, 편차 D2 유효 |

R2와 R7이 이 목록의 핵심이었다. R2는 BLOCK 문구가 통과 가능한지를 정했고 — 답은 "수동 안내만으로는 불가, 읽기 전용 명령을 Next 로 두면 가능" 이다 — R7 이 유지되어 삭제 인벤토리의 전제가 그대로 섰다.

## 0. 사전 지식

| 구분 | 근거 | 핵심 내용 |
|---|---|---|
| 승인 설계 | 위키 노트 `SAGE - uninstall 프로젝트·전역 자산 제거 설계 (26.08.22)` | `pipx uninstall`이 남기는 소비 프로젝트 자산을 `sage uninstall`로 닫는다. SAGE 전용 namespace는 transaction 제거, 공유 파일은 SAGE 부분만, 소유권 불명은 보존·경고. 이 노트가 영구 SSOT이며 저장소 사본을 두지 않는다. |
| 사용자 결정 | 2026-08-24 착수 대화 | 설계 정본은 위키 노트가 소유한다. `plan_docs`는 이번 사이클의 실행 증거만 소유한다. |
| 사용자 결정 | 2026-08-24 착수 대화 | 이 사이클은 SAGE CLI로 사이클을 열지 않고 phase 문서를 수동 작성한다. |
| 사용자 결정 | 2026-08-24 착수 대화 | 선행 병합 전에는 문서 00~02까지만 작성한다. Phase 03과 코드는 rebase 이후에 시작한다. |
| 선행 작업 (미충족) | `sage-operability-diagnostics` (`feat/...`, `0a34b58`) | 미병합. 진단 code·`RecoveryStep`·`Next:` 계약과 복구 완전성 oracle을 소유한다. 이 사이클의 BLOCK 표면 전체가 이것을 소비한다. |
| 구현 기준점 | `main@63cc3bd` | 브랜치 `feat/sage-uninstall`이 이 커밋에서 갈라진다. 모든 실측은 이 커밋 기준이다. |
| install 규모 실측 | 2026-08-24 저장소 조사 | `install.py` 1,665줄 · `generate.py` 1,265줄 · `asset_paths.py` 146줄 · `install_transaction.py` 497줄 · `overlay_classify.py` 236줄. |
| transaction 재사용 지점 | `sage/install_transaction.py` | `DestinationLock`(:141)·`InstallTransaction`(:235)·`rollback`(:447)·`commit`(:485)이 이미 있다. 설계 §10의 "재사용하거나 최소 일반화"는 신규 작성이 아니다. |
| CORE roster 실측 | `sage/overlay_classify.py:37` | `CORE_IDS`가 agents 6종·skills 13종·framework 4종을 소유한다. 주석이 "`install._CORE_AGENTS`/`_CORE_SKILLS`/`_CORE_BOOTSTRAP_SKILLS`와 일치해야 한다(`test_overlay_classify`가 대조)"고 명시한다. 즉 roster는 **두 벌**이다. |
| install roster 실측 | `sage/commands/install.py:35-43` | `_CORE_AGENTS` 6 · `_CORE_SKILLS` 11 · `_CORE_BOOTSTRAP_SKILLS` 2 · `_LEGACY_CORE_SKILLS` 2(`pdca-start`·`sage-pdca-start`). 마지막 것은 은퇴한 이름의 잔존 사본 정리용이다. |
| SAGE marker 실측 | `sage/commands/install.py:46` | `_LEGACY_SKILL_SIGNATURE = "CORE framework bootstrap asset"`가 SAGE가 hand-ship한 모든 CORE skill `SKILL.md`에 들어 있다. 주석이 "공유 공간에서 동명의 사용자 skill을 오삭제하지 않도록"이라고 용도를 밝힌다. 설계 §8이 요구한 "공식 SAGE marker"의 실제 정본이 이것이다. |
| codex 전역 경로 실측 | `install.py:295,304` · `generate.py:1210` | 전역 skill 경로가 **두 가족**이다. `install._codex_global_skill_path(skill_id)`는 `$CODEX_HOME/skills/<skill_id>/`(bare CORE id), `generate`는 `gid = f"{prefix}-{aid}"`로 `$CODEX_HOME/skills/<prefix>-<aid>/`에 배포한다. prefix는 profile의 `project.prefix`이며 없으면 fail-closed다. |
| gitignore managed block 실측 | `install.py:47-51` | `# >>> SAGE LOCAL PROFILE` / `# <<< SAGE LOCAL PROFILE`, `# >>> SAGE LOCAL STATE` / `# <<< SAGE LOCAL STATE` 네 마커가 정본이다. |
| manifest 실측 | `schema/manifest.schema.json` | top-level property **14개** — 위 13개(`sage_version`·`generator_version`·`template_version`·`host_runtime`·`installed_hosts`·`sage_source_commit`·`source_core_content_hash`·`installed_core_content_hash`·`dirty_flag`·`hook_runtime_hash`·`core_renders`·`core_skill_receipts`·`assets`)에 선행이 더한 `runtime_api`가 붙었다. `required`는 3개다. (R5 대조 완료 2026-08-27) |
| framework 표면 위치 실측 | `templates/core/framework/` | 설계 §7이 나열한 `AGENTS.md`·`CLAUDE.md`·`CODEX.md`·`AGENT_GUIDE.md`·`verification-protocol.md`·`docs/agent/`(9개 파일)·`scripts/`는 **엔진 저장소 루트에 없고** 이 템플릿 트리에만 있다. 소비 프로젝트는 이 트리의 내용을 루트에 받는다. |
| 검증 환경 경계 | `sage/_resources.py:50` `is_engine_source_tree` | `templates/core/framework/`와 `sage/cli.py`의 결합으로 엔진 저장소를 판별한다. 설계 §11의 "엔진 저장소에서 project/all uninstall 차단"은 이 함수를 재사용한다. 자기 게이트가 돌지 않으므로 실제 판정은 격리 소비 프로젝트에서만 난다. |
| 작업공간 정책 | 승인 설계 §13 · 사용자 지시 | local worktree·임시 소비 프로젝트·install→uninstall fixture는 `/Users/sejon/project/sage_project_worktree/` 아래 고유 자식 폴더만 쓴다. `/tmp`·`/var/folders`·임의 sibling으로 폴백하지 않는다. |

## 1. 목표

`pipx uninstall sage`가 CLI 패키지만 지우고 소비 프로젝트에 남기는 hook·skill·profile·runtime 자산을 공식 명령으로 닫는다. 목표는 다음 네 가지다.

1. project·global·all 범위를 명시적으로 분리한 `sage uninstall`을 제공한다.
2. SAGE 전용 namespace는 transaction으로 제거하되, 공유 파일에서는 검증된 SAGE 부분만 제거한다.
3. 소유권이 불확실한 파일을 삭제하지 않고 경로와 사유를 모두 보고한다.
4. 기술적 실패 시 project와 global을 하나의 단위로 rollback한다.

종료 상태는 정확히 다음 중 하나다.

- `NOT READY`: 필수 인수 항목이 하나 이상 해결되지 않았다.
- `READY_FOR_USER_MERGE_DECISION`: 구현과 검증은 통과했지만 커밋·머지·push·릴리즈는 수행하지 않았다.

## 2. 범위

### 2.1 포함

- `sage uninstall [--dest PATH]` · `--global` · `--all`과 보조 옵션 `--check`·`--yes`·`--verbose`.
- `COMPLETE(0)`·`PARTIAL(1)`·`BLOCKED(2)`·`CANCELLED(0)` 상태·종료 계약.
- manifest와 canonical inventory를 결합한 삭제 대상 판별과 immutable `UninstallPlan`.
- `DELETE`·`STRIP`·`PRESERVE`·`BLOCK` 네 action의 배타적 분류.
- SAGE 전용 tree 4종(`sage/`·`.sage/`·`docs/sage_harness/`·`scripts/sage_harness/`) 전체 삭제.
- host 자산의 정확한 CORE ID 기반 삭제와 빈 parent만 정리.
- 개별 검증 framework 파일의 receipt·canonical content 대조 삭제.
- `.gitignore` managed block과 host JSON hook 등록의 SAGE 부분만 제거.
- 소유권 불명 최상위 파일 4종의 보존·보고.
- 전역 범위의 CORE skill 제거와 SAGE marker 확인.
- 계획·결과 출력 계약과 대화형 확인.
- 경로 정렬 lock 획득, private backup, output 검증, 통합 rollback.
- 필수 안전 경계(엔진 저장소 차단, 광범위 경로 차단, symlink ancestor 금지, planner 밖 mutation 금지).
- 한영 help·plan·확인·경고·보고와 문서 갱신.
- clean-consumer matrix와 실패 주입 검증.

### 2.2 제외

- 실행 중인 SAGE Python 패키지의 자기 제거와 `pipx`·`pip` 호출.
- `plan_docs`·component plan 문서·Obsidian vault·write-back·프로젝트 소스·테스트·Git 이력 삭제.
- 머신의 모든 SAGE 프로젝트 자동 탐색·철거.
- 파일별 신규 uninstall receipt schema.
- `--force`와 소유권 우회 옵션.
- 과거 `generate`가 덮어쓴 사용자 설정의 복원.
- `install.py`의 uninstall과 무관한 리팩터링.
- 커밋·머지·push·태그·릴리즈.

## 3. 영향 분석

| 영역 | 변경 | 고정 경계 |
|---|---|---|
| `sage/managed_assets.py` (신규) | 두 CORE roster를 하나의 정본으로 통합 | `overlay_classify.CORE_IDS`와 `install._CORE_*`의 **내용**은 바뀌지 않는다. `test_overlay_classify`의 대조가 통합 후에도 살아 있어야 한다. |
| `sage/commands/install.py` | 경로·ID 정본을 `managed_assets`로 이관 | install의 동작과 배치 결과는 불변이다. 이관은 이동이지 재작성이 아니다. |
| `sage/install_transaction.py` | 삭제 target을 다루도록 최소 일반화 | 기존 install 경로의 commit·rollback 의미는 불변이다. |
| 신규 `uninstall` | 계획·확인·실행·보고 | planner에 없는 target을 executor가 추가할 수 없다. |
| `sage/cli.py` | `uninstall` 등록 | 기존 **25개** 서브커맨드의 인자·exit는 불변이다. (R6 대조 완료 2026-08-27) |
| CLI catalog | uninstall 문구와 복구 문구 | 기존 판정 어휘와 도메인 경계는 유지한다. |
| 사용자 문서 | 한영 갱신 | 한영 미러 상태를 유지한다. |

## 4. 전역 불변 조건

### G1. planner에 없는 것은 지우지 않는다

executor는 plan에 없던 target을 추가할 수 없다. 계획 출력 뒤 fingerprint가 바뀌면 삭제하지 않고 차단한다. 이 방향이 뒤집히면 "계획을 보여주고 다른 것을 지우는" 명령이 된다.

### G2. 소유권을 추측하지 않는다

manifest가 증명하지 못하는 파일은 지우지 않는다. 현재 bundle과 내용이 같다는 사실도 생성 소유권을 증명하지 않는다. 애매하면 `PRESERVE`이고 결과는 `PARTIAL`이다. 이것은 실패가 아니라 의도된 안전 판정이다.

### G3. 공유 파일은 SAGE 부분만 건드린다

`.gitignore`·`.claude/settings.json`·`.codex/hooks.json`에서 정상적인 SAGE managed block과 canonical hook 등록만 제거한다. marker 중복·역순·한쪽 누락·손상이나 JSON 손상은 추측해서 고치지 않고 파일 전체를 `PRESERVE`한다.

host 등록 판정은 **present · absent · unknown 세 값**이다. 파싱 실패·비 UTF-8·읽기 실패는 `absent`가 아니라 `unknown`이다. 판정 권위는 하나의 순수 classifier이고 계획·흔적·실행이 모두 그것을 부른다. `unknown`이어도 manifest `installed_hosts`가 그 host 설치를 증명하고 파일이 존재하면 `PRESERVE` action에 반드시 포함한다.

### G3-a. 영수증은 잔재보다 오래 산다

`present` 또는 `unknown` 잔재가 하나라도 남으면 manifest tree(`docs/sage_harness`)를 삭제하지 않고 `uninstall.receipt_retained_for_residual`로 `PRESERVE`한다. 증거를 먼저 버리면 다음 실행은 그 파일이 왜 거기 있는지 증명할 방법을 잃는다. 잔재가 남아 있는 동안 매 실행은 **mutation 없는 `PARTIAL(1)`**이고 같은 경로·사유·손상 좌표·등록 상태를 다시 출력한다. 사용자가 손상을 복구해 SAGE 등록을 뺄 수 있게 된 실행에서만 manifest tree를 마지막 논리 자산으로 제거한다. 잔재가 남은 상태에서 CLI 패키지를 먼저 제거하면 host가 없는 실행 파일을 부르므로 그 순서를 고지한다.

### G3-b. 손상은 좌표로 보고하고 내용은 싣지 않는다

"구조가 손상됐다"는 일반 문장으로 축약하지 않는다. 확인 가능한 경우 안전한 JSON pointer 위치·기대 타입·실제 타입, 문법 오류의 행·열, UTF-8 오류의 바이트 위치, errno 이름을 함께 낸다. 동시에 사용자 설정값·command 원문·주변 JSON 내용·원문 OS 예외는 출력하지 않는다. text와 `--json`은 **같은 structured damage 값**을 소비하고, ko·en JSON은 byte 동일하다.

### G4. 개발 결과물은 write target으로 열지 않는다

`plan_docs`·Obsidian vault·프로젝트 소스·테스트·Git metadata를 transaction의 write target에 열거하지 않는다. 테스트가 불변성 증명을 위해 hash할 수는 있다.

### G5. 등록을 실행 파일보다 먼저 지운다

hook 등록을 shim보다 먼저 제거해 성공 상태에 dangling active hook이 남지 않게 한다. 이 순서 자체가 계약이다.

### G6. 실패하면 함께 되돌린다

project와 global은 하나의 transaction이다. 어느 root에서든 기술적 오류가 나면 둘 다 rollback한다. 예상된 `PRESERVE`는 rollback 사유가 아니다. rollback도 실패하면 보존한 복구 경로를 출력한다.

### G7. 자기 자신과 패키지 매니저를 건드리지 않는다

실행 중인 SAGE 패키지를 제거하지 않고 `pipx`·`pip`를 호출하지 않는다. `--all` 뒤에도 CLI 패키지 제거는 사용자가 별도로 한다.

### G8. 광범위 경로를 거부한다

`/`·filesystem root·사용자 홈, 그리고 **root 직계 자식**(`/usr`·`/opt`·`/Users`, Windows 드라이브 루트의 직계 자식)인 `--dest`를 차단한다. 판정은 깊이로 한다 — "이 모양이면 위험하다"를 손으로 적으면 적은 것과 지켜지는 것이 갈라지고, 실제로 그렇게 갈라진 적이 있다. 차단은 **계획 단계**에서 일어나고, 그 계획은 쓰기 대상을 하나도 갖지 않는다. 상태만 `BLOCKED`이고 목록은 차 있는 계획은 다음 실수 하나로 실행된다.

선언된 write root 밖 경로를 삭제하지 않는다. symlink ancestor를 따라가지 않고, 검증된 SAGE-owned leaf symlink는 target을 따르지 않고 link 자체만 처리한다. 전역 skill root에도 같은 경계를 건다 — `$CODEX_HOME`이 `/`면 전역 root는 `/skills`이고, project에만 문을 걸면 같은 실수가 다른 문으로 그대로 들어온다.

### G8-a. manifest는 증거로 쓸 수 있는 모양일 때만 증거다

설치 기록은 **무엇을 배치했는가**에 대한 유일한 증거다. 그 파일이 증거 구실을 할 수 없으면 우리가 아는 것은 아무것도 없고, 아무것도 모를 때 할 일은 멈추는 것이다.

최상위가 object인지까지만 보면 안 된다. 빈 manifest는 "설치는 증명됐고 배치 기록은 하나도 없다"로 읽히는데, 기록이 없으니 host 렌더도 skill도 후보에 오르지 않고 그런데 SAGE 전용 tree는 이름만으로 지워진다. 그 결과가 **증거를 먼저 지우고 나서 할 일이 없다고 말하는 것**이다.

그래서 필수 필드·타입·`installed_hosts`·`assets`·`core_renders`를 install과 **같은 계약**으로 본다. 읽는 쪽마다 기준을 따로 두면 언제나 느슨한 쪽이 실제 기준이 된다. 계약 위반은 확인 **전에** `BLOCKED(2)`로 수렴한다. 없는 것과 틀린 것은 다르므로, 나중에 생긴 key는 있을 때만 타입을 본다 — 구버전으로 설치한 프로젝트가 제거 자체를 못 하게 되면 그건 안전이 아니라 고장이다.

### G8-b. 경로 표기는 하나다

화면과 `--json`이 같은 함수를 지난 값 하나를 쓴다. 둘이 갈라지면 소비자마다 무엇을 기준으로 비교할지가 달라지고, 사용자는 어느 쪽이 진짜인지 말할 수 없다.

project 자산은 저장소 기준 상대 경로, 전역 자산은 `$CODEX_HOME/skills/...`다. 실경로를 풀어 내면 실행 머신의 홈 경로가 로그와 이슈에 그대로 실리고, 전역 자산은 사용자가 정한 이름으로 말해야 "내 어느 설정이 이걸 만들었는가"가 읽힌다. 제어문자와 개행은 escape한다 — 그대로 찍으면 목록 한 줄이 두 줄이 되고, 두 번째 줄은 우리가 쓴 것처럼 보인다.

### G9. 엔진 저장소에서는 돌지 않는다

`is_engine_source_tree`가 참이면 project·all uninstall을 차단한다. 엔진 개발 트리를 자기 명령으로 지우는 경로를 만들지 않는다.

### G10. 확인 없이 지우지 않는다

불변 plan을 먼저 출력하고 명시적 동의만 실행한다. 취소는 byte 변경 없이 `CANCELLED(0)`이다. 비대화형은 `--yes`가 없으면 동의를 추정하지 않고 `BLOCKED(2)`다.

### G11. 판정은 언어를 타지 않는다

planner는 localized 문장이 아니라 구조화된 code·arguments를 담은 immutable plan을 반환한다. 한영 renderer가 같은 plan을 소비하므로 판정과 exit가 언어에 따라 달라지지 않는다.

### G12. 보고는 생략하지 않는다

`DELETE`는 묶어도 되지만 `STRIP`·`PRESERVE`·`BLOCK`은 길어도 축약·생략하지 않는다. 실행 후에도 실제 처리 결과와 모든 보존 경로·사유를 다시 출력한다.

### G13. 이 저장소에서 안 막히는 것은 증거가 아니다

엔진 소스 트리에서는 자기 게이트가 실행되지 않고, G9에 따라 uninstall 자체도 여기서 돌지 않는다. 모든 판정은 `sage_project_worktree` 아래 격리 소비 프로젝트에서만 검증된다.

### G14. "SAGE 흔적"은 좁게 정의한다

manifest 없이 흔적만 있으면 `BLOCKED(2)`인데, 이때의 흔적이 넓으면 두 번째 uninstall이 차단된다. 첫 실행이 manifest를 마지막으로 지우고 최상위 4종을 `PRESERVE`로 남기기 때문이다. 그래서 흔적은 다음으로 한정한다.

| 흔적으로 센다 | 세지 않는다 |
|---|---|
| `sage/`·`.sage/`·`docs/sage_harness/`·`scripts/sage_harness/` | `PRESERVE`로 남긴 최상위 4종 |
| active canonical hook 등록 | `plan_docs`·Obsidian vault |
| | 일반 프로젝트 파일 |

이 정의가 있어야 "두 번째 uninstall은 멱등"과 "흔적만 있으면 BLOCKED"가 동시에 성립한다. 둘 다 계약이므로 어느 하나를 포기하지 않는다.

### G15. 이번 사이클은 로컬 게이트 증거를 갖지 않는다

SAGE CLI로 사이클을 열지 않으므로 cycle 결속은 문서 규약으로만 유지된다. 사후에 형식만 맞춘 감사 레코드를 만들지 않는다.

## 승인 설계와의 편차

착수 시점 실측에서 설계 문언을 그대로 따르면 자산이 남거나 잘못 지워지는 자리가 셋 나왔다.

### D1. codex 전역 skill은 한 가족이 아니라 두 가족이다

**설계 문언:** §8이 전역 범위를 `$CODEX_HOME/skills/<exact-core-skill-id>/`로만 적고 "비슷한 이름과 사용자 skill은 무시한다"고 한다.

**실측:** 전역 namespace에는 두 종류가 들어간다. `install._codex_global_skill_path(skill_id)`는 bare CORE id로 쓰고(`install.py:304`), `generate`는 `gid = f"{prefix}-{aid}"`로 `<prefix>-<aid>` 형태로 쓴다(`generate.py:1210`). prefix는 profile의 `project.prefix`이며 비면 fail-closed다.

**문제:** 설계대로 bare CORE id만 지우면 **generate가 배포한 `<prefix>-<aid>` skill이 전역에 고아로 남는다.** 이들은 사용자 skill이 아니라 SAGE가 특정 프로젝트를 위해 배포한 자산이고, 그 프로젝트에서 SAGE를 지운 뒤에도 codex 자동발견에 계속 잡힌다.

**바꾼 것:** 전역 삭제 후보를 두 가족으로 나누되, **범위 경계는 설계 §4의 표를 그대로 지킨다.**

| 범위 | `$CODEX_HOME` 처리 |
|---|---|
| `sage uninstall` (project) | **mutation 금지.** 전역에 이 프로젝트가 배포한 skill이 있을 수 있다는 사실만 보고하고 `--all`을 안내한다 |
| `sage uninstall --global` | bare CORE id만 처리 |
| `sage uninstall --all` | project + bare CORE id + 이 프로젝트로 특정 가능한 `<prefix>-<aid>` |

두 가족의 **소유권 판정 기준이 서로 다르다**. 같은 기준을 쓰면 한쪽이 반드시 틀린다.

- bare CORE id: `_LEGACY_SKILL_SIGNATURE` 마커로 판정한다. 이 마커는 `templates/core/**` 아래 24개 CORE 자산에만 있다.
- `<prefix>-<aid>`: **마커로 판정할 수 없다.** generate 배포본은 `_interpretive_render_paths()`가 만드는 프로젝트 렌더(`<dest>/.codex/skills/<aid>/SKILL.md`)이고 `templates/core`를 거치지 않으므로 마커가 없다. 대신 다음 결합으로 판정한다.
  1. 범위가 `--all`일 것
  2. manifest에 해당 `skills/<aid>`가 있을 것
  3. profile prefix가 `^[A-Za-z0-9_-]+$`를 만족할 것
  4. 전역 사본이 프로젝트 `.codex/skills/<aid>/SKILL.md`와 hash·bytes 일치할 것
  5. 하나라도 어긋나면 `PRESERVE`·`PARTIAL`

**설계 의도를 지키는 방법:** 설계 §4는 project 범위를 "현재 프로젝트의 SAGE 자산"으로 못 박고, 다른 프로젝트 영향 경고를 global·all에만 붙였으며, `--global`+`--dest`를 exit 2로 막았다. 이 셋은 범위 분리가 의도된 것임을 함께 말한다. 고아 자산 문제는 실재하지만 그 해법은 project 범위를 넓히는 것이 아니라 `--all`에 두고 project 범위에서는 안내하는 것이다. 4번 hash 대조는 "소유권을 추측하지 않는다"는 G2를 마커 없이 지키는 수단이다 — generate가 `force=True`로 복사하므로 일치가 정상 상태이고, 어긋났다면 사용자가 손댄 것이므로 지우지 않는다.

### D2. CORE roster는 두 벌이며 추출은 통합이다

**설계 문언:** §12가 `sage/managed_assets.py`를 "install/uninstall이 공유하는 canonical CORE ID·target builder"로 신설하고 "`install.py`에서 최소 경로 정본만 추출한다"고 한다.

**실측:** roster가 이미 두 벌이다. `overlay_classify.CORE_IDS`(:37)와 `install._CORE_AGENTS`/`_CORE_SKILLS`/`_CORE_BOOTSTRAP_SKILLS`(:35-40)가 별도로 존재하고, 주석과 `test_overlay_classify`의 대조로만 동기화된다. 순환 import 회피가 분리 사유다.

**문제:** 설계대로 `install.py`에서만 추출하면 roster가 **세 벌**이 된다. 동기화 대상이 하나 늘고 드리프트 확률이 올라간다.

**바꾼 것:** `managed_assets.py`는 신규 정본이 아니라 **기존 두 roster의 통합점**으로 만든다. `overlay_classify`와 `install`이 모두 이 모듈을 참조하고, 기존 대조 테스트는 통합 후에도 살아 있어야 한다. 순환 import 회피라는 원래 제약은 새 모듈이 아무것도 import하지 않는 순수 데이터 모듈이 되면 자동으로 지켜진다.

**설계 의도를 지키는 방법:** 설계가 원한 것은 "install과 uninstall이 같은 정본을 본다"이다. 정본을 하나로 줄이는 것이 그 의도이며, 늘리는 것은 반대다.

### D3. 은퇴한 CORE skill 이름이 삭제 인벤토리에서 빠져 있다

**설계 문언:** §7의 host 자산 절이 현재 CORE ID만 나열한다.

**실측:** `install._LEGACY_CORE_SKILLS = ["pdca-start", "sage-pdca-start"]`가 있고, install은 이 이름의 잔존 사본을 정리한다(`install.py:41-43,220`). rename 수렴을 위한 장치다.

**문제:** 설계대로 현재 ID만 지우면 **install이 정리 대상으로 인정한 자산이 uninstall 뒤에 남는다.** install과 uninstall의 인벤토리가 갈리고, 설계 §12가 요구한 "install과 uninstall inventory 동등성"이 처음부터 깨진 상태로 출발한다.

**바꾼 것:** `_LEGACY_CORE_SKILLS`를 삭제 후보에 포함한다. 단 이름만으로 지우지 않고 `_LEGACY_SKILL_SIGNATURE`(`"CORE framework bootstrap asset"`) 마커 확인을 조건으로 둔다. 마커가 없으면 동명의 사용자 skill일 수 있으므로 `PRESERVE`다.

**설계 의도를 지키는 방법:** §16의 확정 결정 "install과 uninstall inventory 동등성을 테스트로 고정한다"를 실제로 성립시키려면 legacy 이름이 양쪽에 있어야 한다.

## 구현 순서

선행 병합을 경계로 두 구간으로 끊는다.

**선행 병합 전 — 문서 구간 (현재 구간)**

1. 00~02 문서를 작성한다.
2. 코드·테스트·fixture를 만들지 않는다.

**선행 병합 후 — 구현 구간**

3. rebase하고 R1~R7을 대조한 뒤 필요한 문서를 고친다. R2는 선행 소유자와 합의가 필요할 수 있다.
4. Phase 03을 열고 acceptance ID·file owner·검증 명령을 기록한다.
5. `managed_assets.py`로 두 roster를 통합하고 기존 대조 테스트가 통과함을 확인한다.
6. read-only planner와 `UninstallPlan`을 구현한다.
7. 공유 파일 순수 변환(`.gitignore`·host JSON)을 구현한다.
8. transaction executor와 통합 rollback을 구현한다.
9. 한영 renderer·확인·보고를 구현한다.
10. clean-consumer matrix와 실패 주입 검증을 구현한다.
11. 한영 문서를 갱신하고 재스탬프한다.
12. 전체 suite·wheel smoke를 돌리고 독립 리뷰를 최대 3라운드 받는다.

## 주요 위험과 통제

| 위험 | 등급 | 통제 |
|---|:---:|---|
| planner에 없는 경로가 삭제됨 | P0 | executor가 plan 밖 target을 거부하는 검사. plan 출력 후 fingerprint 변화 시 차단. |
| 소유권 불명 파일이 삭제됨 | P0 | 최상위 4종과 수정된 framework 파일의 `PRESERVE` 고정 테스트. |
| `plan_docs`·vault·소스가 삭제됨 | P0 | 실행 전후 byte hash 대조. write target 열거에서 제외됨을 검사. |
| 광범위 경로·엔진 저장소에서 실행됨 | P0 | `is_engine_source_tree`와 광범위 경로 차단 회귀. |
| symlink ancestor traversal로 트리 밖을 지움 | P0 | ancestor symlink fixture 차단 검사. |
| 실패 후 부분 삭제 상태가 남음 | P0 | 각 단계 실패 주입 후 bytes·mode·symlink·tree 복원 검사. |
| 공유 파일에서 사용자 설정까지 지움 | P0 | SAGE·사용자 hook 혼합 fixture에서 사용자 항목 보존 검사. |
| 손상된 marker·JSON을 추측해 고침 | P0 | 중복·역순·부분·손상 fixture에서 파일 전체 `PRESERVE` 검사. |
| 읽지 못한 host JSON이 `absent`로 접혀 잔재가 조용히 남음 | P0 | 문법 손상·비 UTF-8·권한 거부 fixture에서 `unknown` 판정과 `PRESERVE` 검사. |
| 잔재가 남았는데 manifest tree를 지워 다음 실행이 증거를 잃음 | P0 | 잔재 상태 1회차 후 manifest 존재, 2회차 `PARTIAL(1)`·mutation 0 검사. |
| 부분 write 후 I/O 실패가 잘린 파일을 남기고 rollback이 거부됨 | P0 | write 도중 `ENOSPC` 주입 후 원본 bytes·mode 복원 검사. |
| 손상 보고에 사용자 설정값·command 원문이 실림 | P1 | damage 직렬화에 secret·command 문자열 부재 검사. |
| 계획 단계 손상 입력이 traceback으로 끝나 JSON envelope이 없음 | P1 | 비 UTF-8 `.gitignore`·계획 예외 주입에서 `BLOCKED(2)` JSON 검사. |
| generate 배포 전역 skill이 고아로 남음 | P1 | D1의 두 가족 처리를 인수 기준으로 고정한다. |
| roster가 세 벌이 되어 드리프트 | P1 | D2의 통합과 기존 대조 테스트 존속을 인수 기준으로 고정한다. |
| legacy skill 이름이 남아 inventory 동등성이 깨짐 | P1 | D3의 legacy 포함과 marker 조건을 인수 기준으로 고정한다. |
| 성공 상태에 dangling hook 등록이 남음 | P1 | 등록·shim 제거 순서 회귀. |
| BLOCK 문구가 선행 오라클을 위반 | P1 | R1·R2를 rebase 재확인 목록의 필수 항목으로 둔다. |
| 사이클을 CLI로 열지 않아 결속 값이 형식만 남음 | P1 | G15로 명시하고 형식만 맞춘 감사 레코드 생성을 금지한다. |
| project 범위가 전역 namespace를 mutation | P0 | 기본 `sage uninstall` 실행 전후 `$CODEX_HOME` byte 불변 검사. |
| `<prefix>-<aid>`에 마커를 요구해 처방이 무력화 | P0 | 마커 없는 정상 배포본이 `--all`에서 실제로 제거되는 회귀. |
| 전역 사본이 드리프트했는데 삭제됨 | P1 | hash 불일치 fixture에서 `PRESERVE`·`PARTIAL` 검사. |
| 첫 uninstall 뒤 두 번째 실행이 BLOCKED | P1 | 연속 2회 실행 회귀 — 두 번째가 `COMPLETE(0)` no-op. |
| filesystem root 직계 자식(`/usr`·`/opt`·`/Users`)이 대상으로 통과 | P0 | root 직계 자식 실측 목록에서 `BLOCKED(2)`와 **write target 0건** 검사. |
| 구조가 깨진 manifest를 정상 증거로 읽어 증거부터 지움 | P0 | `{}`·타입 위반 10종에서 확인 전 `BLOCKED(2)`·write target 0건 검사. install과 같은 계약을 보는지 대조. |
| 손상 블록 뒤의 SAGE 등록을 못 보고 넘어감 | P0 | 손상 뒤에 command를 둔 fixture에서 `present` 판정 검사. |
| 손상된 host JSON을 STRIP해 우리 파서가 최종 모양을 정함 | P0 | hooks 배열의 비객체 항목 fixture에서 `strippable` 거짓·본문 부재 검사. |
| 화면과 `--json`이 다른 경로를 보임 | P1 | 표기 함수를 갈아 끼우면 양쪽이 함께 바뀌는지 검사. 출력 전체에 절대 경로 부재 검사. |

## 개발·검토 흐름

1. 같은 stem의 00~02와 위키 설계 정본을 모두 읽는다. 저장소에는 설계 사본이 없다.
2. rebase 이후 R1~R7을 대조하고 필요한 문서를 고친 뒤 Revision Log에 남긴다.
3. source edit 전에 Phase 03을 열고 acceptance ID·file owner·검증 명령·`Document-Language: ko`를 기록한다.
4. 구현 구간을 순서대로 진행하며 Phase 03에 파일·증거를 누적한다.
5. Phase 04는 설계 차이·coverage·acceptance evidence를 한국어로 기록하되 최종 판정을 내리지 않는다.
6. fresh-context 독립 검토가 핵심 검증을 재현하고 Phase 05를 한국어로 작성한다. 최대 3라운드다.
7. `APPROVED` 뒤 Phase 06은 `NOT READY` 또는 `READY_FOR_USER_MERGE_DECISION`을 보고한다.
8. 사용자 별도 승인 전 커밋·머지·push·태그·릴리즈를 수행하지 않는다.

## 5. Done Criteria

### 범위와 분류

- [x] project·global·all 범위가 승인된 inventory와 정확히 일치한다.
- [x] 모든 target이 `DELETE`·`STRIP`·`PRESERVE`·`BLOCK` 중 정확히 하나를 갖는다.
- [x] `--global`+`--all`, `--check`+`--yes`, `--global`+`--dest`가 exit 2다.
- [x] SAGE 전용 tree 4종이 내부 수정 여부와 무관하게 제거된다.
- [x] host 자산이 `sage-*` glob이 아니라 정확한 CORE ID로 제거된다.
- [x] 상위 디렉터리가 비었을 때만 제거된다.
- [x] 은퇴한 CORE skill 이름이 marker 확인을 조건으로 삭제 후보에 포함된다.
- [x] 기본 `sage uninstall`(project)이 `$CODEX_HOME`을 mutation하지 않는다.
- [x] project 범위가 전역 배포본 존재 가능성을 보고하고 `--all`을 안내한다.
- [x] generate가 배포한 `<prefix>-<aid>` 전역 skill이 `--all` 범위에서 제거된다.
- [x] `--global` 단독에서 `<prefix>-*`를 추측 삭제하지 않는다.
- [x] bare CORE id 전역 skill이 `_LEGACY_SKILL_SIGNATURE` 확인 후 제거된다.
- [x] `<prefix>-<aid>` 판정에 마커를 요구하지 않는다. 마커를 요구하면 정상 배포본이 삭제되지 않음이 테스트로 드러난다.
- [x] `<prefix>-<aid>`가 manifest aid·안전한 prefix·프로젝트 렌더와의 hash 일치 넷을 모두 만족할 때만 삭제된다.
- [x] 전역 사본이 프로젝트 렌더와 hash 불일치면 `PRESERVE`·`PARTIAL`이다.

### 보존과 소유권

- [x] 소유권 불명 최상위 4종이 항상 보존·보고된다.
- [x] 수정된 framework 파일이 보존·보고된다.
- [x] `.gitignore`에서 정상 managed block만 제거되고 다른 줄이 보존된다.
- [x] host JSON에서 canonical SAGE hook 등록만 제거되고 사용자 hook·설정이 보존된다.
- [x] marker 중복·역순·부분·손상과 JSON 손상 시 파일 전체가 `PRESERVE`된다.
- [x] 문법 손상·비 UTF-8·권한 거부가 `unknown`으로 판정되고 `absent`로 접히지 않는다.
- [x] `unknown`이어도 manifest `installed_hosts` 증명이 있으면 `PRESERVE`에 포함된다.
- [x] 잔재가 남은 동안 manifest tree가 보존되고 매 실행이 mutation 없는 `PARTIAL(1)`이다.
- [x] 복구 후 실행에서만 manifest tree가 마지막 자산으로 제거된다.
- [x] 손상 보고가 좌표(pointer·행·열·offset·errno)를 싣고 사용자 내용을 싣지 않는다.
- [x] host JSON 판정이 전수 검증과 **손상 0에서만 도는 투영** 두 단계이고, 손상이 있으면 본문을 만들지 않는다.
- [x] handler의 `type`을 먼저 확정하고 **종류별 계약**(command→`command`, http→`url`, mcp_tool→`server`·`tool`, prompt·agent→`prompt`)으로 검증한다. `matcher`는 있을 때만 문자열이다.
- [x] 소유권 비교와 `STRIP`이 `type == "command"`인 entry에만 적용된다 — 다른 종류가 우연히 같은 `command` property를 가져도 우리 것이 아니다.
- [x] 정상 prompt·agent·http·mcp_tool handler는 손상이 아니며 bytes/의미 그대로 보존되고, SAGE 등록만 빠진 뒤 재실행이 `COMPLETE(0)` no-op다.
- [x] 모르는 handler 종류와 종류별 필수 필드 누락은 fail-closed로 `PRESERVE`다.
- [x] 판정이 host와 event를 함께 받는다. claude·codex 계약을 한 표로 섞지 않는다.
- [x] claude의 event별 허용 handler 종류가 **공식 계약 그대로** 들어 있다 — 다섯 종류 전부 / `prompt`·`agent` 제외 / `SessionStart`·`Setup`은 `command`·`mcp_tool`만.
- [x] 공식 event 계약표가 등록된 host(현재 claude)에서 표에 없는 event는 전부 허용으로 추정하지 않고 `unknown_event` 손상으로 보존한다. codex는 그 표를 공유하지 않으며 별도 계약으로 관리한다(표를 옮기기 전까지 종류를 제한하지 않는다).
- [x] 정상 SAGE 설치본(5 event)은 이 제한 아래에서도 그대로 `STRIP`된다.
- [x] 중복 key와 비표준 JSON constant(`NaN`·`Infinity`)가 fail-closed로 손상 판정된다.
- [x] `plan_docs`·vault·소스·테스트·unrelated host 자산·Git metadata가 byte 불변이다.
- [x] 부분 제거·수동 보존 경로가 operation·reason과 함께 생략 없이 출력된다.
- [x] 경로 표기가 **단일 formatter**를 지나고 화면과 `--json`이 같은 값을 쓴다 — project는 상대, global은 `$CODEX_HOME/skills/...`, root 밖은 `<outside-project>`, 제어문자는 escape.

### 실행과 원자성

- [x] 불변 plan을 먼저 출력하고 명시적 동의만 실행한다.
- [x] 취소가 byte 변경 없이 `CANCELLED(0)`이다.
- [x] 비대화형에서 `--yes` 없이 `BLOCKED(2)`다.
- [x] `--check`가 mutation 없이 예상 상태와 대응 exit를 낸다.
- [x] plan 출력 후 fingerprint가 바뀌면 삭제하지 않고 차단한다.
- [x] executor가 plan에 없는 target을 추가할 수 없다.
- [x] 등록이 실행 파일보다 먼저 제거된다.
- [x] manifest가 마지막 논리 자산으로 제거된다.
- [x] 기술적 실패 시 project·global이 하나의 단위로 rollback된다.
- [x] rollback 실패 시 보존한 복구 경로가 출력된다.
- [x] 성공한 project uninstall 뒤 active SAGE hook 등록이 없다.
- [x] 성공한 uninstall 뒤 clean reinstall이 통과한다.
- [x] 두 번째 uninstall이 멱등이다.

### 안전 경계

- [x] 엔진 저장소에서 project·all uninstall이 차단된다.
- [x] `/`·filesystem root·홈 같은 광범위 `--dest`가 차단된다.
- [x] 선언된 write root 밖 경로가 삭제되지 않는다.
- [x] symlink ancestor를 따라가지 않는다.
- [x] SAGE-owned leaf symlink가 target을 따르지 않고 link만 처리된다.
- [x] shell `rm`·recursive glob·미해결 환경변수 target을 쓰지 않는다.
- [x] `plan_docs`·vault가 write target으로 열리지 않는다.
- [x] 패키지 매니저 내부와 실행 중인 CLI 환경에 접근하지 않는다.
- [x] manifest 손상 시 확인 전 `BLOCKED(2)`다.
- [x] manifest 구조가 필수 필드·타입·`installed_hosts`·`assets`·`core_renders`·skill receipt까지 검증되고, install과 **같은 계약 함수**를 본다.
- [x] 자산 key가 `<kind>s/<id>` 문법으로 검증된다 — 빈 id·`.`·`..`·추가 separator·절대경로·경로 탈출 문자를 거부하고, id 판정은 저장소 정본을 재사용한다.
- [x] 경로 탈출 asset key가 계획을 만들기 **전에** `BLOCKED(2)`로 수렴하고, `--check`·`--yes` 둘 다 write target 0건이며 manifest bytes·root 밖 파일·프로젝트/전역 tree가 무변경이다.
- [x] 전역 후보가 stat·read·action 전에 `candidate_block`을 지난다 — 계약을 우회한 호출이 생겨도 계획 층이 혼자 막는다.
- [x] 정규화된 경로 기준으로 **같은 target에 정확히 하나의 action**이다. 두 가족이 같은 경로를 주장하면 우선순위를 정하거나 덮지 않고 `uninstall.action_conflict`로 계획 전체가 `BLOCKED(2)`다.
- [x] 실행 층도 lock·mutation 전에 중복·상충 target을 다시 본다.
- [x] 손상 manifest의 사용자 제어 문자열(asset key·host·render key)이 진단에 원문으로 실리지 않는다 — 안전한 이름만 통과하고 나머지는 가린 뒤 `index` 좌표로 대신한다.
- [x] 불완전한 `core_renders` receipt가 소유권 증거로 쓰이지 않는다 — 확인 전 `BLOCKED(2)`, write target 0건, 원본 bytes 무변경.
- [x] filesystem root의 **직계 자식**(`/usr`·`/opt`·`/Users`)과 광범위 전역 skill root가 계획 단계에서 차단되고 write target이 0건이다.
- [x] manifest도 SAGE 흔적도 없으면 `COMPLETE(0)` no-op다.
- [x] manifest 없이 SAGE 흔적만 있으면 `BLOCKED(2)`다.
- [x] "SAGE 흔적"이 4개 tree와 active canonical hook 등록으로 한정된다.
- [x] `PRESERVE`된 최상위 4종·`plan_docs`·vault가 흔적으로 세어지지 않는다.
- [x] 첫 uninstall 직후 두 번째 실행이 `BLOCKED`가 아니라 `COMPLETE(0)` no-op다.
- [x] project 범위가 `$CODEX_HOME`을 **읽지도 쓰지도 않는다** — unit spy 호출 0건과 격리 소비자 증거 둘 다 있다.
- [x] project 범위 보고가 전역 존재를 주장하지 않고 미검사 고지와 `--all` 안내만 낸다.
- [x] `--json`이 네 상태의 exit code를 바꾸지 않고, 사람 화면과 같은 plan을 소비하며, ko·en에서 byte 동일하다.
- [x] 실행형 `--json`에 `--yes`가 없으면 stdin을 기다리지 않고 usage error `2`로 끝난다.
- [x] `BLOCKED(2)` 복구가 읽기 전용 명령·수동 Action·재검증 세 단계이고 파괴적 명령을 내지 않는다.
- [x] 새 uninstall BLOCK code의 CLI 전용 recovery id가 `CLI_ONLY_RECOVERY_IDS`에 정확히 선언되고 변이 검사로 고정됐다.

### 정본과 다국어

- [x] CORE roster 정본이 하나로 통합됐고 기존 대조 테스트가 통과한다.
- [x] install과 uninstall inventory 동등성이 **mutation-sensitive test**로 고정됐다 — 한쪽에만 legacy 이름을 더하면 실패한다.
- [x] install의 동작과 배치 결과에 회귀가 없다.
- [x] planner가 localized 문장이 아니라 code·arguments를 반환한다.
- [x] 한국어·영어가 같은 판정과 exit를 낸다. localization inventory가 0이다.
- [x] 모든 사용자 노출 BLOCK이 선행 계약의 다음 행동을 갖는다.

### 검증 환경

- [x] clean-consumer matrix 8종이 통과한다.
- [x] 실패 주입 7지점에서 bytes·mode·symlink·tree가 복원된다.
- [x] lock 경쟁·권한·광범위 경로·path escape·symlink ancestor·manifest 교체·확인 후 동시 변경이 검증됐다.
- [x] v0.9.84 소비자를 upgrade 없이 uninstall할 수 있다.
- [ ] Python 3.10·3.11·3.12에서 통과한다. **Linux·macOS는 실제 실행**이고, **Windows는 계획
  실행 성공 + mutation 거부(exit 2) + 무변경**이다 — Windows는 상위 디렉터리 교체 경쟁을 막을
  수단(`dir_fd`)이 없어 안전한 제거를 보장할 수 없다. 안전 구현은 EH-30으로 이관했다.
  (사용자 결정 (b), 2026-08-29 Asia/Seoul)
  **미해결로 두는 이유:** 로컬은 이번 회차에 인터프리터 하나(3.14)로만 돌렸고 다중 버전 매트릭스와
  Linux·Windows 러너는 원격 CI 몫이다. 정의(`uninstall_matrix` 9조합)는 있으나 **정의가 있다는
  것이 실행 증거는 아니다** — UNI-AC26·UNI-AC30·UNI-AC30w 는 NOT TESTED 다.
- [x] 공백·Unicode 프로젝트 경로에서 통과한다.
- [x] 기본·사용자 지정 `$CODEX_HOME`에서 통과한다.
- [x] 모든 로컬 fixture가 `sage_project_worktree` 아래 고유 자식 폴더만 사용했다.
- [x] 로컬 무증상을 증거로 쓰지 않았고 형식만 맞춘 감사 레코드를 만들지 않았다.

### Shared-Surface Contract Gate

- [x] Phase 02 §10.1 권한·소유권 18행이 확정돼 있고 scope별 변경 가능 경로가 완전히 분리돼 있다.
- [x] Phase 02 §10.2 신뢰 경계·실패 12행이 확정돼 있다.
- [x] ownership proof 부재·marker/hash/manifest 손상이 `DELETE`가 아니라 `PRESERVE` 또는 `BLOCK`이다.
- [x] Phase 02 §10.3 불변식 J1~J22가 각각 대응 mutation 검사를 갖는다.
- [x] project scope의 `$CODEX_HOME` 변경이 0건이다 (J15).
- [x] P0·P1 7+4항목이 하나도 수용되지 않았다.
- [x] P2 잔여 위험 RU-1~RU-5가 사용자 승인을 받았다.
- [x] Phase 02 §10.5 소비자 E2E CU-1~CU-16이 통과했다.
- [x] 종료 계약 9단계(plan(기준 확보) → 확인 → 정렬 lock → fingerprint 대조 → prepare → 경계 재확인 → backup/rollback → 결과 검증 → commit → cleanup → unlock)가 순서대로 검증됐다. lock 은 대조 **앞**이고 `install`·`generate` 와 **같은 lock** 이다 — 전용 lock 을 따로 두면 두 명령이 서로를 막지 못한 채 각자 잠갔다고 믿는다.
- [x] 보존 대상 다섯(`plan_docs`·vault·소스/테스트·Git metadata·소유권 불명 파일)이 byte 불변이다.
- [x] 사용자 결정 UD-1~UD-5가 내려졌고 §10.1·§10.3·§10.4·§10.6에 반영됐다.
- [x] Gate 판정이 READY로 바뀐 뒤에 Phase 03을 열었다.

### 착수 방식

- [x] rebase 이후 R1~R7을 대조했고 불일치 항목을 문서에 반영했다.
- [x] R2(파괴적 명령 금지 규칙과의 상호작용)가 해소됐다.
- [x] 문서 구간에서 코드·테스트·fixture를 만들지 않았다.

## 6. Done Criteria Revision Log

### Revision 3

- Changed-At: Phase 02 (Shared-Surface Contract Gate)
- Reason: Phase 03 진입 전 종료 범위·신뢰 경계·잔여 위험을 확정하는 Gate를 Phase 02에 추가했다.
- Affected-Phases: 00·01·02
- Summary: Phase 02에 §10 Gate 다섯 표와 정본 순서(§10.0)·종료 계약 6단계·사용자 결정 표·판정 절을 추가했다. scope별 변경 가능 경로를 표로 완전히 분리하고 J15(project scope의 `$CODEX_HOME` 변경 0건)를 최상위 scope 불변식으로 세웠다. Done Criteria에 Gate 12항목을 넣고 헤더에 `Phase03-Entry`를 신설했다. 인수 기준에 UNI-AC32~35를 더했다. 판정은 **BLOCKED** — UD-1~UD-5가 미결이며 그중 UD-2·UD-5는 §10.1 표와 J15·J16의 내용을 바꾼다.

### Revision 2

- Changed-At: Phase 00 (문서 리뷰 반영)
- Reason: D1이 두 결함을 만들었다는 지적이 타당했다. 범위 경계가 승인 설계 §4와 충돌했고, `<prefix>-<aid>`에 CORE 마커를 요구해 처방이 무력화됐다.
- Affected-Phases: 00·01·02
- Summary: D1을 다시 썼다. project 범위의 `$CODEX_HOME` mutation을 금지하고 전역 처리를 `--global`·`--all`로 되돌렸다. `<prefix>-<aid>` 소유권을 마커가 아니라 범위·manifest aid·안전한 prefix·프로젝트 렌더 hash 일치의 결합으로 판정하게 바꿨다. "SAGE 흔적"을 4개 tree와 active hook 등록으로 한정하는 G14를 신설해 멱등 계약과의 충돌을 닫았다(기존 G14는 G15로 이동).

### Revision 4

- Changed-At: Phase 02 Gate (사용자 결정)
- Reason: rebase 이후 R1~R7을 실제로 대조했고, 그 결과와 사용자 결정 UD-1~UD-6이 계약을 바꿨다.
- Affected-Phases: 00·01·02 · 위키 SSOT
- Summary: R2에서 복구 오라클의 두 규칙(파괴적 명령 금지 + BLOCK 당 실행 가능한 명령 최소 하나)이 함께 걸린다는 것을 확인해, `BLOCKED(2)` 복구를 읽기 전용 `--check --verbose` → 수동 Action → 재검증 세 단계로 확정했다(UD-4). UD-5 (b)로 project 범위의 `$CODEX_HOME` 격리를 **쓰기 금지에서 접근 금지**로 넓히고, 전역 "존재 보고"를 "미검사 고지"로 바꿨다 — 보지 않은 것을 봤다고 말하지 않는다. UD-3 (c)로 `--json`을 추가하되 네 상태의 exit code는 고정하고 `--allow-partial`은 만들지 않는다. UD-1 (a)·UD-2 (a)·UD-6 (a)를 확정하고, RU-2 수용 기록에 severity·영향·재현 조건·owner·follow-up EH-29·재검토 조건을 채웠다. R3~R6 실측 정정(`install.py` 1,665줄 유지, hook runtime 22개, manifest property 14개, 서브커맨드 25개)도 함께 반영했다. Phase 03 진입을 READY로 전환한다.

### Revision 10

- Changed-At: Phase 05
- Reason: event 별 handler 계약을 비워 둔 것이 틀렸다. 공식 hooks reference 는 "Not all events support every hook type." 을 명시하고 세 그룹을 나열하는데, 앞 회차에 문서 **요약**을 읽고 제한이 없다고 결론했다. 그 사이 `SessionStart` 의 prompt hook 이 손상 없이 통과해 문서가 다시 쓰였다.
- Affected-Phases: 01, 02, 03, 04
- Summary: Phase 00 자체와 위키 SSOT 도 함께 고쳤다. 공식 표를 `EVENT_HANDLER_KINDS["claude"]` 에 세 그룹 그대로 옮겼다(전체 13 · `prompt`·`agent` 제외 18 · early 2). codex 에는 복사하지 않고 host 분리를 유지한다. 공식 event 계약표가 등록된 host(현재 claude)의 미등록 event 는 전부 허용으로 추정하지 않고 `unknown_event` 손상으로 보존한다(FR-E04l). 검사가 제한을 주입하던 방식을 걷어내고 **production 표를 그대로 읽도록** 다시 썼으며, 표를 비우는 mutation 이 실패하는 것으로 그것을 고정했다. UNI-AC52 의 PASS 를 철회하고 다시 세웠다. Phase 04 질문 10 은 결정 질문이 아니라 **제 확인이 틀렸던 항목**으로 정정했다. 원격 증거(UNI-AC26·AC30·AC30w)는 계속 NOT TESTED 다.

### Revision 9

- Changed-At: Phase 05
- Reason: 같은 전역 경로를 두 가족이 주장해 한 경로에 `DELETE` 와 `PRESERVE` 가 함께 생겼다(P0 · J7·UNI-AC04 위반). 손상 manifest 의 사용자 key 가 진단에 원문으로 실렸고(P1), 판정이 host·event 를 받지 않았다(P1).
- Affected-Phases: 01, 02, 03, 04
- Summary: Phase 00 자체와 위키 SSOT 도 함께 고쳤다. 정규화 경로 기준 단일 action registry 를 계획 층에 두고, 충돌은 우선순위를 정하거나 덮지 않고 `uninstall.action_conflict` 로 `BLOCKED(2)` 처리한다. 실행 층도 lock 전에 같은 검사를 한다. 위반 dict 를 만드는 자리 하나에 관문을 걸어 사용자 제어 문자열을 가리고 `index` 좌표로 대신한다 — install 과 uninstall 이 같은 안전한 값을 소비한다. `classify_host_bytes(raw, commands, host)` 로 host 를 넘기고 event 별 허용 종류를 host 로 갈린 표 하나에 뒀다. Phase 04 acceptance 표의 separator 와 상태 셀을 게이트 파서 계약에 맞춰, 실제 `acceptance_findings()` 가 오류 0·미해결 3(원격 대기)만 남긴다. UNI-AC04 와 전역 가족 판정을 철회 후 재작성했다. 원격 증거(UNI-AC26·AC30·AC30w)는 계속 NOT TESTED 다.

### Revision 8

- Changed-At: Phase 05
- Reason: 파괴적 계획의 경로 권위와 실제 host schema 경계가 틀렸다. manifest asset key가 경로 조각으로 쓰이는데 문법을 보지 않아 계획이 write root 밖을 가리켰고(P0·J8), classifier가 모든 handler에 `command`를 요구해 정상 Claude prompt hook을 손상으로 오판했다(P1).
- Affected-Phases: 01, 02, 03, 04
- Summary: Phase 00 자체와 위키 SSOT도 함께 고쳤다. 자산 key 문법 검증을 공통 계약에 넣고 id 판정은 `hook_launcher.valid_hook_id` 정본을 재사용한다(FR-H04e). `_manifest_skill_ids`와 `_global_actions`에 2차 방어를 걸어 계약을 우회한 호출도 조회 전에 막는다(FR-H04f). handler 검증을 `type` 우선으로 갈라 종류별 필수 필드를 보고, 소유권 비교와 투영을 `type == "command"`로 한정했다(FR-E04i·FR-E04j). Done Criteria를 parser 계약에 맞췄다 — `Changed-At`·`Affected-Phases` 형식을 고치고, 원격 증거 대기 항목은 `[~]`가 아니라 미해결 `[ ]`로 되돌렸다(`[~]`는 같은 줄 `(N/A: reason)` 전용). Phase 01 acceptance separator도 정식 Markdown으로 고쳤다. UNI-AC42·AC46 계열 PASS를 철회하고 새 증거로 다시 세웠다. 원격 증거(UNI-AC26·AC30·AC30w)는 계속 NOT TESTED다.

### Revision 7

- Changed-At: Phase 05
- Reason: 통합을 절반만 한 자리가 정확히 갈라졌다. 공통 계약이 receipt 의 컨테이너 타입만 확인해 빈 receipt 가 소유권 증거로 통과했고(P0), host classifier 가 모양만 확인해 내용이 깨진 항목을 `strippable` 로 처리해 손상 파일의 bytes 가 바뀌었다(P1).
- Affected-Phases: 01, 02, 03, 04
- Summary: Phase 00 자체와 위키 SSOT 도 함께 고쳤다. `assets` 항목·`core_renders` receipt·skill receipt 의 깊은 검증을 전부 `manifest_contract` 로 옮기고 install 은 code 를 문장으로 만드는 일만 남겼다(FR-H04d). host 항목의 `matcher`(있을 때)·`type`·`command` 타입을 검증하고, 중복 key 와 비표준 JSON constant 를 fail-closed 로 판정한다(FR-E04g·FR-E04h). `uninstall_smoke` 의 이중 relpath 를 고쳐 상대 경로를 직접 소비하고 절대 경로를 거부한다. root 밖 표기를 `<outside-project>` 로 바꿨다(FR-H11b). Done Criteria 를 실제 증거에 따라 표시하고(89 항목 `[x]`, 원격 매트릭스 1 항목 `[~]`) 새 계약 7항목을 더했다. Phase 01 acceptance 표의 separator 를 정식 Markdown 으로 고쳤다. UNI-AC22·AC42·AC42a 의 PASS 를 철회하고 새 증거로 다시 세웠다. 05 질문 6·7 은 승인받았고, 7 의 조건이던 renderer 동시 확인 검사를 더했다. 원격 증거(UNI-AC26·AC30·AC30w)는 계속 NOT TESTED 다.

### Revision 6

- Changed-At: Phase 05
- Reason: 재검토가 P0 둘을 포함한 결함 다섯을 실측으로 짚었다. 안전 경계와 증거 판정이 **주석이 말한 규칙과 다르게** 동작하고 있었다.
- Affected-Phases: 01, 02, 03, 04
- Summary: Phase 00 자체와 위키 SSOT 도 함께 고쳤다. G8을 root 직계 자식까지로 넓히고 전역 skill root에도 같은 경계를 걸었다 — 기존 조건은 `/usr`·`/opt`·`/Users`를 통과시켰고, 주석은 막는다고 적혀 있었다. G8-a로 manifest 구조 계약을 install과 공유하도록 세웠다 — 최상위가 dict인지까지만 보던 판정이 `{}`를 정상 증거로 읽어 첫 실행이 증거를 지우고 두 번째가 `COMPLETE(0)`를 냈다. G8-b로 경로 표기를 하나로 모았다(FR-H11). host JSON 판정을 전수 검증과 clean-only 투영 두 단계로 분리했다 — 손상 블록에서 멈춰 뒤쪽 등록을 놓쳤고, hooks 배열의 비객체 항목을 손상으로 보지 않아 손상 문서를 다시 썼다. UNI-AC22·AC09·AC09a·AC14의 PASS를 철회하고 새 증거로 다시 세웠다. 원격 증거(UNI-AC26 Linux·UNI-AC30·UNI-AC30w)는 계속 NOT TESTED다.

### Revision 5

- Changed-At: Phase 03
- Reason: 손상된 host JSON이 빈 registration으로 접혀 경로가 계획에서 사라졌다. 첫 실행이 manifest까지 지우고, 손상 파일이 남은 두 번째 실행이 `COMPLETE(0)`를 냈다.
- Affected-Phases: 01, 02, 03, 04
- Summary: Phase 00 자체와 위키 SSOT 도 함께 고쳤다. host JSON 판정을 단일 typed outcome으로 통합하고 등록 상태를 `present`/`absent`/`unknown` 셋으로 갈랐다(G3 확장). 파싱·인코딩·I/O 실패는 `absent`가 아니라 `unknown`이며, manifest `installed_hosts`가 설치를 증명하면 `PRESERVE`에 반드시 포함된다. G3-a(영수증은 잔재보다 오래 산다)와 G3-b(손상은 좌표로 보고하고 내용은 싣지 않는다)를 신설했다. 별도 blocker였던 부분 write 후 rollback 거부(P0)와 계획 단계 손상 입력의 traceback(P1)도 함께 닫았다. UNI-AC15의 PASS를 철회했다가 사유를 기록하고 다시 세웠다.

### Revision 1

- Changed-At: Phase 00
- Reason: 최초 작성.
- Affected-Phases: —
- Summary: 승인 설계 §15 완료 조건을 `main@63cc3bd` 실측에 맞춰 판정 가능한 항목으로 전개했다. 실측에서 드러난 편차 셋(codex 전역 skill 두 가족, CORE roster 이중화, 은퇴 skill 이름 누락)을 D1~D3로 기록했다. 선행 미병합 상태에서 착수했으므로 rebase 재확인 목록 R1~R7을 문서 상단 계약으로 고정했다.
