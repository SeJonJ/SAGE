# 대화형 profile 저작/수정 + 루프-vault 활성화 — 설계 스펙

> 로드맵 8단계(4차 weatherapp) **직전** 작업. 목적: 루프 엔지니어링(v0.7.0)을 "대화로 켜고 수정"하는
> DX 완성. 4차 weatherapp 이 `/sage-init` 으로 루프를 켜는 현실적 e2e 가 되도록 선행한다.
> 연관: `plan_docs/loop-engineering-plan.md`(v0.7.0). 미구현 — 착수 전 합의용.

## 0. 목표 / 전제

대화형 저작 3종을 완성한다:

| 스킬 | 역할 | 상태 |
|---|---|---|
| `/sage-init` | profile **최초 작성**(루프 포함) | 실재 — 루프 토픽 **추가 필요** |
| `/sage-profile-modify` | profile **수정**(루프·게이트 값) | **신규** |
| `/sage-asset` | agent·hook·skill 자산 추가·수정 | 실재 (변경 없음) |

**전제(불변)**:
- profile 은 hand-authored SSOT — write-guard 대상 아님. 그래서 init/modify 는 **YAML 직접 편집 + `sage validate`**(spec→generate 아님). 자산(sage-asset)과 mechanically 다름.
- "값만 바꾸고 스키마 키 추가/삭제 금지"(sage-init Hard rule 동일).
- 모든 경로가 `sage validate --schema` + `sage doctor` fail-closed 로 마무리. FAIL 우회 금지.

## 1. 빌드 항목 + 의존 순서

```
A. knowledge_capture vault-output 플래그 2개 + validation + sage-review/retro 배선   ← 전제(먼저)
B. sage-init Step 2 에 루프 토글 + (조건부) vault 활성화 인터뷰                       ← 첫 작성
C. /sage-profile-modify CORE 스킬 신설 (B 와 공유 인터뷰 세트)                        ← 수정
```

A 가 없으면 B/C 의 "vault 활성화 대화"가 저장될 곳이 없다 → **A 부터**.

## 2. A — vault-output 활성화 플래그 (스키마 변경 0)

현재 vault 출력(대시보드·retro 노트)은 invocation-only(`--vault` 매번 수동). profile 에 활성화 상태를
둬서 "켜두면 자동"으로 만든다. `knowledge_capture` 는 스키마상 **open object** 라 키 추가에 스키마 수정 불필요
(S5 에서 새 키 0 으로 한 것과 동일 결).

```yaml
knowledge_capture:
  vault_path: ""                  # 마스터 게이트(이미 있음) — 비면 vault 전부 OFF
  note_convention: { folder: "wiki" }
  loop_audit_dashboard: false     # NEW: 루프 종료 시 vault 에 감사 대시보드 자동 갱신
  retro_note: false               # NEW: sage retro 시 vault 에 human-gate 회고 노트 자동 작성
```

**검증(`profile_validate.py` 에 함수 추가, 패턴은 review_loop 검사와 동일):**
- `loop_audit_dashboard` 또는 `retro_note` 가 `true` 인데 `vault_path` 비었음 → **WARN**("vault 출력 켰으나 vault_path 미설정 → OFF"). 기존 obsidian degrade 검사와 동형.
- 두 플래그는 bool 아니면 WARN(타입). knowledge_capture 는 open object 라 키 오타는 스키마가 못 잡지만, 이 둘은 거버넌스 게이트가 아닌 부가 출력이라 WARN 수준으로 충분(닫힌 섹션화 안 함 — 기존 freeform 키 보존).

**배선:**
- `sage-review` SKILL.md(interpretive): 루프 종료(APPROVED/BLOCKED) 직후, `knowledge_capture.loop_audit_dashboard:true` 이고 `vault_path` 설정 시 → `sage review-loop show --vault` 실행을 절차에 추가. (host 가 문서 규칙대로 — 결정론/판단 분리 유지.)
- `sage retro`(결정론 CLI): `knowledge_capture.retro_note:true` 이고 `vault_path` 설정 시 → `--vault` 명시 없어도 vault 출력 기본 on(`args.vault is None` 이면 profile 값으로 활성). 명시 `--vault PATH` 는 그대로 우선.

