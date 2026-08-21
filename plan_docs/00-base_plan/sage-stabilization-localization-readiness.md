# [기본 계획] SAGE 안정화 및 한영 다국어 준비

Cycle-Stem: `sage-stabilization-localization-readiness`
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 5
Status: NOT READY — 필수 acceptance 미해소, 새 Phase 05 재검토 전

## 0. 사전 지식

| 구분 | 근거 | 핵심 내용 |
|---|---|---|
| 승인 설계 | `docs/superpowers/specs/2026-08-12-sage-1.0-stabilization-localization-design.md` | 코드 정리, 영어 의미 정본, 한국어 기본·영어 선택 출력, 안전한 업그레이드, 릴리즈 준비를 분리된 작업 묶음으로 수행한다. |
| 사용자 결정 | 2026-08-12 설계 대화 | 지원 언어는 `ko`, `en`이고 기본값은 한국어다. 일반 출력은 선택 언어 하나만 사용하고 최초 발견 문구만 한영 병기한다. |
| 문서 언어 결정 | 2026-08-12 추가 승인 | 새 사이클은 시작 시 언어를 한 번 결정하고 같은 Cycle-Stem의 00~06 본문 전체를 그 언어로 작성한다. local 설정이 없으면 한국어다. |
| 릴리즈 경계 | 2026-08-12 사용자 명시 | 이 작업의 통과는 `1.0.0` 변경·태그·배포 권한이 아니다. 독립 검토 결과를 보고한 뒤 별도의 사용자 승인이 필요하다. |
| 구현 기준점 | 로컬 `main@ca9dec0` | EH-13~16은 병합됐지만 미배포 상태다. 판정 불변·진단 가시성 보강 계약은 이번 작업의 고정 입력이다. |
| 업그레이드 기준 | `v0.9.84` / `ea2dc10` | 직접 업그레이드 fixture는 현재 main을 흉내 내지 않고 실제 배포 버전으로 생성한다. |
| 테스트 기준 | 2026-08-12 저장소 조사 | `test_*.py` 76개 중 runner 고유 참조는 74개다. `test_build_identity.py`, `test_profile_compile.py`는 죽은 테스트가 아니라 미연결 테스트다. |
| 엔진 저장소 경계 | 저장소 구조와 `sage._resources.is_engine_source_tree` | 이 저장소는 소비 프로젝트가 아니므로 루트 `AGENT_GUIDE.md`와 `sage/project-profile.yaml`이 없는 것이 정상이다. |
| 인터뷰 기록 | `.sage/plan_interview.md` | 플랫폼, 기능, 제약, 완료 조건과 추가 문서 언어 요구사항이 기록되어 있다. |

## 1. 목표

이번 사이클은 SAGE를 사용자가 1.0 릴리즈 여부를 판단할 수 있는 상태로 준비하되 실제 릴리즈는 수행하지 않는다. 목표는 다음 다섯 가지다.

1. 코드 정리 전에 완전하고 경고 없는 동작·테스트·패키지 기준선을 만든다.
2. 증거로 죽었다고 확인된 코드·테스트·주석만 제거하고, 활성 코드 주석·내부 docstring은 한국어를 기본으로 유지하며 내부 의미 정본은 영어로 통일한다.
3. 거버넌스와 기계 계약을 바꾸지 않고 CLI·hook·CORE skill의 한국어 기본·영어 선택 출력을 제공한다.
4. 새 사이클의 언어를 고정하여 Phase 00~06 본문이 중간에 섞이지 않도록 한다.
5. 실제 `v0.9.84`에서 격리된 1.0 후보로 가는 설치·업그레이드·rollback·패키징·릴리즈 준비를 검증한다.

종료 상태는 정확히 다음 중 하나다.

- `NOT READY`: 필수 인수 항목이 하나 이상 해결되지 않았다.
- `READY_FOR_USER_RELEASE_DECISION`: 구현과 검증은 통과했지만 버전·태그·배포는 변경하지 않았다.

독립 검토 결과 보고 후 사용자가 별도로 승인해야만 `1.0.0` 버전 변경과 외부 배포 작업을 시작할 수 있다.

## 2. 범위

### 2.1 포함

