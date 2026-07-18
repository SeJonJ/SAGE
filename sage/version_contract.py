"""Project-required SAGE version contract shared by CLI and hook entrypoints."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


UNKNOWN = "unknown"
_EXACT_VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


@dataclass(frozen=True)
class VersionAxes:
    required: str
    installed: str
    generated: str
    runtime: str


@dataclass(frozen=True)
class VersionContractIssue:
    severity: str
    axis: str
    current: str
    required: str
    message: str
    remediation: str | None = None


def version_is_exact(value: Any) -> bool:
    return isinstance(value, str) and _EXACT_VERSION_RE.fullmatch(value) is not None


def _version_or_unknown(value: Any) -> str:
    return value if isinstance(value, str) and value else UNKNOWN


def version_axes(profile: dict[str, Any] | None,
                 manifest: dict[str, Any] | None,
                 runtime_version: Any) -> VersionAxes:
    sage_section = profile.get("sage") if isinstance(profile, dict) else None
    required = sage_section.get("required_version") if isinstance(sage_section, dict) else None
    return VersionAxes(
        required=_version_or_unknown(required),
        installed=_version_or_unknown(manifest.get("sage_version")
                                      if isinstance(manifest, dict) else None),
        generated=_version_or_unknown(manifest.get("generator_version")
                                      if isinstance(manifest, dict) else None),
        runtime=_version_or_unknown(runtime_version),
    )


def _install_command(profile: dict[str, Any] | None,
                     manifest: dict[str, Any] | None) -> str:
    runtime = profile.get("runtime") if isinstance(profile, dict) else None
    host = None
    if isinstance(runtime, dict):
        host = runtime.get("active_host") or runtime.get("host")
    if host not in ("claude", "codex") and isinstance(manifest, dict):
        host = manifest.get("host_runtime")
    if host not in ("claude", "codex"):
        host = "<claude|codex>"

    scope_arg = ""
    receipts = manifest.get("core_skill_receipts") if isinstance(manifest, dict) else None
    receipt = receipts.get(host) if isinstance(receipts, dict) else None
    scope = receipt.get("scope") if isinstance(receipt, dict) else None
    if host == "codex" and scope in ("global", "project-local", "disabled"):
        scope_arg = f" --skill-scope {scope}"
    return f"sage install --host {host}{scope_arg} --force"


def version_contract_issues(profile: dict[str, Any] | None,
                            manifest: dict[str, Any] | None,
                            runtime_version: Any) -> list[VersionContractIssue]:
    axes = version_axes(profile, manifest, runtime_version)
    sage_section = profile.get("sage") if isinstance(profile, dict) else None
    if sage_section is not None and not isinstance(sage_section, dict):
        return [VersionContractIssue(
            "FAIL", "required", axes.required, axes.required,
            "sage 섹션은 매핑(object)이어야 합니다.",
        )]
    required_present = isinstance(sage_section, dict) and "required_version" in sage_section
    required_raw = sage_section.get("required_version") if required_present else None
    if required_present and not version_is_exact(required_raw):
        return [VersionContractIssue(
            "FAIL", "required", axes.required, axes.required,
            f"sage.required_version={required_raw!r}은 exact SemVer 형식이 아닙니다.",
            "예: sage.required_version: 1.2.3",
        )]
    if axes.required == UNKNOWN:
        return [VersionContractIssue(
            "INFO", "required", UNKNOWN, UNKNOWN,
            "프로젝트 요구 SAGE 버전이 없습니다(legacy profile).",
            "shared profile에 sage.required_version을 exact 버전으로 설정",
        )]

    remediations = {
        "installed": _install_command(profile, manifest),
        "generated": "sage generate --kind hook --write",
        "runtime": f"pipx install --force sage-harness=={axes.required}",
    }
    raw_axes = {
        "installed": (
            isinstance(manifest, dict) and "sage_version" in manifest,
            manifest.get("sage_version") if isinstance(manifest, dict) else None,
        ),
        "generated": (
            isinstance(manifest, dict) and "generator_version" in manifest,
            manifest.get("generator_version") if isinstance(manifest, dict) else None,
        ),
        "runtime": (runtime_version is not None, runtime_version),
    }
    issues: list[VersionContractIssue] = []
    for axis in ("installed", "generated", "runtime"):
        current = getattr(axes, axis)
        if current == axes.required:
            continue
        present, raw = raw_axes[axis]
        if present and not version_is_exact(raw):
            state = f"형식 오류 ({raw!r})"
        else:
            state = "확인할 수 없음" if current == UNKNOWN else f"{current} != {axes.required}"
        issues.append(VersionContractIssue(
            "WARN", axis, current, axes.required,
            f"SAGE {axis} 버전 {state}",
            remediations[axis],
        ))
    return issues
