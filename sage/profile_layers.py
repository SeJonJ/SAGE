"""Shared policy and machine-local capability profile resolution."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import os
import re
import subprocess
from typing import Any

import yaml

from sage.diagnostics import Diagnostic

HOSTS = ("claude", "codex")
POLICIES = ("required", "recommended", "off")
LOCAL_PROFILE_NAME = "project-profile.local.yaml"
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_LOCAL_KEYS = frozenset({"runtime", "capabilities", "cross_model", "knowledge_capture", "models",
                         "interface"})
_SECTION_KEYS = {
    "runtime": frozenset({"installed_hosts"}),
    "capabilities": frozenset(HOSTS),
    "cross_model": frozenset({"enabled"}),
    "knowledge_capture": frozenset({"enabled", "vault_path"}),
    "models": frozenset({"available"}),
    "interface": frozenset({"language"}),
}
# 표시 언어. local 전용이고 `effective_profile` 이 복사하지 않아 공유 profile·manifest·생성물·
# profile hash 어디에도 들어가지 않는다 — 판정에 관여하지 않는 개인 설정이기 때문이다.
INTERFACE_LANGUAGES = ("ko", "en")


@dataclass(frozen=True)
class ProfileLayers:
    shared: dict[str, Any]
    local: dict[str, Any] | None
    effective: dict[str, Any]
    issues: list[tuple[str, str]]
    shared_path: str
    local_path: str

    @property
    def has_fail(self) -> bool:
        return any(severity == "FAIL" for severity, _ in self.issues)


def cross_model_policy(shared: dict[str, Any] | None) -> str | None:
    cross = shared.get("cross_model") if isinstance(shared, dict) else None
    policy = cross.get("policy") if isinstance(cross, dict) else None
    return policy if policy in POLICIES else None


def _local_cross_model_value(local: dict[str, Any] | None) -> bool | None:
    cross = local.get("cross_model") if isinstance(local, dict) else None
    enabled = cross.get("enabled") if isinstance(cross, dict) else None
    return enabled if isinstance(enabled, bool) else None


def cross_model_enabled(shared: dict[str, Any] | None,
                        local: dict[str, Any] | None) -> bool:
    policy = cross_model_policy(shared)
    local_value = _local_cross_model_value(local)
    if policy == "required":
        return True
    if policy == "recommended":
        return True if local_value is None else local_value
    if policy == "off":
        return False
    if local_value is not None:
        return local_value
    options = shared.get("options") if isinstance(shared, dict) else None
    return bool(options.get("cross_model", False)) if isinstance(options, dict) else False


def _unknown_key_issues(local: dict[str, Any]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    unknown = sorted((key for key in local if key not in _LOCAL_KEYS), key=str)
    if unknown:
        issues.append(("FAIL", Diagnostic("layers.local_unknown_top_keys", keys=unknown)))
    for section, allowed in _SECTION_KEYS.items():
        value = local.get(section)
        if value is None:
            continue
        if not isinstance(value, dict):
            issues.append(("FAIL", Diagnostic("layers.local_section_not_mapping", section=section)))
            continue
        section_unknown = sorted((key for key in value if key not in allowed), key=str)
        if section_unknown:
            issues.append(("FAIL", Diagnostic("layers.local_section_unknown_keys", section=section,
                                              keys=section_unknown)))
    return issues


def _local_type_issues(local: dict[str, Any]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    runtime = local.get("runtime")
    if isinstance(runtime, dict) and "installed_hosts" in runtime:
        hosts = runtime["installed_hosts"]
        if (not isinstance(hosts, list) or not hosts or len(set(hosts)) != len(hosts)
                or any(host not in HOSTS for host in hosts)):
            issues.append(("FAIL", Diagnostic("layers.installed_hosts_shape")))

    capabilities = local.get("capabilities")
    if isinstance(capabilities, dict):
        for host, enabled in capabilities.items():
            if host in HOSTS and not isinstance(enabled, bool):
                issues.append(("FAIL", Diagnostic("layers.capabilities_not_bool", host=host)))

    cross = local.get("cross_model")
    if isinstance(cross, dict) and "enabled" in cross and not isinstance(cross["enabled"], bool):
        issues.append(("FAIL", Diagnostic("layers.cross_model_enabled_not_bool")))

    interface = local.get("interface")
    if isinstance(interface, dict) and "language" in interface:
        # 정확한 소문자만 받는다. 대소문자·공백을 관대하게 받으면 profile 마다 표기가 갈리고
        # 그 다양성이 그대로 hook·skill 의 언어 해석 분기로 흘러간다.
        if interface["language"] not in INTERFACE_LANGUAGES:
            issues.append(("FAIL", Diagnostic("layers.interface_language_invalid",
                                              allowed=list(INTERFACE_LANGUAGES))))

    knowledge = local.get("knowledge_capture")
    if isinstance(knowledge, dict):
        if "enabled" in knowledge and not isinstance(knowledge["enabled"], bool):
            issues.append(("FAIL", Diagnostic("layers.knowledge_capture_enabled_not_bool")))
        path = knowledge.get("vault_path")
        if path is not None and (not isinstance(path, str) or not path or "\x00" in path):
            issues.append(("FAIL", Diagnostic("layers.vault_path_invalid")))

    models = local.get("models")
    if isinstance(models, dict) and "available" in models:
        available = models["available"]
        if not isinstance(available, dict):
            issues.append(("FAIL", Diagnostic("layers.models_available_shape")))
        else:
            unknown = sorted((host for host in available if host not in HOSTS), key=str)
            if unknown:
                issues.append(("FAIL", Diagnostic("layers.models_available_unknown_host", hosts=unknown)))
            for host, values in available.items():
                if host not in HOSTS:
                    continue
                if (not isinstance(values, list) or not values
                        or any(not isinstance(value, str) or not _MODEL_RE.fullmatch(value)
                               for value in values)):
                    issues.append(("FAIL", Diagnostic("layers.models_available_host_shape", host=host)))
    return issues


def profile_layer_issues(shared: dict[str, Any] | None,
                         local: dict[str, Any] | None) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    if not isinstance(shared, dict):
        issues.append(("FAIL", Diagnostic("layers.shared_not_mapping")))
        return issues
    cross = shared.get("cross_model")
    if isinstance(cross, dict) and "policy" in cross and cross["policy"] not in POLICIES:
        issues.append(("FAIL", Diagnostic("layers.cross_model_policy_invalid",
                                              value=repr(cross["policy"]), allowed=list(POLICIES))))
    if local is None:
        return issues
    if not isinstance(local, dict):
        issues.append(("FAIL", Diagnostic("layers.local_not_mapping")))
        return issues
    issues.extend(_unknown_key_issues(local))
    issues.extend(_local_type_issues(local))
    if cross_model_policy(shared) == "required" and _local_cross_model_value(local) is False:
        issues.append(("FAIL", Diagnostic("layers.cross_model_required_not_relaxable")))
    return issues


def effective_profile(shared: dict[str, Any], local: dict[str, Any] | None) -> dict[str, Any]:
    effective = deepcopy(shared)
    options = effective.setdefault("options", {})
    if not isinstance(options, dict):
        options = {}
        effective["options"] = options
    options["cross_model"] = cross_model_enabled(shared, local)
    if not isinstance(local, dict):
        return effective

    runtime_local = local.get("runtime")
    if isinstance(runtime_local, dict) and isinstance(runtime_local.get("installed_hosts"), list):
        runtime = effective.setdefault("runtime", {})
        if isinstance(runtime, dict):
            runtime["installed_hosts"] = deepcopy(runtime_local["installed_hosts"])

    capabilities_local = local.get("capabilities")
    if isinstance(capabilities_local, dict):
        capabilities = effective.setdefault("capabilities", {})
        if isinstance(capabilities, dict):
            for host in HOSTS:
                if isinstance(capabilities_local.get(host), bool):
                    capabilities[host] = capabilities_local[host]

    knowledge_local = local.get("knowledge_capture")
    if isinstance(knowledge_local, dict):
        knowledge = effective.setdefault("knowledge_capture", {})
        if isinstance(knowledge, dict):
            enabled = knowledge_local.get("enabled")
            if isinstance(enabled, bool):
                knowledge["enabled"] = enabled
                if not enabled:
                    knowledge["vault_path"] = ""
            path = knowledge_local.get("vault_path")
            if isinstance(path, str):
                knowledge["vault_path"] = path
    return effective


def _load_yaml(path: str, label: str) -> tuple[dict[str, Any] | None, list[tuple[str, str]]]:
    if not os.path.exists(path):
        return None, []
    try:
        with open(path, encoding="utf-8") as handle:
            value = yaml.safe_load(handle) or {}
    except Exception as exc:
        return None, [("FAIL", Diagnostic("layers.yaml_parse_error", label=label,
                                          kind=type(exc).__name__, path=path))]
    if not isinstance(value, dict):
        return None, [("FAIL", Diagnostic("layers.yaml_not_mapping", label=label, path=path))]
    return value, []


def load_profile_layers(shared_path: str, local_path: str | None = None) -> ProfileLayers:
    shared_path = os.path.realpath(shared_path)
    local_path = os.path.realpath(
        local_path or os.path.join(os.path.dirname(shared_path), LOCAL_PROFILE_NAME)
    )
    shared, issues = _load_yaml(shared_path, "shared")
    if shared is None:
        shared = {}
        if not issues:
            issues.append(("FAIL", Diagnostic("layers.shared_missing", path=shared_path)))
    local, local_load_issues = _load_yaml(local_path, "local")
    issues.extend(local_load_issues)
    if not local_load_issues:
        issues.extend(profile_layer_issues(shared, local))
    return ProfileLayers(
        shared=shared,
        local=local,
        effective=effective_profile(shared, local),
        issues=issues,
        shared_path=shared_path,
        local_path=local_path,
    )


def local_profile_git_issues(project_root: str,
                             local_path: str) -> list[tuple[str, str]]:
    """Diagnose accidental publication of a machine-local profile without mutating Git."""
    root = os.path.realpath(project_root)
    local = os.path.realpath(local_path)
    if not os.path.isfile(local):
        return []
    try:
        probe = subprocess.run(
            ["git", "-C", root, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return [("INFO", Diagnostic("layers.git_unavailable"))]
    if probe.returncode != 0:
        return [("INFO", Diagnostic("layers.git_not_a_repo"))]
    git_root = os.path.realpath(probe.stdout.strip())
    try:
        if os.path.commonpath((git_root, local)) != git_root:
            return [("WARN", Diagnostic("layers.local_outside_git_root", path=local))]
    except ValueError:
        return [("WARN", Diagnostic("layers.local_git_path_incomparable", path=local))]
    rel = os.path.relpath(local, git_root)
    try:
        tracked = subprocess.run(
            ["git", "-C", git_root, "ls-files", "--error-unmatch", "--", rel],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return [("WARN", Diagnostic("layers.git_tracked_check_failed", path=rel))]
    if tracked:
        return [("WARN", Diagnostic("layers.local_is_git_tracked", path=rel))]
    try:
        ignored = subprocess.run(
            ["git", "-C", git_root, "check-ignore", "--quiet", "--", rel],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return [("WARN", Diagnostic("layers.git_ignore_check_failed", path=rel))]
    if not ignored:
        return [("WARN", Diagnostic("layers.local_not_gitignored", path=rel))]
    return []
