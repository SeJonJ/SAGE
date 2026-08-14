"""Shared profile contract for manual dual-installed, single-active SAGE hosts."""
from __future__ import annotations

import os
from typing import Any

from sage.diagnostics import Diagnostic

HOSTS = ("claude", "codex")
RUNTIME_KEYS = frozenset({"host", "installed_hosts", "active_host",
                          "external_reviewer", "asset_ssot"})

# `active_host` 를 팀 공유 프로필에 고정하는 것은 dual-host 에서 범주 오류다 — 어느 host 로 일하는지는
# 개발자별·세션별 사실인데 shared profile 은 커밋되고 local profile 은 이 키를 덮을 수 없다
# (profile_layers._SECTION_KEYS). AUTO 는 그 값을 런타임 관측으로 미루겠다는 선언이다.
AUTO = "auto"

# 현재 세션 host 를 알려주는 env 표식. host CLI 가 자기 프로세스에 심는 값이라 프로필과 달리 위조·노후화가 없다.
_HOST_MARKERS = {
    "claude": ("CLAUDECODE",),
    "codex": ("CODEX_SANDBOX", "CODEX_CI", "CODEX_THREAD_ID"),
}
# SAGE 가 peer 를 spawn 할 때 심는 표식. 자식 프로세스는 부모 env 를 상속하므로 marker 존재만으로는
# claude→codex 와 codex→claude 를 구분할 수 없다(실측: 두 계열이 동시에 관측됨). spawn 측이
# 부모 표식을 지우고 이 값을 심어, SAGE 를 경유한 중첩만은 모호해지지 않게 한다.
HOST_ENV_VAR = "SAGE_HOST"


def detect_current_host(environ: dict[str, str] | None = None) -> str | None:
    """실제 실행 중인 host, 판별 불가면 None.

    두 계열 표식이 동시에 존재하면 중첩 실행이고, env 만으로는 어느 쪽이 안쪽인지 알 수 없다.
    이때 한쪽을 고르면 조용히 틀린 답이 나오므로 판별 실패(None)로 둔다 — 호출자는 프로필 값이나
    기존 폴백으로 내려간다.
    """
    env = os.environ if environ is None else environ
    explicit = (env.get(HOST_ENV_VAR) or "").strip().lower()
    if explicit in HOSTS:
        return explicit
    seen = [host for host, markers in _HOST_MARKERS.items()
            if any(env.get(marker) for marker in markers)]
    return seen[0] if len(seen) == 1 else None


def peer_env(peer: str, environ: dict[str, str] | None = None) -> dict[str, str]:
    """peer 프로세스에 넘길 환경 — 부모 host 표식을 지우고 peer 를 명시한다."""
    env = dict(os.environ if environ is None else environ)
    for markers in _HOST_MARKERS.values():
        for marker in markers:
            env.pop(marker, None)
    env[HOST_ENV_VAR] = peer
    return env


def running_host(profile: dict[str, Any] | None, explicit: str | None = None) -> str | None:
    """독립성 판정에 쓸 "지금 도는 host" — 확신할 수 없으면 None(추측하지 않는다).

    `active_host()` 와 갈라놓는 이유: 그쪽은 항상 문자열을 돌려주려고 default 까지 동원하는데,
    리뷰어 선택은 그 default 가 틀리는 순간 자기 자신에게 리뷰를 맡기게 된다. 실제로 중첩 실행에서
    표식이 뒤섞이면 판별이 실패하고, 그때 프로필 default 로 내려가면 실행 중인 host 를 peer 로
    다시 고르는 경로가 열린다. 그래서 여기서는 근거가 없으면 없다고 말한다.

    근거 순서: 호출자가 명시한 값 → env 관측 → 프로필의 명시 pin → 유일한 installed host.
    """
    if explicit in HOSTS:
        return explicit
    detected = detect_current_host()
    if detected is not None:
        return detected
    declared = declared_active_host(profile)
    if declared is not None:
        return declared
    hosts = declared_installed_hosts(profile)
    return hosts[0] if hosts is not None and len(hosts) == 1 else None


