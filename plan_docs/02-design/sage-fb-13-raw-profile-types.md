# [Design] SAGE-FB-13 raw profile 위험 필드 타입 선검증

Cycle-Stem: `sage-fb-13-raw-profile-types`

## 1. Single Validation Primitive

`sage.profile_compile` owns a pure `materialization_issues(profile)` function. It returns deterministic messages
for only the fields the compiler consumes. `materialize_profile` calls it before `deepcopy`/`list`/`extend` and
raises one `ProfileCompileError` containing all findings.

`profile_validate` imports the same primitive and maps each message to `FAIL`, so direct compiled JSON validation
and no-jsonschema environments use identical type vocabulary without circular dependency.

## 2. Caller Flow

```text
generate YAML load
  -> materialize_profile(raw)
     -> raw contract fail: ProfileCompileError -> rc1, no output
  -> write JSON
  -> full validate_profile(compiled)

validate freshness
  -> materialize_profile(raw YAML)
     -> raw contract fail: overall FAIL
  -> compare with JSON

sage-hook gate bootstrap
  -> load YAML + JSON
  -> materialize_profile(raw YAML)
     -> raw contract fail: controlled gate BLOCK
  -> compare and inject JSON path
```

## 3. Schema Layer

`schema/profile.schema.json` top-level risk arrays receive `items: {type:string,minLength:1}`. This is defense in
depth for JSON/schema users; semantic validation remains authoritative when jsonschema is absent.

## 4. Atomicity

`_compile_profile` performs materialization before creating the destination directory or writing JSON. A compile
failure therefore preserves an existing destination tree and cannot leave a freshly coerced profile behind.

## 5. Test Matrix

| Layer | Cases |
|---|---|
| compiler | scalar, null, numeric/bool/empty item, domain scalar, valid output |
| semantic/schema | direct bad compiled dict with and without schema dependency |
| generate | invalid YAML rc1, no JSON/settings/hooks |
| validate | invalid raw + existing JSON produces FAIL not stale WARN |
| hook entry | both hosts gate block with controlled message |

