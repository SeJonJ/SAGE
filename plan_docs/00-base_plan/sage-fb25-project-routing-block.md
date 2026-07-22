# [Base Plan] SAGE-FB25 profile 기반 프로젝트 라우팅 블록

Cycle-Stem: `sage-fb25-project-routing-block`
Risk Level: L3
Status: IMPLEMENTED (자체 7R + codex R1~R5; P1 다수 봉쇄; 릴리즈 유저 대기)

> 본 계획은 초안 `sage-fb25-framework-overlay-domain-refs`(framework overlay 를 domain_refs 전용으로
> 개방)를 **대체**한다. 소비자 분석에서 그 접근이 (1) 오버레이가 잉여이며 (2) 실제 문제를 해결하지
> 못한다는 것이 드러났다(§1.2·§2).

## 1. Context

### 1.1 선행 결정

- `sage-fb-12-framework-overlay-hard-fail`(COMPLETE) 이 framework 4종(`AGENT_GUIDE`, `CLAUDE`,
  `CODEX`, `AGENTS`)을 `overlay_classify.GATE_BEARING_UNBACKED` 로 fail-closed 차단했다.
- FB23 이 게이트 자산 6종을 독립 오라클 backing 으로 (b) 재분류했으나 framework 는 제외했다.
  framework 는 **게이트를 정의하는** auto-loaded governance surface 라, "primary 게이트가 executable
  oracle 로 floored" 라는 (b) 기준을 **구조적으로 만족할 수 없다**. 그 위에 floor 할 오라클이 존재할 수
  없기 때문이다.

### 1.2 초안(domain_refs 전용 개방)이 기각된 이유

1. **오버레이가 잉여다.** 도메인은 프로젝트 전역 속성이라 framework 문서마다 다르게 선언할 이유가
   없다. 문서별 subsetting 요구가 없으면 오버레이가 담을 값은 `profile.risk.domains` 에서 100%
   도출되며, 손으로 유지하는 `domain_refs` 는 authoritative 데이터의 사본이 된다 — SD-4 계약이
   경계하는 바로 그 형태다.
2. **실제 문제를 해결하지 못한다.** 도메인 목록 노출은 §2 의 전달 갭과 별개 사안이다.

