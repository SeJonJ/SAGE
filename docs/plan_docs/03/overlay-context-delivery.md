# Overlay 통합 전달 — 03 구현 기록

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 3
Status: IMPLEMENTED_AND_VERIFIED — 새 R2 독립 검토 완료; 출시·전역 설치 별도
Base: 8e17a88c08f12fc8ea1a5fe5672270c62d13a5ef
Branch: fix/overlay-context-delivery

## 실행 권한과 경계
사용자가 00~03까지만 실행하도록 승인했다. SAGE 소비자용 cycle/gate/review-loop로 이 엔진 변경을 판정하지 않는다. 04 분석·05 독립 승인·06 종료 및 커밋/푸시/릴리스는 수행하지 않는다. 03은 코드와 테스트의 구현 결과를 기록하며 A1~A8 전체 수용 완료를 뜻하지 않는다.

## 파일 소유와 통합 계약
- 수집: sage/overlay_delivery.py, test_overlay_delivery.py. collect_catalog(root, role='root')->dict, render_catalog(catalog)->str, OverlayDeliveryError(code,path).
- 자격·설치: overlay_classify/materialize, commands/install/generate/doctor, 해당 테스트.
- 런타임(parent): hook_entry, runtime/hook_runtime/run_hook/io_* 및 새 runtime 회귀 테스트, reviewer 역할 env 연결.
- CORE: 7종 spec/render와 사용자 한/영 문서. 필수 CORE를 우회하지 않고 현재 대상 view만 적용.
- 모든 역할은 같은 worktree를 사용하며 소유 파일 밖 수정은 parent와 조율한다.

## 구현 체크리스트
- [x] M1 한 번 읽기·검증·hash·정렬된 catalog, 전체 inventory 검사, 불안정 snapshot 재시도, 빈 상태.
- [x] M2 startup defer/UPS refresh/compact·resume 이벤트 전달 코드, 단일 host JSON, CORE selector. 실제 host 동작 수용은04 미실행.
- [x] M3 Fast backing과 표준·Fast 상속, 기존 구조 보호 회귀.
- [x] M4 스킬 물리 공유 span 정리, 설치/sync/검사/전역 Codex 정렬.
- [x] M5 오류 차단·복구/root·역할 경계/진단/등록.
- [x] M6 개발 테스트 작성·실행 및 잠정 한도·미검증 acceptance 기록. 전체 회귀의 열린 항목은 아래에 보존.

## 구현 전 기준선
2026-11-05 새 worktree에서 실행:
`/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python -m unittest discover -s scripts/sage_harness/hooks/tests -p 'test_overlay*.py'`
111 tests, OK, exit 0. 제품 소스 수정 전에 확인했다.

## 구현 결정
- 원본 main의 미추적 설계 6개를 복사했으며 원본은 보존한다.
- 기존 선언된 외부 worktree 위치를 준수했다. native 생성 API는 위치 지정 기능이 없어 git worktree fallback을 사용했다.
- 기존 요구와 사용자 확인이 충분하므로 계획 후 재승인 대기를 반복하지 않고03까지 진행한다.
- 예산은 최종 UTF8 payload 49152 bytes/source 10000 bytes, token 상한을 UTF8 byte수로 잡는 보수적 임시 구현값이다. host 설정 한도60000. 실제 모델/호스트 지원 예산 확정은04 A8에서 검증하며 출시 검증 완료로 표시하지 않는다.

## 개발 검증 결과
소유 영역 증거는 [collector](collector-evidence.md), [runtime](runtime-evidence.md), [policy/install](policy-install-evidence.md), [CORE](core-evidence.md)에 분리했다. 최종 통합 결과:

