# [기본 계획] Fast Cycle 진입 차단 해소와 명시 전환·조기 완료

Cycle-Stem: `sage-fast-cycle-usability-hardening`
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 2
Status: READY_FOR_USER_MERGE_DECISION

## 0. 사전 지식

| 구분 | 근거 | 핵심 내용 |
|---|---|---|
| 승인 설계 | `docs/superpowers/specs/2026-08-18-sage-fast-cycle-usability-hardening-design.md` | Fast Cycle 진입 차단 3건을 해소하고, 개발자의 명시 확인과 사유를 전제로 Standard→Fast 전환과 리뷰 조기 완료를 각각 독립 절차로 제공한다. 정본은 내부 위키 노트이고 이 파일은 사이클 실행용 고정 사본이다. |
| 사용자 결정 | 2026-08-18 착수 대화 | 다섯 기능을 한 사이클에서 검증하되 구현·커밋은 두 단계로 끊는다. A/B/C를 먼저 완료·커밋한 뒤 D/E로 넘어간다. |
| 선행 기능 | `v0.9.81` Fast Cycle | Fast Cycle은 게이트를 끄는 우회가 아니라 위험도와 검증 결과를 유지하며 문서·리뷰 비용을 줄이는 정식 절차다. |
| 구현 기준점 | `feat/sage-stabilization-localization@7375a4a` | 한영 catalog와 `upgrade`를 포함한 1.0 준비 작업 위에서 시작한다. 해당 브랜치에 변경이 생기면 pull 하여 반영한다. |
| 발견 환경 | 내부 프로젝트의 Windows 개발 환경 실사용 | 세 결함이 연쇄로 발생해 Fast Cycle 진입 자체가 불가능했다. 회사·업무 식별 정보는 내부 위키에만 두고 저장소 문서에는 일반화한다. |
| 결함 실측 | 2026-08-18 저장소 조사 | A는 `sage/commands/fast_cycle.py:95`, B는 `pre_implementation_gate_core.py:196`·`:299`·`:1447`, C는 `pre_implementation_gate_core.py:49`와 `runtime/hook_runtime.py:1280` 두 곳에 실재한다. `runtime/risk_declaration.py`는 아직 없다. |
| 검증 환경 경계 | `sage._resources.is_engine_source_tree` | 이 저장소는 엔진 소스 트리라 자기 게이트가 돌지 않는다. 세 결함은 이 저장소에서 재현되지 않으며 fixture와 격리 소비 프로젝트에서만 검증된다. |
| 후속 작업 경계 | 로드맵 `sage-operability-diagnostics` | 이번 사이클이 추가하는 BLOCK 메시지는 후속 진단 작업의 `Next:` 완전성 oracle 대상이 된다. 이번 사이클에서 진단 계약을 선취하지 않는다. |

## 1. 목표

이번 사이클은 Fast Cycle을 실제로 쓸 수 있는 상태로 만들고, 지금은 절차가 없어서 우회하거나 포기해야 했던 두 운영 상황에 정식 절차를 준다. 목표는 다음 세 가지다.

1. 정상 profile과 정상 문서를 가진 프로젝트가 Fast Cycle에 진입하지 못하는 세 결함을 제거한다.
2. Phase 00 Risk Level 선언 해석을 공용 계약으로 승격해 authoring·gate·authority가 같은 판정을 내리게 한다.
3. 진행 중 Standard Cycle의 Fast 전환과 리뷰 라운드 조기 완료를, 실제 위험도를 낮추지 않고 감사 가능한 상태 전이로 제공한다.

종료 상태는 정확히 다음 중 하나다.

- `NOT READY`: 필수 인수 항목이 하나 이상 해결되지 않았다.
- `READY_FOR_USER_MERGE_DECISION`: 구현과 검증은 통과했지만 커밋·머지·push·릴리즈는 수행하지 않았다.

## 2. 범위

### 2.1 포함

