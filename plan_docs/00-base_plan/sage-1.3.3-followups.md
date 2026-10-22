# [기본 계획] 1.3.2 후속 세 가지 — 코드 블록 닫힘·경로 표기·선언 등급 순서 (1.3.3)

Cycle-Stem: `sage-1.3.3-followups`
Document-Language: ko
Risk Level: L3
Status: COMPLETED — 05 codex cross-review 2차 APPROVED, 06 작성(2026-10-22). 설계는 자체 리뷰 3회·codex 설계 리뷰 3회. 사용자 승인으로 커밋·머지·1.3.3 배포(2026-10-23)
Done-Criteria-Revision: 1

## Phase 00 — 기본 계획

### 배경

- 1.3.2(#23) 작업 중 발견했거나 범위를 지키려고 뺀 세 가지다. 사용자 결정(2026-10-22): 1.3.2 를 먼저 내고 1.3.3 에서 다룬다. **세 가지를 무조건 고치지 않는다.** 중요도·위험도·재현도·수정 범위·수정 공수로 판정한다.
- 판정 기준(이 문서 전체 공통)
  - **중요도:** 결함이 실제로 일어났을 때의 결과. 조용히 틀림(사용자가 모름) > 보이는 과차단 > 경고 하나 차이.
  - **위험도:** 고쳤을 때 기존 동작이 바뀌어 생길 수 있는 피해(회귀 가능성).
  - **재현도:** 실제 사용 기록·문서에서 관측한 빈도. 이론상 가능한 것과 관측된 것을 나눠 적는다.
  - **수정 범위:** 바뀌는 모듈·호출부·호스트.
  - **수정 공수:** 코드·시험·문서·리뷰 예상량. 과거 같은 영역의 리뷰 이력을 포함한다.
- 측정은 개인 프로젝트 자료만 쓴다(ChatForYou·GMA·SAGE·weatherapp 시험 프로젝트·개인 위키). 측정 스크립트와 결과는 작업 scratchpad `133/` 에 있다.
- 측정의 한계: 한 사람의 사용 기록이다. Claude 작업 기록은 보존 기간 때문에 2026-09~10 의 52개 세션만 남아 있고, codex 세션은 2026-04~10 이다. 「관측 0건」은 「일어나지 않는다」가 아니다.
- Windows 실기(1.3.2 의 X3)도 이 사이클에서 한다.

### 판정 요약

| | 1. 코드 블록 닫힘 | 2. 경로 표기 | 3. 선언 등급 순서 |
|---|---|---|---|
| 중요도 | 중간 — 문서의 예시 블록이 결속·승인·Done Criteria 판정을 양방향으로 틀리게 한다(중복 오류로 막히거나, 예시의 `APPROVED` 를 승인으로 읽음) | 중간 — 일어나면 위험 규칙을 **조용히** 비켜 감 | 기본 구성 낮음, 사용자 정의 구성 중간 — 단조 profile 은 높은 등급에서 새로 필수가 되는 phase 문서 작성만, 비단조 profile(높은 등급이 더 적게 요구)은 소스 편집 차단까지 높은 선언이 푼다. 선언 없는 판정보다 느슨하지는 않음 |
| 위험도(고칠 때) | 낮음 — 실제 문서에서 판정이 바뀌는 경우 0건. 단 승인 판정도 바뀌는 수정이라 양방향 시험이 필요 | 정규화(A)는 높음(경로 판정 이력) / 감지(B)는 낮음 | 래퍼 확장(A)은 중간 — 의도된 교착 해소 면제와 충돌 |
| 재현도 | 사이클 문서 557개에서 네 판정 함수의 전체 출력이 바뀌는 문서 0개 | 실제 편집 경로 8,289개 중 0개 | 기본 템플릿·실제 profile 0건(2,304 쌍). 사용자 정의 profile 에서만 |
| 수정 범위 | hook 3개 모듈의 닫힘 조건(CI·CLI 공용) | 정규화: `make_rel` + hook 4개 / 감지: 게이트 1곳 | 판정 래퍼 또는 profile 검증 |
| 수정 공수 | 작음 — 소스 세 줄, 시험 10건 안팎, spec 문구 | 정규화: 큼(1.3.2 설계 리뷰 경로 반례 5건 중 4건) / 감지: 작음 — core·runtime·messages·i18n, 시험 10건 안팎, troubleshooting | 래퍼 확장 작음 / profile 검증 작음 — 검사 하나, 진단 키·ko/en, 시험 5건 안팎 |
| **권장** | **수정**(A) | **감지만 수정(경고)**(B), 정규화는 계속 보류 | **profile 검증 경고**(B) + 문서 작성 면제는 계약으로 명시(C) |

### 1. 코드 블록 닫힘 판정

**현상.** 사이클 문서의 구조 선언(`Cycle-Stem:`·`Final Status:`·Done Criteria 절·Fast 증거 줄)은 코드 블록 밖의 줄만 읽는다. 펜스 판정 코드가 세 곳에 복사돼 있다.
- `cycle_binding.non_fenced_lines` — `Cycle-Stem`, 게이트의 `Final Status`(`pre_implementation_gate_core._final_status`)
- `done_criteria_contract._visible_lines` — Done Criteria 절 파싱(CLI·CI 권위 판정 공용)
- `fast_cycle_contract.evidence_marker_issues` — Fast 증거 줄(CLI·CI 권위 판정 공용)

펜스 열림·닫힘 판정은 세 곳이 같다(나머지 — HTML 주석, 들여쓴 줄 처리 — 는 조금씩 다르다). 세 곳 모두 블록이 열린 상태에서 **같은 문자·같거나 긴 길이로 시작하는 줄이면 뒤에 글자가 있어도 닫는다.** CommonMark 는 닫는 펜스 뒤에 공백 말고는 아무것도 허용하지 않는다(```` ```python ```` 은 블록 안의 내용이다).

**재현(v1.3.2 소스, 직접 호출).**

| 문서 | 사람이 보는 것(CommonMark) | SAGE 판정 |
|---|---|---|
| 맨 위 `Cycle-Stem: real` + 3개 백틱 블록 안에 ```` ```yaml ```` 예시와 `Cycle-Stem: example` | 선언 1개 | `Cycle-Stem declaration must appear exactly once (found 2)` → 차단 |
| 맨 위 `Cycle-Stem: real` + 블록 안 ```` ``` 끝 ```` 줄 뒤 `Cycle-Stem: example` | 선언 1개 | 같은 차단 |
| 자기 선언이 없는 문서 + 위 예시 | 선언 0개 | 예시 stem 에 **조용히 결속** |
| 05 문서: 머리 `Cycle-Stem` + 블록 안 ```` ```yaml ```` 예시와 `Final Status: APPROVED`(진짜 판정 줄 없음) | 판정 줄 없음 | `APPROVED` 로 읽어 06 작성 통과(codex 직접 호출) |
| 블록 밖 `APPROVED` + 블록 안 예시 `BLOCKED` | 판정 `APPROVED` | 중복 오류로 차단 |

- 틀리는 방향이 양쪽이다. 「선언·판정이 2개」라는 **보이는 차단**도 있고, 예시의 `APPROVED` 를 진짜 승인으로 읽는 **조용한 오판**도 있다. Done Criteria 절과 Fast 증거 줄도 같은 방식으로 예시를 읽는다.
- 사람이 보는 문서와 SAGE 가 읽는 문서가 달라 원인을 찾기 어렵다.

**재현도(실측).** 개인 프로젝트·위키의 마크다운을 지금 규칙과 권장안 A(닫힘 조건만 바꿈)로 각각 읽었다.
- `Cycle-Stem` 이 있는 사이클 문서 557개에 **실제 판정 함수**(`declared_stem`, 게이트의 `Final Status` 판독, `parse_done_criteria` standard·fast 의 **전체 결과**(`dataclasses.asdict`), `evidence_marker_issues`)를 돌려 비교 — 바뀌는 문서 **0개**. 첫 측정은 Done Criteria 결과를 잘라 비교해 차이를 놓칠 수 있었다(codex 2회차) — 전체 비교로 다시 쟀고, 그 비교가 반례 문서(완료 12 + 잘못 닫힌 블록 안 미완료 예시 → 미해결 1→0)의 차이를 잡는 것도 확인했다.
- 코드 블록이 있는 마크다운 3,012개 중 블록 밖 줄이 달라지는 문서 10개 — 전부 사이클 문서가 아니다(외부 플러그인 문서, 위키 대화 기록).

**선택지.**

| 안 | 내용 | 평가 |
|---|---|---|
| A. 닫힘 조건만 CommonMark 로 | 세 곳의 닫힘 조건에 「펜스 뒤에는 ASCII 공백·탭만」(`[ \t]*`)을 더한다. 유니코드 공백(U+00A0 등)은 닫힘이 아니다(CommonMark 0.31.2). 여는 조건·들여쓰기 규칙은 그대로 | 바뀌는 판정은 실측 0건. 한 줄씩 세 곳 |
| B. 공용 함수로 합치기 | 세 모듈이 한 함수를 쓰게 한다 | 세 모듈은 서로 import 하지 않는 독립 모듈이고(엔진 `sage/` 가 재수출), 소비자 프로젝트에 파일로 복사된다. 의존을 새로 만들면 배포 구조를 건드린다 |
| C. 그대로 둔다 | — | 실제 피해 0건이지만, 문서 예시를 쓰는 순간 원인을 알 수 없는 차단이 난다 |

**권장: A.** 세 곳의 펜스 판정이 같은지는 시험으로 묶는다(F3). B 는 하지 않는다.

**바뀌는 방향.** A 는 판정을 양쪽으로 바꾼다 — 승인 판정도 포함한다. 위 표의 예시 `APPROVED` 문서는 「통과 → 승인 없음 차단」으로, 밖 `APPROVED` + 안 `BLOCKED` 문서는 「중복 오류 → 승인」으로 바뀐다. Done Criteria 는 블록 안 미완료 예시가 빠져 미해결 수가 줄 수 있고, Fast 증거는 중복 오류가 사라질 수 있다. 모든 변화는 「GitHub·CommonMark 에서 코드로 보이는 줄을 SAGE 도 코드로 본다」는 한 방향이다 — 사람이 본 판정과 SAGE 판정이 같아진다. 두 방향을 모두 시험으로 고정한다(F6).

**영향 범위.** 세 판정은 hook 뿐 아니라 `sage review-loop`·`sage fast-cycle`·CI 권위 판정(`ci_authority`)도 쓴다. 소비자 프로젝트의 PR CI 결과가 바뀔 수 있다. 실측은 0건이지만 다른 사용자의 문서는 모른다 — 릴리즈 노트에 「뒤에 글자가 붙은 펜스 줄은 더 이상 블록을 닫지 않는다」를 적는다.

**하지 않는 것.**
- 목록·인용 안 펜스, 여는 펜스의 정보 문자열 검사(백틱 펜스 정보에 백틱 금지) — 1.3.2 표식 판정에서 이 방향의 반례가 세 차수 연속 나왔다. 지금 실측 차이도 없다.
- `sage/commands/knowledge.py`·`absorb.py` 의 펜스 판정 — vault 마커용으로 계약이 다르다.

### 2. 경로 표기

**현상.** `hook_runtime.make_rel` 은 경로를 **글자로** 루트와 비교한다. 같은 프로젝트 파일을 다른 표기로 쓰면 `<outside-project>` 가 되고, 위험 규칙(`src/**` 등)·사이클 검사를 받지 않고 **조용히 통과**한다. `make_rel` 은 hook 4곳(구현 전 게이트, post-tool logger, Phase 4 체크리스트 게이트, project hook)이 쓴다.

| 표기 | macOS·Linux | Windows |
|---|---|---|
| 루트 대소문자 변형 | 밖 | 안(`ntpath` 가 대소문자 무시) |
| 루트로 가는 심볼릭 링크 별칭, `/tmp`↔`/private/tmp` | 밖 | 밖 |
| 루트 짧은 이름(`PROJEC~1`), subst 드라이브 | — | 밖 |

**재현도(실측).** 개인 프로젝트의 실제 편집 기록에서 경로를 세었다.
- Claude Code 작업 기록의 Write·Edit 1,160건, codex 세션의 실제 `apply_patch` 호출 3,752건(호출 ID 로 중복 제거, 경로 7,129개) — 별칭·대소문자 변형으로 프로젝트를 가리킨 경우 **0건**. 첫 codex 측정은 이벤트 종류를 보지 않고 패치 문자열을 세어 편집이 아닌 출력까지 셀 수 있었다(codex 3회차) — 실제 호출만 다시 셌다.
- 신뢰 경계: SAGE 는 「정직한 호스트의 실수를 막는다」(ARCHITECTURE). 일부러 별칭을 쓰는 에이전트는 범위 밖이다.

**과거 이력.** 경로·디렉터리 판정은 같은 종류의 리뷰가 길어진 영역이다(프로젝트 루트 탐색, override 저장소 키의 realpath, 운영 진단 사이클). 1.3.2 설계 5판의 `make_rel` 재작성은 codex 설계 리뷰 1~3회의 경로 반례 5건 중 4건을 만들었다 — 끊긴 링크, `..` 를 접는 순서, Windows 짧은 이름, 루트 **안** 링크를 풀어 보호 경로가 바뀌는 문제.

**선택지.**

| 안 | 내용 | 평가 |
|---|---|---|
| A. 정규화 | `make_rel` 이 루트 별칭을 실제 루트로 풀어 상대 경로를 만든다 | 고치는 것이 근본. 하지만 hook 4곳의 경로가 바뀌고, 루트 안 링크·대소문자 복원·짧은 이름을 다루는 순간 1.3.2 설계 리뷰의 반례 계열로 돌아간다. 실측 0건에 비해 공수·위험이 크다 |
| B. 감지만(경고) | 게이트가 `<outside-project>` 인데 「확인된 밖」이 아닌 경로를 만나면 경고한다. 경로 판정은 바꾸지 않는다 | 조용한 통과를 **보이는 경고**로 바꾼다. 1.3.2 의 `_outside_confirmed` 를 그대로 쓴다. 실제 밖 편집 491건 중 경고가 났을 경우 0건 |
| B'. 감지 후 차단 | B 와 같으나 차단 | 정직한 실수는 경고로 고쳐진다. 하드 링크·권한 오류처럼 「확인 못 한 진짜 밖」을 막게 되고 override 경로를 새로 설계해야 한다 |
| C. 보류 유지 | — | 실측 0건. 하지만 일어나면 조용하다 |

**권장: B.** 일어나면 조용하다는 점이 남는 이유이고, B 는 판정을 바꾸지 않아 경로 이력의 반례 계열을 피한다. A 는 로드맵 보류 행(`make-rel-path-normalization`)으로 계속 둔다.

**B 설계.**
- `hook_runtime.run_pre_implementation_gate` 는 이미 밖 원경로를 모아 `_outside_confirmed` 를 부른다(1.3.2). 변경 중 하나라도 「밖이지만 확인 안 됨」이면 `event["outside_unconfirmed"] = [원경로…]` 를 싣는다.
- core: 최종 판정이 통과면 경고 `warn_path_outside_unconfirmed`(파일·「프로젝트 경로로 다시 써 주세요」)로 올린다. 경고·차단이면 판정 키는 그대로 두고 `outside_unconfirmed` 를 판정에 싣는다.
- override: 활성 override 로 차단을 우회하면 `render_gate` 를 거치지 않고 돌아가고, override 알림은 stderr 에만 나간다. 통과 시 모델에게 닿는 채널은 호스트별 비차단 컨텍스트(`hookSpecificOutput.additionalContext`, ARCHITECTURE 의 전달 계약)다. 그래서 우회 성공 뒤 경로 진단은 그 채널로 따로 보낸다. 시험은 문자열이 아니라 호스트별 JSON 봉투까지 확인한다.
- 표시: 기존 경고 병합은 첫 경고의 키만 남기고, `warn_phase_incomplete` 같은 키는 사유를 출력하지 않는다(codex 직접 호출로 확인). 그래서 경로 진단은 판정 키에 기대지 않고, `gate_text` 가 `outside_unconfirmed` 가 있으면 어떤 판정이든 보조 줄 하나를 덧붙인다(1.3.2 의 `declaration_only` 줄과 같은 방식). 다른 경고·차단과 함께 나는 경우의 표시 시험을 둔다.
- 다른 hook 3곳은 바꾸지 않는다(위험 규칙을 적용하는 곳은 게이트 하나다).
- `_outside_confirmed` 가 거짓이 되는 진짜 밖(하드 링크 파일, 대소문자만 다른 별도 폴더, 조회 오류)은 경고가 난다. 차단이 아니라 작업은 막히지 않는다. 실제 밖 편집 491건(Claude 작업 기록)을 **지금의 파일 상태로** 돌려 보면 0건이다 — 편집 당시의 링크·권한 상태는 재현하지 못하므로 당시 오경고율의 증거는 아니다.
- 루트 설정 자체가 별칭이면(예: 프로젝트 경로 환경변수는 링크 경로, 도구는 실제 경로) 모든 편집이 경고한다. 지금은 이 경우 게이트가 사실상 꺼진 채 조용하다. 경고 문구에 「프로젝트 경로 설정도 확인」을 넣는다.

**닫히지 않는 것.** B 는 구멍을 **보이게** 할 뿐 닫지 않는다. 경고를 무시하면 위험 규칙은 여전히 적용되지 않는다. 사용자가 처음 요청한 「기존 구멍도 함께 수정」에 해당하는 것은 A 이고, 이 문서는 A 를 권하지 않는다 — 근거는 위 재현도(0건)와 과거 이력이다. A 를 원하면 별도 결정이 필요하다.

### 3. 선언 등급끼리의 순서

**현상.** 1.3.2 는 「선언한 판정 ≥ 선언하지 않은 판정」을 구조로 보장했다. 「높은 선언 ≥ 낮은 선언」은 보장하지 않는다. 원인은 의도된 교착 해소 면제다 — 바꾸는 phase 문서가 그 등급의 필수 목록 안이면 결핍 검사를 건너뛴다(L2/L3 를 선언하면 01 을 쓰려는 편집이 02·03 부재로 막히는 교착을 풀려고 둔 것). 등급이 높을수록 필수 목록이 넓어져 면제가 더 자주 켜진다.

**재현.**
- codex(1.3.2 설계 리뷰 4회차): 필수 phase L1=`[00,01]`, L2·L3=`[00,01,02,03]`, 00 만 있음, 02 문서 작성 → 선언 L1 경고, L2·L3 통과, 미선언 통과.
- codex(이 문서 리뷰 1회차): L1=`[00]`, L2=`[00,01]`, L3=`[00,01,02,03]`, 00(L3)만 있음, 유효한 `Cycle-Stem` 의 02 작성 → 선언 L2 `block_phase_incomplete`(01 결핍), L3 `ok_l3`, 미선언 통과. **경고가 아니라 차단이 풀린다.**

**재현도(실측).** 첫 측정은 틀렸다 — phase 문서 쓰기에 `Cycle-Stem` 이 없어 결속 단계에서 먼저 막혀 면제 차이를 재지 못했다(codex 지적). 유효한 phase 문서 쓰기와 전략 결과(있음·없음)로 다시 쟀다. 경로 8(00~04 문서, 소스, 일반 문서, L2 경로) × 있는 phase 조합 8 × 00 등급 3 × 전략 2, 등급 쌍 6 = profile 마다 2,304 쌍.

| profile | 뒤집힌 쌍 | 경로 |
|---|---|---|
| 기본 템플릿(L1=`[00]`, L2·L3=`[00..03]`) | 0 | — |
| weatherapp 시험 프로젝트(L2·L3=`[00,01,02]`) | 0 | — |
| L2=`[00,01]`, L3=`[00..03]` | 8 (차단→통과) | 02·03 문서만 |
| L1=`[00,01]`, L2·L3=`[00..03]` | 40 (경고→통과) | 02·03 문서만 |

실제 개인 프로젝트 profile 5개는 기본 템플릿 또는 weatherapp 형태다. 측정한 두 profile 에서 뒤집힘은 모두 02·03 문서 작성에서만 나왔고 소스·일반 문서 편집에서는 0건이다.

**영향.** 사용자 정의 profile 에서, 높은 등급을 선언하면 낮은 등급 선언에서는 막히던 **높은 등급에서 새로 필수가 되는 phase 문서의 작성**이 통과할 수 있다(측정한 profile 에서는 02·03, codex 3회차 재현에서는 01 — L2=`[00,02]`, L3=`[00..03]`). 이것은 교착 해소 면제가 의도한 동작(그 등급이 요구하는 문서는 순서와 무관하게 쓸 수 있다)이 낮은 등급과 비교될 때 드러나는 것이다. 단조 profile(L1⊆L2⊆L3)에서는 소스 편집의 차단이 풀리지 않는다 — 소스 편집은 phase 작성 면제를 받지 않고, 높은 등급의 결핍 목록이 낮은 등급의 것을 포함한다. **비단조 profile 에서는 소스 편집 차단도 풀린다**(codex 2회차 재현: L1=`[00]`, L2=`[00,01]`, L3=`[00]`, 00 만 있음, `src/x.py` → 선언 L2 `block_phase_incomplete`, L3 `ok_l3`). 이 profile 을 `sage validate` 는 지금 아무 경고 없이 받는다. 어느 경우도 선언 없는 판정보다 느슨하지는 않다(1.3.2 보장).

**선택지.**

| 안 | 내용 | 평가 |
|---|---|---|
| A. 래퍼 확장 | 선언 등급 이하 모든 등급으로 판정해 가장 엄격한 쪽 | 코드는 작다. 하지만 L2 교착 해소 면제가 막으려던 경고를 L1 판정이 다시 들여온다 — 면제의 의도와 충돌하고 「L2 를 선언했는데 L1 요구를 안내」하는 문구가 된다 |
| B. profile 검증 | `pre_implementation_required` 가 L1⊆L2⊆L3 가 아니면 validate 경고. 생략된 등급은 빈 목록으로 비교, pdca 비활성이면 생략 | 소스 편집까지 풀리는 비단조 반례를 잡는다. 단조 profile 의 계획 문서 반례는 못 잡는다. `profile_validate` 에 검사 하나, 진단 키·ko/en 문구 |
| C. 계약으로 명시 | 교착 해소 면제를 명시적인 계약으로 적고, 단조 profile 의 계획 문서 역전을 알려진 한계로 남긴다 | 기본·실제 profile 0건 |

**권장: B + C.** 소스 편집까지 풀리는 경우는 비단조 profile 에서만 나고, B 가 정확히 그 profile 을 잡는다 — 비용이 작고 기존 profile(기본·실제 5개)에는 경고가 나지 않는다. 단조 profile 의 계획 문서 역전은 교착 해소 면제의 의도된 결과라 C 로 계약에 적는다. 게이트 spec 은 지금 「declared ≥ undeclared 만 보장하고 등급끼리는 비교하지 않는다」고만 적고 있어 **차단까지 풀릴 수 있다**는 사실과 범위가 빠져 있다. 단조 profile 의 계획 문서 역전은 사용자 승인으로 받아들이는 잔여 위험이다. A(래퍼 확장)는 하지 않는다.

### 범위

- 포함: 1-A(세 곳 닫힘 조건 + 일치·양방향 시험), 2-B(게이트 경고 + 보조 줄 표시 + override 알림), 3-B(profile 검증 경고) + 3-C(spec·troubleshooting 에 남는 역전 범위 명시), Windows 실기(1.3.2 X3 + 2-B), manifest.
- 제외: 1-B 공용 함수, 2-A 정규화(로드맵 보류 유지), 2-B'(차단), 3-A 래퍼 확장.

### Done Criteria
- [x] 세 블록 판정이 「뒤에 글자가 있는 펜스 줄」을 닫힘으로 보지 않고, 같은 입력에서 세 판정이 일치한다
- [x] 사이클 문서 실측 묶음에서 네 판정 함수의 출력이 바뀌지 않고, 반례 문서에서는 CommonMark 와 같은 판정으로 바뀐다
- [x] 확인 안 된 밖 경로의 진단이 다른 경고·차단과 함께 나도 화면에 보인다
- [x] `sage validate` 가 비단조 `pre_implementation_required` 에 경고한다
- [x] 게이트 spec·troubleshooting 이 남는 등급 역전(단조 profile 의 계획 문서 작성)을 적는다
- [x] 게이트가 확인 안 된 밖 경로에 경고하고, 차단 판정과 확인된 밖 경로는 바뀌지 않는다
- [x] `make_rel` 출력과 hook 4곳의 경로 판정이 바뀌지 않는다
- [x] Windows 11 실기: 1.3.2 X3(다른 드라이브 밖 통과, 짧은 이름 루트는 확인 실패)과 2-B 경고
- [x] spec·troubleshooting(ko/en)·manifest 갱신, 관련 회귀 스위트 통과
- [x] codex cross-review APPROVED

## Phase 01 — 요구사항

### Acceptance Matrix

| ID | 내용 | 증거 | 필수 |
|---|---|---|---|
| F1 | 세 판정에서 ```` ```python ````·```` ``` 끝 ```` 은 열린 블록을 닫지 않는다 | 단위 시험 | yes |
| F2 | 펜스 뒤 공백만 있는 줄, 더 긴 펜스는 닫는다. 다른 문자(`~~~` 안의 ```` ``` ````)는 닫지 않는다(지금과 같음) | 단위 시험 | yes |
| F3 | HTML 주석·들여쓴 줄이 없는 입력 묶음에서 세 판정의 「블록 밖 줄」이 같다(펜스 전이 일치) | 일치 시험 | yes |
| F4 | 위 재현 표의 세 문서: 선언 1개로 결속, 자기 선언 없는 문서는 「선언 없음」 | 단위 시험 | yes |
| F5 | 실측: 사이클 문서 557개에서 네 판정 함수 출력 변화 0 | 측정 기록 | yes |
| F6 | 양방향 고정: 블록 안 예시 `APPROVED` 만 있는 05 → 06 작성 차단, 밖 `APPROVED` + 안 예시 `BLOCKED` → 승인, 블록 안 미완료 Done Criteria 예시는 미해결로 세지 않음, Fast 증거 예시 중복 없음 | 단위 시험 | yes |
| P1 | 선언 없음 + 루트 별칭(링크·`/private/tmp`·대소문자)으로 쓴 `src/x.py` → `warn_path_outside_unconfirmed` | hook 경유 시험 | yes |
| P2 | 확인된 밖 → 경고 없음(지금과 같음) | 시험 | yes |
| P3 | 차단 판정 + 확인 안 된 밖 → 차단 그대로 | 시험 | yes |
| P4 | `make_rel` 출력 불변(기존 시험) | 시험 | yes |
| P5 | ko/en 문구, recovery 없음(경고) | 시험 | yes |
| P6 | `warn_phase_incomplete` 등 다른 경고·차단과 함께 나도 보조 줄이 출력된다 | 표시 시험 | yes |
| P7 | 활성 override 로 차단을 우회할 때도 경로 진단이 호스트별 비차단 컨텍스트(JSON 봉투)로 나간다(claude·codex) | runtime 시험 | yes |
| F7 | 닫힘 꼬리에 U+00A0 등 유니코드 공백이 있으면 닫지 않는다 | 단위 시험 | yes |
| M1 | `pre_implementation_required` 가 L1⊆L2⊆L3 가 아니면 `sage validate` 가 WARN(어느 등급의 어떤 phase 가 빠졌는지), 단조 profile·기본 템플릿은 무경고. 생략된 등급은 게이트와 같이 빈 목록으로 비교한다(L3 생략 + L2=`[00,01]` → 경고) | validate 시험 | yes |
| M3 | `pdca.enabled: false` 면 단조성 경고를 내지 않는다(게이트가 강제하지 않으므로) | validate 시험 | yes |
| M2 | 비단조 profile 반례(L2=`[00,01]`, L3=`[00]`)에서 소스 편집 역전이 실제로 나는 것을 시험이 기록하고 M1 경고가 같은 profile 에 나온다 | core·validate 시험 | yes |
| L1 | 게이트 spec·troubleshooting(ko/en)에 등급 역전과 그 범위 | 문서 시험 | yes |
| W1 | Windows 11: 다른 드라이브 밖(선언 L3) 통과, 짧은 이름 루트 → 확인 실패(1.3.2 X3) | 실기 기록 | yes |
| W2 | Windows 11: 짧은 이름 루트로 쓴 소스 → 2-B 경고 | 실기 기록 | yes |
| X1 | spec·troubleshooting ko/en·manifest | 문서 시험 | yes |

## Phase 02 — 설계

00 의 「B 설계」·선택지 표가 설계 본문이다. 여기는 구현 단위로 내린 결정만 적는다.

### 1. 코드 블록 닫힘
- 세 모듈의 닫힘 조건에 `not raw[<match>.end():].strip(" \t")` 를 더한다. 여는 조건·들여쓰기·HTML 주석 처리는 그대로다. 공용 함수로 합치지 않는다.
- `runtime/prose_language.py` 는 이미 「꼬리가 비어야 닫힘」 규칙이다(`.strip()` 이라 U+00A0 도 공백으로 본다). 문서 언어 검사 전용이고 이번 세 판정과 계약이 달라 바꾸지 않는다.

### 2. 확인 안 된 밖 경로
- runtime: `outside_raw` 의 모든 원경로에 `_outside_confirmed` 를 불러 거짓인 것을 `event["outside_unconfirmed"]`(순서 유지 중복 제거)로 싣는다. `outside_confirmed` 는 「목록이 비었음」으로 같은 값을 낸다.
- core: 기존 `decide()` 를 `_decide_declared()` 로 옮기고, 새 `decide()` 가 그 결과에 경로 진단만 덧붙인다. 통과(`status == "ok"`)는 `outside_unconfirmed_warning(paths)` 를 병합해 경고로 올린다(결속 정보 유지). 경고·차단은 `outside_unconfirmed` 만 싣는다.
- `outside_unconfirmed_warning(paths)`: `warn_path_outside_unconfirmed`, exit 0, risk 빈 값, file = 첫 경로, reason = 경로 세 개까지 + `(+N)`.
- messages: `_gate_record` 에 `("WARN", "", True, None)`. `gate_text` 는 다른 키의 판정에 `outside_unconfirmed` 가 있으면 `gate.outside_unconfirmed` 보조 줄을 붙인다 — 선언 안내 다음, 복구 code 앞. codex 는 `" | "` 로 한 줄.
- override: `_maybe_override` 가 참이면 판정에 경로가 있을 때 `io.render_gate(core.outside_unconfirmed_warning(...))` 로 경고를 렌더한다(두 host 모두 경고는 `hookSpecificOutput.additionalContext`). 반환값은 0 그대로.

### 3. 등급 순서
- `profile_validate._semantic_issues`: `pdca.enabled` 이고 `phases` 가 있고(`_pdca_cfg` 와 같은 조건) `pre_implementation_required` 가 dict 이면, 생략 등급을 `[]` 로 두고 (L1, L2)·(L2, L3) 짝마다 낮은 쪽에만 있는 phase 를 `WARN validate.pre_implementation_not_monotonic(lower, higher, phases)` 로 낸다. 목록이 아닌 값은 기존 타입 검사에 맡기고 묻지 않는다.
- 게이트 spec: 등급 역전의 원인(교착 해소 면제)·범위(단조 = 새로 필수가 되는 phase 문서 작성, 비단조 = 소스 편집까지)·validate 경고를 적는다.

## Phase 03 — 구현

- [x] File ownership assigned before source edits
- [x] Acceptance IDs mapped to implementation tasks
- [x] Verification command plan recorded

### 소유 파일 (단독 작업)
- `scripts/sage_harness/hooks/cycle_binding.py`, `done_criteria_contract.py`, `fast_cycle_contract.py`
- `scripts/sage_harness/hooks/pre_implementation_gate_core.py`, `runtime/hook_runtime.py`, `runtime/messages.py`, `runtime/i18n/ko.py`·`en.py`
- `sage/profile_validate.py`, `sage/i18n/ko.py`·`en.py`
- `docs/sage_harness/hooks/pre-implementation-gate.md`, `docs/troubleshooting.md`·`.en.md`, `docs/sage_harness/.manifest.json`
- 시험: `tests/test_gate_followups.py`(신규), `tests/test_declared_risk_scope.py`(Windows 기대값 한 줄), `tests/run-all.sh`

### 작업 ↔ acceptance

| 작업 | Acceptance |
|---|---|
| 세 모듈 닫힘 조건 | F1~F4, F6, F7 |
| 실제 함수 전후 비교 측정 | F5 |
| runtime 목록·core 경고·표시 보조 줄 | P1~P6 |
| override 뒤 경고 렌더 | P7 |
| validate 단조성 경고 | M1~M3 |
| spec·troubleshooting | L1, X1 |
| Windows 실기 | W1, W2 |

### 검증 명령
- 관련 시험: `PYTHONPATH=$PWD python3 scripts/sage_harness/hooks/tests/<file>.py`
- 전체 스위트 로컬 1회: `bash scripts/sage_harness/hooks/tests/run-all.sh`
- `python -m sage validate --check --schema`
- 측정: scratchpad `133/contract_dump.py` 를 main(`2740da0`) 과 작업본 hooks 로 각각 돌려 비교
- Windows 11(`ssh win11`): 작업본 tar → `venv310`·`venv311`·`venv312`(pyyaml·jsonschema), 설치한 `sage-hook` 에 호스트 입력 주입(`win_check.py`)

## Phase 04 — 분석

Status: COMPLETE — 구현·로컬 검증·Windows 실기 완료, 05 2차 APPROVED

### Acceptance Evidence

| ID | Status | Evidence |
|---|---|---|
| F1 | PASS | `TestClosingFence.test_text_after_a_fence_does_not_close`(```` ```python ````·```` ``` 끝 ````·꼬리 공백·백틱 꼬리, 세 판정) |
| F2 | PASS | `test_spaces_and_longer_fences_close`(공백·탭·더 긴 펜스·들여쓴 닫힘), `test_other_fence_characters_still_do_not_close` |
| F3 | PASS | `test_the_three_readers_agree` — 두 판정은 블록 밖 줄 목록, Fast 증거는 본문 줄을 증거 줄로 채운 개수로 비교 |
| F4 | PASS | `test_one_declaration_binds_and_none_stays_none` |
| F5 | PASS | main(`2740da0`) 과 작업본 hooks 로 실제 판정 함수 출력(`declared_stem`·`_final_status`·`parse_done_criteria` standard·fast 전체 `asdict`·`evidence_marker_issues`)을 덤프해 비교 — 사이클 문서 607개, 차이 0. 설계 때의 557개보다 많은 것은 그 뒤 생긴 문서(1.3.2 05·06, 이 문서, 위키 정본) |
| F6 | PASS | `TestExampleBlocksAreNotRead` 4건 — 예시 `APPROVED` 만 → `block_report_without_approval`, 밖 `APPROVED` + 안 `BLOCKED` → `ok`, 예시 미완료 항목 미집계, 예시 증거 중복 없음 |
| F7 | PASS | `test_unicode_space_after_a_fence_does_not_close`(U+00A0·U+3000·U+2003), `test_only_lf_cr_and_crlf_end_a_line`(줄 끝은 LF·CR·CRLF 만 — 05 1차) |
| P1 | PASS | `TestUnconfirmedOutsideThroughTheHook.test_an_alias_of_the_project_is_warned` — macOS·Linux 는 대소문자 변형·심볼릭 링크, Windows 는 루트 짧은 이름. 두 host 의 JSON 봉투 |
| P2 | PASS | `test_a_confirmed_outside_path_is_quiet`(rc 0, 출력 없음), core `test_confirmed_outside_has_no_warning` |
| P3 | PASS | `test_a_block_stays_the_same_block`(경로 키를 뺀 판정이 기존과 같음), hook `test_a_block_keeps_its_exit_and_names_the_path`(rc 2) |
| P4 | PASS | `test_the_path_seen_by_the_gate_is_unchanged`(게이트가 받는 `changes` 경로), 기존 `test_make_rel_is_unchanged`·`test_hook_runtime` 150건 |
| P5 | PASS | `test_the_warning_reads_in_both_languages`(영어 줄에 한글 없음, `Next:` 없음), `test_localization_inventory` |
| P6 | PASS | `test_the_notice_survives_another_warning`(`warn_phase_incomplete` + 경로, claude·codex × ko·en, codex 한 줄), `test_block_text_carries_the_notice_before_the_next_step`, `test_many_paths_are_cut_in_the_line` |
| P7 | PASS | `test_an_override_still_delivers_the_notice`(override grant, 두 host, rc 0, stdout JSON `additionalContext` 에 경로) |
| M1 | PASS | `TestLevelOrderIsValidated.test_a_higher_level_that_requires_less_is_warned`·`test_an_omitted_level_is_an_empty_list`·`test_monotonic_profiles_are_quiet`·`test_the_default_template_is_quiet`·`test_the_message_names_the_levels` |
| M2 | PASS | `test_the_warned_profile_really_lets_the_higher_declaration_through`(L2 `block_phase_incomplete`, L3 `ok`, 같은 profile 에 validate 경고) |
| M3 | PASS | `test_disabled_pdca_is_not_asked` |
| L1 | PASS | 게이트 spec 「Session risk declaration scope」·PDCA 4항, troubleshooting ko/en 「`sage validate` 가 `pre_implementation_required` 등급 순서를 경고」 |
| W1 | PASS | Windows 11 실기(아래) — 선언 L3 + `D:` 밖 rc 0 무출력(claude·codex), 짧은 이름 루트 `_outside_confirmed` 거짓 → 선언 상향 유지(차단 + 경로 줄) |
| W2 | PASS | Windows 11 실기 — 선언 없음 + `LONGPR~1\src\x.py` → rc 0 + `[GATE WARN]` 경로 경고(claude·codex). 같은 파일의 원래 경로는 차단 |
| X1 | PASS | spec·troubleshooting ko/en(미러 해시 재스탬프)·manifest(`canonical_hash`·`spec_hash`·`hook_runtime_hash.shared`) |

### Windows 11 실기 (2026-10-22, `ssh win11`)

- 작업본을 tar 로 옮겨 `C:\Users\wkdtp\sage133\src`, `venv312` 에 설치(`pip install .`). 새 프로젝트 `work\LongProjectName`(짧은 이름 `LONGPR~1`)에 `sage install --host claude`·`--host codex`, profile 에 이름과 `l2_path_globs: ["src/**"]` 를 넣고 `sage generate --kind hook --write` 두 host.
- 설치된 `sage-hook.exe --runtime <host> --hook pre-implementation-gate` 에 Write·apply_patch 입력을 stdin 으로 넣었다(`win_check.py`, 기록 `win_check-1.log`).

| 입력 | claude | codex |
|---|---|---|
| 선언 L3 + `D:\sage133-outside\notes.md` | rc 0, 출력 없음 | rc 0, 출력 없음 |
| 선언 L3 + 프로젝트 `docs\note.md`(대조) | rc 2 `block_cycle_binding` + 선언 안내 | 같음 |
| 선언 L3 + `LONGPR~1\docs\note.md` | rc 2 + 선언 안내 + 경로 줄 | 같음(한 줄) |
| 선언 없음 + `LONGPR~1\src\x.py` | rc 0 + `[GATE WARN]` 경로 경고 | 같음 |
| 선언 없음 + 원래 경로 `src\x.py`(대조) | rc 2 `block_cycle_binding` | 같음 |
| 선언 없음 + 대소문자 변형 루트(대조) | `src/x.py` 로 판정, rc 2 | 같음 |
| 선언 없음 + `D:` 밖 | rc 0, 출력 없음 | 같음 |

- 직접 호출: `_outside_confirmed(D:)=True`, `_outside_confirmed(짧은 이름)=False`, `make_rel(짧은 이름)=<outside-project>`, `make_rel(대소문자 변형)=src/x.py`, `make_rel(D:)=<outside-project>`.
- 시험: `test_gate_followups`(29)·`test_declared_risk_scope`(43, skip 2)·`test_profile_validate`(132) 를 Python 3.10.11·3.11.9·3.12.10 에서 통과. 3.12 에서 `test_cycle_stem_declaration`·`test_messages`·`test_hook_locale` 통과.
- 3.12 에서 `test_pre_implementation_gate`(error 6)·`test_fast_cycle`(fail 1·error 7)·`test_hook_runtime`(error 2) 가 실패한다. **main(`2740da0`) 에서도 같은 시험이 같은 수로 실패한다** — 시험이 bash 셸 스크립트를 subprocess 로 실행하다 `WinError 2`, 하위 프로세스 출력을 cp949 로 읽다 `UnicodeDecodeError`. 시험 실행 환경 문제이고 이번 변경과 무관하다(06 후속 후보).

### 검증 결과

- 새 시험 29건(`test_gate_followups.py`, 05 1차 뒤 31건). 소스 11개 파일만 수정 전으로 되돌리면(`git stash`, 시험 파일 유지) 29건 중 21건 실패, 8건은 바뀌면 안 되는 동작의 고정이라 통과.
- 전체 스위트(`run-all.sh`, 로컬 Python 3 한 버전) **3,923건 통과, 실패 0**(1.3.2 의 3,894 + 29). 그 뒤 고친 것은 시험 두 파일의 Windows 분기와 보조 줄 `(+N)` 이고, 관련 묶음(`test_gate_followups`·`test_declared_risk_scope`·`test_messages`·`test_hook_locale`·`test_localization_inventory`·`test_pre_implementation_gate`·`test_documentation`·`test_manifest_util`·`test_runner_inventory`)을 다시 돌려 통과.
- `python -m sage validate --check --schema`: WARN(exit 0), main 과 같음. 새 경고 없음.
- 05 1차 반영 뒤 최종 소스로 전체 스위트를 다시 돌려 **3,925건 통과, 실패 0**(새 시험 31건).

### 설계와 달라진 점

- 1.3.2 시험 `test_make_rel_is_unchanged` 가 Windows 에서 실패했다(main 에서도). 대소문자 변형을 밖으로 기대했는데 Windows `ntpath` 는 대소문자를 무시한다 — 00 의 경로 표와 같은 사실이다. 기대값을 OS 별로 나눴다(시험만 변경).
- 새 hook 시험의 별칭은 Windows 에서 루트 짧은 이름을 쓴다. 처음 작성한 대소문자 변형은 Windows 에서 프로젝트 안이라 실기에서 실패했다.
- 보조 줄도 경로를 세 개에서 자르면 `(+N)` 을 붙인다(자체 검토).
- `runtime/prose_language.py` 의 닫힘 판정은 이미 꼬리가 비어야 닫는다(U+00A0 도 공백으로 봄). 문서 언어 검사 전용이라 바꾸지 않았다.

### 05 1차 CHANGES_REQUESTED 뒤 재작업

| 지적 | 독립 확인 | 판단 | 조치 |
|---|---|---|---|
| [P1] `str.splitlines()` 가 U+2028·U+0085·VT·FF 도 줄로 나눠, 블록 안 한 줄(```` ```python<LS>``` ````)이 「안 닫히는 줄 + 닫는 펜스」가 되어 뒤의 예시 `APPROVED` 가 승인으로 읽힘. HEAD 는 우연히(옛 규칙이 앞 조각에서 닫고 뒤 조각에서 다시 열어) 차단 | 재현: 네 문자 모두 HEAD `found 0` → 작업본 `APPROVED`. 이번 변경이 만든 회귀(승인 방향) | 허용 | 세 판독기가 LF·CR·CRLF 로만 줄을 나눈다(`_markdown_lines`, 맨 끝 빈 조각은 `splitlines()` 처럼 뺌). 문자 6종 × 승인·선언·Done Criteria·Fast 증거 + CRLF·CR 정상 시험. 실측 607개 재측정 차이 0(해당 문자가 든 사이클 문서 1개, 판정 불변) |
| [P2] 감사 기록 실패(waiver·선언 stem)로 판정을 새 차단으로 바꾸면 `outside_unconfirmed` 가 빠져 경로 진단이 사라짐 | 코드 확인: 두 실패 갈래가 새 dict 를 반환. 코어 예외(`block_gate_runtime_error`)도 같음 | 허용 | 오케스트레이터가 기록 뒤 판정에 경로가 없으면 event 의 목록을 다시 싣는다. 세 갈래 × 두 host 시험(rc 2, stdout 없음, stderr 에 경로) |

### 판정 요청 (05 에)

- 1: 세 닫힘 조건이 같은 입력에서 같은 블록 경계를 내는가. 판정이 바뀌는 입력이 「GitHub·CommonMark 에서 코드로 보이는 줄」 밖에 있는가.
- 2: 경고로 올리는 조건(`status == "ok"`)과 병합이 기존 판정·감사(선언 stem 기록, waiver 사용, override 기록)를 바꾸지 않는가. override 뒤 렌더가 두 host 에서 stdout 봉투 하나만 내는가.
- 3: validate 의 활성 조건·생략 등급 처리가 게이트(`_pdca_cfg`·`.get(risk) or []`)와 같은가.

## Phase 05 — 교차 리뷰 (codex)

`plan_docs/05-expert-review/sage-1.3.3-followups.md` — 1차 CHANGES_REQUESTED(P1 1·P2 1), 2차 APPROVED.

## Phase 06

`plan_docs/06-report/sage-1.3.3-followups.md` — 잔여 위험과 다음 결정(커밋·릴리즈).

## 알려진 한계

- 2-B 는 경고다. 경고를 무시한 에이전트는 여전히 위험 규칙을 받지 않는다(신뢰 경계: 정직한 실수 교정).
- 3 의 판정은 고치지 않는다. 단조 profile 에서 높은 선언이, 높은 등급에서 새로 필수가 되는 phase 문서 작성의 차단·경고를 풀 수 있다(사용자 승인 잔여 위험). 소스 편집은 해당 없음. 비단조 profile 은 validate 경고만 낸다 — 경고를 무시하면 소스 편집 역전이 남는다.
- 2-B 는 post-tool logger 를 바꾸지 않는다. 별칭으로 쓴 편집은 compliance 기록의 수정 파일 목록에 지금처럼 `<outside-project>` 로 남는다.
- 1-A 는 목록·인용 안 펜스와 여는 펜스 정보 문자열을 CommonMark 와 맞추지 않는다.

## 리뷰 기록

### 자체 리뷰

| 회차 | 관점 | 발견 | 조치 |
|---|---|---|---|
| 1 | 정확성(주장 대 코드·측정) | 1번 실측에 쓴 비교 규칙이 권장안 A 보다 넓었다(여는 펜스 규칙까지 바꿈) | A 와 같은 규칙으로 다시 측정 — 3,012개 문서, 사이클 문서 164개, 구조 선언 변화 0 |
| 1 | 정확성 | 「세 곳이 같은 코드」는 과장 — 펜스 전이만 같고 HTML 주석·들여쓴 줄 처리는 다르다 | 본문 정정, F3 을 「펜스 전이 일치」로 |
| 1 | 정확성 | 개인 프로젝트 profile 수를 6개로 적음(실제 5개) | 정정 |
| 2 | 보안·실패 방향 | 1-A 는 보이는 줄을 양쪽으로 바꾼다(숨던 줄이 보일 수도 있다) | 두 방향 모두 CommonMark 쪽으로 가까워지고, 선언이 사라지는 쪽은 차단으로 끝남을 본문에 적음 |
| 2 | 영향 범위 | 1-A 는 hook 만이 아니라 review-loop·fast-cycle CLI·CI 권위 판정을 바꾼다 — 소비자 PR CI 결과가 바뀔 수 있다 | 본문에 적고 릴리즈 노트 항목으로 |
| 2 | 운영 | 2-B: 루트 설정이 별칭이면 모든 편집이 경고 | 지금은 게이트가 조용히 꺼진 상태라 오히려 원인이 드러난다. 문구에 「프로젝트 경로 설정 확인」 |
| 2 | 범위 | 2-B 는 post-tool logger 기록을 고치지 않는다 | 알려진 한계에 추가 |
| 3 | 근거의 대표성 | 「관측 0건」의 표본 — Claude 기록은 보존 기간 때문에 2개월 52세션, 한 사람의 습관 | 배경에 측정 한계를 적음 |
| 3 | 사용자 요청과의 차이 | 처음 요청은 「기존 구멍도 함께 수정」. 2-B 는 구멍을 닫지 않는다 | 「닫히지 않는 것」 단락으로 숨기지 않고 적음. A 는 별도 결정 사항 |
| 3 | 판정 근거 | 3-C 의 「문서에 이미 명시」를 확인하지 않고 씀 | spec 해당 문장 확인·인용 |
| 3 | 공수 표현 | 「작음」만으로는 비교가 안 됨 | 파일·시험 수 기준으로 구체화 |

### codex 리뷰

| 회차 | 판정 | 지적 | 독립 확인 | 판단 | 조치 |
|---|---|---|---|---|---|
| 1 | CHANGES_REQUESTED | [High] 3번은 경고 차이가 아니라 차단까지 풀린다. 측정 입력이 결속에서 먼저 막혀 면제 차이를 못 쟀다 | 재현: L2=`[00,01]` profile 에서 선언 L2 차단·L3 통과. 유효한 phase 쓰기로 재측정 — 기본·실제 profile 0, 사용자 정의 profile 에서 02·03 문서만 | 허용 | 중요도·영향 정정, 재측정 표 교체. 권장은 C 유지하되 「계약으로 명시 + 잔여 위험 승인」, spec·troubleshooting 에 범위 기록 |
| 1 | | [Medium] 1번의 조용한 오판·변경 방향을 축소 — 예시 `APPROVED` 를 승인으로 읽음, A 는 승인 판정도 바꿈. 실측 정규식이 Done Criteria 항목을 안 봄 | 재현: 블록 안 예시 `APPROVED` 가 현재 `Final Status` 로 읽힘. 실제 판정 함수 네 개로 재측정 — 사이클 문서 557개 변화 0 | 허용 | 중요도 상향, 「조용히 승인되는 방향 없음」 삭제, 양방향 시험 F6 |
| 1 | | [Medium] 2-B 경고가 다른 경고와 병합되면 화면에서 사라짐 | 코드 확인: 병합은 첫 경고 키 유지, `warn_phase_incomplete` 는 사유 미표시 | 허용 | 판정 키와 무관한 보조 줄 표시, P6 |
| 1 | | [Low] 대소문자 glob 누락 주장은 틀림(위험 glob 은 소문자 비교). 491건 측정은 현재 파일 상태 | 코드 확인: `path_risk.imatch` 가 양쪽 소문자 | 허용 | 주장 삭제, 측정 표현 정정 |
| 2 | CHANGES_REQUESTED | [Medium] 1번 재측정이 Done Criteria 결과를 600자로 잘라 비교 — 차이를 놓침(미해결 1→0 이 같다고 보고) | 재현: 잘린 비교의 맹점 확인. `asdict` 전체 비교로 재측정 — 557개 변화 0, 같은 비교가 반례 차이를 잡음 | 허용 | 측정 교체, 본문 정정 |
| 2 | | [Medium] 3번 「소스 편집 차단은 안 풀린다」는 틀림 — 비단조 profile(L2=`[00,01]`, L3=`[00]`)에서 소스 편집도 역전, validate 무경고 | 재현: 선언 L2 `block_phase_incomplete`, L3 `ok_l3`. 단조 profile 에서는 소스 편집 역전이 없음을 논리로 확인(소스는 면제 없음, 결핍 목록 포함 관계) | 허용 | 영향 정정. 권장을 C → **B+C** 로 변경(B 가 이 반례를 정확히 잡음) |
| 2 | | [Medium] `.strip()` 은 U+00A0 꼬리도 닫힘으로 봄 — CommonMark 는 ASCII 공백·탭만 | 재현: NBSP 꼬리 줄이 블록을 닫아 예시 `APPROVED` 를 읽음 | 허용 | 닫힘 꼬리 `[ \t]*`, F7 |
| 2 | | [Low] 2-B: override 우회 경로는 렌더 전에 반환해 경로 진단이 사라짐 | 코드 확인: `_maybe_override` 성공 시 `return 0` | 허용 | override 알림에 진단 한 줄, P7 |
| 3 | CHANGES_REQUESTED | 방향 확인: 1-A·2-B·3-B+C 유지. [Medium] override 우회 뒤 진단을 stderr 알림에만 실으면 모델에게 닿지 않음(통과 시 채널은 `additionalContext`) | 코드·ARCHITECTURE 전달 계약 확인 | 허용 | 비차단 컨텍스트 채널로 별도 전달, P7 을 JSON 봉투 검증으로 |
| 3 | | [Medium] 3-B 의 생략 등급·pdca 비활성 처리 기준 없음 — L3 생략 시 게이트는 빈 목록인데 validate 는 존재 키만 봄 | 코드 확인: 게이트 `.get(risk) or []` | 허용 | 생략 등급은 빈 목록 비교, 비활성이면 경고 생략(M1·M3) |
| 3 | | [Low] 3-C 잔여 위험을 02·03 으로 한정하면 틀림 — 면제는 등급별 목록 포함 관계에 달림(01 작성 반례) | 같은 메커니즘, 코드상 자명 | 허용 | 「높은 등급에서 새로 필수가 되는 phase 문서 작성」으로 일반화 |
| 3 | | [Low] codex 측정이 이벤트 종류를 안 봄 — 편집이 아닌 출력도 셈 | 재현: 패치 문자열은 실제 호출(`exec` 안 `apply_patch`) 말고도 출력·압축 기록에 있음 | 허용 | 실제 호출만, 호출 ID 중복 제거로 재측정 — 3,752 호출·7,129 경로, 별칭 0 |

3회차가 CHANGES_REQUESTED 로 끝났지만 지적은 모두 권장 방향 안의 보완이었다(엔진 수정 범위를 넓히라는 지적 없음). 요청받은 리뷰 횟수(3회)에 맞춰 4회차는 열지 않았다 — 구현 사이클의 05 cross-review 가 이 보완을 다시 본다.