- 공식 runner: `PATH=/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin:$PATH TMPDIR=/Users/sejon/project/sage_project_worktree/overlay-context-evidence/tmp bash scripts/sage_harness/hooks/tests/run-all.sh`.
- R3는 exit1. Python suite 요약114개, 검사 실행4050회(반복 실행을 포함한 runner 로그 합계), skip14, ERROR0, 실패 assertion6건이다. 전체 PASS가 아니다.
- 이 중5건은 `test_runtime_api_preflight.py`가 UPS를 계속 비집행 baseline으로 기대하던3개 테스트 메서드의 subtest 실패다. UPS가 새 overlay 입력 guard가 되었으므로 capture는 비호환에서2로, 실제 비집행 SessionStart/logger는0으로 명시해 기대값을 정렬했다. 같은 제품 소스에서 해당 파일36개를 다시 실행해 exit0/OK를 확인했다. 제품 코드를 변경해 검사를 완화하지 않았다.
- 신규 collector24개와 runtime20개는 R3에서 모두 통과했다. Fast BACKING, 설치/업그레이드/원본 보존, hash drift/missing, 기존 hook_runtime150 등은 공식 runner 결과를 따른다.
- 최종 열린 실패1개는 아래 엔진 자체 manifest 검사다. 마지막 기대값 조정 후 전체 runner를 다시 실행한 것은 아니며, 전체 녹색이라고 보고하지 않는다.
- `git diff --check` exit0, 수정·신규 Python AST 구문검사 통과. R3 시작/종료 및 후속 scoped 재검사 뒤 제품 소스 hash는 동일하다: `sha256:a28e77ee9c85b1e27eb0dbe70db36f1d07946aa9f824b13f9c03538fd98721bd`.
- 원자료: [최종 집계](/Users/sejon/project/sage_project_worktree/overlay-context-evidence/final-test-summary.json), [전체 R3 로그](/Users/sejon/project/sage_project_worktree/overlay-context-evidence/full-run-r3.log), [API 사전검사 최종 로그](/Users/sejon/project/sage_project_worktree/overlay-context-evidence/runtime-api-preflight-final.log).

## 실제 구현 결과

| 문제 | 코드·설치 계약의 변경 | 현재 증거 범위 |
|---|---|---|
| 공유 원문 유실 | 스킬 말미의 소유 확인 shared span을 제거하고 SessionStart resume/fork/compact 및 UPS의 catalog 공급으로 연결 | 개발 event fixture; 실제 자동 압축 수용은04 |
| 개인 CLI fetch 의존 | 같은 collector가 root7 shared/personal 원문과 실제 path/hash를 자동 공급. root CORE의 별도 fetch 지시 제거 | collector·runtime fixture; 실제 모델 적용은04 |
| Fast 미지원 | 세 Fast id를 독립 structural BACKING과 연결, 표준+Fast shared/personal source refs 상속 | 분류·oracle·설치 회귀; 실제 Fast 오적용 행동은04 |

추가 필수 보완은 실제 새 경로에서 재현한 회귀에 한정했다. Read 차단 오인, 같은 root7 source 이중 읽기, API1 실행기의 새 모듈 호환 오인, 새 helper 무결성 누락, bare repo의 부모 root 승계가 해당한다. 광범위 사람 인증·target DB·worker 자동 공급 확대는 포함하지 않았다.

## 열린 개발 검증 항목: 엔진 자체 manifest 검사

공식 runner는 `test_release_readiness.TestTheEngineIsNotStaleAgainstItself.test_self_validate_is_clean`에서 엔진 저장소 자체를 `sage validate --check --schema`로 검사한다. 이 기존 항목이 이번 변경 후 역사적 `docs/sage_harness/.manifest.json`과 달라진 spec/core/runtime hash를 STALE(exit3)로 보고하여 실패했다. **변경 전에도 실패했다는 근거는 없으며 이번 변경으로 드러난 기존 검사 계약의 충돌이다.**

전체 runner에 이 root 자체 검사 항목이 포함된 것을 실행 중 발견했다. 이를 이 엔진 변경의 승인·진행 권위로 사용하지 않는다. 제품 collector/runtime/설치 회귀가 통과한 사실과 전체 runner의 이 실패를 분리하고 전체 PASS로 보고하지 않는다. 엔진 profile 생성/자체 cycle 개방/자기 review-loop/임의 waiver나 전체 manifest 재생성으로 녹색을 만들지 않았다. `docs/sage_harness/.manifest.json`과 CI workflow는 이번에 변경하지 않았다.

