#!/bin/bash
# pre-phase4-checklist-gate — Claude adapter (rendered)
# SSOT: scripts/sage_harness/hooks/pre_phase4_checklist_gate_core.py
# adapter 책임: 입력추출(file_path 단일) / fs_adapter(plan_reads → glob/read → snapshot) /
#              경로·env 바인딩 / 출력렌더(plain stdout + exit). gate 판정은 core. (직접수정 금지)
# profile 외부주입 필수($SAGE_PROFILE) — 없으면 통과(exit 0).

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
CORE_DIR="${SAGE_HOOK_CORE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

INPUT=$(cat)

SAGE_HOOK_INPUT="$INPUT" python3 - "$PROJECT_ROOT" "$CORE_DIR" <<'PYEOF'
import sys, os, glob, json
root, core_dir = sys.argv[1], sys.argv[2]
sys.path.insert(0, core_dir)
import pre_phase4_checklist_gate_core as core

try:
    raw = json.loads(os.environ.get("SAGE_HOOK_INPUT", "{}"))
except Exception:
    sys.exit(0)

prof_path = os.environ.get("SAGE_PROFILE", "")
if not prof_path or not os.path.exists(prof_path):
    sys.exit(0)
with open(prof_path, encoding="utf-8") as f:
    profile = json.load(f)

def rel(p):
    if not p:
        return ""
    if not os.path.isabs(p):
        return p
    try:
        return os.path.relpath(p, root)
    except Exception:
        return p

fp = (raw.get("tool_input") or {}).get("file_path") or ""
event = {"hook_id": "pre-phase4-checklist-gate", "hook_event_name": "PreToolUse",
         "runtime": "claude", "session_id": raw.get("session_id", "") or "",
         "changes": ([{"path": rel(fp), "op": "write"}] if fp else [])}

# fs_adapter: plan_reads → glob/read → snapshot (root-상대 경로)
reads = core.plan_reads(event, profile)
glob_results, files = {}, {}
for g in reads["globs"]:
    matches = sorted(os.path.relpath(p, root) for p in glob.glob(os.path.join(root, g)))
    glob_results[g] = matches
    for rp in matches:
        try:
            with open(os.path.join(root, rp), encoding="utf-8") as fh:
                files[rp] = fh.read()
        except Exception:
            files[rp] = None
snapshot = {"glob_results": glob_results, "files": files}

decision = core.decide(event, profile, snapshot)


def build_msg(dec):
    s = dec["status"]
    if s == "block":
        lines = [f"⛔ [GATE BLOCK — Phase 3→4] 체크리스트 미완료 {dec['total_unchecked']}건",
                 f"  기능: {dec['base']}",
                 "  04-analyze 작성 전 아래 항목을 완료(또는 N/A 사유와 함께 [x])하세요:"]
        for ev in dec["evidence"]:
            lines.append(f"  ▸ {ev['label']}: {ev['file']} ({len(ev['unchecked'])}건 미완료)")
            for it in ev["unchecked"][:6]:
                t = it["text"]
                lines.append(f"      L{it['line']}: {t if len(t) <= 90 else t[:87] + '...'}")
            extra = len(ev["unchecked"]) - 6
            if extra > 0:
                lines.append(f"      ... 외 {extra}건")
        return "\n".join(lines)
    if s == "warn":
        return f"⚠️  [GATE WARN — Phase 3→4] '{dec['base']}' 의 03-implementation 문서를 찾지 못했습니다."
    if s == "ok":
        return f"✅ [GATE OK — Phase 3→4] '{dec['base']}' 체크리스트 완료 확인"
    return ""

msg = build_msg(decision)
if msg:
    print(msg)
sys.exit(decision["exit_code"])
PYEOF
exit $?
