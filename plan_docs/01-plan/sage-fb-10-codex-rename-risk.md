# [Plan] SAGE-FB-10 Codex rename 목적지 L3 분류 우회 차단

Cycle-Stem: `sage-fb-10-codex-rename-risk`

## 1. Requirements (Acceptance Matrix)

| Acceptance ID | Requirement | Required |
|---|---|:---:|
| FB10-AC1 | `Update File: source`와 `Move to: destination`을 모두 정규화한다. | yes |
| FB10-AC2 | 현재 risk precedence에서 L0로 carve-out되지 않은 destination의 L3 filename glob이 전체 변경을 L3로 승격한다. | yes |
| FB10-AC3 | rename hunk의 추가 내용이 source와 destination change 양쪽에 연결된다. | yes |
| FB10-AC4 | orphan `Move to:` 입력도 destination change를 보존한다. | yes |
| FB10-AC5 | add/update/delete와 logger extraction의 기존 계약이 유지된다. | yes |
| FB10-AC6 | Claude fresh headless 코드 리뷰를 3회 수행하고 타당성 판정을 기록한다. | yes |

## 2. Input Contract

입력은 Codex `apply_patch` command 문자열이다. 지원 marker는 다음과 같다.

- `*** Add File: <path>`
- `*** Update File: <path>`
- `*** Delete File: <path>`
- `*** Move to: <destination>`

출력은 `[{path, op, content}]`이며 rename은 source update와 destination move 두 엔트리로 표현한다.

## 3. Failure Policy

- 목적지를 못 찾았을 때 조용히 source-only로 축약하지 않는다.
- marker가 비정상 순서로 오더라도 식별 가능한 destination은 보존한다.
- parser는 실제 파일을 읽지 않으며 patch payload만 결정론적으로 정규화한다.

## 4. Verification Matrix

| Scenario | Expected |
|---|---|
| low-risk source -> L3 destination | L3 filename classification |
| L2 source -> L2 destination + L3 keyword | content-L3 classification |
| orphan Move to L3 destination | destination change retained |
| ordinary multi-file add/update/delete | existing output unchanged |

## 5. Boundary with SAGE-FB-07

하나의 destination이 `l0_pass_globs`와 `l3_filename_globs`를 동시에 만족할 때 현재 엔진은 L0-first로
판정한다. 이 우선순위 자체를 바꾸는 것은 도메인별 L0 예외 계약인 SAGE-FB-07 범위다. FB-10은
rename이 기존 분류기에 source와 destination을 모두 전달하도록 보장하지만 risk precedence를 재정의하지 않는다.
