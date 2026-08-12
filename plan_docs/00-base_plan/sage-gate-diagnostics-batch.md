# [Base Plan] SAGE 진단·가시성 정비 배치 (EH-13 · EH-14 · EH-15 · EH-16)

Cycle-Stem: `sage-gate-diagnostics-batch`
Risk Level: L2
Status: IMPLEMENTED ON WORKTREE (2026-08-12, `worktree-feat+sage-diagnostic-visibility`; merge/release pending)
Done-Criteria-Revision: 1

## 1. Context

백로그 EH-13·EH-14·EH-15·EH-16은 모두 "원인 규명은 끝났고 판정 로직은 건드리지 않으며 진단·가시성만
보강한다"는 성격이라 한 사이클로 묶는다. 넷 다 별도 설계 정본이 없고 백로그 항목 자체가 정본이다.

- **EH-13** — `InstallDriftError`가 "소스가 바뀌었다"까지만 말하고 어느 논리경로가 달라졌는지 알려주지
  않는다. 실제로 원인 특정에 가설 3개를 배제하는 우회 작업이 필요했다.
- **EH-14** — adapter를 bash로 직접 실행하는 테스트가 stdin을 닫지 않아 EOF 없는 stdin(백그라운드 실행)에서
  무한 대기한다. 실패가 아니라 정지라 "테스트가 많아 느리다"로 오진단된다.
- **EH-15** — 게이트 통과 줄에 결속 stem을 붙이는 `_cycle_suffix`가 `message_key` 있을 때만 호출되는데
  L1 통과에는 `message_key`가 없어 출력이 0바이트다.
- **EH-16** — L0 통과도 같은 이유로 stem이 안 보인다.

## 2. Goal

- install drift 진단이 추가·삭제·변경된 논리경로를 이름으로 지목한다.
- adapter 직접 실행 테스트가 어떤 stdin 환경에서도 정지하지 않고, 같은 결함이 재발하면 회귀가 잡는다.
- L1·L0 통과 편집도 어느 사이클에 결속됐는지 확인할 수 있는 경로를 갖는다.
- 위 셋 중 어느 것도 게이트 **판정**을 바꾸지 않는다.

## 3. Architecture

1. `build_identity.source_core_content_snapshot()`이 단일 pass로 (집계 해시, `{논리경로: 파일해시}`)를
   함께 돌려준다. `source_core_content_hash()`는 이 함수의 첫 원소를 반환하도록 바꾸되 **바이트 단위로
   동일한 값**을 유지한다 — 이 값은 설치된 프로젝트 manifest에 박혀 있어 알고리즘이 바뀌면 전 소비자가
   drift로 오판된다.
2. `install.py`는 preflight에서 snapshot을 잡아두고, 두 drift 지점에서 현재 snapshot과 대조해
   added/removed/changed 논리경로를 진단 메시지에 싣는다. 검사 자체는 그대로 fail-closed다.
3. EH-14는 실측으로 범위를 재확정한다(§5 참조). adapter 호출 중 `input=`을 넘기는 것은 이미 stdin이
   닫히므로 대상이 아니다.
4. L1·L0 통과 노출은 **opt-in profile 키**로 넣는다. 통과 줄은 claude·codex 모두 비차단 컨텍스트 채널로
   나가므로(EH-12) 항상 켜면 매 편집마다 모델 컨텍스트에 한 줄씩 쌓인다. 기본값은 현재 동작과 동일하다.

## 4. Implementation Tasks

- [x] T1 EH-14 실측 범위 확정 + 해당 호출 수정 + 재발 방지 회귀
- [x] T2 EH-13 snapshot/diff 구현 + install 두 지점 배선 + 회귀
- [x] T3 EH-15/16 profile 키 + gate core `file_short` 스탬프 + `messages.py` 렌더 + 회귀
- [x] T4 schema/template/문서(한·영)/인터뷰 계약 동기화
- [x] T5 전체 hook suite + 백로그 상태 갱신

## 5. Done Criteria

- [x] install drift 진단이 변경된 논리경로 이름을 포함한다
- [x] `source_core_content_hash()` 반환값이 변경 전과 바이트 단위로 같다
- [x] adapter를 bash로 직접 실행하면서 stdin을 닫지 않는 테스트 호출이 0건이다
- [x] 새로 추가된 adapter 호출이 stdin을 닫지 않으면 회귀가 실패한다
- [x] profile 키가 켜진 경우에만 L1·L0 통과 줄이 나오고, 부재/off는 기존과 동일하다
- [x] 게이트 판정(status·exit_code)은 어떤 항목에서도 변경되지 않는다
- [x] 신규 profile 키가 schema·template·한영 레퍼런스·인터뷰 문서에 모두 도달한다
- [x] none/Claude/Codex 전체 hook suite가 통과한다
- [~] EH-16의 `pdca.enabled=false` 노출 (N/A: PDCA 비활성이면 사이클 개념 자체가 없어 노출할
  결속이 존재하지 않는다. §5-2 실측 참조 — 원안의 "재료는 이미 있다"가 이 경우엔 틀렸다)

## 5-1. 실측으로 뒤집힌 원안 서술

착수 전 백로그 서술을 코드로 재확인하는 과정에서 두 건이 틀린 것으로 확인됐다.

- **EH-14 "12곳" → 실제 1곳.** adapter 호출은 18곳이지만 17곳은 이미 `input=...`을 넘긴다.
  `subprocess.run(input=)`은 파이프를 열어 쓰고 닫으므로 EOF가 전달된다. 둘 다 없는 호출은
  `test_stop_compliance_report.py:162`(`test_no_log_skips`) 하나뿐이고, 실제로 멈춘 테스트도 정확히
  그것이었다. 원안은 mechanism을 맞게 진단한 뒤 범위를 호출 목록 전체로 넓게 잡았다.
- **EH-16 "재료는 이미 있다" → 절반만 참.** `_stamp_cycle_identity`는 `_pdca_cfg(profile) is None`
  이면 즉시 반환해 stem을 싣지 않는다. L0에는 재료가 있고 pdca 비활성에는 없다.

## 5-2. 설계 판단 — 왜 항상 켜지 않았나

EH-15/16을 무조건 노출로 만들지 않고 opt-in 키로 넣었다. 통과 줄은 EH-12 이후 양 host 모두
비차단 컨텍스트 채널(`additionalContext`)로 나간다. L1은 편집 빈도가 가장 높은 tier라 항상 켜면
편집마다 모델 컨텍스트에 한 줄이 쌓인다. 반면 결속 증거 자체는 위험도와 무관하게
`.sage/override.jsonl`에 남고 기록 실패는 이미 fail-closed BLOCK이다 — 즉 이 항목은 손실 복구가
아니라 감시 편의이므로, 비용을 아는 쪽이 켜는 구조가 맞다. 백로그가 "소음 검토 필수"라고 남긴
경고에 대한 답이기도 하다.

부수 결정: 결속할 stem이 없으면 `ok_l1`/`ok_l0`를 취소한다. 정보가 0인 통과 줄은 켠 사람이 얻는
것 없이 컨텍스트 비용만 낸다.

## 6. Done Criteria Revision Log

Initial revision 1. No replanning record.

## 7. Constraints

- 판정 로직·게이트 강도·해시 알고리즘은 바꾸지 않는다. 바꾸는 것은 진단의 정보량과 가시성뿐이다.
- 기본 동작을 바꾸지 않는다 — 신규 노출은 전부 opt-in이며 키 부재는 현재 동작이다.
- 커밋·main 병합·push·release는 사용자 승인 전 수행하지 않는다.