**검증(A) 테스트:**
- profile_validate: 플래그 의존 WARN(켜짐+vault_path 빈) / 정상(켜짐+vault_path 있음) / 꺼짐 무이슈.
- retro: 플래그 true + vault_path 설정 → `--vault` 없이도 노트 생성 / 플래그 false → 미생성 / 명시 `--vault` 우선.

## 3. 공유 인터뷰 질문 세트 (B·C 가 DRY 로 참조)

drift 방지를 위해 review_loop + vault 활성화 질문을 **한 번 정의**하고(권위 출처 `docs/agent/bootstrap-authoring.md` 의 신규 절), `/sage-init` Step 2 와 `/sage-profile-modify` 가 동일 세트를 사용한다. **모든 토글에 한 줄 plain 설명**(sage-init 의 "L0~L3 의미 설명" 스타일).

### 3.1 루프 토글 (Step 2 옵션, 기본 off)

```
"이 프로젝트에서 Phase 05 리뷰를 적대적 루프로 돌릴까요? (기본: 단발 리뷰)"
  · 단발(off)  — reviewer 1회 검토. 가볍고 빠름.
  · 루프(on)   — 찾기→반박→수정을 수렴까지 반복. L2/L3 만. 비싸지만 거짓양성 거르고 누락 줄임.
off → review_loop.enabled:false 유지, 이하 스킵
on  → 아래 상세
```

### 3.2 루프 상세 (on 일 때만, 각 한 줄 설명)

| 질문 | profile 키 | 한 줄 설명 |
|---|---|---|
| 어떤 관점으로 볼까요? (스택 기반 제안) | `lenses` | FIND 가 도는 검토 렌즈. 엔진 어휘: correctness/security/concurrency/convention/lifecycle/performance/error_handling/data_integrity/api_contract |
| L2·L3 최대 몇 라운드? | `max_iterations` | 수렴 못 하면 이 횟수에서 BLOCKED. 기본 L2:1·L3:3 |
| 토큰 예산은? | `budget_tokens` | 누적 토큰 초과 시 BLOCKED(loop-until-budget). 기본 L2:150k·L3:600k |
| 반박자 몇 명? | `refuters` | finding 당 반증 시도 수. 생존 = 반증표 < 과반(거짓양성 필터). 기본 2 |
| 연속 dry 몇 라운드면 수렴? | `dry_rounds` | K라운드 연속 신규 0 → APPROVED. 기본 1 |
| 어떤 심각도면 승인 불가? | `severity_block` | 미해결 시 APPROVED 막는 심각도. 기본 [P0,P1] |
| cross-model 반박 쓸까요? | `cross_model` | `options.cross_model` 연동(상대 런타임이 반박자). 기존 cross_model 토글 따름 |

> `cross_model` 토글은 sage-init 에 이미 있으므로(Step 2), 루프 인터뷰는 그 값을 *재사용*하고 새로 묻지 않는다.

### 3.3 vault 활성화 (조건부: 루프 on **AND** `vault_path` 설정됨일 때만 — 한 턴)

```
"루프 산출물을 Obsidian vault 에도 남길까요? (vault_path 감지됨)"
  · 감사 대시보드  — 라운드별 발견/채택/수렴 추이를 vault 노트로 (plain 테이블, 플러그인 무관)
  · 회고 노트      — sage retro 결과를 approved:false 노트로, vault 에서 검토·승인(human-gate)
  · [둘 다 / 대시보드만 / 회고만 / 안 함]
→ knowledge_capture.loop_audit_dashboard / retro_note 에 매핑
```

루프 off 또는 vault_path 빈 경우 이 턴은 **나타나지 않음**(조건부 — sage-init 의 "켤 때만 상세 진입" 패턴).

## 4. B — sage-init Step 2 확장

