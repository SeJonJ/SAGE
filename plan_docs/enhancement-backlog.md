# SAGE Enhancement 백로그

- SAGE 개발 중 확인된 이슈들로 당장 개발해야하는 내용들은 아니지만, 추후 개발 필요시 참고한다.
- 각 항목 = 배경 · 문제 · 접근 · 규모/위험 · 트리거 · 상태. 즉시 필요 아님 → 트리거 충족 시 착수.

## 코드 검증 · 우선순위 (2026-07-28)

전 항목 코드 재대조 완료(허위/과장 없음, 상태 그대로 유효).

2026-08-04 기준 **EH-1~EH-13 중 8건 완료·5건 보류**(완료 EH-1·2·3·5·6·7·9·12 / 보류 EH-4·8·10·11·13).
EH-8·EH-10·EH-11 은 각각 §10-g·§10-i·§10-j 에서 범위 경계로 분리된 항목이고, EH-12 는 §10-j-1 의
Phase 05 독립 리뷰에서 나와 2026-08-04 에 완료(미릴리즈)했다. EH-13 은 그 사이클에서 나왔다. EH-11 은 9개 하위 중 5개(J-4·J-5·J-6·J-8·J-9)를 `v0.9.78` 로 냈고
결속 본체(J-1·J-2·J-3)와 J-7 이 남아 보류로 유지한다.

- **EH-1·EH-2**: 완료 확인 — 추가 작업 불필요. (EH-1: `sage/commands/generate.py` roster kind + `test_gen_roster.py` /
  EH-2: `output_contract_check.py` `_DEFAULT_MARKERS` 중립화 + 주입 파라미터, 코드 상 실재)
- **EH-6 완료 확인**: SAGE-FB-05로 global/project-local 명시 선택, receipt, duplicate 진단, onboarding,
  transaction rollback, shared global lock까지 구현·검증했다.
- **완료 2건 + 보류 1건**:
  1. **EH-5 → 로드맵 §10-c 완료** — `_cycle_risk` 의 선언값 `max()`는 2026-07-18 하드닝에서 이미
     구현됐다. 남은 실제 결함은 Phase 00 선언 미기입 통과와, 현재 변경의 글롭/내용 감지 tier가 Phase 00보다 높아도
     durable tier 상향을 강제하지 않는 점이었다. 별도 ledger 없이 pre-write에서 Phase 00 선행 상향을
     강제하는 방식으로 구현했다.
  2. **EH-3 → 로드맵 §10-g 완료** — `loop_audit` run별 strict chain을 중심으로 report gate,
     CLI 오류 계약, hook manifest까지 함께 변경했다. 나머지 감사 3종은 EH-8로 분리했다.
  3. **EH-4** — sage-review·PostToolUse·Stop 게이트·profile_validate 다수 컴포넌트 동시 변경(대공사). 남은 우회가
     "과거 checked run_id 정확 복붙"뿐인 좁은 구멍이라 실이익 대비 비용 최대 — 트리거 충족 전 보류 유지.

---

## EH-1 — 동적 컴포넌트 파생 roster (F2 옵션 2)

- **배경**: F2(team roster 역할명 비중립: backend/frontend)는 **옵션 1(중립 rename)** 로 해소 —
  CORE 가 `implementer-a`/`implementer-b` 2개 고정, 컴포넌트 매핑은 `profile.team.core.*.owns` 가 담당.
- **문제(옵션 1의 한계)**: implementer 에이전트가 **2개 고정**. 컴포넌트 1개면 1개가 비고, 3개 이상이면
  한 에이전트가 여러 컴포넌트를 owns 하거나 `team.extensions` 로 수동 추가해야 함 — 컴포넌트 수와 roster 가 불일치.
- **접근(옵션 2 = 진짜 일반화)**: implementer 에이전트를 `profile.components` 개수·id 에 맞춰 **동적 생성**.
  - install-time 고정 에이전트 파일 배포 → **generate-time 에 profile.components 기반 렌더**로 이전.
  - 컴포넌트 id 별 implementer 스펙을 중립 템플릿에서 생성(예: components=[core, ui] → `core`·`ui` 에이전트).
  - leader/qa/reviewer/convention-checker 는 함수 역할이라 고정 유지.
- **규모/위험**: **중대**. install→generate 아키텍처 변경(에이전트 스펙 생성 경로 신설),
  manifest 에이전트 등록·conformance·reverse_extract 연동 재검토 필요.
- **트리거**: 컴포넌트 수가 2와 크게 다른 인스턴스가 등장 / roster-as-config 를 본격 일반화할 때.
- **상태**: ✅ **완료**(2026-06-18, 로드맵 1단계①). `sage generate --kind roster` 신설 — profile.components →
  `implementer-<comp>` spec 결정론 scaffold(접두 명명=함수역할 충돌 회피, 빈 components=고정 implementer-a/b 폴백,
  create-only=손편집 보존). claims/render/manifest 등록은 기존 interpretive agent 파이프라인이 처리(잘 격리된 추가 경로 —
  "중대" cross-cutting 재작성 회피). test_gen_roster(run-all step30, 7케이스) + 변이 teeth. leader/qa/reviewer/convention-checker 고정 유지.

