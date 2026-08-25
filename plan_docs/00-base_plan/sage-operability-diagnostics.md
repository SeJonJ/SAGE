# [기본 계획] 운영 진단·복구 UX와 runtime API 사전 호환성

Cycle-Stem: `sage-operability-diagnostics`
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 12
Status: READY

## 0. 사전 지식

| 구분 | 근거 | 핵심 내용 |
|---|---|---|
| 승인 설계 | 위키 노트 `SAGE - 1.0 운영 진단과 복구 UX 설계 (26.08.13)` | 공통 진단·복구 계약 위에 `sage status`·`sage explain --path`를 얹고, project hook runtime API 불일치를 core import 전에 닫으며, 모든 사용자 노출 BLOCK에 `Next:`를 보장한다. 저장소 고정 사본은 `docs/superpowers/specs/2026-08-23-sage-operability-diagnostics-design.md`. |
| 사용자 결정 | 2026-08-23 착수 대화 | 진단 모델은 기존 `Diagnostic`을 **가산 확장**한다. 439개 호출부를 개수하는 전면 교체안은 채택하지 않는다. |
| 사용자 결정 | 2026-08-23 착수 대화 | 이 사이클은 SAGE CLI로 사이클을 열지 않는다. phase 문서는 같은 구조로 수동 작성한다. 자기 도그푸딩이 이번 변경 대상과 겹치기 때문이다. |
| 선행 작업 | `v1.0.0 준비` (PR #6) · `sage-fast-cycle-usability-hardening` (PR #7) | 한영 catalog·`upgrade`·Fast Cycle 경화가 모두 main에 병합돼 있다. 이 사이클은 그 결과의 catalog·version contract·upgrade API를 기준선으로 삼는다. |
| 구현 기준점 | `main@63cc3bd` | 브랜치 `feat/sage-operability-diagnostics`가 이 커밋에서 갈라진다. |
| 진단 모델 실측 | 2026-08-23 저장소 조사 | `sage/diagnostics.py`는 87줄이고 `Diagnostic(code, evidence, **arguments)` 시그니처다. 호출부는 `sage/`·`scripts/` 합쳐 **439곳**, 20개 이상 모듈에 분포한다. |
| BLOCK 표면 실측 | 2026-08-23 저장소 조사 | hook 코드에서 `block_*` 패턴은 33건 잡히지만 **실제 메시지 키는 29개**다. 나머지 4건은 키가 아니다 — `block_message`는 함수명(`generated_artifact_write_guard_core.py:103`), `block_reason`은 함수 파라미터(`runtime/io_codex.py:254`), `block_release`는 profile 설정 키, `block_stale`은 `block_stale_done_criteria_revision`의 prefix 아티팩트다. CLI catalog는 `sage/i18n/ko.py` 1,438줄·`en.py` 1,421줄이다. |
| write guard 표면 실측 | 2026-08-23 저장소 조사 | 승인 설계 §4.2가 예시로 든 `guard.generated_asset`에는 대응 message_key가 없다. `generated_artifact_write_guard_core.py:103 block_message()`가 완성 한국어를 직접 조립하며 분기가 5개다. catalog 키가 아니고 영어가 없으며 `Next:` 대신 `→`를 쓴다. |
| i18n 부채 스캐너 사각지대 | `sage/i18n/validation.py:132` | `korean_returning_runtime_functions`는 `hooks/runtime/` 아래 7개 모듈만 스캔한다. write guard는 `hooks/` 최상위라 범위 밖이고, 그래서 `KOREAN_JUDGEMENT_DEBT`가 비어 있는 채로 한국어 전용 BLOCK 표면이 "부채 없음"으로 보고된다. |
| CLI BLOCK 규약 부재 | 2026-08-23 저장소 조사 | CLI에는 "BLOCK으로 종료"라는 단일 규약이 없다. `sage/ci_authority.py`만 `status: "BLOCK"`을 내고, 나머지는 exit code와 `cli.*.blocked_*` 류 catalog 키에 흩어져 있다. 설계 §9.1의 CLI 항목은 그대로는 판정 불가능하다. |
| preflight 자리 실측 | `sage/hook_entry.py` (343줄) | `_project_hook_state`(:37)가 이미 manifest를 읽고, `_notify_version_contract`(:248)가 manifest 기반 WARN을 낸다. runtime API preflight는 이 두 함수와 같은 계층에 들어간다. |
| explain 재사용 지점 실측 | `pre_implementation_gate_core.py` | `classify_risk`(:110)와 `_classify_one(path, content, profile)`(:62)이 판정 정본이다. `content`가 인자이므로 path-only 추출이 가능하지만, 추출본이 gate와 갈리면 두 번째 정본이 된다. |
| generated asset 판정 | `generated_artifact_write_guard_core.py` | `is_guarded`(:61)·`block_message`(:103)가 소유권 판정 정본이다. `explain`은 이 함수를 재사용하고 자체 glob을 만들지 않는다. |
| manifest schema 실측 | `schema/manifest.schema.json` | top-level property 13개, `required`는 `sage_version`·`host_runtime`·`assets` 3개다. `runtime_api`는 여기에 추가된다. |
| catalog oracle 실측 | `sage/i18n/validation.py` | `catalog_issues`(:193)·`_domain_issues`(:77)·`_content_issues`(:106)가 이미 한영 key·placeholder 동등성을 강제한다. recovery 완전성 oracle은 이 모듈을 확장한다. |
| 검증 환경 경계 | `sage._resources.is_engine_source_tree` | 이 저장소는 엔진 소스 트리라 자기 게이트가 돌지 않는다. `status`·`explain`·preflight의 실제 판정은 fixture와 격리 wheel 소비 프로젝트에서만 판정된다. |
| 선행 사이클이 남긴 부채 | `sage-fast-cycle-usability-hardening` Phase 00 §2.2 | 직전 사이클이 추가한 BLOCK 메시지는 이번 `Next:` 완전성 oracle의 대상이다. 직전 사이클은 진단 계약을 선취하지 않고 이 사이클로 넘겼다. |
| 후속 작업 경계 | 로드맵 `sage-audit-visibility-no-vault` | `.sage` 감사 4종 통합 조회(`sage audit show`)와 전체 no-vault Golden E2E는 다음 항목이 소유한다. 이번에는 이번 세 기능의 vault 비의존성만 좁게 검증한다. |

## 1. 목표

사용자가 차단된 뒤 무엇을 해야 하는지 추측하지 않게 만든다. 목표는 다음 네 가지다.

1. 판정 소스가 서로 다른 진단을 같은 계약으로 전달하고, 그 계약이 복구 순서를 함께 실어 나른다.
2. 지금 이 프로젝트에서 SAGE를 쓸 수 있는지와 무엇부터 고쳐야 하는지를 읽기 전용 `sage status`가 한 화면에 보여준다.
3. 특정 경로가 왜 그런 요구를 받는지를 `sage explain --path`가 설명하되, 실제 write를 허용한다고 예언하지 않는다.
4. project hook이 요구하는 runtime API가 현재 `sage-hook`보다 새로우면 core import 전에 닫는다.

종료 상태는 정확히 다음 중 하나다.

- `NOT READY`: 필수 인수 항목이 하나 이상 해결되지 않았다.
- `READY_FOR_USER_MERGE_DECISION`: 구현과 검증은 통과했지만 커밋·머지·push·릴리즈는 수행하지 않았다.

## 2. 범위

### 2.1 포함

- 기존 `Diagnostic`에 `severity`를 가산하는 확장과, 생성부가 아닌 단일 매핑 테이블이 소유하는 `RecoveryStep`.
- BLOCK 진단의 recovery 완전성과 한영 catalog 동등성을 강제하는 build-time oracle.
- 읽기 전용 `sage status [--json]`과 project·version·runtime API·profile·host·cycle·gate readiness 7영역 collector.
- `status`의 text 렌더, JSON schema v1, exit code 0·1·2 계약.
- 읽기 전용 `sage explain --path <path>`와 path risk floor·매치 규칙·component·cycle 결속·phase readiness·dynamic 한계 표시.
- `explain`이 재사용할 path normalization/containment, component ownership, path glob risk floor, generated asset ownership, cycle binding, risk별 required phase의 순수 helper 추출.
- manifest top-level `runtime_api.required` 계약과 package 상수 `HOOK_RUNTIME_API = 1`.
- `install --force`·`generate --kind hook --write`의 marker stamp, `validate`의 대조, `upgrade --check`의 migration 표시.
- `sage-hook`의 project core import 전 compatibility preflight와 host별 wire 표현 보존.
- built-in CLI·hook의 모든 사용자 노출 BLOCK에 최소 한 줄 `Next:` 보장과 bootstrap direct print의 구조화.
- write guard `block_message()` 5개 분기를 진단 code·한영 catalog·recovery로 이관.
- Claude·Codex 실제 adapter subprocess 회귀와 wheel 설치 환경 회귀.
- README·quickstart·troubleshooting·CLI reference 한영 문서 갱신과 manifest·hook runtime hash 재스탬프.

### 2.2 제외

- `.sage` 감사 로그 4종을 합쳐 조회하는 `sage audit show`.
- Obsidian dashboard 생성·수정과 vault 존재 여부의 필수조건 승격.
- `doctor`·`validate`의 제거·개명과 그 exit 계약 변경.
- `explain`에서 가상 host event를 합성해 실제 gate를 실행하는 dry-run.
- 자동 수정, 자동 upgrade, 자동 `install --force`.
- project hook 저자가 만든 임의 자연어 메시지의 의미 추론과 그에 맞춘 복구 명령 생성.
- J-3에서 기각한 cross-process project root 자동 통일.
- package 전체를 project hook runtime에 vendoring.
- 기존 `Diagnostic` 439개 호출부의 시그니처 개수.
- `korean_returning_runtime_functions` 술어의 `hooks/*.py` 확장. 현재 술어가 정규식 문자 클래스까지 부채로 세어 release를 잘못 막는다(Phase 03 §3.4). 백로그로 이관한다.
- 기존 CLI 오류의 BLOCK 승격. 승격은 사용자에게 보이는 exit 변경이라 진단 UX 작업이 조용히 수행할 일이 아니다.
- `OPD-AC80`(preflight 이전 runtime의 메시지)의 실증. 이 저장소에 그 runtime이 없어 만들 수 있는 증거가 없다. `plan_docs/enhancement-backlog.md` **EH-25**로 이관했다(Phase 04 §3.3).
- chain 필드 없이 쓰인 옛 Fast 감사를 가진 설치의 이행 안내. `run_issues`가 `chain_ok is None`을 결함으로 올리므로 그런 설치는 이제 붉게 보인다. 게이트는 이전부터 같은 상태를 거부했으므로 새 차단은 아니다. `plan_docs/enhancement-backlog.md` **EH-26**으로 이관했다.
- 전환 provenance reader의 check-to-open 경쟁(Phase 05 P1-02). 로컬 트리 쓰기 권한과 정밀한 동시 파일 교체가 모두 필요한 낮은 빈도의 self-attested 경계이며, 이번 1.0 범위에서는 명시적으로 수용한다. descriptor-bound `O_NOFOLLOW` 읽기는 `plan_docs/enhancement-backlog.md` **EH-27**로 이관했다.
- 커밋·머지·push·태그·릴리즈.

## 3. 영향 분석

| 영역 | 변경 | 고정 경계 |
|---|---|---|
| `sage/diagnostics.py` | `severity` 가산, recovery 매핑 조회, deterministic 정렬, JSON 직렬화 | 기존 `Diagnostic(code, evidence, **arguments)` 시그니처와 `render()`의 `prefix + code` 조립은 불변이다. 이 모듈은 어느 catalog도 import하지 않는다. |
| CLI catalog·oracle | recovery 문구 key와 완전성 검사 | 기존 `catalog_issues` 판정 어휘와 도메인 경계는 유지한다. |
| hook catalog | recovery 문구 key (독립 1벌) | 설치 hook runtime은 `sage.i18n`을 import하지 않는다. 이 경계를 진단 계약을 이유로 열지 않는다. |
| `sage/cli.py` | `status`·`explain` 등록 | 기존 21개 서브커맨드의 인자·exit는 불변이다. |
| 신규 `status`·`explain` | 조회·렌더만 수행 | 새 권한 판정기가 되지 않는다. 파일·감사·상태를 쓰지 않는다. |
| gate core | 순수 helper 추출 | `classify_risk`의 판정 결과는 불변이다. 추출은 이동이지 재작성이 아니며 parity test가 이를 고정한다. |
| `sage/hook_entry.py` | core import 전 preflight | bootstrap BLOCK의 host별 wire 표현(Claude stderr+차단 exit, Codex Stop stdout 단일 JSON+rc 0)은 불변이다. |
| manifest schema·install·generate·validate·upgrade | `runtime_api` stamp·검증·migration | 기존 13개 property와 3개 required의 의미는 불변이다. `required_version` 정본은 계속 shared profile이 소유한다. |
| 29개 block 메시지 키 | recovery id 매핑 등재 | `message_key` 이름은 호환 계약이므로 바꾸지 않는다. |
| 사용자 문서 | 한영 6종 갱신 | 한영 미러 상태를 유지한다. |

## 4. 전역 불변 조건

### G1. 새 판정 정본을 만들지 않는다

`status`와 `explain`은 기존 순수 판정기를 호출한다. 판정 로직을 새 명령 안에 복사하지 않고, collector가 `doctor.run()`·`validate.run()`을 subprocess로 호출해 stdout을 재파싱하지도 않는다. 필요한 함수는 재사용하거나 좁게 추출한다.

### G2. 읽기 전용은 읽기 전용이다

`status`와 `explain`은 tracked 파일과 `.sage` 전체를 바이트 단위로 바꾸지 않는다. 감사·상태·grant를 쓰지 않고, 복구 명령을 자동 실행하지 않는다.

### G3. `explain`은 허용을 약속하지 않는다

최종 결과에 `ALLOW`를 쓰지 않는다. 실제 gate는 새 내용·세션 risk 선언·다중 변경에 의존하므로, 그 축은 `dynamic_checks`로 명시한다. 기존 파일 내용을 읽어 content risk를 추측하지 않는다 — 사용자가 쓰려는 새 내용과 다르기 때문이다.

### G4. 호환성은 import 전에 판정한다

`sage-hook`은 project core를 import하기 **전에** manifest marker를 읽고 정수 API를 비교한다. 판정이 뒤로 밀리면 `ModuleNotFoundError` traceback이 먼저 나오고 host가 그것을 단순 hook 오류로 해석할 수 있다. 이 순서 자체가 계약이며 mutation test가 고정한다.

### G5. 부재는 안전 방향이 아니다

1.0 manifest에서 marker 부재는 legacy 통과로 낮아지지 않고 손상으로 판정된다. legacy 인정은 `generator_version`이 유효한 SemVer이고 major가 `0`일 때만 성립한다. version과 marker를 함께 지우는 downgrade를 통과시키지 않는다.

### G6. 차단은 fail-closed, 기록은 loud

policy를 실행하는 gate와 project hook은 비호환 시 rc 2로 닫힌다. post logger·baseline hook 하나의 비호환은 host 작업 전체를 직접 막지 않고 rc 0 LOUD WARN을 남기되, 실제 write는 pre-implementation gate가 같은 preflight에서 차단한다.

### G7. BLOCK에는 항상 다음 행동이 있다

built-in 사용자 노출 BLOCK은 최소 한 줄의 `Next:`를 가지며 그중 최소 하나는 실행 가능한 명령이다. 사람이 직접 해야 하는 설명은 `Action:`으로 분리한다. 안전한 직접 복구가 없으면 첫 단계는 읽기 전용 진단 명령이다.

### G8. 복구는 안전한 것부터다

복구 순서는 읽기 전용 확인 → 필요한 mutation → 재검증이다. destructive command, 감사 로그 삭제, profile 완화, generic override를 기본 복구로 제시하지 않는다.

### G9. recovery id의 정본은 하나다

같은 recovery id가 장소마다 다른 명령을 내지 않는다. recovery는 진단 생성부가 아니라 단일 매핑 테이블이 소유하며, 이 소유권이 드리프트를 구조적으로 막는다.

### G10. hook은 엔진 없이 돈다

공통 계약을 이유로 hook runtime이 CLI i18n package를 import하게 만들지 않는다. 공통인 것은 code·recovery id의 **형태와 의미**이고, 양쪽 집합의 일치는 build-time oracle이 대조한다.

### G11. JSON은 언어를 타지 않는다

`status --json`은 번역 문장을 담지 않고 byte-stable key·enum만 쓴다. 진단 순서는 `BLOCK → WARN → INFO`, 같은 severity 안에서는 code 정렬로 고정한다. 절대경로·vault 경로·token·환경변수 값은 evidence에 싣지 않는다.

### G12. 기존 명령의 역할과 exit를 깨뜨리지 않는다

`doctor`·`validate`·`upgrade`의 책임과 exit 계약은 그대로다. `status`는 `validate`의 STALE 전용 exit `3`을 재사용하지 않고, stale을 실제 영향에 따라 WARN 또는 BLOCK diagnostic으로 표현한다.

### G13. 안정 식별자는 한 번 나가면 못 바꾼다

진단 `code`는 언어 독립 안정 식별자다. `block_message`·`block_reason`처럼 이름 자체에 의미가 없는 키에서 기계적으로 code를 파생시키지 않는다. 애매한 자동 추론을 금지하고 명시 매핑만 쓴다.

### G14. 이 저장소에서 안 막히는 것은 증거가 아니다

엔진 소스 트리에서는 자기 게이트가 실행되지 않는다. 세 기능의 동작은 fixture와 격리 wheel 소비 프로젝트에서 재현·검증하며, "로컬에서 잘 돈다"를 증거로 사용하지 않는다.

### G15. 이번 사이클은 로컬 게이트 증거를 갖지 않는다

SAGE CLI로 사이클을 열지 않기로 했으므로 `Phase00-Hash`·`Done-Criteria-Revision`·cycle 결속은 문서 규약으로만 유지되고 엔진이 검증하지 않는다. 사후에 형식만 맞춘 감사 레코드를 만들어 통과한 것처럼 보이게 하지 않는다.

## 승인 설계와의 편차

승인 설계는 저장소를 실측하기 전에 작성됐다. 착수 시점 실측에서 설계 문언을 그대로 따르면 설계 자신이 세운 계약이 깨지는 자리가 셋 나왔고, 운영 판단으로 하나를 더 바꿨다. 각 편차는 **무엇이 문제였고 무엇을 바꿨는지**와 **설계 의도를 무엇으로 대신 지키는지**를 함께 기록한다.

### D1. 진단 모델을 새로 만들지 않고 가산 확장한다

- **설계:** §5.1이 `Diagnostic(code, severity, subject, message_key, arguments, evidence, recovery)`를 새 immutable value object로 정의한다. §11은 이를 `sage/diagnostics.py`의 책임으로 둔다.
- **문제:** 같은 이름의 클래스가 이미 `sage/diagnostics.py`에 있고 `(code, evidence, **arguments)` 시그니처로 **439곳**에서 쓰인다. 설계대로 필수 필드를 추가하면 439개 호출부를 개수해야 한다. 더 나쁜 것은 recovery의 소유권이다 — recovery를 생성 인자로 두면 439개 지점이 각자 복구 명령을 적을 수 있고, 그러면 설계 §9.2-7 "같은 recovery id가 여러 곳에서 다른 명령을 내지 않는다"를 강제할 구조적 수단이 사라진다. 검사로 뒤늦게 잡을 수는 있어도 애초에 갈릴 수 없게 만드는 편이 낫다.
- **변경:** 기존 시그니처를 불변으로 두고 `severity`만 기본값을 가진 선택 필드로 가산한다. `recovery`는 생성부가 아니라 `code → tuple[RecoveryStep, ...]` **단일 매핑 테이블**이 소유하고, 진단은 code만 들고 다닌다. 매핑에 등재되는 것은 severity가 BLOCK인 code뿐이며, 착수 시점 hook 쪽 후보는 29개다.
- **설계 의도 보존:** §5.1-4(BLOCK은 recovery가 비어 있을 수 없다)는 매핑 완전성 oracle이 강제한다 — 생성부 소유보다 강한 보장이다. §5.1-6(자동 실행 금지)·§9.2(렌더 규칙)는 그대로다.

### D2. `subject`·`message_key` 필드를 두지 않는다

- **설계:** §5.1 데이터 모델이 `subject`와 `message_key`를 각각 독립 필드로 둔다.
- **문제:** 현재 렌더는 `render(diagnostic, translate, prefix)`가 `f"{prefix}.{code}"`로 catalog key를 조립한다. 즉 `message_key`는 이미 `(prefix, code)`의 함수다. 이를 별도 필드로 저장하면 같은 사실의 정본이 둘이 되고, 둘이 갈렸을 때 어느 쪽이 맞는지 판정할 근거가 없다. 설계 §5.1-2가 "사람이 읽는 문장은 catalog가 소유한다"고 못 박은 것과 같은 이유로, key 조립도 렌더가 소유해야 한다.
- **변경:** `message_key`를 도입하지 않고 기존 `prefix + code` 조립을 유지한다. `subject`는 필드로 두지 않고 필요한 진단이 `arguments`로 싣는다 — 표시 대상은 진단마다 다르고(경로·stem·host·asset id), 고정 필드 하나로 묶으면 의미가 뭉개진다.
- **설계 의도 보존:** §5.1-1(code는 언어 독립 안정 식별자)·-2(문장은 catalog 소유)·-3(JSON에 번역 문장 없음)은 그대로다. 같은 code가 CLI에서 `cli.<code>`, hook에서 `hook.<code>`로 렌더되는 기존 도메인 분리도 유지된다.

### D3. block 키에서 code를 기계 변환하지 않고 명시 매핑만 쓴다

- **설계:** §5.2가 "진단 code는 `gate.<message_key에서 block_ 접두 제거>`로 결정론 변환하거나 명시 매핑한다"며 두 선택지를 준다.
- **문제:** 기계 변환은 **무엇이 키인지조차 스스로 판단하지 못한다.** `block_*` 패턴으로 잡히는 33건 중 4건은 메시지 키가 아니다 — `block_message`는 함수명, `block_reason`은 함수 파라미터, `block_release`는 profile 설정 키, `block_stale`은 다른 키의 prefix다. 변환기에 이 넷을 그대로 먹이면 `gate.message`·`gate.reason`·`gate.release`·`gate.stale`이라는 안정 식별자가 만들어진다. 함수명과 설정 키에서 파생된 사용자 노출 식별자이고, 안정 식별자는 한 번 사용자·CI에 나가면 되돌릴 수 없다. 남은 29개도 접두 제거만으로는 `stale`·`stale_done_criteria_approval`·`stale_done_criteria_revision`처럼 같은 namespace에 뭉쳐 서로 구분되지 않는다.
- **변경:** 설계가 허용한 두 선택지 중 **명시 매핑만** 채택하고 기계 변환 경로 자체를 만들지 않는다. 실제 메시지 키 29개 각각에 의미 있는 code를 사람이 정하고, 키가 아닌 4건은 애초에 대상에서 제외한다.
- **설계 의도 보존:** §5.2의 "애매한 자동 추론은 금지하고 build-time oracle이 누락을 잡는다"를 더 좁게 지킨 것이다. 기존 `message_key` 이름은 호환 계약이므로 그대로 둔다.

### D4. SAGE CLI로 이 사이클을 열지 않는다

- **설계:** §14 구현 순서가 정규 사이클 절차를 전제한다.
- **문제:** 이 저장소는 엔진 소스 트리이고, 이번 사이클이 바꾸는 대상에 `hook_entry`의 부트스트랩 경로, manifest schema, 33개 BLOCK 메시지 렌더가 포함된다. 자기 자산으로 자기 변경을 검증하면 개발 중의 깨진 중간 상태가 곧 개발 도구의 고장이 되고, 그때 무엇이 결함이고 무엇이 미완성인지 분리할 수 없다.
- **변경:** phase 문서는 같은 구조·같은 헤더 규약으로 수동 작성하고, `sage change`를 비롯한 SAGE 사이클 명령은 실행하지 않는다.
- **대가(숨기지 않는다):** 이 사이클의 산출물은 **로컬 게이트 통과 증거를 갖지 않는다.** `Phase00-Hash`·`Done-Criteria-Revision`·cycle 결속은 문서 규약으로만 유지된다. 대신 fixture와 격리 wheel 소비 프로젝트 검증이 유일한 판정 근거이며, 이는 G14가 이미 요구하던 것이라 실질적인 증거 강도는 낮아지지 않는다. 사후에 형식만 맞춘 감사 레코드를 만들지 않는다(G15).

## 구현 순서

세 단계로 끊는다. 각 단계가 실패하면 뒤 단계로 진행하지 않는다.

**1단계 — 계약과 호환성 (커밋 지점)**

1. 현재 사용자 노출 BLOCK inventory와 bootstrap direct print 예외를 실측으로 고정한다.
2. `severity` 가산·recovery 매핑·정렬·JSON 직렬화의 실패 테스트를 먼저 작성한다.
3. `runtime_api` pure contract와 결정표의 실패 테스트를 작성한다.
4. manifest schema·stamp·validate·upgrade compatibility를 구현한다.
5. `sage-hook` import 전 preflight와 dual-host subprocess 회귀를 구현한다.

여기서 전체 suite와 wheel smoke를 돌리고 사용자에게 보고한다.

**2단계 — 조회 명령**

6. `status` collector·text·JSON·exit를 구현한다.
7. gate 순수 helper를 추출하고 parity를 고정한다.
8. `explain` path-only 분석을 구현한다.

**3단계 — 완전성과 마무리**

9. BLOCK code의 recovery 매핑과 완전성 oracle을 구현한다.
10. 한영 사용자 문서 6종을 갱신한다.
11. manifest·hook runtime hash 재스탬프, 전체 suite, wheel smoke, 독립 리뷰를 수행한다.

## 주요 위험과 통제

| 위험 | 등급 | 통제 |
|---|:---:|---|
| preflight가 core import 뒤로 밀려 traceback이 먼저 나옴 | P0 | 순서 자체를 mutation test로 고정한다. preflight를 뒤로 옮기면 실패한다. |
| 1.0 marker 누락이 legacy 통과로 낮아짐 | P0 | `generator_version` major 0 검사와 결정표 5행 전수 테스트. marker+version 동시 삭제 fixture를 포함한다. |
| `explain`이 두 번째 판정 정본이 됨 | P0 | 추출한 helper와 gate가 같은 fixture에 같은 판정을 내는 parity test. `explain`이 existing content를 읽으면 실패하는 이빨. |
| `status`/`explain`이 상태를 씀 | P0 | 명령 전후 tracked 파일과 `.sage` 바이트 snapshot 동일성 검사. |
| recovery가 profile 완화·감사 삭제·override를 기본 해법으로 제시 | P0 | 금지 명령 목록을 검사하는 oracle. 매핑에 해당 명령이 들어오면 실패한다. |
| 가산 확장이 439개 호출부의 기존 렌더를 바꿈 | P1 | 기존 `render()` 출력 무변경 회귀. `severity` 기본값이 기존 진단의 표시를 바꾸지 않음을 고정한다. |
| CLI와 hook의 recovery catalog가 갈림 | P1 | 양쪽 code/recovery id 집합과 placeholder 완전성을 대조하는 build-time oracle. |
| Codex Stop의 wire 표현이 진단 UX를 이유로 exit 2로 통일됨 | P1 | host별 wire 계약 회귀 — Stop은 rc 0 + 단일 `decision:block` JSON, reason 안에 code와 `Next:`. |
| JSON에 번역 문장·개인 경로가 새어 나감 | P1 | locale parity 테스트와 evidence 금지 필드 검사. |
| code 명명이 사이클 후반에 흔들림 | P1 | 1단계에서 inventory와 code 표를 먼저 확정하고 이후 변경은 편차로 기록한다. |
| 키가 아닌 식별자가 code로 승격됨 | P1 | 메시지 키 여부를 catalog 등재로 판정하고, 비키 4건을 명시 제외 목록으로 고정한다. |
| CLI BLOCK 범위가 규약 부재로 폭주하거나 비어 버림 | P1 | CLI 대상은 severity 선언으로 정의하고 B0 인벤토리가 명시 목록을 소유한다. |
| 사이클을 CLI로 열지 않아 결속 값이 형식만 남음 | P1 | G15로 명시하고, 형식만 맞춘 감사 레코드 생성을 금지한다. 증거는 fixture와 격리 소비 프로젝트가 진다. |

## 개발·검토 흐름

1. 같은 stem의 00~02와 승인 설계 고정 사본을 모두 읽는다.
2. source edit 전에 Phase 03을 열고 모든 acceptance ID, file owner, 검증 명령, `Document-Language: ko`를 기록한다.
3. 1단계를 구현하고 Phase 03에 파일·증거를 누적한 뒤 전체 검증을 돌려 사용자에게 보고한다.
4. 2·3단계를 같은 방식으로 이어 기록한다.
5. Phase 04는 설계 차이·coverage·acceptance evidence를 한국어로 기록하되 최종 판정을 내리지 않는다.
6. fresh-context 독립 검토가 핵심 검증을 재현하고 Phase 05를 한국어로 작성한다. 독립 리뷰는 최대 3라운드이며 각 지적은 실제 재현 후 수용 여부를 결정한다.
7. `APPROVED` 뒤 Phase 06은 `NOT READY` 또는 `READY_FOR_USER_MERGE_DECISION`을 보고한다.
8. 사용자 별도 승인 전 커밋·머지·push·태그·릴리즈를 수행하지 않는다.

## 5. Done Criteria

- [x] 기존 `Diagnostic(code, evidence, **arguments)` 시그니처가 불변이고 439개 호출부가 무변경으로 통과한다.
- [x] `severity` 기본값이 기존 진단의 렌더 출력을 바꾸지 않는다.
- [x] recovery의 소유자가 단일 매핑 테이블이며 진단 생성부가 recovery를 인자로 받지 않는다.
- [x] 모든 BLOCK code가 매핑에 존재하고, 매핑에 없는 BLOCK이 하나라도 생기면 build-time oracle이 실패한다.
- [x] 메시지 키가 아닌 `block_message`·`block_reason`·`block_release`·`block_stale`이 진단 code로 승격되지 않는다.
- [x] CLI 쪽 `Next:` 대상이 severity로 선언되며, BLOCK 대상 목록이 B0 인벤토리에 명시돼 있다.
- [x] write guard 5개 분기가 진단 code·한영 catalog·recovery를 거쳐 렌더되고 `Next:`를 가진다.
- [x] write guard 이관 후 한영 문구가 같은 code·같은 recovery id를 가진다.
- [x] 기존 CLI 오류의 exit code가 이번 사이클에서 승격·변경되지 않았다.
- [x] 스캐너 술어 확장 보류가 백로그에 등록돼 있다.
- [x] 전환 provenance(`source_phases_open`)의 legal phase 집합이 `current_phase`가 정한 연속 접두와 일치하고, 각 entry가 저장소 상대 path·canonical sha256·비음수 정수 size를 요구한다.
- [x] 그 provenance 계약을 writer·감사·게이트 셋이 같은 함수로 쓰며, 반례 행렬의 각 행이 세 경로 모두에서 거부된다.
- [x] 전환 writer가 append 전에 provenance를 디스크의 실제 문서와 대조하며, 구조만 맞는 값은 정상 API 경로로도 기록되지 않는다.
- [x] 형식 계약과 실물 검증이 분리돼 감사·게이트가 과거 기록을 디스크와 재대조하지 않고, 이 감사가 self-attested local provenance라는 경계가 문서에 명시돼 있다.
- [x] 모든 block recovery에 실행 가능한 command가 최소 한 개 존재한다.
- [x] recovery 매핑에 profile 완화·감사 삭제·generic override·destructive 명령이 기본 해법으로 등장하지 않는다.
- [x] 같은 recovery id가 서로 다른 명령을 내는 경우가 0건이다.
- [x] CLI와 hook의 code·recovery id 집합과 한영 placeholder 집합이 일치한다.
- [x] `sage/diagnostics.py`가 어떤 catalog도 import하지 않고, hook runtime이 `sage.i18n`을 import하지 않는다.
- [x] 진단 code가 `block_*` 키에서 기계 변환되지 않고 명시 매핑으로만 결정된다.
- [x] 기존 `message_key` 이름이 하나도 바뀌지 않았다.
- [x] `sage status`가 정상 로컬 저장소에서 READY/ATTENTION/BLOCKED를 읽기 전용으로 출력한다.
- [x] `status`가 네트워크에 접근하지 않고 peer CLI·build·regression command를 실행하지 않으며 불가피한 child process에 timeout이 있다.
- [x] `status`가 필수 profile·manifest를 읽지 못했을 때 READY로 낮추지 않고 BLOCK 또는 tool error로 표면화한다.
- [x] `status --json`이 schema v1이고 locale과 무관하게 byte-stable key·enum을 쓴다.
- [x] `status --json`에 번역 문장과 절대경로·vault 경로·token·환경변수 값이 없다.
- [x] 진단 순서가 `BLOCK → WARN → INFO`이고 같은 severity 안에서 code 정렬로 고정된다.
- [x] `status` exit이 0(READY·ATTENTION)·1(BLOCK 존재)·2(tool error)이고 `validate`의 STALE 전용 exit 3을 재사용하지 않는다.
- [x] collector가 `doctor.run()`·`validate.run()`을 subprocess로 호출해 stdout을 재파싱하지 않는다.
- [x] `sage explain --path`가 path risk floor, 매치 규칙, component, cycle, phase readiness, dynamic 한계를 표시한다.
- [x] `explain`의 최종 결과에 `ALLOW`가 등장하지 않는다.
- [x] `explain`이 기존 파일 내용을 읽어 content risk를 올리면 테스트가 실패한다.
- [x] `explain`이 존재하지 않는 경로도 설명하고, `..` 이탈과 경로 중간·leaf symlink를 exit 2로 거부한다.
- [x] generated asset 경로에 write guard 소유권과 canonical spec 수정 경로가 표시된다.
- [x] 추출한 helper와 gate가 같은 fixture에 같은 판정을 내리는 parity가 고정돼 있다.
- [x] `status`·`explain` 실행 전후 tracked 파일과 `.sage`의 바이트 snapshot이 동일하다.
- [x] manifest에 `runtime_api.required`가 있고 package 상수 `HOOK_RUNTIME_API = 1`과 대조된다.
- [x] `install --force`와 `generate --kind hook --write`가 marker를 stamp·보존하고 manifest schema 검증을 통과한다.
- [x] `validate`가 package API·manifest marker·generated runtime hash를 대조하고 `upgrade --check`가 API migration 필요를 표시한다.
- [x] required API가 current보다 클 때 project core import **전에** rc 2로 차단된다.
- [x] preflight를 core import 뒤로 옮기는 mutation이 테스트로 실패한다.
- [x] required/current 비교를 제거하는 mutation이 테스트로 실패한다.
- [x] runtime compatibility 오류에 traceback이 없고 실행 가능한 복구 순서가 나온다.
- [x] 1.0 manifest의 marker 누락·손상이 legacy 통과로 낮아지지 않는다.
- [x] legacy 인정이 `generator_version`이 유효한 SemVer이고 major 0일 때만 성립하며, version과 marker 동시 부재는 손상으로 처리된다.
- [x] gate·project hook은 비호환 시 rc 2, post logger·baseline은 rc 0 LOUD WARN이며 실제 write는 gate가 차단한다.
- [x] Codex Stop 비호환이 rc 0 + 단일 `decision:block` JSON이고 reason 안에 code와 `Next:`가 있다.
- [x] Claude·Codex 실제 adapter subprocess 회귀 7종이 통과한다.
- [x] 렌더된 모든 built-in BLOCK fixture에 `Next:`가 있고 INFO/WARN/OK에는 강제 Next가 붙지 않는다.
- [x] bootstrap direct BLOCK도 diagnostic renderer를 통과한다.
- [x] 한국어·영어가 같은 code, 같은 command, 같은 evidence, 같은 exit를 낸다.
- [x] `Next:` token이 한국어·영어에서 동일하게 유지된다.
- [x] `doctor`·`validate`·`upgrade`의 기존 역할과 exit contract에 회귀가 없다.
- [x] `run-all.sh`에 신규 테스트가 명시 등록되고 test inventory 완전성 검사를 통과한다.
- [x] none·Claude·Codex 환경 전체 hook suite가 통과한다.
- [x] `wheel_smoke.sh`에서 설치 wheel의 `status`·`explain`·runtime preflight가 동작한다.
- [x] `sage validate --kind all --check --schema`가 `STALE 0`으로 통과한다.
- [x] `git diff --check`가 통과하고 한영 문서 6종이 미러 상태다.
- [x] manifest와 hook runtime hash가 current다.
- [x] Obsidian 설정이 없거나 vault가 존재하지 않아도 `status`·`explain`·hook preflight 결과가 동일하다.
- [x] 세 기능의 동작이 fixture와 격리 wheel 소비 프로젝트에서 재현·검증되었고, 로컬 무증상을 증거로 쓰지 않았다.
- [x] 사후에 형식만 맞춘 감사 레코드를 만들지 않았다.
- [x] `status`의 cycle 영역이 mode를 싣고, 그 조회가 audit lock을 잡거나 파일을 만들지 않는다.
- [x] 손상·부분기록·초과크기·symlink 감사를 STANDARD로 낮추지 않는다.
- [x] `status`가 gate readiness를 수집 영역으로 싣고 `explain`과 같은 판정 함수를 쓴다.
- [x] manifest를 못 읽으면 project core를 import하기 전에 판정이 끝난다.
- [x] bootstrap·core-load·dispatch·write-guard를 포함한 모든 BLOCK이 code와 `Next:`를 낸다.
- [x] recovery id 집합이 양방향으로 대조되고 hook 쪽 명령에도 금지 규칙이 적용된다.
- [x] `explain`이 존재하지 않는 root를 `status`와 같은 판정으로 거부한다.
- [x] 한 collector의 실패가 나머지 영역의 결과를 지우지 않는다.
- [x] version 축 severity가 단일 registry에서 생성된다.
- [x] manifest 판독 실패가 built-in gate뿐 아니라 임의의 project 소유 집행 hook에서도 차단된다.
- [x] 조회의 phase readiness가 실제 gate의 Fast 면제 판정과 어긋나지 않는다.
- [x] readiness를 판정하지 못한 상태가 비차단으로 표시되지 않는다.
- [x] 다중 active run 등 semantic 감사 손상이 정상 mode로 표시되지 않는다.
- [x] runtime 직접 BLOCK도 code와 `Next:`를 낸다.
- [x] Codex Stop의 모든 차단이 stdout 단일 JSON + rc 0이다.
- [x] built-in hook 7종 × 양 host가 실제 adapter subprocess로 검증된다.
- [x] 도구 실패와 정책 차단이 다른 상태 토큰으로 나온다.
- [x] 인수 상태에 `부분`을 쓰지 않는다 — `PASS` 또는 사유 있는 `N/A`뿐이다.
- [x] 저장소의 실제 acceptance parser가 01·04의 모든 인수 행을 읽고, `acceptance_findings()`가 구조 오류 0·미해결 0을 낸다.
- [x] 조회의 Fast 면제가 게이트의 전체 검증을 통과한 state로만 성립한다.
- [x] opener 완전성 판정이 mode 조회와 감사 무결성에서 하나다.
- [x] 자동 root 탐색 실패가 두 명령 모두 exit 2다.
- [x] 동결 설계의 7 시나리오 × 2 host가 실제 subprocess로 검증된다.
- [x] recovery 모듈이 없어도 runtime 직접 BLOCK이 최소 다음 행동을 낸다.
- [x] 검사 fixture가 실제 감사 API로 opener를 만든다.

## 6. Done Criteria Revision Log

### Revision 1

- Changed-At: Phase 00
- Reason: 최초 작성.
- Affected-Phases: —
- Summary: 승인 설계 §15 Acceptance Criteria를 저장소 실측(호출부 439곳, 실제 block 메시지 키 29개, manifest top-level 13키)에 맞춰 구현 가능한 판정 항목으로 전개했다. 편차 D1~D4는 §승인 설계와의 편차에 근거와 함께 기록했다.

### Revision 2

- Changed-At: Phase 05
- Reason: 독립 검토가 재현한 반례 7건. 요구는 있으나 판정 항목이 없어 검증되지 않은 축과, 축소로 선언했던 요구가 실제로는 회피 가능했던 축이 함께 드러났다.
- Affected-Phases: 01, 03, 04
- Summary: mode 축소를 철회하고 정본 감사 모듈 안에 락 없는 읽기 API를 만들었다. gate readiness를 수집 영역으로 되살리고 `explain`과 판정 함수를 공유시켰다. manifest 판독 실패를 marker 부재와 분리해 core import 전에 닫았다. 남아 있던 네 개의 BLOCK 경로를 복구 렌더러로 수렴시키고, recovery oracle에 집합 대조와 금지 명령 검사를 넣었다. 인수 기준 18개를 추가했다(§8.1).

### Revision 3

- Changed-At: Phase 05
- Reason: 두 번째 독립 검토가 재작업 산출물에서 반례 5건을 더 재현했다. 그중 하나(project 소유 집행 hook의 fail-open)는 첫 재작업이 만든 회귀이며, 나머지는 새 코드가 기존 gate·wire 계약과 어긋난 지점이다.
- Affected-Phases: 01, 02, 03, 04
- Summary: manifest 판독 실패의 예외 목록을 닫힌 built-in 집합으로 바꿔 임의의 project 정책 hook이 통과하지 못하게 했다. 조회의 phase readiness가 게이트의 Fast 면제 판정을 그대로 쓰게 하고, 판정 실패를 BLOCK으로 올렸다. mode 판정 전에 감사의 semantic 불변식을 확인한다. runtime 직접 BLOCK 3곳을 복구 렌더러로 수렴시키고, Codex Stop의 core-load·dispatch를 host 렌더러로 보냈다. 인수 상태에서 `부분`을 제거했다 — AC28은 범위를 실증 가능한 축으로 좁혀 PASS, AC29는 7종 × 양 host 14조합 증거로 PASS, 좁히며 빠진 축은 AC80으로 분리해 사유 있는 N/A로 남겼다. 인수 기준 11개를 추가했다(OPD-AC80~90).

### Revision 4

- Changed-At: Phase 05
- Reason: 세 번째 독립 검토가 재현한 반례 6건. 가장 큰 것은 검증 자체의 결함이다 — 인수 대조를 저장소의 실제 parser가 아니라 임시 regex로 했고, 그동안 실제 parser는 92개 중 61개만 읽으면서도 오류를 내지 않았다. 보이지 않는 행은 미해결로도 잡히지 않는다.
- Affected-Phases: 01, 02, 03, 04
- Summary: 인수 표를 parser가 읽는 단일 연속 표로 합치고, 대조를 실제 `acceptance_findings()`로 바꿨다. 조회의 Fast 면제가 leaf predicate 대신 게이트의 `_fast_cycle_state` 전체 검증을 쓰게 했다. opener 완전성 판정(`opener_issues`)을 감사 모듈에 두어 조회와 무결성이 같은 판정을 쓴다. 자동 root 탐색 실패를 cwd로 대체하지 않는다. 동결 설계 §12.3의 7 시나리오 × 2 host 행렬을 별도로 만들었다. recovery 모듈 부재 시의 최소 보장을 import 경계 안으로 옮겼다. 축약 opener를 정상으로 박제하던 fixture를 실제 API 호출로 바꿨다. 인수 기준 8개를 추가했다(OPD-AC93~100).

### Revision 5

- Changed-At: Phase 05
- Reason: 네 번째 독립 검토가 재현한 반례 3건. Fast 판정 실패가 게이트의 정상 답과 같은 모양으로 접혀 문서가 다 있는 저장소에서 조용히 통과했고, opener 판정이 여전히 조회와 무결성 두 곳에 따로 있었으며, 설계 §12.3 시나리오 4의 SessionStart WARN이 구현에도 검사에도 없었다.
- Affected-Phases: 03, 04
- Summary: `ReadinessUnavailable`을 신설해 판정 실패가 "Fast가 아니다"와 구별되게 하고, `status`·`explain` 둘 다 `gate.readiness_unavailable`로 받는다. opener 판정을 `run_issues` 하나로 모아 `mode_for_stem`과 `integrity_issues`가 같은 답을 낸다. `lenses`·`plan_hash_open`을 opener 담보에 추가했다. legacy manifest에서 SessionStart만 WARN하고 나머지 hook은 그대로 통과한다. 증거 누락 이빨 검사가 중복 오류로 통과하던 것과 Phase 04의 낡은 서술도 함께 고쳤다.

### Revision 6

- Changed-At: Phase 05
- Reason: 다섯 번째 독립 검토가 재현한 반례 3건. 게이트의 답 `(state, detail)` 중 `detail`을 버려 Fast 선언이 깨진 저장소가 조회에서 통과로 보였고, 담보 완전성 술어가 필드의 존재만 봐서 빈 값이 통과했고, 도구 실패 특례를 손으로 세다가 새 code 둘이 정책 차단과 무경고로 흘러갔다.
- Affected-Phases: 03, 04
- Summary: `fast_exemption`이 `(면제, 사유)`를 돌려주고 `phase_readiness`가 그 사유를 세 번째 값으로 올려 `gate.fast_cycle_invalid`(BLOCK)로 낸다. `_absent()`로 빈 컨테이너를 없는 것으로 보고, `ts`·`epoch`·`actor`·`cycle_stem`을 opener 담보에 추가했다. `TOOL_FAILURE`를 계약 모듈의 단일 집합으로 옮기고 `cycle.mode_unavailable`을 분리해 도구 실패는 모두 ERROR/rc 2다. 인수 mutation 검사 이름을 실제 분류에 맞췄다.

### Revision 7

- Changed-At: Phase 05
- Reason: 여섯 번째 독립 검토가 재현한 반례 2건. Fast 계약이 profile 정책의 하한을 만족하는지 아무도 묻지 않아 0 round Fast가 Standard 01·02 면제를 받았고, `cycle_state` 모듈 로드 실패가 `status`에서는 정책 차단으로 분류되고 `explain`에서는 예외로 전파됐다.
- Affected-Phases: 03, 04
- Summary: `_fast_policy_floor_issue`를 게이트에 두어 `minimum_rounds`·렌즈 수를 정책 하한과 대조한다 — 문서끼리의 일치와 정책 충족은 다른 질문이다. 감사 계층도 `minimum_rounds`를 양의 정수로 요구한다. `cycle.state_unavailable`을 `TOOL_FAILURE`에 넣고, `explain`이 모듈 로드 실패를 진단으로 받으며 최후 안전망(`explain.unavailable`)이 `--json` 계약을 지킨다. Fast 차단 사유가 인용임을 문장이 밝히고, OPD-AC80과 옛 chain 감사 이행을 백로그 EH-25·EH-26으로 이관했다.

### Revision 8

- Changed-At: Phase 05
- Reason: 일곱 번째 독립 검토가 재현한 반례 2건. opener 담보 판정의 소비자를 조회·무결성 둘로 세었으나 실제로는 게이트가 셋째였고, 셋 중 게이트만 느슨해 담보 없는 opener가 Standard 01·02 면제를 받았다. `explain`의 예외 경계를 예외 class로 갈라, 같은 모듈 로드 실패가 종류에 따라 도구 실패와 프로젝트 사실로 갈렸다.
- Affected-Phases: 03, 04
- Summary: opener 담보 계약(`OPENER_REQUIRED`·`absent`·`opener_run_issues`)을 `sage/fast_cycle_contract.py`로 올려 조회·무결성·게이트 셋이 같은 함수를 쓴다 — 게이트 core는 파일을 읽지 않아 감사 모듈을 import할 수 없으므로, 정본이 모든 소비자가 닿는 곳에 있어야 했다. 게이트는 `_opener_contract_issue`로 소비하고, 계약을 부르지 못하면 통과시키지 않는다. `explain`의 경계를 연산 단위로 갈라 모듈 로드 실패는 예외 종류와 무관하게 `cycle.state_unavailable`/rc 2다. 손으로 줄인 run 상태 fixture 둘을 실제 API가 기록하는 필드로 바꿨다.

### Revision 9

- Changed-At: Phase 05
- Reason: 여덟 번째 독립 검토가 재현한 값 도메인 반례 2건. `OPENER_REQUIRED_BY_MODE.get(mode, ())`가 모르는 mode를 빈 담보 집합으로 읽어 `entry_mode`를 아무 문자열로 바꾸면 담보가 통째로 면제됐고, 렌즈 하한이 개수만 세어 정책이 선언한 적 없는 렌즈나 중복 렌즈도 하한을 만족했다.
- Affected-Phases: 03, 04
- Summary: opener 계약이 `entry_mode`를 아는 mode로 제한한다 — mode를 모르면 무엇을 담보해야 하는지도 모르므로 통과가 아니다. 렌즈 하한을 "서로 다른, 정책이 선언한" 렌즈 개수로 세고 미선언 렌즈는 따로 보고한다. 게이트 core는 adapter가 준 snapshot을 믿는 순수 함수이므로 계약이 자기가 받은 state를 검증한다. 감사 writer가 mode를 event 이름에서 유도해 위조 불가라는 사실도 검사로 고정했다.

### Revision 10

- Changed-At: Phase 05
- Reason: 아홉 번째 독립 검토가 재현한 P1. `convert_fast()`가 `{"00": {}, "01": {}}` 같은 구조 없는 provenance를 거부하지 않아, 실제 writer 경로로 만든 전환 run이 `mode_for_stem == FAST` · `integrity_issues == []` · gate `_converted_fast_state == (state, None)` · `_fast_covers_required == True`가 됐다. 전환 시점 문서의 실제 path/hash/size 근거 없이 Standard 01·02가 면제됐다. 원인은 `source_phases_open`을 빈 dict가 아닌지만 보고, gate는 dict key 집합만 본 것이다.
- Affected-Phases: 02, 03, 04
- Summary: 반례별 패치가 아니라 Fast audit state 계약을 닫는 작업으로 전환했다. provenance 구조 검증을 `sage/fast_cycle_contract.py`의 순수 계약(`expected_source_phases`·`source_phase_snapshot_issue`·`converted_provenance_issue`)으로 만들고, legal phase 집합을 `current_phase`가 정하는 연속 접두로 Phase 02 §10에 기록했다. writer(append 전 거부)·감사(UNKNOWN + integrity)·게이트(면제 거부/BLOCK) 셋이 같은 함수를 쓴다. review 스냅샷 검사도 같은 함수로 수렴시켰다. 반례 행렬 25행 × 세 경로 검사와 실제 API→감사→게이트 E2E 3건을 추가하고 인수 기준 둘(OPD-AC101·AC102)을 세웠다. Revision 9의 수정(unknown entry_mode fail-closed, declared distinct lens membership, minimum_rounds 하한, tool-failure 구분)은 그대로 유지했다.

### Revision 11

- Changed-At: Phase 05
- Reason: 열 번째 독립 검토가 재현한 P1. `{"path": ".", "sha256": "sha256:<64 hex>", "size": 0}`을 모든 required phase에 넣으면 구조 계약을 전부 통과했다 — writer append 성공 → FAST → integrity [] → gate Fast state 성공 → Standard 01·02 면제 성공. `.`은 저장소 상대 문자열이지만 phase 문서가 아니다. 구조를 검증한 것과 provenance를 검증한 것은 다르며, Phase 02가 이미 "저장소 안의 그 파일"이라고 주장하고 있었는데 계약이 그것을 배달하지 않았다.
- Affected-Phases: 02, 03, 04
- Summary: 형식 검증과 실물 검증을 두 계층으로 갈랐다. 형식은 `sage/fast_cycle_contract.py`에 남기고(경로 문법에 `.`·`./`·뒤 슬래시·빈 성분 추가, 확장자는 프로필 소관이므로 요구하지 않음), 실물 검증은 `sage/fast_cycle_sources.py`로 분리했다. `convert_fast(root, *, profile, ...)`가 append 전에 호출자 값을 디스크 snapshot과 대조하고, 다르면 쓰지 않으며 조용히 갈아치우지도 않는다 — CLI 밖의 직접 호출도 같은 문을 지난다. 감사·게이트는 디스크를 재검증하지 않는다(전환 뒤 정상 개발이 손상으로 오판되므로). 감사 JSONL 위조 위협은 막지 않고 self-attested local provenance로 명시했다(사용자 결정). 구조 반례 31행 × 세 경로 + 실물 불일치 6행 × writer 검사와 인수 기준 둘(OPD-AC103·AC104)을 추가했다. Revision 9·10의 수정은 유지했다.

### Revision 12

- Changed-At: Phase 05
- Reason: Revision 11의 provenance reader는 symlink/containment 확인 뒤 일반 `open(path)`으로 다시 경로를 따라가므로, 로컬 트리 쓰기 권한을 가진 주체가 그 짧은 사이 leaf를 외부 symlink로 교체하면 외부 바이트가 기록될 수 있다. 직접 재현은 writer append → FAST → integrity `[]`까지 확인했다.
- Affected-Phases: 02, 04, 05
- Summary: 중요도(전환 Fast 면제 계약 위반)·위험도(로컬 쓰기 권한과 정밀한 동시성 필요)·재현 빈도(일반 사용에서는 매우 낮음)를 분리해 평가했다. 사용자가 self-attested local 위협 모델의 잔여 위험으로 명시 수용했다. 계약은 안정된 로컬 파일시스템 상태에서의 snapshot 검증으로 한정하고, descriptor-bound `O_NOFOLLOW`·`fstat()` 읽기는 EH-27 후속 L3 hardening으로 이관한다. P1-02를 해소로 표기하지 않으며, Phase 06은 이 수용 기록을 참조한다.
