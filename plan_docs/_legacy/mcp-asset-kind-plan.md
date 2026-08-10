# MCP — 4th Governance Asset Kind (plan)

> 로드맵 3단계. MCP 서버 정의를 hook·agent·skill 에 이은 **4번째 거버넌스 자산 종류(`mcp`)**로 편입한다.
> 설계 정본 = vault [[SAGE-MCP 개발]] + [[TECH - SAGE 통합 마스터 설계]] §1.2/§5.4/§6 Phase M.
> 본 문서는 그 설계를 **구현 직전 phase-first 로 확정**하고, codex cross-model R1 이 적발한 P0 2건(SSOT 모순·ChatForYou 선반영 실물)을 반영해 설계를 정정한다.

상태: ✅ **구현 완료(2026-06-20)**. cross-model codex 6R 리뷰 통과(최종 SHIP). 전체 회귀 + repo validate --schema PASS, 설치트리 도메인토큰 0.

---

## Phase 00 — CONTEXT (why / scope / 위험)

### 0.1 왜
1차 종합평가에서 MCP 차원만 4/10(최저). SAGE 는 이미 MCP 를 *소비*하면서(codegraph·obsidian) 정작 그 서버 정의는 spec-SSOT·manifest·drift 차단 **밖**에 방치. 표준 연결 레이어를 4번째 자산으로 승격해 동일한 `spec → generate → validate → manifest` 폐루프로 관리한다.

### 0.2 적합성 — MCP 는 결정론 자산
MCP 서버 정의는 `{command,args,env}`(stdio) 또는 `{type,url}`(remote) 같은 **순수 선언 데이터**다. LLM 렌더 불요 → `spec → config 직렬화`가 결정론적. hook 과 같은 결정론 쪽에 안착(agent/skill 의 interpretive 아님).

### 0.3 ★ 설계 정정 — SSOT 위치 (codex R1 P0-1)
**원설계 모순**: "MCP 는 `docs/sage_harness/mcps/{id}.md` spec-SSOT 자산"이라면서 D1 은 "payload 는 `profile.mcp.servers` 전적 주입". payload 가 profile 이면 spec md 는 SSOT 가 아니고, `profile.mcp.servers.x.args` 변경 시 무엇이 stale 인지 불명(manifest 는 spec_hash 만 추적).

**정정 결정 (이 문서가 정본)**:
- **payload(transport·command·args·env 변수명·runtime_targets)는 spec md `docs/sage_harness/mcps/{id}.md` 가 SSOT.** `spec_hash` 가 staleness 담당 — hook/agent/skill 과 동형.
- **`profile.mcp` 는 enable 토글 + 공유 설정만** (어떤 spec 을 생성 대상에 포함할지). payload 아님.
- **독립성(D1) 유지**: 엔진(`sage/*.py`)은 mcp 서버 0종. spec md 는 **소비 프로젝트 인스턴스 자산**(consuming project 가 저작) — hook spec 이 인스턴스 도메인값을 담는 것과 동일. CORE 템플릿은 mcp spec 0종 배포.

근거: SAGE spec-SSOT 철학은 "의도는 spec md, 산출물은 derived". profile 은 전역 config surface(위험 globs·검증 명령 등)이지 asset-local SSOT surface 가 아니다. payload 를 profile 에 두면 두 번째 hash source 가 필요해지고 SSOT 가 쪼개진다.

### 0.4 ChatForYou 선반영 — shadow 파일럿 (codex R1 P0-2)
"참고 데이터로만 사용"은 로드맵 "Enhancement(ChatForYou 선반영)" 항목을 조용히 스킵하는 것. 실물 산출 필요:
- ChatForYou 실제 MCP 정의(codegraph stdio + obsidian-vault)를 **SAGE fixture 로 export** → 샌드박스 인스턴스에서 `.mcp.json`(claude) + `.codex/config.toml`(codex) **생성** → `validate` PASS 까지 폐루프.
- **라이브 무변경 증명**: ChatForYou 의 실제 `.codex/config.toml`·`~/.claude.json` 은 **건드리지 않는다**(마스터 설계 437행: ".claude/.codex 생성기를 ChatForYou 에 과도 적용 금지 = SAGE 본체의 일"). Tier 5 마이그레이션 영역과 분리.
- **한계 명문화(codex R1 P1-7)**: ChatForYou 의 실제 Claude MCP 는 전역 `~/.claude.json` 에 있고 본 설계는 프로젝트 `.mcp.json` 으로 직렬화 → 파일럿은 **codex 측은 실 리허설, claude 측은 test-data 수준**. 과대해석 방지.

