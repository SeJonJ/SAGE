# F9 — PDCA phase 의무구조 CORE 복원 + 게이트 강제

## 문제 (Tier 2 weatherapp 에서 발견)
B'' 범용화 때 PDCA 강제 백본이 CORE 에서 통째로 누락됨:
- `AGENT_GUIDE.md` Workflow 가 "plan doc 하나 써라" 로 축약 → 위험→의무 phase 범위표·Mandatory Writing·Independent Cycle Rule 삭제
- `docs/agent/pdca-templates.md`(phase 00~06 정의 SSOT) 미배포 (9개 중 3개만)
- profile 에 phase 집합/레벨별 의무범위 키 없음
- 게이트가 phase 완성도를 강제하지 않음 → 어떤 인스턴스도 phase 없이 통과 (PDCA 무력화)

권위 SSOT: ChatForYou `AGENT_GUIDE.md §3` + `docs/agent/pdca-templates.md`.
phase 방법론은 **범용**(도메인 무관) → CORE 에 복원. 도메인 트리거만 profile.risk.

## 표준 phase (00~06) + 위험→의무범위
00-base_plan(CONTEXT) / 01-plan(CONTENT) / 02-design / 03-implementation / 04-analyze / 05-expert-review / 06-report.
L0=없음 · L1=00–03 · L2=00–05 · L3=00–06(+리뷰 라운드).

## 수정 (게이트 강제 — 사용자 결정)
1. CORE `AGENT_GUIDE.md`: §Risk & Workflow Gate 복원(phase 표 + Mandatory + Independent Cycle), 중립.
2. CORE `docs/agent/pdca-templates.md` 신규: 중립 포팅(역할명 leader/reviewer/qa, 도메인→profile 참조).
3. profile `pdca` 블록: enabled(기본 ON) + phases(00~06) + pre_implementation_required(L1:[00], L2/L3:[00,01,02]) + report/approve_phase.
4. **게이트 강제** (`pre_implementation_gate_core`):
   - 구현 전 의무 phase 검사: L2/L3 코드 변경인데 required phase 문서 없음 → `block_phase_incomplete`. L1 → warn.
   - report←approve: report_phase 문서 작성 시 approve_phase 에 APPROVED 없으면 `block_report_without_approval`.
   - **pdca 비활성 → None 반환 → 기존 동작 100% 보존**(하위호환, 독립).
   - 어댑터(claude/codex): snapshot.phase_docs 구성(phase 별 glob 스캔) + 신규 message 렌더.
5. 테스트: 의무 phase 누락 block / 충족 통과 / report 게이트 / 비활성 하위호환. 재스탬프 + validate.
6. weatherapp 인스턴스 재정비: 평면 01/02 → phase 디렉토리, profile.pdca 채움, 게이트 실증.

## 절차 (사용자 지시)
구현 후 3~5회: 코드 리뷰 → 리뷰 타당성 검증(재현/근거, 맹목수용 금지) → 수정. 라운드별 기록.

## 검증
- 전체 hook 테스트 PASS, `validate --schema` PASS, 비활성 프로젝트 회귀 0.
- weatherapp: 의무 phase 미충족 시 실제 BLOCK 재현 → phase 작성 후 OK 폐루프.

## 반복 리뷰 절차 기록 (사용자 지시: 리뷰→타당성검증→수정)
- **R1 (테스트 주도)**: report←approve 게이트가 `**/*.md` 글롭을 fnmatch 로 매칭 → `glob.glob`(recursive)과 의미 불일치로 직속 `06-report/feature.md` 미감지. **재현**: test_report_blocked_without_approval FAIL. **타당**(실결함). **수정**: `_glob_base`+`_under_dir`(base 디렉토리 prefix 매칭)로 교체 → 28/28 PASS.
- **R2 (재현 배터리)**: codex 어댑터 phase 강제가 exit0(미차단)으로 보임. **타당성 검증**: bash -x 추적 → zsh `echo \n` 이 JSON 문자열에 리터럴 개행 삽입 → 어댑터 `json.loads` except→sys.exit(0). **결론: 테스트 하네스 결함(코드 정상)**. printf/유효 JSON 재현 시 codex 도 BLOCK exit2 확인. 부수발견: malformed-JSON fail-open(`except: sys.exit(0)`)은 **기존 설계**(F9 범위 밖, 변경 시 transient 입력에 도구호출 전면차단 위험 → 보류, 향후 hardening 후보).
- **R3 (설계/엣지)**: 게이트 순서(report→L0단축→phase→기존 per-level), 하위호환(_pdca_cfg None), 독립성(phase명 전부 profile, 엔진 도메인값 0), 오설정 방어(report_phase 미정의/approve 문서 없음 → 안전 None/block) 검토. **결함 없음**(재현으로 확인). 부수: phase 충족이 L3 review 게이트를 단축하지 않음(test 로 보존 확인).
- **R4 (문서 정합)**: AGENT_GUIDE 의무범위표(L2=00-05 cycle) vs pre_implementation_required(코드 전 00-02 subset) 구분 명문화 확인. 04 게이트=pre-phase4 hook, 06←05=report-gate 로 사이클 다지점 강제 — 정합.
- **R5 (실인스턴스)**: weatherapp 적용 = 경험적 최종 검증(아래).