---

## EH-2 — output_contract 마커 profile 주입화 (독립성)

- **배경**: F7(stop 정책 배선) 중 발견 — `policies/output_contract_check.py._MARKERS` 에
  스택 토큰(`backend`/`frontend`/`gradlew` 등)이 하드코딩됨 = 제약 #2(엔진 도메인값 0) 위반.
- **영향**: 현재 output_contract 는 **codex-only** 배선이라 영향 제한적이나, 비-웹 codex-host 인스턴스에서
  마커가 부정확. claude 미적용(F7 결정)이라 즉시 위험은 낮음.
- **접근**: `_MARKERS` 를 profile 주입(예: `profile.output_contract.markers`)으로 빼고 기본값은 중립화.
- **규모/위험**: 소~중. 정책 모듈 + codex stop 어댑터 + 테스트.
- **트리거**: output_contract 를 CORE 승격하거나 비-웹 codex-host 인스턴스 적용 시.
- **상태**: ✅ **완료**(2026-06-18, 로드맵 1단계②). `_MARKERS`→`_DEFAULT_MARKERS` 중립화(backend/frontend/desktop/gradlew
  제거), `check(..., markers=None)` profile 주입 파라미터 신설, io_codex 가 `profile.output_contract.markers` 주입.
  임계 `hit≥(마커수-1)` 일반화(기본 5→4). profile 템플릿 `output_contract.markers` 안내. test 신규(중립성+주입+폴백) + 변이 teeth(스택토큰 재주입→FAIL).

---

## EH-3 — loop_audit run별 strict hash-chain 자기검증

- **배경**: `scripts/sage_harness/hooks/runtime/loop_audit.py` 의 `_next_seq` 는 seq 연속성 검사가
  *수기 append·순서 뒤바뀜·누락* 같은 게으른 우회를 잡는 **anti-lazy-bypass sanity** 검사이지
  위변조 내성이 아님을 스스로 자인한다(seq = 레코드 수 → 파일을 읽어 다음 정수를 맞춰 append 하면 통과).
- **문제**: 감사 로그(`.sage/loop_audit.jsonl`)가 "위변조 방지"로 오인될 수 있다. 경계는 문서로 명시했으나
  (`docs/ARCHITECTURE.md` 신뢰 경계 · README), 현재는 seq 연속성 외에 레코드 내용의 자기검증 수단이 없다.
- **접근(§10-g locked)**: run별 immediate predecessor만 허용하는 **strict hash-chain**을 적용한다.
  각 신규 레코드는 `prev_hash`와 자기 자신을 검증하는 `record_hash`를 함께 저장하고, stamp+append를
  크로스플랫폼 프로세스 잠금 안에서 수행한다. `audit_summary.runs[run_id].chain_ok`를 실제 report gate와
  `integrity_issues()`가 소비하며, 기존 레코드는 재작성하지 않고 legacy tri-state로 유지한다.
- **규모/위험**: 중. `loop_audit` 스키마/잠금/검증 + report gate 배선 + CLI 오류 계약 + 하위호환.
- **트리거**: Git 이력 대조 전에도 Loop A 레코드의 우발적·단순 소급 변경을 기계적으로 판별하고,
  손상된 run이 report gate의 승인 증거로 쓰이지 않게 할 필요가 생길 때. 적대적 host나 규제 수준 보장은
  서명·외부 witness가 필요한 별도 범위다.
- **상태**: ✅ **로드맵 §10-g 완료(2026-07-30, v0.9.75)**. 정본 설계:
  `plan_docs/00-base_plan/sage-loop-audit-strict-hash-chain.md`. run별 strict chain, OS 소유 lock,
  손상 줄 fail-closed, terminal-newline 없는 정상 JSONL append 복구, 실제 report gate 배선과 회귀 테스트를
  구현했다. 교차 리뷰 2라운드에서 나온 개행 결합 결함은 단일 write separator로 닫고 회귀로 박제했으며,
  run 전체 체인 필드 제거 downgrade는 레코드 밖 provenance가 필요한 범위 밖 경계로 설계·문서·테스트에
  명시했다. 해시 전체 재계산에 대한 tamper-resistance는 제공하지 않으며, Git 이력은 외부 검토 앵커로 남는다.

---

## EH-4 — cycle-binding ledger (retro 게이트 잔여 우회 봉쇄)

- **배경**: retro 게이트 결정론 강제(v0.9.40)에서 06↔사이클 결속을 **06 자기선언**(`Loop-Run: <run_id>`)으로
  재설계하며 신뢰 경계가 05(리뷰어 작성)→06(host 작성)로 이동했다. Stop 훅은 06 이 선언한 run_id 를 읽어 검증한다.
- **문제(좁은 잔여 우회)**: 06 이 **다른 사이클의 실재+checked+approved** run_id 를 정확히 복붙하면 Stop 이
  그 run 만 보고 통과 → 이번 사이클 retro 미실행이 새어나간다. 오타·지어낸 id·미선언·상충은 전부
  fail-closed BLOCK 이라, **유일 우회는 "과거 checked run_id 정확 복붙"이라는 좁은 경로** 하나뿐.
