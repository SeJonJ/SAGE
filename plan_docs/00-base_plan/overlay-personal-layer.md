# 개인 overlay 층 분리

Cycle-Stem: overlay-personal-layer
Document-Language: ko
Risk Level: L3
Issue: https://github.com/SeJonJ/SAGE/issues/34
Baseline: a87c0619a7f11d6356a7c56a039ef2ddcc1feb0e

> 엔진 비도그푸딩: 이 문서와 일반 테스트는 작업 기록·제품 증거다. SAGE 자체 gate/review/waiver를 진행·승인 권위로 사용하지 않는다. 커밋·머지·릴리즈는 사용자 지시 전 수행하지 않는다.

## 1. 목표
공유 overlay의 기존 합성을 유지하고 체크아웃별 Git 제외 개인 overlay를 검사 후 실행에 추가한다.

## 2. 범위
`asset_overrides.local`, 읽기 전용 loader/CLI, 현재 허용 8개 자산의 안내, headless packet 전달, retro/absorb 범위, 05 관측 기록, ignore/보존/upgrade 안내 및 한영 문서.

## 3. 비범위
자동 이행·분류·삭제·untrack, HOME 전역 층·별도 렌더·불변 bundle·cycle 잠금·새 gate·감사 DB·허용 목록 확대·fallback 정책 변경·엔진 guide 구현·CI 개편.

## 4. 위험과 처리
개인 원문 유출은 공유 산출물 무변경·본문 없는 오류로 방지한다. 완화 검사·경로/자격 검사는 기존 함수를 재사용한다. 기존 공유 내용 수동 정리는 사용자 결정이다. native LLM 준수·05 유실·중도 편집은 명시적 한계로 남기며 자동 enforcement를 만들지 않는다.

## 5. Done Criteria
| ID | 완료 조건 | 증거 | 상태 |
|---|---|---|---|
| D1 | 개인 없음의 기존 동작·공유 산출물 유지 | 회귀/바이트 대조 | 확인 완료(04 증거) |
| D2 | 프로젝트 경계·canonical/허용 목록·symlink·예약 토큰·완화 검사 | loader/CLI 부정 시험 | 확인 완료(04 증거) |
| D3 | 실제 content/hash 일치, 공유 validate/sync 개인 무시 | 집중 통합 시험 | 확인 완료(04 증거) |
| D4 | same/cross/fallback 대상 지침 한 번 전달·상태 유지 | 실제 packet 단언 | 확인 완료(04 증거) |
| D5 | personal/project/legacy/invalid scope·미승인·hook/profile 호환 | retro/absorb 시험 | 확인 완료(04 증거) |
| D6 | install/upgrade/rollback/uninstall 개인 원문 보존·ignore·안내만 | lifecycle 회귀 | 확인 완료(04 증거) |
| D7 | 배포 source/spec/render와 한영 문서 정렬·clean wheel consumer | 패키징/설치 시험 | 확인 완료(04 증거) |
| D8 | Claude/Codex 제한 실제 적용 smoke 및 05 독립 리뷰 | 별도 실행 기록 | 제한 smoke·정식5라운드 독립 코드 리뷰 완료, 운영한계/미실행 별도·사용자 최종 판단 대기 |

## 6. Done Criteria Revision Log
초기 선언. 범위 추가는 증거와 사용자 결정 없이 하지 않는다.

## 인계 상태
구현·자동 검증·Phase05 독립 코드 리뷰 완료. 정식5라운드(매회5렌즈+Claude peer+2반박자), 코드4건 최소수정·운영 안내1건 보완, 최종runtime3984PASS/6skip·문서18PASS를 기록했다. 기존 실패rollback 잠재P2·조건부Git노출P3·N1 기존P3와 미실행플랫폼은 05/06에 명시했다. 사용자 수용/종료·커밋·머지·릴리즈는 대기다.

2026-10-26 재시작 전 상태 정정(역사 기록): 외부 통합 리뷰+수정 확인2회를 L3 리뷰 완료로 집계하지 않는다. 렌즈별 검토·반박·수렴 확인 절차 미실행으로 Phase05는 미완료이며 06은 인계 초안이다.

2026-10-26 후속: 위 절차 누락을 보완해 정식 R1~R5와 FIND/REFUTE/TRIAGE/REWORK 기록을 완료했다. 운영 한계의 문서화는 위험 제거/사용자 수용이 아니다. 현행 판단은 05의 재시작 절과 06 개발 보고서를 따른다.

## 2026-10-30 릴리즈 진행
사용자가 관련 README 갱신→푸시·병합→원격 병합 확인 후 릴리즈 순서를 지시했다. 한영 루트 README·문서 목차를 갱신하고 기존 배포 순서의 다음 버전1.3.6을 준비한다. 제품 runtime41파일의 이전 리뷰 신원을 확인했으며 코드 변경 없이 문서4개·버전3개만 추가했다. 현재 검증·플랫폼 실행·PR/릴리즈 사실은 해당 GitHub PR·Release와 기기06 보고서에 후속 기록한다. 기존 운영 한계는 유지하고 새 기능/이행 자동화를 추가하지 않는다.
