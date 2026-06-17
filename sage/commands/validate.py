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
from pathlib import Path

from sage.asset_paths import AssetPaths
from sage.commands._common import contract_version_of, not_implemented

# severity rank (exit code 매핑은 _exit_code)
_SEV_RANK = {"PASS": 0, "WARN": 1, "STALE": 2, "FAIL": 3}
_EXIT = {"PASS": 0, "WARN": 0, "FAIL": 1, "STALE": 3}


def register(sub):
    # 주: JSON Schema 검증이 아니라 hash 기반 drift/staleness + regression 검사다(schema 파일은 참조 문서).
    p = sub.add_parser("validate", help="drift/staleness + regression 결정론 검사 (읽기전용)")
    p.add_argument("--check", action="store_true", help="staleness 만 (regression 미실행, 빠른 CI/hook용)")
    p.add_argument("--schema", action="store_true", help="manifest 를 JSON Schema 로 구조검증 (jsonschema 선택의존, 미설치 시 WARN skip)")
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


def _schema_check(root, manifest):
    """manifest 를 schema/manifest.schema.json 으로 구조검증 → (sev, [msgs]).

    jsonschema 는 선택의존(미설치 시 WARN skip — 핵심 CLI 는 의존성 경량 유지). schema 파일은
    target root/schema 우선, 없으면 SAGE 번들(_resources). README 의 "schema valid" 주장을 재현가능하게 함.
    """
    try:
        import jsonschema
    except ImportError:
        return "WARN", ["  WARN jsonschema 미설치 — schema 구조검증 skip (pip install 'sage-harness[schema]')"]
    sp = os.path.join(root, "schema", "manifest.schema.json")
    if not os.path.exists(sp):
        from sage import _resources
        sp = os.path.join(_resources.schema_dir(), "manifest.schema.json")
    if not os.path.exists(sp):
        return "WARN", ["  WARN schema 파일 없음 — 구조검증 skip"]
    try:
        schema = json.loads(Path(sp).read_text(encoding="utf-8"))
        jsonschema.validate(manifest, schema)
        return "PASS", ["  ✅ manifest JSON Schema 구조검증 통과"]
    except jsonschema.ValidationError as e:
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        return "FAIL", [f"  FAIL schema 위반 @ {loc}: {e.message}"]


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
    """asset_id 'hooks/<id>' → 검사할 파일 경로 후보. 경로 규약은 AssetPaths 단일소스(P2-6)."""
    ap = AssetPaths(root, "hook", asset_id.split("/", 1)[1])
    return {
        "spec": ap.spec,
        "core_py": ap.core,
        "native_sh": ap.native,
        "adapter_claude": ap.adapter("claude"),
        "adapter_codex": ap.adapter("codex"),
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

    # 0. 미스탬프 감지(install 후 generate 전): hash 없음 → STALE "generate 필요"
    #    (pre-generate 등록만 된 hook 이 PASS 로 보여 위험을 가리는 것 방지 — Codex P2-6)
    stamped = entry.get("spec_hash") and (entry.get("render_hash") or entry.get("canonical_hash"))
    if not stamped and os.path.exists(p["spec"]):
        bump("STALE"); msgs.append("  STALE 미스탬프 — sage generate --write 로 hash 등록 필요")

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

    # 3b. 계약버전 (R3/P1-3): core.CONTRACT_VERSION 과 manifest 스탬프 대조.
    #     hash(내용) 드리프트와 별개로 core.decide() 인터페이스 변경을 잡는 두 번째 방어선.
    if form == "core_adapter" and os.path.exists(p["core_py"]):
        want = contract_version_of(p["core_py"])
        have = entry.get("adapter_contract_version")
        if want and have and want != have:
            bump("STALE"); msgs.append(f"  STALE 계약버전 불일치 ({have}→{want}) — sage generate 재스탬프 필요")

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


def _conformance_check(root, asset_id, claims_path):
    """render(.md) 산출물을 claims 에 conformance_lint → (bump_sev, [msgs]).

    P1-4(폐루프 비대칭 해소): hook 은 hash/contract_version 으로 generate↔validate 폐루프가 강제되나,
    agent/skill 은 conformance_lint 가 존재하되 validate 에 배선되지 않아 강제되지 않았다. 여기서 배선해
    "닫는 게이트=validate" 로 대칭화한다. render 는 여전히 interpretive(런타임 AI) — 결정론 생성은 하지 않음.
    - render(.claude|.codex/<subdir>/<id>.md) 부재 = skip(미렌더, 강제 대상 아님).
    - conformance FAIL(누락 required claim·금지위반) = validate FAIL(강제 — 비대칭의 본질).
    - conformance WARN(금지주제 미언급·서술형 미검출 등 약신호) = INFO(비게이팅, sev 불변 —
      validate 가 자체 descriptive unresolved 를 INFO 로 다루는 것과 동일 선. auto_approve 과민 회피).
    - pyyaml/conformance 미가용 = INFO skip(validate 경량 유지, exit 불변).
    conformance 모듈은 엔진 위치(_resources.sage_root)에서 로드 — validate 는 엔진 명령이므로
    타깃 vendored 본이 아닌 엔진 결정론 로직이 권위. contradiction_patterns 는 엔진 기본(commit/push)만
    (프로젝트 고유 패턴은 런타임 config 주입 영역)."""
    subdir, aid = asset_id.split("/", 1)
    renders = {rt: os.path.join(root, host, subdir, f"{aid}.md")
               for rt, host in (("claude", ".claude"), ("codex", ".codex"))}
    present = {rt: p for rt, p in renders.items() if os.path.exists(p)}
    if not present or not os.path.exists(claims_path):
        return "PASS", []
    try:
        from sage import _resources
        harness = os.path.join(_resources.sage_root(), "scripts", "sage_harness")
        if harness not in sys.path:
            sys.path.insert(0, harness)
        import conformance as cf
        import reverse_extract_common as rc   # P2-7: claims 단일 canonical 리더(pyyaml 우선+결정론 폴백)
    except Exception as e:
        return "PASS", [f"  INFO conformance skip — 모듈 로드 실패: {e}"]
    try:
        claims = rc.load_claims_yaml(claims_path)
    except Exception as e:
        return "PASS", [f"  INFO conformance skip — claims 파싱 실패: {e}"]

    bump = "PASS"
    msgs = []
    for rt, p in sorted(present.items()):
        try:
            res = cf.conformance_lint(Path(p).read_text(encoding="utf-8"), claims)
        except Exception as e:
            msgs.append(f"  INFO conformance[{rt}] skip — lint 오류: {e}")
            continue
        st = res["status"]
        if st == "FAIL":
            bump = "FAIL"
            mr = "; ".join(f"{m['type']}:{m['value']}" for m in res["missing_required"]) or "없음"
            ct = "; ".join(m["value"] for m in res["forbidden_policy_contradictions"]) or "없음"
            msgs.append(f"  FAIL conformance[{rt}] — 누락 required claim: {mr} | 금지위반: {ct}")
        elif st == "WARN":
            n_w = len(res["warnings"]); n_mp = len(res["forbidden_policy_missing"])
            msgs.append(f"  INFO conformance[{rt}] WARN(비게이팅) — 미검출 {n_w}건, 금지주제 미언급 {n_mp}건")
    return bump, msgs


def _validate_interpretive(root, asset_id, entry, run_regression=True):
    """interpretive 자산(agent/skill) → spec_hash + claims_hash staleness + conformance(P1-4) + (선택)regression.

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
    # descriptive unresolved(비게이팅) 표면화: claims.yml 의 confidence:unresolved 중 manifest gating 에 없는 것.
    # 서술형(절차/when_to_use 등)은 게이팅 제외 설계지만 조용히 숨으면 PDCA 핵심 의미가 빠질 수 있어 INFO 로 가시화(sev 불변).
    if os.path.exists(claims):
        try:
            total_unres = sum(1 for ln in Path(claims).read_text(encoding="utf-8").splitlines()
                              if "confidence: unresolved" in ln)
        except Exception:
            total_unres = 0
        descriptive = total_unres - len(entry.get("unresolved", []))
        if descriptive > 0:
            msgs.append(f"  INFO descriptive unresolved {descriptive}건 (비게이팅 — 절차/서술 의미 누락 주의, {os.path.basename(claims)} 확인)")
    # conformance lint (P1-4): render(.md) 가 존재하면 claim 부합을 강제 — hook hash/contract 강제와 대칭.
    #   --check(빠른 모드)에서도 실행(정규식·subprocess 없음 → cheap). FAIL=게이팅, WARN=INFO(비게이팅).
    csev, cmsgs = _conformance_check(root, asset_id, claims)
    bump(csev)
    msgs.extend(cmsgs)
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
        manifest = json.loads(Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).read_text())
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

    # JSON Schema 구조검증 (--schema, 선택)
    if args.schema:
        ssev, smsgs = _schema_check(root, manifest)
        mark = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[ssev]
        print(f"{mark} SCHEMA {ssev}")
        for m in smsgs:
            print(m)
        if _SEV_RANK[ssev] > _SEV_RANK[overall]:
            overall = ssev

        # profile 구조+의미 검증 (R2/P0-2): 오타 키·전략 부재·미정의 phase = 게이트 침묵 비활성.
        prof_path = os.path.join(root, "sage", "project-profile.json")
        if os.path.exists(prof_path):
            from sage.profile_validate import validate_profile
            try:
                prof = json.loads(Path(prof_path).read_text(encoding="utf-8"))
            except Exception:
                prof = None
            if prof is not None:
                _map = {"FAIL": "FAIL", "WARN": "WARN", "INFO": "PASS"}   # INFO 는 exit 무영향
                psev = "PASS"
                for sev, msg in validate_profile(prof, root):
                    mk = {"FAIL": "❌", "WARN": "⚠️ ", "INFO": "ℹ️ "}.get(sev, "")
                    print(f"  {mk} profile {sev}: {msg}")
                    if _SEV_RANK[_map[sev]] > _SEV_RANK[psev]:
                        psev = _map[sev]
                pmark = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[psev]
                print(f"{pmark} PROFILE {psev}")
                if _SEV_RANK[psev] > _SEV_RANK[overall]:
                    overall = psev

    print(f"---- 종합: {overall} (exit {_EXIT[overall]}) ----")
    return _EXIT[overall]