- 모든 `test_*.py`를 실행하거나 구체적 사유가 있는 명시적 제외 목록에 두는 runner 완전성.
- 저장소 소유 `ResourceWarning` 제거와 재발 차단.
- 죽은 import·변수·private helper·중복 테스트·낡은 주석·주석 처리 코드·무효 TODO/FIXME의 증거 기반 정리.
- 프로젝트 소유 Python/shell/YAML 개발 주석과 내부 docstring의 한국어 기본 정책 유지. 정확한 외부 literal, 기계 token, 생성·vendor 자산은 언어 강제 대상이 아니다.
- framework 규칙, hook 명세, CORE skill 13개, CORE agent 6개의 영어 의미 정본.
- managed CORE 원본 `templates/core/framework/docs/agent/language-policy.md`와 소비 프로젝트 설치본 `docs/agent/language-policy.md`.
- subcommand 앞 전역 옵션 `--lang {ko,en}`.
- Git에서 제외되는 `sage/project-profile.local.yaml`의 `interface.language: ko|en`.
- 한국어 기본값, 영어 선택, bare `sage`와 미지원 명시 언어의 한영 안내.
- CLI help/parser 오류/명령 출력, hook 메시지, CORE skill 대화의 선택 언어 적용.
- 새 표준·Fast 사이클의 `Document-Language` 결정, Phase 00 정본화, `.sage/cycle.json` 미러, 00~06 일관성 gate.
- 분리된 CLI/hook catalog와 key·placeholder·충돌·참조 완전성 검증.
- EH-13 경로 drift 진단과 EH-15/16 `ok_l1`·`ok_l0` 가시성 보존.
- 읽기 전용 `sage upgrade --check`와 트랜잭션형 `sage upgrade --apply`.
- 실제 `v0.9.84` fixture, 실패 주입 rollback, 멱등성, clean consumer, wheel/sdist/pipx형, Linux/macOS/Windows smoke.
- 사용자에게 릴리즈 준비 상태를 보고하기 위한 문서와 publish preflight.

### 2.2 제외

- 일본어·중국어·OS locale 자동 감지·사용자 번역 pack·원격 번역 서비스.
- 기존 역사적 plan/review/report/audit/Obsidian 증거의 일괄 번역.
- 자연어 번역 품질의 완전 자동 판정.
- 공개 CLI 삭제, 자동 downgrade, 모든 과거 0.9 버전에서의 직접 migration 보장.
- 저장소 전체 formatting·strict typing·복잡도 재작성·무관한 구조 개선.
- 이름이나 승인 여부가 정해지지 않은 미래 기능.
- 별도 사용자 승인 전 `1.0.0` 영구 변경, `v1.0.0` 생성·push, PyPI·GitHub Release 배포.

## 3. 영향 분석

| 영역 | 변경 | 고정 경계 |
|---|---|---|
| 최상위 CLI | 언어 bootstrap scan, localized parser, 최초 발견 문구 | command/option 이름, channel, 기존 exit는 유지하며 bare `sage`만 승인대로 exit 0으로 바뀐다. |
| 명령 모듈 | 사용자 문자열을 catalog key와 named argument로 교체 | 의미, 파일 쓰기, JSON field, 실패 분류는 유지한다. |
| local profile | local 전용 schema/resolver에 `interface.language` 추가 | 공유 YAML/compiled JSON/manifest/profile hash에 들어가지 않는다. |
| 사이클 상태 | Phase 00에 문서 언어 정본, `.sage/cycle.json`에 미러 | 같은 stem의 00~06 언어는 생성 후 변경할 수 없다. |
| Phase 작성 skill | 선택 언어로 설명 본문·제목 작성 | marker, ID, status, path, command 등 기계 token은 번역하지 않는다. |
| hook 판정 core | locale과 무관한 key/argument 생산 | status, exit, evidence, audit, 분기는 불변이다. |
| hook IO | 독립 catalog로 render 후 host 형식 적용 | 설치 hook runtime은 main `sage`를 import하지 않는다. |
| CORE framework | 영어 canonical 규칙과 managed language policy | 설치 경로와 write-guard 소유권을 보존한다. |
| installer/build identity | 새 문서·catalog 배포 및 logical path drift 진단 | EH-13 aggregate hash 알고리즘은 변경하지 않는다. |
| upgrade | check/apply, backup, rollback | local preference, policy, overlay, authored asset, plan/evidence/audit, 프로젝트 코드를 보존한다. |

