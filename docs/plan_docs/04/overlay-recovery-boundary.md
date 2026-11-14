# Overlay 복구 경계 — 분석·QA

Cycle-Stem: overlay-recovery-boundary
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Status: ANALYZED_AND_VERIFIED — C1-C6 representative acceptance complete
Phase05: APPROVED — independent review complete and C2/C6 evidence resolved

## 계획 대비 결과

M1: 전달 오류를 일반 도구 권한과 분리했다. 회복 가능한 오류는 root/role 현재 무효 상태와 원인·수치 안내를 공급하고 과거/부분 본문은 정상으로 공급하지 않는다. 기존 독립 gate/무결성 오류는 분리한다. M2: 공통 collector를 기존 CLI 적용 전에 연결하고 profile/manifest 복구가 검사 자체로 봉쇄되는 회귀를 수리했다. M3: write-guard smoke는 순수 경로 보호를 맡고 실제 설치 host의 전달 검사를 별도로 수행한다. 새 상태/전달 채널/의존성/복구 프로그램은 없다.

## 수용 근거와 공백

| ID | 결과 | 근거·한계 |
|---|---|---|
| C1 | PASS (installed hook protocol scope) | source 초과 중 양 host 프롬프트·읽기·진단 통과, 보호된 쓰기2, 사용자 직접 source 수정 뒤 새 본문 재공급. 실제 앱 전체 작업 인수는 별도 |
| C2 | NOT_TESTED (live model) | 무효 marker·개인 비노출·현재 정상 교체의 deterministic 검사는 PASS. 모델이 실제로 무효 상태에서 SAGE 진행을 보류하는 행동은 이번 미실행 |
| C3 | PASS (bounded CLI/state checks) | 개인11KB install/sync/upgrade check/apply/generate/validate 사전 거부·수치 안내·원문 보존, profile 수리/기존 force/새 dest 회귀 |
| C4 | PASS | Codex-only8KB sync/strict validate0, Claude 추가는 host 한도 사전 거부·manifest 보존 |
| C5 | PASS (declared skips retained) | 최종 전체115스크립트·4,163Ran(15skip 포함)·실패/오류0·runner exit0. skip은PASS 수에 합산하지 않음 |
| C6 | NOT_TESTED (Windows) | clean wheel/실제 설치 hook protocol/macOS platform smoke PASS. 새 Windows 실기·원격 CI는 미실행 |

설치된 hook 프로토콜은 실제 모델 앱의 자동 훅 실행과 다르다. 종료 코드·원문 marker만으로 모델 적용을 PASS로 올리지 않는다. Windows를 다시 켜거나 준비됐다고 추정하지 않는다. 미실행은 NOT_TESTED로 남기며 실제 환경 차단을 관측하지 않았으므로 임의 BLOCKED 사유를 만들지 않는다.

## 변경 위험과05 인계

- 전체 도구 차단을 제거한 결과와 독립 gate 보존을 함께 검토해야 한다. 기존 Bash 임의 쓰기를 경로 write-guard가 전부 막는다고 보장하지 않는다.
- 현재 무효 상태의 CORE 처리·실제 모델 보류/복귀는 남은 검증이다.
- install의 planned manifest/profile 입력 검사는 기존 원문·경로·크기 제한을 우회하는 공개 옵션이 아니다. runtime 기본 무결성 검사는 유지한다.
- required 미검증을 면제하거나 APPROVED로 바꾸지 않는다. 이번04 보고 후05는 사용자 지시 전까지 시작하지 않는다. 과거 리뷰 생략·예산은 자동 상속하지 않는다.

증거: 노트북(macOS) `/Users/sejon/project/sage_project_worktree/overlay-recovery-evidence-20261112/`. 위키 정본은 `SAGE - overlay 오류 복구·적용 전 검사·호스트 검증 수정 정본 (26.11.12)`. 커밋·푸시·PR·이슈·05/06·릴리즈·전역 설치를 하지 않았다.

## 최종 실행 결과와 중지