### 0.5 위험 / 범위
- **L3 도메인 = 시크릿**: MCP env 는 API 키·토큰 흔함. 생성물에 리터럴 시크릿이 새면 사고. → D2 시크릿 거부 문법(§1.4)이 핵심 위험 통제.
- **공유 config 클로버**: `.codex/config.toml` 전체 재작성은 비-MCP 섹션 파괴. → managed-block 소유권 모델(§2.3).
- 범위 밖(v1 제외, 명시): MCP gateway 거버넌스 / 시크릿 저장소 연동(env 변수명 참조까지만) / `absorb --kind mcp`(§1.7 결정).

---

## Phase 01 — CONTENT (요구사항 / 데이터 스키마 / 계약)

### 1.1 spec md 섹션 (`docs/sage_harness/mcps/{id}.md`)
★ codex R2 P1: **모든 기계 필드는 frontmatter** 에 두고 **pyyaml 로 파싱**(generate 빌드 의존성 이미 사용). hook 의 regex `_parse_runtime_bindings`(generate.py:42) 는 단일 인라인 맵 전용이라 `runtime_targets`/`args`/`env` 배열을 안전히 못 실음 → **재사용 금지, 별도 ad-hoc 섹션 파서도 금지**. 본문은 사람용 `## intent` 만.
```
---
id: codegraph
kind: mcp
transport: stdio            # stdio | http | sse
runtime_targets: [claude, codex]
server_binding:
  command: codegraph                      # stdio 전용
  args: ["serve", "--mcp"]
  env: [CODEGRAPH_TOKEN]                   # env 변수명만 (값 절대 금지)
  # remote 예: url: "https://..."  (http/sse 전용, userinfo/query-token 금지)
---
## intent
(이 서버가 무엇을 연결하나 — 사람이 쓰는 1~3줄. 기계 파싱 안 함.)
```
- 파싱: frontmatter YAML 블록을 `yaml.safe_load`. pyyaml 미설치 → generate FAIL(hook profile 컴파일과 동일 fail-closed).

### 1.2 profile.mcp (enable 토글 — payload 아님)
```yaml
mcp:
  enabled: [codegraph, obsidian]   # 생성 대상 spec id 목록 (없거나 빈값 = mcp 생성 0건, 하위호환)
```
profile.schema.json top-level 에 `"mcp": { "type": "object" }` 추가(`additionalProperties:false` 통과용). 내부는 느슨.

### 1.3 manifest 엔트리 (`mcps/{id}`)
- 신규 `form: "declarative"` (codex R1 P1-6 — native/interpretive 재사용 시 `sage review`·currentness 오분류).
- `spec_hash`: spec md 해시(SSOT staleness).
- `render_hash`: target 별 — **placeholder-preserving canonical 직렬화의 해시**(claude=`.mcp.json` 의 해당 서버 블록 / codex=managed-block 추출 모델). ★ codex R2: 전체 `config.toml` 아님 — 블록 밖 무관 편집이 false-STALE 유발 방지. spec 이 env 값을 애초에 안 담으므로 "시크릿 제외"는 불필요(거부 문법이 hash 전에 secret-bearing config 를 FAIL).
- `conformance`: PASS/FAIL/STALE/UNKNOWN (기존).
- manifest.schema.json: form enum 에 `declarative` 추가, render_hash 는 기존 claude/codex 키 재사용.

### 1.4 ★ 시크릿 거부 문법 (codex R1 P1-3, fail-closed)
validate 가 렌더 config 를 **파싱 후** 검사. **FAIL**(redact 아니라 거부) vs **WARN** 구분 (★ codex R2 P1 — 오탐 방지):
- **FAIL**: `env` 값이 정확한 `${VAR}` placeholder 아님(리터럴 값 금지) / remote `url` userinfo(`user:pass@`) 또는 token·query(`?...token=`,`?...key=`) / `Authorization: Bearer ...` 류 헤더가 args 에 인코딩 / 고엔트로피 토큰이 **`key=`·`token=`·`auth` 컨텍스트와 동반**.
- **WARN**: 고엔트로피 토큰 **단독**(base64-ish 플래그·해시·opaque id·JWT-유사 테스트 입력 오탐 방지) / `command`·`args` 절대경로의 `/Users/<name>` username 누출(이식성·프라이버시).
- hash 는 **placeholder-preserving canonical 모델**에 대해 계산(secret-bearing 은 hash 전에 거부).