- Step 2(Options) 에 **루프 토글**을 신규 추가(cross_model 토글 *뒤* — 의존 때문). §3.1 → on 이면 §3.2 인터뷰 → §3.3 조건부 vault.
- 기존 Hard rule·언어(한국어 인터뷰)·"한 토픽 한 턴" 스타일 그대로.
- Step 0 의 "이미 부트스트랩됐으면 멈춤" 동작은 유지 — 루프 토픽도 *최초 작성* 한정. 이미 켜진 루프 수정은 C 로.
- 산출: `profile.pdca.review_loop` + `knowledge_capture.{loop_audit_dashboard,retro_note}` 작성 → 기존 handoff(generate/validate)로.

## 5. C — /sage-profile-modify (신규 CORE 스킬)

CORE 부트스트랩 스킬(sage-asset 와 동급 — 단일 소스, install 이 claude repo·codex 전역 배포, write-guard 면제, 매니페스트 비추적). `install._CORE_SKILLS` 에 추가.

**파일**: `templates/core/framework/.claude/skills/sage-profile-modify/SKILL.md`(렌더) + `templates/core/skills/sage-profile-modify.md`(참조 스펙).

**절차:**
- **Step 0**: 현재 `sage/project-profile.yaml` + `AGENT_GUIDE.md` + `bootstrap-authoring.md` 읽기. profile 이 미부트스트랩이면 → "수정 아니라 `/sage-init` 부터" 안내 후 중단.
- **Step 1**: 어느 섹션 수정? (유저 의도에서 추론 or 질문) — project / components / verification.commands / risk(L0~L3 globs·keywords·l3_review_strategy) / **pdca.review_loop**(§3 공유 세트) / options / **knowledge_capture**(vault_path·§3.3 플래그) / file_type_map.
- **Step 2**: 현재 값 읽어 보여주기 → 변경안 **diff 제안** → **consequence 경고**(§6) → 승인 받기.
- **Step 3**: 승인 시 profile.yaml **직접 편집**(generate 아님).
- **Step 4**: `sage validate --schema --kind all` + `sage doctor` 실행. FAIL → 가리킨 값 수정, **우회 금지**.
- **Hard rules**: 값만(스키마 키 불변) · consequence-aware · 항상 validate.

**review_loop/vault 수정은 §3 공유 인터뷰 세트 재사용**(B 와 동일 질문·설명) → 드리프트 0.

## 6. consequence 경고 규칙 (C 의 핵심 — 적용 *전* 고지)

profile 수정은 거버넌스 게이트 강도를 바꾼다. 아래는 변경 적용 전 반드시 설명:

| 변경 | 고지할 영향 |
|---|---|
| `risk.l3_filename_globs`/`l3_content_keywords` 제거 | 그 도메인이 더는 L3 게이트/리뷰를 안 받음(완화) |
| `risk.l3_review_strategy` 비움/변경 | L3 가 hard-block 되거나 리뷰 매칭 방식이 바뀜 |
| `pdca.pre_implementation_required` phase 제거 | 그 phase 없이도 코드 수정 허용(게이트 완화) |
| `verification.commands` 비움 | 그 검사(build/test/lint) skip |
| `review_loop.enabled` false | Phase 05 가 단발 리뷰로 복귀 |
| `review_loop.max_iterations[L3]` 낮춤 | BLOCKED 전 rework 라운드 감소(예: 1=사실상 단발) |
| `review_loop.budget_tokens` 낮춤 | 루프가 예산으로 더 일찍 BLOCKED |
| `review_loop.severity_block` 축소 | 낮은 심각도 finding 이 APPROVED 를 안 막음 |
| `knowledge_capture.vault_path` 비움 | vault 기능 전부 OFF |

## 7. 검증 + codex 리뷰 게이트

