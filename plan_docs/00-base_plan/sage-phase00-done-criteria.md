# [Base Plan] SAGE EH-19 Phase 00 Done Criteria Gate

Cycle-Stem: `sage-phase00-done-criteria`
Risk Level: L3
Status: IMPLEMENTED ON LOCAL MAIN (2026-08-11, commit 4ba3aa0; push/release pending)
Done-Criteria-Revision: 1

## 1. Context

Phase 00 완료 기준은 현재 자유 산문이며 각 Phase 전환, Phase 05 승인, Phase 06 report가 그 상태를
결정론적으로 확인하지 않는다. 구현 중 설계가 바뀌어 Phase 00을 고쳐도 영향 Phase 재실행과 기존
승인 무효화 계약이 없다.

## 2. Goal

- 표준·Fast Phase 00의 Done Criteria를 같은 구조 파서로 검증한다.
- Phase 01..04에서는 구조와 진행률을 확인하고 정상 미완료는 허용한다.
- 재계획은 revision·사유·영향 Phase를 기록하고 영향 Phase 재실행을 요구한다.
- Phase 05 APPROVED는 unresolved 0과 현재 revision을 요구한다.
- Phase 05 승인 시 Phase 00 전체 text hash 하나만 Loop audit에 결속하고 Phase 06에서 stale 승인을 막는다.
- local hook과 server authority가 같은 결과를 낸다.

## 3. Architecture

1. `sage.done_criteria_contract`가 Markdown section, 3상태 item, revision log, LF-normalized full-text
   SHA-256을 소유한다.
2. `pre_implementation_gate_core`는 주입된 Phase snapshot과 Loop audit summary만 사용해 Phase별
   진행·최종 report 판정을 수행한다.
3. `review-loop close APPROVED`는 현재 cycle의 Phase 00을 exact 선택하고 unresolved 0을 확인한 뒤
   hash를 `loop_close` record에 기록한다.
4. Phase 05 문서는 같은 `Phase00-Hash`와 `Loop-Run`을 선언하고, Phase 06 gate와 server authority가
   current 00 == 05 == Loop close를 비교한다.
5. profile 키 부재/off는 기존 동작을 유지한다.

## 4. Implementation Tasks

- [x] T1 parser unit 실패 테스트 작성 후 `sage/done_criteria_contract.py` 구현
- [x] T2 profile schema/manual/init 대화 계약 테스트 후 구현
- [x] T3 Phase 01..06 local gate·메시지·non-overridable 테스트 후 구현
- [x] T4 review-loop APPROVED·loop audit hash 결속 테스트 후 구현
- [x] T5 server authority parity 테스트 후 구현
- [x] T6 표준/Fast skeleton·templates·skills 테스트 후 구현
- [x] T7 한·영 README/reference/quickstart/troubleshooting 문서 동기화
- [x] T8 manifest 재스탬프, wheel, none/Claude/Codex 전체 검증
- [x] T9 Claude 적대적 리뷰 3R와 지적별 재현·수용 판단 완료

## 5. Done Criteria

- [x] standard/Fast parser가 exact section과 `[ ]`·`[x]`·reasoned `[~]`를 검증한다
- [x] Phase 01..04는 valid unresolved를 허용하고 구조·revision 오류를 mode대로 처리한다
- [x] 재계획 사유와 영향 Phase가 없거나 영향 Phase가 current revision이 아니면 다음 전환을 막는다
- [x] APPROVED close는 unresolved 0과 current revision을 요구하고 Phase 00 hash를 기록한다
- [x] Phase 06은 current Phase 00·05·selected Loop run hash 불일치를 stale 승인으로 차단한다
- [x] Fast 기존 전체 plan hash·Document Mapping 계약이 유지된다
- [x] schema/manual/local-server/Claude-Codex 판정 parity 회귀가 통과한다
- [x] 한·영 사용자 문서와 설치 wheel에 신규 계약이 포함된다
- [x] `sage validate --kind all --check --schema`가 STALE 없이 통과한다

## 6. Done Criteria Revision Log

Initial revision 1. No replanning record.

## 7. Constraints

- Stop hook과 완료된 과거 Phase 00 문서는 수정하지 않는다.
- Phase별·항목별·의미 정규화 hash를 추가하지 않는다.
- 커밋·main 병합·push·release는 사용자 승인 전 수행하지 않는다.

## 8. External Review Evidence

- Round 1: 약한 Loop summary로 Phase 06을 통과할 수 있던 결함과 Phase 05 revision 검사 불일치를
  재현해 수정했다. 들여쓰기 code block을 criterion으로 취급하라는 제안은 Markdown 의미론상 기각했다.
- Round 2: Fast 명령이 `off/advisory/enforce`를 무시하던 결함과 server authority가 사용자 지정
  `approve_marker`를 무시하던 결함을 재현해 수정했다. 파일 교체 TOCTOU는 낮은 현실성과 구현 복잡도를
  근거로 이번 범위의 잔존 위험으로 수용했다.
- Round 3: Fast server hash 결속 누락 지적은 기존 `_fast_evidence_reasons`가 current plan hash,
  Fast/Loop strict chain, stem, rounds, lenses를 검증하고 `fast-cycle close`도 review hash를 대조하므로
  재현되지 않아 기각했다. CI request builder의 양 audit 주입도 확인했다.
- 최종: none/Claude/Codex `run-all.sh`, wheel smoke, all-kind schema/manifest 검증과 diff check 통과.
