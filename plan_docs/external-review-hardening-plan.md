# 외부검토 1차 엔진 하드닝 — 실행 계획 (260617~)

> 2026-06-17 외부 전문가 1차 검토(평가 6.5/10 + 구조 보완점 P0~P3 + 리팩터링 R1~R4)를
> **코드 레벨로 재검증**한 뒤 상/중/하로 우선순위화한 실행 계획. wiki 정본:
> `TECH - SAGE 1차 외부 검토자료 (260617)`. weatherapp 2차 재구축은 본 계획 **전체 완료 후** 착수.

## 검증 원칙
- 리뷰를 맹신하지 않고 각 주장에 **코드 증거**를 댄 뒤에만 실행등급 부여(F1 선례: 빈 게이트 실증 후 수정).
- 안전 결함은 임의 완화 금지([[cross_model_p0_no_downgrade]]). 단 "리팩터 vs 설계결정필요 기능"은 실행순서로 분리 가능(투명 고지).
- 각 단계: 변이 teeth(테스트가 결함을 실제로 잡는지) + 전체 회귀(run-all.sh) + `sage validate` 통과 후 다음.

## 검증 결과 (코드 증거)
| 항목 | 리뷰 | 증거 | 실행등급 |
|---|:--:|---|:--:|
| R1 어댑터 IO 복제 | P0 | 5쌍 ~296 동일라인(pre-impl 158/154L 중 100 공통) | 상 |
| R2 profile 스키마 부재 | P0 | `generate._compile_profile`=`yaml.safe_load`만, `schema/`에 profile 스키마 없음 | 상 |
| R3 계약버전 미강제 | P1 | hook 엔트리에 `adapter_contract_version` 스탬프 자체가 없음(`_stamp_manifest`), validate 미검사. agent/skill은 하드코딩 "1" | 상 |
| R4 자산경로 분산 | P2 | `id.replace("-","_")`+경로조립이 generate(×2)·validate·absorb 4사이트 재구현 | 상(무위험 enabler 격상) |
| P1-4 폐루프 비대칭 | P1 | generate가 agent/skill 산출물 미생성(안내만) | 중(설계결정 필요) |
| P1-5 감사·override 부재 | P1 | CLI 7종에 override 없음 | 중(신규 기능) |
| P2-7 YAML 3종 | P2 | pyyaml/정규식 frontmatter/정규식 claims 공존 | 중 |
| P2-10 CI/패키징 | P2 | `.claude/settings.json` 없음(자기 도그푸딩 X), `.github/workflows` 없음 | 중 |
| P2-8 cross-model 역방향 | P2 | doctor §12 미해결, codex_host 스텁 | 하 |
| P2-9 L0 우회 | P2 | `_classify_one` L0 즉시 return(내용스캔 전). 단 대상=문서, 수정=WARN | 하(저위험) |
| P3-11 Windows 이식성 | P3 | `python3`/bash 하드코딩 | 하 |

---

## 상 — 엔진 견고성 (weatherapp 전 필수, 순서대로)
- [x] **R4. 자산 경로 로케이터 단일화** (P2-6, 무위험 선행) ✅
  - [x] `sage/asset_paths.py` `AssetPaths(root, kind, id)` 신설 (spec/core/native/adapter(rt)/claims)
  - [x] generate `_gen_hook`·`_stamp_manifest`, validate `_hook_paths`, absorb 4사이트 수렴
  - [x] test_asset_paths.py(run-all step23) + 변이 teeth(core 규약 깨면 FAIL) + 전체 회귀 PASS + validate PASS
