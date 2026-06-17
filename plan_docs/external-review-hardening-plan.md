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
- [ ] **R3. adapter_contract_version 강제** (P1-3, 회귀안전망)
  - [ ] `_stamp_manifest`가 core.CONTRACT_VERSION 스탬프 + validate 일치검사(STALE)
  - [ ] test + 변이 teeth(core 버전 bump → STALE 검출)
- [ ] **R2. profile 스키마 + 의미검증** (P0-2, 침묵 비활성 차단)
  - [ ] `schema/profile.schema.json`(additionalProperties:false) + `sage/profile_validate.py`
  - [ ] install/generate/doctor/validate 배선(FAIL이면 generate 중단)
  - [ ] test + 변이 teeth(오타 키 → FAIL 검출)

## 중 — 설계결정·기능 (상 완료 후)
- [ ] P1-4 hook vs agent/skill 폐루프 비대칭 해소(scaffold vs subcommand 분리 결정)
- [ ] P1-5 `sage override --reason --ttl` + append-only JSONL 감사 스키마
- [ ] P2-7 YAML 처리 단일화(pyyaml 통일 또는 claims 기계전용 정책)
- [ ] P2-10 패키징(importlib.resources) + 최소 GitHub Actions

## 하 — 안전·이식성 보강
- [ ] P2-9 L0 통과 후에도 l3_content_keywords 스캔(문서도 L3키워드면 WARN)
- [ ] P2-8 codex-host→Claude 호출 경로(§12)
- [ ] P3-11 sys.executable/탐지 + doctor OS·bash·python 점검

## 진행 로그
- 2026-06-17: 코드 재검증 완료, 상/중/하 확정. R4 착수.
