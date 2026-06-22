# Loop Engineering (Loop A + Loop C) + Obsidian 옵션 + DX — 개발 plan

> 설계 정본: vault `TECH - 루프 엔지니어링 개념과 SAGE 적용 설계` (개념·트레이드오프) ·
> `TECH - SAGE loop engineering 설계 스키마 및 초안` (구현 스키마·프롬프트 골격) ·
> `TECH - SAGE 3차 외부자 평가(260622)` (설계 출처).
> 로드맵상 7단계. v0.6.0 → 다음 마이너 릴리즈 대상.

## 0. 목표 / 불변식

SAGE는 codex/claude 등 여러 agent를 통합하는 **SSOT harness engineering system**이다.
이 기능도 동일 원칙을 지킨다:

- **2층 불변식**: 판단 루프는 interpretive phase(05/Act)에만. 결정론 코어(hash·CONTRACT_VERSION·
  write-guard·report←approve)는 루프-free이며 그것이 판단 루프를 종료·한정한다.
- **실행 주체 경계**: SAGE는 루프를 돌리지 않는다. 루프의 진입·종료·예산·카운터를 *게이트*하고,
  루프 본문은 host runtime(claude/codex)이 스킬로 실행한다.
- **하나의 스펙 → host별 렌더**: sage-review 절차는 단일 스펙, claude/codex 양쪽에 렌더. cross-model은
  상대 런타임이 반박자.
- **host 양쪽 동작 필수**: claude-host와 codex-host 모두에서 검증한다(SAGE의 정체성).

## 1. 범위

| 포함 | 제외(후속) |
|---|---|
| Loop A (Phase 05 적대적 review-rework 엔진화) | Loop B (04 커버리지) |
| Loop C (`sage retro` — process-absorb 학습) | Loop D (generate/validate self-heal) |
| Obsidian 옵션 (loop_audit 시각화 + retro human-gate 노트) | — |
| DX (Windows happy-path·5분 quickstart·위협모델 절) | — |

Loop B/D 필요 여부는 4차 weatherapp 검증(8단계) 후 판단.

## 2. 구현 표면 (코드 근거 — v0.6.0 클론본 직접 확인)

| # | 자산 | 위치 | 패턴 재사용 |
|---|---|---|---|
| 1 | `pdca.review_loop` 스키마 | `schema/profile.schema.json`(pdca properties) + `templates/project-profile.yaml` | pdca 폐쇄섹션 확장 |
| 2 | review_loop 검증 | `sage/profile_validate.py`(`_CLOSED_SECTION_FALLBACK["pdca"]` + `_semantic_issues`) | R2/P0-2 fail-closed 패턴 |
| 3 | 루프 감사로그 | `scripts/sage_harness/hooks/runtime/loop_audit.py` | `override_audit.py` append-only JSONL(`_append`/`_read_jsonl`/`_iso`) |
| 4 | Loop A 절차 인코딩 | `templates/core/skills/sage-review.md`(spec) + `templates/core/framework/.claude/skills/sage-review/SKILL.md`(claude 렌더) + codex 전역 렌더 | 기존 CORE 부트스트랩 스킬(매니페스트 비추적, write-guard 면제) |
| 5 | Loop C 명령 | `sage/commands/retro.py` + `sage/cli.py` `_COMMANDS` 등록 | `absorb.py`(제안전용·manifest 루트탐색·자동반영 금지) |
| 6 | Obsidian 옵션 | 기존 `knowledge_capture.vault_path`(마스터 게이트) + `policies/knowledge_capture.py` + `note_convention` | 이미 동작하는 정책 모듈 확장 |
| 7 | doctor 진단 | `sage/commands/doctor.py`(review_loop 유효성 + obsidian 노출) | 기존 옵션 의존성 점검 |

종료 backstop은 이미 존재(`pre_implementation_gate_core.py`의 `_report_gate`: 06은 05 APPROVED 없으면 BLOCK) → 신규 hook 불필요.

## 3. 빌드 순서 (결정론을 안 깨는 순서 — 설계 §8)

- [x] **S1. review_loop 스키마 + 검증 (결정론, 안전)** ✅ 완료
  - schema/profile.schema.json: pdca.properties 에 review_loop 서브스키마(additionalProperties:false, sentinel oneOf, minimum 제약)
  - profile_validate.py: `_CLOSED_SECTION_FALLBACK["pdca"] += review_loop` + `_review_loop_issues` fail-closed 규칙
  - templates/project-profile.yaml: review_loop 기본값 블록(enabled:false — 신규설치 무영향, advisory 우선)
  - sage/commands/doctor.py: `## Loop A` 진단 섹션
  - 단위테스트 45개(유효/무효/병적입력/no-jsonschema 경로)
  - **codex 리뷰 #1 — 6라운드 적대적 검토, 전부 반영:**
    - R1: P0(enabled:1 침묵 disable)·P1×3(sentinel 오타·tier 누락·스칼라 타입) → fail-closed 강화
    - R2: lenses/severity_block 비-list 크래시·refute_threshold 타입 → 가드
    - R3: 부모섹션(profile/pdca/options/risk) 비-dict 크래시 → 섹션 타입 가드(단일출처 FAIL)
    - R4: sorted() 혼합타입·phases/pre_impl 비-iterable → key=str + isinstance 가드
    - R5: 중첩 unhashable 값 → validate_profile 예외 backstop(입력 totality)
    - R6: schema-infra 예외 → WARN 폴백(입력 FAIL 과 구분). root 는 신뢰 파라미터로 의도적 미감싸기(masking 회피, 문서화)
  - **결과**: validate_profile 이 신뢰불가 profile 입력에 대해 total(크래시 0), jsonschema 유무 동일 fail-closed
