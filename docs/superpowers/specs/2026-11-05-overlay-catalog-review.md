# 대상별 문맥 묶음 설계 — 검토·최소 실현성 기록

- 작성일: 2026-11-05
- 대상: [재설계 권고안](2026-11-05-overlay-context-catalog-design.md)
- 범위: 설계 검토와 격리 probe. 제품 구현·출시 승인·구현 후 L3 리뷰가 아니다.

## 1. Claude 추가 아키텍처 자문

- session: `07032d49-d5b6-4c6d-a95e-463536447e52`
- 실제 모델: `claude-opus-5-5`
- 결과: success, is_error=false, num_turns=1.
- 입력: 새 catalog 후보, 기존 호스트 관측, 현재 자격 분류 코드 발췌. 전체 제품 실행이나 저장소 직접 검토는 하지 않은 tool-less 자문이다.
- 판정: **전달 구조로 조건부 채택 가능. 승인 단계는 아니며 예산·compact·scope/역할 검증 필요.**
- [입력](/Users/sejon/project/sage_project_worktree/overlay-catalog-redesign-neptj1og/catalog-challenge-prompt.txt) · [원문](/Users/sejon/project/sage_project_worktree/overlay-catalog-redesign-neptj1og/catalog-challenge-review.txt)

| 지적 | 처분 |
|---|---|
| catalog도 다른 대상 본문에 노출되며 JSON을 안전 경계로 부르면 안 됨 | 채택. 바이트 노출·적용 범위·의미 준수 검증을 구분하고 Fast 0바이트 조건 철회 사실 명시 |
| 많은 turn의 누적 및 첫 요청 두 사본 비용 | 채택. startup은 UPS로 공급하는 별도 native 시험 수행. 재개/압축의 두 사본 및 여러 turn 비용은 acceptance에 포함 |
| Codex compact 경로 불명 | 새 native probe로 보완. 실제 수동 compact 이벤트와 다음 요청의 14개 본문 관측. 자동 압축·실제 모델 요약은 미확인 |
| scope/selector 소실과 요청 없는 Fast 전환 | 채택. 실제 작은 scope 표본과 제품 반복/압축 시험을 분리. 새 방식 때문에 Fast 자동 개방이 재현되면 A3로 출시 차단 |
| empty catalog로 이전 source 무효화 | 채택. 마지막 파일 삭제 후 빈 generation을 공급하며 hash/mtime으로 최신 순서 추론 금지 |
| blocked 자산 실행에도 다른 root source가 노출됨 | 채택. 자기 적용 자격과 타 source 노출을 구분. blocked view를 만들지 않으며 프로필 floor 변경 반례 추가 |
| 모호한 child에는 누락 방지를 위해 root 주입 | 채택하지 않음. 역할 오매핑을 피하려고 새 root 주입은 하지 않음. 부모가 이미 상속한 과거 본문까지 삭제했다고 주장하지 않음 |
| 모든 worker 개인 본문도 즉시 자동화 | 이번 필수 범위로 승격하지 않음. 원 제보의 세 증상은 스킬에 관한 것. 7종 스킬과 기존 worker packet 회귀를 범위로 고정하고, native worker 자동화는 재현·중요도로 평가할 추가 후보로 명시 |
| Fast 확인자 문자열 한계가 구조 floor 부재와 같지는 않음 | 채택. 기존 한계를 숨기지 않되 구조 BACKING·네 슬롯 적대 시험을 생략하거나 단순 92 PASS로 자격 개방하지 않음 |
| guard는 문맥 존재를 보증하지 않고 입력만 재검사함 | 채택. hook 미실행/timeout/구버전의 한계도 명시 |

## 2. 독립 builder check

새 문서를 전달받은 fresh Codex 에이전트 `catalog_design_builder_check`가 구현 계획 전에 필요한 질문만 읽기 전용으로 제시했다. 세 건 모두 다음처럼 결정했다.

| 질문 | 결정·반영 |
|---|---|
| UPS가 막힌 상태에서 대화 안 복구 요청은 어떻게 받는가 | 기본 수리는 호스트 밖 터미널/에디터. 수리 후 다음 입력 재검사. 대화 수리용 allowlist/새 승인 체계를 만들지 않음 |
| child에게 root 본문이 없어야 하는가, 새로 주입하지 않는 것인가 | 새 역할 packet에 root catalog를 추가하지 않는 계약. 부모 문맥 상속까지 지웠다는 보장은 하지 않음. 독립 리뷰의 clean-context 경계는 유지 |
| 구조 gate가 통과한 Fast 자동 전환을 잔여 위험으로 수용 가능한가 | 새 catalog 때문에 요청 없는 Fast 개방이 재현되면 A3 실패. 구조 GREEN만으로 수용하지 않음. 수정 불가면 catalog 안을 거절 |

