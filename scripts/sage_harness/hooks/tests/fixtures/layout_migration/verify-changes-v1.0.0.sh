#!/usr/bin/env bash
# verify-changes.sh — deterministic verification runner (build/test/lint).
#
# Neutral CORE template. Commands are project-specific and come from
# sage/project-profile.yaml (profile.verification.commands). This script reads
# the requested gate level and runs the declared commands; it hardcodes no
# stack-specific commands (independence: domain values live in the profile).
#
# Usage: scripts/verify-changes.sh [L1|L2|L3]
set -euo pipefail

LEVEL="${1:-L2}"
PROFILE="${SAGE_PROFILE:-sage/project-profile.yaml}"

echo "== verify-changes ($LEVEL) =="

if [ ! -f "$PROFILE" ]; then
  echo "  (no profile at $PROFILE — nothing to run; declare profile.verification.commands)"
  exit 0
fi

# Minimal, dependency-free extraction of commands for the level.
# Expected profile shape:
#   verification:
#     commands:
#       build: "..."
#       test:  "..."
#       lint:  "..."
case "$LEVEL" in
  L1) CHECKS="syntax" ;;
  L2|L3) CHECKS="build test lint" ;;
  *) echo "unknown level: $LEVEL" >&2; exit 2 ;;
esac

rc=0
for c in $CHECKS; do
  cmd=$(awk -v key="    $c:" '$0 ~ key {sub(/^[^:]*:[[:space:]]*/,""); gsub(/^"|"$/,""); print; exit}' "$PROFILE" 2>/dev/null || true)
  if [ -z "$cmd" ]; then
    echo "  - $c: (no command declared — skipped)"
    continue
  fi
  echo "  - $c: $cmd"
  if ! bash -c "$cmd"; then
    echo "    FAIL: $c" >&2
    rc=1
  fi
done

[ "$rc" -eq 0 ] && echo "== verify-changes: PASS ==" || echo "== verify-changes: FAIL ==" >&2
exit $rc
