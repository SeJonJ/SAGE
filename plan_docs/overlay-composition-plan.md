# 오버레이 물리 합성(materialization) + FAIL 게이트 + framework 오버레이 kind

> 통합 대상: GitHub 이슈 #5(오버레이가 실제로 반영됐는지 강제 검증하는 장치 부재) ∪ §9-F/SD-3(framework-doc 오버레이 — AGENT_GUIDE override). 두 항목은 **같은 메커니즘의 두 면**이라 하나로 개발한다.
>
> 코드 기준: `sage_project` HEAD `79ab152` (v0.9.60). 아래 file:line 은 이 시점 실측.
>
> 리뷰: codex R1(P0×3)→R2(P0×3)→R3(P0×3·P1×4)→R4(P0-3)→R5(P0-3 §6/§10)→R6(P0-3 알고리즘)→R7(P0-3 (c)블록 제거·§6 Phase 문구) 전량 수용. §12 로그. **본 v8 은 R7 반영본**(코어 설계는 R7 에서 정합 확인, 잔여는 제거 시맨틱·문구).

## Implementation Status (2026-07-16)

- **Phase 1 COMPLETE**: classification resolver, physical materialization, base receipts,
  install/sync/SessionStart/validate/doctor wiring, blocked-asset guard, AGENT_GUIDE
  write guard, and preflight-first writes are implemented.
- **Phase 2 COMPLETE**: framework overlays are materialized for AGENT_GUIDE and host
  wrappers, backed by `risk.domains`, critical-domain pointers, and domain-contract lint.
- **SD-1~SD-8 COMPLETE in source**: fail-closed registered gates, content-L3 block
  provenance, strict validation identities, multi-host receipts, critical-domain
  diagnosis, and cycle/domain/two-round review binding are implemented.
- Build identity records source commit, source/installed content hashes, and dirty state.
  Project-local verification scripts explicitly declared by the profile survive force install.
- Independent review hardening is complete in code: build identity now covers the full
  Python engine, framework overrides bypass the CORE write guard, sync updates every
  installed host without laundering version/source drift, second-host installs merge
  receipts without `--force`, and SessionStart prefers the packaged `sage-hook` runtime.
- Verification (latest before Phase 05):
  - `/tmp/sage-adoption-test-venv/bin/python -m pytest -q` -> `1027 passed, 1 skipped, 57 subtests passed`
  - source hook regeneration followed by `validate --check --kind all --schema --strict` -> `PASS`
  - `bash scripts/sage_harness/hooks/tests/run-tests.sh` -> `PASS=61 FAIL=0`
  - ChatForYou registered-hook acceptance -> `16 passed, 0 failed`

The development worktree remains intentionally dirty until the user chooses commit/push.
`dirty_flag=true` is therefore surfaced as an advisory build-identity warning, not hidden.

---

## 1. 왜 하나인가

- **이슈 #5**: 기존 오버레이(agents/skills)는 `--force` 에도 보존되지만(install 이 ship 안 함), **실제 반영은 전적으로 LLM 판단**이다. CORE 렌더에 "Optional project overlay … Apply it before the CORE instructions" 프로즈만 있고(`templates/core/framework/.claude/agents/leader.md:13-14`), 오버레이가 물리적으로 합쳐지지도 `validate` 가 반영을 검증하지도 않는다.
- **SD-3/§9-F**: 여기에 framework/AGENT_GUIDE override kind 를 추가하려 한다. "CORE 에 override-read 문장 추가"로 하면 이슈 #5 결함을 **가장 고위험 문서(L3 안전 도메인 포인터 SSOT)** 에 재생산한다.

→ 단일 메커니즘: **물리 합성(materialization) + FAIL-capable 검증 게이트**, kind 파라미터화. 이슈 #5 = *메커니즘*, SD-3 = *범위 확장*.

**용어**: "reflection"(byte 일치)은 LLM 이 지시를 따랐다는 증거가 아니다. 강제 대상은 **materialization** — 오버레이가 렌더에 물리적으로 존재함. "적용"은 그 다음이며 materialization 은 필요조건일 뿐. materialize 게이트는 "오버레이가 안전한가"가 아니라 "물리적으로 반영됐는가"만 본다. 안전성은 별개 층(overlay content-lint + hook/CI 권위)이 담당한다(§3·§8).

---

## 2. 현재 코드 실측 (R1·R2 검증 반영)

