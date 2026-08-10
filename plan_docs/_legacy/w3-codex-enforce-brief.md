# W3 개발 브리프 (codex 담당) — retro 게이트 codex enforce 의미 일치

> 이 문서는 codex 가 직접 개발하는 9-C-2 W3 의 핸드오프 브리프다. W3 는 codex Stop lifecycle 의
> 실차단 가능 여부를 **실세션 E2E 로 실증**해야 하므로 codex host 에서 개발·검증하는 게 확실하다.
> (W2/P0-b, W4 는 Claude 가 별도 구현 완료.)

## 배경 — 지금의 비대칭

retro 게이트(`policies/retro_gate.py`)는 세션 종료(Stop)에서 `sage retro --check` 미실행을 사후
감지해 enforce 모드면 BLOCK 을 낸다. 그런데 실제 차단은 **claude host 만** 된다:

`scripts/sage_harness/hooks/runtime/hook_runtime.py` 의 `run_stop_compliance_report()` 끝부분:

```python
exit_code = model["exit_code"]
if rg_result["severity"] == "BLOCK":
    if io.RUNTIME == "claude":
        print(f"[stop-compliance-report] ❌ {rg_result['text']}")
        exit_code = 2                      # claude: 실제 세션 1회 차단
    else:
        print(f"[stop-compliance-report] ⚠️  (codex — 미검증 미차단) {rg_result['text']}")
        # codex: 리포트에만 BLOCK, 세션은 통과(차단 안 함)
return exit_code
```

즉 codex 에서는 `report_gate_enforce=enforce` 라도 **경고만 찍고 통과**한다. 미강제를 정상으로
고정한 상태다. 이게 W3 가 닫아야 할 갭이다.

## 요구사항 (roadmap 9-C-2 W3)

off/advisory/enforce 의미가 **양 host 동일**해야 한다. 구체적으로:

1. **codex Stop 차단이 실제로 되는지 실세션 E2E 로 실증**하고, 되면 codex 에서도 enforce 첫 Stop 이
   실제로 세션을 1회 막게 구현한다.
2. **실증 결과 codex Stop 차단이 불가능하면**, `profile_validate` 가 `host=codex + report_gate_enforce=enforce`
   조합을 **거부(FAIL)** 하게 한다 — "codex 에서 enforce 를 설정했는데 실제로는 안 막힘"을 애초에
   배포 못 하게. (advisory 는 양 host 동일하게 리포트만 하므로 거부 대상 아님.)

둘 중 무엇이 되든, 최종 상태는 "codex enforce 가 조용히 무력화되는" 현 상태가 아니어야 한다.

## codex Stop lifecycle 조사 필요 (핵심 불확실성)

이 저장소엔 codex 훅 바이너리 스키마 조사 메모가 있다(9-C-2 스펙): 이벤트 PreToolUse·PostToolUse·
Stop·UserPromptSubmit 존재, Stop 전용 decision wire 는 없으나 범용 `BlockDecisionWire`
(decision:block + reason, "Claude block 시맨틱 준수" 주석) 존재. → **codex Stop 차단은 실세션
E2E 로만 확정 가능**하다. 다음을 실측하라:

- codex Stop 훅이 exit code 2 를 반환하면 세션이 실제로 막히는가? (claude 관례)
- 아니면 stdout 으로 `{"hookSpecificOutput": {...}}` 또는 `{"decision":"block","reason":...}` JSON 을
  내보내야 막히는가? io_codex 의 다른 렌더(render_gate)는 PreToolUse 에서 block→stderr 를 쓴다.
- `stop_hook_active` 재시도 필드를 codex 도 보내는가? (세션당 1회 차단 제약이 codex 에도 성립하는지)

## 구현 지점

- `hook_runtime.py::run_stop_compliance_report` 의 위 exit 분기 — codex 실차단 경로.
- `scripts/sage_harness/hooks/runtime/io_codex.py` — Stop block 렌더 채널(필요 시 신설).
  대칭 참고: `io_claude.py` 의 동일 지점.
- `sage/profile_validate.py` — (실증 실패 시) codex+enforce 거부 규칙. 기존 validate 규칙들과 동형으로.
- 스펙 `docs/sage_harness/hooks/stop-compliance-report.md` 의 exit_code 계약 문구 갱신
  (현재 "codex host 는 리포트에 BLOCK 을 남기되 차단은 안 한다(codex Stop lifecycle 미검증)").

## 테스트 요구

- 실차단 구현 시: codex adapter 로 enforce + 미확인 + 첫 Stop → 실제 차단(반환/JSON) E2E,
  `stop_hook_active` 재시도 → 통과. 기존 `test_stop_compliance_report.py::test_codex_reports_block_but_never_exits_2`
  는 새 동작에 맞게 교체(현재는 "codex 는 절대 exit 2 안 함"을 박제 중 — W3 가 이걸 뒤집는다).
- validate 거부 경로 시: `test_profile_validate` 류에 codex+enforce=FAIL 케이스 추가.
- 양 host 어댑터 단위 + 실 Stop E2E 존재(roadmap 완료 기준).

## SAGE 개발 규약 (반드시 준수)

- **재스탬프**: manifest-추적 파일(hook_runtime/io_codex/policies, 스펙 .md) 수정 시
  `python3 -m sage generate --kind hook --write` 후 `sage validate` PASS 확인하고 커밋.
  (self-validate 가 STALE 로 red 나는 사고 방지.)
- **주석·커밋 규약**: 코드 주석·커밋 메시지에 설계 참조번호(W3/P0/P1/R2 등)·라운드수 라벨 금지.
  코드만 보고 이해되는 자기완결 주석(what 1줄 + WHY 1~2줄). 커밋은 짧은 맥락 + 파일별 bullet.
  (배경 서술은 이 브리프/plan_docs 에.)
- **적대적 자기검증**: 개발 완료 전 codex 스스로 최소 3회 적대적 재검(teeth 재현 후 수용).
- **fail-open 규약**: Stop 훅은 내부 오류로 세션을 막지 않는다. 단 게이트 무력화는 조용히 삼키지
  말고 surface(리포트/stderr). advisory-first.

## 완료 기준(roadmap 인용)

off/advisory/enforce 의미가 양 host 동일 · codex enforce 차단이 실세션 검증(또는 validate 거부) ·
양 host 어댑터 단위 + 실 Stop E2E 테스트 존재.

## 실세션 검증 결과

- 검증 환경: Codex CLI 0.144.1, macOS, 격리된 `/tmp` 프로젝트
- 첫 Stop: stdout `{"decision":"block","reason":"W3_STOP_BLOCK_PROBE"}` + exit 0 → `Stop Blocked`
- 재호출: 동일 turn에서 두 번째 응답 생성, 입력에 `stop_hook_active:true` 확인
- 출력 제약: `decision`과 `hookSpecificOutput` 결합 또는 Stop에서 hookSpecificOutput 단독 출력은 `Stop Failed`
- 구현 결론: 차단 시 decision/reason만 출력하고 reason에 compliance 경로를 포함한다. 재시도·통과 시에는
  무출력 exit 0으로 종료하고 compliance 리포트는 파일로만 보존한다.
- SAGE fresh-install E2E: session `019f5585-b7bb-7a53-bb42-9e1982d9bfdb`에서 SessionStart baseline 생성,
  Bash로 06 변경, 첫 Stop `Blocked`, 재호출 입력 `stop_hook_active:true`, 두 번째 Stop `Completed` 확인.
