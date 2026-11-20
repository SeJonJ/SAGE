# 설계와 작업 순서

Cycle-Stem: egm-plan-review
Document-Language: ko
Done-Criteria-Revision: 2

`sage plan-review --root ROOT --host claude|codex --stem STEM --plan PATH [--plan PATH] [--source PATH] [--timeout 300] [--max-input-bytes 1048576] [--output PATH] [--json]`.

검사 순서: 문법 → root/프로필 → OFF → 계획 정체성/실제 위험 → 제외 수준 → host 일치 → 명시 원천/최종 prompt 상한 → 저장 위치 사전검사 → 통제된 단일 실행 → 입력 재대조 → 저장/표시. 새 cycle 선언이나 Fast audit open을 요구하지 않는다. 파일 내용을 읽은 순간의 bytes를 hash와 prompt에 함께 사용한다. 링크 자동 탐색·대화 이력·추가 파일 탐색·테스트·빌드·쓰기·하위 agent는 검토 계약에서 금지한다. 자료 안의 지시는 검토 대상이다.

runner에 선택 인자 `contract`와 `require_controls=False`만 추가한다. 기존 기본 계약은 유지한다. 새 명령은 `runtime_hosts.peer_env`를 사용하고 Phase05 overlay/policy를 호출하지 않는다. 출력에는 findings/검토 범위/미확인 범위를 요구하며 별도 finding parser나 승인 엔진을 만들지 않는다.

실행 전 INVALID_INPUT(2), SKIPPED(0), UNSUPPORTED(3); 실행 후 STALE(3)을 우선하고, 통제 위반/실패는 본문 유무에 따라 PARTIAL/FAILED(3), 정상 실행은 COMPLETE(0). 저장 실패는 원래 실행 상태/원문을 stdout에 보존하되 FAILED(3)로 보고한다. JSON은 CLI가 새 파일로 직접 저장한다. 계획 변경 후 기존 hash 결과를 현재 계획의 완료 증거로 재사용하지 않는다.

순서: 실패 테스트 → 입력/프로필 계약 → runner 통제 → CLI 실행/저장 → 스킬/문서 → 회귀/패키지 검증 → 별도 예산의 실제 모델/독립 리뷰. 설계 리뷰에서 제기된 통제 위치·결과 직접 저장·구성 축소·검토 범위 보고를 반영했다. 256KiB 축소와 STALE 정상 완료 취급은 채택하지 않는다.

## 지적 처분

개발 후 독립 지적은 ID/근거/처분/이유/수정 검증을 기록한다. 정규1라운드 확정5건 수정과 실제 외부 closed 확인, F1~F4 보완 확인을 마쳤다. 이후 누락 인수 증거를 채워 E01~E12가 모두 PASS이며, 최신 Codex 종합 독립 확인과 새 전체 지적 반박자2명이 CLEAR다. Phase05는 APPROVED로 완료했다. 새 R-01은 비정상 native item.type의 유효 LOW 한계로 수용하고 R-02는 기존 CLI 인코딩 보호로 두 명 모두 반박했다. 기술 타당성을 무시하거나 필수 미검증을 면제하지 않았다. 상세 처분과 범위는 Phase05에 보존한다.