후속04에서 이 검사를 독립 packaging 검사/격리 consumer 제품 검사와 어떻게 구분할지 검토해야 한다. 중요도 높음(기존 CI가 같은 자체 검사 명령을 보유), 재현됨(고정된 source의 R2/R3), 처분은 현재 OPEN이다. 이 기록은 CI 변경·검사 삭제·면제·승인을 뜻하지 않는다.

## 수용 조건 추적
A1~A8은 구현 후04에서 평가한다. 03 단위/fixture 시험은 부분 근거일 뿐 실제 자동 압축·역할 행동·예산 검증을 대신하지 않는다. 기존 설계 리뷰를05 구현 리뷰로 재사용하지 않는다.


## 구현에 따른 계약 구체화

- root7 catalog 공급 원문은 같은 normalized 문자열을 한 번 읽어 검사/hash/직렬화한다. worker는 공급 범위 밖의 기존 physical 합성 검사를 유지하므로 별도 추가 읽기가 가능하다.
- 필수 package API가 생겨 `HOOK_RUNTIME_API=2`로 올렸다. 새 설치본은 API1 package에서 core import 전에 거부되며 API2 package가 기존 API1 요구 설치를 읽는 호환성은 유지한다.
- 새 `runtime/overlay_context.py`도 설치 runtime hash roster에 포함한다. 소스/설치본 변경·누락 진단의 범위를 새 모듈까지 확장한 것이다.
- 지원 크기는 아직 source 10000/catalog49152 UTF8 bytes와 Codex60000의 잠정 설정이다. 특히 기존에는 이 byte 제한이 없었으며, 큰 기존 overlay는 명시적 오류가 될 수 있다. 실제 한국어 입력/두 사본/누적 문맥 비용과 지원 상한 확정은04 A8에서 검증한다.

## 작업 상태와 다음 경계

00~02 문서와03 제품 구현/개발 테스트를 작성했다. 04~06은 미착수이고 A1~A8은 모두 unchecked다. 전역 SAGE 설치/실제 사용자 설정 변경/원격 CI/clean wheel 최종 수용/실제 모델 자동 압축/독립05 리뷰/커밋/푸시/배포는 수행하지 않았다. 원래 main의 tracked 파일은 그대로이며 변경은 별도 worktree의 미커밋 상태로 보존한다.

## Phase04 후속 결과 — 위03 시점의 열린 항목 갱신

위03 결과와 실패 로그는 당시 증거로 보존한다. 이후 사용자가04까지 승인해 native 검증 중 QG-01/02와 Claude 출력 spill을 재현·수리했다. 엔진 자체 manifest 실패는 historical manifest를 재생성하지 않고 격리 wheel consumer의 정상/변조 검사로 CI와 회귀를 연결해 해결했다. false L1 keyword의 구 package 호환 실패도 수리했다. 변경 파일·RED/GREEN과 검증 한계는04/qa-gap-evidence.md, ci-rework-evidence.md, budget-evidence.md, overlay-context-delivery.md에 기록했다.

최종 R5 전체 runner는 exit0, 검사 실행4,066건(반복 포함), skip14, 실패0/ERROR0이다. 최종 별도 wheel helper도 exit0이며 설치 정상0/변조3과 engine sentinel 불변을 확인했다. 최종 product source hash는 `sha256:70d33114c45ec4cc80111a7b319bca3ce60a2094915240411793dc3bd0a27bd8`이다. 이제 위03의 CI 미수리/04 미착수 설명은 과거 시점이며 현재 상태는04가 정본이다. 여전히05/06·원격 CI·전역 설치·커밋/푸시/배포는 미실행이고 A1~A8 전체는 미완료다.

## 2026-11-06 상태 참조

후속 승인으로 수행한 추가 수용 시험·독립 검토 시도의 최신 판정은 [05](../05/overlay-context-delivery.md)다. 필수 수용 미완료와 reviewer subject 결속 오류·실제 Claude 한도·리뷰 예산 초과로 BLOCKED이며06은 미착수다. 이번 후속 실행에서 제품 소스는 수정하지 않았다. 기존 제품 변경은 보존했다.

