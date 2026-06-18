# SAGE — System for Agentic Governance & Engineering

> **한 줄 요약**: AI 코딩 에이전트(Claude Code · Codex)가 "규칙대로" 일하도록 강제하는 **거버넌스 하네스**를,
> 특정 프로젝트에 종속되지 않게 **재사용 가능한 프레임워크**로 추출·일반화한 standalone 프로젝트.

---

## 왜 SAGE인가 (문제의식)

AI 에이전트에게 코딩을 시키면 빠르지만, **암묵 규칙을 자주 어깁니다** — 고위험 파일을 plan 문서 없이 고치고,
PDCA(Plan-Do-Check-Act) 단계를 건너뛰고, 생성된 산출물을 손으로 덮어쓰고, 자기 모델의 편향으로 자기 코드를 리뷰합니다.

보통은 이런 규칙을 사람이 매번 잔소리하거나, 프로젝트마다 `.claude/`·`.codex/` 설정을 손으로 관리합니다.
SAGE는 그 규칙을 **hook 게이트 + spec-SSOT 자산 사이클**로 코드화해서, 에이전트가 규칙을 어기는 행동을
**실행 시점에 차단(BLOCK)하거나 경고(WARN)**하도록 만듭니다. 그리고 그 장치 전체를 **한 프로젝트가 아니라 어떤 프로젝트에도
얹을 수 있는 엔진**으로 분리했습니다 — 프로젝트 고유값(스택·도메인·위험 패턴)은 전부 `profile`에서 주입되고,
엔진 자체에는 도메인 값이 **0개**입니다.

> 설계 SSOT(원천 문서)는 Obsidian vault: `TECH - SAGE 통합 마스터 설계` · `TECH - SAGE 자산관리 사이클 최종검증` ·
> `TECH - SAGE CORE/OPTION 설치 리소스 카탈로그`. 본 레포는 그 설계의 **구현체**입니다.

---

## 핵심 개념 (멘탈 모델)

SAGE를 이해하는 데 필요한 개념은 다섯 개입니다.

1. **host_runtime — 런타임 택1**
   설치 시 `claude` 또는 `codex` 중 하나를 고릅니다. 어느 쪽도 특권화하지 않습니다(같은 코어, IO만 런타임별로 분기).

2. **spec-SSOT — 의도가 단일 진실원천**
   모든 자산의 "의도(intent)"는 `docs/sage_harness/{hooks,agents,skills}/{id}.md`에 사람이 씁니다.
   실제로 런타임이 읽는 `.claude/.codex` 산출물은 여기서 **생성된 결과물(generated artifact)**이며,
   손으로 직접 고치는 것은 차단됩니다. "고치려면 의도(spec)를 고쳐라"가 원칙입니다.

3. **hook 게이트 — 규칙을 실행 시점에 강제**
   에이전트가 파일을 쓰거나 단계를 넘길 때 hook이 끼어들어 판정합니다. 핵심은 **순수 코어 + 어댑터** 구조입니다:
   정책 판정 로직(`{id}_core.py`)은 입출력이 전혀 없는 순수 함수이고, 런타임별 입출력(파일 읽기·메시지 렌더)은
   얇은 어댑터가 담당합니다 — 덕분에 정책은 테스트하기 쉽고 런타임 간 동작이 일관됩니다.

4. **자동 도출 claims — 사람 수기 최소화**
   agent/skill의 검증 기준(`{id}.claims.yml`)은 spec에서 `reverse_extract`로 자동 도출됩니다.
   사람이 쓰는 건 `intent + advisory_scope`까지고, 나머지는 기계가 만듭니다.

5. **auto_approve_safe_default — 사람은 예외만 본다**
   검증(conformance/hash)이 통과하면 자동 승인하고, 사람은 위험·불일치 같은 **예외만** 검토합니다.

### 자산 사이클 (한 흐름으로)

```
사람이 의도를 쓴다        →  generate          →  런타임에 배치        →  validate / hook 게이트
docs/.../{id}.md (spec)     등록 산출물 + manifest    .claude/.codex/...      drift·staleness·conformance 강제
                            스탬프(hash·계약버전)     (generated artifact)    + 실행 시점 BLOCK/WARN
        ▲                                                                              │
        └──────────────────  absorb (직접수정 → spec patch 제안) ──────────────────────┘
```

핵심은 **폐루프**입니다 — spec에서 산출물을 만들고(generate), 산출물이 spec과 어긋나면 잡아냅니다(validate).
산출물을 급히 손으로 고쳤다면 `absorb`가 그 변경을 다시 spec으로 되돌려 흡수하도록 제안합니다(자동 반영은 안 함).

---

## CLI (8개 명령)

