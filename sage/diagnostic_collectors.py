"""`sage status` 가 읽는 7 영역 — 조회만 한다.

## 이 모듈이 하지 않는 것

**판정하지 않는다.** 각 영역의 판정 정본은 이미 저장소에 있다 — `version_contract`,
`profile_layers`, `runtime_hosts`, `runtime_api`, `cycle_state`. 여기서 하는 일은 그것들을
부르고 결과를 같은 계약(`Finding`)으로 옮겨 담는 것뿐이다.

`doctor.run()` 이나 `validate.run()` 을 subprocess 로 부르고 stdout 을 다시 파싱하는 구현은
금지다. 그건 판정을 문자열로 되돌리는 짓이고, 문자열은 언어를 탄다 — 같은 저장소 상태가
사용자 언어에 따라 다른 status 를 내게 된다.

## 예외를 밖으로 던지지 않는다

collector 는 파일을 읽되 예외를 올리지 않고 진단으로 바꾼다. `status` 가 스스로 죽으면
사용자는 아무 다음 행동도 받지 못한다 — 진단 도구가 진단 불가로 죽는 것이 가장 나쁜 실패다.

## 부재를 통과로 읽지 않는다

읽지 못한 필수 입력은 "없음" 이 아니라 BLOCK 이다. 부재를 안전한 방향으로 해석하면 READY 가
거짓말이 된다.
"""
from __future__ import annotations

import json
import os

from sage.diagnostic_contract import Finding

_MANIFEST_REL = ("docs", "sage_harness", ".manifest.json")
_PROFILE_YAML_REL = ("sage", "project-profile.yaml")
_PROFILE_JSON_REL = ("sage", "project-profile.json")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle), None
    except FileNotFoundError:
        return None, "absent"
    except (OSError, ValueError) as exc:
        return None, type(exc).__name__


def read_manifest(root):
    return _read_json(os.path.join(root, *_MANIFEST_REL))


def collect_project(root, manifest, manifest_error):
    """설치 대상인가. 아니면 나머지 영역은 물어볼 것도 없다."""
    facts = {"installed": bool(isinstance(manifest, dict) and manifest.get("assets") is not None)}
    if manifest_error == "absent":
        return facts, (Finding("project.not_installed"),)
    if manifest_error:
        return facts, (Finding("project.manifest_unreadable",
                               evidence={"error": manifest_error}),)
    if not isinstance(manifest, dict):
        return facts, (Finding("project.manifest_not_mapping"),)
    return facts, ()


def collect_version(profile, manifest, runtime_version):
    """정본은 `version_contract`. severity 도 거기서 온다 — 여기서 다시 정하지 않는다."""
    from sage.version_contract import version_axes, version_contract_issues

    axes = version_axes(profile, manifest, runtime_version)
    facts = {"required": axes.required, "runtime": axes.runtime,
             "installed": axes.installed, "generated": axes.generated}
    findings = tuple(
        Finding(issue.message.code,
                evidence={"axis": issue.axis, "current": issue.current,
                          "required": issue.required},
                arguments=dict(issue.message.arguments))
        for issue in version_contract_issues(profile, manifest, runtime_version))
    return facts, findings


def collect_runtime_api(manifest):
    """`sage-hook` 이 실행 시점에 쓰는 것과 **같은** 순수 함수를 쓴다.

    여기서 따로 해석하면 status 가 READY 라고 한 설치를 hook 이 막는 상태가 만들어진다.
    """
    from sage.runtime_api import HOOK_RUNTIME_API, compatibility

    if not isinstance(manifest, dict):
        return {"current": HOOK_RUNTIME_API, "required": None, "compatible": None}, ()
    status, evidence = compatibility(manifest)
    facts = {"current": HOOK_RUNTIME_API,
             "required": evidence.get("required_api"),
             "compatible": status in ("ok", "legacy")}
    if status == "ok":
        return facts, ()
    if status == "legacy":
        return facts, (Finding("runtime.api_marker_absent_legacy", evidence=dict(evidence)),)
    if status == "too_old":
        return facts, (Finding("runtime.api_too_old", evidence=dict(evidence),
                               arguments={"required": evidence.get("required_api"),
                                          "current": evidence.get("current_api")}),)
    reason = evidence.get("reason")
    code = ("runtime.api_marker_missing"
            if reason in ("marker_missing", "marker_missing_version_unreadable")
            else "runtime.api_marker_damaged")
    return facts, (Finding(code, evidence=dict(evidence),
                           arguments={"reason": reason or "unknown"}),)


