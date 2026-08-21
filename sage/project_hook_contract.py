"""Validation and deterministic scaffolding for project-authored hooks."""

import os
import re
from pathlib import Path

import yaml

from sage.diagnostics import Diagnostic

from sage.commands._common import contract_version_of


_STRICT_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HOSTS = {"claude", "codex"}
_BINDING_KEYS = {"event", "matcher", "timeout"}
_CLAUDE_TOOLS = {"Write", "Edit", "MultiEdit"}


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


class _SpecError(ValueError):
    """spec 파싱 실패를 진단으로 실어 올린다.

    이 예외 문구는 바깥에서 `evidence` 로 다시 실린다. 여기에 완성 문장을 두면 영어 화면에
    한국어 조각이 그대로 얹힌다 — evidence 는 외부 도구 원문일 때만 번역 대상이 아니고,
    우리가 만든 문장은 아니다.
    """

    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.code)


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise _SpecError(Diagnostic("hook_spec.frontmatter_key_not_string"))
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
        raise _SpecError(Diagnostic("hook_spec.frontmatter_missing"))
    value = yaml.load(match.group(1), Loader=_UniqueKeyLoader)
    if not isinstance(value, dict):
        raise _SpecError(Diagnostic("hook_spec.frontmatter_not_mapping"))
    return value


def _binding_issue(host, value):
    where = f"runtime_bindings.{host}"
    if not isinstance(value, dict):
        return Diagnostic("binding.not_mapping", where=where)
    unknown = sorted(set(value) - _BINDING_KEYS, key=str)
    if unknown:
        return Diagnostic("binding.unknown_fields", where=where, fields=unknown)
    if value.get("event") != "PreToolUse":
        return Diagnostic("binding.event_invalid", where=where)
    timeout = value.get("timeout", 10)
    if type(timeout) is not int or not 1 <= timeout <= 600:
        return Diagnostic("binding.timeout_invalid", where=where)
    matcher = value.get("matcher")
    if not isinstance(matcher, str) or not matcher:
        return Diagnostic("binding.matcher_not_string", where=where)
    if matcher != matcher.strip():
        return Diagnostic("binding.matcher_whitespace", where=where)
    if host == "codex":
        return None if matcher == "apply_patch" else Diagnostic(
            "binding.matcher_not_apply_patch", where=where)
    tokens = matcher.split("|")
    if any(not token or token != token.strip() for token in tokens):
        return Diagnostic("binding.matcher_token_blank", where=where)
    if len(tokens) != len(set(tokens)):
        return Diagnostic("binding.matcher_token_duplicated", where=where)
    if not set(tokens).issubset(_CLAUDE_TOOLS):
        return Diagnostic("binding.matcher_not_subset", where=where)
    return None


def inspect_project_hook(root, hook_id):
    """Return (metadata, issues) without writing or importing the authored core."""
    issues = []
    if not strict_hook_id(hook_id):
        return None, [Diagnostic("hook_spec.id_invalid", id=repr(hook_id))]
    spec_path = os.path.join(root, "docs", "sage_harness", "hooks", f"{hook_id}.md")
    core_path = os.path.join(root, "scripts", "sage_harness", "hooks",
                             f"{hook_id.replace('-', '_')}_core.py")
    if not os.path.isfile(spec_path) or os.path.islink(spec_path):
        issues.append(Diagnostic("hook_spec.spec_missing", path=spec_path))
        return None, issues
    if not os.path.isfile(core_path) or os.path.islink(core_path):
        issues.append(Diagnostic("hook_spec.core_missing", path=core_path))
        return None, issues
    try:
        fm = _frontmatter(spec_path)
    except _SpecError as exc:
        return None, [exc.diagnostic]
    except Exception as exc:
        return None, [Diagnostic("hook_spec.parse_failed", kind=type(exc).__name__,
                                 evidence=str(exc))]
    unknown_top = sorted(set(fm) - {"id", "kind", "runtime_bindings"}, key=str)
    if unknown_top:
        issues.append(Diagnostic("hook_spec.unknown_fields", fields=unknown_top))
    if fm.get("id") != hook_id:
        issues.append(Diagnostic("hook_spec.id_mismatch", spec_id=repr(fm.get("id")),
                                 file_id=repr(hook_id)))
    if fm.get("kind") != "hook":
        issues.append(Diagnostic("hook_spec.kind_invalid"))
    bindings = fm.get("runtime_bindings")
    if not isinstance(bindings, dict):
        issues.append(Diagnostic("hook_spec.bindings_not_mapping"))
        bindings = {}
    elif set(bindings) != _HOSTS:
        issues.append(Diagnostic("hook_spec.bindings_hosts"))
    for host in sorted(_HOSTS):
        issue = _binding_issue(host, bindings.get(host))
        if issue:
            issues.append(issue)
    contract_version = contract_version_of(core_path)
    if not contract_version:
        issues.append(Diagnostic("hook_spec.core_missing_contract_version"))
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
