# [Plan] SAGE-FB-08 서버측 PR-diff 권위 게이트와 attestation

Cycle-Stem: `sage-fb-08-server-authority-attestation`
Risk Level: L3

## 1. Acceptance Matrix

| ID | Requirement | Required? |
|---|---|:---:|
| FB08-AC1 | git base/head full blob과 rename 양 경로를 구조화하고 삭제 content 우회를 차단한다. | yes |
| FB08-AC2 | base policy와 head policy로 각각 분류한 뒤 최고 위험도를 적용한다. | yes |
| FB08-AC3 | pure-core CI 판정은 local override/waiver audit을 읽거나 실행하지 않는다. | yes |
| FB08-AC4 | attestation은 issuer/repository/base/head/diff/cycle/risk/verdict/nonce/expiry에 서명 결속된다. | yes |
| FB08-AC5 | 서명·claim·만료·expected binding 오류와 secret 부재는 모두 BLOCK한다. | yes |
| FB08-AC6 | L3는 exact cycle의 Phase 00~05와 APPROVED Phase 05를 요구한다. | yes |
| FB08-AC7 | CLI는 PR head 파일을 shell/import하지 않고 git object로만 읽는다. | yes |
| FB08-AC8 | 보호 workflow template은 pull_request_target, 최소 권한, fork secret 부재 BLOCK을 명시한다. | yes |
| FB08-AC9 | three independent Claude review rounds와 finding triage를 완료한다. | yes |

## 2. Authority Contract

- required check의 고유 이름은 `sage-authoritative-gate`로 고정한다.
- caller workflow는 default branch 보호 revision에서 실행되어야 하며 SAGE engine ref는 40-hex commit SHA여야 한다.
- 검증 대상 checkout에서는 어떤 executable도 실행하지 않는다. `git diff`, `git show`, `git ls-tree`로 data만 읽는다.
- attestation key는 command line 인자가 아닌 환경변수/파일 descriptor로만 전달한다.
- fork/Dependabot에서 protected secret이 없으면 neutral/advisory가 아니라 exit 2 BLOCK이다.

## 3. Delivery Split

FB-08은 engine API, CLI, reusable template, local fixture 검증까지 완료한다. 원격 SAGE ref 게시, ChatForYou
workflow 실행, expected source 지정, required check/ruleset 적용 증명은 FB-09가 담당한다.
