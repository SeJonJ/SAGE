# 03 CORE와 전달 문서 구현 증거

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Status: IMPLEMENTED — 지정 문서/스킬 변경, native acceptance 미실행

## 변경 범위

- `templates/core/skills/`의 sage-cycle/plan/team/review와 cycle-fast/plan-fast/team-fast 7종 spec, 대응 `templates/core/framework/.claude/skills/<id>/SKILL.md` 7종 render.
- `docs/sage_harness/hooks/`의 generated-artifact-write-guard, capture-declared-risk, session-start-snapshot 3종 계약.
- `docs/ARCHITECTURE{,.en}.md`, `docs/troubleshooting{,.en}.md`, `docs/cli-reference{,.en}.md`의 overlay 관련 계약과 해당 영어 문서의 source-hash 헤더.
- 이 증거 문서 이외의 제품 Python·테스트·설치 설정·manifest 파일은 이 역할에서 수정하지 않았다.

## 구현한 계약

7종 spec/render frontmatter 바로 뒤에 같은 내용의 고정 자기 id selector를 넣었다. schema 2 root/role/generation과 현재 경계 확인, sources의 실제 전달 문자열과 refs, 표준 두 슬롯/Fast 네 슬롯의 정확한 순서, 필수 CORE·프로젝트·독립 gate > 공유 > 개인, 미선택 원문 적용 금지, catalog를 호출·Fast 전환·사람 승인으로 해석하지 않는 계약이다.

현재 경계의 빈 catalog도 이전 지침을 대체한다. 과거 hash/mtime로 freshness를 추론하지 않으며 root/role/generation·현재 대상이 불명확하면 중지한다. 실제 compact 뒤 수동 재선택을 자동 복구 성공으로 보고하지 않는다. 부모→자식 plan/team/review는 자기 view로 바꾸고 복귀 시 부모 view를 쓰며 DB를 추가하지 않는다.

root 7종의 `sage overlay-local --kind skill ...` 실행 의존은 제거했다. worker는 자신의 kind/id로 loader를 호출해 기존 역할별 shared/personal 본문과 실제 refs를 packet에 전달하는 경로를 보존했다. `sage review`/`sage cross-check`의 reviewer CLI 1회 로딩과 `SAGE_LOCAL_OVERLAY_REF` 예외도 유지했다. catalog 전체를 worker packet에 전달하지 않는다.

Fast spec의 overlay unsupported 문구는 독립 구조 oracle과 standard+Fast 자동 공급 계약으로 바꾸었다. 기존 profile opt-in·Hard boundary·실제 risk·명시 사용자 Fast 입력·변환 승인·review/close 절차는 유지했다. CLI 문자열이나 공급 사실이 사람 동의 진위를 인증한다고 표현하지 않았다.

hook spec은 양 host PreToolUse matcher `*`, 공통 입력검사 후 기존 write/path gate, UPS 단일 JSON과 invalid inventory native block, SessionStart startup 본문 defer와 resume/fork/compact 재공급을 기술한다. 기존 write-once 06 baseline과 compact reentry 결과를 별도 보존한다. 읽기/Bash 포함 넓어진 입력 차단과 원래 쓰기 경로 판정을 구분한다.

한영 안내는 7종 scope, 같은 문맥 노출과 적용 구분, 외부 수리, 개인 원본/전역 비노출, 소유 확인 legacy span 제거와 worker span 보존, doctor와 실제 전달/행동 검증 구분을 반영했다. 잠정 source 10,000 UTF-8 bytes/catalog 49,152 UTF-8 bytes/Codex limit 60,000 및 byte 기반 보수적 token 상한을 실측 지원 확정으로 표시하지 않았다.

## 개발 중 직접 검토

- 7쌍의 selector 본문을 추출·대조: 모두 spec/render 동일, 자기 고정 id 일치. 표준 4종은 각 두 refs, Fast 3종은 표준 공유→Fast 공유→표준 개인→Fast 개인의 네 refs를 직접 확인했다.
- 지정 파일의 `sage overlay-local --kind skill`, Fast unsupported, CORE보다 overlay 우선이라는 이전 문구를 검색해 제거 범위를 확인했다. CLI reference의 skill loader 예시는 수동 진단으로 명시해 유지했다.
- hook3종 diff를 직접 읽어 matcher `*`, JSON 출력과 baseline/위임 경계의 일치를 확인했다. 기존 Phase·risk·review·close 본문은 보존했다.
- 한영 문서 링크·7개 id·기존 CLI 명령 철자를 검토했고 변경한 한영 3쌍의 영어 source-hash 헤더를 현재 한국어 파일 hash에 맞췄다.
- 첫 `git diff --check`에서 Fast 6개 파일의 EOF 빈 줄을 발견해 제거했다. 지정 소유 파일 범위의 최종 `git diff --check`는 exit 0으로 통과했다.

이 작업은 문서/스킬 지침 변경이므로 문구 assert만 하는 테스트 파일을 추가하지 않았다. 제품 collector/runtime 통합 테스트는 각 제품 코드 소유자가 기록한다.

## 미실행과 열린 수용 조건

이 역할은 04~06 문서를 만들거나 실제 native/모델 acceptance를 실행하지 않았다. 현재 호스트에 설치·활성화됐다는 증거도 이 변경에 포함되지 않는다. A1~A8은 unchecked이며 특히 실제 자동 압축·중첩 복귀·다른 target 유혹·Fast 자동 선택 방지·지원 도구 coverage·전역/로컬 설치·최대 입력/두 hook 사본 비용은 후속 승인된 검증이 필요하다. 커밋·푸시·배포하지 않았다.


## R1 잔여 문서·절차 수리 — 2026-11-06

DOC-R1-01의 한영 architecture/troubleshooting 4개 문서에서 낡은 Phase04 미검증 표현을 제거하고 관측한 Claude2.1.318/Codex0.166.0의 유한 검증과 미실행 범위를 구분했다. 영어 source hash를 한국어 전체 bytes와 정렬했다.

C4-P-03: sage-profile-modify는 YAML 직접 편집과 derived JSON 생성을 구분하고, 외부 generate(기존 설치 host target 유지) → 필요한 routing sync → validate/doctor → 다음 경계 검증 순서로 정리했다. sage-asset-override는 physical worker/routing 변경의 외부 sync와 유효한 root context-only/personal 입력의 비물리 경로를 구분했다. sage-init와 공용 bootstrap-authoring은 활성 hook이 도구를 차단할 때 Auto 승인으로 우회할 수 없다는 외부 복구 조건을 명시했다. 세 spec/render와 공유 참조만 변경했다.

별도 tool-less 모델 세션의 입력·응답·SHA·usage는 B/supplement-r1/authoring-* 및 authoring-procedure-assessment.json에 보존했다. profile baseline은 generate 금지 때문에 JSON 복구 명령을 빠뜨렸고 수정 후 정확한 순서를 제시했다. override baseline은 context-only 예외를 판별하지 못했고 수정 후 구분했다. init baseline은 외부 복구를 이미 추론했으므로 행동 RED라고 주장하지 않는다. 기존 Auto 문구와 실제 활성 hook 차단의 통합 충돌을 명시적으로 정렬했으며 후속 응답은 이를 따른다. 초기 qa(차단 대상) 시나리오는 유효 worker 근거에서 제외하고 비용만 보존했다. 단일 표본을 모든 미래 모델 준수 보장으로 확대하지 않는다. 독립 코드 리뷰를 대체하지 않는다.

검증: skill interview coverage 17 PASS, bilingual documentation 18 PASS, git diff --check exit0. 커밋·푸시·실사용 설치는 하지 않았다.
