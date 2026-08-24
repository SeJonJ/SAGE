#!/usr/bin/env python3
"""Pure decision core for the generated-artifact write guard."""
from __future__ import annotations

import json
import os
import re
from pathlib import PurePosixPath

CONTRACT_VERSION = "2"

_PATCH_PATH = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$")
_MOVE_PATH = re.compile(r"^\*\*\* Move to: (.+)$")
_FRAMEWORK_DOCS = {"agent_guide.md", "claude.md", "codex.md", "agents.md"}
_OVERLAY_AGENTS = {"implementer-a.md", "implementer-b.md", "leader.md", "reviewer.md"}
_BLOCKED_AGENTS = {"qa.md", "convention-checker.md"}
_OVERLAY_SKILLS = {"sage-cycle", "sage-plan", "sage-review", "sage-team"}
_BLOCKED_SKILLS = {"sage-init", "sage-asset", "sage-profile-modify", "sage-asset-override"}
# 사이클 선언 파일. `.mcp.json` 처럼 basename 으로 매칭하면 프로젝트의 아무 cycle.json 이나
# 걸리므로 **경로 꼬리**로 판정한다.
_CYCLE_DECLARATION_TAIL = (".sage", "cycle.json")


def _normalized(path: object) -> str:
    if not isinstance(path, str):
        return ""
    value = path.strip().replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.lower()


def _parts(path: object) -> tuple[str, ...]:
    normalized = _normalized(path)
    return PurePosixPath(normalized).parts if normalized else ()


def _host_asset(parts: tuple[str, ...]) -> tuple[str, str, tuple[str, ...]] | None:
    for index, part in enumerate(parts):
        if part not in (".claude", ".codex") or index + 2 >= len(parts):
            continue
        kind = parts[index + 1]
        if kind in ("agents", "hooks", "skills"):
            return part, kind, parts[index + 2:]
    return None


def _is_framework_override(parts: tuple[str, ...]) -> bool:
    marker = ("sage", "asset_overrides", "framework")
    for index in range(len(parts) - len(marker)):
        if parts[index:index + len(marker)] == marker:
            tail = parts[index + len(marker):]
            return len(tail) == 1 and tail[0].endswith(".md")
    return False


def _is_cycle_declaration(parts: tuple[str, ...]) -> bool:
    return parts[-len(_CYCLE_DECLARATION_TAIL):] == _CYCLE_DECLARATION_TAIL


def is_guarded(path: object) -> bool:
    parts = _parts(path)
    if not parts or _is_framework_override(parts):
        return False
    if parts[-1] == ".mcp.json" or parts[-1] in _FRAMEWORK_DOCS:
        return True
    # 선언 파일은 게이트가 "어느 사이클인가" 를 읽는 자리다. 편집 도구로 직접 쓸 수 있으면
    # 에이전트가 완결 사이클을 지목해 자기 게이트를 끌 수 있다 — env 통로에서는 불가능했던
    # 구멍이고(hook 프로세스는 호스트가 띄운다), 파일로 옮기면서 생겼으므로 여기서 닫는다.
    # CLI(`sage cycle set`)는 편집 도구 밖이라 그대로 동작한다.
    if _is_cycle_declaration(parts):
        return True
    return _host_asset(parts) is not None


def _overlay_hint(path: object) -> str:
    asset = _host_asset(_parts(path))
    if not asset:
        return ""
    _host, kind, tail = asset
    if kind == "agents" and len(tail) == 1 and tail[0] in _OVERLAY_AGENTS:
        return f"sage/asset_overrides/agents/{tail[0]}"
    if kind == "skills" and len(tail) >= 2 and tail[0] in _OVERLAY_SKILLS:
        return f"sage/asset_overrides/skills/{tail[0]}.md"
    return ""


def _is_blocked_core_render(path: object) -> bool:
    asset = _host_asset(_parts(path))
    if not asset:
        return False
    _host, kind, tail = asset
    if kind == "agents" and len(tail) == 1 and tail[0] in _BLOCKED_AGENTS:
        return True
    return kind == "skills" and len(tail) >= 2 and tail[0] in _BLOCKED_SKILLS


def _is_framework_doc(path: object) -> bool:
    parts = _parts(path)
    return bool(parts) and parts[-1] in _FRAMEWORK_DOCS