def collect_profile(root):
    """shared 는 필수, local 은 선택. compiled 는 shared 에서 재생성 가능해야 한다."""
    from sage.profile_layers import load_profile_layers

    shared_path = os.path.join(root, *_PROFILE_YAML_REL)
    compiled_path = os.path.join(root, *_PROFILE_JSON_REL)
    facts = {"shared": "absent", "local": "absent", "compiled": "absent"}

    if not os.path.exists(shared_path):
        return facts, (Finding("profile.shared_missing"),)
    try:
        layers = load_profile_layers(shared_path)
    except Exception as exc:                                   # 판독 실패는 진단으로 표면화한다
        facts["shared"] = "unreadable"
        return facts, (Finding("profile.shared_invalid",
                               evidence={"error": type(exc).__name__}),)

    facts["shared"] = "loaded"
    findings = []
    for severity, message in layers.issues:
        code = "profile.layer_invalid" if severity == "FAIL" else "profile.layer_warning"
        findings.append(Finding(code, evidence={"severity": severity},
                                arguments={"detail": message}))
    if layers.local is not None:
        facts["local"] = "loaded"

    compiled, compiled_error = _read_json(compiled_path)
    if compiled_error == "absent":
        facts["compiled"] = "absent"
        findings.append(Finding("profile.compiled_missing"))
    elif compiled_error:
        facts["compiled"] = "unreadable"
        findings.append(Finding("profile.compiled_unreadable",
                                evidence={"error": compiled_error}))
    else:
        facts["compiled"] = "loaded"
        # freshness 는 "지금 shared 에서 만든 것과 같은가" 다. 다르면 게이트가 읽는 값과
        # 사람이 편집한 값이 갈라져 있다는 뜻이고, 그건 판정이 낡았다는 신호다.
        try:
            from sage.profile_compile import materialize_profile
            if materialize_profile(layers.effective) != compiled:
                facts["compiled"] = "stale"
                findings.append(Finding("profile.compiled_stale"))
        except Exception as exc:
            findings.append(Finding("profile.compiled_uncomparable",
                                    evidence={"error": type(exc).__name__}))
    return facts, tuple(findings)


def collect_host(profile, manifest):
    from sage.runtime_hosts import active_host, configured_hosts

    try:
        active = active_host(profile) if isinstance(profile, dict) else None
        configured = configured_hosts(profile) if isinstance(profile, dict) else []
    except Exception as exc:
        return {"active": None, "configured": []}, (
            Finding("host.profile_unreadable", evidence={"error": type(exc).__name__}),)

    facts = {"active": active, "configured": list(configured)}
    findings = []
    installed = manifest.get("installed_hosts") if isinstance(manifest, dict) else None
    if isinstance(installed, list) and active and active not in installed:
        # 활성 host 에 설치 흔적이 없다 — hook 이 등록되지 않았을 가능성이 높다.
        findings.append(Finding("install.hook_registration_missing",
                                evidence={"active": active, "installed": list(installed)},
                                arguments={"host": active}))
    return facts, tuple(findings)


