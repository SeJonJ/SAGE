# [Implementation] SAGE-FB-14 최초 install CORE base 신뢰 앵커 검증

Cycle-Stem: `sage-fb-14-install-core-trust-anchor`
Status: IMPLEMENTED_REVIEWED

## 0. Pre-Implementation Declaration

- Risk: L3 trust boundary hardening.
- Required phases: 00~06.
- Review: three fresh headless rounds; Claude error/quota uses user-authorized fallback, no subagents.
- Components: SAGE engine only; ChatForYou application code N/A.

## 1. Planned Files

- `sage/commands/install.py`: expected resolver, trust preflight, conflict reporting, run ordering.
- `scripts/sage_harness/hooks/tests/test_install.py`: first-install, existing-anchor, force, both-host regressions.

## 2. Checklist

- [x] Add deterministic expected CORE render resolver.
- [x] Compare existing canonical base with anchor and current bundle before writes.
- [x] Reject symlink/read/malformed render collisions.
- [x] Print deterministic inventory and migration/force guidance.
- [x] Add no-write/manifest preservation tests.
- [x] Run install/materialization regression suites.
- [x] Complete three independent review rounds and triage.

## 3. Implemented Behavior

- `overlay_materialize.render_targets`를 신뢰 preflight와 manifest anchor의 공통 대상 열거로 사용한다.
- framework/agent/skill 배포 정본을 읽고 Claude agent에는 설치 profile의 model/effort 렌더링을 적용한다.
- non-force 설치는 기존 파일의 canonical base가 기존 anchor 및 현재 배포 base와 모두 일치할 때만 진행한다.
- 충돌 시 정렬된 inventory를 출력하고 project/global write, prune, materialize, manifest 갱신 전에 종료한다.
- `--force`는 명시적 교체 경로이며 symlink target을 따라 쓰지 않고 project-local link 자체를 일반 파일로 바꾼다.

## 4. Verification Before Review

- `test_install.py -b`: 85 tests pass.
- `test_overlay_materialize.py`: 15 tests pass.
- `git diff --check`: pass.
- Total focused regression: 100 tests pass.

## 5. Round-1 Rework

- ancestor symlink를 모든 모드에서 차단하고 leaf symlink만 `--force`가 링크 자체를 교체하도록 제한했다.
- FIFO 등 non-regular leaf를 읽기 전에 `lstat`으로 차단해 preflight hang을 제거했다.
- non-UTF-8, malformed marker, parent symlink, FIFO 회귀 테스트를 추가했다.
- conflict inventory 테스트가 path/reason 및 독립 계산한 expected/actual SHA-256 값을 검증하도록 강화했다.

## 6. Round-2 Rework

- `plan_materialize`가 계산한 exact base snapshot을 current bundle expected hash에 결속한 후에만 적용/기록한다.
- `_write`를 same-directory temp + atomic replace로 변경해 force가 외부 hard-link inode를 truncate하지 않게 했다.
- atomic replace 이후 기존 regular file mode 보존 및 신규 파일 umask 호환을 유지했다.
- 다중 Codex conflict의 exact sorted stderr, complete destination snapshot, non-opt-out `CODEX_HOME` 무변경을 검증한다.

## 7. Round-3 Triage

Accepted and fixed:

- shared `AGENT_GUIDE.md`의 other-host receipt도 현재 anchor로 갱신한다.
- malformed/non-mapping manifest의 non-force 재설치를 fail-closed하고 bytes를 보존한다.
- materialization atomic replace가 기존 render mode를 보존한다.

Deferred with explicit residual risk:

- same-permission concurrent process의 ancestor 교체 및 plan/apply 사이 mutation은 directory-FD/CAS 기반
  전체 install transaction 문제다. FB-14의 pre-existing-file trust 범위를 넘으므로 FB-15에서 다룬다.
- 현재 구현은 materialization snapshot hash를 current bundle에 결속해 arbitrary base receipt는 차단하고,
  이후 동시 drift는 expected anchor와 불일치해 validate에서 검출되도록 유지한다.

## 8. Closure Rework

- 첫 closure review가 mapping-shaped manifest 손상(`core_renders: []`, `assets: []`, malformed host history)을
  non-force가 정상화하는 누락을 발견했다.
- 선택 의존 `jsonschema` 없이도 install이 유실시킬 수 있는 핵심 구조를 순수 Python으로 fail-closed 검증한다.
- 네 가지 mapping-shaped 손상 회귀가 rc=1 및 manifest byte 보존을 검증한다.

## 9. Closure-2 Rework

- force recovery가 invalid mapping-shaped asset와 other-host receipt를 재보존하지 않도록 sanitize한다.
- `installed_hosts`는 primary `host_runtime`을 반드시 포함하며 force recovery도 primary를 복원한다.
- 레거시 호환은 필수 필드가 유효하고 optional `installed_hosts`/`core_renders`만 없는 manifest를 실제
  install run 경로로 검증한다.
- recovery 결과는 `_manifest_structure_issue`를 통과하고 shared guide receipts가 동일함을 검증한다.

## 10. Closure-3 Rework

- final closure가 mapping 형태이지만 JSON Schema를 위반하는 nested asset/receipt를 추가로 발견했다.
- asset entry의 허용 키, required enum, SHA 형식, nested hash map, scalar/array 타입을 선택 의존성 없이
  `manifest.schema.json`과 동등하게 검증한다.
- CORE receipt는 정확히 `base_sha256`과 `sage_version`만 허용한다.
- non-force는 구조 손상 manifest bytes를 보존한 채 차단하고, force recovery는 해당 엔트리를 제거한다.
- 수정 후 fresh closure session `019f6c6d-a347-7900-a4a4-445408807a8a`가 `CLEAN`을 반환했다.
