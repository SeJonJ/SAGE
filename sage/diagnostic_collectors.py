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
    _ensure_hook_path()
    try:
        import cycle_state
    except Exception as exc:
        return {"stem": None}, (Finding("cycle.state_unavailable",
                                        evidence={"error": type(exc).__name__},
                                        arguments={"error": f"{type(exc).__name__}: {exc}"[:160]}),)

    try:
        record = cycle_state.read_declaration_record(root)
    except Exception as exc:
        return {"stem": None}, (Finding("cycle.declaration_unreadable",
                                        evidence={"error": type(exc).__name__}),)

    if record.error:
        return {"stem": None, "risk": None}, (
            Finding("cycle.declaration_damaged", evidence={"error": str(record.error)}),)
    stem = record.stem or None
    mode, mode_evidence, mode_error = _cycle_mode(root, stem)
    facts = {"stem": stem,
             "mode": mode,
             "risk": _declared_risk(root, stem),
             "document_language": record.document_language,
             "legacy": bool(record.legacy)}
    findings = ()
    if mode_error:
        # 판정이 터진 것은 프로젝트 상태가 아니라 도구 실패다. `cycle.mode_unknown` 으로
        # 내면 손상된 감사와 같은 자리에 놓이고, 사용자는 고칠 것이 없는 곳을 고치러 간다.
        findings = (Finding("cycle.mode_unavailable",
                            evidence=dict(mode_evidence),
                            arguments={"error": mode_error}),)
    elif mode == "UNKNOWN":
        findings = (Finding("cycle.mode_unknown", evidence=mode_evidence),)
    return facts, findings


def _ensure_hook_path():
    """hook 런타임 모듈을 import 할 수 있게 한다.

    각 collector 가 직접 부른다 — 다른 collector 가 먼저 실행되면서 남긴 sys.path 부작용에
    기대면, 호출 순서를 바꾸거나 한 영역이 실패했을 때 조용히 import 가 깨진다.
    """
    import sys

    from sage import _resources
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    for path in (os.path.join(hooks, "runtime"), hooks):
        if path not in sys.path:
            sys.path.insert(0, path)


def _cycle_mode(root, stem):
    """(mode, evidence, tool_error). STANDARD | FAST | UNKNOWN.

    Fast 감사를 읽되 **락을 잡지 않는다.** 락 경로(`audit_summary`)는 `.sage/` 와 `.lock`
    파일을 만들고 진행 중인 전이를 기다린다 — 읽기 전용을 약속한 조회 명령이 할 일이 아니다.
    그래서 정본 모듈 안에 락 없는 `mode_for_stem` 을 두고 그것을 쓴다. 여기서 JSONL 을 직접
    파싱하면 감사 형식의 두 번째 해석기가 생기므로 그 길은 택하지 않았다.

    못 읽거나 깨진 감사는 STANDARD 로 낮추지 않고 UNKNOWN 이다. 부재를 정상으로 접으면
    손상된 감사가 조용히 "일반 사이클" 로 보인다.
    """
    _ensure_hook_path()
    try:
        import fast_cycle_audit
    except Exception as exc:
        return "UNKNOWN", {"error": type(exc).__name__}, f"{type(exc).__name__}: {exc}"
    try:
        mode, evidence = fast_cycle_audit.mode_for_stem(root, stem)
    except Exception as exc:
        return "UNKNOWN", {"error": type(exc).__name__}, f"{type(exc).__name__}: {exc}"
    return mode, evidence, None


def collect_gate(root, profile, risk, stem):
    """구현 전 요구 phase 가 실제로 있는가. `explain` 과 같은 정본을 쓴다.

    이 영역이 없으면 `status` 는 "필수 phase 가 통째로 없는 저장소" 를 ATTENTION 으로
    통과시킨다 — 사용자가 "지금 쓸 수 있는가" 를 묻는 명령이 가장 흔한 차단 원인을
    비차단으로 표시하는 셈이다.
    """
    from sage import gate_readiness

    required = gate_readiness.required_phases(profile, risk)
    if required is None:
        return {"required_phases": None, "present": (), "missing": (),
                "fast_cycle_error": None}, ()
    try:
        present, missing, fast_error = gate_readiness.phase_readiness(
            root, profile, stem, required)
    except Exception as exc:
        # 판정하지 못한 것을 "요구 없음" 으로 접지 않는다. `missing` 이 비어 있다는 것은
        # 요구가 충족됐다는 적극적 사실이고, 여기서 그 자리를 빌려 쓰면 판정 실패가 화면에서
        # 준비 완료와 같아진다.
        return ({"required_phases": tuple(required), "present": (), "missing": (),
                 "fast_cycle_error": None},
                (Finding("gate.readiness_unavailable",
                         evidence={"error": type(exc).__name__, "detail": str(exc)[:200]},
                         arguments={"error": f"{type(exc).__name__}: {str(exc)[:160]}"}),))
    facts = {"required_phases": tuple(required),
             "present": tuple(present), "missing": tuple(missing),
             "fast_cycle_error": fast_error}
    findings = []
    if fast_error:
        # 게이트는 이 사유 하나로 막는다 — 요구 문서가 전부 있어도. 그래서 `missing` 이
        # 비었는지와 무관하게 올린다.
        findings.append(Finding("gate.fast_cycle_invalid",
                                evidence={"reason": str(fast_error)[:300]},
                                arguments={"reason": str(fast_error)[:300]}))
    if missing:
        findings.append(Finding("gate.phase_incomplete",
                                evidence={"missing": ", ".join(missing)},
                                arguments={"miss": ", ".join(missing)}))
    return facts, tuple(findings)


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
    _ensure_hook_path()
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