최종 전체 `full-final.log`:115개 스크립트·4,163 Ran(15skip 포함)·failure/error0·exit0. 관련 신규8테스트와 기존 runtime/collector71도 통과했다. 설치145·doctor52·문서18·인벤토리15의 보완 실행은 최종 전체에 포함되므로 따로 더해 고유 PASS 수를 만들지 않는다.

`consumer-complete/report.json`:fresh wheel bundle/RECORD·격리 설치·정상 검증·고의 변조 검출 PASS, engine sentinel 불변. wheel SHA256 `b6d411b9b439ca28ec9341836e9bf8ea7f138959a62178f7adb5ba15ce492662`. 최종 source snapshot과 현재 제품/test347경로의 bytes 일치 확인. `protocol-complete/report.json`:설치 CLI/hook33사례 PASS(앱 모델 세션 아님). macOS platform smoke10/0. Python3.10 문법247파일 오류0은 native3.10 실행이 아니다.

04 분석·보고를 마치며 멈춘다. C2 실제 모델·C6 Windows는 미실행이다. 로컬 성공을 원격 CI·독립 승인·릴리즈 가능으로 올리지 않는다.05/06 미착수, 새 이슈·커밋·푸시·PR·머지·태그·배포·전역 설치 없음. 사용자에게 이 결과와 남은 검증을 보고한 뒤 새 지시를 기다린다.


## 03 재작업 후 재검증 예정 (2026-11-13)

위 2026-11-12 PASS는 당시 source의 이력이다. 03 필수5묶음 보완을 시작하여 새 source의 C1/C3/C4/C5 결과는 재검증 대기다. C2 실제 모델/C6 Windows는NOT_TESTED를 유지한다. 새 실행 근거가 확보되면 이 절과 해당 수용 근거를 갱신한다. 05는 user-selected same-runtime 독립 검토로 진행하며 엔진 자기 gate는 승인 권위로 실행하지 않는다.


## 03 보완 후 최신 재검증 (2026-11-13)

현재 판단은 필수5묶음 구현·로컬 재검증 완료다. raw review finding의 closure는 새 same-runtime 독립 검토에서 판단한다. 이전 리뷰의 bfd46794 source에 붙은 모델 결과를 변경 source 승인으로 옮기지 않는다. 추가 확인 후보를 개발 범위로 자동 편입하지 않았다.

| ID | 최신 결과 | 새 근거·한계 |
|---|---|---|
| C1 | PASS (bounded protocol scope) | L1 실패·reentry 병합 overflow의 body-free invalid 공급, fitting UPS 대체 뒤 risk capture/clear·단일 렌더, non-fitting 독립 출력의 상태 보존·거부. 새17 및 기존71 통과 |
| C2 | NOT_TESTED | 실제 모델이 과거 지침을 대체하고 SAGE를 보류/재개하는 앱 동작은 미검증 |
| C3 | PASS (bounded CLI scope) | 첫 shared/personal lint 뒤 source 초과 검출, personal WARN/strict·적용 거부 유지. asset-filter의 stale-profile WARN을 복원하되 whole-project routing 무결성 FAIL 유지. 원문 자동 변경 없음 |
| C4 | PASS | 실제 wheel의 Claude-primary/Codex global·disabled upgrade에서 Codex registration 재생성·strict validate. primary/installed receipt 불일치 force에서 Claude host 예산 거부 및 manifest/source 보존. Codex-only8KB 회귀 유지 |
| C5 | PASS (15 skips retained) | 전체115실행 요약·4,172Ran(15skip)·실패/오류0·runner0. 새17 및71은 전체에 포함하므로 중복 가산하지 않음. 관련 명세 보완 뒤 문서18·인벤토리15 재검증 |
| C6 | NOT_TESTED (Windows) | macOS 격리wheel/CLI/hook23검사 통과. 새 Windows 실제기기·원격CI는 미실행 |

근거는 `/Users/sejon/project/sage_project_worktree/overlay-recovery-rework-20261113/`의 rework-report.json·full-rework.log·wheel-check-isolated/report.json·python310-syntax.json이다. wheel source와 번들/설치 패키지는 테스트 consumer에 격리했다. 첫 wheel fixture의 build환경/disabled 인자 오류는 교정하고 원문을 보존했으며 제품 결함으로 세지 않았다.

