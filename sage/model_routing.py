"""Static model routing contract shared by profile validation and runtime consumers."""
from __future__ import annotations

import re
from typing import Any

from sage.runtime_hosts import HOSTS, active_host, configured_hosts, opposite_host

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_COMPONENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_COMPONENT_KEYS = frozenset({"id", "paths", "model", "runtime_models"})
_REVIEWER_KEYS = frozenset({"host", "model"})


def _valid_model(value: Any) -> bool:
    return isinstance(value, str) and bool(_MODEL_RE.fullmatch(value))


def _valid_component_path(value: Any) -> bool:
    if (not isinstance(value, str) or not value.strip() or len(value) > 512
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        return False
    return all(part not in ("", ".", "..") for part in normalized.split("/"))


def component_model(component: dict[str, Any] | None, host: str) -> str | None:
    models = component.get("runtime_models") if isinstance(component, dict) else None
    value = models.get(host) if isinstance(models, dict) else None
    return value if _valid_model(value) else None


def reviewer_selection(profile: dict[str, Any] | None) -> tuple[str, str | None]:
    peer = opposite_host(profile)
    cross = profile.get("cross_model") if isinstance(profile, dict) else None
    reviewer = cross.get("reviewer") if isinstance(cross, dict) else None
    if not isinstance(reviewer, dict):
        return peer, None
    host = reviewer.get("host")
    model = reviewer.get("model")
    return (host if host in HOSTS else peer, model if _valid_model(model) else None)


def component_issues(profile: dict[str, Any] | None) -> list[tuple[str, str]]:
    if not isinstance(profile, dict):
        return []
    components = profile.get("components")
    if components is None:
        return []
    if not isinstance(components, list):
        return [("FAIL", f"components 는 배열이어야 함 (받음: {type(components).__name__})")]
    issues = []
    active = active_host(profile)
    installed = set(configured_hosts(profile))
    seen_ids = set()
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            issues.append(("FAIL", f"components[{index}]는 매핑이어야 함"))
            continue
        unknown_keys = sorted((key for key in component if key not in _COMPONENT_KEYS), key=str)
        if unknown_keys:
            issues.append(("FAIL", f"components[{index}]의 알 수 없는 키: {unknown_keys} "
                                   f"(허용: {sorted(_COMPONENT_KEYS)})"))
        cid = component.get("id")
        label = cid if isinstance(cid, str) and cid.strip() else f"index {index}"
        if not isinstance(cid, str) or not _COMPONENT_ID_RE.fullmatch(cid):
            issues.append(("FAIL", f"components[{index}].id={cid!r} — 경로 안전 토큰 "
                                   "[A-Za-z0-9][A-Za-z0-9_-]{0,79} 필요"))
        elif cid in seen_ids:
            issues.append(("FAIL", f"component id 중복: {cid!r}"))
        else:
            seen_ids.add(cid)
        paths = component.get("paths")
        if paths is not None and (not isinstance(paths, list)
                                  or any(not _valid_component_path(path) for path in paths)):
            issues.append(("FAIL", f"component {label} paths는 제어문자/절대경로/부모경로가 없는 "
                                   "512자 이하 repository-relative glob 배열이어야 함"))
        tier = component.get("model")
        if tier is not None and not _valid_model(tier):
            issues.append(("FAIL", f"component {label} model={tier!r} — 안전한 work-intensity/model 토큰 필요"))
        models = component.get("runtime_models")
        if models is None:
            continue
        if not isinstance(models, dict) or not models:
            issues.append(("FAIL", f"component {label} runtime_models는 non-empty host:model 매핑이어야 함"))
            continue
        unknown = sorted((host for host in models if host not in HOSTS), key=str)
        if unknown:
            issues.append(("FAIL", f"component {label} runtime_models의 알 수 없는 host: {unknown}"))
        for host, model in models.items():
            if host in HOSTS and not _valid_model(model):
                issues.append(("FAIL", f"component {label} runtime_models.{host}={model!r} — 유효한 model id 필요"))
            if host in HOSTS and host not in installed:
                issues.append(("WARN", f"component {label} runtime_models.{host}는 installed_hosts에 없는 host 설정"))
        if active not in models:
            issues.append(("WARN", f"component {label} runtime_models에 active_host={active} 선택 없음 — host 기본 모델 사용"))
    return issues


def reviewer_issues(profile: dict[str, Any] | None) -> list[tuple[str, str]]:
    if not isinstance(profile, dict):
        return []
    options = profile.get("options")
    enabled = options.get("cross_model") if isinstance(options, dict) else False
    cross = profile.get("cross_model")
    if cross is None:
        return ([('WARN', "options.cross_model=true 이지만 cross_model.reviewer host/model 미선택 "
                          "→ opposite runtime의 CLI 기본 모델 사용(인터뷰에서 명시 선택 권장)")]
                if enabled is True else [])
    if not isinstance(cross, dict):
        return []
    reviewer = cross.get("reviewer")
    if reviewer is None:
        return ([('WARN', "options.cross_model=true 이지만 cross_model.reviewer host/model 미선택 "
                          "→ opposite runtime의 CLI 기본 모델 사용(인터뷰에서 명시 선택 권장)")]
                if enabled is True else [])
    if not isinstance(reviewer, dict):
        return [("FAIL", f"cross_model.reviewer는 매핑이어야 함 (받음: {type(reviewer).__name__})")]
    issues = []
    unknown = sorted((key for key in reviewer if key not in _REVIEWER_KEYS), key=str)
    if unknown:
        issues.append(("FAIL", f"cross_model.reviewer의 알 수 없는 키: {unknown}"))
    if set(reviewer) & _REVIEWER_KEYS != _REVIEWER_KEYS:
        issues.append(("FAIL", "cross_model.reviewer는 host와 model을 모두 명시해야 함"))
        return issues
    host = reviewer.get("host")
    model = reviewer.get("model")
    if host not in HOSTS:
        issues.append(("FAIL", f"cross_model.reviewer.host={host!r} — {list(HOSTS)} 중 하나여야 함"))
    elif host != opposite_host(profile):
        issues.append(("FAIL", f"cross_model.reviewer.host={host!r}는 active_host의 opposite runtime이 아님"))
    if not _valid_model(model):
        issues.append(("FAIL", f"cross_model.reviewer.model={model!r} — 유효한 model id 필요"))
    if enabled is not True:
        issues.append(("WARN", "cross_model.reviewer가 설정됐지만 options.cross_model=false → reviewer 선택 무동작"))
    return issues


def profile_issues(profile: dict[str, Any] | None) -> list[tuple[str, str]]:
    return component_issues(profile) + reviewer_issues(profile)


def catalog_status(catalog: dict[str, Any], model: str) -> str:
    ids = {item.get("id") for item in catalog.get("candidates", []) if isinstance(item, dict)}
    if catalog.get("verification") == "cache-confirmed":
        return "confirmed" if model in ids else "not-in-local-catalog"
    if catalog.get("verification") == "syntax-only/account-unverified":
        return "syntax-only/account-unverified" if model in ids else "account-unverified"
    return "discovery-unavailable"
