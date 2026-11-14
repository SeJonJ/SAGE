# Overlay 복구 경계 — 구현

Cycle-Stem: overlay-recovery-boundary
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1

Status: REWORK_IMPLEMENTED_AND_LOCALLY_VERIFIED — round3 same-runtime pending

## 소유·작업 순서

root가 순차 구현한다. 새 서브에이전트·독립 리뷰·유료 review 호출 없음. `superpowers:executing-plans`와 TDD 적용. 사용자 승인 범위에 따라 task별 자동 commit 및 최종 whole-branch review는 실행하지 않는다.

- [x] T1 M1 runtime/CORE 계약 및 관련 테스트 RED→GREEN.
- [x] T2 M2 공통 preflight와 CLI 적용 지점·source 수치 진단 RED→GREEN.
- [x] T3 M3 설치 host별 명시 검증·write-guard 독립성 RED→GREEN.
- [x] T4 직접 관련 명세/README/troubleshooting 최소 정렬·전체 회귀·wheel.
- [x] 04 계획 대비 차이·수용 증거·NOT_TESTED·안전 경계 기록 후05 전 보고.

## 실행 명령·근거

Python: `/Users/sejon/project/sage_project_worktree/overlay-issue36-platform-20261107/mac-venv/bin/python` (Python3.11, 기존 의존성 재사용; 엔진 설치 안 함).
관련 baseline: `-m unittest discover -s scripts/sage_harness/hooks/tests -p test_overlay*delivery.py` →71tests/OK, 로그는 노트북(macOS) `/Users/sejon/project/sage_project_worktree/feedback-1.3.7-analysis-20261111/new-cycle-baseline.log`.
전체 runner: `PATH=<위 venv>/bin:$PATH bash scripts/sage_harness/hooks/tests/run-all.sh`.
실행 증거는 별도 scratch `/Users/sejon/project/sage_project_worktree/overlay-recovery-evidence-20261112/`에 보존한다. 제품·수리 원문·전역 설치는 engine 개발 환경과 분리한다.

## 판단 기록

Ruling: 새05 리뷰·commit/push는 사용자 지시의04 중지 경계를 우선해 생략한다. 이전 Windows 리뷰 생략은 상속하지 않는다.

## 구현·회귀 기록

- 신규 복구/개인/host preflight4테스트 RED(9subtest failures)→GREEN. CLI 적용/보존/host/프로필 수리3테스트 추가 RED(5failures)→GREEN. 파일명 오류1테스트 RED→GREEN. 초기 대소문자 파일명 fixture는 macOS에서 기존 파일을 덮어쓴 실수였고, 기존 파일을 제거해 실제 `.MD` 항목을 만든 뒤 제품 차단을 재현했다. 이 fixture 오류를 제품 결함 수로 세지 않는다.
- 기존 runtime71테스트는 변경된 전체 차단 계약만 명시적으로 갱신했다. 무결성 실패·개인 비노출·기존 phase/risk 회귀는 유지한다. 기존 설치145·doctor52·golden7·문서18·인벤토리15의 재검증 결과는 각각 evidence 로그에 있다.
- 전체R1은 작성 중 문서 hash/기존 force manifest 복구/새 dest/구 진단 문구·휴리스틱 정책의 실패를 보존한다. 모두 원인에 맞춰 수리·재검증했다. 전체R2는 번역 인벤토리 hash1건 실패였고 기존 generator로1줄 재생성했다. 최종 전체 runner는 별도 로그로 남긴다.
- Ruling: 기존 force manifest 복구·최초 dest 생성은 이번 회귀이므로 입력 검사의 적용 예정 상태만 보완했다. 기존 transaction/CLI 의미 전면 개편을 하지 않았다.
- Ruling: validate 휴리스틱 WARN 정책은 보존하고 명시적 전달 오류만 별도 검출한다.
- CORE7종의 source/render에는 같은 짧은 무효 상태 처리 지침만 추가했다. 한영 README/architecture/troubleshooting·hook3명세·메시지2개 언어와 파생 인벤토리를 정렬했다. 원문 자동 수정·새 채널/DB/복구 CLI·이슈·05 호출·commit/push 없음.

최종 전체115스크립트·4,163Ran(15skip 포함)·실패/오류0·exit0, 최종wheel/CLI-hook33·macOS platform10 통과. 최종 보고는04와 `phase04-report.json`을 따른다.05는 시작하지 않았다.


## Phase05 지적에 따른03 보완 재개 (2026-11-13)

기존 승인된 M1–M3 안의 필수5묶음(G1 upgrade host, G3 validate 오류/정책, G5 reentry 무효 상태, G6 submit 병합 예산 복구, G8 force host 정규화)을 보완한다. root가 순차로 회귀 RED→최소 수정→GREEN을 수행한다. 동시 편집/child/추가 hardening/기존 sync 동시성은 자동 편입하지 않는다. 별도 기존코드 백업·로그: `/Users/sejon/project/sage_project_worktree/overlay-recovery-rework-20261113`.

- [x] 5묶음 회귀 RED 확보
- [x] 필수 코드 보완 및 관련 GREEN
- [x] 전체 회귀·문서 정합성 및04 새 근거 갱신
- [ ] 새 source 고정 후05 same-runtime 독립 검토

사용자가 “cross-review 말고 same-review 로 진행해”라고 지시했다. 05는 의도적으로 clean-context same-runtime(Codex)로 선택한다. 기존5관점·반박2명을 유지하며 독립 peer 자리도 fresh Codex로 대체한다. 이전 Claude 결과를 same-runtime 결과로 재표기하지 않는다. 새 리뷰 호출/예산 초기화/상한 증액 승인은 이 지시에서 추정하지 않는다. 추가 모델 호출은0회로 유지한다.