### 1.5 중복/충돌 정책
- 같은 `mcp_servers.<name>` 가 managed-block **밖**에 존재 → validate FAIL(소유권 충돌).
- spec id 중복 / enabled 에 미존재 spec 참조 → FAIL.

### 1.6 validate 매트릭스 (테스트가 검증할 케이스)
정상 PASS · missing managed-block · managed-block marker 중복/malformed · `.codex/config.toml` TOML 파싱 실패 · inline secret(FAIL 케이스) · stale hash · unsupported transport · target mismatch(spec runtime_targets ↔ 생성 대상) · placeholder 위반 · **orphan `mcps/{id}.md`(manifest 미등록)** · **`.mcp.json` 에 managed 밖 unmanaged 서버 존재** · **단일-target(claude-only/codex-only) currentness 오분류 없음** · **블록 밖 무관 config.toml 편집이 false-STALE 안 만듦**.

### 1.7 absorb 결정
v1 = **`absorb --kind mcp` 미구현**(명시). 손편집 config → spec 역흡수는 v2. 이유: v1 은 정방향(spec→config) 폐루프 확립이 우선, 역방향은 hook/skill absorb 처럼 후속. plan 에 박제해 "미구현"이 누락 아닌 결정임을 분명히.

---

## Phase 02 — DESIGN (아키텍처 / touch-points / 테스트)

### 2.1 코드 touch-points (실측 검증됨)
- kind choices 에 `"mcp"` 추가: `generate.py:21` · `validate.py:32` · `review.py:21`. (absorb 는 §1.7 로 v1 미배선 — choices 도 추가 안 함, 추가 시 미구현 경로 노출.)
- `AssetPaths`(asset_paths.py): kind 에 `mcp` 허용. spec 경로 일반화됨(`{kind}s/{id}.md`) → `mcps/{id}.md` 자동. core/native/adapter/claims 는 mcp 미사용(spec 만).
- `generate.py`: `_gen_mcp(args, root)` 신설 + `run()` 분기 + `--kind mcp` choices. spec frontmatter 를 **pyyaml** 로 파싱(§1.1) → JSON·TOML 직렬화 + manifest 스탬프. `_gen_hook` 의 스탬프 패턴(`_stamp_manifest`) 참고하되 mcp 전용 스탬프(spec_hash + render_hash) 작성.
- `validate.py`: 3번째 검증 경로 `_validate_mcp`(결정론 schema check — 필수필드·transport 화이트리스트·시크릿 거부·중복·staleness). hook(hash+contract)·interpretive(agent/skill) 와 분리. **orphan 탐지를 mcps/ 로 일반화**(현 validate.py:328 은 hooks/ 만 스캔 → mcps/ 추가).
- `review.py`: form `declarative` 의미 + **단일-target 인식**(spec.runtime_targets 가 claude-only/codex-only 면 그 target 만 currentness 판정 — 누락을 stale 로 오분류 방지).
- `manifest.schema.json`: form enum + `declarative`. `profile.schema.json`: top-level `mcp`.
- **★ py3.10 TOML 구멍(codex R2 P0)**: `requires-python>=3.10` + CI 3.10/3.11/3.12. `tomllib` 은 3.11+ → guarded import `try: import tomllib except ImportError: import tomli as tomllib`. `tomli` 를 py<3.11 조건부 의존(pyproject `[project.optional-dependencies]`/환경마커)으로 선언. 둘 다 없으면 TOML 검증은 best-effort skip(생성은 진행, WARN). 정본 직렬화 자체는 표준 라이브러리 불요(문자열 빌드).

### 2.2 직렬화 (target 별)
- **claude → `.mcp.json`** (SAGE 전용 파일, 프로젝트 스코프): JSON `{"mcpServers": {"<id>": {command,args,env} | {type,url}}}`. **SAGE 소유 + write-guard 대상**(D3 비대칭 — codex R1 P1-4).
- **codex → `.codex/config.toml`** (공유 파일): `[mcp_servers.<id>]` 를 **managed-block 으로 교체**:
  ```
  # >>> SAGE MCP START (generated by sage generate — do not edit)
  [mcp_servers.codegraph]
  ...
  # <<< SAGE MCP END
  ```
  - 블록 **밖**의 비-MCP 섹션 보존(전체 재작성 금지).
  - 생성 후 `tomllib`(py3.11+ 표준)로 파싱해 유효 TOML 검증(깨진 산출 방지). **tomlkit/tomli-w 의존 회피** — managed-block 문자열 치환 + 표준 파서 검증으로 충분(codex R1 P1-5).
  - 블록 내부 ordering/spacing canonical 고정(결정론).
