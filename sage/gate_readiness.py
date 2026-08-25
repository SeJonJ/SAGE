"""구현 전에 요구되는 phase 가 실제로 있는가 — `status` 와 `explain` 의 공용 정본.

두 명령이 각자 계산하면 정본이 둘이 된다. 같은 저장소에서 `status` 는 "준비됐다" 고 하고
`explain` 은 "02 가 없다" 고 말하는 상태가 만들어지고, 그때 어느 쪽이 옳은지 판정할 근거가
없다. 그래서 경로 위험도를 `path_risk` 하나로 모은 것과 같은 이유로 여기 모은다.

문서 결속 판정은 이 모듈이 직접 하지 않고 `cycle_binding.select_document` 를 부른다 —
게이트가 쓰는 바로 그 함수여야, 여기서 "있다" 고 센 문서를 게이트가 "다른 사이클" 로
거부하는 어긋남이 생기지 않는다.
"""
import glob as globlib
import os
import sys

from sage import _resources


class ReadinessUnavailable(Exception):
    """준비 상태를 **판정하지 못했다.** 준비됐다는 뜻도, 안 됐다는 뜻도 아니다.

    이 예외가 따로 있는 이유는 게이트의 정상 답과 모양이 같아지는 것을 막기 위해서다.
    `_fast_cycle_state` 는 "Fast 가 아니다" 를 `(None, detail)` 로 돌려준다. 판정 자체가
    실패했을 때도 같은 모양으로 접으면 두 상태가 구별되지 않고, 호출부는 "Fast 가 아니다"
    로 읽어 Standard 문서만 세다가 전부 있으면 조용히 통과시킨다 — 판정 실패가 준비 완료로
    보이는 방향의 실패다.
    """


def _load(module):
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    for path in (os.path.join(hooks, "runtime"), hooks):
        if path not in sys.path:
            sys.path.insert(0, path)
    return __import__(module)


def required_phases(profile, risk):
    """이 위험도가 구현 전에 요구하는 phase id 목록. pdca 비활성이면 None.

    `None` 과 `[]` 는 다르다 — 전자는 "이 프로젝트는 PDCA 를 쓰지 않는다", 후자는
    "쓰지만 이 위험도엔 요구가 없다" 다. 호출부가 둘을 구분해야 하므로 접지 않는다.
    """
    pdca = profile.get("pdca") or {}
    if not pdca.get("enabled") or not pdca.get("phases"):
        return None
    return list((pdca.get("pre_implementation_required") or {}).get(risk) or [])


def _phase_documents(root, profile, phase_id):
    """이 phase 의 후보 문서들. 게이트 snapshot 과 같은 모양({path, content})."""
    phases = {str(entry.get("id")): entry
              for entry in (profile.get("pdca") or {}).get("phases", [])
              if isinstance(entry, dict)}
    pattern = (phases.get(phase_id) or {}).get("glob")
    documents = []
    for path in (globlib.glob(os.path.join(root, pattern), recursive=True)
                 if pattern else []):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
        except OSError:
            continue
        documents.append({"path": os.path.relpath(path, root).replace(os.sep, "/"),
                          "content": content})
    return documents


def fast_state(root, profile, stem):
    """(state, detail). 게이트가 쓰는 **바로 그** 검증을 통과한 Fast state 또는 None.

    leaf predicate(`_fast_covers_required`) 하나만 부르면 안 된다. 게이트는 그 앞에서
    composite Fast Plan 파싱, policy 활성, run binding, hash chain, risk 일치를 모두
    확인하고, 그중 하나만 어긋나도 Fast 를 인정하지 않는다. 마지막 조각만 부르면 게이트가
    거부하는 프로젝트를 조회가 "준비됨" 으로 표시한다.

    감사는 락 없는 `snapshot` 으로 읽는다 — 판정 로직은 게이트와 같고, 읽는 방법만 다르다.

    판정이 실패하면 `ReadinessUnavailable` 을 올린다. 삼키고 `(None, detail)` 을 돌려주면
    "Fast 가 아니다" 와 구별되지 않는다.
    """
    try:
        gate = _load("pre_implementation_gate_core")
        audit = _load("fast_cycle_audit")
        cfg = (profile.get("pdca") or {})
        snapshot = {"phase_docs": {"00": _phase_documents(root, profile, "00")},
                    "fast_cycle_audit": audit.snapshot(root)}
        event = {"changes": [], "cycle_stem": stem}
        return gate._fast_cycle_state(event, profile, snapshot, cfg)
    except ReadinessUnavailable:
        raise
    except Exception as exc:
        raise ReadinessUnavailable(f"{type(exc).__name__}: {exc}") from exc


