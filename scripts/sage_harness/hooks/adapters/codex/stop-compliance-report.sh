#!/bin/bash
# stop-compliance-report — Codex adapter (rendered)
# SSOT: scripts/sage_harness/hooks/stop_compliance_report_core.py (공유 집계)
# adapter: session JSONL→snapshot / 경로·env / report 파일쓰기. 집계는 core.
# audit 1회차 P0-2 수정: Codex-only 정책(output_contract/knowledge_capture)을 policy_results 에 연결
#   (canonical core 는 중립 유지, Codex adapter 만 Codex 런타임 정책 주입 — claude adapter 는 미적용). (직접수정 금지)
# profile 외부주입 필수($SAGE_PROFILE) — 없으면 통과.

PROJECT_ROOT="${CODEX_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
LOG_DIR="$PROJECT_ROOT/.codex/logs"
CORE_DIR="${SAGE_HOOK_CORE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
TODAY="${SAGE_TODAY:-$(date +%Y-%m-%d)}"
LOG_FILE="$LOG_DIR/session-$TODAY.jsonl"
[ -f "$LOG_FILE" ] || exit 0

BRANCH=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)
INPUT=$(cat 2>/dev/null || true)   # Codex Stop hook: transcript_path 포함

SAGE_HOOK_INPUT="$INPUT" SAGE_TODAY="$TODAY" SAGE_BRANCH="${SAGE_GATE_BRANCH:-$BRANCH}" \
python3 - "$LOG_FILE" "$LOG_DIR" "$CORE_DIR" <<'PYEOF'
import sys, os, json, time, calendar
log_file, log_dir, core_dir = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, core_dir)
sys.path.insert(0, os.path.join(core_dir, "policies"))
import stop_compliance_report_core as core
import output_contract_check
import knowledge_capture

prof_path = os.environ.get("SAGE_PROFILE", "")
if not prof_path or not os.path.exists(prof_path):
    sys.exit(0)
with open(prof_path, encoding="utf-8") as f:
    profile = json.load(f)

entries = []
with open(log_file, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            try: entries.append(json.loads(line))
            except Exception: pass

snapshot = {"entries": entries, "today": os.environ.get("SAGE_TODAY", ""),
            "branch": os.environ.get("SAGE_BRANCH", ""), "runtime": "codex"}
event = {"hook_id": "stop-compliance-report", "hook_event_name": "Stop", "runtime": "codex"}
model = core.decide(event, profile, snapshot)

# ── Codex-only 정책 주입(policy_results) ──
CODE_TYPES = ("backend-main", "backend-test", "frontend-js", "frontend-server", "frontend-config")
has_code = any(e.get("type") in CODE_TYPES for e in entries)

def last_assistant_text(path):
    if not path or not os.path.exists(path):
        return ""
    last = ""
    seen = 0
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                seen += 1
                if seen > 200000:   # audit P1: 거대 transcript DoS 방지 (라인 캡)
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                role = d.get("role") or (d.get("message") or {}).get("role")
                if role == "assistant":
                    c = d.get("content") or (d.get("message") or {}).get("content") or ""
                    last = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
    except Exception:
        return ""
    return last

def epoch_of_iso(s):
    try:
        return calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None

try:
    raw = json.loads(os.environ.get("SAGE_HOOK_INPUT", "{}"))
except Exception:
    raw = {}
transcript = raw.get("transcript_path", "") or ""

# output_contract (Codex-only)
oc = output_contract_check.check(last_assistant_text(transcript), has_code)
model["sections"]["policy_results"].append(oc)

# knowledge_capture (OPTION — vault from profile)
vault = (profile.get("knowledge_capture", {}) or {}).get("vault_path", "") or ""
wiki_log = os.path.join(vault, "wiki", "log.md") if vault else ""
wiki_mtime = os.path.getmtime(wiki_log) if (wiki_log and os.path.exists(wiki_log)) else None
code_ts = [epoch_of_iso(e.get("ts", "")) for e in entries if e.get("type") in CODE_TYPES]
code_ts = [t for t in code_ts if t]
earliest = min(code_ts) if code_ts else None
kc = knowledge_capture.check(vault, has_code, wiki_mtime, earliest)
model["sections"]["policy_results"].append(kc)

md = core.render_markdown(model)
report = os.path.join(log_dir, f"compliance-{snapshot['today']}.md")
with open(report, "a", encoding="utf-8") as f:
    f.write(md)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "Stop",
      "additionalContext": f"Compliance report saved: .codex/logs/compliance-{snapshot['today']}.md"}}, ensure_ascii=False))
sys.exit(model["exit_code"])
PYEOF
exit 0