- Fast CLI가 profile을 검증할 때 `_root(args)`가 확정한 프로젝트 root를 `validate_profile()`까지 전달하는 수정.
- `sage validate`와 `sage fast-cycle open`의 동일 profile·root 경로 판정 일치.
- 미작성 pre-implementation phase 검사에서 phase 문서 전용 변경만 좁게 제외하는 교착 해소.
- pending Fast Plan 자체의 작성·복구 허용과, open 성공 전 소스 편집 BLOCK 유지.
- Phase 00 헤더 metadata 영역만 읽는 dependency-free Risk 선언 parser 신설.
- `pre_implementation_gate_core.py`의 후보 정규식·문서 전체 스캔과 `hook_runtime.py`의 두 번째 정규식을 그 공용 parser로 흡수.
- `missing`·`duplicate`·`malformed`·`placeholder` 구분과 줄 번호·원문 발췌 표시.
- profile의 `pdca.fast_cycle.standard_transition`과 `pdca.review_loop.early_completion` opt-in 계약.
- 문서를 쓰지 않는 `sage fast-cycle convert`와 `.sage/fast_cycle.jsonl`의 `fast_convert` opener.
- 전환 시점 00~04의 경로·raw-byte SHA-256·크기 provenance와 review 시점 delta 기록.
- `review-loop round`의 `--survived-by-severity` 영수증과 합계 검산.
- `review-loop close`의 `USER_AUTHORIZED_EARLY` 단일 terminal 전이.
- Phase 05·06의 `Review-Assurance`·`Review-Close-Reason`·`Review-Rounds`·`Residual-Findings` metadata와 로컬 gate 검증.
- Fresh Fast와 Converted Fast, 정상 close와 조기 close를 구분하는 `sage/ci_authority.py` evidence 판정.
- Fast/standard cycle·plan·team·review CORE 스킬과 `sage-init`·`sage-profile-modify` 대화.
- Obsidian 파생 dashboard 갱신과 vault 실패의 WARN 처리.
- README·CLI reference·profile reference·troubleshooting 한영 문서.
- 추적 자산 변경 후 manifest 재스탬프.

### 2.2 제외

- 일반 gate override의 의미 변경과 acceptance waiver·review exception 통합.
- 리뷰 0회 승인, profile 차단 severity·architecture escalation·FAIL·감사 손상의 사용자 확인 통과.
- Obsidian을 권한 정본으로 사용하는 것과 원격 사용자 신원 증명.
- Standard↔Fast 자동 전환, profile만 보고 하는 자동 선택, Fast→Standard 역전환.
- CLI와 hook의 전역 root 통합 및 J-3 `K1` 재개.
- `sage/ci_authority.py`의 bundle root를 checkout root로 단순 교체하는 수정. tree-aware profile 검증은 별도 작업이다.
- 후속 `sage-operability-diagnostics`가 소유하는 공통 진단 계약, `sage status`, `sage explain`, 전체 BLOCK `Next:` oracle.
- 커밋·머지·push·태그·릴리즈.

## 3. 영향 분석

| 영역 | 변경 | 고정 경계 |
|---|---|---|
| Fast CLI | profile 검증 root 전달, `convert` 하위명령, 전환 preflight | 기존 open/review/close/show의 성공 판정과 exit는 유지한다. root 탐색기를 새로 만들지 않는다. |
| review loop CLI | severity 영수증 인자, `USER_AUTHORIZED_EARLY` close | 정상 `CONVERGED|DRY` 경로의 판정·exit·감사 형식은 불변이다. |
| pre-implementation gate | phase 전용 예외, 공용 risk parser 사용, converted run 인식, 06 보증 검증 | `all()` 의미론을 유지한다. 소스가 섞인 변경에 예외를 주지 않는다. desktop block·write guard·cycle binding은 그대로다. |
| hook runtime | 자체 Risk 정규식 제거 후 공용 parser 사용 | 설치 hook runtime은 main `sage` package를 import하지 않는다. `message_key`와 evidence 계약은 유지한다. |
| 감사 writer | `fast_convert` opener, severity 영수증, 조기 terminal metadata | 기존 strict hash-chain·seq·OS lock·부분쓰기 rollback을 그대로 적용한다. 과거 레코드를 재작성하지 않는다. |
| profile | 두 기능의 opt-in 필드와 schema·validator·compiler | 기본값은 `false`다. local profile에서 활성화하거나 하한을 낮출 수 없다. profile hash 계약은 기존 규칙을 따른다. |
| Phase 05/06 | 보증 수준 metadata | 최종 판정 토큰 `APPROVED`는 호환을 위해 유지한다. |
| CORE 스킬 | 전환·조기 완료 확인 화면과 CLI 호출 | 스킬은 사용자의 실제 답변만 전달한다. 확인을 추론하거나 대신 답하지 않는다. |
| Obsidian | Fast Cycle·Review Loop dashboard | vault는 JSONL에서 재생성 가능해야 하며 권한 판단에 쓰지 않는다. |

