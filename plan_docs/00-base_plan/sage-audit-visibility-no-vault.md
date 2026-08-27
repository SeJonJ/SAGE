# [기본 계획] 통합 감사 조회와 Obsidian 비의존성

Cycle-Stem: `sage-audit-visibility-no-vault`
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 4
Status: READY
Phase03-Entry: READY (Phase 02 §10.7 — UD-1·UD-2·UD-3 확정, 2026-08-25)

## 이 문서의 잠정성 — 선행 미완 착수와 rebase 재확인 계약

이 사이클은 선행 작업 `sage-operability-diagnostics`가 **main에 병합되기 전에** 착수했다. 선행 브랜치는 착수 시점에 Phase 04까지만 진행됐고 독립 리뷰(Phase 05)와 보고(Phase 06)를 받지 않았다. 따라서 이 문서를 포함한 00~02는 **잠정 문서**다.

- 00~02의 일부 내용은 선행 병합 후 rebase 시점에 **변경될 수 있다**. 이는 결함이 아니라 이 착수 방식이 처음부터 수용한 대가다.
- 변경 가능성의 근거는 둘이다. 첫째, 실측 기준선이 `main@63cc3bd`이므로 선행이 바꾼 값은 이 문서에 반영돼 있지 않다. 둘째, 선행의 진단·복구 계약이 독립 리뷰에서 바뀌면 그 계약을 소비하는 서술도 함께 바뀐다.
- 그래서 이 사이클은 **문서 00~02까지만 선행 착수**하고 코드를 만들지 않는다. Phase 03은 rebase 이후에 연다.

### rebase 이후 재확인 목록

Phase 03을 열기 전에 00~02를 다시 읽고 아래를 대조한다. 대조 없이 "읽었다"로 넘어가지 않는다. 각 항목은 불일치 시 해당 문서를 고친 뒤 진행하며, 고친 내용은 Done Criteria Revision Log에 남긴다.

| # | 대조 대상 | 이 문서의 현재 값 | 불일치 시 |
|:-:|---|---|---|
| R1 | CLI 서브커맨드 수 | 21개 (`sage/cli.py:21-23`) | §3 영향 분석의 고정 경계 문구를 갱신 |
| R2 | `sage/i18n/{ko,en}.py` 줄 수 | ko 1,438 · en 1,421 | §0 사전 지식 실측 행을 갱신 |
| R3 | `asset_paths.hook_runtime_files()` 추적 목록 | 선행이 2개 추가 예정 (`path_risk.py`·`recovery.py`) | 01 §6 파일 소유권과 §4 G7의 등록 대상을 갱신 |
| R4 | 진단 계약의 최종 형태 | `Diagnostic`에 `severity` 가산 + 단일 recovery 매핑 테이블 | §4 G8·02 §6의 재사용 서술을 실제 시그니처에 맞춤 |
| R5 | 복구 완전성 oracle의 판정 범위 | `sage/i18n/validation.py`가 BLOCK의 recovery 누락·파괴적 명령·순서 위반을 검사 | 01 §8 인수 기준의 `audit show` 오류 표면 항목을 갱신 |
| R6 | 감사 source 모듈 6종의 무변경 | 선행이 하나도 건드리지 않음 | 건드렸다면 §0 실측과 02 §3 추출 대상을 전면 재확인 |

R6가 깨지면 이 사이클의 전제 자체가 바뀐다. 나머지는 서술 갱신으로 흡수된다.

### rebase 재확인 결과 (2026-08-25, `main@3f34902`)

선행이 `3f34902`로 병합된 뒤 위 여섯을 실측 대조했다.

| # | 결과 | 실측값과 처리 |
|:-:|:-:|---|
| R1 | 불일치 | 서브커맨드 21 → **23**(`status`·`explain` 추가). §3 고정 경계 문구를 갱신했다. 이 사이클이 `audit`을 더해 24가 된다. |
| R2 | 불일치 | `ko.py` 1,438 → **1,514** · `en.py` 1,421 → **1,497**. §0 실측 행을 갱신했다. |
| R3 | 일치 | `asset_paths.hook_runtime_files()`가 `path_risk.py`·`recovery.py` 둘 다 추적한다. 01 §6과 G7의 등록 대상은 그대로다. |
| R4 | 불일치 | 계약 이름이 `Diagnostic`이 아니라 **`Finding`**이고, `severity`는 가산 필드가 아니라 code에서 파생되는 property다(`SEVERITY`·`RECOVERY` 두 표). G8과 02 §6의 재사용 서술을 실제 시그니처에 맞췄다. |
| R5 | 보강 | `sage/i18n/validation.py::recovery_issues()`가 BLOCK의 recovery 누락·금지 명령·**CLI↔hook 양쪽 표의 recovery id 대칭**까지 검사한다. 이 사이클이 추가하는 BLOCK code는 CLI `RECOVERY`에 기존 step id만으로 순서를 가져야 한다. |
| R6 | **깨짐** | 선행이 `loop_audit.py`(+47)·`fast_cycle_audit.py`(+166/−28)를 바꿨다. 아래에 따로 적는다. |

**R6가 깨진 내용은 충돌이 아니라 설계 전제의 변경이다.** 선행이 이 사이클이 만들려던 것을 먼저 만들었고, 동시에 이 사이클의 설계 하나를 명시적으로 반대하는 계약을 병합했다.

| 선행이 만든 것 | 이 사이클에 미치는 영향 |
|---|---|
| `loop_audit._read_status_unlocked(path, max_bytes)` — 락을 잡지 않는 조회 전용 읽기, 4MB 상한, `absent`·`valid`·`damaged` 반환 | D2의 bounded lock을 대체한다. viewer는 이 경로를 쓴다 |
| `fast_cycle_audit.summarize_records(records, file_issues)` — 순수 접기 함수 | §3.2의 경계 정리가 fast 쪽은 이미 끝났다. loop·acceptance만 남는다 |
| `fast_cycle_audit.snapshot(root)` — 락 없는 조회 API | source adapter가 그대로 소비한다 |
| `sage/commands/status.py` — `Finding`·`order`·`TOOL_FAILURE`·`SCHEMA_VERSION`·`--json`·exit 집계 | `audit show`가 따라야 할 표현 층 선례다. 새 양식을 만들지 않는다 |

`_read_status_unlocked`가 달고 있는 계약 문언이 D2를 직접 반박한다 — "락 경로는 `.sage/`와 `.lock` 파일을 **만든다** — 쓰기다. 읽기만 하겠다고 약속한 명령이 그걸 부르면 약속을 깬다." D2는 폐기하고 D3으로 대체한다.