def block_reason(path: str):
    """(code, arguments) — 언어 중립 판정. 완성 문장을 만들지 않는다.

    이전에는 이 자리가 한국어 문장을 직접 조립했다. 그 문장들은 catalog 키가 아니었고, 영어가
    없었고, 어떤 한영 대조에도 걸리지 않았다 — 부채 스캐너의 범위가 `hooks/runtime/` 아래로
    한정돼 있어서 이 파일은 검사조차 되지 않았다. 판정이 code 만 돌려주면 그 상태가 구조적으로
    불가능해진다.
    """
    if _is_cycle_declaration(_parts(path)):
        return "guard.cycle_declaration", {"path": path}
    if _is_framework_doc(path):
        return "guard.framework_doc", {"path": path}
    overlay = _overlay_hint(path)
    if overlay:
        return "guard.core_render", {"path": path, "overlay": overlay}
    if _is_blocked_core_render(path):
        return "guard.core_render_blocked", {"path": path}
    return "guard.generated_asset", {"path": path}


def _hook_catalog():
    """hook catalog 를 최선으로 찾는다. 못 찾아도 예외를 올리지 않는다.

    이 가드가 catalog 를 못 읽는다는 이유로 죽으면 표시 계층이 판정 계층을 무너뜨린다.
    """
    try:
        from .runtime import i18n as module          # noqa: F401
        return module
    except Exception:
        pass
    for name in ("i18n",):
        try:
            return __import__(name)
        except Exception:
            continue
    return None


def block_message(path: str, language: str = None) -> str:
    """차단 사유 + 복구 순서. code 를 항상 앞에 남긴다.

    code 는 언어를 타지 않는 유일한 조각이라, 문장만 내면 사용자가 검색할 수도 CI 가 수집할
    수도 없다.
    """
    code, arguments = block_reason(path)
    catalog = _hook_catalog()
    if catalog is None:
        return f"⛔ SAGE write guard [{code}]"
    language = language or catalog.DEFAULT_LANGUAGE
    # `frag` 를 쓰는 이유는 이 키들이 `message_key` 가 아니기 때문이다. `MESSAGES` 는 게이트
    # 결정이 싣는 message_key 의 테이블이고, 여기 code 는 그 계약에 속하지 않는다.
    template = catalog.frag(language, code)
    try:
        body = template.format(**arguments) if template else f"[SAGE] {code}"
    except (KeyError, IndexError, ValueError):
        body = f"[SAGE] {code}"
    lines = [f"⛔ SAGE write guard [{code}]", body]
    try:
        from .runtime import recovery as recovery_module
    except Exception:
        try:
            recovery_module = __import__("recovery")
        except Exception:
            recovery_module = None
    if recovery_module is not None:
        lines.extend(recovery_module.render(
            code, lambda key: catalog.frag(language, key), path=path, host="<host>"))
    return "\n".join(lines)


def extract_paths(raw_text: str) -> list[str]:
    try:
        data = json.loads(raw_text or "{}")
    except (TypeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return []
    paths: list[str] = []
    direct = tool_input.get("file_path") or tool_input.get("path")
    if isinstance(direct, str) and direct:
        paths.append(direct)
    command = tool_input.get("command") or ""
    if isinstance(command, str):
        for line in command.splitlines():
            match = _PATCH_PATH.match(line) or _MOVE_PATH.match(line)
            if match:
                paths.append(match.group(1).strip())
    return paths


def decide_paths(paths: list[str]) -> dict:
    for path in paths:
        if is_guarded(path):
            code, arguments = block_reason(path)
            return {"status": "block", "exit_code": 2, "path": path,
                    "code": code, "arguments": arguments,
                    "message": block_message(path)}
    return {"status": "pass", "exit_code": 0, "path": "", "message": ""}


def decide_json(raw_text: str) -> dict:
    return decide_paths(extract_paths(raw_text))


def decide_input(raw_text: str, direct_path: str | None = None, environ=None) -> dict:
    """Preserve legacy direct-call precedence before falling back to hook stdin JSON."""
    environ = os.environ if environ is None else environ
    if direct_path is not None:
        return decide_paths([direct_path])
    env_path = environ.get("SAGE_GUARD_PATH")
    if env_path:
        return decide_paths([env_path])
    return decide_json(raw_text)