- [x] **S2. loop_audit.py (결정론, append-only JSONL)** ✅ 완료
  - `scripts/sage_harness/hooks/runtime/loop_audit.py` — override_audit 패턴. loop_open/round/loop_close + read/runs/rounds_of/close_of + `integrity_issues`(run_id 무결성 체크가능 불변식)
  - `.sage/loop_audit.jsonl`(커밋 대상, override.jsonl 과 동급). permissive recorder — 어휘 강제는 CLI/스킬 레이어(S3)
  - 단위테스트 15개 + run-all.sh #34 등록
  - **codex 리뷰 #2 — 2라운드, CLEAN:**
    - R1: P2(비-dict JSON 줄 소비자 크래시)→dict 필터 / P2(run_id 무결성)→integrity_issues 불변식(write 강제 아닌 체크가능, override_audit uuid4 신뢰 선례) / P3 int 계약 문서화
    - R2: CLEAN (비-dict 크래시 봉쇄·integrity 건전·write 미강제 tradeoff 타당 확인)
- [x] **S3. sage-review SKILL 에 Loop A 절차 인코딩 (interpretive)** ✅ 완료
  - `sage review-loop` CLI(review_loop.py, cli.py 등록) — loop_audit 래핑. 프로젝트 루트 자동탐색(cwd 무관), result↔reason 짝 강제, run_id orphan/중복open/중복close/종료후활동 거부, 불가능튜플(survived>found 등) 거부, 음수거부, cfg 스냅샷, show+무결성
  - sage-review SKILL.md(**단일소스→claude repo·codex 전역 동일 배포 = host parity 자동**): disabled/L0L1=단발(하위호환, verdict→Final Status 마커 매핑 명시) / enabled+L2L3=Loop A(FIND/REFUTE/TRIAGE/REWORK 프롬프트 + 고정 우선순위 종료판정 + 라운드 감사 + advisory-first). report←approve backstop 절대 우회 안 함
  - integrity_issues 강화(dup open/close, orphan, 종료후활동) + 참조 스펙·review-protocol.md 동기화
  - 테스트: review-loop CLI 18개 + loop_audit 17개 + run-all #35
  - **codex 리뷰 #3 — 2라운드, CLEAN:** R1 P1(cwd-의존 root)·P2(단발 vocab↔게이트 마커)·P2(CLI integrity 미강제) → 전부 수정. R2 CLEAN + 스코핑 합의(게이트 substring=기존/스코프밖, permissive-lib/strict-CLI=설계)
- [x] **S4. sage retro (Loop C) — 제안 전용** ✅ 완료
  - `sage retro`(retro.py, cli.py 등록): loop_audit 라운드 집계(=리뷰가 잡은 체계적 누락) + 05 approve-phase 문서 결정론 수집 → distiller 프롬프트(기계적→hook/profile·의미적→agent/skill) 제시. **자동반영 없음**(absorb 미러·human-gate). 루트 자동탐색, approve-glob을 profile.pdca 에서(도메인값 0), --feature 토큰경계 필터, --run-id
  - **결정론/interpretive 분리**: gather=결정론(LLM 0), distillation=host AI 프롬프트(sage-review 와 동형). host 분기 없음(프롬프트 host-중립) → parity 자동
  - 테스트: retro 10개(test_retro.py) + run-all #36
  - **codex 리뷰 #4 — 2라운드, CLEAN(P0/P1 0):** R1 P2(손상 audit 줄 silent drop→증거불완전)→integrity 손상줄 표면화 / P3(--feature raw 부분문자열)→basename 토큰경계 매치. R2 P2 CLOSED, P3 좌측'.'경계 보완 후 CLOSED. 설계 충실성(proposal-only·SSOT 미변경·gather/distill 분리) 확인
