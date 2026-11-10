# Overlay 전달 통합 설계 — Claude 적대적 리뷰 3회 기록

- 대상: `2026-11-04-overlay-delivery-unification-design.md`
- 실행: Claude Code CLI, 실제 응답 모델 `claude-opus-5-5`
- 방식: 서로 다른 새 세션 3개. 문서·코드 발췌를 stdin으로 제공한 tool-less 적대적 설계 검토
- 순서: 1차 → 지적 검증·설계 수정 → 2차 → 지적 검증·설계 수정 → 3차 → 지적 검증·최종 문서 반영
- 제품 코드·설치·실제 압축 시험은 실행하지 않았다. 이번 3회를 정식 SAGE L3 리뷰 또는 제품 승인으로 집계하지 않는다.

## 1. 실제 실행 신원

| 회차 | 입력 설계 SHA-256 | Claude session | 보고된 지적 항목 |
|---|---|---|---:|
| 1 | `beeba1c98a0f5867233b77bd3411177f8adf8457c9b2bfaaa430f50a9f723a23` | `1a672b0a-fcd4-48ff-8f43-499df26d76fc` | 7 |
| 2 | `83d4e674d1f6abdfd7c502a55c5e94c56a7a3ac06a4296fcb9a9badffb52f286` | `5809c191-48ed-4c5a-b59f-27dc8c338043` | 6 |
| 3 | `b236a236234e14cd4a5c5589bcca7ecae2eda7506cb0e024cb039ab9987823cc` | `1e316f82-9ee6-4136-a84e-a09600f4da46` | 5 |

각 호출은 `subtype=success`, `is_error=false`, `num_turns=1`을 반환했다. 항목 수는 리뷰별 보고 수이며, 같은 문제의 재지적·구체화가 있어 독립 버그 18개라는 뜻은 아니다. 이전 분석 자문과 builder check는 이 세 번에 포함하지 않았다.

원문과 입력 snapshot은 다음 경로에 보존했다.

- [1차 원문](/Users/sejon/project/sage_project_worktree/overlay-adversarial-3rounds-dopq734_/round-1-review.txt)
- [2차 원문](/Users/sejon/project/sage_project_worktree/overlay-adversarial-3rounds-dopq734_/round-2-review.txt)
- [3차 원문](/Users/sejon/project/sage_project_worktree/overlay-adversarial-3rounds-dopq734_/round-3-review.txt)
- [입력/응답 신원 메타데이터](/Users/sejon/project/sage_project_worktree/overlay-adversarial-3rounds-dopq734_/review-metadata.json)

## 2. 1차 지적과 판단

판정 요지: 범위는 대체로 일관되지만 대상 신호·상속 자격·오류 복구·예산에 결정 공백이 있음.

| ID | 지적 | 판단·반영 이유 |
|---|---|---|
| R1-F1 | compact에 선택 대상 신호가 없는데 상태도 쓰지 않음 | 채택. phase 추측을 금지하고, 실패 시 임의 fallback 대신 설계 정지 조건을 명시. 새 상태 자동 채택 제안은 보류했다가 2차의 구체적 반례로 최소 영수증 결정만 승격 |
| R1-F2 | 표준 출처의 자격으로 Fast 차단을 우회할 수 있음 | 채택. Fast 대상 자격 → 출처 검증 → 네 슬롯 구성 순서와 open/convert 자기 승인 유도 fixture 추가. 실제 독립 floor 성립은 D3 미실행 |
| R1-F3 | 개인 오류가 baseline·재진입 및 wire까지 깨뜨릴 수 있음 | 채택. 독립 결과 수집·단일 host 응답·본문 없는 오류 명시. 기존 L1 조기 반환까지 정리하는 구체화는 R2-F2에 반영 |
| R1-F4 | 큰 입력 예산과 설정 변경 방침 모순, 이중 채널 | 부분 채택. handler의 출력 상한 설정과 신뢰 우회는 다르므로 구분. 무제한 기본값 금지·spill 실패·채널 혼재 시험 추가. Fast 디스크 정책은 R3-F1에서 확정 |
| R1-F5 | root/worktree의 없음·미전달 구분이 없음 | 부분 채택. 이벤트 cwd/명시 root와 검사 경계 표 추가. 다만 worktree에 개인 파일이 실제 없는 것은 기존 checkout별 소유 계약상 정상 부재이며 부모 개인 파일을 자동 승계하지 않음 |
| R1-F6 | child/reviewer에 부모 규칙이 들어갈 수 있음 | 채택. 런처의 packet 문맥과 root 전달을 분리. 표지 없으면 compact/resume으로만 좁히자는 제안만으로 자식 격리가 입증되지는 않으므로 채택하지 않음 |
| R1-F7 | headless 충돌 처리와 현재 CORE의 의미가 없음 | 부분 채택. 비대화는 BLOCKED 상위 보고, CORE는 현재 호출 스킬로 명시. 표준 phase 문장을 Fast로 자동 번역하라는 제안은 원문 의미 변경이므로 제외 |

## 3. 2차 지적과 판단

판정 요지: 범위·결정 시험 초안으로 조건부 진행 가능하나 전체 root 묶음·오류 처리·버전 식별·상속 공격 시험에 모순이 있음.

