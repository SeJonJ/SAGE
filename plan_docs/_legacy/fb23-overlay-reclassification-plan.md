# FB23 — 오버레이 합성 자격 (c)→(b) 재분류 (backing 증명분 개방)

- 상태: 설계(승인 대기)
- 계보: `overlay-composition-plan.md` v8 §8/§11 의 "gate-classification 확정 — SD-8 오라클
  설계에 의존" 을 닫는 트랙. 위키 로드맵 §9-G-3 FB23.
- 코드 진입점: `sage/overlay_classify.py::INDEPENDENT_ORACLE_COMPOSE_ALLOWED`(현재 `frozenset()`)

---

## 1. 목표 (bounded · completable)

`overlay_classify.py` 의 (c) 게이트-보유·오라클-미보증 자산 중, **게이트가 자산 텍스트를
읽지 않는 독립 결정론 오라클로 이미 floored 됨을 적대적 우회 테스트로 증명한 부분집합만**
`INDEPENDENT_ORACLE_COMPOSE_ALLOWED` 로 옮겨 (b) 로 재분류한다.

FB23 은 "(c) 전체 개방"이 아니라 **"증명 가능한 subset 만 개방"** 이다. 증명 불가분은 (c)
로 남기고 FB24/FB25 로 명시 분리한다 → FB23 자체가 완결(정의된 완료 판정 존재).

## 2. 멤버십 규율 (유저 확정)

> 재분류는 **선언이 아니라 테스트가 판정**한다.

각 후보 자산에 대해 "해당 자산 프로즈가 뒤집으려는 게이트"를 **오라클이 실제로 차단하는지**를
적대적 우회 테스트로 확인한다. 오라클이 malicious overlay 를 **BLOCK 하면 GREEN → (b) 등록**,
차단하지 못하면 **RED → (c) 잔류(defer)**. "핵심 5" 는 후보 명단일 뿐 확정 명단이 아니다.

## 3. (b) 건전성 기준

자산 X 가 (b) 인 필요충분조건:

> X 의 프로즈가 참여하는 모든 활성 게이트가, X 를 읽지 않고 platform 이벤트(Stop/PreToolUse)에
> 반응하며 **docs(00~06)/session log/컴파일된 profile-JSON 만** 읽는 hook/CI 오라클로 floored
> 되어 있어, 오버레이가 물리 반영돼도 그 floor 를 낮출 수 없다.

핵심: 오라클은 **자산 텍스트를 입력으로 받지 않는다**. 오버레이는 자산 텍스트일 뿐 audit
레코드/사이클 문서를 위조할 수 없으므로(그건 host-level tamper = EH-3 영역, 위협모델 밖)
floor 를 못 낮춘다.

**잔여 "품질/LLM-신뢰 갭"(얕은 plan, rubber-stamp review)은 합성이 새로 여는 forge 가
아니라 base 도 동일하게 가진 선존 갭**이다 → 합성 위협모델 범위 밖. FB23 는 "합성이
새 우회를 여느냐"만 판정한다.

### 3.1 멤버십 정밀화 (R3): "primary 게이트가 floored"

오라클이 floor 하는 것은 **구조**다 — 06←05 APPROVED 마커 존재, loop_audit 무결성, 04
evidence row/status 존재, bound phase 문서 존재. **내용 진위**(04 PASS 가 실제 통과인지, 01
acceptance matrix 가 완전한지)는 어떤 오라클도 재검하지 않는다. 그래서 내용-forge 는 포함/제외
자산을 가리지 않고 모두 미포착이다(자체검증 R3 재현):

| forge | 자산 | 오라클 | delta |
|---|---|---|---|
| fake all-PASS 04 | qa | 미포착(ok) | 0(base 도 가능) |
| 01 matrix 축소 | leader | 미포착(ok) | 0 |
| qa 우회 fake-PASS 04 대필 | sage-team | 미포착(ok) | 0 |
| 04 required row 누락(**구조**) | 임의 | **포착(BLOCK)** | — |

내용-forge 는 전부 **합성 delta=0**(오버레이 없이 base 자산도 가능) → 합성 위협모델 밖. 따라서
멤버십은 **"primary 워크플로 기여가 floored 인가"**로 정한다: leader/sage-cycle/sage-team 은
primary 기여(plan/phase 존재·사이클 시퀀싱)가 구조 오라클로 floored → (b). **qa 는 primary
기여 자체가 미검증 내용(04 진위)**이라 (c) 로 남긴다 — 실행 재검 오라클(FB24/SD-9) 완성 시 재검토.
이 구분은 `test_overlay_reclassification_backing.py::TestAcceptanceContentGapIsPreExisting` 가 고정한다.

## 4. 후보별 backing 오라클 매핑 · 예상 판정

| 자산 | kind | 프로즈가 참여하는 게이트 | backing 오라클(자산-불read) | 예상 |
|---|---|---|---|---|
| leader | agents | plan/phase 작성, 분해 | `_missing_pre_impl_phases` + `_acceptance_gate` + `_report_gate` | PASS(강) |
| sage-cycle | skills | PDCA 진행 | 위 + `retro_gate`(Stop) | PASS(강) |
| sage-plan | skills | 계획 인터뷰 | `_missing_pre_impl_phases`(plan/phase 결속 강제) | PASS |
| reviewer | agents | Phase-05 판정 | `_audit_gate`(loop_audit clean/closed/APPROVED/seq_ok/¬degraded) + `_report_gate` | PASS(테스트 필수) |
| sage-review | skills | review-loop 구동 | `_audit_gate` + `review_loop` | PASS(테스트 필수) |
| sage-team | skills | 팀 오케스트레이션 | review_loop.enabled 조건부 | **조건부**(테스트 판정) |
| qa | agents | 04 acceptance 증거 | `_acceptance_gate`(구조만; 실행 재검 오라클 부재) | **DEFER 예상** |