- **접근**: **cycle-binding ledger 서브시스템** — sage-review(신뢰 경로)가
  `{cycle_id, canonical 06 경로, canonical 05 경로, run_id}` 유일 결속을 영구 기록(`_doc_match` recent-fallback
  제거, 0/2개↑=실패) → 쓰기 성공 **PostToolUse** 에서 `session_id`+operation id 로 확정 → Stop 은 이번 세션
  확정 결속만 소비. 추가: coupling(`retro enforce ⇒ review_loop.enabled`)을 profile_validate **FAIL** 로 강제.
- **규모/위험**: **중대**. sage-review·PostToolUse 어댑터·Stop 게이트·profile_validate 다수 컴포넌트 대공사.
- **트리거**: retro 게이트 우회가 실제 관측되거나 "정직한 host" 전제가 바뀔 때. **현 위협모델상 낮은 긴급도**
  (남은 우회가 좁고, 나머지 실패모드는 이미 BLOCK).
- **상태**: 🕗 **defer(2026-07-11, 유저 승인 "Option 1 로 진행")**. codex R2/R3 파생. 정본 vault
  `SAGE - retro 게이트 결정론 강제 개발(26.07.11)`.
  코드 재확인(2026-07-14): `cycle_binding` 모듈 부재, `profile_validate.py` 에 review_loop coupling FAIL 부재 —
  미착수 확정, 우선순위 4순위(다수 컴포넌트 대공사, ↑ 코드 검증 참고).

---

## EH-5 — Risk Level 강제 게이트 + 완전 effective-max 결정론화

- **배경**: write-back 심층 노트(9-E)가 "이 사이클 risk tier 로 노트 깊이 결정"을 지시. 후속 A 로
  00 템플릿에 `Risk Level: Lx` 필수 필드 + sage-plan 기입 지침 + write-back 이 그 라인을 읽어 **선언값
  결정론 정본화**는 완료(재개 세션에도 tier 확정, `_cycle_risk` 정규식과 동일 라인).
- **문제(A 의 advisory 한계)**:
  1. **미기입 무방비** — sage-plan Step 3/6 이 채워짐을 *프롬프트로* 확인하나 훅 차단은 아님. leader 가
     placeholder 를 남겨도 결정론으로 막지 못한다(현재는 write-back 이 unknown→L2 심층 fallback 으로 안전 degrade).
  2. **effective-max의 실제 변경 결속 불완전** — `_cycle_risk` 자체는 현재
     `max(event.declared_max, snapshot.cycle_risk, 같은 stem의 00~05 전체 선언)`을 반환한다. 그러나
     `build_snapshot()`은 `cycle_risk`를 생산하지 않고 post-tool 로그도 risk를 보존하지 않아, 이전 소스 편집에서
     글롭/내용으로 감지된 상위 tier가 Phase 00에 반영되지 않으면 06 시점에 복원되지 않는다.
  3. **재조정 강제 부재** — 계획 L1 이 구현 후 L2/L3 로 커져도 자동 상향 없음. write-back 이 06 전에 `profile.risk`
     로 재분류해 00 을 갱신하도록 *프롬프트로* 지시하나 best-effort(집행 없음).
- **접근(§10-c locked)**: (1) Phase 00-only 쓰기는 복구 경로로 허용하되, 이후 phase 또는 L1/L2/L3
  소스 쓰기 전에 같은 stem의 00에 유효한 risk 선언이 정확히 하나인지 강제한다. (2) 현재
  `classify_risk()`의 effective tier가 00보다 높으면 소스 쓰기를 차단하고 00을 별도 편집으로 먼저 상향하게 한다.
  (3) 기존 `_cycle_risk` 전체 선언 max와 unknown fail-closed 동작은 보존한다. 새 훅·profile 키·risk ledger는
  만들지 않는다.
- **규모/위험**: **중간**. PDCA 문서 계약(00 스키마)·pre-implementation 게이트·`_cycle_risk`·테스트 동시 변경.
- **트리거**: write-back 노트 깊이 오분류가 실제 관측되거나, "정직한 host" 전제로 부족할 때. **현 긴급도 낮음**
  — 미기입/불명확은 write-back 이 L2 심층 fallback 으로 안전 degrade.
- **상태**: ✅ **로드맵 §10-c 완료(2026-07-28)**. Cycle-Stem:
  `sage-risk-level-effective-max-gate`. 정본 plan:
  `plan_docs/00-base_plan/sage-risk-level-effective-max-gate.md`부터 동일 stem의 01/02 문서.
  gate core, override floor, host messages, runtime/golden/overlay 회귀, 문서·템플릿을 갱신했고
  targeted 180 PASS, runtime smoke 13 PASS, overlay backing 13 PASS, wheel smoke와 clean-context
  L3 리뷰 APPROVED를 확인했다. host-sensitive 테스트를 실행 환경과 격리한 뒤 main의 ambient-Codex
  실행과 10-c의 pipx/명시-host 실행에서 전체 hook suite가 모두 통과했다.
  교차 모델 Claude 리뷰는 세션 한도로 미실행했으며 Phase 05에 same-runtime 사실을 명시했다.