- [x] **R1. 어댑터 런타임 모듈 추출** (P0-1, 중심·점진) ✅ — 전 5 hook × 2 런타임 전환 완료
  - [x] `hooks/runtime/{run_hook.py, hook_runtime.py, io_claude.py, io_codex.py}` verbatim lift(공유 단일소스 719L)
  - [x] 단위테스트 18(extract·snapshot·전략F8b·렌더채널·logger/phase4 추출·stop 정책순서) — run-all step24
  - [x] **5 hook 전부**(pre-impl·capture-declared-risk·post-tool-logger·pre-phase4·stop-compliance-report) claude+codex thin launcher 전환
  - [x] 임베드 Python(heredoc) 잔존 0 — claude 어댑터 5종 합계 451L→46L
  - [x] 기능검증: capture/post-tool-logger 양 런타임 수동 e2e + 기존 reverse_extract 폐루프·smoke·golden-e2e·stop adapter e2e(F7 비대칭 포함) 무회귀
  - [x] adapter_hash 전 hook 재스탬프 → validate PASS. 변이 teeth: 공유 runtime 무력화→smoke 12 FAIL
  - 부수효과(문서화): post-tool-logger·pre-phase4·stop 도 malformed profile 시 pre-impl 과 동일 fail-open+surface(이전 crash/exit1) — 게이트 BLOCK(exit2) 계약 불변, 일관성+안전 개선
  - (refine 보류) messages.py 메시지 통일은 동작변경이라 별도(현재 io별 verbatim 보존)
- [x] **R3. adapter_contract_version 강제** (P1-3, 회귀안전망) ✅
  - [x] `_common.contract_version_of`(정규식, import 부작용 0) + generate `_stamp_manifest` core.CONTRACT_VERSION 스탬프
  - [x] validate `_validate_hook` 3b: core 값 vs manifest 대조 → 불일치 STALE(hash 와 별개 인터페이스 드리프트 가드)
  - [x] test_contract_version(run-all step25, 5케이스 incl. no-import-side-effect) + 변이 teeth(core 1→2 → validate STALE exit3)
  - (잔여 follow-up) agents/skills 의 하드코딩 "1"(manifest_util) → reverse_extract CONTRACT_VERSION 파생은 R3 범위 밖(hook core 계약 우선)
- [x] **R2. profile 스키마 + 의미검증** (P0-2, 침묵 비활성 차단) ✅
  - [x] `schema/profile.schema.json` — top-level + risk(12키) + pdca(6키) additionalProperties:false(타입은 느슨, 부분 profile 허용)
  - [x] `sage/profile_validate.py` — schema(jsonschema 선택의존) + 의미검증(전략 모듈 존재·phase 참조·글롭 전무 INFO)
  - [x] generate 배선: 컴파일 후 검증, FAIL이면 산출물 쓰기 전 중단(fail-closed). validate --schema 배선(PROFILE 판정)
  - [x] test_profile_validate(run-all step26, 7케이스) + 통합 teeth: 단수 오타 profile→generate exit1, settings.json 미생성
  - (잔여 follow-up) install/doctor advisory 배선은 빈 템플릿이라 가치 낮음 — generate/validate 우선 적용


## 중 — 설계결정·기능 (상 완료 후) ✅ 전부 완료
- [x] **P1-4 폐루프 비대칭 해소** — 유저결정: conformance_lint 를 validate 에 배선(scaffold 아님). ✅
  - [x] `validate._conformance_check`: render(.claude|.codex/<subdir>/<id>.md) 존재 시 conformance_lint 강제.
        FAIL(누락 required claim·금지위반)=validate FAIL(hook hash/contract 강제와 대칭), WARN=INFO 비게이팅.
  - [x] 엔진 위치(_resources.sage_root)에서 conformance 로드. render 부재/pyyaml 미가용=INFO skip.
  - [x] test_validate_conformance(step27, 6) + 변이 teeth(bump 무력화→FAIL 3건). 커밋 486be20.
- [x] **P1-5 override + 감사** — 유저결정: 파일기반 TTL 토큰 + 감사 JSONL. ✅
  - [x] `override_audit`(runtime 공유): .sage/override.jsonl append-only, 상태=감사 단일소스, TTL 만료 자동회수, gate 스코프.
  - [x] `hook_runtime._maybe_override`(순수코어 IO 0 불변): 양 게이트 block→활성 override 면 통과+bypass 감사.
  - [x] `sage override --reason --ttl [--gate] / --list` CLI. test_override_audit(step28, 12) + 변이 teeth(만료체크 무력화→FAIL)
        + 런타임 e2e(어댑터 subprocess 양런타임 BLOCK→통과+감사·스코프격리). 커밋 fc1676c.
- [x] **P2-7 YAML 단일화** — claims.yml 단일 canonical 코덱. ✅
  - [x] `reverse_extract_common.load_claims_yaml`(emitter 짝, pyyaml 우선+결정론 폴백, 빈섹션 None→list).
        absorb(lossy 정규식 제거)·validate 둘 다 경유. test_claims_codec(step29, 6) + 변이 teeth. 커밋 b987104.
  - profile.yaml(pyyaml 빌드티어)·frontmatter(전용 단일 사용처)는 유지(3-way 아님).