def declared_active_host(profile: dict[str, Any] | None) -> str | None:
    """프로필이 명시한 host. `auto`·부재·오타는 None(= 선언 없음)."""
    runtime = profile.get("runtime") if isinstance(profile, dict) else None
    if not isinstance(runtime, dict):
        return None
    active = runtime.get("active_host")
    if active in HOSTS:
        return active
    if isinstance(active, str) and active.strip().lower() == AUTO:
        return None
    legacy = runtime.get("host")
    return legacy if legacy in HOSTS else None


def active_host(profile: dict[str, Any] | None, default: str = "claude") -> str:
    """Resolve the single active host, preferring the new key over the legacy alias.

    `auto`(또는 선언 부재)면 실행 관측으로 답한다. 관측도 안 되면 installed_hosts 가 하나뿐일 때만
    그것으로 확정한다 — 후보가 하나면 모호하지 않기 때문이고, 여럿이면 default 로 떨어진다.
    """
    declared = declared_active_host(profile)
    if declared is not None:
        return declared
    detected = detect_current_host()
    if detected is not None:
        return detected
    runtime = profile.get("runtime") if isinstance(profile, dict) else None
    hosts = runtime.get("installed_hosts") if isinstance(runtime, dict) else None
    if isinstance(hosts, list) and len(hosts) == 1 and hosts[0] in HOSTS:
        return hosts[0]
    return default


def declared_installed_hosts(profile: dict[str, Any] | None) -> list[str] | None:
    """명시된 installed_hosts, 선언이 없거나 무효면 None.

    `configured_hosts` 는 선언이 없을 때 active_host 하나로 폴백하는데, 그건 "이것만 설치됐다" 는
    주장이 아니라 "아는 게 이것뿐" 이라는 뜻이다. 둘을 구분해야 미선언 프로필에 대해 설치 여부를
    단정하는 검사를 하지 않을 수 있다.
    """
    runtime = profile.get("runtime") if isinstance(profile, dict) else None
    if not isinstance(runtime, dict):
        return None
    values = runtime.get("installed_hosts")
    if isinstance(values, list) and values and all(value in HOSTS for value in values):
        return list(dict.fromkeys(values))
    return None


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
        return [("FAIL", Diagnostic("runtime.not_mapping", received=type(runtime).__name__))]
    issues = []
    unknown = sorted((key for key in runtime if key not in RUNTIME_KEYS), key=str)
    if unknown:
        issues.append(("FAIL", Diagnostic("runtime.unknown_keys", keys=unknown,
                                          allowed=sorted(RUNTIME_KEYS))))
    legacy = runtime.get("host")
    active = runtime.get("active_host")
    allowed = {"host": HOSTS, "active_host": HOSTS + (AUTO,)}
    for key, value in (("host", legacy), ("active_host", active)):
        if value is not None and value not in allowed[key]:
            issues.append(("FAIL", Diagnostic("runtime.invalid_value", key=key,
                                              value=repr(value), allowed=list(allowed[key]))))
    if legacy in HOSTS and active in HOSTS and legacy != active:
        issues.append(("FAIL", Diagnostic("runtime.alias_conflicts_with_active")))

    hosts = runtime.get("installed_hosts")
    if hosts is not None:
        if (not isinstance(hosts, list) or not hosts
                or any(host not in HOSTS for host in hosts)
                or len(set(hosts)) != len(hosts)):
            issues.append(("FAIL", Diagnostic("runtime.installed_hosts_shape")))
        else:
            # 선언된 값만 검사한다. auto 는 실행 시점에 정해지므로 정적으로 소속을 따질 대상이 없고,
            # 여기서 실측을 끌어들이면 같은 프로필이 도는 host 에 따라 통과/실패가 갈린다.
            resolved = declared_active_host(profile)
            if resolved is not None and resolved not in hosts:
                issues.append(("FAIL", Diagnostic("runtime.active_host_not_installed", value=repr(resolved))))
            options = profile.get("options")
            cross = options.get("cross_model") if isinstance(options, dict) else False
            if len(hosts) > 1 and cross is not True:
                issues.append(("WARN", Diagnostic("runtime.double_host_without_cross_model")))
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
        issues.append(("WARN", Diagnostic("runtime.desired_hosts_mismatch",
                                          desired=desired, actual=actual)))
    if active not in actual:
        issues.append(("WARN", Diagnostic("runtime.active_host_surface_absent", value=active)))
    return issues