---

## EH-6 — Codex CORE skill 전역/프로젝트 로컬 설치 scope

- **배경**: Codex CORE skill은 과거 `$CODEX_HOME/skills`에 설치하고 `--no-global-skill`로만 생략했다. SAGE를
  계속 개발하면서 동일 프로젝트에 도그푸딩하거나 저장소 로컬 `CODEX_HOME`을 함께 쓰면 같은 `$sage-*` skill이
  전역과 프로젝트에 중복 노출될 수 있다. 저장소를 받은 팀원이 별도 전역 설치를 해야 하는지도 명확하지 않다.
- **해결한 문제**: 설치 위치가 ambient 환경변수와 선행 설치 상태에 의존해, 어떤 사본이 선택되는지·어느 버전이 유효한지·
  저장소 자산만으로 팀 온보딩이 가능한지를 `install`/`doctor`/`validate`가 설명하거나 검증하지 못한다.
- **구현**: Codex 설치 시 **global / project-local scope를 명시적으로 선택**하게 하고, 선택 결과를 설치 영수증에
  기록한다. global은 사용자 공용 skill, local은 대상 저장소의 `.codex/skills`를 소유한다. 중복 발견 시 조용히
  공존시키지 않고 우선순위와 정리 방법을 진단하며, 팀원 온보딩 안내도 선택 scope에 맞춰 생성한다. 정확한 CLI
  안내한다. SAGE-FB-05에서 transaction rollback과 cross-repository shared global lock까지 함께 닫았다.
- **규모/위험**: 중. `install` 경로 결정, manifest/receipt, `doctor` 중복·버전 진단, 업그레이드·제거·양 host 회귀,
  문서와 팀 온보딩 계약을 함께 변경해야 한다.
- **트리거**: 이미 ChatForYou 도그푸딩에서 `$sage` skill 중복 노출과 팀원 설치 여부 질문이 발생해 충족됐다.
- **상태**: ✅ **완료(2026-07-17, SAGE-FB-05)**. 세 fresh Claude 리뷰와 closure review, full 1,316 tests,
  official hook suite를 통과했다. 요구사항 정본은 `SAGE - ChatForYou 실증 2차 후속 개발 요구사항 (26.07.17)`의
  `SAGE-FB-05`다.

---

## EH-7 — 장수 브랜치 cycle stem 해석 + 선언 통로 감사

- **배경**: ChatForYou `chatforyou_v2_sage` 브랜치에서 L2 파일이면 무엇이든 편집이 차단됐다
  (`⛔ [GATE BLOCK — L2] 의무 PDCA phase 미작성: [00, 01, 02, 03]`). SAGE 자산뿐 아니라 앱 코드
  (`ChatApplication.java`, `server.js`)도 동일하게 막혀, 자산 한정 문제가 아니었다.
- **원인**: phase 문서가 아닌 파일을 고칠 때는 바인딩할 경로가 없어 `cycle_binding` 이 stem 을 git 브랜치의
  마지막 세그먼트에서 추론한다. 사이클마다 브랜치를 따는 흐름에서는 맞지만, 여러 사이클이 한 장수 브랜치를
  공유하면 추론값이 어떤 phase 문서와도 맞지 않아 문서가 전부 있어도 영영 결핍 판정이 난다. `resolve()` 가
  이미 `source: ["branch-leaf"]` 를 돌려주는데 아무도 소비하지 않아, 안내는 "phase 문서를 작성하세요" 로
  방향이 틀린 채였다.
- **부수 발견(더 무거움)**: 탈출구인 `SAGE_CYCLE_STEM` env 는 저장소 전체에서 주입 한 줄만 존재하고 문서·출력·
  테스트에 전무했다. 게다가 이 선언은 phase 검사만 우회하지 않는다 — acceptance waiver grant 매칭 키이자 L3
  리뷰 증거 판정 기준이라, **이미 완결된 과거 사이클의 stem 을 선언하면 증거가 모두 갖춰진 상태로 판정되어
  전 게이트가 통과**하고, 그 통과가 감사 로그·출력 어디에도 남지 않았다.
- **구현**: `decide` 가 판정에 `cycle_stem`/`cycle_source`/`cycle_stem_declared` 를 스탬프한다(판정 로직 불변).
  안내는 출처로 분기해 추론일 때만 선언 경로를 제시하고, 경로 유래 결핍에는 기존 문서 작성 안내를 유지한다
  (우회를 가르치지 않기 위해). 선언 사용은 `.sage/override.jsonl` 의 `cycle_stem_declared` 로 세션·stem 1회
  기록하며, 기록 실패 시 통과를 허용하지 않는다(`block_cycle_stem_audit_failure`). 선언 자체는 막지 않는다 —
  장수 브랜치에서는 이게 유일한 정상 경로이고, 봉쇄하면 개발이 다시 멈춘다.