- render_hash 는 위 산출(시크릿 제외 모델)에 대해 계산.

### 2.3 소유권 모델 (D3, codex R1 P1-4 / R2 P1 비대칭)
- `.mcp.json`: 전적 SAGE 소유 → write-guard 경로 추가. ★ codex R2: 현 가드(`generated-artifact-write-guard.sh:43`)는 `.claude/.codex/{agents,hooks,skills}/*` 만 매칭 → `.mcp.json` 은 **repo 루트**라 미보호. **루트파일 규칙 신규 추가** + 테스트(spec md `generated-artifact-write-guard.md:23` 도 갱신). 깨끗한 추가.
- `.codex/config.toml`: 전체 파일 가드 불가(비-MCP 설정 공존) → managed-block 만 소유. validate 가 (a) 블록 staleness (b) 블록 밖 중복 `mcp_servers.<name>` 검사. "no write-guard anywhere" 안일함 회피.

### 2.4 ChatForYou shadow 파일럿 산출물
- fixture: `fixtures/mcp/chatforyou/` 에 codegraph(stdio)·obsidian(filesystem stdio) spec md + enable profile.
- 샌드박스 인스턴스(임시 dir)에서 install→generate(`--kind mcp --target both`)→validate PASS 폐루프 테스트(golden-instance e2e 에 mcp 케이스 추가).
- 변이 teeth: 시크릿 리터럴 주입 시 FAIL / managed-block 밖 중복 시 FAIL / spec 변경 후 미generate 시 STALE.
- 라이브 ChatForYou config 무변경(테스트는 임시 dir 한정) — grep 가드.

### 2.5 테스트 계획
- `_gen_mcp` 단위: JSON·TOML managed-block 직렬화 결정론(byte-stable), 재생성 idempotent.
- `_validate_mcp` 단위: §1.6 매트릭스 전 케이스.
- 시크릿 거부 문법(§1.4) 각 항목 변이 teeth.
- 기존 hook/agent/skill 회귀 0(kind 추가가 기존 경로 불변).
- wheel smoke + golden e2e 에 mcp 합류.
- 전체: `validate --kind all` PASS, 설치트리 도메인토큰 0, CI green.

### 2.6 작업 순서
1. 스키마(profile.mcp + manifest form:declarative) + AssetPaths mcp 허용.
2. `_gen_mcp` JSON 직렬화(claude) → 단위 테스트.
3. `_gen_mcp` TOML managed-block(codex) + tomllib 검증 → 단위 테스트.
4. `_validate_mcp`(시크릿 거부·중복·transport·staleness) → 매트릭스 테스트.
5. write-guard `.mcp.json` 경로 + config.toml managed-block 소유.
6. CLI choices(generate/validate/review) + review form:declarative 의미.
7. ChatForYou shadow fixture + golden e2e mcp 케이스 + 변이 teeth.
8. README/wiki 반영.
- **각 단계 후 필요 시 codex 논의, 최종 완료 전 codex 3~5R 리뷰**(유저 지침).

---

