"""sage validate — 스키마 · drift · staleness 검사 (읽기전용).

Codex 2R 합의(step5, hook):
- 읽기전용: manifest 갱신 안 함(갱신은 generate --write). validate 가 갱신하면 staleness 은폐기가 됨.
- per-asset 판정: hash 재계산 대조 불일치=STALE / 파일없음=FAIL(missing) / regression 실패=FAIL.
  전부 일치 + (--check 아니면) regression PASS = PASS. unresolved/risk/safety_degraded = WARN(표시만).
- exit: PASS=0 / FAIL=1 / TOOL_ERR=2 / STALE=3. 우선순위 FAIL > STALE > WARN > PASS.
- orphan(spec 있고 manifest 없음)=WARN / missing(manifest 있고 파일 없음)=FAIL.
- form: native(단일 .sh) / core_adapter(core+adapter). test 경로는 manifest 명시.
"""

import hashlib
import json
import os
import subprocess
import sys

from sage.commands._common import not_implemented

# severity rank (exit code 매핑은 _exit_code)
_SEV_RANK = {"PASS": 0, "WARN": 1, "STALE": 2, "FAIL": 3}
_EXIT = {"PASS": 0, "WARN": 0, "FAIL": 1, "STALE": 3}


def register(sub):
    # 주: JSON Schema 검증이 아니라 hash 기반 drift/staleness + regression 검사다(schema 파일은 참조 문서).
    p = sub.add_parser("validate", help="drift/staleness + regression 결정론 검사 (읽기전용)")
    p.add_argument("--check", action="store_true", help="staleness 만 (regression 미실행, 빠른 CI/hook용)")
    p.add_argument("--kind", choices=["hook", "agent", "skill", "all"], default="hook")
    p.add_argument("--id", default=None, help="단일 자산 검사")
    p.add_argument("--root", default=None, help="SAGE 레포 루트 (기본: cwd 에서 탐색)")
    p.set_defaults(func=run)