- **기각한 안**: SAGE 자산을 PDCA 대상에서 제외 — 앱 코드도 막히므로 대다수 케이스가 안 풀리고,
  `project-profile.yaml` 은 `pdca.enabled`·`risk.*` 를 담은 게이트 정책 소스라 무게이트로 열면 한 줄로 전
  시스템 게이트를 끄는 무검증 경로가 생긴다. branch-leaf 추론 자체를 변경 — `test_cycle_binding.py` 가
  의도된 계약으로 못박고 있고, 사이클=브랜치 흐름에서는 옳다.
- **상태**: ✅ **완료(2026-07-25)**. `test_cycle_stem_declaration.py` 17 케이스로 재현·안내·감사·fail-closed 를
  못박았다.

---

## EH-8 — 나머지 감사 로그 3종의 authority-aware 무결성

- **배경**: SAGE는 `.sage/acceptance-waivers.jsonl`, `.sage/retro_audit.jsonl`,
  `.sage/override.jsonl`을 서로 다른 권한·감사 목적으로 쓴다. §10-g 검토에서 네 로그 전체를 같은 해시
  writer로 묶는 안을 검토했지만, 각 로그의 권한성과 실패 계약이 달라 별도 범위로 분리했다.
  §10-h에서 개인 vault 경로를 담는 `retro_audit.jsonl`은 로컬 상태로 전환했으며, 나머지 두 로그는
  계속 커밋 정본이다. 이 추적 정책 변경은 EH-8의 로그 자체 무결성 과제를 구현하거나 해소하지 않는다.
- **문제**: acceptance waiver는 report 예외 권한의 정본이고 별도 `flock`·secure-open 하드닝을 갖는다.
  retro audit은 Stop gate 증거지만 읽기 실패의 fail-open/reporting 경계가 있다. override audit은 사후 추적용이며
  실제 활성 권한은 저장소 밖 grant store가 결정한다. 동일한 `prev_hash` 필드만 추가하면 검증되지 않는 해시를
  보안 기능처럼 보이게 하거나 기존 권한/복구 계약을 깨뜨릴 수 있다. 세 writer 모두 terminal newline 없는
  정상 JSONL 뒤에 구분자 없이 append해 레코드를 합치는 기존 결함도 있으므로, 로그별 실패 정책을 보존하면서
  같은 단일-write separator 회귀를 각각 닫아야 한다.
- **접근**: 로그별 위협모델과 소비 정책을 먼저 고정한다. acceptance는 chain 오류 시 권한 판정을 fail-closed,
  retro는 Stop/doctor의 BLOCK·WARN·unreadable 계약을 명시, override는 권한 store와 감사 trail의 책임을
  분리한 채 CLI/doctor에서 무결성을 표면화한다. 공통화는 canonical hash 같은 순수 primitive에 한정하고 각
  writer의 잠금·secure-open·오류 정책은 유지한다. 적대적 편집자까지 범위에 넣으면 서명된 head나 외부 witness를
  별도 설계한다.
- **규모/위험**: 중대. 권한 판정, Stop hook, doctor, CLI, POSIX/Windows 잠금, legacy 정책을 함께 검증해야 한다.
- **트리거**: 실제 감사 변조가 관측되거나 규제·외부감사 요구로 committed audit 자체를 권한 근거로 강화할 때.
- **상태**: 🕗 **보류(2026-07-30, §10-g에서 분리)**. §10-g 완료 후 독립 L3 설계·검토 대상으로 유지한다.

---

## EH-9 — 소비자 생성·project hook 확장 계약 통합 하드닝

- **배경**: ChatForYou에 0.9.76을 역적용하면서 생성 onboarding의 trailing whitespace,
  `checklist_scan_targets` schema/runtime drift, project-authored hook의 create-new lifecycle 부재가 함께 확인됐다.
- **문제**: 잘못된 profile이 strict validation을 통과한 뒤 thin adapter에서 exit 1 traceback 또는 무음 무동작으로
  나타나고, 신규 project hook은 manifest·adapter 선요구 때문에 문서화된 `spec + pure core` 흐름으로 등록할 수 없다.
  수동 host 등록도 runtime의 unknown ID exit 0 때문에 장식용 gate가 된다. 첫 구현 시도에서는 별도 rollback을
  추가하며 snapshot 시점, 부분쓰기, chmod 실패, 동시 manifest/adapter 변경 같은 트랜잭션 결함이 반복됐다.
- **접근(§10-i 통합 확정)**: profile 객체·경로·진입점 계약과 project hook 등록·generic dispatch를 한 L3 변경으로
  구현한다. `sage generate --kind hook --write`가 쓰는 compiled profile, manifest, canonical adapters,
  host 설정과 shims를 기존 `DestinationLock` + `InstallTransaction`으로 묶는다. 최종 산출물을 메모리에서 모두
  검증·렌더한 뒤 기록하며, manifest는 중간 등록 없이 한 번만 쓴다. 신규 project hook은 양 host만 허용한다.