## 4. 전역 불변 조건

### G1. 표시 언어는 판정을 바꾸지 않는다

언어 외 입력이 같으면 `ko`와 `en`의 decision, status, exit code, `message_key`, named argument, JSON 구조, 생성 파일, audit, profile/hash가 같아야 한다. 사람용 문장만 달라질 수 있다.

### G2. 한국어가 호환 기본값이다

유효한 설정이 없으면 `ko`다. 기존 한국어 동작을 먼저 catalog로 재현하고 기준선과 비교한 후 영어를 활성화한다.

### G3. local 언어는 공유 거버넌스가 아니다

`interface.language`는 Git 제외 local profile에서만 읽으며 shared profile·manifest·판정·hash·audit에 들어가지 않는다. 새 Phase 문서의 본문과 `Document-Language` marker만 의도된 커밋 결과다.

### G4. 사이클 문서 언어는 한 번만 결정한다

새 사이클은 `명시적 사이클 시작 --lang → local profile → ko`로 결정한다. Phase 00의 `Document-Language`가 정본이고 `.sage/cycle.json`은 미러다. 이후 local 설정 변경이나 충돌하는 `--lang`은 활성 사이클을 바꾸지 못하며 불일치는 쓰기 전에 차단한다.

### G5. 기계 어휘는 번역하지 않는다

command, option, path, YAML/JSON key, ID, hash, `L0`~`L3`, `PASS`, `FAIL`, `WARN`, `BLOCKED`, `APPROVED`, `Cycle-Stem`, `Document-Language`와 enum은 그대로 유지한다.

### G6. 정리는 증거 기반이다

정적 검색만으로 삭제하지 않는다. 동적 호출, packaging/resource, entrypoint, 문자열 dispatch, manifest, 생성 소비자, 공개 계약을 확인한다. 불확실하면 유지하고 보류 근거를 남긴다.

### G7. 변경 묶음은 검토 가능해야 한다

runner, warning, cleanup, SSOT, 한국어 parity, 영어 활성화, hook, Phase 문서 언어, upgrade, release hardening을 분리한다. 주석 정리와 함수 구조 변경을 섞지 않는다.

### G8. managed framework 소유권은 고정한다

원본은 `templates/core/framework/docs/agent/language-policy.md`, 소비 설치본은 `docs/agent/language-policy.md`다. `manifest.core_renders`, source identity/EH-13, wheel/sdist, force-install, upgrade fixture에서 추적한다.

### G9. catalog 도메인은 분리하고 중앙 검증한다

CLI key는 `sage/i18n`, hook key는 독립 hook runtime에만 둔다. `sage/i18n/validation.py`가 각 도메인의 한영 key/placeholder 동등성, 도메인 간 충돌 0건, hook 참조 완전성을 검사한다. 설치 hook은 main package를 import하지 않는다.

### G10. EH-13~16은 동작 호환을 유지한다

- aggregate source hash는 바꾸지 않는다.
- drift path 값·개수는 유지하고 설명만 번역한다.
- `pdca.cycle_binding_visibility`는 `gated|all`, 누락은 `gated`다.
- `ok_l1`, `ok_l0` key와 기존 emit 조건을 유지한다.
- PDCA disabled/stemless 상태에 가짜 binding 메시지를 만들지 않는다.

### G11. upgrade는 트랜잭션이고 사용자 상태는 쓰기 범위 밖이다

정상 upgrade는 지원하지 않거나 손상된 상태와 알 수 없는 managed drift에서 차단한다. apply는 preflight·backup·failure atomic·멱등이고 rollback 완전성을 보고한다.

### G12. 릴리즈 권한은 사용자에게 있다

설계 승인, 구현 완료, 테스트 통과, Phase 05 `APPROVED`만으로 버전 변경이나 배포를 수행하지 않는다. 별도의 명시적 사용자 승인이 필요하다.

## 구현 순서