같은 reviewer의 후속 읽기 확인에서 §8/11/12와 M5/A3/A5 사이에 세 결정의 모순이 없고, **그 세 결정에 관한 중요한 미해결 질문이 없다**는 응답을 받았다. 전체 코드 정확성이나 A1~A8 통과를 승인받았다는 뜻은 아니다.

## 3. Native 채널 관측

모의 모델에 연결한 실제 설치 CLI를 사용했다. 합성 catalog는 root 7종 × 공유/개인 14개 원문 token과 대상별 출처 배열로 구성했다. 제품 validator·hash 구현은 이 fixture에 들어 있지 않다.

| 사례 | 실제 관측 |
|---|---|
| Codex 구조화 표준/Fast 선택 | 각각 선택 스킬 본문은 달랐고 두 요청 모두 14개 catalog token을 수신 |
| Codex 수동 compact | 두 thread에서 `thread/compact/start`, 각각 SessionStart compact 관측. 다음 요청에도 14개 token 있음 |
| Claude startup | 실제 요청에서 14개 token 있음 |
| startup 공급을 UPS로 미룬 대조 시험 | Claude 1개 요청, Codex 2개 선택 요청 각각 한 catalog 사본과 14개 token 있음 |

자료는 `/Users/sejon/project/sage_project_worktree/overlay-catalog-redesign-neptj1og/`의 `codex-ui-catalog*`, `claude-catalog*` 아래에 있다. 자동 압축이나 실제 모델 의미 적용의 근거로 재사용하지 않는다.

## 4. 실제 모델의 작은 scope 동작

각 source는 고유 token을 결과에 추가하는 규칙을 담고, native 합성 스킬은 자기 target view만 적용하도록 했다. 일반/Fast의 source 배열을 모델이 구별하는지 보는 시험이며 제품 행동 전체의 검증이 아니다.

| 호스트 | 실제 모델 | 진입 | 결과 |
|---|---|---|---|
| Codex | `gpt-6.1-sol` | 구조화 Skill, 표준 1회 | 공유 표준+개인 표준 2 token만, 순서 일치 |
| Codex | `gpt-6.1-sol` | 구조화 Skill, Fast 1회 | 공유 표준+공유 Fast+개인 표준+개인 Fast 4 token만, 순서 일치 |
| Claude | `claude-opus-5-5` | native Skill, 표준 1회 | 대응 2 token만, 순서 일치 |
| Claude | `claude-opus-5-5` | native Skill, Fast 1회 | 대응 4 token만, 순서 일치 |

Claude 유효 표본 session은 각각 `f274666a-45dc-4e3b-bf40-1b4185c0d551`, `5db8d438-bc50-4e51-b7d9-5f4d4bfa6614`다. 앞선 tool-less slash 시도 두 번은 스킬이 활성화되지 않아 제외했다. 이를 실패 은폐 없이 별도 자료로 남기고, 정상 scope 표본을 더해 성공률 4/6처럼 계산하지 않는다. 제외 원인은 시험 진입 구성 문제이며 scope 적용 회귀와 다른 분모다.

Codex 실모델 driver의 원래 `result.json`에 있는 `requests=0`은 **사용하지 않은 로컬 모의 서버의 요청 수**다. 실제 네트워크 요청 0건이라는 뜻이 아니다. 실모델 실행/결과 근거는 `app-events.json`의 두 thread/turn과 agentMessage다.

- [Codex 실제 응답 이벤트](/Users/sejon/project/sage_project_worktree/overlay-catalog-redesign-neptj1og/codex-ui-behavior/app-events.json)
- [Claude 유효 결과](/Users/sejon/project/sage_project_worktree/overlay-catalog-redesign-neptj1og/claude-behavior-results.json)
- [파생 scope 대조 결과](/Users/sejon/project/sage_project_worktree/overlay-catalog-redesign-neptj1og/scope-assessment.json)

계정 인증 내용은 보고서에 포함하지 않았다. Codex 시험은 격리 home에서 기존 CLI 인증을 로컬 참조했고, 시험 후 해당 임시 symlink만 제거했다. 사용자 인증 원본과 전역 설정은 수정하지 않았다.

## 5. 남은 검증

실제 제품 CORE, 큰 한국어/escape payload, 여러 turn 누적, 양 호스트 자동 압축, Claude 수동 압축, resume/fork, 중첩/blocked/역할 혼입, 오류와 외부 복구, 기존 source 업그레이드, Fast 네 슬롯 적대 공격, 설치/패키지 소비자 검증은 새 설계의 A1~A8로 수행해야 한다. 작은 표본을 이 전체의 완료 근거로 사용하지 않는다.
