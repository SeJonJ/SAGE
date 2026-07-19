"""Read-only host model candidate discovery with explicit provenance."""
from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_CACHE_BYTES = 2 * 1024 * 1024
CLAUDE_ALIASES = ("opus", "sonnet", "haiku", "fable")


def _base(host: str, source: str, verification: str) -> dict[str, Any]:
    return {
        "host": host,
        "source": source,
        "verification": verification,
        "account_verified": False,
        "fetched_at": None,
        "client_version": None,
        "stale": None,
        "candidates": [],
        "issues": [],
    }


def _model_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > 200 or any(ord(char) < 32 for char in value):
        return None
    return value


def _cache_age(fetched_at: Any) -> tuple[bool | None, str | None]:
    if not isinstance(fetched_at, str) or not fetched_at.strip():
        return None, "cache fetched_at missing"
    try:
        parsed = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - parsed).total_seconds() > 7 * 86400, None
    except (ValueError, TypeError):
        return None, "cache fetched_at malformed"


def _codex_cache(codex_home: str | None = None) -> dict[str, Any]:
    result = _base("codex", "codex-local-cache", "unavailable")
    home = Path(codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    path = home / "models_cache.json"
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        result["issues"].append(f"cache missing: {path}")
        return result
    except OSError as exc:
        result["issues"].append(f"cache stat failed: {type(exc).__name__}")
        return result
    if stat.S_ISLNK(info.st_mode):
        result["issues"].append("cache symlink rejected")
        return result
    if not stat.S_ISREG(info.st_mode):
        result["issues"].append("cache is not a regular file")
        return result
    if info.st_size > MAX_CACHE_BYTES:
        result["issues"].append(f"cache size exceeds {MAX_CACHE_BYTES} bytes")
        return result
    fd = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            result["issues"].append("opened cache is not a regular file")
            return result
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            result["issues"].append("cache changed during secure open")
            return result
        if opened.st_size > MAX_CACHE_BYTES:
            result["issues"].append(f"opened cache size exceeds {MAX_CACHE_BYTES} bytes")
            return result
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = None
            raw = stream.read(MAX_CACHE_BYTES + 1)
        if len(raw.encode("utf-8")) > MAX_CACHE_BYTES:
            result["issues"].append(f"cache read exceeds {MAX_CACHE_BYTES} bytes")
            return result
        payload = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        result["issues"].append(f"cache parse failed: {type(exc).__name__}")
        return result
    finally:
        if fd is not None:
            os.close(fd)
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        result["issues"].append("cache root/models shape invalid")
        return result

    candidates = []
    seen = set()
    malformed = 0
    for item in payload["models"]:
        if not isinstance(item, dict):
            malformed += 1
            continue
        model_id = _model_id(item.get("slug"))
        if model_id is None:
            malformed += 1
            continue
        if item.get("visibility") == "hide" or model_id in seen:
            continue
        seen.add(model_id)
        efforts = []
        raw_efforts = item.get("supported_reasoning_levels")
        if isinstance(raw_efforts, list):
            for entry in raw_efforts:
                effort = entry.get("effort") if isinstance(entry, dict) else None
                if isinstance(effort, str) and effort and effort not in efforts:
                    efforts.append(effort)
        display = item.get("display_name")
        candidates.append({"id": model_id,
                           "display_name": display.strip() if isinstance(display, str) and display.strip() else model_id,
                           "reasoning_efforts": efforts})
    if malformed:
        result["issues"].append(f"ignored malformed model entries: {malformed}")
    result["fetched_at"] = payload.get("fetched_at") if isinstance(payload.get("fetched_at"), str) else None
    result["client_version"] = (payload.get("client_version")
                                if isinstance(payload.get("client_version"), str) else None)
    result["stale"], age_issue = _cache_age(result["fetched_at"])
    if age_issue:
        result["issues"].append(age_issue)
    if not candidates:
        result["issues"].append("cache has no visible valid model candidates")
        return result
    result["verification"] = "cache-confirmed"
    result["candidates"] = candidates
    return result


def _claude_aliases() -> dict[str, Any]:
    result = _base("claude", "claude-cli-aliases", "syntax-only/account-unverified")
    result["candidates"] = [
        {"id": alias, "display_name": alias, "reasoning_efforts": []}
        for alias in CLAUDE_ALIASES
    ]
    result["issues"].append(
        "Claude CLI exposes model input aliases but no stable account model-list command; entitlement is unverified"
    )
    return result


def discover(host: str, codex_home: str | None = None) -> dict[str, Any]:
    if host == "codex":
        return _codex_cache(codex_home)
    if host == "claude":
        return _claude_aliases()
    raise ValueError(f"unknown host: {host!r}")
