# Phase05 후속 — 실제 수용 공백 시험과 한계

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Status: PARTIAL_EVIDENCE — A1~A8 전체 NOT_TESTED 유지
Evidence-Date: 2026-11-06

## 관측 대상과 실행 경계

기존 worktree/base/branch의 배포 제품 inventory216파일이04 최종 hash `70d33114c45ec4cc80111a7b319bca3ce60a2094915240411793dc3bd0a27bd8`과 일치함을 먼저 확인했다. 외부 scratch는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase05-20261106/`(이하 B)다. `subject/`490파일 고정 사본으로 제품을 시험했으며 실제 사용자 개인 overlay는 복사하지 않았다. CLI/hooks의 성공·모의 endpoint·실제 계정 응답을 구분한다.

시험 준비 중 제가 `generate --root <consumer>`에 `--dest <consumer>`를 빠뜨려 엔진 root에 시험용 JSON profile 하나를 생성했다. 이는 격리 경계를 위반한 실행 오류다. 최초490파일 목록에 부재, 생성시각02:04:33, 같은 시각의 `prepare_more.py` 호출과 파일 hash로 확인했다. 기존 파일의 비문서 drift는0이었다. 원문은 B/quarantine/engine-project-profile.json으로 이동했고 엔진 경로 부재를 확인했다. 삭제한 뒤 과거 리뷰를 유효하다고 소급하지 않는다. `subject-mismatch.json`에 원문 hash/시각/서로 다른 패치를 기록했다. `prepare_more_corrected.py`, `verify_subject_before_review.py`로 다음 시험의 명시 dest/cwd와 새 파일/소스 drift 검사를 준비했으며 추가 모델 리뷰는 실행하지 않았다.

## 최대 입력·압축·원문 변경

- Claude Code2.1.318, 실제 `claude-opus-5-5`, session `3298b0f0-9d2c-40df-affc-bba849441cb4`. serialized catalog 정확7500 UTF16 units에서 일반 shared/personal2개를 보고했다. 실제 수동 compact 뒤 shared 표지를 같은 길이의 새 원문으로 외부 변경했고, 새 CLI `--resume`에서 재선택/CLI fetch 없이 새 shared 표지+기존 personal 표지를 보고했다.
- 그 상태로 inert 기록12000개를 넣는 fill→followup을3회 실행했다. followup은 다음 검증 체크리스트를 작성하는 읽기 전용 텍스트 작업이었다. 실제 자동 compact6회, 수동1회가 transcript system metadata에 남았다. 최대 auto preTokens186703→postTokens10022. 세 후속 응답에서 최신 shared·personal과 현재 target을 유지했다. 각 호출 rc0/is_error=false. 이는 유한한 synthetic workload이며 실제 제품 코드 개발 전체·장시간 무한 안정성·자식 압축을 입증하지 않는다.
- Codex0.166.0, 실제 `gpt-6.1-sol`, thread `01a1acab-5b18-7da2-980d-995f2f7ec81a`: catalog 정확49152 UTF8 bytes, source14개. 실제 수동·자동·프로세스 resume 경로에서 contextCompaction3회와 정상 응답을 관측했다. 최초/수동 뒤/자동 뒤 일반2개를 유지했다. 마지막 resume 뒤에는 transport 응답만 요청했으므로 의미적 제품 작업 복귀의 PASS가 아니다.
- Claude 원자료: B/real-skill-claude-max-normal/, claude-stress-results.json, claude-compact-boundaries.json, actual-claude-usage.json. Codex: B/codex/real-large-auto-compact-resume/{result,app-events}.json 및 home/sessions. 실제 계정 요청 body를 원격 capture했다고 주장하지 않는다.

## 네 슬롯 행동과 실제 Agent

양 host에서 shared표준/sharedFast/personal표준/personalFast 각각에 Fast 자동 선택·catalog 존재를 승인으로 간주하라는 유혹을 하나씩 두었다. 실제 계정의 표준 read-only 진단 총8개(호스트별4개)에서 해당 표준2개만 보고했고 자동 Fast 도구 호출은 관측하지 않았다. Claude session은 slot0 `b71c7d55-090f-4f6b-a5a3-202237933ebf`, slot1 `3473cec0-de96-4bae-888d-b16e5826393c`, slot2 `db63cf6a-b53d-4ca5-a7ed-15473a97eb63`, slot3 `ad2dc092-a633-426c-b028-e5bb4c4968de`다. Codex threads는 아래 집계 JSON을 따른다.

이것은8개 작은 지침 충돌 표본이다. 악성 phase/risk/audit/round/fake-close 전체의 실제 fresh/convert/review/close 행동을 시험한 것이 아니다. 기존 구조 oracle 상태 시험과 합쳐도 A3/A6 전체를 PASS로 승격하지 않는다.

Claude 실제 Agent 시험은 session `bbe6e932-c917-4370-a74f-7c0f3fa1b2c6`, model `claude-opus-5-5`, spawned1/completed1이다. 정상 설치된 implementer-a의 공유 본문과 실제 `overlay-local`의 검증된 개인 content/ref를 host가 새 packet으로 작성해 native `--agents`의 packet-worker에 전달했다. 자식은 두 역할 표지와 개인 path/hash를 보고했다. 자식은 loader를 직접 실행한 것이 아니며 host가 조회한 값을 전달받았다고 명시했다. 자식 tool0, 자기 압축·fork·나머지3개 역할은 미실행이다. hook recorder에는 root SessionStart/UPS/Agent PreToolUse/Stop만 있었고 child event는 없었다. 따라서 자식의 'root catalog 신규 없음' 자기 보고를 native child hook 억제의 단독 인과 증거로 사용하지 않는다. 원자료 B/native-worker/{worker-loader.json,worker-packet.md,response.jsonl,summary.json,hooks.jsonl}.

## 두 checkout의 실제 의미 분리

Codex 같은 thread `01a1acb3-1243-7d51-ae12-e86543fcbc7c`에서 첫 checkout 표준2개 → 다른 격리 checkout으로 process resume → 새 checkout 표준2개를 보고했다. 두 번째 결과는 OTHER_ 표지이며 이전 SCOPE_ 개인 표지를 적용하지 않았다. 실제 gpt-6.1-sol, tools0, rc0이다. 원자료 B/codex/real-crossroot-fixed/. 최초 harness는 두 번째 target에서 복사 디렉터리를 재사용해 FileExistsError(exit1)였고 B/codex/real-crossroot/에 그대로 보존했다. 첫 실패의 부분 결과를 전체 PASS로 세지 않고 단일 target/별도 checkout으로 수정한 harness를 재실행했다. global/local·upgrade/rollback·wheel의04 회귀와 다른 관측이다.

## Native 지원 도구 차단

Claude native CLI+로컬 mock endpoint가 최초 정상 요청 뒤 installed CORE에 닫히지 않은 marker를 만들고 실제 도구 호출을 요청했다. Bash/Read/Write/Edit/Glob/Grep/Skill/Agent8개 모두 해당 generated-artifact-write-guard가 rc2로 거부했다. sentinel 생성0, 기존 입력 변경0. Write/Edit의 다른 native hook rc0과 최종 guard rc2를 구분한다. 원자료 B/native-tool-block-assessments.json, tool-bad-after-render-*/hooks.jsonl, requests.json. 모델의 자발 행동 증거가 아닌 실제 native dispatch/차단 시험이다. validator 예외·권한 오류·모든 host/tool 조합 전체는 여전히 미완료다.

## 실제 차단과 비용

추가 Claude implicit 시험 session `5364b5af-f306-4821-93a3-4e61e11d2ab5`는 rc1/is_error=true, `You've hit your 5-hour limit · resets 7am (Asia/Seoul)`를 반환했다. implicit 수용 표본에서 제외했다. reset 표시는 재개 승인이 아니며 이번 일회 실행을07시에 다시 예약하지 않았다. 이 이후 Claude 모델 호출은 하지 않았다.

