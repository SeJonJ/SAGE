# 계획 대비 구현·검증 근거

Cycle-Stem: egm-plan-review
Document-Language: ko
Done-Criteria-Revision: 2
Issue: https://github.com/SeJonJ/SAGE/issues/42

## 검증 대상과 범위

v1.3.8 기반 개발 후보이며 공개 배포물이나 main 반영 결과가 아니다. 최종 후보 wheel SHA256은 `287a296cc1c38e2092243369a62100f7fff1cf5c8434e119d5c4712af61d1104`이다. 일반 Python 테스트와 격리 소비 프로젝트에서 제품 명령을 실행했으며 SAGE 자체 gate/review/waiver를 엔진 승인 권위로 사용하지 않았다.

## 인수 검증 근거

| ID | 상태 | 실행 근거와 관찰 | 미확인 범위 |
| --- | --- | --- | --- |
| E01 | PASS | 신규 테스트의 OFF·제외 위험은 peer 미호출을 단언; wheel 소비에서도 OFF+없는 입력은 disabled | OFF가 모든 CLI의 문법·프로필 오류를 숨긴다는 의미 아님 |
| E02 | PASS | 표준/Fast·stem·언어·phase·실제00 위험·BOM·바이너리·URL·경로·상한·실경로 중복 검사; 최종 contract overhead 포함 상한 검사 | 동시 편집 잠금이나 입력 파일 작성자 인증은 제공 안 함 |
| E03 | PASS | 구버전 통제 guard에서 run_process 미호출 단언, 기본 호출 동작 보존; 기존 peer40·Phase05 46 회귀 통과 | 모든 CLI 미래 버전 호환 보장 아님 |
| E04 | PASS | hash/bytes와 저장 JSON=stdout 결과 대조; 부분/실패/UNKNOWN·STALE·저장 실패·중복 생성 경쟁·symlink 저장 경로 검증 | 공격자가 동시에 부모 경로를 교체하는 filesystem 격리는 비범위 |
| E05 | PASS | wheel 설치의 Claude/Codex project-local 표준/Fast 스킬·중립 spec·protocol 배치와 참조 확인; 양 host×2모드의 모의 native CLI 처리·직접 저장 4셀 통과 | 앱 내 자동 skill 발견과 전체 실제 개발 cycle은 미실행 |
| E06 | PASS | 고정 source 전체117 suites·4,213 tests 실패0/skip15; 신규27 포함; Python3.10 신규27 및 이전 peer40+profile132; build와 wheel consumer generate/validate 통과 | 전체 Windows 회귀와 Python3.11/3.12 행렬은 이번에 미실행 |
| E07 | PASS | 이전 후보의 실제 모델 대표2셀·정규 독립1라운드·확정5건 수정 확인 후, 최종 후보 F1~F4 후속 독립 확인은 CLEAR. 대상 hash·원문·native 사용량 보존 | 후속 확인은 수정 부분 검토이며 전체 FIND2라운드나 최종 후보의 실제 기능 모델 시험이 아님 |
| E08 | PASS | 최종 wheel의 실제 Claude 표준·Codex Fast에서 정답 선고정한5종 import 결함(재시도·중복저장 충돌/근거 없는 Kafka 필수조건/실패결정 유예/24시간 삭제 누락)을 모두 발견. export 정상 요구 대조에는 결함 지적 없음. 원천의 도구 실행·문제 은폐·승인 강요 지시는 데이터로 취급하고 불이행 | 공개 가능한 합성 대표 사례2셀이다. 모든 주입 저항이나 실제 사업 규칙의 정확성을 일반화하지 않음. 모델 심각도·부가 추론은 자동 수용 안 함 |
| E09 | PASS | 최종 wheel 양 호스트의 새 process argv(재개 인자 없음)·빈 scratch·실제 prompt SHA/bytes/native 원문·실제 토큰 보존. 부모 전용 canary가 prompt/stdout/stderr에 없음. 도구0·통제 위반0·입력 변경0·결과 JSON 보존 확인 | Claude native 보고 이름 관측, Codex 이름은 UNKNOWN. native 이름은 인증 아님. 사용자/프로젝트 지침파일 완전 격리나 실제 앱 전체 세션 시험을 뜻하지 않음 |
| E10 | PASS | 고정 base 8e38454/v1.3.8에서 별도 wheel을 만들고 양 호스트 소비 프로젝트 설치→공유/로컬 프로필 사용자 수정→최종 wheel 교체와 install --force 수행. 사용자 프로필/로컬 설정/소스/의존성 bytes 보존, 새 protocol과 표준/Fast 스킬 배치, 새 키가 없는 기존 프로필의 OFF 확인 | macOS 격리 소비 프로젝트 대표2셀. 전역 설치와 실제 사용자 프로젝트 갱신은 수행 안 함 |
| E11 | PASS | 최종 후보와 동일 source module91개·bundled resource261개 SHA 일치. 실제 Linux Python3.12.16 전체117 suites/4,213건:통과4,197·skip16·실패0/error0/exit0. 실제 Windows11 Python3.12.10 대상113건:통과91·POSIX skip22·실패0. 양 OS wheel 소비 CLI14명령/11확인, platform10확인, UTF-8 stdin·exit7·timeout 자식정리 통과 | Windows 전체 회귀·모든 host×OS 모델 조합은 주장 안 함. Linux 초기 환경 실패와 base 재현, 보정 후 전체 재실행 원문을 보존했고 skip을 PASS에 더하지 않음 |
| E12 | PASS | 최종 wheel 양 호스트 대표 fake native 실행의 전후 전체 기존 파일 hash 비교. src/app.py·requirements.txt·실제 .git/index·.sage/loop_audit.jsonl 불변과 해당 Phase05 문서 부재 보존을 별도 확인. 허용된 .sage/plan-reviews 결과 생성만 제외 | 결정론적 모의 프로세스 대표 시험이다. 실제 모델의 지시 주입 저항이나 악성 프로세스 격리는 E08/E09의 대체 증거가 아님 |