- **A(코드)**: profile_validate 단위(플래그 의존 WARN) + retro 자동-vault 테스트 + sage-review 절차 문구. run-all 등록. → codex 리뷰.
- **B(스킬)**: interpretive 라 단위테스트 대신 — 스킬 본문에 루프 토픽 존재(conformance) + fresh-project dry-run. → codex 리뷰(host 중립·결정론 분리·인터뷰 부담).
- **C(스킬)**: 신규 CORE 스킬 본문 + install `_CORE_SKILLS` 배포 확인(claude/codex 양 host) + 시나리오(값 편집→validate). → codex 리뷰.
- 각 단계 host 양쪽 동작 + 도메인값 0 확인.

## 8. 빌드 체크리스트

- [x] A1. knowledge_capture `loop_audit_dashboard`/`retro_note` 플래그 + 템플릿 기본값(false) + 검증(`_knowledge_capture_issues`: vault_path 의존 WARN·비-bool WARN)
- [x] A2. retro 가 profile 1회 로드 + `retro_note` 플래그 읽어 `--vault` 자동화 + 테스트(자동활성/off 미활성)
- [x] A3. sage-review SKILL 에 "loop_audit_dashboard 면 종료 시 show --vault" 절차 추가
- [x] A4. **codex 리뷰 A** — host parity·is True·WARN-level 건전 확인. P2×2 반영: `--no-vault`(명시 off 우선순위) + 타입 가드(knowledge_capture 비-dict FAIL·vault_path 비-str WARN·vault_target/retro/doctor 방어). closure 후 doctor.py 잔여까지 수정.
- [x] B1. `bootstrap-authoring.md` 에 "Review loop + vault interview set" 공유 세트 정의(토글·상세 7키·조건부 vault, 각 한 줄 설명)
- [x] B2. sage-init Step 2 에 루프 토글 + 공유 세트 참조 + 조건부 vault(cross_model 재사용 명시)
- [x] B3. **codex 리뷰 B — CLEAN(1회):** DRY 단일소스·키 정합(A와)·조건부 명확·one-topic-per-turn·Hard rule 무충돌 확인
- [x] C1. `/sage-profile-modify` 렌더 + 스펙 + install `_CORE_SKILLS` 등록(claude repo·codex 전역) + AGENT_GUIDE/test_install 갱신. e2e 양 host 배포 확인
- [x] C2. consequence 경고 표(§6) + 공유 인터뷰 세트 참조(DRY) + 직접편집/validate 마무리 + 미부트스트랩 시 /sage-init 라우팅
- [x] C3. **codex 리뷰 C — 반영 완료:** P1(미부트스트랩 라우팅을 is_bootstrapped 술어와 일치) + P2(AGENT_GUIDE 면제목록) → 추가로 **잠복 write-guard 코드 갭**(생성가드 .sh 면제 패턴에 sage-profile-modify 누락 → 직접편집 차단됐을 것) + cases.tsv 테스트행 + hook 스펙 문서까지 4곳 정합. manifest 재스탬프(validate PASS).
- [x] D. 전체 회귀(37스텝)+install(25)+신규 테스트 PASS. host parity 구조적(단일소스 양 host 배포 e2e 확인). fresh-project 실세계 e2e 는 8단계 4차 weatherapp.

## 9. 진행 로그

- 2026-06-23 설계 스펙 작성(미구현). 의존순서 A→B→C. 4차 weatherapp 선행.
- 2026-06-23 A 완료 — knowledge_capture vault 플래그+검증+retro 자동활성+sage-review skill. codex 1라운드(P2×2: --no-vault 우선순위·타입가드+doctor 잔여) 반영.
- 2026-06-23 B 완료 — bootstrap-authoring 공유 인터뷰 세트 + sage-init Step 2 루프 토글. codex CLEAN.
- 2026-06-23 C 완료 — /sage-profile-modify CORE 스킬(렌더+스펙+install 등록+양 host 배포) + consequence 경고. codex 1라운드(P1 라우팅·P2 면제목록 + 잠복 write-guard 코드갭) 반영, manifest 재스탬프.
- **🎯 7.5단계 A·B·C 전부 완료. 전체 회귀+install PASS. 미커밋. 다음=커밋→릴리즈 판단→8단계 4차 weatherapp.**