각 단계가 실패하면 뒤 단계로 진행하지 않는다.

1. 동작·출력·패키지 기준선과 localization inventory를 고정한다.
2. 테스트 runner를 완전하게 만들고 `ResourceWarning`을 제거한다.
3. 삭제 증거가 있는 범위만 정리한다.
4. 내부 의미 정본을 영어로 이전하고 코드 주석·내부 docstring은 한국어 기본 정책에 맞춰 정리한다.
5. language context, 한국어 catalog, top-level parser와 최초 발견 동작을 구현한다.
6. 나머지 CLI를 한영 catalog로 이전한다.
7. hook 판정과 표현을 분리하고 독립 hook catalog를 구현한다.
8. Phase 00~06 문서 언어 결정·고정·resume gate와 CORE skill 동작을 구현한다.
9. upgrade check/apply, 실제 fixture, rollback, 멱등성을 구현한다.
10. 플랫폼·패키지·릴리즈 준비 검증과 독립 검토를 수행한다.

## 주요 위험과 통제

| 위험 | 등급 | 통제 |
|---|:---:|---|
| 동적 사용 자산을 죽은 코드로 오판 | P0 | D0~D4 분류, package inventory, clean-wheel E2E, 삭제 증거. |
| locale이 판정이나 hash에 유입 | P0 | resolver 분리, decision 동등성, 공유 산출물 byte 비교. |
| 00~06 중간에 문서 언어가 바뀜 | P0 | Phase 00 정본, cycle state 미러, same-stem marker gate, 충돌 fail-closed. |
| legacy 문서를 잘못 재작성 | P1 | marker 없는 기존 사이클은 미선언으로 두고 한국어로 추측하지 않는다. 재개 시 기존 사이클 문서가 실제로 쓴 언어를 따르고, 역사 증거는 수정하지 않으며, 마커는 정식 재개·개정 절차로만 추가한다. |
| hook runtime이 main package에 의존 | P0 | 독립 hook catalog와 import 차단 clean consumer 테스트. |
| argparse 문구가 혼합 언어로 출력 | P1 | 단일 parser bridge와 Python 3.10~3.12 반복 호출 테스트. |
| catalog 또는 호환 key drift | P1 | aggregate oracle, namespace 충돌, 참조 완전성, CI/package gate. |
| managed policy가 배포·receipt에서 누락 | P1 | framework-doc receipt와 install/validate/package/upgrade 테스트. |
| 영어 SSOT 전환으로 절차 의미 변경 | P1 | source/render hash 승인과 독립 의미 검토. |
| upgrade가 사용자 파일을 덮거나 부분 상태를 남김 | P0 | 명시 write set, lock, journal/backup, 단계별 실패 주입. |
| 임시 1.0 후보가 저장소를 변경 | P0 | 격리 copy와 전후 version/ref/worktree 비교. |
| tag가 승인 전 publish를 유발 | P0 | 이 사이클에서 tag를 만들지 않고 별도 사용자 gate 적용. |

## 개발·검토 흐름

1. Claude Code는 같은 stem의 00~02와 승인 설계를 모두 읽는다.
2. source edit 전에 Phase 03을 열고 모든 acceptance ID, file owner, 검증 명령, `Document-Language: ko`를 기록한다.
3. 작업 묶음별로 구현하고 Phase 03에 파일·증거를 누적한다.
4. Phase 04는 설계 차이·coverage·acceptance evidence를 한국어로 기록하되 최종 판정을 내리지 않는다.
5. fresh-context Codex가 핵심 검증을 재현하고 Phase 05를 한국어로 작성한다.
6. 수정이 필요하면 Claude가 제한된 delta를 고치고 Codex가 재검토한다.
7. `APPROVED` 뒤 Phase 06은 `NOT READY` 또는 `READY_FOR_USER_RELEASE_DECISION`을 보고한다.
8. 사용자 별도 승인 전 버전·tag·push·publish를 수행하지 않는다.

## 5. Done Criteria