## 4. 전역 불변 조건

### G1. 실제 위험도는 낮추지 않는다

전환의 `--level`은 Fast 리뷰 정책 선택일 뿐이다. Phase 00 공용 parser가 읽은 실제 Risk Level을 감사에 고정하며, 어떤 사용자 확인도 실제 위험도를 덮어쓰지 못한다.

### G2. 사용자 확인은 추론하지 않는다

명시적 CLI 입력 없이는 상태가 바뀌지 않는다. 확인 토큰·사유·승인자 중 하나라도 없으면 append 전에 exit 2이며 파일과 감사 로그를 쓰지 않는다. 사유는 비어 있지 않은 한 줄이고 원문을 감사에 남긴다.

### G3. 두 승인은 서로를 대체하지 않는다

Standard→Fast 전환 승인은 리뷰 조기 완료 권한을 포함하지 않고, 반대도 마찬가지다. 두 기능은 독립된 profile opt-in, 독립된 확인 토큰, 독립된 감사 이벤트를 가진다.

### G4. 차단해야 할 것은 확인으로 통과되지 않는다

리뷰 0라운드, profile `severity_block` 대상 미해결 finding, architecture escalation, 필수 검증 실패, Done Criteria 미해결, acceptance FAIL, waiver 없는 필수 NOT TESTED, 감사 손상은 사용자 승인으로도 통과하지 못한다.

### G5. 문서를 쓰지 않는 전환이다

전환은 기존 Standard 00~04를 삭제·이동·병합·재작성하지 않고 composite 00을 만들지 않으며 변환 metadata를 문서에 삽입하지 않는다. 전환의 정본은 `.sage/fast_cycle.jsonl`의 `fast_convert` opener 하나다. append 실패는 전환 전 상태를 그대로 유지한다.

### G6. 예외는 phase 문서 전용 변경에만 준다

pre-implementation 예외는 모든 변경 대상이 선언된 exact stem의 phase 문서일 때만 성립한다. 소스·설정·생성 산출물이 한 도구 호출에 섞이면 예외가 없다. `any()` 기반 완화를 도입하지 않는다.

### G7. pending은 소스 편집을 열지 않는다

`Fast-Audit-Run: pending`은 pending Fast Plan 자체의 작성·복구만 허용한다. `sage fast-cycle open` 성공 전 소스 편집은 계속 BLOCK이며, open 실패 메시지는 원인과 재실행 명령과 Standard 복구 절차를 함께 표시한다.

### G8. Risk 선언 정본은 하나이고 소비자는 전부 같은 parser를 쓴다

정본은 exact stem으로 선택된 Phase 00의 헤더 metadata 영역이다. 헤더 영역은 문서 시작부터 첫 H2 이상 heading 전까지이며 H1 제목은 허용한다. fenced code, blockquote, 들여쓴 코드, 인라인 예시, 첫 H2 뒤 본문은 후보가 아니다. 표준 Phase 00, Fresh Fast composite 00, pre-implementation gate, report/write-back tier 판정, server authority가 같은 dependency-free parser를 사용한다. 저장소에 Risk 선언을 자체 해석하는 두 번째 정규식을 남기지 않는다.

### G9. 감사 보증 수준은 올려 보이지 않는다

기존 strict hash-chain·seq·OS lock·부분쓰기 rollback을 그대로 적용하고, 과거 레코드를 재작성하거나 rehash하지 않는다. 감사 기록 실패·손상·결속 불일치는 fail-closed다.