```
sage install    # 런타임 택1 + CORE 하네스 배치(framework + CORE hook 정본/spec/어댑터 + roster agent + manifest)
sage generate   # spec → 등록 산출물(settings.json/hooks.json) + {host}/hooks shim + profile 컴파일 + manifest 스탬프
sage validate   # drift · staleness · conformance · regression 결정론 검사 (읽기전용). --check(빠름) / --schema
sage review     # auto_approve_safe_default — 통과는 자동승인, 사람은 예외(review)만
sage absorb     # 직접수정 diff → spec patch 제안 (자동 반영 없음)
sage doctor     # 옵션 의존성 점검 + 실행 환경(OS/python/bash) 진단 + cross-model reviewer fallback 노출
sage change     # 자연어 의도 → generate/absorb 라우팅 안내 (v1)
sage override   # 게이트 BLOCK 시한부 합법 우회 grant + append-only 감사(.sage/override.jsonl)
```

---

## hook 6종 (무엇을 강제하나)

| hook | 시점 | 역할 |
|---|---|---|
| `pre-implementation-gate` | 파일 수정 전(PreToolUse) | 위험도 분류(L0~L3) + plan/리뷰/PDCA phase 강제. 미충족 시 BLOCK |
| `pre-phase4-checklist-gate` | 단계 전환 전 | PDCA 03→04 전환 시 체크리스트 완료 강제 |
| `capture-declared-risk` | 프롬프트 제출(UserPromptSubmit) | 유저가 선언한 작업 위험레벨 포착 |
| `post-tool-logger` | 도구 실행 후(PostToolUse) | 변경 분류를 세션 JSONL에 기록 |
| `stop-compliance-report` | 세션 종료(Stop) | 컴플라이언스 리포트 생성 |
| `generated-artifact-write-guard` | 파일 수정 전(native) | 생성 산출물 직접수정 차단 → spec으로 redirect |

> form 2종: `core_adapter`(순수 코어 + 런타임 어댑터 — 대부분) / `native`(단일 `.sh` — write-guard).

---

## 디렉토리

```
sage/                       # sage CLI (Python) — install/generate/validate/review/absorb/doctor/change/override
docs/sage_harness/          # 자산 intent SSOT (사람이 쓰는 원천) + .manifest.json
scripts/sage_harness/hooks/ # hook 정본 알고리즘 (canonical executable)
  └─ runtime/               # 공유 런타임(hook_runtime) + 런타임별 IO(io_claude/io_codex) + override_audit
templates/                  # profile/spec/claims 템플릿
schema/                     # manifest·profile JSON Schema
.github/workflows/          # CI (테스트 매트릭스 + sage validate + sdist 패키징 가드)
```

---

## 예시: 프로젝트 적용 (worked example)

가상의 `backend/ + frontend/` 웹앱(고위험 도메인 = 결제/암호)에 SAGE를 적용한다고 하자. 엔진은 이 도메인값을
전혀 모르며, 전부 profile/spec에서 옵니다 — 다른 스택이면 profile만 바꾸면 같은 엔진이 동작합니다(독립).

1) `sage/project-profile.yaml` (발췌):

```yaml
project: { name: "acme", prefix: "acme" }
risk:
  l1_path_globs: ["*frontend/*.js", "*frontend/*.css"]      # 저위험(UI)
  l2_path_globs: ["*backend/*.java", "*backend/*.gradle"]   # 소스/설정(build+test+lint)
  l3_filename_globs: ["*payment*", "*crypto*", "*auth*"]    # 고위험 도메인(plan+리뷰 필수)
  l3_content_keywords: ["encrypt", "PrivateKey", "chargeCard"]
  desktop_block_glob: "*generated/*"                        # 동기화 산출물 직접수정 차단
  plan_glob: "plan_docs/**/*.md"
  l3_review_strategy: "codex_feature_signal"
file_type_map:
  - { glob: "backend/src/main/*", type: backend-main }
  - { glob: "frontend/static/*",  type: frontend-js }
verification:
  commands: { build: "./gradlew build", test: "./gradlew test", lint: "ktlint" }
```

2) agent spec — CORE 기본은 중립(`docs/sage_harness/agents/implementer-a.md`), 인스턴스가 컴포넌트(예: core) 할당 후 채운 예:

```markdown
---
id: implementer-a
kind: agent
---
## intent
할당된 컴포넌트(core)의 설계·구현·컴포넌트 단위테스트.
## advisory_scope
- owns: src/core
- role_boundary: 통합/HTTP/경계값 테스트는 qa 영역
- convention_doc: docs/core-conventions.md
```

3) `sage generate` 후 자동도출 `implementer-a.claims.yml` (발췌, reverse_extract):

```yaml
required_claims:
  - { type: owned_paths,    value: "src/core", confidence: high }
  - { type: convention_doc, value: "docs/core-conventions.md",  confidence: high }
forbidden_claims:
  - { type: safety_forbid,  value: "forbid:integration/http/boundary tests", confidence: high }
  - { inherited_forbidden_claims: "AGENT_GUIDE.non_negotiable_boundaries" }
```