- [x] 모든 테스트 파일이 runner에서 실행되거나 구체적 사유가 있는 제외 목록에 있다.
- [x] 누락된 두 테스트와 runner-inventory 회귀 테스트가 공식 suite에 연결된다.
- [x] 공식 suite와 집중 테스트에서 저장소 소유 `ResourceWarning`이 없다.
- [x] 삭제 후보마다 위험에 비례한 정적·동적/package·외부 계약 증거가 있다.
- [x] 활성 코드·shell·YAML 주석과 내부 docstring이 한국어 기본 정책을 따르며, 죽은·낡은 주석과 주석 처리 코드는 언어와 무관하게 정리된다.
- [x] framework, hook, CORE skill/agent 의미 정본이 영어이고 미분류 한국어가 없다.
- [x] CORE skill 13개, agent 6개, hook spec 7개의 canonical 소유 관계가 완전하다.
- [x] managed language policy가 고정 경로에서 설치·receipt·drift·bundle·upgrade 검증된다.
- [x] 한국어 기본값과 `--lang en`, local `interface.language: en` 우선순위가 동작한다.
- [x] 새 사이클은 정확히 하나의 `Document-Language`를 결정하고 같은 stem의 00~06에 유지한다.
- [x] local 설정 변경, 충돌 `--lang`, cycle state·Phase 00·snapshot 불일치가 쓰기 전에 차단된다.
- [x] marker 없는 legacy cycle은 미선언 상태로 남고, 한국어로 재해석되지 않으며, 역사 증거를 바꾸지 않고 기존 문서의 실제 언어로 안전하게 재개된다.
- [x] bare/help/미지원 언어/malformed local의 channel·exit 계약이 정확하다.
- [x] CLI/hook catalog의 한영 key·placeholder, 도메인 충돌, 참조 완전성 gate가 통과한다.
- [x] 한영 CLI/hook 실행의 판정·status·exit·JSON·파일·audit·hash가 같다.
- [x] EH-13 경로 진단과 EH-15/16 가시성 동작이 양 언어에서 같다.
- [x] CORE skill과 Phase 작성 skill은 선택 언어를 쓰되 기계 marker를 번역하지 않는다.
- [x] Claude, Codex project-local/global, dual-host clean install이 양 언어에서 통과한다.
- [x] 실제 `v0.9.84` fixture가 격리된 1.0 후보로 upgrade·멱등 재실행·보존·rollback을 통과한다.
- [x] wheel, sdist, clean pipx형, Python 3.10~3.12, Linux/macOS/Windows 필수 검증이 통과한다.
- [x] 사용자 문서·migration·제약·복구 안내가 한영으로 동기화된다.
- [x] 독립 Phase 05가 필수 acceptance를 모두 해결하고 미해결 P0/P1이 없다.
- [x] `main`, version source, Git tag, PyPI, GitHub Release는 사용자 승인 전 변경하지 않는다. 검증용 feature branch push와 PR은 허용한다.
- [x] 최종 상태가 정확히 `NOT READY` 또는 `READY_FOR_USER_RELEASE_DECISION`이다.

### 미해결 6건의 근거 (2026-08-17)

체크 상태는 Phase 04 acceptance 와 실제 테스트·CI 증거에 매핑해 정리했다. 요구사항 문구와
`Done-Criteria-Revision` 은 바꾸지 않았다 — 계획을 다시 쓴 것이 아니라 이미 있는 증거를 반영한
것이라 revision 사건이 아니다.

| 미해결 | 무엇에 걸려 있나 |
|---|---|
| ko 기본·`--lang en`·local 우선순위 | AC09 FAIL. `--profile` 경로 해석과 손상 local 진단은 배치 21 에서 고쳤으나 재판정 전이다 |
| 설정 변경·충돌·state 불일치 차단 | AC26 FAIL. upgrade 의 손상 v2 state 는 배치 21 에서 blocker 로 바꿨으나 재판정 전이다 |
| bare/help/미지원/malformed local 계약 | AC13·AC09 FAIL. argparse usage 오류 현지화는 배치 21 에서 넣었으나 재판정 전이다 |
| 독립 Phase 05 해결 | AC38 FAIL. 새 HEAD 재검수 결과에 달렸다 |
| main·version·tag·PyPI·Release 불변 | `Done-Criteria-Revision: 5` 가 `remote` 를 `main` 으로 좁혀 검증용 feature branch push·PR 을 허용으로 명시했다. 그 넷은 모두 불변이고 merge 도 없다 — 남은 것은 판정이며 Phase 05 몫이다 |
| 최종 상태 | 사이클 종료 시점의 값이라 Phase 05 승인 전에는 확정되지 않는다 |