- [x] **P2-10 CI + 패키징 가드** — GitHub Actions + sdist 리소스 가드. ✅
  - [x] `.github/workflows/ci.yml`: test(py3.10/3.11/3.12: editable install→run-all→validate) + packaging(build sdist→가드).
  - [x] `scripts/ci/check_sdist_resources.py`: sdist 가 엔진 리소스 번들하는지 검증(MANIFEST.in 회귀). 변이 teeth(schema 제거→exit1).
  - [x] CI 첫 실행 GitHub green(전 잡 ✓). actions v6 핀. 커밋 4192473·07379f2.
  - (후속) 순수 PyPI wheel 단독배포(scripts/sage_harness 패키지 이전 + importlib.resources)는 blast radius 큰
    별도 아키텍처 과제 — _resources/pyproject 가 이미 추적(공개 전 과제). 현 라운드는 CI + sdist/editable 보존까지.

## 하 — 안전·이식성 보강 ✅ 전부 완료
- [x] **P2-9 L0 통과 문서 L3 키워드 스캔** — classify_risk 가 L0 파일 content 를 l3_content_keywords 로 스캔,
      decide 가 비차단 WARN(warn_l0_l3_content, exit0). 양 io render. manifest 재스탬프. 변이 teeth. 커밋 5c50dcb.
- [x] **P2-8 codex-host→Claude 역방향(§12 스텁 제거)** — doctor.reviewer_resolution 대칭 능력게이팅:
      codex-host 도 claude CLI(caps.claude) 요구(claude-host 의 gstack 요구와 대칭). 맹신 스텁 제거. 변이 teeth. 커밋 d346240.
- [x] **P3-11 Windows 이식성** — validate subprocess sys.executable, 어댑터 10종 SAGE_PYTHON→python3→python 폴백,
      doctor '실행 환경'(OS/python/bash) 진단. manifest 재스탬프. 기능 teeth(SAGE_PYTHON override). 커밋 ab5ffdd.

## ✅ 외부검토 1차 하드닝 전체 완료 (2026-06-18)
상(R4·R1·R3·R2) + 중(P1-4·P1-5·P2-7·P2-10) + 하(P2-9·P2-8·P3-11) 11항목 전부 코드 재검증→구현→
변이 teeth+전체 회귀(run-all 29 step)+validate PASS+**CI GitHub green**. 후속 추적 1건: 순수 PyPI wheel
단독배포(scripts/sage_harness 패키지 이전 + importlib.resources, blast radius 큰 별도 아키텍처 과제).
**weatherapp 2차 재구축 착수 가능.**

## 진행 로그
- 2026-06-17: 코드 재검증 완료, 상/중/하 확정. R4 착수.
- 2026-06-17: **상 블록 전부 완료** — R4(dba1e9a)·R1 파일럿(e9eda01)·R1 완료(33699bc)·R3(1c5047a)·R2.
  각 단계 변이 teeth + 전체 회귀(run-all 26 step) + validate PASS. 다음 라운드: 중(P1-4/P1-5/P2-7/P2-10).
- 2026-06-18: **중 블록 전부 완료** — P1-4 conformance→validate 배선(486be20)·P1-5 override+감사(fc1676c)·
  P2-7 claims 단일코덱(b987104)·P2-10 CI+패키징가드(4192473, actions v6 07379f2). P1-4/P1-5 는 유저 설계결정
  반영(conformance 배선 / 파일기반 TTL+감사). 각 단계 변이 teeth + 전체 회귀(run-all 29 step) + validate PASS +
  **CI GitHub 첫 실행 green**.
- 2026-06-18: **하 블록 전부 완료** — P2-9 L0 L3키워드 WARN(5c50dcb)·P2-8 codex-host→Claude 대칭 능력게이팅(d346240)·
  P3-11 sys.executable+어댑터 PY폴백+doctor 환경진단(ab5ffdd). 각 변이/기능 teeth + run-all PASS + validate PASS + CI green.
  **→ 외부검토 1차 하드닝(상+중+하 11항목) 전체 완료. weatherapp 2차 착수 가능.**
