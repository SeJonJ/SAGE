#!/bin/bash
# pre-implementation-gate — Codex adapter (rendered, 부분추출)
# SSOT: scripts/sage_harness/hooks/pre_implementation_gate_core.py
# adapter: 입력추출(apply_patch 다중파일+content) / declared_max / plan_files snapshot / 출력렌더 / 경로바인딩.
# L3 review 전략 UNRESOLVED(미선택) → core L3 BLOCK+override. (직접수정 금지)
# profile 외부주입 필수($SAGE_PROFILE) — 없으면 통과.

PROJECT_ROOT="${CODEX_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
CORE_DIR="${SAGE_HOOK_CORE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BRANCH=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)
INPUT=$(cat)

SAGE_HOOK_INPUT="$INPUT" SAGE_BRANCH="${SAGE_GATE_BRANCH:-$BRANCH}" python3 - "$PROJECT_ROOT" "$CORE_DIR" <<'PYEOF'
import sys, os, json, glob, re
root, core_dir = sys.argv[1], sys.argv[2]
sys.path.insert(0, core_dir)
import pre_implementation_gate_core as core

try:
    raw = json.loads(os.environ.get("SAGE_HOOK_INPUT", "{}"))
except Exception:
    sys.exit(0)
if (raw.get("tool_name") or "") != "apply_patch":
    sys.exit(0)

prof_path = os.environ.get("SAGE_PROFILE", "")
if not prof_path or not os.path.exists(prof_path):
    sys.exit(0)
with open(prof_path, encoding="utf-8") as f:
    profile = json.load(f)

def rel(p):
    if not p: return ""
    if not os.path.isabs(p): return p
    try: return os.path.relpath(p, root)
    except Exception: return p

# apply_patch 본문 → 파일별 {path, op, content(+라인 누적)}
command = (raw.get("tool_input") or {}).get("command") or ""
changes, cur = [], None
for line in command.splitlines():
    m = re.match(r"^\*\*\* (Add|Update|Delete) File: (.+)$", line)
    if m:
        cur = {"path": rel(m.group(2).strip()), "op": m.group(1).lower(), "content": ""}
        changes.append(cur)
        continue
    if cur is not None and line.startswith("+"):
        cur["content"] += line[1:] + "\n"

declared = None
sid = re.sub(r"[^A-Za-z0-9_-]", "_", raw.get("session_id", "") or "nosession")[:64]
dp = os.path.join(root, ".codex", "logs", f"declared-risk-{sid}.json")
try:
    with open(dp, encoding="utf-8") as f:
        declared = json.load(f).get("level")
except Exception:
    pass

event = {"hook_id": "pre-implementation-gate", "hook_event_name": "PreToolUse", "runtime": "codex",
         "session_id": raw.get("session_id", "") or "", "branch": os.environ.get("SAGE_BRANCH", ""),
         "declared_max": declared, "changes": changes}

pg = (profile.get("risk") or {}).get("plan_glob", "plan_docs/00-base_plan/**/*.md")
paths = sorted(glob.glob(os.path.join(root, pg), recursive=True), key=lambda p: -os.path.getmtime(p)) if os.path.isdir(os.path.join(root, "plan_docs")) else []
plan_files = []
for p in paths:
    try:
        with open(p, encoding="utf-8", errors="ignore") as f: c = f.read()
    except Exception: c = ""
    plan_files.append({"path": rel(p), "content": c})
snapshot = {"plan_files": plan_files, "review_candidates": []}

decision = core.decide(event, profile, snapshot, None)

def msg(d):
    k = d.get("message_key"); fs = d.get("file_short",""); rs = d.get("reason","")
    table = {
        "block_desktop": f"[GATE BLOCK - Desktop] chatforyou-desktop/src 직접수정 금지. 파일: {fs}",
        "block_l3_no_plan": f"[GATE BLOCK - L3] L3 작업 + plan 문서 없음. 파일: {fs} | 근거: {rs}",
        "block_l3_strategy_unresolved": f"[GATE BLOCK - L3] L3 review 전략 미선택(unresolved) → 리뷰 확인 불가. 파일: {fs} (override required)",
        "warn_l3_no_review": f"[GATE WARN - L3] 2라운드 리뷰 문서 미확인. 파일: {fs} | 근거: {rs}",
        "warn_l2_no_plan": f"[GATE WARN - L2] 소스/설정 변경인데 plan 문서 없음. 파일: {fs} | 근거: {rs}",
        "ok_l3": f"[GATE OK - L3] review 확인됨 | {fs}",
        "ok_l2": f"[GATE OK - L2] plan 확인 | {fs}",
    }
    return table.get(k, "")

m = msg(decision)
if decision["status"] == "block":
    if m: print(m, file=sys.stderr)
elif m:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": m}}, ensure_ascii=False))
sys.exit(decision["exit_code"])
PYEOF
exit $?