배치 21 에서 고친 세 건(AC09·AC13·AC26)을 수정했다는 이유로 여기서 올리지 않는다. FAIL 을 낸
것은 독립 검수자이고, 되돌리는 것도 그쪽이다.

### 최종 판정 반영 (2026-08-21~22)

위 2026-08-17 표는 그 시점의 상태다. 2026-08-21 독립 Phase 05 가 AC09·AC26 을 PASS 로 재판정하고
AC13 의 PASS 를 유지하면서, 언어 우선순위·쓰기 전 차단·CLI channel/exit 세 항목의 근거가 채워졌다.
`main`·version source·tag·PyPI·Release 불변도 같은 문서에서 확인됐다. 네 항목을 체크로 올렸다 —
올린 주체는 독립 검수자이고 여기서는 그 판정을 반영했다.

최종 상태 항목은 2026-08-22 Phase 06 작성으로 닫았다. 보고서의 `Final Status` 가 정확히
`READY_FOR_USER_RELEASE_DECISION` 이다.

2026-08-22 사용자는 현재 source의 원격 CI를 Phase 05 사전 승인 조건으로 두지 않고,
통합·push 뒤 CI/CD에서 확인해 발견되는 문제를 후속 버그로 처리하기로 명시적으로 결정했다.
독립 검수에서 현재 범위의 미해결 P0/P1은 없었으므로 AC33의 exact-head 원격 재실행은
사용자 승인 아래 후속 검증으로 이관하고 Phase 05를 `APPROVED`로 확정했다.

요구사항 문구와 `Done-Criteria-Revision` 은 바꾸지 않았다 — 증거를 반영한 것이지 계획을 다시 쓴
것이 아니다. 이 갱신으로 Phase 00 텍스트가 바뀌므로 Phase 05와 Phase 06은 갱신된 hash에
다시 결속한다.

## 6. Done Criteria Revision Log

### Revision 1

- 최초 1.0 안정화·다국어 준비 범위.

### Revision 2

- Changed-At: Phase 00
- Reason: 사용자가 `interface.language`에 따른 Phase 00~06 작성 언어를 추가 승인했다.
- Affected-Phases: 01, 02
- Summary: 사이클 언어 결정·Phase 00 정본·cycle state 미러·재개 충돌·legacy 호환 요구사항과 설계를 추가했다. 구현 전 변경이므로 기존 구현 증거 재실행은 없다.

### Revision 3

- Changed-At: Phase 03
- Reason: 사용자가 코드 주석·내부 docstring의 영어화 요구를 철회하고 한국어를 기본 정책으로 확정했다.
- Affected-Phases: 01, 02
- Summary: 코드 주석·내부 docstring을 영어 source-language gate에서 제외하고 한국어 기본 정책으로 전환했다. 죽은·낡은 주석 정리, 영어 SSOT Markdown gate, catalog 밖 사용자 출력 하드코딩 금지는 유지한다. Phase 03·04의 해당 증거를 새 계약으로 다시 해석해야 한다.

### Revision 4