## 0. 사전 지식

| 구분 | 근거 | 핵심 내용 |
|---|---|---|
| 승인 설계 | 위키 노트 `SAGE - 통합 감사와 Obsidian 선택성 설계 (26.08.13)` | 새 감사 파일 없이 기존 `.sage/*.jsonl`을 읽는 투영 계층 `sage audit show`를 만들고, source별 무결성 보증 차이를 정직하게 표시하며, Obsidian 비의존성을 격리 Golden E2E로 고정한다. |
| 사용자 결정 | 2026-08-24 착수 대화 | 설계 정본은 위키 노트가 소유한다. 저장소에 `docs/superpowers/specs/` 고정 사본을 만들지 않는다. `plan_docs`는 이번 사이클의 실행 증거만 소유한다. |
| 사용자 결정 | 2026-08-24 착수 대화 | 이 사이클은 SAGE CLI로 사이클을 열지 않는다. phase 문서는 같은 구조로 수동 작성한다. 추출 대상인 감사 writer가 이 저장소 자신의 리뷰 루프가 기록하는 모듈이기 때문이다. |
| 사용자 결정 | 2026-08-24 착수 대화 | 선행 병합 전에는 문서 00~02까지만 작성한다. Phase 03과 코드는 rebase 이후에 시작한다. |
| 선행 작업 (충족) | `sage-fast-cycle-usability-hardening` (PR #7, `63cc3bd`) | Fast Cycle 전환·조기완료 감사 이벤트가 main에 있다. 설계 §11.2 시나리오 4의 전제가 이미 성립한다. |
| 선행 작업 (충족) | `sage-operability-diagnostics`, `main@3f34902` (PR #8) | **병합 완료.** 진단 code·`RecoveryStep`·`Next:` 계약과 복구 완전성 oracle을 소유한다. 계약 정본은 `sage/diagnostic_contract.py`이고 진단 한 건은 `Finding`이다. 이 사이클의 CLI 오류 표면이 이것을 소비한다. |
| 구현 기준점 | `main@3f34902` | 브랜치 `feat/sage-audit-visibility-no-vault`가 이 커밋 위로 rebase됐다. 문서 00~02의 최초 실측은 `main@63cc3bd` 기준이었고, 달라진 값은 위 재확인 결과 표가 소유한다. |
| 선행과의 파일 교집합 | 2026-08-25 rebase 후 실측 | 선행이 바꾼 61개 파일 중 감사 source 모듈은 **2개**다 — `loop_audit.py`·`fast_cycle_audit.py`. `override_audit.py`·`retro_audit.py`·`acceptance_waiver.py`·`commands/*`는 무변경이다. |
| 감사 source 실측 | 2026-08-25 rebase 후 실측 | `loop_audit.py` 674줄 · `fast_cycle_audit.py` 462줄 · `override_audit.py` 426줄 · `retro_audit.py` 154줄 · `acceptance_waiver.py` 346줄 · `feedback.py` 241줄. |
| 추출 출발점 실측 | `loop_audit.py`·`fast_cycle_audit.py` | 양쪽 모두 `read_records()`·`audit_summary()`·`integrity_issues()`를 대칭으로 갖고, `loop_audit`에는 `_chain_states(records)`·`_parse_bytes(data)`가 분리돼 있다. `fast_cycle_audit`는 선행이 `summarize_records(records, file_issues)`로 접기를 이미 떼어냈다. 설계 §8.2의 pure 추출은 신규 작성이 아니라 **경계 정리**이고, 남은 대상은 `loop_audit`·`acceptance_waiver` 둘이다. |
| override 이중 기록 | `override_audit.py:326-327,346-347` | `grant`·`revoke`는 `.sage/override.jsonl`(추적·커밋)과 state home의 `grants/<root_key>.jsonl`(집행·로컬) **양쪽에** append된다. `bypass`와 cycle stem 선언은 추적본에만 간다. 집행 정본은 로컬이며 저장소 트리 안이면 fail-closed다(`grants_path`). |
| 감사 lock 실측 | `loop_audit.py` `_audit_lock` · `_read_status_unlocked` | `_audit_lock`은 `fcntl.flock(LOCK_EX)` / `msvcrt.locking(LK_LOCK)`을 **timeout 없이 무기한 blocking**으로 걸고, 부수적으로 `.sage/`와 `.lock` 파일을 **만든다**. 선행이 그 옆에 `_read_status_unlocked`를 두어 락 없는 조회 경로를 정본화했다. viewer는 후자만 쓴다(D3). |
| 진단 격리 실측 | `override_audit.py:58` `_diagnostic` | hook runtime 모듈은 `sage.diagnostics`를 import할 수 없어 같은 모양의 plain dict를 올린다. 엔진 없이 소비 프로젝트에서 단독 실행되어야 하기 때문이다. 설계 §12-6의 "재사용하되 결합하지 않는다"가 이 제약의 다른 표현이다. |
| ARTIFACTS 문구 실측 | `docs/ARTIFACTS.md:13` | "**Obsidian 미사용 시 `.sage`, 사용 시 vault**" 문구가 실재한다. 설계 §10.3이 지목한 대상이며 영어 미러 `docs/ARTIFACTS.en.md`가 함께 있다. |
| 감사 파일 등재 실측 | `docs/ARTIFACTS.md:21` | 공유 4종(`override`·`acceptance-waivers`·`loop_audit`·`fast_cycle`)과 로컬 목록(`retro_audit.jsonl`·`plan_interview.md`·`knowledge_scan.md`·`tmp/`·`context/`)이 명시돼 있다. **`feedback.jsonl`은 어느 쪽에도 등재돼 있지 않다.** |
| Golden E2E 공백 실측 | `test_golden_instance_e2e.py` | 180줄, 테스트 7개다. install→generate→validate→shim 실행까지만 덮고 review loop·Fast·retro·feedback·knowledge·감사 조회는 한 흐름에서 검증하지 않는다. 설계 §2.3의 8개 공백이 실측으로 확인된다. |
| 검증 환경 경계 | `sage._resources.is_engine_source_tree` | 이 저장소는 엔진 소스 트리라 자기 게이트가 돌지 않는다. no-vault 보장과 `audit show`의 실제 판정은 fixture와 격리 wheel 소비 프로젝트에서만 판정된다. |

## 1. 목표

사용자가 감사 이력을 한 명령으로 보게 하되, 그 화면이 실제보다 강한 보증을 하지 않게 만든다. 그리고 Obsidian이 없는 환경이 있는 환경과 같은 거버넌스 결과를 갖게 한다. 목표는 다음 네 가지다.

1. 기존 `.sage` 감사 정본을 읽기 전용으로 조회하는 단일 명령을 만들되, 새 정본이나 새 authority를 만들지 않는다.
2. source마다 다른 무결성 보증 수준을 하나의 `verified`로 뭉개지 않고 두 축으로 정직하게 표시한다.
3. 개인정보가 담길 수 있는 로컬 감사를 기본 조회에서 제외하고, 절대경로를 어떤 출력에도 싣지 않는다.
4. Obsidian vault·앱·플러그인·MCP가 없어도 PDCA와 감사가 동작함을 격리 환경 Golden E2E로 고정한다.

종료 상태는 정확히 다음 중 하나다.

- `NOT READY`: 필수 인수 항목이 하나 이상 해결되지 않았다.
- `READY_FOR_USER_MERGE_DECISION`: 구현과 검증은 통과했지만 커밋·머지·push·릴리즈는 수행하지 않았다.

## 2. 범위

### 2.1 포함

- 읽기 전용 `sage audit show [--json]`과 6개 감사 source adapter.
- source별 `integrity.method`(`strict_chain`·`semantic`·`structural`·`none`)와 `integrity.status`(`valid`·`invalid`·`legacy`·`unreadable`·`not_applicable`) 2축 표시.
- 공유 4종 기본 조회와 로컬 2종의 `--include-local` 명시 노출 경계.
- `--source`·`--cycle-stem`·`--run-id`·`--limit`·`--root` 필터와 bounded 출력, truncation 표시.
- 언어 중립 JSON schema v1, 이벤트 envelope, source별 `data` allowlist.
- symlink 거부·크기 상한·동시 append 재시도를 포함하고 **락을 잡지 않는** 안전한 snapshot read.
- 기존 writer/gate가 쓰는 검증 로직의 pure `bytes/records -> summary` 경계 정리와 golden fixture parity.
- retro 절대경로 비노출과 저장소 상대경로 검증을 통과한 값만 표시하는 redaction.
- Git 추적 상태 읽기 전용 probe와 정책 불일치 안내.
- Obsidian 네 상태 계약과 `docs/ARTIFACTS.md` 한영 문구 정정.
- 격리 wheel 소비 프로젝트의 no-vault Golden E2E 12개 시나리오와 별도 degraded 시나리오.
- README·quickstart·CLI reference·ARTIFACTS·ARCHITECTURE 한영 갱신.

### 2.2 제외

- 새 `.sage/audit.jsonl` 생성과 기존 로그의 이중 쓰기.
- 기존 JSONL의 migration·rewrite·rehash.
- `override`·`acceptance`·`retro`의 공통 무결성 강화. 이는 백로그 EH-8이 소유한다.
- 감사 로그를 새로운 write·Stop·서버 authority로 사용하는 것.
- Obsidian dashboard 통합 화면 신설과 앱·플러그인·MCP 설치·탐지.
- retro 절대경로를 portable 경로로 변환하는 것.
- `feedback.jsonl`의 자동 Git 추적 또는 기존 파일 자동 untrack.
- `.claude`·`.codex`의 `logs/session-*.jsonl` 세션 telemetry 통합.
- authority attestation artifact 통합.
- 감사를 이유로 cycle 완료 상태를 바꾸는 자동 복구.
- override 집행 정본(state home `grants/*.jsonl`)의 조회. 편차 D1 참조.
- 기존 감사 writer의 함수 시그니처·append bytes 변경.
- 커밋·머지·push·태그·릴리즈.

## 3. 영향 분석

| 영역 | 변경 | 고정 경계 |
|---|---|---|
| `loop_audit.py`·`fast_cycle_audit.py` | 검증 로직의 pure 경계 정리 | 기존 함수 시그니처와 append되는 bytes는 불변이다. writer·gate의 판정 결과가 바뀌면 실패다. |
| `override_audit.py`·`retro_audit.py` | 읽기 경로 재사용만 | 집행 경로(`grants_path`)와 state home 판정에 손대지 않는다. |
| `acceptance_waiver.py`·`feedback.py` | 의미 검증 결과의 조회 노출 | 기존 검증 어휘와 exit 계약은 유지한다. |
| 신규 `audit show` | 조회·렌더만 수행 | 새 권한 판정기가 되지 않는다. 감사 파일을 생성·수정·정리하지 않는다. |
| `sage/cli.py` | `audit` 등록 | 기존 **23개** 서브커맨드의 인자·exit는 불변이다(R1 재확인 완료). 등록 후 24개가 된다. |
| CLI catalog | `audit` 문구 key 추가 | 기존 판정 어휘와 도메인 경계는 유지한다. |
| hook catalog | 변경 없음 | hook runtime은 `sage.i18n`을 import하지 않는다. 이 경계를 조회 기능을 이유로 열지 않는다. |
| `docs/ARTIFACTS.md`(+`.en`) | 정본·파생 뷰 문구 정정, feedback 로컬 정책 등재 | 공유 4종·로컬 목록의 기존 판정은 바꾸지 않는다. 문구만 정정한다. |
| Golden E2E | 격리 소비 프로젝트 시나리오 확장 | 기존 7개 테스트의 판정은 불변이다. |

## 4. 전역 불변 조건

### G1. 새 감사 정본을 만들지 않는다

`audit show`는 기존 파일을 읽기만 한다. `.sage/audit.jsonl` 같은 통합 파일을 만들지 않고, 조회 결과를 어디에도 캐시하지 않는다. "통합"은 저장소 통합이 아니라 조회 경험 통합이다.

### G2. 읽기 전용은 읽기 전용이다

명령 실행 전후로 모든 감사 파일의 bytes가 동일하다. 파일을 생성·수정·정리하지 않고, 손상된 줄을 고치지 않으며, 조회 실패가 writer의 원문을 rollback하거나 truncate하지 않는다.

### G3. 보증을 올려 표시하지 않는다

`integrity.method`는 해당 source가 실제로 하는 검증만 말한다. hash-chain이 없는 source를 파싱 성공했다는 이유로 `valid`로 올리지 않고, chain 필드가 없는 과거 run을 실패로 속이지도 않는다(`legacy`). 보증 수준을 올리는 것은 EH-8의 일이며 이 사이클의 일이 아니다.

### G4. 조회는 게이트 의미론을 바꾸지 않는다

viewer가 `invalid`를 발견해도 기존 hook 판정 코드가 새로 차단하도록 바뀌지 않는다. 반대로 기존 hook이 fail-closed하는 source를 viewer가 WARN으로 낮추지도 않는다. 조회는 조회다.

### G5. parser를 두 벌 만들지 않는다

review·fast·acceptance는 기존 검증 로직을 재사용한다. viewer용 정규식이나 간소 parser를 새로 만들지 않는다. pure 경계 정리 전후로 golden fixture summary가 byte-for-byte 같아야 한다. 이 등가성이 깨지면 추출이 아니라 재작성이다.

### G6. 개인 데이터는 명시해야 나온다

`retro`와 `feedback`은 기본 조회에서 제외된다. `--include-local`은 해당 터미널 출력에만 영향을 주며 Git 추적 상태를 바꾸지 않는다. 조회 편의를 이유로 공유 범위를 조용히 넓히지 않는다.

### G7. 절대경로는 어떤 출력에도 없다

retro의 `note_path`, vault 경로, HOME, state home은 text와 JSON 어디에도 싣지 않는다. 예외 메시지에도 싣지 않는다. 대체 정보는 boolean과 저장소 상대경로뿐이다. 경로 필드가 절대경로·`..`·root 이탈이면 값을 숨기고 issue로 표시한다.

경로 필드 검증만으로는 이 보장이 성립하지 않는다. allowlist에는 `reason`·`scope`·`remaining_evidence`·`note`·`marker_text` 같은 **자유 문자열**이 있고 사용자가 여기에 절대경로를 직접 입력할 수 있다. 특히 retro의 `reason`은 이 source가 로컬로 분류된 사유(vault 절대경로)와 같은 자리에 있다. 따라서 출력 직전 **모든 문자열 값**이 공통 sanitizer를 통과한다. sanitizer는 절대 경로 토큰(POSIX `/`, Windows drive, `~`, UNC)을 치환하고 치환 사실을 issue로 남긴다. 필드별 예외를 두지 않는다.

### G8. hook은 엔진 없이 돈다

공통 조회를 이유로 hook runtime이 CLI i18n package나 `sage.diagnostics`를 import하게 만들지 않는다. 진단 계약 정본(`sage/diagnostic_contract.py`의 `Finding`·`SEVERITY`·`RECOVERY`)은 **표현 층에서만** 소비한다. pure parser·summary 모듈은 `fcntl`·`msvcrt`를 import하지 않고, viewer 경로는 어느 층에서도 lock을 걸지 않는다(D3).

### G9. JSON은 언어를 타지 않는다

최상위 key와 enum은 영어 고정이며 `--lang`에 따라 바뀌지 않는다. 안정 계약은 `summary_code`뿐이고 자연어 문장은 renderer가 catalog에서 만든다. 한국어와 영어 JSON은 byte 동일하다.

### G10. 원본 record를 그대로 흘리지 않는다

`data`는 source별 allowlist만 허용한다. review의 raw `cfg`, 전체 profile, host payload는 출력하지 않는다. unknown event는 버리지 않되 제한된 envelope로만 표시하고 WARN을 남긴다.

### G11. 부분 snapshot을 정상으로 표시하지 않는다

읽기 전후 file identity와 size가 바뀌면 한 번만 재시도하고, 그래도 append 중이면 실패한다. 마지막 줄이 불완전할 때 진행 중인 append인지 손상인지 추측해 skip하지 않는다.

### G12. 조회는 기다리지 않는다

viewer는 어떤 source에도 lock을 걸지 않고 lock 파일을 만들지도 않는다. 그래서 기다릴 일 자체가 없다. 대신 락 없이 읽었기 때문에 볼 수 있는 상태 — `absent`·`damaged`·부분 append — 를 정상으로 접지 않고 읽기 실패 의미로 표면화한다. 무기한 blocking lock(`_audit_lock`)을 viewer에서 호출하지 않는다.

### G13. Git 상태는 읽기만 한다

추적 정책과 실제 상태가 달라도 안내만 한다. 자동 `git add`, `git rm --cached`, `.gitignore` 수정을 하지 않는다. Git 저장소가 아니거나 probe가 실패하면 `unavailable`로 낮추고 감사 조회는 계속한다.

### G14. vault는 정본이 아니다

`audit show`는 profile의 `vault_path`를 읽을 이유가 없고 vault에 쓰지 않는다. vault dashboard를 삭제해도 조회 결과는 달라지지 않는다. vault가 존재해도 감사 authority는 `.sage` source에 남는다.

### G15. 자동 파생물 실패가 core를 되돌리지 않는다

자동 dashboard·write-back 실패는 이미 성공한 감사 close를 rollback하지 않고 WARN에 그친다. 반대로 사용자가 명시적으로 요구한 `--vault` 출력의 실패는 nonzero다. 실패를 N/A로 숨기지 않는다.

### G16. 이 저장소에서 안 막히는 것은 증거가 아니다

엔진 소스 트리에서는 자기 게이트가 실행되지 않는다. no-vault 보장과 조회 동작은 fixture와 격리 wheel 소비 프로젝트에서 재현·검증하며, "로컬에서 잘 돈다"를 증거로 사용하지 않는다.

### G17. 이번 사이클은 로컬 게이트 증거를 갖지 않는다

SAGE CLI로 사이클을 열지 않으므로 cycle 결속은 문서 규약으로만 유지되고 엔진이 검증하지 않는다. 사후에 형식만 맞춘 감사 레코드를 만들어 통과한 것처럼 보이게 하지 않는다.

## 승인 설계와의 편차

승인 설계는 저장소를 실측하기 전에 작성됐다. 착수 시점 실측에서 설계 문언을 그대로 따르면 설계 자신이 세운 계약이 깨지는 자리가 둘 나왔고, rebase 이후 그중 하나가 다시 바뀌었다. 각 편차는 무엇이 문제였고 무엇을 바꿨는지, 설계 의도를 무엇으로 대신 지키는지를 함께 기록한다.

### D1. override는 공유 파일 한 줄이 아니라 이중 기록이다

**설계 문언:** §2.1 표가 `override`를 `.sage/override.jsonl` 공유 한 줄로 적고, §9.1이 이를 공유 감사로 분류한다.

**실측:** `grant`·`revoke`는 `.sage/override.jsonl`(추적·커밋)과 state home의 `grants/<root_key>.jsonl`(집행·로컬) 양쪽에 append된다. `bypass`와 cycle stem 선언은 추적본에만 간다. 집행 정본은 저장소 트리 밖에 있어야 하며 안이면 fail-closed다.

**문제:** 설계대로 `.sage/override.jsonl`만 읽으면 화면은 "override 감사"라고 말하지만 실제로는 **집행 정본이 아닌 추적 사본**을 보여준다. 두 파일은 갈릴 수 있다 — revoke는 집행을 먼저 하고 추적을 나중에 기록하므로 그 사이 중단되면 집행됐지만 추적에 없는 상태가 남는다.

**바꾼 것:** 조회 대상은 추적본으로 유지하되, source 상태에 **이것이 추적 사본이고 집행 정본은 로컬 state home에 있다**는 사실을 명시한다. 집행 정본 조회는 범위에서 제외한다(§2.2). 로컬 state home을 조회 대상에 넣으면 G7의 절대경로 비노출과 충돌하고, 머신마다 다른 값을 공유 감사처럼 보이게 만든다.

**설계 의도를 지키는 방법:** "실제보다 강한 보증을 하지 않는다"가 설계의 핵심이다. 추적본을 집행 정본처럼 보이게 두는 것이 바로 그 위반이므로, 이 편차는 설계 의도를 어기는 것이 아니라 실측에 맞춰 지키는 것이다.

### D2. 5초 bounded 대기는 기존 lock 함수로 만들 수 없다 — **D3으로 대체됨 (2026-08-25)**

**설계 문언:** §8.1-9가 "writer lock을 함께 쓰는 source도 최대 5초만 기다린다", §8.3이 "현재 무기한 blocking lock을 viewer에서 그대로 호출하지 않는다"고 적는다.

**실측:** `_audit_lock`은 `fcntl.flock(fd, LOCK_EX)` / `msvcrt.locking(fd, LK_LOCK, 1)`을 timeout 인자 없이 건다. 두 호출 모두 무기한 blocking이며 이 함수에는 non-blocking 변형이 없다.

**문제:** 설계가 "그대로 호출하지 않는다"고만 적어 무엇을 대신 쓸지가 비어 있다. 이 자리를 비워두면 구현자가 writer lock을 우회해 lock 없이 읽거나, 반대로 무기한 대기를 그대로 상속한다.

**바꾼 것:** viewer 전용 bounded snapshot helper를 별도로 둔다. `LOCK_EX | LOCK_NB`(POSIX) / `LK_NBLCK`(Windows)로 시도하고 실패 시 짧은 간격으로 재시도하며 5초 총 상한을 둔다. 상한 초과는 lock을 훔치지 않고 진단 code로 실패한다. G8에 따라 이 helper는 pure parser 모듈이 아니라 snapshot 경계에 둔다.

**설계 의도를 지키는 방법:** 설계가 금지한 것은 "무기한 대기"와 "writer lock 무시" 둘 다다. 양쪽을 피하는 유일한 방법이 bounded 시도이므로 이는 설계의 구체화다.

**폐기 사유:** 이 편차는 "lock을 얻지 못했다고 lock 없이 읽는 경로를 만들지 않는다"를 전제로 했다. 선행이 그 전제를 뒤집었다 — 조회가 lock을 잡는 행위 자체가 쓰기이므로 읽기 전용 계약 위반이라는 것이다. D3이 이 자리를 대신한다.

### D3. 조회 경로는 lock을 만들지도 잡지도 않는다

**설계 문언:** §8.1-9가 "writer lock을 함께 쓰는 source도 최대 5초만 기다린다", §8.3이 "현재 무기한 blocking lock을 viewer에서 그대로 호출하지 않는다"고 적는다. D2는 이를 bounded 시도로 구체화했다.

**실측:** 선행이 `loop_audit._read_status_unlocked`를 병합하면서 반대 방향의 계약을 정본으로 세웠다. `_audit_lock`은 `.sage/` 디렉터리와 `.lock` 파일을 **생성**한다 — 읽기만 하겠다고 약속한 명령이 그 함수를 부르면 그 순간 약속이 깨진다. 얻는 lock이 bounded인지 unbounded인지와 무관한 문제다. `fast_cycle_audit.snapshot(root)`도 같은 이유로 lock 없이 읽고, `sage status`가 그 경로를 쓴다.

**문제:** D2를 그대로 구현하면 `audit show`가 `.sage/*.lock` 파일을 만든다. 이는 G2(읽기 전용은 읽기 전용이다)와 §10.0-3(원본을 건드리지 않는다)의 직접 위반이며, 사용자가 조회 한 번으로 프로젝트 트리에 파일을 남기게 된다. bounded 대기는 이 문제를 전혀 줄이지 않는다.

**바꾼 것:** viewer는 **lock을 생성하지도 획득하지도 않는다.** `audit_sources`의 secure snapshot이 `lstat` → 안전 open → identity·size 확인 → 읽기 → 재확인의 순서로 읽고, 변화가 있으면 한 번만 재시도한 뒤 `audit.source.concurrent_change`로 실패한다. `audit.source.lock_timeout` code는 만들지 않는다.

**락이 없어서 보이는 상태를 접지 않는다.** `absent`·`damaged`·부분 append는 각각 다른 사실이고, 어느 것도 "기록이 없다"나 "정상이다"로 접히지 않는다. `absent`는 exit 기여 없음, `damaged`와 부분 append는 exit 1이다. 부재를 안전 방향으로 읽는 것이 선행이 반복해서 막은 실패 양식이고, 락을 없앤 대가로 이 구분이 더 중요해진다.

**설계 의도를 지키는 방법:** 설계가 지키려던 것은 "조회가 끝난다"와 "부분 상태를 정상으로 표시하지 않는다" 둘이다. 락을 아예 잡지 않으면 첫째는 자명하게 성립하고, 둘째는 identity·size 재확인과 상태 3분기가 대신 진다. 설계가 lock을 요구한 이유였던 일관성은 이 사이클이 애초에 보장할 수 없는 것이었다 — 여섯 source에 걸친 교차 시점 일관성은 source별 lock으로 얻어지지 않는다.

## 구현 순서

이 사이클은 선행 병합을 경계로 두 구간으로 끊는다.

**선행 병합 전 — 문서 구간 (현재 구간)**

1. 00~02 문서를 작성한다.
2. 코드·테스트·fixture를 만들지 않는다.

**선행 병합 후 — 구현 구간**

3. rebase하고 위 재확인 목록 R1~R6를 대조한 뒤 필요한 문서를 고친다.
4. Phase 03을 열고 acceptance ID·file owner·검증 명령을 기록한다.
5. 기존 6개 source parser의 golden fixture를 먼저 확보한다.
6. pure 경계를 정리하고 fixture parity를 고정한다.
7. normalized model과 lock 없는 secure snapshot을 구현한다.
8. `audit show`의 human·JSON renderer와 exit 계약을 구현한다.
9. local source 경계·redaction·tracking probe를 구현한다.
10. no-vault Golden E2E를 구현한다.
11. 한영 문서·catalog를 갱신하고 manifest·hook runtime hash를 재스탬프한다.
12. 전체 suite와 wheel smoke를 돌리고 독립 리뷰를 최대 3라운드 받는다.

## 주요 위험과 통제

| 위험 | 등급 | 통제 |
|---|:---:|---|
| pure 경계 정리가 writer·gate 판정을 바꿈 | P0 | 정리 전후 golden fixture summary의 byte 동일성 검사. 다르면 실패한다. |
| viewer가 감사 파일을 수정·정리함 | P0 | 명령 전후 모든 감사 파일 bytes snapshot 동일성 검사. |
| 보증 없는 source가 `valid`로 표시됨 | P0 | source별 `method` 고정 테스트. override·feedback에 `valid`가 나오면 실패한다. |
| retro 절대경로·vault 경로가 출력에 샘 | P0 | text·JSON 전수 검사에서 절대경로 0건. redaction 제거 시 실패하는 이빨. |
| 로컬 source가 기본 출력에 나옴 | P0 | 기본 출력에 retro·feedback 이벤트 0건 검사. |
| 원본 record가 allowlist를 우회해 흘러나옴 | P0 | allowlist 밖 key 0건 검사. |
| viewer가 lock 파일을 만들거나 writer lock을 기다림 | P0 | 실행 전후 `.sage/` 파일 목록 동일 검사와, 살아 있는 writer lock 보유 상태에서 조회가 대기 없이 끝나는 회귀. |
| 추적 사본을 집행 정본처럼 표시함 | P1 | D1의 source 상태 명시를 인수 기준으로 고정한다. |
| 부분 snapshot을 정상으로 오인함 | P1 | append 진행 중 fixture에서 재시도 후 안정 실패 검사. |
| ko·en JSON이 갈림 | P1 | locale parity byte 비교. |
| Golden E2E가 vault 밖에 씀 | P1 | 소비 프로젝트·상태 홈 밖 sentinel tree의 before·after hash 대조. |
| 정상 OFF와 설정 오류를 같은 테스트로 뭉갬 | P1 | 두 시나리오를 분리해 각각 기대 exit를 고정한다. |
| pure 모듈이 플랫폼 lock을 import해 Windows viewer가 죽음 | P1 | pure 모듈의 `fcntl`·`msvcrt` import 금지 검사. |
| rebase 후 문서와 실제가 갈린 채 03이 진행됨 | P1 | R1~R6 재확인 목록을 Phase 03 시작 체크리스트의 선행 조건으로 둔다. |
| 사이클을 CLI로 열지 않아 결속 값이 형식만 남음 | P1 | G17로 명시하고 형식만 맞춘 감사 레코드 생성을 금지한다. |

## 개발·검토 흐름

1. 같은 stem의 00~02와 위키 설계 정본을 모두 읽는다. 저장소에는 설계 고정 사본이 없으므로 정본은 위키 노트다.
2. rebase 이후 R1~R6를 대조하고 필요한 문서를 고친 뒤 Revision Log에 남긴다.
3. source edit 전에 Phase 03을 열고 모든 acceptance ID, file owner, 검증 명령, `Document-Language: ko`를 기록한다.
4. 구현 구간을 순서대로 진행하며 Phase 03에 파일·증거를 누적한다.
5. Phase 04는 설계 차이·coverage·acceptance evidence를 한국어로 기록하되 최종 판정을 내리지 않는다.
6. fresh-context 독립 검토가 핵심 검증을 재현하고 Phase 05를 한국어로 작성한다. 최대 3라운드이며 각 지적은 실제 재현 후 수용 여부를 결정한다.
7. `APPROVED` 뒤 Phase 06은 `NOT READY` 또는 `READY_FOR_USER_MERGE_DECISION`을 보고한다.
8. 사용자 별도 승인 전 커밋·머지·push·태그·릴리즈를 수행하지 않는다.

## 5. Done Criteria

**해소 근거 (2026-08-26).** 아래 74항목을 표시만 바꾸지 않고 항목별 증거를 대조해 해소했다. 항목 ↔ 검사 매핑의 정본은 `plan_docs/04-analyze/` §4.1(AVN-AC01~34)과 §4.4(CE-1~CE-10)이며, 재현 명령과 결과는 §6에 있다. 04 문서는 gitignore 대상이라 브랜치를 따라가지 않으므로, 검증을 다시 돌릴 사람은 §6의 명령 목록을 그대로 실행하면 된다.

표시하면서 **넓혀 읽히면 안 되는 것 둘**을 여기 남긴다.

- AVN-AC23의 `feedback`·`knowledge`는 이제 **직접 실행**으로 확인된다. `wheel_smoke.sh` `[11/11]`이 순수 wheel 소비자에서 임시 `HOME`·`XDG_STATE_HOME`·`SAGE_STATE_HOME`·`CODEX_HOME`을 세우고 vault 환경변수를 지운 채, 마커 스캔 → 기록 → `audit show` 재조회와 `vault_path: ""`의 `n/a` 보고서까지 돌린다. 경계 밖 sentinel 해시 무변경과 격리 경계 전체의 vault 산출물 0건을 함께 잰다(04 §4.1).
- 잔여 위험은 2026-08-27 사용자 승인으로 전부 닫혔다. RA-1~RA-6은 P2 수용이고, Phase 05에서 등재된 **RA-7은 severity P1**이라 "P0·P1 수용 불가"의 **단일 예외**로 따로 수용됐다(백로그 EH-28, 승인자 사용자(SeJon)). 선택 결정 UD-4·UD-5도 (a)로 확정됐다. **수용이지 해소가 아니다** — RA-7의 동작은 그대로이고 검사 셋이 그것을 못박고 있다(02 §10.4).

### 조회와 무결성 표시

- [x] 새 통합 감사 파일 없이 기존 공유 4종이 한 명령에서 보인다.
- [x] `--include-local`에서만 retro·feedback이 보이고 기본 출력에는 0건이다.
- [x] `--source retro`·`--source feedback`을 `--include-local` 없이 주면 exit 2와 안내가 나온다.
- [x] source별 `integrity.method`가 실제 보증보다 강하게 표시되지 않는다.
- [x] override·feedback에 `status=valid`가 나오지 않고 `not_applicable`을 쓴다.
- [x] review·fast의 chain 필드 부재가 실패가 아니라 `legacy`로 표시된다.
- [x] strict source의 chain·seq 조작이 exit 1과 `evidence.source` 결속 진단으로 드러난다.
- [x] acceptance의 중복·충돌 의미 검증 결과가 exit 1로 전달된다.
- [x] 한 source가 실패해도 다른 source의 partial result가 함께 출력된다.
- [x] 파일 부재가 WARN이 아니라 `present=false`·`record_count=0`·진단 없음·exit 0으로 처리된다.
- [x] `override` source 상태에 추적 사본이며 집행 정본이 아니라는 사실이 표시된다.

### 읽기 안전성

- [x] 명령 실행 전후 모든 감사 파일의 bytes가 동일하다.
- [x] symlink source가 거부되고 non-regular file이 `unreadable`로 표면화된다.
- [x] source당 크기·줄 수 상한 초과가 bounded 실패로 표면화된다.
- [x] invalid UTF-8이 추측 복구 없이 issue로 보고된다.
- [x] 읽기 전후 identity·size 변화가 한 번 재시도 후 안정 실패한다.
- [x] 불완전한 마지막 줄을 진행 중 append로 추측해 skip하지 않는다.
- [x] 조회가 lock 파일을 만들지도 획득하지도 않는다 — 실행 전후 `.sage/` 하위 파일 목록이 동일하다.
- [x] 살아 있는 writer lock을 보유한 프로세스가 있어도 조회가 그것을 기다리지 않고 끝난다.
- [x] `absent`·`damaged`·부분 append가 각각 다른 결과로 표면화되고 어느 것도 "기록 없음"이나 정상으로 접히지 않는다.
- [x] viewer 실패가 writer 원문을 rollback·truncate하지 않는다.
- [x] pure parser·summary 모듈이 `fcntl`·`msvcrt`를 import하지 않는다.

### 계약 재사용

- [x] pure 경계 정리 전후 golden fixture summary가 byte-for-byte 같다.
- [x] 기존 감사 writer의 함수 시그니처와 append bytes가 불변이다.
- [x] viewer 전용 정규식·간소 parser가 새로 만들어지지 않았다.
- [x] hook runtime이 `sage.i18n`과 `sage.diagnostics`를 import하지 않는다.

### 출력 계약

- [x] JSON 최상위 key 열둘과 enum이 영어 고정이고 `--lang`에 영향받지 않는다.
- [x] 한국어·영어 JSON이 byte 동일하다.
- [x] `data`에 allowlist 밖 key가 0건이다.
- [x] unknown event가 버려지지 않고 제한된 envelope와 WARN으로 표시된다.
- [x] 교차 source 정렬이 표시 순서일 뿐이라는 사실이 출력에 명시된다.
- [x] 한 source 안의 append 순서가 `source_index`로 보존된다.
- [x] `--limit` 생략 건수(`omitted`)와 `truncated` boolean 이 반드시 표시된다.
- [x] exit이 0(부재·정상)·1(unreadable·malformed·invalid)·2(옵션·root·계약 오류)다.
- [x] `--cycle-stem`·`--run-id`가 exact 일치이며 부분검색·정규식이 아니다.
- [x] 필터가 원본 무결성 판정을 생략하지 않는다.

### 개인정보와 추적

- [x] retro `note_path`가 text·JSON 어디에도 없다.
- [x] vault·HOME·state home 절대경로가 예외 메시지를 포함해 어디에도 없다.
- [x] `reason`·`scope`·`remaining_evidence`·`note`·`marker_text`에 절대경로를 넣어도 출력에 0건이다.
- [x] sanitizer가 치환한 사실이 issue로 남고 조용히 삼켜지지 않는다.
- [x] feedback의 `note`·`marker_text`가 `--include-local` 없이는 접근되지 않는다.
- [x] 저장소 상대경로 검증을 통과하지 못한 경로 값이 숨겨지고 issue로 표시된다.
- [x] 추적 정책 불일치가 안내만 하고 Git index를 자동 변경하지 않는다.
- [x] Git 저장소가 아니거나 probe 실패 시 `unavailable`로 낮추고 조회가 계속된다.
- [x] Git probe가 읽기 전용 호출만 쓰고 각각 timeout을 갖는다.
- [x] `feedback.jsonl`이 조용히 공유 추적 대상으로 확대되지 않는다.

### Obsidian 비의존성

- [x] vault 폴더·앱·플러그인·MCP가 없어도 Standard·Fast cycle과 감사가 동작한다.
- [x] `vault_path: ""`가 정상 OFF로 처리되고 WARN을 만들지 않는다.
- [x] 설정된 vault 경로가 없거나 쓰기 불가일 때 자동 파생은 WARN, 명시 출력은 nonzero다.
- [x] 명시적 `--no-vault`가 해당 run에 결속된 skip 감사 기록을 남긴다.
- [x] 자동 dashboard 실패가 이미 성공한 감사 close를 되돌리지 않는다.
- [x] `audit show`가 `vault_path`를 읽지 않고 vault에 쓰지 않는다.
- [x] vault dashboard를 삭제해도 조회 결과가 달라지지 않는다.
- [x] 정상 OFF와 설정 오류가 서로 다른 테스트로 분리돼 있다.

### 검증 환경

- [x] 격리 wheel 소비 프로젝트에서 Claude·Codex 양 host Golden E2E가 통과한다.
- [x] 소비 프로젝트·상태 홈 밖 sentinel tree의 hash가 실행 전후 불변이다.
- [x] 엔진 저장소 파일이 소비 프로젝트의 import path로 사용되지 않는다.
- [x] `run-all.sh`에 신규 테스트가 명시 등록되고 test inventory 완전성 검사를 통과한다.
- [x] none·Claude·Codex 환경 전체 hook suite가 통과한다.
- [x] `sage validate --kind all --check --schema`가 `STALE 0`으로 통과한다.
- [x] `git diff --check`가 통과하고 한영 문서가 미러 상태다.
- [x] manifest와 hook runtime hash가 current다.
- [x] `docs/ARTIFACTS.md`의 정본 이동 오해 문구가 한영 모두 정정됐다.
- [x] 로컬 무증상을 증거로 쓰지 않았고 형식만 맞춘 감사 레코드를 만들지 않았다.

### Shared-Surface Contract Gate

- [x] Phase 02 §10.1 권한·소유권 14행이 확정돼 있다.
- [x] Phase 02 §10.2 신뢰 경계·실패 12행이 확정돼 있다.
- [x] Phase 02 §10.3 불변식 I1~I15가 각각 대응 mutation 검사를 갖는다.
- [x] P0·P1 6+4항목이 하나도 수용되지 않았다.
- [x] P2 잔여 위험 RA-1~RA-5가 사용자 승인을 받았다.
- [x] Phase 02 §10.5 소비자 E2E CE-1~CE-10이 격리 wheel 소비 프로젝트에서 통과했다.
- [x] 사용자 결정 UD-1·UD-2·UD-3이 내려졌고 §10.4·§10.6에 반영됐다.
- [x] Gate 판정이 READY로 바뀐 뒤에 Phase 03을 열었다.

### 사용자 결정 (2026-08-25)

Phase 02 §10.6의 필수 결정 셋이 확정됐다. 각 결정은 §10.4 P2 잔여 위험의 수용 근거이기도 하다.

| id | 결정 | 구현이 지는 의무 |
|---|---|---|
| UD-1 | **수용.** viewer는 `.sage/override.jsonl`만 조회하고, 집행 정본(state home `grants/*.jsonl`) 검증은 하지 않는다. | source 상태에 "추적 사본이며 집행 정본 검증은 하지 않음"을 **항상** 표시한다. 사본과 집행 정본의 불일치는 이 기능의 검출 범위 밖임을 문서와 출력 양쪽에 명시한다. |
| UD-2 | **고정 토큰 `<redacted-path>`.** | 발견된 경로 **전체**를 이 토큰으로 치환한다. 원문·부분 경로·HOME·vault 경로가 어느 출력에도 남지 않는다. JSON에는 치환 발생을 식별할 수 있는 issue code를 남긴다. |
| UD-3 | **허용.** 엔진 소스 트리에서도 `audit show` 실행을 허용한다. | 엔진 트리에서의 성공은 소비자 E2E 증거가 **아니다**. Phase 03 종료 증거는 격리 wheel 소비 프로젝트에서만 인정한다(G16·G17). |

### Phase 03·04 착수 (2026-08-26)

rebase 재확인을 마치고 Phase 03을 열었다. 구현 결과는 `plan_docs/03-implementation/`, 격차 분석은 `plan_docs/04-analyze/`가 소유한다(둘 다 gitignore 대상이라 브랜치를 따라 이동하지 않는다 — 이 문서가 그 사실의 유일한 기록이다).

구현 중 잔여 위험 하나가 새로 드러나 Phase 02 §10.4에 RA-6으로 등재했다. `retro_audit` 레코드에는 `epoch`가 없고 `ts`만 있어 retro 이벤트가 교차 시간 정렬에서 항상 맨 뒤에 온다. 조회가 `ts`를 파싱해 epoch를 지어내지 않는 것이 수용 조건이며, 수용 여부 판단은 05로 넘긴다.

### 착수 방식

- [x] rebase 이후 R1~R6를 대조했고 불일치 항목을 문서에 반영했다.
- [x] 문서 구간에서 코드·테스트·fixture를 만들지 않았다.

## 6. Done Criteria Revision Log

### Revision 4

- Changed-At: Phase 02 → 03 경계 (rebase 재확인)
- Reason: 선행 `sage-operability-diagnostics`가 `main@3f34902`로 병합되어 R1~R6를 대조했고, R6가 깨져 설계 전제 하나가 바뀌었다. 아울러 §10.6의 필수 사용자 결정 셋이 확정됐다.
- Affected-Phases: 00·01·02
- Summary: R1·R2·R4의 실측값을 갱신하고 R6 결과를 별도 절로 고정했다. 선행이 `_read_status_unlocked`로 "조회는 lock을 잡지 않는다"를 정본화했으므로 D2(bounded lock)를 폐기하고 D3(lock 비생성·비획득, `absent`·`damaged`·부분 append의 명시적 표면화)으로 대체했다. G12를 "조회는 기다리지 않는다"로 다시 썼고 관련 Done Criteria·위험 표·구현 순서를 함께 고쳤다. UD-1(추적 사본만 조회하고 항상 표식) · UD-2(고정 토큰 `<redacted-path>`) · UD-3(엔진 트리 실행 허용, 단 종료 증거는 격리 wheel에서만) 결정을 기록하고 Phase 03 진입 판정을 **READY**로 바꿨다.

### Revision 3

- Changed-At: Phase 02 (Shared-Surface Contract Gate)
- Reason: Phase 03 진입 전 종료 범위·신뢰 경계·잔여 위험을 확정하는 Gate를 Phase 02에 추가했다.
- Affected-Phases: 00·01·02
- Summary: Phase 02에 §10 Gate 다섯 표(권한·소유권 / 신뢰 경계·실패 / 불변식·mutation / 오류 수용 / 소비자 E2E·복구)와 사용자 결정 표·판정 절을 추가했다. Done Criteria에 Gate 8항목을 넣고 헤더에 `Phase03-Entry`를 신설했다. 인수 기준에 AVN-AC32~34를 더했다. 판정은 **BLOCKED** — UD-1(override 불일치 수용) · UD-2(sanitizer 대체 표기) · UD-3(엔진 트리 실행 허용)이 미결이다.

### Revision 2

- Changed-At: Phase 00 (문서 리뷰 반영)
- Reason: G7의 절대경로 보장이 경로 필드 검증만으로는 성립하지 않는다는 지적이 타당했다.
- Affected-Phases: 00·01·02
- Summary: G7에 자유 문자열 공통 sanitizer 요구와 대응 Done Criteria 3항목을 추가했다. 로컬 source를 `--include-local` 없이 `--source`로 지목한 미정의 조합을 exit 2로 닫았다. 01의 registry 소유자 모순을 02 기준으로 통일하고, 01 인수표를 정본 5열로 바꾸고, `--lang`을 전역 옵션 위치로 고쳤다.

### Revision 1

- Changed-At: Phase 00
- Reason: 최초 작성.
- Affected-Phases: —
- Summary: 승인 설계 §16 Acceptance Criteria를 `main@63cc3bd` 실측에 맞춰 판정 가능한 항목으로 전개했다. 실측에서 드러난 편차 둘(override 이중 기록, 무기한 blocking lock)을 D1·D2로 기록했다. 선행 미병합 상태에서 착수했으므로 rebase 재확인 목록 R1~R6를 문서 상단 계약으로 고정했다.
