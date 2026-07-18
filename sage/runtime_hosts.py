"""Shared profile contract for manual dual-installed, single-active SAGE hosts."""
from __future__ import annotations

from typing import Any

HOSTS = ("claude", "codex")
RUNTIME_KEYS = frozenset({"host", "installed_hosts", "active_host",
                          "external_reviewer", "asset_ssot"})


def active_host(profile: dict[str, Any] | None, default: str = "claude") -> str:
    """Resolve the single active host, preferring the new key over the legacy alias."""
    runtime = profile.get("runtime") if isinstance(profile, dict) else None
    if not isinstance(runtime, dict):
        return default
    active = runtime.get("active_host")
    if active in HOSTS:
        return active
    legacy = runtime.get("host")
    return legacy if legacy in HOSTS else default


def configured_hosts(profile: dict[str, Any] | None) -> list[str]:
    """Return valid desired discovery surfaces; malformed values are reported separately."""
    runtime = profile.get("runtime") if isinstance(profile, dict) else None
    if not isinstance(runtime, dict):
        return [active_host(profile)]
    values = runtime.get("installed_hosts")
    if isinstance(values, list) and values and all(value in HOSTS for value in values):
        return list(dict.fromkeys(values))
    return [active_host(profile)]


def profile_issues(profile: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Validate runtime host semantics without relying on optional jsonschema."""
    if not isinstance(profile, dict):
        return []
    runtime = profile.get("runtime")
    if runtime in (None, ""):
        return []
    if not isinstance(runtime, dict):
        return [("FAIL", f"runtime 은 매핑이어야 함 (받음: {type(runtime).__name__})")]
    issues = []
    unknown = sorted((key for key in runtime if key not in RUNTIME_KEYS), key=str)
    if unknown:
        issues.append(("FAIL", f"runtime 의 알 수 없는 키: {unknown} (허용: {sorted(RUNTIME_KEYS)})"))
    legacy = runtime.get("host")
    active = runtime.get("active_host")
    for key, value in (("host", legacy), ("active_host", active)):
        if value is not None and value not in HOSTS:
            issues.append(("FAIL", f"runtime.{key}={value!r} — {list(HOSTS)} 중 하나여야 함"))
    if legacy in HOSTS and active in HOSTS and legacy != active:
        issues.append(("FAIL", "runtime.host legacy alias와 runtime.active_host가 다름 — active host 정본이 모호함"))

    hosts = runtime.get("installed_hosts")
    if hosts is not None:
        if (not isinstance(hosts, list) or not hosts
                or any(host not in HOSTS for host in hosts)
                or len(set(hosts)) != len(hosts)):
            issues.append(("FAIL", "runtime.installed_hosts는 non-empty unique [claude|codex] 배열이어야 함"))
        else:
            resolved = active_host(profile)
            if resolved not in hosts:
                issues.append(("FAIL", f"runtime.active_host={resolved!r}가 installed_hosts에 없음"))
            options = profile.get("options")
            cross = options.get("cross_model") if isinstance(options, dict) else False
            if len(hosts) > 1 and cross is not True:
                issues.append(("WARN", "double-host 구성인데 options.cross_model=true가 아님 — "
                                       "반대 runtime 독립 리뷰를 강하게 권장"))
    return issues


def opposite_host(profile: dict[str, Any] | None) -> str:
    return "codex" if active_host(profile) == "claude" else "claude"


def receipt_hosts(manifest: dict[str, Any] | None, fallback: str = "claude") -> list[str]:
    values = manifest.get("installed_hosts") if isinstance(manifest, dict) else None
    if not isinstance(values, list):
        legacy = manifest.get("host_runtime") if isinstance(manifest, dict) else fallback
        values = [legacy]
    return list(dict.fromkeys(host for host in values if host in HOSTS)) or [fallback]


def receipt_issues(profile: dict[str, Any] | None,
                   manifest: dict[str, Any] | None) -> list[tuple[str, str]]:
    desired = configured_hosts(profile)
    active = active_host(profile)
    actual = receipt_hosts(manifest, active)
    issues = []
    if set(actual) != set(desired):
        issues.append(("WARN", f"profile desired_hosts={desired}와 install receipt={actual} 불일치"))
    if active not in actual:
        issues.append(("WARN", f"active_host={active}의 discovery surface가 install receipt에 없음"))
    return issues