- **규모/위험**: **중대(L3)**. profile schema/compiler/validator/runtime, generate/install transaction,
  manifest, 양 host dispatch, template/docs, wheel packaging을 함께 변경한다.
- **트리거**: ChatForYou 0.9.76 역적용과 project-authored gate 실증에서 충족됐다.
- **상태**: ✅ **완료·릴리즈 `v0.9.77`(2026-08-02)**. 10-i-1/10-i-2를
  한 transaction/acceptance로 구현했다. 최소 fixture 출력 12곳·전체 설치 소비자 출력 22곳과 record/verify
  실패 주입 rollback, schema/manual parity,
  install force 보존, none/Claude/Codex 공식 suite와 clean wheel의 template→양 host dispatch→validate를 통과했다.
  독립 검증에서 나온 recursive glob 디렉터리 오차단, `--id` 없는 project parser 우회, install/generate manifest
  key-order churn을 재현해 수정하고 회귀를 추가했다. compiled profile `0600` 전환, project hook profile 필수,
  `event.changes` 공개 계약도 한영 문서에 명시했다. 후속 재검증에서 확인된 호출부 없는 구 `_stamp_manifest`
  writer는 제거하고 테스트를 실제 generate transaction 경로로 이전했다.
  정본: `plan_docs/00-base_plan/sage-consumer-generation-extension-contract-hardening.md`.

---

## EH-10 — adapter/shim 직접 실행 경로의 profile freshness (CORE 공통)

- **배경**: §10-i 독립 검토에서 "생성된 project hook adapter가 stale profile을 통과시킨다"가 완료 차단으로
  제기됐다. 재현은 사실이나 project hook 고유 결함이 아니라 adapter 계층 전체의 기존 성질임을 실측으로 확인해
  §10-i 범위 밖 경계로 분리했다(정본 base plan §5.4 "경계 — profile freshness는 entrypoint SSOT가 아니다").
- **문제**: hook 런타임은 **의존성 0(compiled JSON만 읽음)** 계약이라 `project-profile.yaml`을 파싱할 수 없다.
  그래서 YAML↔compiled JSON 동등성 비교는 `sage-hook`(`hook_entry._prepare_gate_profile`) 한 곳에만 있고,
  canonical adapter와 host shim은 `SAGE_PROFILE`을 직접 주입한 뒤 `run_hook.py`를 exec 하므로 그 비교를 건너뛴다.
  YAML만 고치고 `sage generate`를 다시 돌리지 않은 상태에서 CORE hook과 project hook 모두 adapter/shim은 rc=0,
  `sage-hook`은 rc=2다. 소비자 실행 경로는 host 등록 command가 `sage-hook`이라 보호되고 `sage validate`가
  `profile-yaml-json-stale` WARN + `overlay-materialize-drift` FAIL로 표면화하므로, 남은 노출은 adapter/shim
  **직접 호출**(테스트·디버깅)뿐이다. 다만 "세 entrypoint가 같은 guarded dispatch를 쓴다"는 계약과는 어긋난다.
- **접근**: generate가 `project-profile.yaml` 바이트 해시를 compiled JSON에 스탬프하고 런타임이 대조하면
  의존성 0을 지키면서 모든 entrypoint가 검사를 받는다. 단 바이트 해시는 주석·공백 변경도 stale로 판정해
  현재 `sage-hook`의 의미 비교(`materialize_profile` 동등성)와 규칙이 갈리므로, `hook_entry`도 같은 규칙으로
  옮겨 한쪽으로 통일해야 한다. project adapter만 `sage-hook`을 경유시키는 국소 수정은 PATH 부재 시 fallback이
  검사를 건너뛰어 반쪽이고 CORE adapter와 비대칭을 만들므로 채택하지 않는다.
- **규모/위험**: 중. CORE 게이트 8종의 실행 계약과 `hook_entry`, 양 host adapter, compiled profile 스키마,
  관련 회귀를 함께 바꾼다. 주석 편집이 stale로 잡히는 의미 변경을 받아들일지가 선결 판단이다.
- **트리거**: adapter/shim을 직접 호출하는 host 배선이 실재하거나, 세 entrypoint의 검사 동등성을 계약으로
  강제해야 할 때. 현 위협모델상 긴급도 낮음 — host 경로는 차단되고 validate가 잡는다.
- **상태**: 🕗 **보류(2026-08-02, §10-i에서 경계로 분리)**. 독립 L3 설계·검토 대상.

---

## EH-11 — 장수 브랜치 다중 사이클 결속 검증 + 선언 risk 오탐

- **배경**: §10-a(EH-7)는 장수 브랜치에서 cycle stem을 브랜치 leaf로 추론할 때의 *오안내*와 *선언 감사*를
  닫았다. 그러나 한 브랜치에서 사이클을 이어 돌릴 때 **추론이 엉뚱한 사이클에 성공하는 경로**는 남았다.
  ChatForYou `chatforyou_dual_implementation_doc_gate` 사이클 개발(실측 `0.9.77`)에서 수집했고, J-8·J-9는
  같은 사이클의 Phase-05 cross-model 리뷰가 찾은 CORE 결함이다.
