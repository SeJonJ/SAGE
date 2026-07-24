"""Shared launcher contract for generated hook commands and environment diagnostics."""

import os
import re
import shutil


_HOOK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def valid_hook_id(hook_id):
    return isinstance(hook_id, str) and bool(_HOOK_ID_RE.fullmatch(hook_id))


def command_template(target, hook_id, platform_name=None):
    """Return the command persisted in Claude/Codex hook registration."""
    if target not in {"claude", "codex"}:
        raise ValueError(f"unsupported hook runtime: {target}")
    if not valid_hook_id(hook_id):
        raise ValueError(f"invalid hook id: {hook_id!r}")

    args = f"--runtime {target} --hook {hook_id}"
    platform_name = os.name if platform_name is None else platform_name
    if platform_name == "nt":
        return f"sage-hook {args}"
    return (
        "/bin/sh -c '"
        'if [ -n "${SAGE_HOOK_BIN:-}" ] '
        '&& [ "${SAGE_HOOK_BIN#/}" != "$SAGE_HOOK_BIN" ] '
        '&& [ -f "$SAGE_HOOK_BIN" ] && [ -x "$SAGE_HOOK_BIN" ]; then '
        f'exec "$SAGE_HOOK_BIN" {args}; '
        "elif command -v sage-hook >/dev/null 2>&1; then "
        f"exec sage-hook {args}; "
        'elif [ -x "$HOME/.local/bin/sage-hook" ]; then '
        f'exec "$HOME/.local/bin/sage-hook" {args}; '
        'else printf "%s\\n" "sage-hook not found: install SAGE or set absolute SAGE_HOOK_BIN" >&2; '
        "exit 127; fi'"
    )


def resolve_sage_hook(environ=None, platform_name=None):
    """Resolve the launcher using the same candidate order as generated commands."""
    environ = os.environ if environ is None else environ
    platform_name = os.name if platform_name is None else platform_name

    if platform_name != "nt":
        configured = environ.get("SAGE_HOOK_BIN", "")
        if (
            configured
            and os.path.isabs(configured)
            and os.path.isfile(configured)
            and os.access(configured, os.X_OK)
        ):
            return configured, "SAGE_HOOK_BIN"

    found = shutil.which("sage-hook", path=environ.get("PATH", os.defpath))
    if found:
        return found, "PATH"

    if platform_name != "nt":
        home = environ.get("HOME", "")
        fallback = os.path.join(home, ".local", "bin", "sage-hook") if home else ""
        if fallback and os.path.isfile(fallback) and os.access(fallback, os.X_OK):
            return os.path.abspath(fallback), "pipx-default"

    return None, None
