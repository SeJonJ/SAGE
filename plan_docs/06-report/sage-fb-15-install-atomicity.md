# [Report] SAGE-FB-15 install preflight-first와 실패 원자성

Cycle-Stem: `sage-fb-15-install-atomicity`
Source-05: `plan_docs/05-expert-review/sage-fb-15-install-atomicity.md`
Status: COMPLETE

## 1. Completion Summary

`sage install`의 overlay/domain/profile/manifest/CORE trust 판단을 일반 copy, global skill write, legacy prune보다
앞으로 이동하고, apply 중 catch 가능한 실패를 project와 Codex global 범위에서 되돌리는 transaction을
구현했다. 동일 destination의 협조 install은 직렬화되고, preflight 이후 핵심 입력과 install-owned 출력의
drift는 logical commit 전에 차단된다.

## 2. Delivered Controls

| Control | Result |
|---|---|
| preflight-first | render-independent overlay/domain/profile/manifest/CORE trust 검사 |
| destination lock | NFC/casefold canonical path + existing inode, per-user secure lock root |
| failure atomicity | write-ahead journal, same-parent original backup, reverse rollback |
| rollback ownership | concurrent output는 삭제하지 않고 current value와 backup을 recovery evidence로 보존 |
| force/global scope | force CORE replacement, Codex global skills, legacy prune가 한 transaction 공유 |
| drift detection | profile/manifest/overlay/render/ancestor/source/output fingerprint와 final CAS |
| filesystem safety | project/global symlink ancestor, unsafe manifest/profile/overlay leaf 차단 |
| profile consistency | YAML materialization과 generated JSON의 exact recursive type equality |
| write safety | exclusive atomic temp write, process-global umask 접근 제거 |
| security exception | FB-12 exact blocked managed-block cleanup만 base/manifest 보존 조건으로 선행 허용 |

## 3. Review and Verification

- Required reviews: three distinct user-authorized fresh Codex headless fallbacks because Claude was quota-limited.
- Required session IDs: `019f6dcb-c880-7ed3-a79c-4017c341e6b8`,
  `019f6de1-c15a-73b0-a8a2-ef7b7048d25a`, `019f6df7-6b78-7160-996c-8128fb365793`.
- Closure: initial P2 accepted in `019f6e08-a167-7600-9e6b-5fd294f7f7ec`; final fresh session
  `019f6e12-0bde-7452-a55b-ac37d331be05` returned `CLEAN_FOR_FB15_CLOSURE`.
- Focused install/transaction/overlay suite: 153 passed.
- Full Python suite: 1,200 passed, 1 skipped.
- Official hook suite: `ALL HOOK TESTS PASS`.
- Final `git diff --check` is part of the report closure verification.

## 4. Acceptance Result

FB15-AC1 through FB15-AC10 are PASS. Preflight failure does not leave general install mutation, apply failure restores
installer-owned state, concurrent non-owned output is preserved instead of overwritten during rollback, and success
is reported only after logical commit.

## 5. Residual Risk

The transaction is failure-atomic for catchable Python control flow, not durable across SIGKILL, `os._exit`, kernel
failure, or power loss. Same-permission non-cooperative processes remain outside the local authoritative boundary;
post-install `sage validate` and FB-08 server attestation own broader integrity.

The default PATH Python 3.11 lacks `jsonschema`. Official schema verification uses the Homebrew Python environment or
requires installing the schema extra. No cycle audit `run_id` exists in this engine repository, so this report does
not fabricate a `Loop-Run` marker.

## 6. Component Impact

- SAGE engine: install ordering, transaction, locking, profile/manifest/overlay safety, and regressions updated.
- ChatForYou Backend: N/A, no application source changed.
- ChatForYou Frontend: N/A, no application source changed.
- ChatForYou Desktop: N/A, no application source changed.

## 7. Final Status

COMPLETE. Phase 05 approved this exact cycle before Phase 06 authoring.