- **문제**: (A) 1차 L3 사이클 뒤 같은 브랜치에서 2차 L2 소스 편집이 **차단도 경고도 없이 1차 사이클에 결속**된다.
  위험도 판정은 10-c의 effective-max 규칙상 정상이고, 결함은 **어느 사이클에 결속됐는지 아무도 확인하지
  않는다**는 점이다. 실제로 `Component-Backend: N/A`를 선언한 사이클로 backend 코드를 고치는데 게이트가
  승인했다. 피해는 침묵이다 — 2차 acceptance 증거가 1차 버킷에 쌓이고 Phase 05가 1차 문서로 2차 코드를 판정한다.
  (B) `capture-declared-risk`가 **가정 질문**("L3 개발을 1차로 한 후 …")에서 위험도를 선언으로 포착하고
  `max(levels)`로 L3를 채택해, 세션 전체가 L3로 간주돼 모든 편집이 차단됐다. 안내는 *00을 L3로 올리라*고 해
  따르면 위험도 기록을 허위 상향하게 된다. 정정 명령이 없어 방치하면 2일 TTL까지 세션이 묶인다.
  (C) claude 런타임은 BLOCK을 stdout으로 렌더하는데 Claude Code는 exit 2일 때 stderr를 사유로 읽어
  차단 사유가 사용자에게 전달되지 않는다(codex는 정상 — 런타임 간 계약 불일치).
  (D) 거버넌스 자산 소스가 도메인 content keyword를 이름으로 담으면 자기 자신이 상위 tier로 분류된다.
  (E) `io_codex.extract_phase4_changes`가 `*** Move to:` 목적지를 무시해 **파일 이동으로 Phase04 게이트를
  우회**할 수 있고(같은 모듈의 범용 `extract_changes`는 처리하므로 Phase04 전용 추출기만 빠졌다),
  `_project_snapshot`은 `plan_reads` 오반환을 `runtime_contract_error`로 잡지 않는다.
- **접근**: J-1~J-9로 분해했다. J-1(완결 사이클 결속 차단)은 새 데이터 없이 profile의 `report_phase`/
  `approve_phase`/`approve_marker`와 실제 06·05 문서로 판정 가능하다. J-3(`sage cycle use <stem>`)은
  §10-e가 grant를 저장소 밖으로 옮긴 선례를 따라 머신 로컬 상태에 둬 닭-달걀·저장소 오염·낡은 값을 함께 해소한다.
  J-5는 안내 순서가 핵심 — 계산 위험도가 세션 *선언*에서 왔으면 "선언이 맞습니까"를 먼저 묻고, 경로·내용 기반일
  때만 00 상향을 제시한다(출처 구분은 §10-a의 `cycle_source` 스탬프로 가능).
- **경계**: branch-leaf 추론 자체는 바꾸지 않는다(§10-a에서 기각, `test_cycle_binding.py`가 계약으로 못박음).
  선언 통로도 막지 않는다(장수 브랜치의 정상 경로). 10-c의 effective-max 규칙은 불변 — 결함은 위험도 계산이
  아니라 결속 검증 부재와 선언 입력 품질이다. 정규식을 느슨하게 해 포착을 늘리는 방향은 금지 — **오탐이 곧
  세션 정지라 미포착보다 오탐이 비싸다**.
- **규모/위험**: 중~중대. `cycle_binding`, pre-implementation gate, `capture-declared-risk` core,
  양 host io 렌더 채널, 신규 CLI(`sage cycle use`)와 머신 로컬 상태를 함께 다룬다. 하위 항목별 분할 착수 가능.
- **트리거**: J-8은 게이트 우회 경로라 즉시 착수 후보다. 나머지는 장수 브랜치 다중 사이클 운용이 계속될 때.
- **상태**: 🕗 **일부 완료(2026-08-03)**. J-4·J-5·J-6·J-8·J-9 는 두 사이클로 개발해 `v0.9.78` 릴리즈.
  잔여: 결속 본체 J-1·J-2·J-3(EH-12 선행 필요 — J-2 가 그 위에 선다)과 J-7. 정본 위키:
  `SAGE - 장수 브랜치 다중 사이클 결속·선언 risk 설계 (10-j, 26.08.02)`.

## EH-12 — claude PreToolUse 의 비차단 메시지가 사용자에게 닿지 않음

- **배경**: §10-j-1(hook 런타임 IO 계약 정합)의 Phase 05 독립 리뷰에서 나왔다. 그 사이클은 BLOCK 사유가
  claude 에서 stdout 으로 나가 유실되던 것을 stderr 로 옮겨 닫았는데, 같은 확인 과정에서 **반대 방향의
  비대칭**이 드러났다.