| 요소 | 위치 | 현 동작 · 정정 |
|---|---|---|
| 오버레이 루트/스캔 | `overlay_lint.py:41`·`55-79` | agents/skills 만(64). **임의 `*.md` 수용**(CORE id 미검증)→오타 조용히 무시(R1 #5). 읽기실패 silent skip(71-75, R1 #12) |
| validate exit | `validate.py:23-25` `_EXIT={"WARN":0}` | **WARN=exit0**. **FAIL=exit1 은 네이티브**(R2: CLI 강제에 SD-5 불필요) |
| 반영 프로즈 | 렌더/SKILL.md | 조건 없음 → 합성 후 이중적용 위험(R1 #8) |
| AGENT_GUIDE 안전경계 | `AGENT_GUIDE.md:123-133` | non-negotiable. 블록이 "우선"이면 덮음(R1 #2) |
| managed-block 선례 | `mcp_common.py:208-232` | 마커 구간 교체·중복/짝불일치 error·idempotent. body 는 serializer 소유(overlay 는 user 소유→마커 취약 R1 #11). `generate.py:457-498` temp-stage+`os.replace` = **per-file 원자성만**(순차 replace 는 cross-file 트랜잭션 아님 R2 P1) |
| **_resources 버전** | `_resources.py:18-33` | env→wheel→repo = **현재 실행 패키지**. 프로젝트를 설치한 버전 아님 → **버전 skew**(R2 P0-1) |
| **hook 코어 로컬 우선** | `hook_entry.py:36-45` | 프로젝트-로컬 설치본 우선 → CLI 업그레이드해도 옛 로컬 코어 실행. skew 확대(R2 P0-1) |
| manifest 설치버전 | `install.py:479-484` `sage_version=__version__` | 설치 버전 기록됨 — **skew 판정·base 앵커의 근거로 사용 가능**(현재 미사용) |
| install framework/agent | `install.py:522-529`·`139-149`(claude frontmatter)·`558-564`(codex `_copy_tree`) | `--force` 시만 덮음. **agent 배치 host별 상이**(R1 #9) |
| install skill | claude repo(589-592) / **codex 전역 `$CODEX_HOME`(593-596)** | codex 전역 합성 시 프로젝트 간 누출(R1 #7) |
| core_skill_ids | `install.py:171-173` `[BOOTSTRAP,*CORE]` | sage-init 포함(열거 누락 금지 R1 #5, 전역이라 D3 제외 R1 #7) |
| doctor drift | `install.py:355-372`(byte 대조)·`doctor.py:186-211` | 합성 블록 stale 오판(R1 #6) |
| profile 소스 분기 | install/doctor=YAML(`install.py:120`) / hook=JSON(`hook_runtime.py:41`, generate 컴파일 `generate.py:156`) | 같은 profile 이 caller 별 다른 base bytes 가능(R2 P1) |
| codex 발견 | `.codex/agents` 라우팅 프로즈(558-564), `AGENTS.md`(3-10) auto-read, 충돌 시 `--force` 아니면 skip(553-557) | 존재만으론 로드/라우팅 보장 아님(R1 #4·R2 P1) |
| write-guard | `guard.sh:48-60` | `.claude/.codex/{agents,hooks,skills}`+`.mcp.json` 만. AGENT_GUIDE 미가드(R1 #3) |
| wrapper 모순 | `CLAUDE.md:16-19`·`CODEX.md:20-23` | CORE 렌더 "write-guard exempt — edit directly" **거짓**(R1 #13) |
| overlay-read 프로즈 산재 | `AGENT_GUIDE.md:38`·각 SKILL.md·`sage-asset-override/SKILL.md:104`·`retro.py:107`·`absorb.py:335` | 문서 인벤토리 광범위(R2 P2) |

---

## 3. 강제 모델 (R1 #1·R2 P0-3 — 모순 제거)

install-time 합성만으론 "applied each session" 미달(편집→sync 없이 새 세션→stale). 두 층, 역할을 **모순 없이** 확정. **핵심(R3 P0-2)**: L1(SessionStart)은 프로젝트-로컬 런타임을 실행(`hook_entry.py:36`, adapter 가 `$CORE_DIR/runtime/run_hook.py`)하므로 **실행 SAGE 버전을 관측할 수 없다**(로컬 코어가 stale 일 수 있음) → **L1 은 skew 탐지·업그레이드 판정을 하지 않는다.**

- **L1 로컬 self-heal (advisory, 순수 블록 재합성)**: SessionStart 에서 **마커 구간만** expected_block 으로 수렴시킨다. **§4 `classify` 경유(R6·R7)**: (a)/(b)=오버레이 블록 삽입/갱신, **(c)/미분류=expected_block=""→기존 조작 블록 제거(스트립)**(신규 삽입 안 함 + 남은 블록 제거, R7). 동작: 설치본의 base 영역 해시 == manifest 영수증(§4)이면 마커 구간을 expected_block 으로 갱신((c)는 빈 값=제거), **불일치면 no-op**(base 를 절대 재작성하지 않음 → mixed-version base 생성 불가). retro-gate·profile-JSON 무관 독립 스텝으로 스냅샷 early-return(`hook_runtime.py:608` 이하) **이전에** 실행(R2 P0-3), fail-open. **profile 불필요**(base 를 만들지 않고 블록만 얹음 → YAML/JSON 분기·frontmatter 재현 회피). **수렴적**(expected 블록은 오버레이 파일의 순수 함수 → 동시 세션 동일 bytes, race 무해). L1 은 편의(staleness 창 축소)일 뿐 권위 아님. **버전 skew·업그레이드 필요는 L1 이 아니라 현재-패키지 entrypoint(validate/doctor/install)가 판정**(§4). pre-v3 설치 업그레이드 경로 = `sage install --force`(자동 SessionStart 탐지 불주장, R3 P0-2).
- **L2 게이트 (권위, FAIL)**: `validate` 가 `render == expected_render(...)`(§4) 대조 → 불일치 **FAIL(exit1 네이티브)**. **CLI/CI 강제에 SD-5 불필요** — `_EXIT{FAIL:1}` 이 이미 막는다(R2). **SD-5 역할은 오직** 이 check-id 를 CI strict allowlist 로 승격해 정당한 advisory 와 구분하는 것. **adversarial 권위(R3 P0-1)**: manifest 영수증은 로컬이라 위조 가능(base 편집자가 manifest 도 편집·write-guard 미보호) → **로컬 영수증은 accidental drift 탐지용(advisory)**, 진짜 tamper-proof 권위는 **L2 를 CI 보호 컨텍스트에서 실행해 프로젝트 manifest 를 신뢰하지 않고 CI-pinned canonical 패키지로 expected 를 재계산**하는 것(SD-9 서버측 게이트 영역). **required downstream check 는 각 프로젝트 branch-protection 설정**(§10, SAGE 가 타repo 강제 불가 — 정직 범위).

L1 이 창을 축소하고 L2(+CI 재계산)가 권위. §9·§11 "FAIL now vs SD-5" 모순 제거: **FAIL 은 지금부터 네이티브, SD-5 는 allowlist 관리일 뿐.**

---

## 4. `expected_render()` + base drift 영수증 (R1 #3·#6·R2 P0-1·R3 P0-1)

**base 를 현재 실행 패키지에서 뜨지 않는다**(`_resources` 는 업그레이드 시 새 버전 → skew, R2 P0-1). install 시점 canonical base 해시를 manifest 에 기록하되, **이것은 tamper-proof 앵커가 아니라 accidental-drift 영수증(advisory)**이다(R3 P0-1: 로컬이라 위조 가능). tamper-proof 권위는 **L2 를 CI-pinned canonical 로 재계산**(§3).

```
# install 시 engine-owned 최상위 맵(assets 아님 — assetEntry 는 form/conformance 필수+additionalProperties:false 라 부적합, R3 P1):
manifest.core_renders["<host>/<kind>/<id>"] = {
    "base_sha256": <compose 에 쓴 최종 base(claude agent 는 frontmatter 주입 후)의 해시>,
    "sage_version": <install 당시 __version__>,   # 이 엔트리 전용(최상위 sage_version 과 구분, R3 P0-1)
}

# 단일 분류 resolver — L1·install·sync·validate 전부 이걸 통해서만 오버레이를 다룬다(R6):
classify(kind,id) -> "compose" | "blocked"   # (a)/(b)=compose, (c)/미분류=blocked(fail-closed 기본)

expected_block(kind,id,root):
    if classify(kind,id) == "blocked": return ""          # (c)/미분류 = 블록 없음(R6, 분류-aware)
    return compose_block( overlay_text(root,kind,id) or "" )   # (a)/(b) 만 합성. base 무관, 블록만

expected_render(kind,id,root):
    base' = 설치본에서 마커구간 제거
    (a) sha256(base') == core_renders[...].base_sha256   → base 무결성(R1 #3)
    (b) 설치본 마커구간 == expected_block(kind,id,root)   → 오버레이 반영((c)=마커 0 이어야 통과)
    (c) classify=="blocked" 인데 오버레이 파일 존재 → FAIL("SD-8 전까지 미지원", R4)
```

- **engine-owned 수명(R3 P0-1)**: `core_renders` 는 CORE hook 처럼 엔진 자산 → **`_manifest()` 의 인스턴스 자산 보존(`install.py:468-472`)에서 제외**하고 **매 `install --force` 마다 최종 base 로 전량 재계산**(CORE hook reset 패턴 `install.py:473-477`). per-entry `sage_version` 을 비교(최상위 stamp 와 preserved 옛 엔트리 공존 방지). 엔트리 부재/손상 → **FAIL**(명시적 force-migration 예외).
- **버전 skew(R2 P0-1·R3 P0-2)**: **현재-패키지 entrypoint 인 validate/doctor/install** 이 판정 — `core_renders[...].sage_version != 실행 __version__` 이면 STALE/업그레이드 안내. **L1 은 skew 판정 안 함**(로컬 코어가 stale 일 수 있음, R3 P0-2) — 영수증-base 일치 시 블록만, 불일치 시 no-op.
- **base 변조(R1 #3)**: (a) 불일치 FAIL. **AGENT_GUIDE.md 렌더도 Phase 1 에서 core_renders 앵커 대상**(expected_block="", framework 오버레이 kind 는 아직 없음) → codex 가 AGENTS.md 로 auto-load 하는 AGENT_GUIDE 에 overlay-read 지시를 재주입하는 변조가 materialize 게이트에 잡힌다(R6 P0-3 봉쇄, 단 로컬은 advisory·권위는 CI 재계산).
- **doctor freshness(R1 #6·R3 P1)**: `core_render_status` 는 **버전 일치 시 profile override 를 재계산해 freshness 도 검사**(`doctor.py:203-210` 거동 유지) + **영수증은 base 무결성에 별도 사용**. 영수증-only 로 대체하지 않는다(profile 변경 미탐 방지). 합성 블록은 expected_block 대조라 stale 오판 없음.
- **마커 삭제(R1 #11)**: 마커 0쌍→base'=설치본 전체→해시 불일치 FAIL. L1 은 영수증 일치 설치본에만 재삽입.
- **profile 분기(R2 P1)**: 영수증 base 해시는 install 의 **YAML 렌더 결과** → 이후 caller 는 base 를 재계산 않고(§ freshness 는 예외) 해시 대조 → JSON 분기 무관.
- **schema/routing(R3 P1)**: `manifest.schema.json` 에 `core_renders` 별도 정의 추가, validate 인식 prefix(`validate.py:516-524`)와 별개 검사 경로 배선.
- **AGENT_GUIDE 하드닝 = Phase 1 P0-3 선행(R6)**: (1) AGENT_GUIDE:39-40 의 블랭킷 "each CORE render reads its overlay first" 지시 **제거**(그게 (c)까지 흘리는 근원) → §6 분류별 per-render 지시로 대체, (2) AGENT_GUIDE.md 를 core_renders 앵커·write-guard(`is_guarded`)에 편입. **이것은 framework 오버레이 kind(SD-3/SD-4, Phase 2)와 별개** — 위험한 블랭킷 지시 제거+무결성 앵커는 Phase 1 안전 선행이다(오버레이를 framework 에 *받는* 능력이 아니라, framework 문서가 (c) 조작을 흘리지 않게 막는 것).

---

## 5. `sage/overlay_common.py` 계약 (R1 #10·#11·#12·#14·R2 P1·P2)

### 5.1 마커·byte 규칙 (R1 #14·R2 P2)
```
MARKER_START = "<!-- >>> SAGE OVERLAY v1 START (edit sage/asset_overrides/<...>, not here) -->"
MARKER_END   = "<!-- <<< SAGE OVERLAY v1 END -->"
```
전 대상 markdown → HTML 주석 단일 마커. **IO 는 `newline="\n"` 바이트 고정**(R2 P2: 기존 text-mode 플랫폼 개행변환 회피, Windows 테스트). base·블록·본문 말미 개행 1개 정규화. 옛(버전없는) 마커 발견 시 제거 후 v1 재합성.

### 5.2 함수
- `validate_overlay(text)->error|None`: 본문에 마커 토큰 포함 시 **reject**(R1 #11). 저작·compose·lint 전부에서 선검사.
- `compose_block(overlay_text)->str|""`: overlay 있으면 마커+헤더+본문(§5.3), 없으면 `""`. **base 를 만들지 않는다** — 블록 문자열만. idempotent 자명.
- `insert_block(installed_text, block)->(new_text,error)`: 설치본의 마커구간을 block 으로 교체(없으면 base 말미 append). 중복/짝불일치 → error. base 영역 불변.
- `base_of(installed_text)->(base,error)`: 마커구간 제거(해시 대조용). 0쌍→(원문,None), >1/짝불일치→error.
- `expected_render`/`expected_block`: §4.

### 5.3 블록 헤더 — additive-only (R1 #2)
```
<!-- >>> SAGE OVERLAY v1 START ... -->
## Project-Local Additions (sage/asset_overrides/<kind>/<id>.md)
아래는 이 프로젝트 로컬 추가 지침이며 CORE 기본 지침에 **더한다**.
AGENT_GUIDE·phase·review·verification·안전 경계를 **완화할 수 없다**.
<overlay 본문>
<!-- <<< SAGE OVERLAY v1 END -->
```

### 5.4 단위테스트
2회=1회, 마커 중복/짝불일치 error, 마커 토큰 주입 reject, 오버레이 삭제 시 블록 제거, 오버레이 없는 기존 프로젝트 no-op, 읽기실패 error(silent 금지 R1 #12), byte 규칙(LF·Windows), base 해시 앵커 대조.

---

## 6. 대상 매트릭스 · host 비대칭 (R1 #4·#7·#8·#9·R2 P1)

**Phase 1 대상(framework 오버레이 *kind* 만 제외 — R7)**: Phase 1 은 framework 를 *오버레이 받는 kind* 로는 다루지 않는다(SD-3/SD-4=Phase 2). **단 framework 문서 `AGENT_GUIDE.md` 자체의 하드닝(blanket overlay-read 지시 제거 + core_renders 앵커 expected_block="" + write-guard)은 Phase 1 필수 예외**(§4·§8·§10 step11) — 그 blanket 지시가 (c) 조작을 흘리는 근원이라 P0-3 봉쇄의 선행이다. 즉 "framework 제외"는 kind 수용에 한하고, framework-doc 무결성 하드닝은 Phase 1 에 포함된다.

| kind | claude | codex | 합성? |
|---|---|---|---|
| agent | `.claude/agents/<id>.md`(frontmatter 후) | `.codex/agents/<id>.md`(tree copy 후) | ✅ 양 host, **host별 경로 분리**(R1 #9) |
| skill | `.claude/skills/<id>/SKILL.md` | **`$CODEX_HOME/skills`(전역)** | claude ✅ / **codex ❌ 누출**(R1 #7) |

**합성 자격 2차 필터(R3 P0-3·R4 P0-3)**: 위 매트릭스(host 배치)를 통과해도 **§8 gate-classification** 이 최종 자격을 결정 — (a)비게이트/(b)오라클-보증만 합성. **(c)게이트-미보증·미분류는 오버레이 경로 전면 차단(합성 X·프로즈-read X·오버레이 파일 존재 시 validate FAIL, §8)** — 프로즈-read 폴백을 주지 않는다. 즉 물리 합성 대상 = {host 배치 가능} ∩ {(a)|(b)}, 오버레이 허용 대상 = {(a)|(b)}.

**D3 제외 경계(R1 #7·R4 P0-3)**: codex 전역 skill = `_CORE_SKILLS` + **sage-init**(둘 다 전역) 전부 물리 합성 제외. `--no-global-skill` 시 타깃 부재. project skill(prefix 경로 `generate.py:728`)은 CORE 아님 → 범위 밖. **codex 전역 skill 의 프로즈-read 폴백은 (a)/(b) 에만 적용**. (c) 전역 skill(예: `sage-cycle`·`sage-plan`·`sage-team`·`sage-review`)은 합성도 프로즈-read 도 없음 → 오버레이 파일 존재 시 FAIL(§8, R4 조작경로 봉쇄). (a)/(b) 전역 skill 은 이슈 #5 미해결 정직 표기(완전해결=repo-scoped 전환, SD-6 인접, 범위 밖).

**분류-게이트 per-render 오버레이 지시(R1 #8·R4 P0-3)**: **블랭킷 AGENT_GUIDE:38 "모든 CORE 렌더가 오버레이 먼저 읽어라" 지시를 제거**하고(그게 (c)까지 오버레이를 흘리는 근원, R5), 각 렌더가 **분류별 per-render 지시**를 담는다:
- **(a)/(b) claude(합성)**: "아래 SAGE OVERLAY 블록을 적용" — 외부 파일 재read 안 함.
- **(a)/(b) codex-전역(미합성)**: "외부 오버레이 파일을 읽어 적용"(프로즈-read 폴백, (a)/(b)라 안전).
- **(c)/미분류**: 오버레이 지시 **없음**(오버레이 언급 자체 부재) → LLM 이 (c) 오버레이를 읽으라는 지시를 어디서도 받지 않음. **validate FAIL 은 방어심화**(present (c) 오버레이 파일을 CI 에서 잡음)이며, 세션-시간 1차 차단은 "지시 부재" 자체다.

**codex 발견 검증 강화**(R1 #4·R2 P1): `.codex/agents`·라우터는 존재만으론 로드 보장 아님. L2 는 **AGENTS.md 가 canonical 라우터 내용과 일치**(단순 존재 아님)를 대조 — 기존 충돌 보존본(`install.py:553`)이 라우팅을 무력화하는 경우 FAIL. 과대주장 금지: "합성됨 ≠ 로드됨".

---

## 7. install / sync-overlays 배선 (R1 #10·R2 P1)

**단일 resolver 경유(R6)**: install·sync·L1·validate 는 모두 §4 `classify(kind,id)` 를 거쳐 `expected_block` 만 쓴다 — **분류를 우회해 오버레이를 합성하는 경로가 없다**. `classify=="blocked"`((c)/미분류)이면 expected_block="" 이라 어떤 합성 경로도 (c) 오버레이를 삽입하지 못하고, 오버레이 파일이 있으면 preflight 에서 FAIL.

**expected_block="" 는 "블록 없음으로 수렴"이다(R7)**: (c)/미분류 대상의 목표 상태는 **마커 구간 0** — 신규 삽입 안 함 + **기존 조작 블록이 있으면 제거**한다(앵커 FAIL 은 탐지일 뿐, install·sync·L1 이 모두 `insert_block(installed, expected_block="")`=블록 스트립으로 실제 제거). 즉 (c) 는 install/L1/sync 어디서든 렌더가 no-block 으로 수렴한다. base 영역은 불변, `_write`/`--force` skip 의미 그대로.

**(a)/(b) 합성**: 오버레이가 있으면 마커 구간에 expected_block 삽입/갱신, 없으면 블록 제거. 오버레이 없는 일반 install 은 완전 no-op(사용자 편집 파괴 없음).

**preflight-first**: 쓰기 전 **모든** 대상의 (classify·읽기가능·마커토큰 부재·manifest base 해시 확보) 선검증. 하나라도 실패 → **아무것도 안 쓰고 abort**. **(c)/미분류에 오버레이 파일이 있으면 `validate` 가 FAIL**(저자에게 파일 삭제 요구) — 단 이는 게이트 신호이며, install/sync/L1 의 (c) **블록 제거(스트립)는 파일 존재와 무관하게 수행**(조작 블록이 남지 않도록). 통과 후 대상별 temp-stage → `os.replace`.

**원자성·크래시 복구 정직화(R2 P1·R3 P1)**: 순차 `os.replace` 는 **per-file 원자성만** 보장(cross-file 트랜잭션 아님). install 은 렌더를 manifest 보다 먼저 쓴다(`install.py:522-596` → `606-610`) → 쓰기 중 크래시는 **새 base + 옛 anchor** 를 남길 수 있다. 이 경우 L1 은 anchor 불일치 base 를 **거부(no-op)하며 스스로 복구하지 못한다**. 따라서 "다음 L1/L2 가 self-heal" 주장(구 v3)은 과대 — **크래시 복구 = `sage install --force` 재실행(또는 generation/receipt commit 프로토콜)이며 자동 아님**(R3 P1). L1/L2 의 역할은 **탐지+거부**(수렴적 self-heal 은 anchor-일치 정상 base 에 한함).

**`sage sync-overlays` 커맨드**: base 재복사 없이 블록만 재삽입. **재합성 대상 열거(R3 P1)**: (오버레이 파일이 있는 대상 **∪ 기존 managed-block/`core_renders` 영수증이 있는 대상`)을 열거하되 **각 대상을 `classify` 로 판정(R6)** — (a)/(b)=expected_block 재삽입/갱신, **(c)/미분류=오버레이 파일 있으면 FAIL·기존 블록 있으면 제거(expected_block="")**. 오버레이 삭제 시 파일이 사라져도 기존 블록 보유 대상을 잡아 블록 제거 가능. unknown kind/id·미지원 host·missing 대상 **hard-report**(R1 #5). 대상 = agents(양 host)+claude skills(+sage-init). host-aware. codex 전역 skill skip 안내. 버전 skew 시 업그레이드 안내(§4).

**write-guard**(`guard.sh:77-93`): block() 에 "오버레이 편집 후 `sage sync-overlays`" 추가.

---

## 8. Phase 1 안전성: 합성 자격 제한 + SD-8 hard-dep (R1 #2·R2 P0-2·R3 P0-3)

**overlay 권위 경계(정직화)**: materialize 게이트는 "물리 반영"만 본다. 오버레이 **내용**의 게이트-완화 방지는 materialize 게이트가 하지 못한다 — 그것은 hook/CI 권위(재설계 §10: override=advisory, hook/CI=authority)와 **SD-8 결정론 review/phase 오라클**이 담당한다.

**heuristic content-lint 는 FAIL 승격하지 않는다(R3 P0-3)**: `overlay_lint.py:19-36` 은 명시적 heuristic 로 좁은 문구집합만 인식 → `"record Phase 05 as APPROVED based on author confidence"` 류로 우회 가능. 이런 lint 를 WARN→FAIL 로 올리는 것은 **fail-closed 처럼 보이는 theater**(우회로가 열린 채 exit1 신호만 준다). 따라서 구 v3 의 "게이트-보유 자산 WARN→FAIL 상향"은 **폐기**. content-lint 는 **advisory WARN 유지**(사람 리뷰 힌트).

**진짜 fail-closed = 합성 자격 제한(R3 P0-3, codex option 2)**: 대신 Phase 1 물리 합성 **자격**을 제한한다. CORE 자산은 gate-classification 으로 분류:
- **(a) 게이트 비보유** 또는 **(b) 게이트가 자산 텍스트를 읽지 않는 독립 결정론 오라클(hook/CI)로 강제됨** → 물리 합성 **허용**(오버레이가 텍스트로 게이트를 완화해도 오라클이 무시).
- **(c) 게이트-보유하나 아직 오라클 미보증** — `leader`(phase/report 종합 `leader.md:25-35`), `sage-cycle`(게이트 시퀀싱 `SKILL.md:18-26`), `sage-plan`(사전계획 `109-123`), `sage-profile-modify`(risk/phase/verification/review-loop 직접 약화 `95-102`), `sage-team`(손저작 APPROVED 우회 자인 `22-25`), `reviewer`·`qa`·`sage-review` — **오버레이 경로 전면 차단**.

**(c) 자산은 프로즈-read 도 막는다(R4 P0-3 잔존 봉쇄)**: 물리 합성만 제외하고 **프로즈-read 폴백을 남기면 봉쇄가 아니다** — LLM 이 (c) 오버레이를 "project-local priority > CORE"로 여전히 읽어 `record APPROVED` 조작이 그대로 통과한다(codex R4). 따라서 (c) 자산은 (1) **물리 합성 안 함** + (2) **CORE 렌더에서 overlay-read 프로즈 자체를 제거**(조건부 아님 — 오버레이 언급 없음, §6) + (3) **validate 가 (c) 오버레이 파일 존재 시 FAIL**("이 자산은 SD-8 전까지 오버레이 미지원" 명시 거부, silent ignore 아님). 이로써 오버레이 메커니즘을 통한 (c) 게이트 조작 경로가 **닫힌다**(오버레이는 읽히지도 통과하지도 않음). **(c) CORE 렌더 자체 변조 방어(R5)**: base_sha256 앵커는 **(c) 포함 모든 CORE 렌더**에 기록한다(§10 step2) — (c) 는 합성 대상이 아니지만 expected_block=""(블록 없음)로 base 무결성만 검사해, (c) 렌더에 오버레이-읽기 지시를 심는 변조를 materialize 게이트가 잡는다. (c) 오버레이 지원은 SD-8(결정론 오라클) 완성 후에만 (c)→(b) 재분류로 개방.

**분류 기본값 = fail-closed**: gate-classification 매니페스트에서 **미분류/불확실 자산은 (c) 로 간주해 오버레이 전면 차단**(입증된 (a)/(b)만 합성). 이로써 "물리 반영이든 프로즈-read든 승인-조작 오버레이가 게이트를 통과하는" R2 P0-2/R4 P0-3 경로를 **자격 단계에서 원천 차단**(evadable lint 에 의존하지 않음).

**framework kind = Phase 2, hard-dep 2**(R1 #2):
1. **framework content-relaxation = FAIL**(WARN 아님) + §5.3 additive-only.
2. **SD-4 선행 설계**: framework 오버레이는 `domain_refs` machine-readable frontmatter 계약(schema·parser·허용 레지스트리·중복/미지 처리·해소 의미·결정론 테스트) 위에서만 안전. **SD-4 는 별도 설계문서로 확정 후** framework 착수(R2 P1: "named, not designed"). 임의 prose framework 오버레이 배포 금지.

**framework L1 freshness 한계(R2 P1)**: codex 는 `AGENTS.md` auto-read 로 AGENT_GUIDE 를 **SessionStart 수리 이전에** 로드 → framework materialization freshness 는 L1 이 아니라 **install/sync 시점**에 의존(첫 세션 freshness 주장 불가, 정직 표기).

---

## 9. 경계 / 비목표

- **SD-4**: framework kind 의 **선행 의존 설계문서**(§8) — seam 아님.
- **SD-5**: L2 FAIL 을 CI strict allowlist 로 관리하는 배선(`overlay-materialize-drift` 등재). **FAIL 자체는 SD-5 없이 네이티브**(§3).
- codex 전역 skill 물리 합성·codex 라우터 실제 로드·타repo required-check 강제 = 비목표(정직 범위).

---

## 10. 구현 순서 + 회귀가드

```
Phase 1 — 이슈 #5 코어(agents + claude skills), 안전 배포:
 1. overlay_common.py — 마커 v1·LF byte IO·validate_overlay(토큰 reject)·compose_block·insert_block·base_of·expected_render + 단위테스트(§5.4).
 2. manifest base 앵커 — install 이 **(c) 포함 모든 CORE 렌더**의 base_sha256+sage_version 기록(§4, R5: (c) 렌더 변조 방어). (a)/(b)=expected_block(오버레이), (c)=expected_block="". expected_render/core_render_status 를 앵커 대조로 전환(R1 #6, R2 P0-1/P0-3/P1).
 3. install.py — 오버레이 보유 대상만·마커구간만 삽입(--force 보존 R2 P1), preflight-first, host별 agent 경로(R1 #9), codex 전역 skill 제외(R1 #7).
    회귀가드: 오버레이 없는 install --force = 블록 0·base 불변; 합성 렌더가 doctor stale 아님; 버전 skew 시 재기록 안 함(R2 P0-1).
 4. gate-classification 매니페스트 + **단일 `classify` resolver(R6)** — CORE 자산을 (a)비게이트/(b)오라클-보증/(c)게이트-미보증 분류, **미분류=(c)fail-closed 기본값**(R3 P0-3). `classify(kind,id)` 를 install·sync·L1·validate 가 **모두 경유**(우회 합성 경로 없음). 합성 자격 = (a)|(b) 만.
 5. overlay_lint.py — CORE id 검증(오타 hard-report R1 #5)+읽기실패 FAIL(R1 #12). content-lint 는 **advisory WARN 유지**(heuristic 이라 FAIL 승격은 theater R3 P0-3). 조건부 프로즈로 CORE 렌더 문구 교체(R1 #8); **(c) 자산은 overlay-read 프로즈 제거 + (c) 오버레이 파일 존재 시 FAIL**("SD-8 전까지 미지원" R4 P0-3).
 6. sage sync-overlays — 재합성 대상 = 오버레이 파일 ∪ 기존 블록/영수증 보유 대상(삭제 처리 R3 P1)·hard-report·host-aware·sage-init 포함·codex 전역 skip·skew 안내.
 7. validate.py — L2 materialize 게이트 FAIL(check-id overlay-materialize-drift), AGENTS.md 라우터 내용 대조(R1 #4/R2 P1). FAIL 네이티브(§3). schema/routing: `core_renders` 별도 정의+검사 경로(R3 P1).
 8. doctor.py — 버전 일치 시 profile override 재계산 freshness 유지(R3 P1) + 영수증은 base 무결성 별도. 미분류/missing anchor FAIL.
 9. session-start L1 — 블록만 재합성, retro-gate 무관 독립 스텝·early-return 이전 실행(R2 P0-3), profile-free·수렴적(R2 P1), fail-open. **skew 판정 안 함**(R3 P0-2).
 10. 업그레이드 마이그레이션(R3 P0-2) — pre-v3 설치 업그레이드 = 명시적 `sage install --force`(자동 SessionStart 탐지 불주장). skew/missing-anchor 는 현재-패키지 entrypoint(validate/doctor)가 표면화. install/sync + CI 로 강제(문서만 아님).
 11. **AGENT_GUIDE 하드닝(Phase 1 P0-3 선행, R6)** — 블랭킷 `AGENT_GUIDE:39-40` "each CORE render reads its overlay first" **제거**((c) 로 흘리는 근원, codex auto-load 경로) → 분류별 per-render 지시로 대체(§6). AGENT_GUIDE.md 를 **core_renders 앵커(expected_block="")+write-guard(`is_guarded`) 편입**(overlay-read 재주입 변조 탐지). framework 오버레이 *kind* 수용(SD-3/SD-4)과는 별개.
 12. 문서 인벤토리 전수(R2 P2) — 각 SKILL.md·agent 렌더·sage-asset-override:104·retro.py:107·absorb.py:335·CLAUDE.md:16·CODEX.md:20 정합화((c) 자산에 오버레이 언급 0 검증).

Phase 2 — framework kind (선행: SD-4 설계문서 + framework=FAIL, AGENT_GUIDE 하드닝은 Phase 1 완료):
  13. framework 오버레이 kind 수용 — framework 경로·lint subdir+FAIL+CORE id 검증·framework 오버레이용 AGENT_GUIDE per-render 지시·/sage-asset-override kind 확장. (AGENT_GUIDE 앵커/write-guard 는 Phase 1 step11 에서 이미 편입.) codex 사전-SessionStart freshness 한계는 install/sync+CI 로 강제(§8).
```

**핵심 e2e**: (a) 오버레이 편집→새 세션(L1)→렌더 fresh; sync 미실행 CI→L2 FAIL(exit1)→sync→PASS. (b) 오버레이 삭제→enum 이 기존 블록 대상 포착→sync→블록 제거(R3 P1). (c) base 변조→로컬 L2 advisory FAIL + CI 재계산 FAIL(앵커, R1 #3). (d) 마커 삭제→해시 불일치 FAIL, sync 정상 복구(R1 #11). (e) CLI 업그레이드(skew)→L1 재기록 안 함·validate/doctor 업그레이드 안내(R2 P0-1·R3 P0-2). (f) **위조 anchor**(base+manifest 동시 편집)→로컬 통과·**CI-pinned 재계산 FAIL**(R3 P0-1). (g) 크래시(새 base+옛 anchor)→L1 거부·`install --force` 재실행으로 복구(R3 P1, 자동 self-heal 아님). (h) profile YAML 변경→doctor freshness 재계산 탐지(R3 P1). (i) (c)게이트-미보증 자산에 오버레이 파일→**validate FAIL**("SD-8 전까지 미지원")·CORE 렌더에 overlay-read 프로즈 부재·물리 합성/프로즈-read 모두 없음(R4 P0-3). (j) **(a)/(b)** codex 전역 skill 프로즈-read 유지·합성 안 됨; **(c)** codex 전역 skill 은 프로즈-read 도 없음·오버레이 파일 시 FAIL(R4/R5). (k) 오타 `reviwer.md`→hard-report(R1 #5). (l) 마커토큰 오버레이→preflight abort(R1 #10). (m) AGENT_GUIDE 에 overlay-read 지시 재주입(codex auto-load 경로)→core_renders 앵커 불일치 FAIL(R6). (n) (c) 자산에 이미 물리화된 조작 블록→install·sync·L1 **어느 경로든 expected_block=""로 제거**(탐지 아닌 제거, R7)·신규 합성 차단·오버레이 파일 존재 시 validate FAIL(R6 단일 resolver).

---

## 11. 열린 질문

- **L1 self-heal 의 SessionStart 삽입 지점**: retro-gate 무관 독립 스텝으로 early-return 이전(`hook_runtime.py:615-625`) 실행하도록 구조 조정(또는 별도 훅). 세션당 1회·fail-open 규율 구현 시 확정.
- **gate-classification (a)/(b)/(c) 확정(R3 P0-3)**: 각 CORE agent/skill 의 게이트 보유 여부 + 그 게이트가 독립 결정론 오라클로 강제되는지 판정 — **SD-8(review/phase 오라클) 설계에 의존**. 그 전까지 보수 기본값=(c)제외. leader/sage-cycle/sage-plan/sage-profile-modify/sage-team/reviewer/qa/sage-review 는 현재 (c).
- **영수증 독립 바인딩 vs advisory(R3 P0-1)**: 로컬 `core_renders` 를 tamper-proof 로 만들려면 write-guard 편입+서명 등 별도 바인딩 필요 → SD-9(서버측) 영역. 그 전까지 로컬=advisory drift 영수증, 권위=CI 재계산.
- **codex 전역 skill 근본 해결**: repo-scoped 전환(SD-6 인접) 전까지 미해결 잔존 — upstream 백로그.

---

## 12. Codex 리뷰 로그 (min3~max5, model=gpt-5.6-sol effort=high, read-only)

### R1 (2026-07-15) — NO-SHIP, P0×3·P1×9·P2×2 전량 수용 → v2
P0-1 "applied each session" 미구현→§3 L1/L2. P0-2 framework 안전 SSOT 우선-덮음→additive-only+Phase 분리. P0-3 기대 base 설치본에서 떠 변조 흡수→canonical base. P1-4 codex 미로드·P1-5 sage-init 누락+임의이름·P1-6 doctor 재설치루프·P1-7 D3 경계·P1-8 공유소스 이중적용·P1-9 codex agent 경로·P1-10 원자성·P1-11 마커·P1-12 읽기실패·P2-13 문서·P2-14 마커버전. D1/D2/D4 REJECT, D3 경계 재설계.

### R2 (2026-07-15) — NO-SHIP, P0×3 잔존(6 Closed·5 Partial·4 Not closed) 전량 수용 → v3
- **P0-1 base 버전 skew**: `_resources` 는 실행 패키지(설치 버전 아님) → 업그레이드 후 mixed-version 재기록 → **§4 manifest.base_sha256 앵커 + skew 시 재기록 금지·업그레이드 안내**. `_resources.py:18`·`hook_entry.py:36`·`install.py:479`
- **P0-2 Phase1 agent/skill 완화 잔존**(WARN=exit0, 물리반영이 "read before CORE"보다 강함) → **§8 게이트-보유 자산 WARN→FAIL + overlay 권위 경계 정직화(authority=hook/CI)**. `validate.py:23`
- **P0-3 강제모델 미결·훅 lifecycle 오결합**(SessionStart profile-JSON 필수·retro off 기본 early-return·write-once; §3/§9/§11 SD-5 모순) → **§3 L1 독립 스텝·early-return 이전·profile-free; FAIL 네이티브(SD-5 은 allowlist 만)**. `hook_runtime.py:608`·`validate.py:23`
- **P1**: caller profile 분기(YAML/JSON)→§4 앵커로 base 재계산 제거. `--force` 파괴→§7 오버레이 보유 대상·마커구간만. 다중파일 원자성 허위→§7 per-file+수렴 self-heal 정직화·L1 race 는 수렴적 무해. codex AGENTS.md 존재≠라우팅→§6 내용 대조. Phase 경계 모순(§4/6/7/e2e 에 AGENT_GUIDE)→**§6 Phase1 매트릭스 framework 제외**·codex L1 freshness 한계. SD-4 미설계→§8 선행 설계문서.
- **P2**: 문서 인벤토리 불완전→§10 전수. LF byte IO 부재→§5.1 `newline="\n"`+Windows.
- **Closed(R1)**: P1-5·P1-7·P1-8·P1-9·P1-11·P1-12.

### R3 (2026-07-15) — NO-SHIP, P0×3·P1×4 전량 수용 → v4
- **P0-1 manifest 는 독립 신뢰 앵커 아님**: base 편집자가 `.manifest.json` 도 편집 가능(write-guard 미보호 `guard.sh:48-59`, schema 검증 optional `validate.py:31-33`). 또 `--force` 가 dict 자산 보존(`install.py:468-472`)+최상위 버전만 stamp(`479-485`) → **옛 render anchor 가 새 최상위 버전과 공존**. → **§4 `core_renders` engine-owned 최상위 맵·`_manifest()` 보존 제외·매 force 전량 재계산·per-entry 버전 비교·missing/손상=FAIL; 로컬=advisory drift 영수증, tamper-proof 권위=CI-pinned 재계산**. `install.py:468-485`
- **P0-2 SessionStart 는 실행 버전 관측 불가**: adapter 가 프로젝트-로컬 런타임을 `python3` 로 직접 실행(`session-start-snapshot.sh:8-11`)·entrypoint 도 로컬 우선(`hook_entry.py:36-45`) → 로컬 코어가 L1 을 아예 안 담을 수도(pre-v3 업그레이드). → **§3 L1 은 skew 판정 제거; §4 skew=현재-패키지 entrypoint(validate/doctor/install); §10 업그레이드=명시적 force·install/sync+CI 강제(문서만 아님)**. 
- **P0-3 Phase1 content-safety fail-closed 아님**: 게이트-보유 4항목 목록 불완전(leader/sage-cycle/sage-plan/sage-profile-modify/sage-team 도 게이트 `leader.md:25-35`·`sage-cycle:18-26`·`sage-plan:109-123`·`sage-profile-modify:95-102`·`sage-team:22-25`)+lint heuristic 우회 가능(`overlay_lint.py:19-36`). WARN→FAIL 승격은 theater. → **§8 lint FAIL 승격 폐기(advisory WARN)·진짜 fail-closed=합성 자격 제한((a)비게이트|(b)오라클-보증만, 미분류=(c)제외)·SD-8 hard-dep**.
- **P1**: profile frontmatter stale(doctor freshness 재계산 유지)→§4·§10 step9. 오버레이 삭제 열거 모순(파일 사라짐)→§7 오버레이∪기존블록/영수증 합집합. manifest schema/routing 부적합(`manifest.schema.json:35-39`·`validate.py:516-524`)→§4·§10 `core_renders` 별도. 크래시=탐지 not self-heal(`install.py:522-610`)→§7 L1 거부·force 재실행 복구.
- **Closed(R2)**: L1 profile-free 가능·retro early-return 위치·L2 FAIL exit1·마커-only 비파괴·framework Phase1 제외 정합.

### R4 (2026-07-15) — NO-SHIP, P0-3 잔존(P0-1·P0-2·P1×4 CLOSED) 수용 → v5
- **CLOSED P0-1**: `core_renders` engine-owned·CI 재계산 권위·로컬 advisory 정직화 확인.
- **CLOSED P0-2**: L1 skew 책임 제거·current-package entrypoint·명시적 force migration 확인.
- **CLOSED P1×4**: deletion enum 합집합·crash 정직화·schema/routing 분리·doctor freshness 유지 확인.
- **RESIDUAL→수용 P0-3**: (c) 자산을 **물리 합성만** 제외하고 **프로즈-read 를 남긴 것**이 봉쇄 아님 — LLM 이 (c) 오버레이를 project-local priority 로 읽어 `record APPROVED` 조작이 통과(`leader.md:17`·`sage-team.md:113`). codex 처방: SD-8 전까지 (c) 오버레이를 **아예 읽지 않거나** prose-read 전 오라클 강제. → **§8 (c) 오버레이 경로 전면 차단**(합성 X + overlay-read 프로즈 제거 + 오버레이 파일 존재 시 validate FAIL), §6 (c) 예외, §10 step5/e2e(i).
- **DEV-READY Phase 1: R4 시점 NO**(P0-3 잔존). v5 봉쇄로 재검증 대상(R5).

### R5 (2026-07-15) — NO-SHIP, P0-3 재잔존(v5 봉쇄가 §6/§10 과 미정합) 수용 → v6
v5 가 §8 에서 (c) 프로즈-read 를 막았으나 **다른 절과 충돌**해 조작 경로가 재개방(codex 확인, teeth 재현):
- **§6 line126** "(c)/미분류 프로즈-read 폴백" 이 §8 전면차단과 정면충돌 → **§6 (c)=전면차단으로 수정**.
- **§6 D3** codex 전역 skill 프로즈-read 무조건 유지 → (c) 전역 skill(sage-cycle/sage-plan/sage-team/sage-review)이 그 경로로 조작 → **프로즈-read 폴백을 (a)/(b) 로 한정, (c) 전역=FAIL**.
- **e2e(j)** "codex 전역 프로즈-read 유지" vs e2e(i) 충돌 → **(a)/(b)만**으로 한정.
- **AGENT_GUIDE:38** 블랭킷 "모든 CORE 렌더 오버레이 먼저 읽어라" 가 (c)까지 강제 → **블랭킷 제거+분류별 per-render 지시**(§6·§10 step11). validate FAIL 은 방어심화, 1차 차단은 "지시 부재".
- **§10 step2** base_sha256 를 "합성 대상"에만 기록 → (c) 렌더 무결성 앵커 부재로 §8 "CORE 변조는 앵커가 잡음" 주장 불성립 → **앵커를 (c) 포함 전 CORE 렌더로 확장**(expected_block="").
- **DEV-READY Phase 1: R5 시점 NO**. v6 정합으로 재검증 대상(R6).

### R6 (2026-07-15) — NO-SHIP, P0-3 알고리즘 미정합 수용 → v7
v6 의 산문 봉쇄가 **알고리즘 정의와 미정합**해 재개방(codex teeth 재현):
- **§4 `expected_block` 분류-blind**: `compose_block(overlay or "")` 가 (a/b/c) 무관 전량 합성 → L1/expected_render 가 (c) 오버레이도 삽입, §10 step2 `(c)=expected_block=""` 와 모순 → **§4 `expected_block` 을 `classify` 경유로 수정**((c)="") + **단일 `classify` resolver 를 install·sync·L1·validate 가 모두 경유**(§7·§10 step4).
- **§7 sync/install 알고리즘에 (a)/(b) 필터 미명시** → (c) 물리 합성 가능 → **§7 preflight 에 classify 편입·(c) 파일 존재 FAIL**.
- **AGENT_GUIDE blanket-read Phase 경계 모순**: AGENTS.md:8 이 AGENT_GUIDE auto-load → blanket "overlay 먼저 읽어라"(AGENT_GUIDE:39-40)가 (c)까지 강제. 그런데 v6 은 AGENT_GUIDE 편집·앵커·write-guard 를 Phase 2 로 미룸 → Phase 1 P0-3 봉쇄가 Phase 1 수단으로 성립 안 됨 → **AGENT_GUIDE 하드닝(blanket 제거+앵커 expected_block=""+write-guard)을 Phase 1 선행으로 이동**(framework 오버레이 kind 와 분리, §4·§8·§10 step11).
- **(c) render 앵커 방식 자체는 codex 가 "올바르면 충분" 확인**(일반삽입=base hash 불일치, block 삽입=empty-block 불일치, manifest 동시변조=CI 재계산).
- **DEV-READY Phase 1: R6 시점 NO**. v7 정합으로 재검증 대상(R7).

### R7 (2026-07-15) — 코어 설계 정합 확인, P0-3 잔여 2건(제거 시맨틱·Phase 문구) 수용 → v8
codex 확인: **`classify→expected_block`·미분류=blocked·(c) prose-read 제거·전 CORE anchor 설계가 서로 정합**. 잔여 2건:
- **(c) 기존 블록 "제거"가 install/L1 에서 미명시**: v7 §7 은 (c)="블록 write 없음"이라 신규만 막고, 이미 물리화된 조작 블록 제거는 sync 에만 있었음(앵커 FAIL=탐지≠제거). → **§3 L1·§7 install/sync 모두 expected_block=""=블록 스트립으로 수렴**(제거), (c) 오버레이 파일 FAIL 은 게이트 신호이되 블록 제거는 파일 존재와 무관히 수행.
- **§6 "framework 제외" 문구가 AGENT_GUIDE Phase-1 하드닝과 모순**: → **§6 을 "framework overlay *kind* 만 제외, AGENT_GUIDE 하드닝은 Phase-1 필수 예외"로 명시**.
- **DEV-READY Phase 1: R7 시점 NO → v8 반영 후 self-verify**. 7라운드 도달(convention 상한), 코어 정합 확인됨 → 잔여 봉쇄를 자체검증으로 마무리.

---

## 관련
- 상위 재설계: `[[SAGE - ChatForYou 적용 재설계 (AGENT_GUIDE override 기반, 26.07.15)]]` §4 SD-3/SD-4, §9-F.
- GitHub 이슈 #5. managed-block 선례: `sage/mcp_common.py:208-232`.
