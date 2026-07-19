"""Shared policy and machine-local capability profile resolution."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import os
import re
import subprocess
from typing import Any

import yaml


HOSTS = ("claude", "codex")
POLICIES = ("required", "recommended", "off")
LOCAL_PROFILE_NAME = "project-profile.local.yaml"
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_LOCAL_KEYS = frozenset({"runtime", "capabilities", "cross_model", "knowledge_capture", "models"})
_SECTION_KEYS = {
    "runtime": frozenset({"installed_hosts"}),
    "capabilities": frozenset(HOSTS),
    "cross_model": frozenset({"enabled"}),
    "knowledge_capture": frozenset({"enabled", "vault_path"}),
    "models": frozenset({"available"}),
}


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
        issues.append(("FAIL", f"local의 알 수 없는 최상위 키: {unknown}"))
    for section, allowed in _SECTION_KEYS.items():
        value = local.get(section)
        if value is None:
            continue
        if not isinstance(value, dict):
            issues.append(("FAIL", f"local {section}는 매핑이어야 함"))
            continue
        section_unknown = sorted((key for key in value if key not in allowed), key=str)
        if section_unknown:
            issues.append(("FAIL", f"local {section}의 알 수 없는 키: {section_unknown}"))
    return issues


def _local_type_issues(local: dict[str, Any]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    runtime = local.get("runtime")
    if isinstance(runtime, dict) and "installed_hosts" in runtime:
        hosts = runtime["installed_hosts"]
        if (not isinstance(hosts, list) or not hosts or len(set(hosts)) != len(hosts)
                or any(host not in HOSTS for host in hosts)):
            issues.append(("FAIL", "local runtime.installed_hosts는 non-empty unique host 배열이어야 함"))

    capabilities = local.get("capabilities")
    if isinstance(capabilities, dict):
        for host, enabled in capabilities.items():
            if host in HOSTS and not isinstance(enabled, bool):
                issues.append(("FAIL", f"local capabilities.{host}는 boolean이어야 함"))

    cross = local.get("cross_model")
    if isinstance(cross, dict) and "enabled" in cross and not isinstance(cross["enabled"], bool):
        issues.append(("FAIL", "local cross_model.enabled는 boolean이어야 함"))

    knowledge = local.get("knowledge_capture")
    if isinstance(knowledge, dict):
        if "enabled" in knowledge and not isinstance(knowledge["enabled"], bool):
            issues.append(("FAIL", "local knowledge_capture.enabled는 boolean이어야 함"))
        path = knowledge.get("vault_path")
        if path is not None and (not isinstance(path, str) or not path or "\x00" in path):
            issues.append(("FAIL", "local knowledge_capture.vault_path는 유효한 non-empty 문자열이어야 함"))

    models = local.get("models")
    if isinstance(models, dict) and "available" in models:
        available = models["available"]
        if not isinstance(available, dict):
            issues.append(("FAIL", "local models.available은 host별 model 배열 매핑이어야 함"))
        else:
            unknown = sorted((host for host in available if host not in HOSTS), key=str)
            if unknown:
                issues.append(("FAIL", f"local models.available의 알 수 없는 host: {unknown}"))
            for host, values in available.items():
                if host not in HOSTS:
                    continue
                if (not isinstance(values, list) or not values
                        or any(not isinstance(value, str) or not _MODEL_RE.fullmatch(value)
                               for value in values)):
                    issues.append(("FAIL", f"local models.available.{host}는 non-empty model id 배열이어야 함"))
    return issues


def profile_layer_issues(shared: dict[str, Any] | None,
                         local: dict[str, Any] | None) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    if not isinstance(shared, dict):
        issues.append(("FAIL", "shared profile은 매핑이어야 함"))
        return issues
    cross = shared.get("cross_model")
    if isinstance(cross, dict) and "policy" in cross and cross["policy"] not in POLICIES:
        issues.append(("FAIL", f"cross_model.policy={cross['policy']!r} — {list(POLICIES)} 중 하나여야 함"))
    if local is None:
        return issues
    if not isinstance(local, dict):
        issues.append(("FAIL", "local profile은 매핑이어야 함"))
        return issues
    issues.extend(_unknown_key_issues(local))
    issues.extend(_local_type_issues(local))
    if cross_model_policy(shared) == "required" and _local_cross_model_value(local) is False:
        issues.append(("FAIL", "cross_model.policy=required는 local cross_model.enabled=false로 완화할 수 없음"))
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
        return None, [("FAIL", f"{label} profile YAML 파싱 오류({type(exc).__name__}): {path}")]
    if not isinstance(value, dict):
        return None, [("FAIL", f"{label} profile은 매핑이어야 함: {path}")]
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
            issues.append(("FAIL", f"shared profile 없음: {shared_path}"))
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
        return [("INFO", "local profile Git 점검 N/A (Git 실행 불가)")]
    if probe.returncode != 0:
        return [("INFO", "local profile Git 점검 N/A (Git 저장소 아님)")]
    git_root = os.path.realpath(probe.stdout.strip())
    try:
        if os.path.commonpath((git_root, local)) != git_root:
            return [("WARN", f"local profile이 Git 저장소 밖에 있음: {local}")]
    except ValueError:
        return [("WARN", f"local profile Git 경로를 비교할 수 없음: {local}")]
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
        return [("WARN", f"local profile Git 추적 상태 점검 실패: {rel}")]
    if tracked:
        return [("WARN", f"local profile이 Git에 추적됨: {rel} — index에서 제외 필요")]
    try:
        ignored = subprocess.run(
            ["git", "-C", git_root, "check-ignore", "--quiet", "--", rel],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return [("WARN", f"local profile Git ignore 상태 점검 실패: {rel}")]
    if not ignored:
        return [("WARN", f"local profile이 .gitignore에서 ignore되지 않음: {rel}")]
    return []
