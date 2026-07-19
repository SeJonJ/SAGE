# [Base Plan] SAGE-FB-13 raw profile 위험 필드 타입 선검증

Cycle-Stem: `sage-fb-13-raw-profile-types`
Risk Level: L3
Status: COMPLETE

## 1. Context

`materialize_profile`은 `list(risk.get(...))`를 사용한다. YAML에서 `l3_filename_globs: auth`처럼
문자열 스칼라를 넣으면 `['a', 'u', 't', 'h']`로 변환되고, 이후 compiled profile validator는 이미
유효한 문자열 배열만 보기 때문에 원본 오류를 놓친다. freshness 비교도 같은 coercion 결과를 사용해
YAML/JSON이 서로 일치한다고 오판한다.

## 2. Goal

- compiler가 materialization 전에 risk glob/keyword 값을 비어있지 않은 문자열 리스트로 검증한다.
- raw YAML, compiled JSON 직접 검증, YAML/JSON freshness, runtime hook 준비 경로가 모두 fail-closed다.
- invalid raw profile은 compiled JSON이나 hook registration을 만들지 않는다.
- 정상 domain materialization과 highest-risk dedupe 동작은 유지한다.

## 3. Scope

In scope:

- top-level risk glob/keyword list fields
- `risk.domains[*].path_globs/content_keywords`
- profile compiler exception contract와 모든 production caller 처리
- profile schema/semantic validation 및 generate/validate/hook regression tests
- Claude fresh headless 3회 review-rework 검증; Claude 오류/사용량 제한 시 사용자 지정 independent headless fallback

Out of scope:

- profile의 모든 list 필드에 대한 전면 strict typing
- 새로운 profile key 또는 migration CLI
- L0/L3 precedence 정책(FB-07)

## 4. Impact

- SAGE compiler/generate/validate/hook bootstrap: malformed profile이 WARN/traceback/문자배열 대신 명시적 FAIL이 된다.
- Existing valid projects: output bytes and domain materialization remain unchanged.
- ChatForYou Backend/Frontend/Desktop: direct application code impact N/A.
- Governance: typo와 type drift로 위험 게이트가 침묵 약화되는 경로를 차단한다.

## 5. Done Criteria

1. scalar/null/non-string item risk triggers are rejected before materialization.
2. domain trigger lists follow the same contract.
3. `sage generate --write` does not write compiled JSON or hook assets for invalid raw YAML.
4. `sage validate` treats invalid raw freshness input as FAIL, not WARN-only.
5. `sage-hook` gate returns controlled block instead of traceback or stale equality.
6. direct compiled JSON validation fails even without jsonschema.
7. valid materialization regression tests pass.
8. Claude 또는 명시된 오류 fallback의 independent fresh headless reviews 3회와 finding triage가 기록된다.
