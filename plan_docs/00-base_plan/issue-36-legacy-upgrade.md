# #36 구 레이아웃 업그레이드 기본 계획

Cycle-Stem: `issue-36-legacy-upgrade`
Document-Language: ko
Risk Level: L3

Done-Criteria-Revision: 2

## 1. 근거와 권위

위키 [[SAGE - 이슈 36 구 레이아웃 확장 자산 업그레이드 차단 분석과 수정 범위 (26.10.31)]]가 정본이다. 사용자 승인: 2026-10-31 권장 수정·정식 00–06 진행 후 개발 시작 요청. 브랜치 fix/36-project-hook-upgrade, 기준 8e17a88. 엔진 자체 profile/gate/review-loop/waiver를 진행·승인 권위로 사용하지 않는다. 현재 루트에 엔진 전용 guide/진입점이 없는 것은 별도 비도그푸딩 guide 개발 항목의 미구현 상태이며 이번에 consumer guide를 설치하지 않는다. 위키에 기록된 외부 00–06·3축 finding 원칙을 직접 따른다.

## 2. 목표

사용자 확장 때문에 경로 이행이 불가능하면 이행만 보류하고 기존 레이아웃에서 관리 자산·버전 갱신을 지원한다. 위험한 경로·누락 코드·손상은 계속 전체 차단한다.

## 3. 비범위와 한계

확장 자동 이동·등록 해제, 일반 EH-21 동시성, 대표 host 외 다른 host의 CORE 일괄 재설계는 제외한다. 양 host 설치의 오래된 보조 host CORE 때문에 overlays가 실패하는 현상은 기존 동작과 비교·기록하고 수정 여부를 독립 처분한다. 플랫폼 미실행을 PASS로 간주하지 않는다.

## 4. 진행

00–02 문서 → 03 RED/최소 구현/회귀 → 04 증거·gap → 05 독립 리뷰(Claude 우선, 불가 시 명시적 clean-context 대안) → 06 승인 근거가 갖춰진 뒤 보고. 커밋/push/배포는 요청 전 하지 않는다. 초기 16–28시간은 기본 수정 공수이며 L3 반복 리뷰·플랫폼 대기는 추가될 수 있다.

## 5. Done Criteria

- [x] DC1 정상 hook 설치본을 공식 CLI로 갱신하고 4축 일치·구 레이아웃·core/spec/adapter/등록 보존 및 실제 차단 결정 확인.
- [x] DC2 실제 사용자 strategy 파일을 보존하고 갱신 후 실제 runtime strategy 실행을 확인. 누락·비정상 파일은 변경 전 차단.
- [x] DC3 extension+위험 blocker 혼합, 공존, 경로 이탈, profile 오류는 전체 차단. 확장 없는 정상 이행 유지.
- [x] DC4 단계 실패 rollback·재실행·신 트리 미생성 검증. Codex global 쓰기·은퇴 자산도 전체 가역 단계 실패 시 복구하며, 충돌로 복원 불가하면 exit2·백업 보존을 확인. 일반 동시성 한계는 별도 기록.
- [x] DC5 한영 화면/JSON에 이행 보류와 버전 갱신 결과 구분, 보류 시 실행하지 않은 삭제 계획은 실행 대상으로 표시하지 않음.
- [ ] DC6 Claude·Codex project-local/global·양host 범위, 전체 회귀, 후보 wheel 소비자, 최소 Python 문법과 플랫폼 검증 결과 및 미실행 명시.
- [x] DC7 독립 리뷰·3축 finding 처분·위키 동기화. acceptance 미실행은 코드 finding과 별도로 보고하며 완료로 숨기지 않음.

## 6. Done Criteria Revision Log

- revision 1: 사용자 정본에서 DC1–DC7 도출. 미검증을 사용자 동의 없이 면제하지 않음.

- 검증 체크는 04의 macOS·격리 scope·최소 Python 증거에 한정한다. revision2에서 DC4 전역 복구와 DC7 독립 finding 처분·정본 동기화를 완료했다. DC6은 Linux/Windows native 검증을 완료했고 원격 CI 수용 근거가 없어 미완료이며 06·릴리즈 승인으로 확대하지 않는다.

- revision 2 | Changed-At: 2026-10-31 | Reason: 사용자가 전역 롤백 동시 수정 승인 | Affected-Phases: 01–05 | Summary: DC4에 전역 쓰기/은퇴 제거 복구·충돌 보존·전역 lock 수명 검증 추가. 기존 후보 검증과 리뷰는 revision1 근거이며 새 후보에 재검증한다. 추가 8–16시간, 총 추정24–44시간.

- 상태 정정(2026-10-31): Claude cross-review와 수정 후 독립 재검토는 완료. 05는 코드 리뷰 COMPLETE / acceptance 공백에 따른 최종 판정 BLOCKED이며 추가 코드 리뷰 진행 중을 의미하지 않는다. 선언되지 않은 고정 L3 반복 라운드를 미완료 근거로 삼지 않는다.

- 플랫폼 실행 완료(2026-11-01): Linux3.10.12 전체4007PASS14skip0fail, Windows11 x64/NTFS Python3.10.11·3.11.9·3.12.10 각각최종layout53/53·wheelplatform10/10·실제v1.0 3scope/global복원/native양hook/reapply PASS. 코드리뷰COMPLETE유지, 원격CI미실행으로최종판정BLOCKED/06미작성. 기존Windows mode단언1종은baseline에서도동일실패한별도#28이며원본rc1보존.
