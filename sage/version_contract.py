"""Project-required SAGE version contract shared by CLI and hook entrypoints."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from sage.diagnostics import Diagnostic


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
    """version 축 하나의 판정. `message` 는 **언어 중립 진단**이다.

    `remediation` 은 두 종류가 섞인다 — 사용자가 그대로 입력하는 명령(`sage install ...`)은
    문자열로 두고 번역하지 않으며, 지시문은 진단으로 둔다. 호출부의 렌더가 문자열은 그대로
    통과시키므로 두 종류가 같은 필드에 있어도 안전하다.
    """

    severity: str
    axis: str
    current: str
    required: str
    message: "Diagnostic"
    remediation: "Diagnostic | str | None" = None


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
            Diagnostic("version.sage_section_not_mapping"),
        )]
    required_present = isinstance(sage_section, dict) and "required_version" in sage_section
    required_raw = sage_section.get("required_version") if required_present else None
    if required_present and not version_is_exact(required_raw):
        return [VersionContractIssue(
            "FAIL", "required", axes.required, axes.required,
            Diagnostic("version.required_not_semver", value=repr(required_raw)),
            Diagnostic("version.required_semver_example"),
        )]
    if axes.required == UNKNOWN:
        return [VersionContractIssue(
            "INFO", "required", UNKNOWN, UNKNOWN,
            Diagnostic("version.required_absent"),
            Diagnostic("version.set_required"),
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
        # 상태별로 **완전한 문장**을 고른다. `f"SAGE {axis} 버전 {state}"` 처럼 조각을 이어
        # 붙이면 어순이 다른 언어에서 반드시 깨지고, 깨진 뒤 어느 조각이 원인인지 보이지 않는다.
        if present and not version_is_exact(raw):
            message = Diagnostic("version.axis_malformed", axis=axis, value=repr(raw))
        elif current == UNKNOWN:
            message = Diagnostic("version.axis_unknown", axis=axis)
        else:
            message = Diagnostic("version.axis_differs", axis=axis,
                                 current=current, required=axes.required)
        issues.append(VersionContractIssue(
            "WARN", axis, current, axes.required, message, remediations[axis],
        ))
    return issues