### G10. 조기 완료는 정상 수렴을 대체하지 않는다

첫 라운드에서 `survived=0`이면 기존 `CONVERGED`로 즉시 승인되며 조기 완료 기능을 쓰지 않고 `REDUCED` 경고도 붙이지 않는다. `next=STOP|CONVERGED` 상태에서 조기 종료 명령은 거부하고 정상 close를 안내한다. `max_iterations`는 최소 요구 횟수가 아니라 상한이다.

### G11. 보증 저하는 감춰지지 않는다

조기 완료의 최종 판정 토큰은 호환을 위해 `APPROVED`를 유지하되, Phase 05·06에 보증 수준·종료 사유·라운드 수·잔여 finding 심각도 집계를 정확히 1개씩 기록한다. 로컬 gate·dashboard·authority·후속 보고가 일반 승인과 조기 완료 승인을 구분한다. `P2/P3` 같은 비차단 잔여 finding을 사라진 것으로 취급하지 않는다.

### G12. Obsidian은 파생 뷰다

감사 정본은 항상 `.sage`에 남는다. vault 산출물은 JSONL에서 재생성 가능해야 하고 권한 판단에 쓰이지 않으며, 자동 dashboard 실패는 WARN이고 이미 성공한 감사 close를 되돌리지 않는다.

### G13. 로컬 확인은 로컬 확인이다

승인자 기록의 attestation은 `self_asserted_local`이다. 원격 신원 증명이나 조직 승인 시스템으로 과장해 표기하지 않는다.

### G14. 이 저장소에서 안 막히는 것은 증거가 아니다

이 저장소는 엔진 소스 트리라 자기 게이트가 실행되지 않는다. 세 결함의 해소는 fixture와 격리 wheel 소비 프로젝트에서 재현·검증하며, "로컬에서 더 이상 막히지 않는다"를 수정 증거로 사용하지 않는다.

### G15. 범위 밖 root 문제를 열지 않는다

`sage/ci_authority.py`의 bundle root를 checkout root로 단순 교체하지 않는다. base commit에는 있으나 현재 checkout에서 삭제된 파일을 오판하기 때문이다. tree-aware profile 검증은 protected authority 활성화 전 별도 작업이 소유한다. CLI와 hook의 전역 root 통합과 J-3 `K1`도 재개하지 않는다.

## 구현 순서

두 단계로 끊는다. 1~3을 완료하고 커밋한 뒤 4~7로 넘어간다. 각 단계가 실패하면 뒤 단계로 진행하지 않는다.

**1단계 — 진입 차단 해소 (커밋 지점)**

1. A/B/C 최소 재현을 회귀 테스트로 먼저 고정한다.
2. working-tree root 전달과 phase 전용 교착을 각각 독립적으로 해결한다.
3. 공용 Phase 00 Risk parser를 도입하고 gate·hook runtime·report/write-back·authority의 parity를 고정한다.

여기서 전체 suite와 wheel smoke를 돌리고 manifest를 재스탬프한 뒤 사용자에게 보고한다. 커밋은 사용자 승인 후 수행한다.

**2단계 — 명시 전환과 조기 완료**

4. profile에 두 기능의 opt-in 계약을 추가한다.
5. 문서를 쓰지 않는 `fast_convert` 상태 전이와 Fresh/Converted 공통 요약을 구현한다.
6. Loop round severity 영수증과 `USER_AUTHORIZED_EARLY` 단일 terminal 전이를 구현한다.
7. Phase 05/06 metadata, 로컬 gate, server authority를 같은 판정 helper에 결속한다.

**공통 마무리**

8. Fast/standard 스킬과 `sage-init`·`sage-profile-modify` 대화를 갱신한다.
9. Obsidian 파생 dashboard와 한영 사용자 문서를 갱신한다.
10. manifest 재스탬프, 전체 suite, wheel, Windows 회귀, 독립 리뷰를 수행한다.

## 주요 위험과 통제

