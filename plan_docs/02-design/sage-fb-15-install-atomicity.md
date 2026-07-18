# [Design] SAGE-FB-15 install preflight-first와 실패 원자성

Cycle-Stem: `sage-fb-15-install-atomicity`

## 1. Execution Order

```text
acquire destination lock outside project
  -> plan exact FB-12 blocked-block cleanup
  -> load/validate profile and manifest
  -> CORE trust preflight
  -> overlay/domain contract preflight (render-independent)
  -> capture immutable input fingerprints
  -> apply FB-12 exact cleanup exception
  -> revalidate fingerprints
  -> begin install transaction
     -> project framework/CORE/spec writes
     -> optional Codex global skill writes
     -> legacy prune (journaled move)
     -> re-run materialization plan against copied renders
     -> verify anchors and input fingerprints
     -> materialize through transaction writer
     -> manifest/schema/template writes
     -> final integrity/CAS checks
  -> logical commit
  -> remove backups as post-commit GC
catchable failure after begin -> rollback reverse journal -> rc=1 (BaseException control signals re-raised)
release lock
```

정상 preflight 오류에서는 FB-12 exact cleanup 외 mutation이 없다. Overlay preflight는 render 파일이 없어도
profile/domain/overlay inventory를 검사할 수 있도록 `overlay_materialize`의 pure helper로 분리하고,
`plan_materialize`도 동일 helper를 재사용해 scanner drift를 막는다.

## 2. Install Transaction

새 transaction 모듈은 destination lock과 mutation journal을 소유한다.

- `stage_write(path)`: 첫 변경 전에 journal/original 상태를 기록한 뒤 기존 leaf를 같은 parent backup으로
  `os.replace`; 신규 path는 absent로 기록한다.
- `write_text(path, content, mode)`: staged path에 atomic LF write 후 mode를 적용한다.
- `stage_remove_tree(path)`: legacy directory를 backup으로 이동하고 commit 전까지 삭제하지 않는다.
- `commit()`: 먼저 transaction을 committed로 표시한 뒤 backup을 post-commit GC로 제거한다. cleanup 중
  control signal은 이미 완성된 새 출력을 rollback하지 않으며 backup residue만 남길 수 있다.
- `rollback()`: reverse order로 installer-owned 출력만 제거하고 backup object를 원래 이름으로 복귀한다.
  현재 path fingerprint가 기록 출력과 다르거나 backup이 사라졌으면 현재 path/남은 backup을 보존하고
  recovery conflict를 보고한다.
- transaction이 만든 parent 목록을 역순으로 `rmdir`해 새 빈 directory를 정리한다.

같은-parent backup은 regular file의 mode, symlink, hard-link inode 관계와 directory tree를 byte-copy 없이
보존한다. Backup 이름은 충돌 불가능한 random token이며 정상 cleanup/rollback 뒤 남지 않아야 한다.
logical commit 뒤 cleanup control signal이 발생한 경우에는 새 출력과 함께 residue가 남을 수 있다.

## 3. Optimistic CAS

Fingerprint는 `lstat` object type, mode, device/inode, symlink target 또는 regular-file SHA-256을 포함한다.
Preflight가 신뢰 판단에 사용한 profile YAML/생성 JSON, manifest, overlay files, CORE render와 existing
ancestors를 캡처한다. YAML과 JSON이 함께 있으면 JSON은 YAML materialization과 정확히 같아야 하며,
JSON-only 설치 호환성은 유지한다.

- transaction 첫 mutation 전에 전체 fingerprint를 다시 비교한다.
- 각 CORE render를 stage하기 직전 해당 path/ancestor를 다시 비교한다.
- materialization 직전 profile/overlay snapshot을 비교한다.
- manifest 쓰기 직전 기존 manifest snapshot을 비교한다.

드리프트는 `install input changed during preflight`로 fail하며 transaction을 rollback한다. Process lock은
협조하는 SAGE install 경합을 제거하고 CAS는 비협조 변경을 탐지한다. 동일 권한 공격자가 검사 직후와
커널 write 사이를 무한 경쟁하는 상황은 로컬 trust boundary 밖이며 최종 `validate`와 FB-08이 담당한다.
최종 input/output/source 검증 직후 logical commit하고, 성공 보고는 commit 및 post-commit cleanup 뒤에만
수행한다.

## 4. Error and Reporting

- preflight 오류는 정렬된 path/reason을 출력한다.
- apply 오류는 원인과 rollback 결과를 구분해 출력한다.
- rollback 성공이어도 install은 rc=1이다.
- rollback 실패는 affected backup/original path를 남겨 수동 복구가 가능하게 보고한다.
- 메모리 journal이 실행될 수 없는 SIGKILL/전원 중단은 이번 실패 원자성 범위 밖이며 crash-safe/durable
  transaction으로 표현하지 않는다.

## 5. Tests

- invalid/blocked/relaxing overlay와 domain contract의 first/reinstall/force no-write snapshot
- N번째 `_write`, materialization, manifest write failure injection 후 exact tree/object restoration
- Codex global skill과 legacy directory rollback
- lock contention, profile/manifest/overlay/render drift injection
- success idempotency, force upgrade, both hosts, mode/symlink/hard-link regressions
