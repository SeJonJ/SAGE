"""retro_gate — Stop 훅 정책: `sage retro --check` 가 실제로 통과했는지 사후 확인(9-C v1).

배경: `sage retro --check` 는 host 가 스스로 실행해야만 효력이 있다. 06←05 훅으로는 강제할 수 없다
(sage-team 절차상 06 이 retro 보다 먼저 쓰여, 06 게이트가 도는 시점엔 retro 노트가 아직 없다). 유일하게
06 과 retro 둘 다를 볼 수 있는 지점이 세션 종료(Stop) 다.

**범위(v1, 의도적으로 좁음)**: Stop 훅의 `stop_hook_active` 를 지키면(Claude Code·codex 공식 문서 확인)
block 은 세션당 정확히 1회만 가능하다 — 이건 설계 선택이 아니라 플랫폼 제약. 그래서 이 게이트의
"enforce" 는 "완료할 때까지 못 끝냄" 이 아니라 **"1회 강한 넛지 + 감사기록"** 이다. 무시하고 재시도하면
세션은 끝나지만, retro_audit 에 "미완료로 종료됨" 이 남아 이후 `sage doctor`/다음 사이클이 볼 수 있다.
진짜 차단(완료 전 세션 종료 불가)은 별도 백로그(9-C-2, 새 결정론 게이트 필요 — Stop 훅만으론 불가능).

또한 v1 은 **세션당 정확히 하나의 05→06 사이클**만 다룬다. 한 세션에 05→06 사이클이 여러 번(멀티
사이클) 있으면 어떤 06 이 어떤 05 에 결속되는지 모호해질 수 있어(codex 설계리뷰 P0) — 이 경우
run_id 를 하나로 특정할 수 없다고 보고 게이트를 건너뛴다(fail-open, 오탐보다 침묵이 낫다).
"""

_SEVERITIES = ("INFO", "OK", "WARN", "BLOCK")


def check(mode, has_06_this_session, run_id, retro_checked, stop_hook_active, notes_enabled=True):
    """순수 함수. 입력은 전부 adapter(hook_runtime.py)가 세션/파일시스템에서 미리 계산해 넘긴다.

    mode: "off"|"advisory"|"enforce"|기타(무효 → off 취급).
    has_06_this_session: 이번 세션에 06 phase glob 매치 파일이 쓰였는가.
    run_id: 06 작성에 쓰인 05 문서의 Loop-Run: 마커에서 특정한 run_id. None = 특정 불가(멀티사이클/마커없음 등) → 게이트 skip.
    retro_checked: retro_audit.jsonl 에 이 run_id 의 유효 기록이 있는가.
    stop_hook_active: 이번 Stop 시도가 이전 Stop 훅의 block 때문에 생긴 재시도인가(플랫폼 제공 필드).
    notes_enabled: knowledge_capture.retro_note 가 켜져 있는가(retro 노트가 생성되는가).

    반환: {"name": "retro_gate", "severity": one of _SEVERITIES, "text": str}.
    severity="BLOCK" 일 때만 오케스트레이터가 프로세스를 exit 2 로 종료해야 한다(플랫폼별 IO 모듈이 판단).
    """
    if mode not in ("advisory", "enforce"):
        return {"name": "retro_gate", "severity": "INFO", "text": "N/A — pdca.retro.report_gate_enforce=off"}
    if not notes_enabled:
        # retro_note off → 노트가 안 만들어져 `sage retro --check` 자체가 불가. enforce 는 노트 워크플로가
        # 켜져 있음을 전제하므로 게이트를 skip 한다(codex 구현리뷰 6R P1: sage-team 이 vault off 면 retro 를
        # skip 하라 안내하는데 여기서 block 하면 정상 흐름과 충돌). profile_validate 가 이 조합을 WARN 한다.
        return {"name": "retro_gate", "severity": "INFO",
                "text": "N/A — knowledge_capture.retro_note off (노트 미생성 → --check 불가, 게이트 무동작)"}
    if not has_06_this_session:
        return {"name": "retro_gate", "severity": "INFO", "text": "N/A — 이번 세션에 06 문서 작성 없음"}
    if run_id is None:
        return {"name": "retro_gate", "severity": "INFO",
                "text": "N/A — run_id 특정 불가(05 문서에 Loop-Run 마커 없음 또는 세션에 05→06 사이클 다중) — 게이트 skip"}
    if retro_checked:
        return {"name": "retro_gate", "severity": "OK",
                "text": f"retro --check 통과 확인됨 (run_id={run_id})"}

    text = (f"retro --check 미확인 (run_id={run_id}) — `sage retro --run-id {run_id} --feature <stem>` 로 "
            f"human-gate 노트를 작성·확인한 뒤 `sage retro --check <노트> --run-id {run_id}` 를 실행하세요.")
    if mode == "enforce" and not stop_hook_active:
        return {"name": "retro_gate", "severity": "BLOCK", "text": text}
    # enforce 인데 stop_hook_active=true(이미 1회 block 했음) → 더 block 하지 않고 advisory 로 낮춘다.
    # advisory 모드는 애초에 block 안 함.
    return {"name": "retro_gate", "severity": "WARN", "text": text}