| 위험 | 등급 | 통제 |
|---|:---:|---|
| root 수정이 J-3 전역 root 문제를 다시 엶 | P0 | 같은 프로세스 내 데이터 전달로 범위를 한정하고, hook root resolver·cycle declaration 테스트 무변경 PASS를 요구한다. |
| authority root를 함께 고쳐 과거 revision profile을 오판 | P0 | 이번 사이클에서 `ci_authority.py` 인자를 교체하지 않는다. base/head fixture가 각 revision 파일 집합만 참조함을 테스트로 고정한다. |
| phase 예외가 소스 편집 우회로 확대 | P0 | `all()` 의미론 유지, 문서와 소스 혼합 변경 차단 테스트, `any()` 도입 시 실패하는 mutation 이빨. |
| pending 완화가 감사 미개시 우회를 만듦 | P0 | pending은 Fast Plan 작성·복구만 허용하고 소스 편집 BLOCK을 유지하는 회귀 테스트. |
| 공용 parser 전환 중 소비자별 판정이 갈림 | P0 | 같은 Phase 00 fixture에 대해 gate·Fast·report/write-back·authority가 같은 판정을 내는 parity 테스트와 두 번째 정규식 잔존 검사. |
| 전환이 실제 위험도를 낮추는 경로가 됨 | P0 | 실제 risk를 감사에 고정하고 `--level`과 분리, 실제 L1 전환 거부, 확인 토큰 없는 전환 거부. |
| 조기 완료가 차단 finding을 통과시킴 | P0 | severity 영수증 합계 검산, `severity_block` 미해결 시 거부, architecture·FAIL·Done Criteria 미해결 거부. |
| 감사 append 부분 성공으로 상태가 갈라짐 | P0 | 단일 OS lock 임계구역, append 실패 시 write 0건, 동시 전환에서 단일 run 생성 테스트. |
| 조기 close 이후 변경이 stale 승인을 남김 | P1 | Phase 00 hash·Done Criteria revision·plan hash·cycle stem·profile 변경 시 재리뷰 요구와 중복 close 차단. |
| 새 BLOCK 메시지가 한영 catalog에서 갈림 | P1 | key·placeholder 동등성 gate와 도메인 충돌 0건 검사. |
| 이 저장소에서 재현되지 않아 수정을 오판 | P1 | fixture와 격리 wheel 소비 프로젝트 검증을 필수로 하고 로컬 무증상을 증거로 인정하지 않는다. |
| vault 실패가 감사 성공을 되돌림 | P1 | dashboard 실패는 WARN이고 core close를 rollback하지 않음을 테스트로 고정한다. |

## 개발·검토 흐름

1. Claude Code는 같은 stem의 00~02와 승인 설계를 모두 읽는다.
2. source edit 전에 Phase 03을 열고 모든 acceptance ID, file owner, 검증 명령, `Document-Language: ko`를 기록한다.
3. 1단계(A/B/C)를 구현하고 Phase 03에 파일·증거를 누적한 뒤 전체 검증을 돌려 사용자에게 보고한다. 커밋은 사용자 승인 후 수행한다.
4. 2단계(D/E)를 같은 방식으로 구현하고 Phase 03에 이어 기록한다.
5. Phase 04는 설계 차이·coverage·acceptance evidence를 한국어로 기록하되 최종 판정을 내리지 않는다.
6. fresh-context Codex가 핵심 검증을 재현하고 Phase 05를 한국어로 작성한다. 독립 리뷰는 최대 3라운드이며 각 지적은 실제 재현 후 수용 여부를 결정한다.
7. `APPROVED` 뒤 Phase 06은 `NOT READY` 또는 `READY_FOR_USER_MERGE_DECISION`을 보고한다.
8. 사용자 별도 승인 전 커밋·머지·push·태그·릴리즈를 수행하지 않는다.

## 5. Done Criteria

