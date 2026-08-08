# [Base Plan] SAGE 사이클 선언 사용성 완성

Cycle-Stem: `sage-cycle-usability`
Risk Level: L2
Status: IMPLEMENTED (2026-08-08, UNRELEASED)

## 1. 문제

`v0.9.79` 는 장수 브랜치에서 현재 사이클을 `.sage/cycle.json` 으로 선언할 통로를 만들었지만,
CLI 동사와 정상 생성 경로, 선언 생명주기의 소유자가 빠져 있다. 사용자는 `use` 를 "선언"으로
해석해야 하고, Phase 00 이 없으면 문서를 수동 작성해야 하며, 스킬은 `set`/`clear` 를 호출하지 않아
낡은 선언이 다음 사이클에 남는다.

## 2. 목표

1. `sage cycle set <stem>` 으로 선언 동사를 교체한다. 숨은 `use` 는 실행하지 않고 이전 안내만 한다.
2. `set <stem> --create --risk L1|L2|L3 [--path <dir>]` 로 유효한 Phase 00 하나를 만든 뒤 선언한다.
3. 기존 문서 재개와 새 문서 생성을 관측 가능한 Phase 00 상태로 구분해 안내한다.
4. `sage-plan` 이 검증 후 선언하고, `sage-team` 이 재개 시 대조하고 실제 완료 뒤 해제한다.
5. `$sage-cycle` 은 직접 중복 실행하지 않되, 위임 소유권과 최종 상태를 사용자에게 분명히 보인다.

## 3. 핵심 계약

- 게이트 판정 `_decide` 는 변경하지 않는다.
- `--create` 는 현재 root 의 YAML `pdca.phases[id=00].glob` 만 정본으로 사용한다.
- JSON 부재는 부트스트랩으로 허용하고 generate 경고를 출력한다. JSON 손상 또는 phase 00 glob
  불일치는 거부한다.
- `--path` 는 root 상대 디렉터리다. 절대경로, `..`, root 밖 symlink, phase 00 glob 불일치를 거부한다.
- 대상 또는 phase 00 glob 아래 같은 basename 엔트리는 내용과 무관하게 덮지 않는다. 충돌 경로
  전부와 configured 00~06 에서 충돌하지 않는 `<stem>-N` 후보 3개를 출력하고 자동 적용하지 않는다.
- 문서 생성 성공 뒤 선언 실패는 문서를 보존하고 `sage cycle set <stem>` 복구 명령을 출력한다.
  문서 자체의 부분 쓰기 실패만 이번 프로세스가 만든 불완전 엔트리를 제거한다.
- `sage-team` 은 context restore 와 cycle identity hard stop 뒤, evidence-anchor 판정 전에 선언을
  대조한다. `clear` 는 write-back, retro, snapshot, 종료 게이트 확인 뒤 `## Done` 직전에 실행한다.
- `BLOCKED`/`FAIL` 에서는 선언을 유지한다. env 선언은 파일 `clear` 로 없어지지 않으므로
  `unset SAGE_CYCLE_STEM` 을 안내한다.

## 4. 구현 범위

- CLI 및 선언 상태: `sage/commands/cycle.py`, 필요 시 cycle runtime 공용 헬퍼
- 안내 정본: hook runtime messages와 canonical hook 문서
- 스킬: `sage-plan`, `sage-team`, `sage-cycle`
- 사용자 문서: 한·영 README, CLI reference, troubleshooting, PDCA guidance
- 테스트: K-T1∼K-T27. 기존 `test_cycle_state.py` 를 확장하고 필요할 때만 runner를 추가한다.

## 5. 검증과 중단 조건

1. 테스트를 먼저 추가해 의도한 RED를 확인한다.
2. `sage generate --kind hook --write` 로 추적 자산을 재스탬프한다.
3. `sage validate --kind hook --check --schema` 는 `STALE 0` 이어야 한다.
4. `run-all.sh` 를 none/claude/codex env에서 순차 실행하고 wheel smoke, 문서 미러,
   `git diff --check` 를 확인한다.
5. 독립 구현 리뷰는 최대 3R이다. 차단 지적이 남으면 중단해 보고한다.
6. 커밋, 머지, 릴리즈는 사용자의 명시적 허락 전 수행하지 않는다.