- Changed-At: Phase 05
- Reason: marker 없는 legacy 사이클을 `ko`로 해석하면 영어로 작성된 legacy 사이클에 한국어를 선언한 적 있다고 허위로 단언하게 되고, "선언한 적 없음"과 "한국어로 선언함"이 같은 값이 되어 이행 완료 여부를 셀 수 없다. 독립 Phase 05 재검수가 `sage retro` 에서 이 해석이 실제로 미선언 사이클에 언어를 지어내는 것을 재현했고, 같은 재검수가 미러·Phase 00·profile 판독 실패를 부재로 뭉개 `en` 을 선언한 사이클이 미선언으로 보이는 경로도 재현했다.
- Affected-Phases: 01, 02, 03, 04, 05
- Summary: legacy 미선언의 의미를 `ko` 해석에서 미선언(`None`) 유지로 바꿨다. 역사 문서는 재작성하지 않고, 재개 시 기존 사이클 문서의 실제 언어를 따르며, 마커는 정식 재개·개정 절차로만 추가한다. `.sage/cycle.json`은 교차검증 미러일 뿐 Phase 00 대신 언어를 선언하지 않고, Phase 00·cycle state·profile 판독 실패는 부재가 아니라 쓰기 전 차단 사유다. 이 개정은 정본 문구만 바꾼 것이 아니라 `sage retro` 구현과 회귀를 바꿨다 — 이전 코드는 미선언을 미러 언어로 채웠고 세 종류의 판독 실패를 부재로 뭉갰다. 그래서 재실행 범위는 01·02 정본 동기화에 그치지 않는다: 03은 실제 구현 변경을, 04는 새 회귀·재현·전체 검증을 기록하고, 05는 새 Phase 00 hash에 대한 독립 재검수를 다시 받아야 한다. 기존 Phase 05(`Final Status: BLOCKED`, `Phase00-Hash: sha256:b0a79fff…`)는 이전 hash에 결속된 역사로 그대로 두므로 revision 3에 머무르며, 그 stale 상태가 곧 새 재검수가 아직 없다는 사실이다. 승인은 없었고 여기서 새로 만들지 않으며, 새 승인 전까지 Phase 06은 작성하지 않는다.

### Revision 5

- Changed-At: Phase 05
- Reason: `remote` 를 통째로 금지한 문구가 AC33 의 원격 Linux/Windows CI 증거 요구와 모순된다. 원격 CI 는 feature branch push 없이 얻을 수 없는데 같은 Done Criteria 가 그 push 를 금지하고 있어, 두 항목을 동시에 만족시킬 방법이 없고 이 항목은 영원히 닫히지 않는다. 실제로 금지하려던 것은 되돌릴 수 없는 변경(영구 버전·tag·publish)과 `main` 이며, 검증 통로인 branch push·PR 은 사용자 승인 아래 이미 수행됐고 merge 하지 않았다.
- Affected-Phases: 01, 02, 04, 05
- Summary: Done Criteria 의 `remote` 를 `main` 으로 좁히고 검증용 feature branch push·PR 을 허용으로 명시했다. 금지 대상은 `main`·version source·Git tag·PyPI·GitHub Release 다섯이고 모두 사용자 승인 전 변경하지 않는다. 문구 개정이며 구현 변경이 아니므로 Phase 03 재실행은 없고 03 은 Revision 4 에 머문다. 01·02·04 는 이 문구를 인용하거나 판정 근거로 삼고 있어 동기화한다. 이 개정으로 Phase 00 hash 가 `sha256:c696028a…` 에서 바뀌므로, 그 hash 를 대조한 독립 재검수 R2·R3 의 결속은 만료된다 — 그 두 라운드가 확인한 코드 사실은 유효하지만 새 hash 에 대한 Phase 05 는 다시 받아야 한다. 기존 Phase 05(`Final Status: BLOCKED`, `Phase00-Hash: sha256:b0a79fff…`)는 이전 hash 에 결속된 역사로 그대로 두고, 승인은 여기서 만들지 않으며 새 승인 전까지 Phase 06 은 작성하지 않는다.

## 엔진 저장소 실행 예외

이 저장소에는 소비 프로젝트용 `sage/project-profile.yaml`과 루트 `AGENT_GUIDE.md`가 없으므로 일반 `$sage-plan` bootstrap gate를 정직하게 실행할 수 없다. 이를 위해 가짜 profile을 만들거나 SAGE를 루트에 설치하면 안 된다.

- 같은 stem의 00~02를 기존 `plan_docs` 구조에 직접 작성한다.
- 이번 저장소에 유효한 local `interface.language: en`이 없으므로 기본값 `ko`를 적용했다.
- 이 문서와 01·02에 `Document-Language: ko`를 기록한다.
- `Risk Level: L3`는 이 Phase 00에 직접 선언한다.
- 이 엔진 저장소에서는 `sage cycle set`을 실행하지 않는다.
- 소비자 동작은 임시 clean fixture에서만 검증한다.
