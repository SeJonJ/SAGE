# [Base Plan] SAGE-FB-03 Manual Double-Host 운영 모델

Cycle-Stem: `sage-fb-03-manual-double-host`
Risk Level: L3

## 1. Problem

manifest는 여러 host 설치를 기록하지만 profile과 Phase 05 reviewer는 `runtime.host` 하나만 본다. 사용자가
Claude에서 00~02를 작성하고 Codex에서 수동 재개해도 현재 host 정본과 반대 reviewer 선택이 일치한다는 보장이 없다.

## 2. Boundary

- 두 host의 SAGE discovery surface 설치를 허용한다.
- 한 시점/사이클의 active host는 하나만 허용한다.
- phase 자동 전환, 동시 실행, 세션 전달 자동화는 하지 않는다.
- 작성된 phase 문서의 exact Cycle-Stem이 수동 재개의 상태 전달 계약이다.

## 3. Impact

- SAGE engine/profile/doctor/review/generate/install docs and tests: affected.
- ChatForYou Backend/Frontend/Desktop source: N/A.