| ID | 지적 | 판단·반영 이유 |
|---|---|---|
| R2-F1 | 7종 전체 주입은 일반/Fast 분리와 실제 최대 예산을 위반 | 채택. 전체 묶음 후보를 폐기하고 선택 대상 payload로 축소. 현재 일반 payload의 Fast 0바이트와 역사적 Fast 문맥을 구분하며 둘 다 시험 |
| R2-F2 | 기존 공유 L1 early return이 baseline·재진입 보존을 깨뜨림 | 채택. 단지 새 return을 금지하는 것에 그치지 않고 기존 조립 경로도 최소 정리. 공유 오류·L1 쓰기 실패·개인 오류 각각+compact 시험 추가 |
| R2-F3 | 진단만 내면 fail-closed가 fail-open으로 바뀔 수 있음 | 핵심 채택, 제안 해법은 수정. 공유만 전달+STOP 산문으로 해결하지 않음. 새 payload는 원자적 실패, 실제 native 차단 필수. host가 제공하지 못하면 D1/DC6 실패이며 제품 지원 완료로 세지 않음 |
| R2-F4 | 개인 CLI와 훅의 이중 읽기, A/B hash와 05 참조 모호 | 채택. 현재 payload가 있으면 중복 CLI 지시 제거. 한 수집 결과로 검사·hash·전달, 요청 경계 기준 신원, 실제 전달한 ref 사용. 새 B 실패 시 A 재사용 금지 |
| R2-F5 | 악성 표준 슬롯이 Fast 공격 시험에서 빠짐 | 채택. 공유/개인 × 표준/Fast 네 슬롯 모두 Fast BACKING의 적대적 범위에 포함 |
| R2-F6 | root 이동·표지 없는 child 판정 기준이 모호 | 채택. 미주입 기본값과 식별/중단 검증 명시. 식별할 수 없는 필수 진입을 조용히 제외하지 않고 설계 차단으로 둠. 3차에서 경로 목록을 더 구체화 |

## 4. 3차 지적과 최종 반영

판정 요지: 결정 시험 명세는 대체로 일관되나, **명세를 차단하는 지적 3건(F1~F3)**과 이후 구현 조건 2건(F4~F5)이 남았음. 아래 수정은 이 응답을 받은 뒤 반영했다. 4차 재검토를 받았다는 뜻은 아니다.

| ID | 지적 | 최종 설계 반영·판단 |
|---|---|---|
| R3-F1 | Fast 디스크 공유 사본이 별도 부분 채널로 재첨부됨 | 채택. Fast 3종은 overlay 허용과 디스크 합성 여부를 분리하고 payload 전용으로 고정. 과거 host 문맥을 삭제할 수 있다는 주장은 하지 않음 |
| R3-F2 | 새 payload의 전부/전무가 기존 디스크 채널과 별도 읽기를 놓침 | 채택. 원자적 실패의 범위를 신규 payload로 명시하고 잔여 표준 사본이 있어도 native 차단 필수. 같은 SessionStart의 L1과 payload는 한 수집 결과 사용 |
| R3-F3 | D1 허용 신호와 필수 진입 목록이 없어 판정 불가 | 채택. Claude slash/Skill, Codex 명시/암묵, 위임·복귀, headless, compact/resume/worktree를 명시. host 해석 정보/SAGE handoff/동등성을 검증한 제한 parser만 후보로 허용. 자발적 영수증 명령 단독 금지. Codex 신호의 실현 가능성은 아직 미확인 |
| R3-F4 | 현재 영수증의 대체·종료·복귀 수명 공백 | 채택. 현재 포인터의 원자적 대체, handoff 결합 복귀, 종료 해제와 지연 결과 대조 규칙 추가. 관측할 실제 신호의 존재는 D1에서 입증해야 함 |
| R3-F5 | 기존 표준 overlay가 업그레이드로 Fast에 새 영향을 줌 | 부분 채택. 기존 파일+업그레이드 직후 첫 Fast fixture와 본문 없는 상속 출처 안내를 추가. Fast 필드 lint 확대는 필요성 평가 없이 자동 채택하지 않으며 lint만으로 사용자 동의를 보증하지 않음 |

## 5. 왜 범위를 이렇게 바꿨는가

1. **모든 규칙 동시 주입을 버림:** 일반 작업에 Fast 규칙이 섞이는 반례가 있어 전달 대상과 예산을 줄였다.
2. **Fast payload 전용:** Fast 렌더의 부분 공유 사본과 네 슬롯 전체 묶음이 따로 움직이는 직접 원인을 제거한다.
3. **기존 복구 경로만 최소 정리:** 새 전달 기능이 baseline·재진입을 가리거나 wire를 깨뜨리지 않게 한다. 다른 gate를 전면 개편하지 않는다.
4. **한 번 읽은 내용으로 처리:** 디스크 A와 payload B가 같은 시점의 정상 결과처럼 섞이는 것을 막는다. 큰 잠금·DB 시스템은 추가하지 않는다.
5. **필요한 식별 정보만 검토:** compact에 대상이 없으므로 최소 영수증/host 식별자 재사용을 검토하되, 선택 신호가 없는데 있다고 가정하지 않는다.

## 6. 현재 남은 상태

- 요청된 Claude 적대적 리뷰 3회와 각 회차 뒤의 문서 수정은 완료했다.
- 마지막 지적 반영본의 4차 리뷰, D1~D3 실측, 제품 구현·패키지·실제 압축 검증은 미실행이다.
- 특히 **Codex의 선택 대상 신호, Claude/Codex의 해당 이벤트 native 중단, 중첩 복귀·worktree 연결**은 구현 전에 풀어야 한다. 지원 경로를 제외하거나 수동 읽기로 바꿔 해결됐다고 보고하지 않는다.
- 따라서 현재 산출물은 **검토 지적을 반영한 설계·결정 시험 명세**다. 무지적 수렴·설계 승인·구현 착수 가능한 최종 알고리즘 확정을 주장하지 않는다.

[수정 설계안](2026-11-04-overlay-delivery-unification-design.md) · [그림으로 보는 ELI5 설명](2026-11-04-overlay-delivery-eli5.html)