- **문제**: Claude Code 는 exit 0 hook 의 평문 stdout 을 디버그 로그에만 쓴다. 컨텍스트로 올라가는 이벤트는
  `UserPromptSubmit`·`UserPromptExpansion`·`SessionStart` 뿐이고 **PreToolUse 는 아니다**(공식 문서 확인).
  `io_claude.render_gate`·`render_phase4` 의 OK/WARN 은 평문 stdout 이므로 claude 사용자·모델 어느 쪽에도
  닿지 않는다. codex 는 같은 상황에서 `hookSpecificOutput.additionalContext` 를 쓰므로 보인다.
  PreToolUse 도 `additionalContext` 를 지원하므로 이는 host 제약이 아니라 SAGE 의 미사용이다.
- **왜 지금 중요한가**: EH-11 의 **J-2(OK 줄에 판정 stem 과 출처를 항상 표기)가 이 위에 서 있다.**
  이걸 먼저 닫지 않으면 J-2 는 claude 에서 아무 효과가 없는 기능이 된다.
- **접근**: `io_claude` 의 비차단 렌더를 `hookSpecificOutput.additionalContext` JSON 으로 전환한다.
  BLOCK(stderr)·비차단(JSON) 분리는 codex 와 같은 모양이 되어 런타임 대칭이 완성된다.
- **경계**: BLOCK 채널은 §10-j-1 에서 이미 닫았으므로 건드리지 않는다. 문구(`messages`)도 불변이다.
  `render_declared_capture` 는 `UserPromptSubmit` 바인딩이라 평문 stdout 이 정확하며 대상이 아니다.
- **규모·위험**: 코드는 작다(렌더러 2곳). 위험은 claude 출력 프로토콜이 평문→JSON 으로 바뀌는 것이라
  stdout 평문을 단언하는 기존 테스트가 흔들린다. §10-j-1 에서 채널 이동만으로 16건이 걸린 전례가 있다.
- **트리거**: EH-11 의 J-2 착수 전. 또는 claude 에서 게이트 OK/WARN 이 안 보인다는 보고가 다시 나올 때.
- **상태**: ✅ **완료(2026-08-04, 미릴리즈)**. `io_claude` 의 PreToolUse 비차단 렌더 둘을
  `hookSpecificOutput.additionalContext` 로 전환. 차단(stderr)·`UserPromptSubmit` 계열(평문)은 불변.
  정본 `plan_docs/00-base_plan/sage-claude-nonblock-context-channel.md`.

---

## EH-13 — install source drift 진단이 어느 파일인지 알려주지 않는다

- **배경**: §10-j-2·EH-12 사이클의 전체 스위트 실행에서 `install.run()` 이
  `InstallDriftError: SAGE source resources changed during install` 로 실패했다.
  **원인은 제품 결함이 아니라 검증 방식이었다** — 변이 스위트와 독립 리뷰어(`git stash`)가
  `scripts/sage_harness/hooks/**` 의 파일을 제자리에서 고쳤다 되돌리는데, 그 경로가
  `build_identity._inventory()` 의 `hooks` 루트라 install 이 정당하게 drift 를 잡은 것이다.
  즉 **검사는 설계대로 동작했다.**
- **문제**: 진단이 "소스가 바뀌었다"까지만 말하고 **어느 논리 경로가 달라졌는지** 알려주지 않는다.
  그래서 원인 특정에 세 가지 가설(pycache 오염·lock inode 재사용·인벤토리 내용 변경)을 배제하는
  우회 작업이 필요했다. 실제로는 해시 비교 두 값의 차이를 파일 단위로 보여주기만 하면 즉시 끝난다.
- **접근**: preflight 인벤토리를 (논리경로 → 해시)로 보관하고, drift 시 추가·삭제·변경된 논리경로
  목록을 진단에 싣는다. 152개 파일이라 메모리·시간 비용이 무시할 수준이다.
- **경계**: 검사 자체를 완화하거나 재시도로 덮지 않는다. 설치 도중 엔진 소스가 바뀌면 반쯤 섞인
  산출물이 나오므로 fail-closed 가 정답이다. 바꾸는 것은 **진단의 정보량**뿐이다.
- **부수 개선(완료)**: `test_install.py` force-reinstall 보존 테스트와 `test_doctor.py` claude 렌더
  drift 테스트가 `install.run()` rc 를 단언하지 않아 실패가 `FileNotFoundError` 로만 나타났다.
  두 곳에 rc 단언을 추가해 사유가 바로 보이게 했다.
- **운영 메모**: 변이 테스트·독립 리뷰를 **전체 스위트와 동시에 돌리지 않는다.** 둘 다 저장소
  소스를 일시 변경하므로 install 계열 테스트가 정당하게 실패한다.
- **규모·위험**: 작다. 진단 문자열과 preflight 자료구조만 바뀐다.
- **트리거**: install 트랜잭션을 다시 손댈 때. 또는 같은 진단이 실제 원인 불명으로 나올 때.
- **상태**: 보류. 원인 규명 완료(제품 결함 아님), 진단 개선만 남음.

---

## (참고) 보류 — 자산 사이클 내 기록
- F5(클린 업그레이드)는 하드닝에서 해소(profile create-only). F1/F3/F7/malformed 동일.
- 진행 로그: vault `TECH - SAGE 구현 진행 로그.md`
