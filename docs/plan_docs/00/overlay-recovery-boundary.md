# Overlay 복구 경계 — 목표

Cycle-Stem: overlay-recovery-boundary
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1

Status: DEVELOPMENT_COMPLETED — external cycle CLOSED

## 목표·정본·권위

위키 `SAGE - overlay 오류 복구·적용 전 검사·호스트 검증 수정 정본 (26.11.12)`에서 파생된 실행 기록이다. 사용자 원문은 사용자가 직접 조정한다. SAGE는 입력 검사·파일/원인/크기/한도 안내·진단/수리 통로·유효 입력 재공급을 제공한다. 기존 정상 자동 전달·Fast 상속은 유지한다.

별도 worktree `/Users/sejon/project/sage_project_worktree/overlay-recovery-boundary`, branch `fix/overlay-recovery-boundary`, base `f7b04e1713ca1a13fb6e10625aa0547a1887cd4a`. GitHub 이슈는 만들지 않는다. 승인 범위는00–04이며05 전 보고한다. 커밋·푸시·PR·릴리즈는 하지 않는다. SAGE 자체 gate/review-loop/waiver를 승인 권위로 사용하지 않는다.

## 필수·제외

M1 overlay 전달 오류와 일반 도구 실행 분리/무효 상태/수리 후 재공급. M2 기존 collector의 shared/personal·크기·host 검사를 적용 전 연결. M3 순수 write-guard smoke와 설치 host별 전달 검사 분리.
새 채널·용량 증액·원문 자동 이전/축약/분할·DB·복구 CLI·shell parser·매 도구 자동 sync·#36/rollback 전면 개편 제외. 추가는 완료 조건을 막는 재현·직접 회귀·안전 경계 우회만 최소 포함.

## 5. Done Criteria

- [x] C1 입력 오류 중 양 host 대화·읽기·진단·허용 수리 가능, 사용자 원문 수정 후 재공급.
- [x] C2 현재 무효 상태를 전달하고 과거/부분 catalog 미사용. 양 host 실제 모델 대표3단계 검증 완료(아래 최신 근거).
- [x] C3 install/sync/upgrade 사전 검사 일치·수치 안내·원문/정상본 보존·generate profile 수리 유지.
- [x] C4 Codex-only8KB 정상, Claude/dual 초과 명시 검출.
- [x] C5 정상 전달·Fast·resume/compact·scope·독립 gate 회귀 유지.
- [x] C6 후보 wheel Mac/Windows 대표 복구 근거. 미실행 NOT_TESTED와04 완료 보고를 구분.

## 6. Done Criteria Revision Log

Revision1:2026-11-12 정본·사용자00–04 지시를 반영. 체크는 실제 증거가 있을 때만 수행하며05/06은 미착수.

04 종료: C1/C3/C4/C5는04에 기록한 설치 hook/CLI/회귀 범위에서 확인했다. C2 live-model과C6 새Windows는NOT_TESTED이며 체크하지 않는다. 전체 사이클 완료·05 승인·출시 가능을 선언하지 않는다.


2026-11-13 경계 재확인: 이후 사용자 지시로05를 진행했고 same_runtime을 선택했다. 2라운드 지적1건을 기존M1 안에서03보완→04재검증했다. C1/C3/C4/C5의 최신 근거는04의4175/15skip·wheel23·잘못된입력hook24다. C2/C6는미검증으로체크하지않는다. 06/commit/push/PR/merge/release는승인하지않았다.


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