- [x] **S5. Obsidian 옵션 배선** ✅ 완료
  - `sage/commands/_vault.py` 공용 헬퍼 — 마스터 게이트=`knowledge_capture.vault_path`(3-모드: 미지정=출력안함 / `--vault`=profile게이트 / `--vault PATH`=명시 opt-in). **스키마 키 추가 0**(기존 knowledge_capture 활용)
  - `sage review-loop show --vault` → `<vault>/<folder>/SAGE-loop-audit.md` 대시보드(plain 마크다운 테이블, 플러그인 무관)
  - `sage retro --vault` → `<vault>/<folder>/sage-retro-<stem>-<date>.md` human-gate 노트(`approved: false`, create-only 로 사람 승인 상태 보존)
  - 안전성: folder realpath containment(심링크 포함), leaf-심링크 unlink, filename basename-only, frontmatter 키/값 주입 방지, --feature 토큰경계
  - 테스트: vault 22개(test_vault.py) + run-all #37
  - **codex 리뷰 #5 — 3라운드, CLEAN:** R1 P1(folder 경로탈출)·P1(--vault 게이트)·P2(retro 노트 클로버)·P3(리스트 YAML) / R2 잔여(symlink realpath·리스트 quote) / R3 잔여(leaf symlink·키 주입) → 전부 닫음. 위협모델(사용자 자기 vault) 스코핑 합의(TOCTOU out-of-scope)
- [x] **S6. DX 문서** ✅ 완료
  - README: 위협모델/신뢰경계 절(결정론 게이트 vs 판단, 방어/비방어 명시) + Loop A/C 개요 + Windows happy-path(Git Bash/WSL·SAGE_PYTHON) + CLI 참조에 review-loop/retro 추가 + Obsidian 루프 출력
  - **codex 리뷰 #6(doc-accuracy) — CLI/SAGE_PYTHON 정확 확인, 3건 정직성 교정 반영:** P2(cross-model 조건부로 한정)·P2(루프 종료 *판단*은 host advisory, SAGE는 감사/무결성/설정검증/report←approve backstop — 종료 결정론 *집행*은 후속 명시)·P3(retro 파일명 stem 예시 정확화). 과장 제거, 위협모델 정직성 확보
  - 기존 30초 quickstart 유지(위협모델·루프 개요로 "첫 경험" 보강)
- [x] **S7. 회귀 + host parity 확인** ✅ 완료(구조적)
  - run-all.sh 37개 스텝 전부 PASS (신규 #34 loop_audit·#35 review-loop CLI·#36 retro·#37 vault 포함). profile_validate 45개.
  - **host parity 구조적 보장**: review_loop/retro/_vault CLI 는 host 분기 0(codex 확인), sage-review SKILL 은 단일 소스가 claude(repo)·codex(전역)에 동일 배포. S1 검증 엔진은 양 host 공유 코드.
  - 신규 테스트 합계: profile_validate 35 신규 + loop_audit 17 + review-loop CLI 18 + retro 10 + vault 22 = 102개
  - ⚠️ **fresh-project 양 host e2e**(install→loop→retro)는 8단계 4차 weatherapp 에서 실세계 검증(로드맵)

## 4. 검증 게이트 (각 단계 공통)

- 단위/회귀 테스트 PASS
- codex cross-model 리뷰 (P0/P1 완화 금지 — 제거 우선, 완화는 유저 승인)
- claude + codex 양 host 동작 확인
- 도메인 토큰 0 (엔진 중립성 — 값은 profile에만)

## 5. 진행 로그

- 2026-06-22 plan 작성. S1 착수.
- 2026-06-22 S1 완료 — review_loop 스키마+검증+doctor 진단. codex 6라운드 적대적 리뷰 전부 반영(P0×1, P1×다수, 크래시 하드닝). 45 테스트 + 전체 회귀 PASS.
- 2026-06-22 S2 완료 — loop_audit.py(append-only JSONL + integrity 불변식). codex 2라운드 CLEAN. 15 테스트 + 전체 회귀 PASS.
- 2026-06-22 S3 완료 — sage review-loop CLI + sage-review SKILL Loop A 인코딩(단일소스 양 host) + 스펙/protocol 동기화. codex 2라운드 CLEAN(host parity·결정론 경계·report←approve 미우회 확인). 35 테스트(CLI 18+audit 17) + 전체 회귀 PASS.
- 2026-06-22 S4 완료 — sage retro(Loop C process-absorb): 결정론 증거수집 + distiller 프롬프트, 자동반영 없음. codex 2라운드 CLEAN(P0/P1 0). 10 테스트 + 전체 회귀 PASS.
- 2026-06-22 S5 완료 — Obsidian 옵션(_vault 헬퍼 + show --vault 대시보드 + retro --vault human-gate). 스키마 키 추가 0(기존 knowledge_capture 활용). codex 3라운드 CLEAN(경로탈출·심링크·키주입 전부 닫음, 위협모델 스코핑 합의). 22 테스트 + 전체 회귀 PASS.
- 2026-06-22 S6 완료 — README DX(위협모델·Loop A/C·Windows·CLI참조·Obsidian). codex doc-accuracy 리뷰로 과장 3건 교정(정직성 확보).
- 2026-06-22 S7 완료 — 전체 회귀 37스텝 PASS + 신규 102 테스트. host parity 구조적 보장(단일소스 스킬·host-중립 CLI). fresh-project 양 host e2e 는 4차 weatherapp(로드맵 8단계)로.
- **🎯 S1~S7 전부 완료. Loop A(엔진화)+Loop C(retro)+Obsidian 옵션+DX 문서. codex 6리뷰 사이클 전부 반영. 미커밋.**