리뷰 방식은 사용자 선택 same_runtime이다. 새 검토 subject/packet 준비 후 기존 잔여 예산926과 별도로 실제 추가 모델 호출 예산이 필요하다. 이 제한은 코드 수정·로컬 검사 중단 사유로 쓰지 않았으며03→04를 완료했다. 05는BLOCKED,06·commit/push·PR·merge·release·이슈 생성·엔진 자기 gate 실행은 하지 않았다.


## 2라운드 R1 뒤 재검증 대기 (2026-11-13)

앞선4172/15skip·wheel23은 이전44eddace subject의 근거로 보존한다. 이번 입력 경계 수정 후 새 근거로 갱신하며 C2/C6 NOT_TESTED는 유지한다.


## 2라운드 R1 뒤 최신 검증 (2026-11-13)

C1은 malformed/nonmapping 이벤트의 body-free invalid 상태·실제 baseline helper 호출 시도·알 수 없는session의claim미생성을추가검증했다. 기존유효startup의catalog생략·위험도capture/clear·host크기·독립gate회귀는전체검사에서유지됐다. C3/C4의기존보완코드는동일하며새wheel의global/disabledupgrade와force-host예산거부를재확인했다. C5는115실행요약·4175Ran(15skip)·실패/오류0·runner0이다.

새wheel/CLI23,잘못된입력의실제설치hook프로토콜24가통과했다. hook protocol은실제모델적용증거가아니므로 C2 NOT_TESTED,Windows미실행으로 C6 NOT_TESTED를유지한다. 새근거는 round3-rework-report.json·r3-required-final-source.log·r3-runtime-stable.log·full-r3-stable.log·wheel-round3/report.json·native-invalid-report.json이다. 단계05는독립same-runtime3라운드검토전이며새subject에기존결과를승인으로옮기지않는다.


## C2 실제 모델 대표 검증 완료·Windows 대기 (2026-11-13)

사용자: “widnow 테스트 환경은 가능할대 내가 알려줄게 나머지는 너가 할수있는거아니야?” 사용자가 준비를 알릴 때까지 Windows는 실행/가용으로 추정하지 않는다. 실행 가능한 C2 실제 모델 검증은 이번에 수행했다.

**C2는 대표 실제 모델 사례 범위에서 PASS다. 남은 required acceptance는 C6 Windows NOT_TESTED다.** 코드리뷰 실행은 이미 완료했으며 이번 제품 코드 변경·추가 리뷰 호출은0회다. 기존 최종 검토 source와358개 wheel bundle 파일이 정확히 일치함을 확인한 후보를 시험했다.

### 실제 모델·네이티브 실행 근거

- Claude Code 실제 `claude-opus-5-5`, session `5ae63f61-84cb-4241-80e2-7dba1be5b8de`: 설치된 native hooks와 Skill 도구를 사용했다.
- Codex 실제 `gpt-6.1-sol`, thread `01a1d461-2217-7231-91d9-085397084890`: native app-server, 설치 hook 신뢰해시 확인, structured skill 선택을 사용했다. reasoning effort는 low로 기록한다.
- 각 host에서 같은 session/thread의3단계: 정상A → 개인 source11024 UTF-8 bytes로10000한도 초과 → 외부 시험자가 시험용 원문을 고친 정상B.
- 최초 `sage-team-fast` 선택에서 standard shared → Fast shared → standard personal → Fast personal의4개 지침을 순서대로 적용했고, 다른 target의 유인 label은 적용하지 않았다.
- 오류 단계는 observed=[]·state=paused로 이전/부분 catalog를 사용하지 않았다. 문제 파일·관측 크기·한도를 안내하고 원문을 자동 축약/이전/수정하지 않았다. 잘못된 source의 bytes가 모델 실행 전후 동일함을 확인했다.
- 외부 시험자가 synthetic fixture를 직접 고친 다음, 스킬 재선택/재호출 없이 새B세대의4개 지침으로 복귀했다. Claude의 Skill 도구 호출은 처음1회뿐이고, Codex는 처음 structured 선택 이후 도구/재선택 없이 진행했다.
- 양 host 실제 UserPromptSubmit3회의 원문 hook input/output/exit를 pass-through로 기록했다. 오류 때 body-free unavailable만 공급하고 이전 catalog나 private invalid 본문이 나오지 않았다. 정상A/B는 실제 catalog source content와 모델 observed label이 일치했다. 가짜 모델 응답/서버는 사용하지 않았다.