> 테스트/문서용 generic 예시 config는 `scripts/sage_harness/extract_config_example.py` +
> `fixtures/**/example.profile.json`에 있습니다(프레임워크 레포엔 실제 인스턴스를 두지 않음).

---

## 개발 현황 (2026-06-18 기준)

### 어디까지 됐나

1. **코어 엔진 완료** — CLI 8종 + hook 6종 + spec-SSOT 폐루프(generate↔validate). 런타임 claude/codex 양쪽 동작.
2. **golden-instance e2e** — 합성 인스턴스로 install→generate→validate→설치 shim 구동까지 전체 파이프라인을 폐루프 테스트로 박제.
3. **외부 검토 1차 하드닝(11항목) 완료** — 외부 전문가 1차 검토(6.5/10)에서 지목된 P0~P3 + 리팩터링 R1~R4를
   **코드 레벨로 재검증한 뒤** 상/중/하로 구현. 각 항목은 변이 teeth(테스트가 결함을 실제로 잡는지 확인) +
   전체 회귀 + `sage validate` PASS + CI green으로 닫음.

### 이번 하드닝이 "지금 보장하는 것" (사람 말로)

- **어댑터에 복붙된 Python 0** (R1) — 5개 hook × 2런타임에 흩어져 있던 ~300줄 중복 IO를 공유 `hook_runtime` +
  런타임별 `io_claude`/`io_codex` 단일소스로 통합. 한 곳만 고치면 양 런타임에 반영됩니다.
- **오타 한 글자로 게이트가 조용히 꺼지지 않음** (R2) — `profile`의 위험/PDCA 키에 오타(`l3_filename_glob` 등)가 있으면
  스키마+의미검증이 잡아 `generate`를 **산출물 쓰기 전에 중단**합니다(침묵 비활성 차단).
- **인터페이스 드리프트 이중 방어** (R3) — 코어의 계약 버전을 manifest에 스탬프하고 `validate`가 대조 → 내용 해시와 별개로
  코어 계약이 바뀌면 STALE로 잡습니다.
- **agent/skill도 hook처럼 폐루프 강제** (P1-4) — 렌더된 산출물이 required claim을 누락하거나 금지를 위반하면
  `sage validate`가 **FAIL**합니다(예전엔 hash만 봤음).
- **게이트를 합법적으로, 추적 가능하게 우회** (P1-5) — `sage override --reason --ttl`로 사유·기한을 남기고 BLOCK을 우회하며,
  grant와 실제 우회(bypass)가 모두 `.sage/override.jsonl`에 append-only로 기록됩니다. TTL 만료로 권한 자동 회수(상시 우회 방지).
- **자기 자신을 테스트하는 CI** (P2-10) — push/PR마다 GitHub Actions가 전체 회귀(29 step / 250+ 테스트) +
  `sage validate` + sdist 리소스 번들 검증을 돌립니다.
- **문서 속 민감정보 경고** (P2-9) · **cross-model 역방향 능력 검증**(P2-8) · **Windows 이식성**(P3-11, `sys.executable` +
  어댑터 `SAGE_PYTHON` 폴백 + doctor 환경 진단)까지 보강.

### 정직하게 — 아직 안 된 것

- **순수 PyPI wheel 단독 배포**는 아직입니다. 현재 동작하는 설치 경로는 **git clone / `pip install -e .`(editable) / sdist**이며,
  리소스 경로는 `sage/_resources.py`(`$SAGE_RESOURCE_ROOT` override + repo fallback)로 해석합니다.
  순수 wheel은 dual-use인 `scripts/sage_harness`의 패키지 이전(`importlib.resources`)이 필요 — 별도 마일스톤으로 예정.
- `pyyaml`은 `generate`(빌드) 의존성입니다. **hook 런타임은 의존성 0**(순수 JSON)으로 가볍게 유지합니다.

---

## 로드맵 (다음 순서)

확정된 진행 순서는 vault `TECH - SAGE 앞으로 개발할 내용`에 있습니다. 요약:

1. **잔여 open 엔진 항목** — EH-1 동적 roster → EH-2 output_contract 독립화 → wheel 패키징(독립 게이팅 마일스톤)
2. **weatherapp 2차** — F9 게이트 강제 하의 첫 정상 Tier 2 실세계 골든 인스턴스(wheel 설치 경로 실증)
3. **MCP 개발** — MCP 서버를 4번째 거버넌스 자산 종류로 편입(Enhancement는 ChatForYou 선반영 → SAGE Standalone 승격)
4. **weatherapp 3차** — MCP 자산 클래스 포함 end-to-end 실증

---

## License

This project is licensed under the **Creative Commons Attribution‑NonCommercial 4.0 International (CC BY‑NC 4.0)**.

You may **share** and **adapt** the material for **non‑commercial** purposes only, provided you give appropriate credit, indicate if changes were made, and distribute any derivative works under the same non‑commercial license.

For the full license text, see: https://creativecommons.org/licenses/by-nc/4.0/