따라서 framework overlay 를 여는 대신, **profile 에서 결정론 블록을 직접 생성**한다. 선례가 이미
있다 — `sage/commands/install.py:118 _render_local_profile_gitignore`("user 항목 보존 + SAGE 가
결정론 블록 1개 소유")가 오버레이 없이 관리 블록을 주입하는 동형 패턴이다.

## 2. 문제 — 프로젝트 거버넌스의 전달 갭

프로젝트는 자기 소유 거버넌스 문서와 도메인 프로토콜을 갖지만, **에이전트가 세션 시작에 읽는
auto-loaded surface 에서 그 존재를 알 방법이 없다.** 규칙이 "문서에는 있으나 전달되지 않는" 상태다.

ChatForYou 실측:

- `docs/chatforyou-agent/` 에 거버넌스 문서 4종(`output-contract`, `verification`,
  `pdca-extensions`, `knowledge-capture-fallback`)이 존재한다.
- 그러나 `AGENT_GUIDE.md`(CORE 렌더)의 `docs/` 참조는 **전부 SAGE 중립 문서**(`docs/agent/*`,
  `docs/sage_harness/*`)이며 프로젝트 문서 포인터는 **0개**다.
- `profile.risk.domains` 의 `protocol_pointer`(`sage/critical-domains/<id>.md`) 도 governance
  surface 에 노출되지 않는다. 런타임 소비자
  (`scripts/sage_harness/hooks/runtime/hook_runtime.py:173 _matched_domains`)는 변경 파일을
  glob/keyword 로 매칭할 뿐, 에이전트에게 도메인 존재를 알리지 않는다.

**이 갭이 framework override 가 존재했던 실제 이유다.** override 의 기능은 그 포인터를 governance
surface 에 주입하는 것이었고, FB-12 차단 이후 물리화↔제거를 반복하며 루트 md churn 을 만든다.
`profile.conventions` 는 대안이 아니다 — 실측상 `scope/stack/doc/file_globs` 구조의 **코드 린팅 대상
매핑**이며 거버넌스 문서 레지스트리가 아니다.

## 3. Goal

- profile 에서 도출한 **결정론 "프로젝트 라우팅 블록"** 을 framework 렌더에 생성한다.
- 블록은 **라우팅(경로 포인터 + 짧은 라벨)만** 담는다. 규칙 본문은 프로젝트 소유 문서에 남기고
  주입하지 않는다.
- 블록은 `install --force` 후에도 재생성되어 **업그레이드를 견딘다**.
- `FB-12` 의 framework overlay fail-closed 를 **되열지 않는다**(영구 유지).
- 분류 진실의 두 번째 소스를 만들지 않는다 — authoritative trigger 는 렌더하지 않는다.

## 4. Scope

In scope:

- **profile 레지스트리 신설** — 거버넌스 문서 포인터를 담는 신규 키(예: `governance_docs`;
  `doc` 상대 안전 경로 + 짧은 `label`). 스키마·`profile_validate` 검증·경로 존재 확인.
  - **하위호환**: 키는 **optional**. 부재 시 도메인 블록만 렌더하고 기존 프로젝트 profile 은
    무손상 통과한다(required 승격 금지 — 전 기존 profile 이 깨진다).
  - **shared-only 고정(안전 속성)**: 이 키는 shared policy 계층에만 둔다. local 계층이 이를
    덮어쓰거나 비우면 규칙 라우팅이 통째로 무력화되므로, shared/local 병합 allowlist에서
    **local override 를 금지**한다(FB20 "local 이 안전정책을 낮추지 못한다" 원칙).
- **라우팅 블록 렌더러** — 두 소스를 결정론 렌더:
  1. `risk.domains` → `id` · `risk_level` · `protocol_pointer`
  2. `governance_docs` → `doc` · `label`
- **install/sync 배선** — framework 렌더 생성 시 블록 주입. 정본 위치는 `AGENT_GUIDE`
  (`install.py:782` 기준 양 host 공유 단일 물리 렌더).
- **AGENTS.md 처리 결정** — codex 가 `AGENTS.md` 를 AGENT_GUIDE 보다 먼저 auto-read 하므로,
  블록 중복 생성 또는 포인터 1줄 중 택일(설계에서 확정).
- **trigger 미렌더 강제** — `path_globs`/`content_keywords` 는 블록에 절대 포함하지 않으며 이를
  회귀 테스트로 고정.
- **`core_renders` 앵커/해시 공존** — 블록이 주입되면 AGENT_GUIDE 렌더 내용이 프로젝트마다
  달라진다(`install.py:782` 가 양 host 공유 receipt 로 관리). 기존 오버레이 물리화가 쓰는 방식
  (관리 블록을 제외한 base 로 앵커 비교)을 **재사용**하고, 블록이 앵커 판정을 오염시키지 않음을
  명시적으로 배선·테스트한다.
- **write-guard 미러링** — `generated-artifact-write-guard.sh` 는 AGENT_GUIDE 직접 편집을 막는다.
  SAGE 가 생성하는 라우팅 블록은 그 경로로 들어오므로 예외 배선이 필요하다(사람 손편집은 계속
  차단, 생성 경로만 허용).
- **drift 검사** — 렌더된 블록 ≠ 현재 profile → `validate` STALE/FAIL. 기존 core-render drift 검사와
  동형 배선.
- **profile 유래 문자열 lint** — `label` 등에 기존 gate-relaxation 스캔(`overlay_lint.scan_text`)을
  적용해 방어 일관성 확보.
- **회귀·적대 테스트** — trigger 재복제 시도, 미등록 domain, 존재하지 않는 doc 경로, drift 감지,
  양 host 렌더 정합, **framework overlay 가 여전히 blocked 임을 확인하는 회귀**.
- 세 번 이상 독립 리뷰(codex `gpt-5.6-sol`/high 우선, 불가 시 clean-context headless) 후 finding
  triage.

Out of scope:

- **framework overlay 개방** — `FB-12` fail-closed 를 유지한다. `sage/asset_overrides/framework/`
  경로는 계속 blocked 이며 본 트랙에서 열지 않는다.
- 자유 프로즈를 framework 렌더에 주입하는 모든 형태.
- `qa` · `sage-profile-modify` 의 (c) 상태(각각 FB24/SD-9 트랙).
- 적용 프로젝트의 규칙 본문 작성·이관·override 삭제(적용 프로젝트 측 작업).
- 도메인별 상세 지침 주입 등 블록 의미론 확장.
- 버전 bump·릴리즈(설계·구현 승인 후 별도 단계).

## 5. 해결 커버리지 (ChatForYou 기준 — 목표 달성 검증)

목표: **프로젝트 고유 거버넌스 규칙이 `install --force` 를 견디며 양 host 에이전트에게 전달된다.**

| 규칙 | 현재 전달 경로 | 본 트랙 후 |
|---|---|:--:|
| git commit/push 유저 전용 | `AGENT_GUIDE.md` CORE 본문 | 이미 전달 |
| `chatforyou-desktop/src` 직접수정 금지 | `risk.desktop_block_glob` 결정론 hook | 이미 전달(프로즈보다 강함) |
| Backend/Frontend/Desktop 영향 명시 | 없음 | **라우팅 블록** |
| knowledge write-back fallback | 없음 | **라우팅 블록** |
| 프로젝트 로컬 검증 명령 | 없음 | **라우팅 블록** |
| PDCA 확장 규칙 | 없음 | **라우팅 블록** |
| L3 도메인 프로토콜 | 없음 | **라우팅 블록** |
| host 라우팅 | `.codex/config.toml`·`scripts/run-codex-local.sh` 자기문서화 | 이미 전달 |
| PR base | 문서 자체 없음 | 적용 프로젝트 측 별도 조치(범위 밖) |

전달 경로가 없던 **5건이 닫힌다.** 이것이 본 트랙의 성공 기준이다.

## 6. Done Criteria

1. `profile.risk.domains` + `governance_docs` 로부터 라우팅 블록이 **결정론 생성**되고, 동일 profile
   에 대해 재실행이 동일 산출을 낸다.
2. 블록에 `path_globs`/`content_keywords` 가 **포함되지 않음**을 회귀 테스트가 고정한다.
3. `install --force` 후에도 블록이 재생성되어 규칙 라우팅이 **업그레이드를 견딘다**.
4. 렌더된 블록 ≠ 현재 profile 이면 `validate` 가 STALE/FAIL 로 감지한다.
5. `governance_docs` 의 `doc` 경로 부재·비안전 경로는 `profile_validate` 가 FAIL 한다.
6. **하위호환**: `governance_docs` 부재 profile 이 무손상 통과하고 도메인 블록만 렌더된다.
7. **shared-only(안전 속성)**: local 계층이 `governance_docs` 를 덮어쓰거나 비우려 하면 병합
   단계에서 거부되며, 이를 적대적 테스트가 증명한다.
8. `core_renders` 앵커/해시 판정이 라우팅 블록에 오염되지 않는다(블록 유무와 무관하게 base 대조).
9. write-guard 가 사람의 AGENT_GUIDE 직접 편집은 계속 차단하고 생성 경로만 통과시킨다.
10. `label` 등 profile 유래 문자열에 gate-relaxation 스캔이 적용된다.
11. **framework overlay 는 여전히 blocked** 임을 회귀 테스트가 증명한다(`FB-12` 불변).
12. 양 host(codex·claude) 렌더가 정합하며 `AGENTS.md` 처리 방식이 설계대로 반영된다.
13. `run-all.sh` + `validate --check --schema` 그린, manifest 재스탬프(live==stored).
14. 세 번 이상 독립 리뷰와 finding triage 완료.

## 7. 구현 결과 (as-shipped)

- **신규 모듈** `sage/routing_block.py` — profile(domains+governance_docs) → 라우팅 본문 순수 렌더.
  경로 포인터 + 단일 라인 라벨만, trigger 미렌더. `overlay_common.wrap_routing_block` 이 전용 마커
  (`SAGE PROJECT ROUTING v1`)로 감싼다 — 오버레이 마커와 분리해 FB-12 blocked 와 직교.
- **base_of 확장**: 오버레이 + 라우팅 두 관리 구간을 함께 strip → 앵커가 라우팅 값에 불변(DC8).
- **주입 지점**: `overlay_classify.expected_routing_block` 이 AGENT_GUIDE 한 곳만 채운다(양 host
  공유 정본; codex 는 AGENTS.md 라우터→AGENT_GUIDE read order 로 도달). materialize/check 통합.
- **검증**: `governance_docs` 스키마(root 키, additionalProperties:false) + profile_validate 의미검증
  (safe path·**doc 실재**·gate-relaxation scan·예약 마커 토큰·개행/제어문자 거부). shared-only 는
  FB20 `_LOCAL_KEYS` allowlist 밖 배치로 성립(local 거부).
- **테스트**: `test_routing_block.py`(45) — 렌더/주입/앵커불변/drift/backward-compat/framework-blocked
  회귀/codex parity/shared-only/검증. run-all.sh §41b 등록. 신규 프로젝트 e2e(install→governance_docs
  →install --force→AGENT_GUIDE 라우팅 블록 확인, trigger 부재, 변조→validate FAIL) 확인.
- **자체 적대적 리뷰 7R** → 개행 주입(R2) 봉쇄. 이어 **codex(gpt-5.6-sol/high) R1~R5 적대적 리뷰**로
  다수의 실질 P1 을 추가 발굴·봉쇄(개별 라운드마다 재현+수정+회귀테스트, 매 라운드 전체 그린):
  - **R1**(P1×5): F1 앵커 오염(reversed 마커 count-통과·regex-실패) / F2 검증이 render 경계에서
    미강제(advisory) / F3 마크다운·백틱 breakout / F4 유니코드 라인구분자(U+0085/2028/2029) /
    F5 심링크·Windows `..\` 경로 탈출.
  - **R2**(P1×4+P2×3): 오버레이/라우팅 마커 교차중첩, malformed governance_docs silent-ignore,
    pointer 경로탈출 재발, domain id 마커주입, 라벨 autolink/취소선, authoring↔render 불일치.
  - **R3**(P1×3+P2×1): JSON-only profile 이 domains 검증 우회, `governance_docs: null` silent-strip,
    pointer leading-space/URI/`~`/Windows-abs 탈출, authoring↔render parity 미완.
  - **R4**(P1×3): `risk: null` install 우회, **경로 필드에 프로즈 gate-relaxation 스캐너 오탐**
    (정상 파일명 `review-optional.md` 거부), governance_docs null legacy-validate 갭.
  - **R5**: codex 사이버보안 콘텐츠 필터 오탐으로 verdict 전 중단(코드 결함 아님; imports/determinism
    확인). R5 검증 항목(파리티·문법 충분성·backstop·round-trip·결정론)은 in-context 자체검증으로 완결.
- **최종 방어 구조**: 렌더 대상 필드별 안전등급 분리 — 경로(doc/pointer/id)는 **엄격 문법**(마커·마크다운
  문자 표현 불가로 증명적 차단, 프로즈 스캔 미적용→오탐 제거), 라벨만 **프로즈 gate-relaxation 스캔**.
  전 검증을 **render 경계(expected_routing_block)에서 강제**(install/sync/L1/validate 공통 경유)하고
  authoring(profile_validate)이 **동일 helper 공유**로 파리티 보장. base_of 는 두 관리구간 strip 후
  잔여 마커까지 거부(앵커 불변). 명시적 null·malformed shape·JSON-only 우회 fail-closed.
  - **잔여(수용)**: legacy manifest(core_renders 없음)+`--check`(no `--schema`) 경로의 semantic 미검증은
    SAGE 전반의 pre-existing 구조(FB25 한정 아님)이며 install(변형 경로)은 항상 fail-closed.
  - **잔여(설계선택)**: 문법·80자 라벨 안의 평문 지시는 shared-policy(maintainer 소유)+게이트 훅 강제
    독립성으로 봉쇄(codex 도 R2-5/R5 에서 release defect 아님으로 동의).