def collect_cycle(root):
    """선언 부재는 정상이다. 손상은 정상이 아니다."""
    from sage import _resources
    import sys

    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    for path in (os.path.join(hooks, "runtime"), hooks):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        import cycle_state
    except Exception as exc:
        return {"stem": None}, (Finding("cycle.state_unavailable",
                                        evidence={"error": type(exc).__name__}),)

    try:
        record = cycle_state.read_declaration_record(root)
    except Exception as exc:
        return {"stem": None}, (Finding("cycle.declaration_unreadable",
                                        evidence={"error": type(exc).__name__}),)

    if record.error:
        return {"stem": None, "risk": None}, (
            Finding("cycle.declaration_damaged", evidence={"error": str(record.error)}),)
    stem = record.stem or None
    facts = {"stem": stem,
             "risk": _declared_risk(root, stem),
             "document_language": record.document_language,
             "legacy": bool(record.legacy)}
    return facts, ()


# 승인 설계 §5.2 는 cycle 영역에 mode(STANDARD/FAST)도 싣기를 요구했다. **싣지 않는다.**
#
# Fast 감사를 읽는 유일한 정본(`fast_cycle_audit`)은 읽기에도 audit lock 을 잡는다 — 일관된
# 스냅샷을 얻기 위한 설계이고, 그 자체는 옳다. 문제는 그것을 `status` 가 부르면 두 가지가
# 따라온다는 것이다.
#
#   1. `.sage` 에 lock 파일이 생긴다. 읽기 전용이 아니게 된다(G2).
#   2. 진행 중인 Fast 전이와 락 경쟁을 한다. 1~2초를 약속한 조회 명령이 실제 작업을 기다리게
#      되고, 반대로 실제 작업이 조회를 기다릴 수도 있다.
#
# JSONL 을 직접 파싱해 우회할 수는 있지만, 그건 감사 형식의 두 번째 해석기를 만드는 일이다.
# 이 사이클이 `path_risk` 와 `risk_declaration` 에서 피한 바로 그 형태다.
#
# 그래서 mode 는 그 질문을 이미 소유한 명령에 맡긴다 — `sage cycle show` 와
# `sage fast-cycle show`. 이건 알려진 한계이고 Phase 04 §3 에 기록돼 있다.


def _declared_risk(root, stem):
    """Phase 00 이 선언한 실제 위험도. 못 읽으면 `None`.

    선언 해석은 `risk_declaration` 하나가 소유한다 — 저장소에 두 번째 해석기를 만들지
    않는다. 여기서는 그 결과를 표시할 뿐이고, 선언이 잘못됐다는 판정은 게이트가 내린다.
    """
    if not stem:
        return None
    import glob as globlib

    from sage.commands._common import _load_profile_yaml
    profile = _load_profile_yaml(os.path.join(root, "sage", "project-profile.yaml"))
    if not isinstance(profile, dict):
        return None
    phases = (profile.get("pdca") or {}).get("phases") or []
    pattern = next((entry.get("glob") for entry in phases
                    if isinstance(entry, dict) and str(entry.get("id")) == "00"), None)
    if not pattern:
        return None
    try:
        import cycle_binding
        import risk_declaration
    except Exception:
        return None
    # `select_document` 은 경로 문자열이 아니라 {"path", "content"} 를 받는다. 문서 내부의
    # Cycle-Stem 선언과 파일명 stem 이 함께 맞아야 결속으로 인정하기 때문이다 — 파일명만
    # 보면 이름만 바꿔 다른 사이클의 문서를 지목할 수 있다.
    candidates = []
    for path in globlib.glob(os.path.join(root, pattern), recursive=True):
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
        except OSError:
            continue
        candidates.append({"path": os.path.relpath(path, root).replace(os.sep, "/"),
                           "content": content})
    document, error = cycle_binding.select_document(candidates, stem)
    if error or not document:
        return None
    content = document.get("content") if isinstance(document, dict) else None
    if content is None:
        return None
    declaration = risk_declaration.parse(content)
    return declaration.tier if declaration.status == "valid" else None