## 03 보완 실행 결과 (2026-11-13)

필수5묶음을 보완했다. (1) upgrade hook target은 CORE skill scope와 분리해 계획된 설치 host를 사용한다. (2) force preflight는 결과 manifest와 같은 primary/installed/requested host 합집합을 검사한다. (3) validate의 전달 검사와 heuristic lint를 분리해 첫 lint 뒤 source/host 검사 누락을 막고 personal lint의 WARN/strict 정책을 적용한다. YAML의 예정 profile로 크기를 검사하되 기존 전체 프로젝트 routing 무결성 FAIL은 유지한다. (4) L1 동기화 실패 시 본문 없는 현재 invalid 상태를 reentry에 전달한다. (5) 병합 overflow는 catalog만 unavailable로 대체한 후 재검사하며 risk 렌더를 반복하거나 commit 전에 risk 상태를 바꾸지 않는다. 필수 독립 notice+상태도 안 들어가면 unchecked 출력 없이 실패한다.

새 회귀9개를 추가해 총17개 RED11failure/0error→GREEN17을 확인했다. 기존 runtime/collector71, 전체115실행 요약·4,172Ran(15skip)·0failure/error·runner0, 문서18/인벤토리15 통과. 전체 중 capability 검사가 요구하는 실제 merge_output 호출을 유지하도록 연동 회귀를 수리했다. 기존9990-unit SessionStart fixture의 무효 상태 누락 허용 계약은 최종 envelope 거부로 명시 갱신했다.

새 wheel의 격리 build/install·Claude-primary/Codex global 및 disabled upgrade·strict validate·양 host invalid→사용자 source 수정 후 정상 공급·force host 누락 차단 등23검사가 통과했다. 실제 모델/Windows 검증은 아니다. Python3.10 문법268파일 오류0은 native3.10 실행이 아니다. wheel hash와 실패/fixture 교정 이력은 rework-report.json 및 wheel-check-isolated/report.json에 보존한다. 추가 모델 호출0·기존 리뷰399,074/400,000은 유지한다. 코드 보완은 구현·로컬 검증 상태이고 독립 리뷰 closure는 미완료다.


## 2라운드 R1 보완 착수 (2026-11-13)

malformed/nonmapping 이벤트를 unavailable이 재파싱하면서 baseline helper 전 예외가 나는1건을 재현했다. 추가 분기 검사에서 safe parse만으로는 후속 startup 필터의 invalid 상태 누락과 공통 parser의 stdin→dict 계약이 해결되지 않음을 확인했다. 외부 회귀3개 RED23subtest failures/0errors를 확보했다. 기존 M1 안에서 안전한 mapping 정규화·현재 invalid 상태 유지·기존 parser 계약을 보완한다. 새로운 gate/상태/채널을 만들지 않는다. 예산700,000을 유지하며 모델 추가 승인 없이 필요한 보완·재검증을 이어간다.


## 2라운드 R1 보완 완료 (2026-11-13)

unavailable의 malformed/nonmapping JSON을 안전한 mapping으로 정규화하고, SessionStart의 invalid_event는 startup catalog 생략 필터에서 현재 invalid 상태를 잃지 않게 했다. baseline helper는 session_id를 알 수 없는 nonmapping 입력에 claim을 만들지 않고 기존 결과0으로 종료한다. 공통 parse_input_fail_open은 이전 AST 그대로 두어 다른 gate의 입력 처리 정책을 넓히지 않았다.

최종 로컬 경계 회귀3개 RED16failure→20개 전체복구GREEN, runtime71GREEN. 전체115실행요약·4175Ran(15skip)·실패/오류0·runner0. 새 wheel23 및 실제 설치 hook의 malformed/array/null ×2host×2scope×2hook24검사에서 SessionStart invalid 상태, UPS의기존차단2, 기존session로그불변을확인했다. 실제모델/Windows검증은아니다. 새wheel953e5b35660fdbd2f2b5ccdfeff989d151eee554a9ecfe2688d9c3d8b4766ab9. fixture alias 교정과 중간 full 실행 중단은 원문으로 보존하고 제품 결함으로 가산하지 않았다. 다음은 같은700,000상한의same-review3라운드다.


## Windows 시험 단언의 이식성 보완 (2026-11-14)

Windows11일반권한에서새회귀의기능분기는동작했지만personal lint 진단경로를POSIX문자열로비교하는단언1건이실패했다.실제출력은정상Windows구분자이며중요도/위험도는시험이식성에한정된다.제품코드/규칙/원문/진단은변경하지않고test_overlay_recovery.py의기대경로한줄만os.path.join으로바꿔3개Python에서재검증한다.최초실패원문과변경전시험을보존한다.심볼릭링크생성WinError1314는일반사용자권한의환경제약으로분리해기존3개링크시험을관리자권한에서도실행하며일반권한PASS로위장하지않는다.설치수집기는-I로무시되는PythonUTF8환경변수와WindowsACP출력을구분해원문bytes를먼저저장하고CLI의실제encoding으로복호화한다.새제품기능/리뷰범위는추가하지않는다.


2026-11-14최종:제품코드변경없이시험기대경로1줄보완후Mac관련91PASS,Windows각Python일반88PASS/3skip·동일링크3관리자PASS,설치native각84·platform각10PASS. 초기/중간실패와권한/인코딩차이는04/05·외부Windows근거에보존한다. 추가리뷰/모델호출0,06/commit/push미진행.


2026-11-15:사용자의06/종료·문서·커밋/푸시·머지/릴리즈·위키지시로개발사이클완료보고06을작성하고외부문서상CLOSED로종료했다. 기존실행근거와한계는유지하며실제통합/게시는PR/태그/배포의별도근거로확인한다.