## Phase05 재개 재작업 소유 — 2026-11-06

재현된 runtime L1/reentry·UPS baseline/risk 순서·구 package 설치 호환은 runtime 담당이 검증·최소 수리한다. doctor의 hooks:null 예외·오류 언어 소유는 doctor 담당이 검사하며 runtime 문자열 교체는 parent와 경계를 조율한다. 독립 QA는 기존 수용 증거의 요구별 충분성과 남은 유한 검증을 확인하고 외부 harness/04 후속 증거만 작성한다. parent가 immutable snapshot/patch 결속·Claude fresh peer·독립5렌즈/반박2·통합 회귀와 최종 수용 판정을 소유한다. 이 분담 이후에만 추가 제품 편집을 시작한다.

### 최종 경계 검사에서 재현한 alias root 회귀

parent가 immutable candidate R1에서 같은 실제파일을canonical경로와symlink checkout경로로전달했다. eventroot를realpath로바꾸고기존gate make_rel은문자열root를비교해같은src대상이2차경로에서는outside로분류되고pre-implementation-gate가rc0으로통과했다. 기존base는환경root의lexical절대경로를유지했으므로이번rootresolver변경이새롭게노출한회귀다. parent소유test_overlay_runtime_delivery.py 통합회귀를먼저작성하고hook_runtime.make_rel에서문자열상밖인경로가실제로현재root안으로해결되는경우만정상상대경로로복원한다. event/collector의canonicalroot계약은유지한다. 실제밖경로나기존내부경로분류·gate정책은변경하지않는다. 기존candidateR1/R6결과는보존하되새candidate를고정해관련회귀·전체검사를다시확인한다.

## R1 정식 FIND·REFUTE 이후 재작업 소유

2026-11-06 사용자가누적리뷰상한150만토큰을승인했다.R1의5렌즈/freshClaude/독립반박자2명은고정C4를검토했고,2표모두생존한C4-P-01/02/03과DOC-R1-01을국소수리한다.C4-P-04는2표반증으로기각(새기능은설치runtime/CORE갱신필요,기존본문유실아님)하며원문/반증보존.새persistent상태/락/권한서비스/targetDB확대없음.

- runtime담당: hook_entry,run_hook,hook_runtime와관련API/entry/runtime테스트.非SAGE eventroot에서는catalog경계를유지하고기존hostproject의Stop/risk/baseline소유를보존.필요한선택context_root호출계약은기존runtimeAPI호환경계로검사하며구package가새계약을조용히실행하지않게한다.
- materialize담당: rootcontext분기의routing블록수렴누락만수리.기존공유span호환보호와다른바이트보존유지.
- doctor담당: READONLY render_sync상태와문제별외부복구명령,기존i18n주인유지.
- parent: 관련skill spec/render의외부복구절차와한영사용자문서정렬,원문hash갱신,최종통합검사/불변snapshot/유효R2재검토/06보고.

새생존반례가A5/A7증거에미치는영향을재검증한다.수용기준문구는변경하지않는다.


## 새 리뷰 R1의 한정 재작업 소유

새5렌즈/freshClaude/두반박자의 원문은 restart evidence에 보존한다. R1에서 F01(블록 밖 LF 보존), F02(snapshot획득 중 변경의1회retry), F03(기존 dual-host local CORE upgrade), F04(nonSAGE로 바뀐root의명시적empty replacement)는 두표모두 기존계약의국소수리로확인했다. 신규컴포넌트/인증·targetDB·다중root정책결합은추가하지않는다. F05/06/07의정책확장제안은두표반증이며적용하지않는다. F08~12는실제영향/기존프로듀서/독립검사근거를더확인한후처분하며자동개발대상이아니다.

소유: parent=overlay_materialize+그회귀(F01) 및통합검증/리뷰;collector담당=overlay_delivery+그회귀(F02);runtime담당=hook_runtime/overlay_context+그회귀(F04);policy/install담당=upgrade+그회귀(F03). 새signature/state/global-write범위를만들어야하면구현을멈추고근거보고. 기존global/local설치선택과rollback경계를그대로사용하고외부기존global경로를새로소유하지않는다.
