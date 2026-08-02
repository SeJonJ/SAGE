"""Validation and deterministic scaffolding for project-authored hooks."""

import os
import re
from pathlib import Path

import yaml

from sage.commands._common import contract_version_of


_STRICT_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HOSTS = {"claude", "codex"}
_BINDING_KEYS = {"event", "matcher", "timeout"}
_CLAUDE_TOOLS = {"Write", "Edit", "MultiEdit"}


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ValueError("frontmatter key는 문자열이어야 함")
        if key in result:
            raise ValueError(f"frontmatter duplicate key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def strict_hook_id(value):
    return isinstance(value, str) and _STRICT_ID.fullmatch(value) is not None


def _frontmatter(path):
    text = Path(path).read_text(encoding="utf-8")
    match = re.match(r"^---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.DOTALL)
    if not match:
        raise ValueError("spec frontmatter가 없거나 닫히지 않음")
    value = yaml.load(match.group(1), Loader=_UniqueKeyLoader)
    if not isinstance(value, dict):
        raise ValueError("spec frontmatter는 mapping이어야 함")
    return value


def _binding_issue(host, value):
    where = f"runtime_bindings.{host}"
    if not isinstance(value, dict):
        return f"{where} 는 mapping이어야 함"
    unknown = sorted(set(value) - _BINDING_KEYS, key=str)
    if unknown:
        return f"{where} 미지 필드: {unknown}"
    if value.get("event") != "PreToolUse":
        return f"{where}.event 는 PreToolUse 이어야 함"
    timeout = value.get("timeout", 10)
    if type(timeout) is not int or not 1 <= timeout <= 600:
        return f"{where}.timeout 은 1..600 정수여야 함(bool 불가)"
    matcher = value.get("matcher")
    if not isinstance(matcher, str) or not matcher:
        return f"{where}.matcher 는 비어있지 않은 문자열이어야 함"
    if matcher != matcher.strip():
        return f"{where}.matcher 앞뒤 공백은 허용되지 않음"
    if host == "codex":
        return "" if matcher == "apply_patch" else f"{where}.matcher 는 apply_patch 이어야 함"
    tokens = matcher.split("|")
    if any(not token or token != token.strip() for token in tokens):
        return f"{where}.matcher 토큰 공백/빈 토큰은 허용되지 않음"
    if len(tokens) != len(set(tokens)):
        return f"{where}.matcher 중복 토큰은 허용되지 않음"
    if not set(tokens).issubset(_CLAUDE_TOOLS):
        return f"{where}.matcher 는 Write|Edit|MultiEdit의 부분집합이어야 함"
    return ""


def inspect_project_hook(root, hook_id):
    """Return (metadata, issues) without writing or importing the authored core."""
    issues = []
    if not strict_hook_id(hook_id):
        return None, [f"project hook id는 lowercase kebab-case여야 함: {hook_id!r}"]
    spec_path = os.path.join(root, "docs", "sage_harness", "hooks", f"{hook_id}.md")
    core_path = os.path.join(root, "scripts", "sage_harness", "hooks",
                             f"{hook_id.replace('-', '_')}_core.py")
    if not os.path.isfile(spec_path) or os.path.islink(spec_path):
        issues.append(f"project hook spec 없음/비정상: {spec_path}")
        return None, issues
    if not os.path.isfile(core_path) or os.path.islink(core_path):
        issues.append(f"project hook canonical core 없음/비정상: {core_path}")
        return None, issues
    try:
        fm = _frontmatter(spec_path)
    except Exception as exc:
        return None, [f"project hook spec parse 실패: {type(exc).__name__}: {exc}"]
    unknown_top = sorted(set(fm) - {"id", "kind", "runtime_bindings"}, key=str)
    if unknown_top:
        issues.append(f"project hook frontmatter 미지 필드: {unknown_top}")
    if fm.get("id") != hook_id:
        issues.append(f"project hook spec id={fm.get('id')!r} 가 파일명 id={hook_id!r} 와 다름")
    if fm.get("kind") != "hook":
        issues.append("project hook spec kind는 hook 이어야 함")
    bindings = fm.get("runtime_bindings")
    if not isinstance(bindings, dict):
        issues.append("runtime_bindings 는 mapping이어야 함")
        bindings = {}
    elif set(bindings) != _HOSTS:
        issues.append("runtime_bindings 에 claude와 codex가 모두 정확히 필요함")
    for host in sorted(_HOSTS):
        issue = _binding_issue(host, bindings.get(host))
        if issue:
            issues.append(issue)
    contract_version = contract_version_of(core_path)
    if not contract_version:
        issues.append("project hook core에 CONTRACT_VERSION 문자열 상수가 필요함")
    if issues:
        return None, issues
    return {
        "id": hook_id,
        "spec_path": spec_path,
        "core_path": core_path,
        "bindings": bindings,
        "contract_version": contract_version,
    }, []


def adapter_body(host, hook_id):
    root_env = "CLAUDE_PROJECT_DIR" if host == "claude" else "CODEX_PROJECT_ROOT"
    return (
        "#!/bin/bash\n"
        "# generated by sage generate - project hook adapter; do not edit.\n"
        f'PROJECT_ROOT="${{SAGE_PROJECT_ROOT:-${{{root_env}:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}}}"\n'
        'CORE_DIR="$PROJECT_ROOT/scripts/sage_harness/hooks"\n'
        '[ -z "${SAGE_PROFILE:-}" ] && [ -f "$PROJECT_ROOT/sage/project-profile.json" ] && '
        'export SAGE_PROFILE="$PROJECT_ROOT/sage/project-profile.json"\n'
        'PY="${SAGE_PYTHON:-python3}"; command -v "$PY" >/dev/null 2>&1 || PY=python\n'
        f'exec "$PY" "$CORE_DIR/runtime/run_hook.py" --runtime {host} --hook {hook_id} '
        '--root "$PROJECT_ROOT" --core-dir "$CORE_DIR"\n'
    )
