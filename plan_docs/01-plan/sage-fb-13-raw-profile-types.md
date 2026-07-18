# [Plan] SAGE-FB-13 raw profile 위험 필드 타입 선검증

Cycle-Stem: `sage-fb-13-raw-profile-types`

## 1. Acceptance Matrix

| Acceptance ID | Requirement | Required |
|---|---|:---:|
| FB13-AC1 | top-level risk glob/keyword 필드는 명시 시 non-empty string list여야 한다. | yes |
| FB13-AC2 | domain path_globs/content_keywords도 같은 list/item 계약을 따른다. | yes |
| FB13-AC3 | materializer는 invalid raw profile에 controlled `ProfileCompileError`를 발생시킨다. | yes |
| FB13-AC4 | generate는 invalid profile에서 JSON/registration을 쓰기 전에 exit 1 한다. | yes |
| FB13-AC5 | validate freshness와 sage-hook gate는 invalid raw profile을 fail-closed 처리한다. | yes |
| FB13-AC6 | compiled JSON semantic/schema validation도 scalar와 bad item을 FAIL한다. | yes |
| FB13-AC7 | valid domain merge/dedupe output은 회귀하지 않는다. | yes |
| FB13-AC8 | Claude review 또는 Claude 오류 시 fresh headless fallback review를 3회 수행하고 findings를 선별 반영한다. | yes |

## 2. Governed Fields

Top-level `risk`:

- `l0_pass_globs`
- `l1_path_globs`
- `l2_path_globs`
- `l3_filename_globs`
- `l2_content_keywords`
- `l3_content_keywords`

Domain-level:

- `risk.domains[*].path_globs`
- `risk.domains[*].content_keywords`

각 값은 key가 존재하면 `list[str]`이며 모든 item은 `strip()` 후 비어있지 않아야 한다. key가 없는
것은 기존처럼 빈 목록으로 materialize할 수 있지만, 명시적 null은 작성 오류로 FAIL한다.

## 3. Error Contract

- compiler library: `ProfileCompileError(ValueError)` with deterministic field paths.
- CLI generate: stderr에 profile 컴파일 실패 원인을 출력하고 rc=1, partial output 없음.
- validate freshness: `FAIL profile-raw-type-invalid`, overall rc=1.
- `sage-hook`: gate bootstrap message + rc=2; advisory hooks remain existing fail-open behavior.
- profile validator: jsonschema availability와 무관하게 semantic FAIL.

## 4. Compatibility

- Missing fields and empty lists remain valid.
- Existing valid list order/dedupe/highest-risk ownership remains unchanged.
- Compiler output schema remains the same; only invalid inputs stop earlier.