이는 macOS root·Fast4출처의 대표 사례다. 모든 child/checkout/압축 경로·전체 개발 워크플로·모든 모델의 일반적 성공률까지 PASS로 확대하지 않는다. C5의 기존 회귀와 C2 실제 모델 증거를 구분한다. 사용자 실제 overlay 원문은 건드리지 않았고 별도 시험 프로젝트만 변경했다.

### 비용·권위·후속

종료된 리뷰 원장은 **790,356/800,000·잔여9,644** 그대로다. 이번 추가 작업은 리뷰가 아닌 실제 모델 수용검증으로 별도 영수증에 기록했다. Claude 신규IO18,027/cache39,857, Codex 신규IO11,786/cache47,232, **검증 신규IO29,813/cache87,089**다. 리뷰+이번수용검증 신규IO 합계는 **820,169**이며 이 합계가80만 안에 든다고 표현하지 않는다. 과거 제외 리뷰850,390과 진행자 미계량 비용은 종전대로 분리한다. 새 리뷰 상한 증액·비용 초기화는 없다.

C6 Windows는 사용자 환경 준비 통보를 기다리는 NOT_TESTED다. 사용자 통보는 준비 시점에 대한 것이며 검증 면제/잔여 위험 승인으로 처리하지 않는다. 따라서 Phase05 최종BLOCKED·릴리즈중단 유지, Phase06·commit/push·PR·merge·release는 실행하지 않았다.

검토 후00/04의 C2 실행 증거와 체크 상태, 결과 문서05/위키만 갱신했다. 당시 frozen review source/patch/원문은 그대로 보존한다. 00/04의 문서 hash는 새 실행 증거 때문에 달라지므로 기존516경로 전체가 현재와 동일하다고 하지 않는다. 그 외514경로 및 제품/시험코드는 동일하고, post-review-evidence-update.json에 전후 문서 hash와 현재 snapshot을 별도로 기록한다. 완료 기준의 의미·범위·Done-Criteria-Revision은 바꾸지 않았다.

근거: 노트북(macOS) `/Users/sejon/project/sage_project_worktree/overlay-c2-native-model-20261113/`; 보존 `{VAULT}/artifacts/sage-overlay-repair-20261112/acceptance/c2-native-model-20261113/`. 원문 native 응답·hook 기록·session/model·usage·시험 source hash·358개bundle 일치 검증을 함께 보존한다.


## Windows 실기기 검증 완료·C6 해소 (2026-11-14)

사용자 “window 테스트 시작해줘” 지시로 실제 Windows11 Pro x64(build26200)에서 후보wheel을 검증했다. SSH의관리자권한은환경준비/링크fixture보충에만구분해사용하고,주검증은TaskScheduler Limited에서실제로elevated=false임을확인했다. 후보wheel SHA256은 `953e5b35660fdbd2f2b5ccdfeff989d151eee554a9ecfe2688d9c3d8b4766ab9`다. 각환경의설치package358파일이이wheel과bytes동일하다.

| Python 실제버전 | 일반권한 회귀 | 링크 생성 권한별 보충 | 일반권한 설치CLI/native hook | 플랫폼smoke |
|---|---|---|---|---|
|3.10.11|88 PASS·3 skip·실패/오류0|같은3시험 관리자권한 PASS|84항목 PASS|10 PASS|
|3.11.9|88 PASS·3 skip·실패/오류0|같은3시험 관리자권한 PASS|84항목 PASS|10 PASS|
|3.12.10|88 PASS·3 skip·실패/오류0|같은3시험 관리자권한 PASS|84항목 PASS|10 PASS|