def _sha(path):
    with open(path, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def _safe_test_path(root, test):
    """manifest.test 를 안전 실행 경로로만 허용 (audit 4회차 P1: 오염 manifest 임의 실행 차단).

    조건: 상대경로 / `..` 없음 / .py·.sh 확장자 / realpath 가 root 내부 / scripts/sage_harness/ 하위.
    위반 시 None.
    """
    if not test or os.path.isabs(test) or ".." in test.split("/"):
        return None
    if not (test.endswith(".py") or test.endswith(".sh")):
        return None
    rp = os.path.realpath(os.path.join(root, test))
    root_rp = os.path.realpath(root)
    allowed = os.path.realpath(os.path.join(root, "scripts", "sage_harness"))
    if not rp.startswith(root_rp + os.sep) or not rp.startswith(allowed + os.sep):
        return None
    return rp if os.path.exists(rp) else None


def _find_root(start):
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(cur, "docs", "sage_harness", ".manifest.json")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _hook_paths(root, asset_id):
    """asset_id 'hooks/<id>' → 검사할 파일 경로 후보."""
    hid = asset_id.split("/", 1)[1]
    snake = hid.replace("-", "_")
    H = os.path.join(root, "scripts", "sage_harness", "hooks")
    return {
        "spec": os.path.join(root, "docs", "sage_harness", "hooks", f"{hid}.md"),
        "core_py": os.path.join(H, f"{snake}_core.py"),
        "native_sh": os.path.join(H, f"{hid}.sh"),
        "adapter_claude": os.path.join(H, "adapters", "claude", f"{hid}.sh"),
        "adapter_codex": os.path.join(H, "adapters", "codex", f"{hid}.sh"),
    }


def _validate_hook(root, asset_id, entry, run_regression):
    """단일 hook asset → (severity, [messages])."""
    msgs = []
    sev = "PASS"
    p = _hook_paths(root, asset_id)
    form = entry.get("form", "core_adapter")

    def bump(s):
        nonlocal sev
        if _SEV_RANK[s] > _SEV_RANK[sev]:
            sev = s

    # 1. spec hash
    if not os.path.exists(p["spec"]):
        bump("FAIL"); msgs.append(f"  FAIL missing spec: {p['spec']}")
    elif entry.get("spec_hash") and _sha(p["spec"]) != entry["spec_hash"]:
        bump("STALE"); msgs.append("  STALE spec_hash 불일치 (spec 변경 → 재생성 필요)")

    # 2. canonical hash
    canon = p["native_sh"] if form == "native" else p["core_py"]
    if not os.path.exists(canon):
        bump("FAIL"); msgs.append(f"  FAIL missing canonical: {canon}")
    elif entry.get("canonical_hash") and _sha(canon) != entry["canonical_hash"]:
        bump("STALE"); msgs.append("  STALE canonical_hash 불일치")

    # 3. adapter hash (core_adapter 만)
    if form == "core_adapter":
        for rt, key in (("claude", "adapter_claude"), ("codex", "adapter_codex")):
            ah = (entry.get("adapter_hash") or {}).get(rt)
            if not os.path.exists(p[key]):
                bump("FAIL"); msgs.append(f"  FAIL missing adapter[{rt}]: {p[key]}")
            elif ah and _sha(p[key]) != ah:
                bump("STALE"); msgs.append(f"  STALE adapter_hash[{rt}] 불일치")

    # 4. WARN 정보 (exit 영향 없음)
    if entry.get("safety_degraded"):
        bump("WARN"); msgs.append("  WARN safety_degraded=true")
    for u in entry.get("unresolved", []):
        bump("WARN"); msgs.append(f"  WARN unresolved: {u}")

    # 5. regression (--check 아니고 hash 가 FAIL/STALE 아니면)
    if run_regression and sev in ("PASS", "WARN"):
        test = entry.get("test")
        if test:
            tpath = _safe_test_path(root, test)
            if tpath is None:
                bump("FAIL"); msgs.append(f"  FAIL unsafe/missing test path: {test}")
            else:
                runner = ["python3", tpath] if tpath.endswith(".py") else ["bash", tpath]
                r = subprocess.run(runner, cwd=root, capture_output=True, text=True)
                if r.returncode != 0:
                    bump("FAIL"); msgs.append(f"  FAIL regression 실패: {test}")
    return sev, msgs


def _validate_interpretive(root, asset_id, entry, run_regression=True):
    """interpretive 자산(agent/skill) → spec_hash + claims_hash staleness + (선택)regression.

    asset_id 'agents/<id>' 또는 'skills/<id>' — prefix 에서 디렉토리 결정(독립: 하드코딩 아님)."""
    msgs = []
    sev = "PASS"
    subdir, aid = asset_id.split("/", 1)
    spec = os.path.join(root, "docs", "sage_harness", subdir, f"{aid}.md")
    claims = os.path.join(root, "docs", "sage_harness", subdir, f"{aid}.claims.yml")

    def bump(s):
        nonlocal sev
        if _SEV_RANK[s] > _SEV_RANK[sev]:
            sev = s

    if not os.path.exists(spec):
        bump("FAIL"); msgs.append(f"  FAIL missing spec: {spec}")
    elif entry.get("spec_hash") and _sha(spec) != entry["spec_hash"]:
        bump("STALE"); msgs.append("  STALE spec_hash 불일치")
    if not os.path.exists(claims):
        bump("FAIL"); msgs.append(f"  FAIL missing claims: {claims}")
    elif entry.get("claims_hash") and _sha(claims) != entry["claims_hash"]:
        bump("STALE"); msgs.append("  STALE claims_hash 불일치")
    for u in entry.get("unresolved", []):
        bump("WARN"); msgs.append(f"  WARN unresolved: {u}")
    # render_hash 는 interpretive/외부 산출물이라 v1 staleness 재계산 제외(정보성)
    test = entry.get("test")
    if run_regression and test and sev in ("PASS", "WARN"):
        tpath = _safe_test_path(root, test)
        if tpath is None:
            bump("FAIL"); msgs.append(f"  FAIL unsafe/missing test path: {test}")
        else:
            r = subprocess.run(["python3", tpath], cwd=root, capture_output=True, text=True)
            if r.returncode != 0:
                bump("FAIL"); msgs.append(f"  FAIL regression 실패: {test}")
    return sev, msgs


def run(args):
    # hook/agent/skill/all 전부 지원 (skill = interpretive, agent 와 동일 경로)

    root = _find_root(args.root)
    if not root:
        print("[sage validate] TOOL ERROR: docs/sage_harness/.manifest.json 을 찾을 수 없음", file=sys.stderr)
        return 2
    try:
        manifest = json.load(open(os.path.join(root, "docs", "sage_harness", ".manifest.json")))
    except Exception as e:
        print(f"[sage validate] TOOL ERROR: manifest 파싱 실패: {e}", file=sys.stderr)
        return 2

    assets = manifest.get("assets", {})
    prefixes = []
    if args.kind in ("hook", "all"):
        prefixes.append("hooks/")
    if args.kind in ("agent", "all"):
        prefixes.append("agents/")
    if args.kind in ("skill", "all"):
        prefixes.append("skills/")
    target_ids = [k for k in assets if any(k.startswith(p) for p in prefixes)]
    if args.id:
        target_ids = [k for k in target_ids if k.split("/", 1)[1] == args.id or k == args.id]
        if not target_ids:
            print(f"[sage validate] TOOL ERROR: manifest 에 '{args.id}' 없음", file=sys.stderr)
            return 2

    overall = "PASS"
    print(f"== sage validate ({args.kind}{', --check' if args.check else ''}) — {len(target_ids)} assets ==")
    for aid in sorted(target_ids):
        if aid.startswith("hooks/"):
            sev, msgs = _validate_hook(root, aid, assets[aid], run_regression=not args.check)
        else:  # agents/ or skills/ — interpretive
            sev, msgs = _validate_interpretive(root, aid, assets[aid], run_regression=not args.check)
        if _SEV_RANK[sev] > _SEV_RANK[overall]:
            overall = sev
        mark = {"PASS": "✅", "WARN": "⚠️ ", "STALE": "🔶", "FAIL": "❌"}[sev]
        print(f"{mark} {sev:5} {aid}")
        for m in msgs:
            print(m)

    # orphan: spec 있는데 manifest 없음 → WARN
    spec_dir = os.path.join(root, "docs", "sage_harness", "hooks")
    if os.path.isdir(spec_dir):
        for fn in sorted(os.listdir(spec_dir)):
            if fn.endswith(".md") and f"hooks/{fn[:-3]}" not in assets:
                if overall == "PASS":
                    overall = "WARN"
                print(f"⚠️  WARN  orphan spec (manifest 미등록): hooks/{fn[:-3]}")

    print(f"---- 종합: {overall} (exit {_EXIT[overall]}) ----")
    return _EXIT[overall]
