"""Deterministic parsing and validation for a composite Fast Plan."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

PHASES = ("00", "01", "02", "03", "04")
_HEADING = re.compile(r"(?m)^## Phase (00|01|02|03|04)\b.*$")
_META = re.compile(r"(?m)^([A-Za-z][A-Za-z0-9 -]*):[ \t]*(.*?)\s*$")
_RUN_ID = re.compile(r"^fc-[a-f0-9]{12}$")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


@dataclass(frozen=True)
class FastPlan:
    metadata: dict[str, str]
    sections: dict[str, str]
    content: str

    @property
    def plan_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def parse_fast_plan(content: str) -> tuple[FastPlan | None, list[str]]:
    if not isinstance(content, str):
        return None, ["Fast Plan content must be text"]
    matches = list(_HEADING.finditer(content))
    found = [match.group(1) for match in matches]
    issues = []
    if found != list(PHASES):
        issues.append(f"Fast Plan phase headings must appear exactly once in order 00..04; found={found}")
    metadata = {}
    for key, value in _META.findall(content[:matches[0].start()] if matches else content):
        if key in metadata:
            issues.append(f"duplicate Fast Plan metadata: {key}")
        metadata[key] = value.strip().strip("`")
    sections = {}
    if found == list(PHASES):
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            sections[match.group(1)] = content[match.end():end]
    return FastPlan(metadata, sections, content), issues


def open_issues(plan: FastPlan, *, stem: str, level: str, lens_count: int,
                reason: str, minimum_rounds: int, lenses: list[str],
                require_pending_phase4: bool = True) -> list[str]:
    meta = plan.metadata
    expected = {
        "Cycle-Stem": stem,
        "Cycle-Mode": "FAST",
        "Fast-Review-Level": level,
        "Fast-Minimum-Rounds": str(minimum_rounds),
        "Fast-Lens-Count": str(lens_count),
        "Fast-Lenses": ", ".join(lenses),
        "Fast-Reason": reason,
    }
    issues = [f"{key} must be {value!r}, got {meta.get(key)!r}"
              for key, value in expected.items() if meta.get(key) != value]
    if meta.get("Risk Level") not in ("L2", "L3"):
        issues.append("Risk Level must be L2 or L3 for Fast Cycle")
    run_id = meta.get("Fast-Audit-Run")
    if run_id != "pending" and not (isinstance(run_id, str) and _RUN_ID.fullmatch(run_id)):
        issues.append("Fast-Audit-Run must be pending or a valid fc-* run id")
    phase0 = plan.sections.get("00", "")
    required_mapping = (
        "- [x] Phase 00 context complete",
        "- [x] Phase 01 requirements and acceptance matrix embedded",
        "- [x] Phase 02 design and failure handling embedded",
        "- [x] Phase 03 ownership, implementation checklist, and verification plan ready",
    )
    issues.extend(f"missing checked mapping item: {item}" for item in required_mapping if item not in phase0)
    phase3 = plan.sections.get("03", "")
    required_pre = (
        "- [x] File ownership assigned before source edits",
        "- [x] Acceptance IDs mapped to implementation tasks",
        "- [x] Verification command plan recorded",
    )
    issues.extend(f"missing checked pre-implementation item: {item}" for item in required_pre if item not in phase3)
    phase1 = plan.sections.get("01", "")
    ids = re.findall(r"(?m)^\|\s*([A-Za-z][A-Za-z0-9_-]*)\s*\|", phase1)
    ids = [item for item in ids if item != "ID"]
    if not ids or len(ids) != len(set(ids)):
        issues.append("Phase 01 acceptance matrix needs at least one unique acceptance ID")
    for acceptance_id in ids:
        if not re.search(rf"\b{re.escape(acceptance_id)}\b", phase3):
            issues.append(f"Phase 03 acceptance trace missing {acceptance_id}")
    if require_pending_phase4 and "Status: PENDING — implementation not started" not in plan.sections.get("04", ""):
        issues.append("Phase 04 must retain the exact pre-implementation PENDING marker at open")
    return issues


def bind_run_id(content: str, run_id: str) -> str:
    matches = list(re.finditer(r"(?m)^Fast-Audit-Run:[ \t]*(pending|fc-[a-f0-9]{12})[ \t]*$", content))
    if len(matches) != 1:
        raise ValueError("Fast-Audit-Run line must occur exactly once")
    current = matches[0].group(1)
    if current != "pending" and current != run_id:
        raise ValueError(f"Fast-Audit-Run already bound to {current}")
    return content[:matches[0].start()] + f"Fast-Audit-Run: {run_id}" + content[matches[0].end():]


def reason_issue(reason: str) -> str | None:
    if not isinstance(reason, str) or not reason.strip():
        return "reason must be a non-empty line"
    if len(reason) > 1000 or any(ord(char) < 32 or char in "\u0085\u2028\u2029" for char in reason):
        return "reason must be one line without control characters and at most 1000 characters"
    return None


def evidence_marker_issues(content: str, *, fast_run_id: str, loop_run_id: str) -> list[str]:
    """Require one exact Fast evidence declaration outside Markdown code blocks."""
    expected = (
        f"Fast-Run: {fast_run_id}",
        f"Loop-Run: {loop_run_id}",
        "Final Status: APPROVED",
    )
    counts = {marker: 0 for marker in expected}
    in_fence = False
    fence_char = ""
    fence_len = 0
    for raw in (content or "").splitlines():
        match = _FENCE.match(raw)
        if match:
            token = match.group(1)
            if not in_fence:
                in_fence, fence_char, fence_len = True, token[0], len(token)
            elif token[0] == fence_char and len(token) >= fence_len:
                in_fence = False
            continue
        if in_fence or raw.startswith("\t") or re.match(r"^ {4,}", raw):
            continue
        if raw in counts:
            counts[raw] += 1
    return [f"{marker!r} must appear exactly once outside Markdown fences (found {count})"
            for marker, count in counts.items() if count != 1]