- [x] 프로젝트 상대 `governance_docs`를 가진 fixture에서 `sage validate`와 `sage fast-cycle open`이 같은 경로 판정을 내린다.
- [x] `--root` 명시값과 자동 탐색값이 검증·문서 선택·감사 경로에서 동일하다.
- [x] Fast profile 검증에 `_resources.sage_root()`를 되돌리는 mutation이 테스트로 실패한다.
- [x] hook root resolver와 cycle declaration 테스트가 무변경으로 PASS한다.
- [x] `ci_authority.py`의 root 인자를 이번 사이클에서 교체하지 않았고, base/head fixture가 각 revision 파일 집합만 참조한다.
- [x] 선언된 exact stem의 phase 문서 00·01·02·03 각각의 단독 생성이 허용된다.
- [x] phase 문서와 소스가 섞인 변경에는 예외가 없고, 다른 stem 문서와 ambiguous 문서는 차단된다.
- [x] pending Fast Plan의 작성·복구는 허용되고 `sage fast-cycle open` 성공 전 소스 편집은 BLOCK이다.
- [x] `sage fast-cycle open` 실패 메시지가 원인, 재실행 명령, Standard 복구 절차를 함께 표시한다.
- [x] Phase 00 헤더 metadata 영역만 읽는 dependency-free Risk parser가 존재하고 설명문·인라인 코드·인용문·첫 H2 뒤 본문의 `Risk Level`을 무시한다.
- [x] 중복·placeholder·malformed·missing이 구분되고 줄 번호와 원문 발췌가 표시된다.
- [x] gate, Fast, report/write-back, authority가 같은 Phase 00 fixture에 같은 판정을 내린다.
- [x] 저장소에 Risk 선언을 자체 해석하는 두 번째 정규식이 남아 있지 않다.
- [x] `standard_transition`과 `early_completion`이 shared profile 기본 `false`이고 local profile에서 활성화하거나 하한을 낮출 수 없다.
- [x] `minimum_completed_rounds`의 엔진 하한이 1이며 profile은 상향만 가능하다.
- [x] 확인 토큰·사유·승인자·level·lens 중 하나라도 없으면 전환이 exit 2이고 파일·감사 write가 0건이다.
- [x] 완결 cycle, active Fast 충돌, 손상 audit, 실제 L1은 전환을 차단한다.
- [x] 전환 전후 원본 00~04 바이트가 동일하고 composite 문서가 생성되지 않는다.
- [x] `fast_convert`가 00~04의 경로·SHA-256·크기와 `--current-phase`, Done Criteria revision을 기록한다.
- [x] 전환 후 Phase 04 변경이 허용되고 review snapshot이 delta를 기록한다.
- [x] 감사 append 실패 시 문서·상태 write가 0건이고, 동시 전환에서 단일 run만 생성된다.
- [x] Fresh `fast_open`과 Converted `fast_convert`가 혼동되지 않고 이후 review·close를 공유한다.
- [x] 전환 승인이 리뷰 조기 완료 확인으로 오용되지 않는다.
- [x] `review-loop round`가 `--survived-by-severity`를 기록하고 합계가 `survived`와 정확히 일치하지 않으면 거부한다.
- [x] severity 영수증이 없는 레거시 run은 조기 완료에 사용할 수 없으나 정상 `CONVERGED|DRY`에는 계속 쓸 수 있다.
- [x] 리뷰 0라운드, `severity_block` 미해결, architecture escalation, Done Criteria 미해결, acceptance FAIL, exact waiver 없는 필수 NOT TESTED, 감사 손상, 결속 불일치가 조기 완료를 차단하고 append는 0건이다.
- [x] acceptance 판정이 Phase 06 리포트 게이트와 같은 정책·같은 파서를 쓰고, `verification.acceptance`를 쓰지 않는 프로젝트에는 없던 검사가 켜지지 않는다.
- [x] 필수 검증 실패(FR-E05a)와 05 이후 재리뷰(FR-E05b)가 엔진 차단 대상이 아니라는 사실이 스킬·사용자 문서·Phase 04 잔여에 명시돼 있다.
- [x] `next=STOP|CONVERGED` 상태에서 조기 종료가 거부되고 정상 close가 안내된다.
- [x] `loop_close`가 run당 한 번만 append되며 조기 close 이후 round·중복 close·교차 cycle 사용이 차단된다.
- [x] loop close append 실패 시 run이 계속 active이고 Phase 06이 차단된다.
- [x] Phase 05·06에 보증 수준·종료 사유·라운드 수·잔여 finding 집계가 정확히 1개씩 기록되고, metadata와 terminal audit이 서로 없거나 다르면 차단된다.
- [x] 일반 정상 1라운드 `CONVERGED`와 상한까지 진행한 `APPROVED` 경로에 회귀가 없다.
- [x] 새 사용자 노출 문구의 한영 catalog key·placeholder가 일치하고 도메인 충돌이 0건이다.
- [x] vault 미설정은 N/A이고 vault 쓰기 실패는 WARN이며 core 감사 close를 되돌리지 않는다.
- [x] vault dashboard를 JSONL에서 재생성할 수 있고 vault 내용을 변조해도 gate 판정이 불변이다.
- [x] `run-all.sh`가 none·Claude·Codex 환경에서 통과하고 양 host 실제 adapter subprocess 회귀가 통과한다.
- [x] `sage validate --kind all --check --schema`가 `STALE 0`으로 통과한다.
- [x] clean wheel install·generate·validate·CLI smoke와 Windows 네이티브 경로·lock 분기가 통과한다.
- [x] `git diff --check`가 통과하고 한영 문서가 미러 상태다.
- [x] manifest와 hook runtime hash가 current다.
- [x] 세 결함의 해소가 fixture와 격리 소비 프로젝트에서 재현·검증되었고, 로컬 무증상을 증거로 쓰지 않았다.