## cross-model 리뷰 로그
- **R1 (설계, 구현 전)**: codex-cli 0.141.0. P0 2건(SSOT 모순→payload spec md 이동 / ChatForYou shadow 파일럿 실물) + P1 6건(시크릿 거부 문법·D3 비대칭 소유권·TOML managed-block·form:declarative·claude 전역 한계·absorb 명시) 전부 반영(완화 없음, [[feedback_cross_model_p0_no_downgrade]]). → 본 plan 에 박제.
- **R2 (정정된 plan, 구현 전)**: payload→spec-md 이동이 **옳다고 확인**(독립성 보존, P0-1 해소). 신규 P0 1건(py3.10 `tomllib` 부재 → guarded import + tomli 폴백) + P1 6건(spec frontmatter pyyaml 파싱·review 단일-target 인식·write-guard `.mcp.json` 루트 규칙·entropy 휴리스틱 WARN 강등·validate orphan mcps/ 일반화·render_hash managed-block 한정) + P2 1건(secret-excluded→placeholder-preserving 용어) 전부 반영.
- **R3 (구현 리뷰)**: 실제 코드 검토(repro 동반). P0 1건 + P1 3건 + P2 1건 전부 수정(완화 없음):
  - **P0 산출물 드리프트 미탐지**: validate 가 spec→manifest 만 대조 → `.mcp.json`/`.codex` managed-block **직접편집** 미탐지(.codex 는 write-guard 없음). → validate 가 **실제 산출물**을 spec 기대값과 대조(claude 엔트리 canonical / codex 블록 조각), 산출물 부재·변조 = STALE.
  - **P1 parse 타입 미검증**: `args:"--mcp"`→문자분해, `env:"X"`→문자분해, `id:foo.bar`→TOML 중첩테이블. → args/env 리스트 타입 강제 + id 문법(`[A-Za-z0-9_-]+`, 점 금지).
  - **P1 generate 비원자성**: .mcp.json 쓴 뒤 codex FAIL → 부분상태. → validate-all-then-write-all(전 target 검증 후에만 쓰기).
  - **P1 split-arg 시크릿 우회**: `["--token","<hi-entropy>"]`→WARN. → 인접 인자(시크릿 플래그 뒤 고엔트로피) FAIL.
  - **P2 frontmatter 취약**: CRLF/trailing-space 실패. → 정규식 `---[ \t]*\r?\n` 완화.
  - 각 수정 회귀 가드 테스트 추가(test_gen_mcp.py TestR3Hardening 7건). 전체 회귀 + write-guard 29 PASS.
- **R4 (R3 수정 검증)**: R3 수정 대부분 **정확 확인**(.mcp.json 드리프트·parse 타입·CRLF·bearer). 신규 P0 1건 + P1 2건 추가 수정:
  - **P0 codex substring 우회**: managed-block 안 multiline 문자열에 기대 조각을 숨기고 실제 서버 변조 가능. → `codex_block_has_server` 를 **TOML 파싱 후 구조 비교**로 교체(파서 미가용 시만 substring 폴백).
  - **P1 write 비원자성 잔여**: per-file 순차 쓰기 → 중간 OSError 시 부분상태. → **temp 파일 + os.replace 일괄 승격**(기존 파일 무손상).
  - **P1 split-secret 오탐**: `_SECRET_FLAG_RE` 비앵커 → `oauth` 가 `auth` 접미사로 오탐. → `^...$` 앵커(인자 전체가 플래그여야).
  - 회귀 가드 추가(TestR4Hardening 4건). 전체 회귀 PASS, repo validate --schema PASS.
- **R5 (구현 재검증)**: R4 수정 3건 정확 확인. 신규 P1 1건: managed-block '안'에 미선언 서버(`[mcp_servers.rogue]`) 주입이 validate PASS·review auto 통과(블록은 SAGE 전적 소유인데 초과 서버 미탐지). → `codex_servers_inside_block`(TOML 파싱) + validate 소유권 검사에 "블록 내 미선언 서버 = FAIL" 추가. 판정 NO-SHIP.
- **R6 (최종 확인)**: R5 수정이 validate 는 닫았으나 `sage review` 는 per-asset `_validate_mcp` 만 호출 → run-level 소유권 검사 누락 → 주입 서버 review auto-approve(end-to-end 미폐쇄). → review 가 ownership 검사를 1회 수행, FAIL 시 codex-target mcp 자산 자동승인 차단. 회귀 가드 추가(review --gate exit 1). 판정 NO-SHIP→수정.
- **최종 확인**: R6 수정 검증 → **SHIP**. MCP kind 잔여 P0/P1 없음.

총 6라운드: P0 3건 + P1 8건 + P2 2건 전부 완화 없이 해소([[feedback_cross_model_p0_no_downgrade]]). 회귀 가드 = test_gen_mcp.py 40건 + test_mcp_shadow_pilot.py 2건 + cases.tsv 7행.

---

## v2 백로그 (P2/P3 — 이번 범위 밖, 문서화)
- `absorb --kind mcp`: 손편집 config → spec 역흡수(§1.7, v1 정방향만).
- generate 쓰기 cross-file 원자성: temp+rename per-file atomic + manifest 후스탬프까지 했으나, 두 os.replace 사이 크래시 시 혼합상태(복구가능 STALE — 침묵 false-PASS 아님, codex R4 수용). 완전 원자성은 후속.
- MCP gateway 거버넌스 / 시크릿 저장소(vault·keychain) 연동: env 변수명 참조 규약까지만(D2).
- claude 전역 `~/.claude.json` MCP 지원: v1 은 프로젝트 `.mcp.json` 만(파일럿 한계 §0.4).