관련91시험의각버전전체경로를두권한실행으로확인했다(273개case-version쌍). 일반권한skip9회는삭제하지않고,해당링크fixture생성이필요한동일9시험을관리자권한에서별도로통과한것이다.관리자시험을일반권한PASS로표기하지않는다. 설치CLI/native252항목과platform30항목은모두일반권한이다. Windows전체4175회귀나Windows실제LLM앱은이번에실행하지않았고,실제모델은별도C2 macOS근거를유지한다.

### 실제 동작과 최소 변경

실제설치본에서개인source한도초과중프롬프트/읽기/진단/허용source쓰기유지,관리생성물쓰기차단,body-free무효상태,원문보존과외부수정후새본문공급,malformed/array/null의기존차단,한글/emoji·ASCII강제출력,재진입resume/fork/compact를검증했다. Claude-primary/Codex-global·disabled의upgrade hook재생성,force유지host예산과manifest보존,Codex-only8KB정상및Claude추가시거부,독립manifest손상fail-closed도확인했다.

제품코드변경은0이다. 새회귀시험의기대경로1줄을POSIX고정문자열에서os.path.join으로바꿨다. Windows진단에는이미올바른backslash경로가있었으므로제품버그로분류하지않았다. 중요도/실질위험은시험이식성에한정되고재현도는Windows에서결정적이다. 최소단언보완후Mac관련91도실패/오류0으로통과했다. 이전검토에없는제품수정이나개발범위확대는없다.

최초실패·중간실패는별도로그에보존한다. 링크생성WinError1314는환경제약이었다. -I가PYTHONUTF8환경변수를무시하여CLI가정상CP949출력을하는데수집기가UTF8로가정한오류는raw bytes를보존하고CLI실제ACP로복호화하도록시험수집기만수정했다. nativehook출력은계속UTF8로엄격검사한다. 회귀fixture의UTF8읽기는-X utf8로명시했다. 관리자시험의PowerShell ErrorAction Stop이unittest stderr를오류로취급한문제는Python파일descriptor로수집하도록wrapper만보완했다. 이를제품결함·새필수개발로합산하지않았다.

### 현재 판정과 권위

C1–C6는계획한대표검증범위에서모두충족했다. 기존same-review3라운드(5관점+peer+반박2)완료·새필수수정0과후속C2/C6실행근거를합산해Phase05의종합상태를APPROVED로갱신한다. 이는진행자의외부검증종합판정이며,당시C2/C6미실행을이유로BLOCKED였던모델원문을APPROVED로고쳐쓴것이아니다. frozenreview source/patch/모델원문·비용은그대로보존한다. 개발중인SAGE자체gate/review-loop/waiver를승인권위로실행하지않았다.

Phase06·commit/push·PR·원격CI·merge·release는이번요청범위가아니어서실행하지않았다. 별도후보G2/G4/G7/G9/G10/목적지항목도자동개발·잔여위험수용으로승격하지않는다. 리뷰790,356/800,000과별도실제모델검증29,813의원장은변경없고,이번Windows에서추가리뷰/모델호출은0회다. 임시예약작업3개는실행종료를확인한뒤해제했고시험자료는보존했다.

근거: 노트북(macOS) `/Users/sejon/project/sage_project_worktree/overlay-recovery-windows-20261114/`; `{VAULT}/artifacts/sage-overlay-repair-20261112/acceptance/windows-20261114/`. 초기실패·최종원문1153파일,정규/관리자권한별report,원본wheel/source hash,시험1줄전후hash를보존한다. Windows의backslash대장경로는노트북검증시분리자만대응하여원문bytes/hash를대조했다.


2026-11-15:사용자의06/종료·문서·커밋/푸시·머지/릴리즈·위키지시로개발사이클완료보고06을작성하고외부문서상CLOSED로종료했다. 기존실행근거와한계는유지하며실제통합/게시는PR/태그/배포의별도근거로확인한다.
