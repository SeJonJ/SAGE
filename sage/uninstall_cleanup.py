"""자동 제거가 불가능하거나 실패했을 때의 **수동 정리 안내**.

## 왜 "남은 파일 목록" 이 아닌가

남은 것을 전부 삭제 목록으로 주면 사용자는 공유 설정 파일과 자기 파일을 통째로 지운다. 이
명령이 자동 실행에서 지키던 네 의미(`DELETE`·`STRIP`·`PRESERVE`·`BLOCK`)는 수동 안내에서도
그대로 지켜져야 한다 — 자동일 때만 조심하고 수동일 때 놓으면, 조심의 이유가 사라진 것이 아니라
책임만 사용자에게 넘어간 것이다.

- `DELETE` — 소유권이 증명된 경로만. 삭제 가능
- `STRIP` — **파일 전체 삭제 금지.** SAGE 등록·managed block 만 손으로 제거
- `PRESERVE` — 삭제하지 않는다. 이유를 확인
- `BLOCK` — 수동 삭제를 지시하지 않는다. 입력·경계를 먼저 복구해야 한다

`BLOCK` 이 순서에 없는 이유가 그것이다. 손댈 대상이 아니라 고쳐야 할 상태다.

## 실패한 뒤의 목록은 계획이 아니다

실행이 중간에 실패했다면 일부 action 은 이미 적용됐다. 그때 **의도했던 계획**을 "남은 목록"
이라고 부르면 이미 지워진 것을 다시 지우라고 말하거나, 되돌아온 것을 아직 남았다고 말한다.
그래서 근거(`basis`)를 함께 낸다.

되돌리기까지 실패한 상태(`uncertain`)에서는 삭제 가능 주장을 **하지 않는다.** "지워도 된다" 는
되돌릴 수 없는 조언이고, 확인하지 못한 상태에서 그 말을 하는 것은 추측을 사실로 파는 것이다.

## 이 층이 배열을 복제하지 않는 이유

`--json` 의 `deleted`·`stripped`·`preserved`·`blocked` 가 정본이다. 여기서 같은 경로를 다시
실으면 두 목록이 생기고, 두 목록은 언젠가 갈라진다. 이 값이 말하는 것은 **어떤 순서와 어떤
신뢰도로 그 배열을 읽어야 하는가** 뿐이다.
"""
from sage import uninstall_plan as _plan

# mutation 전에 안전하게 거부했다. 계획은 방금 실제 상태에서 만들어졌으므로 그대로 믿을 수 있다.
BASIS_VERIFIED = "verified_plan"
# 실행이 실패했지만 되돌리기는 성공했다. 되돌린 뒤 다시 읽어 만든 목록이다.
BASIS_POST_ROLLBACK = "post_rollback_plan"
# 요청한 제거는 끝났고 보관소만 남았다. 남은 것은 우리가 만든 임시 파일뿐이다.
BASIS_COMMITTED = "committed_with_leftovers"
# 되돌리기까지 실패했다. 무엇이 남았는지 확정할 수 없다.
BASIS_UNCERTAIN = "uncertain"

BASES = (BASIS_VERIFIED, BASIS_POST_ROLLBACK, BASIS_COMMITTED, BASIS_UNCERTAIN)

# 읽는 순서. 등록을 먼저 치우지 않고 실행 파일을 지우면 host 가 없는 command 를 부른다.
FULL_ORDER = (_plan.STRIP, _plan.DELETE, _plan.PRESERVE)

REGISTRATION_FIRST = "uninstall.notice.remove_registration_first"
NO_DELETE_CLAIM = "uninstall.notice.manual_state_uncertain"


def guidance(plan, *, basis=BASIS_VERIFIED, unknown=(), leftovers=()):
    """수동 정리를 어떤 순서와 신뢰도로 읽어야 하는지. **계획의 경로를 복제하지 않는다.**

    `leftovers` 만 예외다. 그 경로들은 계획의 네 배열 어디에도 없다 — 우리가 실행 중에 만든
    임시 보관소이기 때문이다. 배열에 없는 것을 안내에서도 빼면, commit 뒤 뒷정리가 실패했을 때
    화면은 "치울 것이 있다" 고 말하면서 **무엇을 치울지는 말하지 않는** 상태가 된다.
    """
    if basis not in BASES:
        raise ValueError(f"unknown manual cleanup basis: {basis}")
    counts = {kind: len(plan.of_kind(kind)) for kind in FULL_ORDER}
    order = []
    if basis != BASIS_COMMITTED:
        for kind in FULL_ORDER:
            if kind == _plan.DELETE and basis == BASIS_UNCERTAIN:
                # 확정되지 않은 상태에서 삭제 가능 목록을 내지 않는다.
                continue
            if counts[kind]:
                order.append(kind)
    warnings = []
    if _plan.STRIP in order and _plan.DELETE in order:
        warnings.append(REGISTRATION_FIRST)
    if basis == BASIS_UNCERTAIN:
        warnings.append(NO_DELETE_CLAIM)
    unknown = [str(path) for path in unknown]
    leftovers = [str(path) for path in leftovers]
    return {
        "available": bool(order) or bool(unknown) or bool(leftovers),
        "basis": basis,
        "order": list(order),
        "warning_codes": warnings,
        "unknown": unknown,
        # commit 뒤 치우지 못한 우리 보관소. 지워도 되는 유일한 목록이다 — 요청한 변경은
        # 이미 끝났고 이것들은 우리가 만든 임시 파일이다.
        "leftovers": leftovers,
    }


def applies(plan, executed, leftovers=()):
    """이 결과에 수동 안내가 필요한가.

    성공한 실행과 `--check` 미리보기에는 붙이지 않는다. 붙이면 "자동으로 끝났는데 손으로도
    정리하라" 는 말이 되고, 그 말은 사용자를 안 해도 되는 삭제로 이끈다.
    """
    if leftovers:
        return True
    return not executed and plan.status == _plan.BLOCKED