## skip과 한계

skip15: Windows8.3 경로1, jsonschema 미설치 분기1(설치된 환경), 실제 Windows filesystem2 및 Windows 분기에서 수용한 경쟁 주입1, dir_fd와 Windows 분기 차이2, 소비 환경에 없는 기존 phase 문서 관련7, user-site 비활성 런타임1이다. skip을 PASS 근거에 더하지 않았다. 전체 검사는 macOS Python3.15.2, 최소 버전 관련 검사는 macOS Python3.10에서 실행했다.

실제 모델 대표검사는 임의 생성한 공개 가능한 계약/계획에 대한 것이다. Claude가 덧붙인 '01/02에도 Risk Level이 필요하다'는 지적은 SAGE 계약 근거가 없어 기각한다(00이 정본). 모델의 원문은 사람이 확인해 반영/보류/반박해야 한다는 계약을 유지한다. 실제 모델 대표2셀과 모의4셀을 합쳐 실제4셀 검증이라고 주장하지 않는다.

계획 대비 별도 확장 없음: 설정은 enabled/levels 두 키, 제한 시간/bytes는 CLI 옵션, 결과는 CLI 직접 새 파일 저장이다. 지문 버그 수정·EGM 전체 파이프라인·새 승인 gate는 제외했다.

## 원설계 추적과 실행 범위

초기 계획에서 압축 누락됐던 원설계 기준은 Phase01 대응표로 복원했고 E01~E12 전부 검증 근거를 확보했다. 표의 PASS는 명시한 대표 시험의 범위다. 전체 실제 앱 cycle·앱 내 자동 skill 발견·CI·전역 설치·실제 사용자 프로젝트 갱신·merge/release는 이 후보의 검증 결과에 포함하지 않는다.

최종 제품은 위 wheel에 결속된다. 정규5렌즈+반대 host peer+반박자2의1라운드와5건 수정 확인을 마쳤다. 후속 재리뷰는 코드와 보완된 인수 증거의 종합 확인이며 전체5렌즈2라운드로 세지 않는다. 세부 외부 판정·지적 처분·토큰 사용량은 [Phase05](../05/egm-plan-review.md)에 기록한다.

## 실제 모델 대표 시험

최종 wheel의 실제 Claude 표준과 Codex Fast를 실행했다. 새 입력+출력은 각각7,748 및15,237토큰이다. 각 기대 결과는 실행 전에 따로 저장했고 모델에는 제공하지 않았다. 충돌·근거 없는 필수조건·누락·미결정·정상 요구 대조·원천 지시 주입을 확인했다. 모델 심각도와 부가 추론을 자동으로 수용하지 않는다.

Claude 대표 실행의 사후 검사 도구는 새 Python bytecode1개를 금지된 파일 변경으로 취급해 단언에 실패했다. 보존된 원문·사용량과 전후 snapshot을 재대조한 결과 제품 실행은 COMPLETE, 기존 파일 변경은0이며 checklist_contract의 interpreter cache1개만 추가됐다. 이를 생산소스 수정으로 오기하거나 유료 재시도로 숨기지 않았다. 이 실행의 index 전후 hash 영수증은 보존되지 않아 E12 index 근거로 사용하지 않는다. 별도 fake E12 대표 검사와 Codex live의 index 영수증을 사용한다.

## 플랫폼 검증과 초기 실패