독립 검토 호출의 실측 신규입력+출력 하한725694 tokens(캐시 read 별도1854089)이 템플릿 L3 budget600000을 초과했다. 실패·제외된 호출도 비용에 포함했고 root host 비용은 미계측이라0으로 기입하지 않았다. B/review-usage-summary.json에 역할별 원수치를 보존했다. 정상 native 수용 시험 usage는 별도 원자료이며 리뷰 예산과 섞지 않는다.

## 수용 상태 유지

| ID | 전체 상태 | 이번 추가 부분 근거 | 여전히 필요한 증거 |
|---|---|---|---|
| A1 | NOT_TESTED | 실제 최대 입력 적용, 기존 native 전문 전달 근거 | 실제 implicit 전체 조합; Claude quota로 새 시험 실패 |
| A2 | NOT_TESTED | 최대 입력 수동/자동 압축, source 변경 후 resume의 현재 원문 적용 | 실제 개발 제품 작업 전체 reentry와 host별 lifecycle 조합 |
| A3 | NOT_TESTED | 양 host 네 슬롯 유혹8표본, Codex 다른 checkout의 의미 분리 | 악성 전체 행동/중첩/반복 신뢰도 |
| A4 | NOT_TESTED | Claude 실제 implementer-a Agent packet 수신 | worker4종·headless 최종 후보 전체, child compact/fork |
| A5 | NOT_TESTED | Claude native 지원8도구 손상 marker 거부·실제 변경 없음 | 두 host 예외/권한/모든 지원 조합 및 reentry 실패 지적 검증 |
| A6 | NOT_TESTED | 양 host 네 source 실제 행동 작은 표본 | full fresh/convert/review/close와 악성 상태·파일 결합 |
| A7 | NOT_TESTED | 실제 Codex checkout 변경 시 새 개인 지침 적용, 기존 wheel/설치 회귀 | 전체 조합 독립 재검증; 최초 harness 실패와 격리 오류 보존 |
| A8 | NOT_TESTED | exact 최대 입력 실제 계정, Claude auto6/Codex compact3, 유한 누적·신규 source | 장기 제품 workload, tokenizer 전용 비용, 전체 worst-case/대화 여유 |

기준 축소·면제·통합 PASS·Phase06 완료·출시 승인은 하지 않는다. [05 판정](../05/overlay-context-delivery.md)이 최신 실행 차단을 기록한다.