## 6. Done Criteria Revision Log

### Revision 2

- Changed-At: Phase 05
- Reason: FR-E05가 한 줄에 두 층의 책임을 적었다. 조기 완료 경로가 막을 수 있는 상태와, 엔진이 읽을 수 있는 근거 자체가 없는 상태를 구분하지 않았다.
- Affected-Phases: 01, 02, 03, 04, 05
- Summary: acceptance FAIL과 exact waiver 없는 필수 NOT TESTED를 조기 완료 차단 대상으로 구현하고, 필수 build/test/lint 실패는 FR-E05a(에이전트 의무), 05 이후 재리뷰는 FR-E05b(06 게이트·권위 책임)로 분리했다.

필수 검증 결과는 `scripts/verify-changes.sh`가 실행하고 Phase 03 산문에만 남는다. 프로필 `verification` 블록에서 엔진이 읽는 것은 `acceptance` 하위뿐이라, "필수 검증이 실패했다"를 가리키는 기계 판독 영수증이 저장소 어디에도 없다. 영수증 계약을 새로 만드는 것은 이 사이클의 범위 밖이므로, 그 상태를 막는 책임을 엔진이 아닌 에이전트에게 명시적으로 둔다 — 없는 검사를 요구사항이 있다고 적어 두는 것보다, 어디가 사람의 책임인지 적어 두는 편이 사후 판별에 낫다.

05 이후 재리뷰는 close 시점에 성립할 수 없다. Phase 05는 loop가 닫힌 **뒤**에 작성되므로 조기 close가 볼 수 있는 05 상태가 없다.

이 상태를 실제로 막는 층은 무엇이 바뀌었느냐에 따라 다르다. **계획 문서**가 바뀌면 `Phase00-Hash`와 `Done-Criteria-Revision` 대조가 06과 서버 권위 양쪽에서 잡는다. **소스만** 바뀌면 둘 다 그대로이므로 이 축은 아무것도 잡지 못한다 — 로컬 06 게이트는 문서를 결속하지 실행 코드를 결속하지 않아 소스 전용 변경을 탐지하지 못한다. 남는 차단 근거는 서버 권위 하나다: `ci_authority.evaluate`가 요구하는 attestation은 `diff_sha256`·`head_sha`에 정확히 묶여 있어, 05 이후 소스가 바뀌면 diff가 달라져 그 attestation이 더는 검증되지 않는다.

즉 소스 전용 변경의 재리뷰 강제는 **원격 권위에만 있다**. 서버 권위를 쓰지 않는 프로젝트에서는 05 이후 소스를 고쳐도 로컬 게이트가 통과시킨다.