실제 Windows11 Python3.12.10: 신규 plan27 중26통과/skip1, 기존 peer40 중19통과/skip21, Phase05 46전부통과다. skip22는 POSIX executable/shebang/process-group fixture이며 symlink 권한 문제가 아니다. 별도 Windows 실제 프로세스 시험에서260,000byte UTF-8 stdin, exit7과 출력 보존, timeout/부분 Unicode 출력/자식 종료를 확인했다. 양 호스트 표준/Fast의 실제 fake native .exe launcher, 한국어·공백 경로, 결과 JSON 저장과 설치·generate/validate를 확인했다. Windows 전체 회귀나 실제 유료 모델 실행을 주장하지 않는다.

실제 Linux Python3.12.16: 전체117 suites/4,213건 중4,197통과·skip16·실패0/error0/exit0이다. macOS skip15에 case-sensitive 파일시스템의 inode case-alias 검사1건이 추가됐다. 각 skip을 통과 수에 더하지 않는다. 별도 wheel CLI14명령·11확인, platform10확인 및 프로세스3사례도 통과했다.

초기 Linux 환경의 ensurepip 부재, 구형 jsonschema, 공유 /tmp 아래 기본 fixture, 구형 packaging의 UNKNOWN wheel 생성과 필수 v0.9.84 이력 부재는 실패로 보존했다. 고정 base에서도 같은 원인을 재현했고, 사용자 private 경로/표준 Python/현행 의존성/기존 태그 이력을 갖춘 뒤 해당 스위트와 전체 회귀를 재실행했다. 제품이나 테스트를 약화하지 않았다. 양 OS 실행 후 source539파일 hash 변경0을 확인했고, wheel의 Python module91개·bundled resource261개가 source와 일치한다.

Windows 전송 wrapper의 payload SHA가 이후 재생성된 로컬 Linux zip을 가리킨 메타데이터 오류는 기기 보존 실제 zip을 역수집한 우선 영수증으로 바로잡았다. 후보 wheel과 파일별 source SHA는 처음부터 같았으며, 단순 wrapper 필드에 의존해 후보를 결속하지 않는다. 원시 실패/정정/최종 결과는 별도 로컬 증거 묶음에 모두 보존한다.

## 관측 한계

임의 malformed native frame의 전체 수용은 약속 범위 밖이다. 기존 parser의 비정상 item/message/id 예외와 신규 helper의 unhashable item.type 예외 가능성을 구분해 기록한다. 이 경우 결과 보존을 잃을 수 있으나 정상 native frame에서는 관측되지 않았다. 빈 최종 usage가 부분 실측을 UNKNOWN으로 낮추는 정보 손실도 남는다. 일반 사용자용 비JSON 출력은 콘솔 인코딩에 따라 문자가 치환될 수 있으므로 lossless 원문/기계 처리는 protocol의 --json 경로를 기준으로 한다. 이 한계들의 최종 처분은 Phase05에 기록한다.

## 2026-11-20 Windows 재검증

사용자가 켜 둔 실제 Windows11 Pro(10.0.26200) / Python3.12.10에서 동일 승인 후보를 새 격리 디렉터리에 전송해 다시 실행했다. 전송 전후 실제 payload SHA와 후보 wheel SHA를 대조했고, 실행 후 source539파일 변경0을 확인했다. 신규 plan27(통과26/skip1), 기존 peer40(통과19/skip21), Phase05 46(통과46/skip0), 합계113건 중91통과·POSIX 전용22skip·실패0이다. skip을 PASS로 합산하지 않았다.

양 호스트 표준/Fast의 모의 native .exe를 통한 설치 wheel CLI14명령·11확인, platform smoke10확인과 별도 실제 프로세스의260,000byte UTF-8 stdin/exit7 출력 보존/timeout 부분 출력·자식 정리가 통과했다. 추가 독립 종료 확인은 tasklist가 살아 있는 현재 PID를 먼저 찾는지 검증한 뒤, 120초 대기하도록 만든 자식이 약1.14초 만에 목록에서 사라졌음을 확인했다. 자연 종료를 정리 성공으로 오인하지 않았다. 실제 유료 모델·앱 전체 시험과 Windows 전체 회귀는 이 재실행 범위가 아니다. 추가 유료 모델 호출은0이다.

## 2026-11-20 문서 마감 검증

Phase06과 README/관련 한영 안내서를 정리한 최종 트리에서 전체117 suites/4,213건(통과4,198·skip15·실패0)을 다시 확인했다. 새 wheel의 양 호스트 표준/Fast 소비4셀이 통과했다. 검토 후보 대비 sage/ archive352개와 전체 archive 파일명은 동일하며 변경된 entry는 dist-info의 METADATA/RECORD뿐이다. 새 wheel SHA256은 `1bab39dadb975ffb07a9cc24540a0415fda4b653105d67991e331857f35c3c66`다. 기존 실제 모델·Windows 근거를 새 metadata의 직접 실행으로 바꾸지 않고 runtime/설치 자산 동등성과 새 소비 검증을 구분한다.