- **reviewer/sage-review 가 (b) 인 결정적 논거**: `_audit_gate` 는 `loop_audit.jsonl` 레코드
  (`seq_ok`/`degraded`/clean/closed/`result==APPROVED`)를 읽는다. 이 레코드는 runtime hook 이
  실제 이벤트에서 append 한다 — reviewer/sage-review **오버레이 프로즈는 audit 레코드를 못
  쓴다**. 따라서 "always approve" 오버레이가 있어도 forged clean+APPROVED run 을 만들 수
  없어 06←05 report gate 가 BLOCK 을 유지한다.
- **qa DEFER 논거**: qa 의 게이트는 "04 증거가 truthful" 인데, `_acceptance_gate` 는 required
  ID 별 PASS/FAIL/NOT TESTED/N-A **구조**만 검증하고 claimed PASS 를 재실행해 검증하는 오라클이
  없다. "모두 PASS 로 기입" 오버레이가 만든 구조적으로 유효한 04 를 오라클이 못 잡는다 →
  적대적 테스트 RED → qa 는 (c) 잔류. (미래 test-execution 오라클 = qa판 SD-9 필요.)

## 5. profile-blind 설계 플래그 (필수 반영)

`classify(kind, id)` 는 profile 을 안 본다(무조건 compose/blocked). 그런데 reviewer/sage-review/
sage-team 의 `_audit_gate` teeth 는 `review_loop.enabled` 일 때만 발화한다. 따라서 적대적
테스트는 **review_loop-ON 과 review_loop-OFF 두 projection 모두**에서 malicious overlay 가
floor 를 못 낮춤을 증명해야 한다.

- review_loop-OFF 에서도 `_report_gate`(05 APPROVED 마커)·`_acceptance_gate`(04 증거)·
  `_missing_pre_impl_phases` 는 자산-불read 로 발화한다 → base 와 overlay 의 floor 가 동일 →
  합성 delta 0 → 건전. 테스트가 이 delta-0 을 실증한다.

## 6. 산출물 (Deliverables)

① **재분류**: 테스트 GREEN 인 자산을 `INDEPENDENT_ORACLE_COMPOSE_ALLOWED` 에 등록,
   `GATE_BEARING_UNBACKED` 에서 제거. `classify()` 결과 (c)→(b) 전환.
② **조건부 2 판정**: sage-team/qa 는 적대적 테스트 결과로 등록/잔류 결정(선언 아님).
③ **backing 레코드 + 강제 테스트**: `overlay_classify.py` 에 `BACKING`(자산→오라클 근거)
   dict 추가 + "모든 `INDEPENDENT_ORACLE_COMPOSE_ALLOWED` 항목은 BACKING 근거와 적대적
   테스트를 가진다" 를 강제하는 메타 테스트(등록만 하고 근거·테스트 없는 항목 = FAIL).
④ **적대적 우회 회귀 테스트**: 자산별 malicious-overlay 사이클 상태로 오라클을 구동해
   여전히 BLOCK 임을 assert. review_loop-OFF projection 포함. (자산별 신규 테스트 케이스.)
⑤ **spec 오버레이 선언 flip**: 재분류 자산의 `templates/core/{agents,skills}/…` 스펙에서
   `- self_overlay: unsupported` → `- overlay: optional` (기존
   `test_reference_specs_advertise_only_executable_overlay_eligibility` 계약 충족).
⑥ **주석/문서 갱신**: `overlay_classify.py` line 13 "SD-8 …" 주석을 FB23 backing 근거 +
   FB24/FB25 제외 사유로 교체. `overlay-composition-plan.md` §8/§11 상태 갱신.
   `test_gate_bearing_blocked` 를 남은 (c) 집합만 검사하도록 수정.
⑦ **AGENT_GUIDE per-render (b)-claude 합성 문구**: 재분류 자산이 claude 렌더에서 오버레이
   합성됨을 명시하는 per-render directive.
⑧ **codex 적대적 리뷰 3~7R**(model=gpt-5.6-sol, effort=high), teeth 재현 후 수용.

## 7. 범위 밖 (명시 분리)

| 트랙 | 자산 | 제외 사유 |
|---|---|---|
| **FB24** | sage-profile-modify | profile 을 편집 = 오라클의 **입력**을 바꿈 → floor 를 스스로 낮춤. 서버 attestation(SD-9) 선행 필요. |
| **FB25** | framework ×4 (AGENT_GUIDE/CLAUDE/CODEX/AGENTS) | SD-4 domain_refs 계약(authoritative domain 재복제 차단)이 phase/review/verify 오라클이 아님. 루트 md OVERLAY 블록 churn 실해결 트랙. |

## 8. 완료 판정

- 적대적 테스트 GREEN 자산만 `INDEPENDENT_ORACLE_COMPOSE_ALLOWED` 등록(RED = 잔류).
- 산출물 ③ 메타 테스트로 "등록=backing+테스트 보유" 불변 강제.
- `run-all.sh` ALL PASS + touched sage-level 전체 그린 + manifest live==stored.
- codex 3R+ CLEAN(또는 잔여리스크 문서화).
- 릴리즈: patch bump 4곳 → main push → ci.yml green → 태그. 위키 §9-G-3 상태 갱신.

## 9. 비변경 (불변식)

- 권위 = 서버측 CI(로컬 advisory) — FB23 이 이 경계를 바꾸지 않는다.
- fail-closed 기본값: 미분류/미지 = blocked 불변.
- host-level tamper(audit 레코드 위조)는 위협모델 밖(EH-3) — FB23 은 오버레이-프로즈
  위협만 닫는다.
