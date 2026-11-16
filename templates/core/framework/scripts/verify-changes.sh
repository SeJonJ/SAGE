#!/usr/bin/env bash
# verify-changes.sh — deterministic verification runner (build/test/lint).
#
# Neutral CORE template. Commands are project-specific and come from
# sage/project-profile.yaml (profile.verification.commands). This script reads
# the requested gate level and runs the declared commands; it hardcodes no
# stack-specific commands (independence: domain values live in the profile).
#
# Usage: sage_harness/verify-changes.sh [L1|L2|L3]
set -euo pipefail

LEVEL="${1:-L2}"
PROFILE="${SAGE_PROFILE:-sage/project-profile.yaml}"

echo "== verify-changes ($LEVEL) =="

if [ ! -f "$PROFILE" ]; then
  echo "  (no profile at $PROFILE — nothing to run; declare profile.verification.commands)"
  echo "== verify-changes: NO_EVIDENCE (executed=0; skipped=unknown) =="
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
executed=0
skipped=0
executed_checks=""
skipped_checks=""
for c in $CHECKS; do
  cmd=$(awk -v key="    $c:" '$0 ~ key {sub(/^[^:]*:[[:space:]]*/,""); gsub(/^"|"$/,""); print; exit}' "$PROFILE" 2>/dev/null || true)
  if [ -z "$cmd" ]; then
    skipped=$((skipped + 1))
    skipped_checks="${skipped_checks:+$skipped_checks }$c"
    echo "  - $c: (no command declared — skipped)"
    continue
  fi
  executed=$((executed + 1))
  executed_checks="${executed_checks:+$executed_checks }$c"
  echo "  - $c: $cmd"
  if ! bash -c "$cmd"; then
    echo "    FAIL: $c" >&2
    rc=1
  fi
done

echo "  executed checks: ${executed_checks:-(none)}"
echo "  skipped checks: ${skipped_checks:-(none)}"
if [ "$rc" -ne 0 ]; then
  echo "== verify-changes: FAIL (executed=$executed; skipped=$skipped) ==" >&2
elif [ "$executed" -eq 0 ]; then
  echo "== verify-changes: NO_EVIDENCE (executed=0; skipped=$skipped) =="
else
  echo "== verify-changes: PASS (executed=$executed; skipped=$skipped) =="
fi
exit $rc