def fast_exemption(root, profile, stem, required):
    """(면제 여부, 게이트가 낼 차단 사유). 게이트의 판정을 그대로 쓴다.

    이 면제를 모르면 정상 Fast 사이클이 조회 화면에서 "01·02 가 없다" 로 보인다. 반대로
    게이트의 앞선 검증을 건너뛰면 게이트가 막는 프로젝트를 준비됐다고 말한다. 둘 다
    사용자가 화면을 믿지 못하게 만든다.

    **두 번째 값을 버리면 안 된다.** `_fast_cycle_state` 가 사유를 돌려준 상태에서 게이트는
    요구 phase 문서가 전부 있어도 차단한다(`block_fast_cycle_audit`). 그 사유를 버리고
    Standard 문서만 세면, Fast 선언이 깨진 저장소가 문서를 다 갖춘 덕에 조회에서 비차단으로
    보인다 — 게이트는 막는데 화면은 통과라고 말하는, 이 모듈이 없애려던 바로 그 어긋남이다.
    """
    if not required:
        return False, None
    state, detail = fast_state(root, profile, stem)
    if detail:
        # 사유가 있으면 게이트는 막는다. 면제 여부를 따질 자리가 아니다.
        return False, detail
    if state is None or not set(required).issubset({"00", "01", "02", "03"}):
        return False, None
    gate = _load("pre_implementation_gate_core")
    return bool(gate._fast_covers_required(state, required)), None


def phase_readiness(root, profile, stem, required):
    """(present, missing, fast_error). 세 번째는 게이트가 Fast 경로에서 낼 차단 사유다.

    판정할 수 없으면 `ReadinessUnavailable` 을 올린다 — 빈 `missing` 은 "요구가 충족됐다"
    는 적극적 사실이라, 판정 실패를 그 자리에 놓으면 부재가 통과로 떨어진다.

    `fast_error` 가 두 값과 나란히 서는 이유는 그것도 **차단 사유**이기 때문이다. 문서가
    다 있다는 사실과 Fast 선언이 깨졌다는 사실은 둘 다 참일 수 있고, 뒤쪽만으로도 게이트는
    막는다.
    """
    if not required:
        return [], [], None
    exempt, fast_error = fast_exemption(root, profile, stem, required)
    if exempt:
        return list(required), [], None
    if not stem:
        return [], list(required), fast_error
    try:
        cycle_binding = _load("cycle_binding")
    except Exception as exc:
        raise ReadinessUnavailable(f"{type(exc).__name__}: {exc}") from exc
    phases = {str(entry.get("id")): entry
              for entry in (profile.get("pdca") or {}).get("phases", [])
              if isinstance(entry, dict)}
    present, missing = [], []
    for pid in required:
        pattern = (phases.get(pid) or {}).get("glob")
        candidates = []
        for path in (globlib.glob(os.path.join(root, pattern), recursive=True)
                     if pattern else []):
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as handle:
                    content = handle.read()
            except OSError:
                continue
            # phase 문서의 내용을 읽는 것은 대상 경로의 내용을 읽는 것과 다르다. 결속 판정이
            # 문서 안의 Cycle-Stem 선언을 요구하고, 게이트도 같은 것을 읽는다.
            candidates.append({"path": os.path.relpath(path, root).replace(os.sep, "/"),
                               "content": content})
        document, error = cycle_binding.select_document(candidates, stem)
        (missing if (error or not document) else present).append(pid)
    return present, missing, fast_error
