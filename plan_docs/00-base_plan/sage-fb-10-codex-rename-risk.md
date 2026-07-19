# [Base Plan] SAGE-FB-10 Codex rename 목적지 L3 분류 우회 차단

Cycle-Stem: `sage-fb-10-codex-rename-risk`
Risk Level: L3
Status: COMPLETE

## 1. Context

Codex `apply_patch` pre-implementation 입력 파서는 `Add|Update|Delete File:`만 change set에
포함하고 `Move to:` 목적지는 버린다. 따라서 저위험 출발지를 L3 경로로 rename하면 파일명 기반
게이트가 출발지만 분류해 L3 계획·리뷰 절차를 우회할 수 있다. post-tool logger는 이미 목적지를
파싱하므로 사전 게이트와 사후 로그의 입력 의미도 서로 다르다.

## 2. Goal

- rename 출발지와 목적지를 모두 pre-implementation change set에 포함한다.
- 두 경로 중 높은 위험도가 전체 변경 위험도가 되게 한다.
- rename과 함께 추가되는 내용이 source/destination 어느 쪽에서도 content-L3 분류를 잃지 않게 한다.
- malformed 또는 목적지만 보이는 입력도 목적지 위험을 fail-safe하게 분류한다.

## 3. Scope

In scope:

- `scripts/sage_harness/hooks/runtime/io_codex.py`의 `extract_changes`
- Codex change extraction 및 gate classification 회귀 테스트
- 항목 전용 Phase 00~06 문서와 Claude fresh headless 3회 리뷰

Out of scope:

- branch 숫자/cycle 결속(SAGE-FB-01/11)
- profile 타입 검증(SAGE-FB-13)
- `extract_phase4_changes`의 rename 정책 변경
- `apply_patch` 문법 자체의 재구현

## 4. Impact

- SAGE runtime: Codex PreToolUse gate 입력 정규화가 바뀐다.
- Claude runtime: 영향 없음. Claude는 단일 `file_path` 입력을 사용한다.
- ChatForYou application Backend/Frontend/Desktop: 직접 코드 영향 없음.
- Security/governance: rename으로 L3 filename gate를 우회하던 경로를 차단한다.

## 5. Prior Knowledge

- 요구사항 정본: `SAGE - ChatForYou 실증 2차 후속 개발 요구사항 (26.07.17)` SAGE-FB-10.
- 재현: harmless source를 L3 destination으로 이동하면 기존 extractor는 source만 반환했다.
- 사후 logger의 `extract_logged_changes`는 `Move to:`를 이미 파싱한다.

## 6. Done Criteria

1. source와 destination이 모두 change set에 존재한다.
2. 현재 L0-first carve-out과 겹치지 않는 destination-only L3 glob이 `classify_risk`에서 L3로 판정된다.
3. rename patch의 추가 내용이 content-L3 분류에 반영된다.
4. 기존 add/update/delete extraction이 회귀하지 않는다.
5. 결정론 테스트와 전체 관련 테스트가 통과한다.
6. 서로 이어받지 않는 Claude headless 세션 3회 리뷰를 거치고, 각 발견을 수용/기각 근거와 함께 기록한다.
