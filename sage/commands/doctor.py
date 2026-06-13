"""sage doctor — 옵션 의존성 점검 + reviewer_resolution 노출 (step10).

Codex 2R 합의: cross-invocation 경로(§12 미해결, codex-host→Claude)를 v1 에서 fallback 으로 닫음.
reviewer_resolution 은 순수 판정 함수, doctor 가 옵션 의존성(gstack/codegraph/vault) + reviewer mode 를 정보성 출력.
gstack 가용성 = profile requires/capabilities + PATH which (개인경로 의존 금지). 항상 exit 0.
"""

import os
import shutil
import sys


def register(sub):
    p = sub.add_parser("doctor", help="옵션 의존성 점검 + reviewer fallback 노출")
    p.add_argument("--profile", default=None, help="project-profile.yaml 경로 (없으면 templates 기본)")
    p.set_defaults(func=run)


def reviewer_resolution(profile: dict, caps: dict) -> dict:
    """Phase 05 reviewer 해석 (순수). caps={'gstack':bool} 는 doctor 가 주입.

    4행 결정표(Codex 2R 합의):
    - cross_model off               → clean_context_same_runtime (의도적, degraded=false)
    - cross on, claude-host, gstack  → opposite_runtime(codex)
    - cross on, claude-host, !gstack → clean_context fallback (degraded, gstack_unavailable)
    - cross on, codex-host           → clean_context fallback (degraded, codex_host_claude_invocation_unresolved)
    """
    runtime = profile.get("runtime", {}) or {}
    host = runtime.get("host", "claude")
    cross = bool((profile.get("options", {}) or {}).get("cross_model", False))
    invocation = (profile.get("cross_model", {}) or {}).get("invocation", {}) or {}

    def res(mode, rt, fb, deg, reason, notice):
        return {"reviewer_mode": mode, "reviewer_runtime": rt, "fallback_used": fb,
                "reviewer_degraded": deg, "reviewer_degrade_reason": reason, "notice": notice}

    if not cross:
        return res("clean_context_same_runtime", host, False, False, None,
                   "cross_model off — 의도적 same-runtime (degraded 아님)")
    if host == "claude":
        if invocation.get("claude_host") and caps.get("gstack"):
            return res("opposite_runtime", "codex", False, False, None,
                       "claude-host → Codex via gstack /codex")
        return res("clean_context_same_runtime", "claude", True, True, "gstack_unavailable",
                   "cross_model on 이나 gstack 미가용 → clean-context fallback (모델편향 못없애는 최소안전선)")
    # host == codex
    if invocation.get("codex_host"):
        return res("opposite_runtime", "claude", False, False, None, "codex-host → Claude (경로 설정됨)")
    return res("clean_context_same_runtime", "codex", True, True, "codex_host_claude_invocation_unresolved",
               "codex-host→Claude 호출 경로 미확정(§12) → v1 fallback")


def _load_profile(path):
    try:
        import yaml  # pyyaml (선언 의존성)
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return None


def run(args):
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # sage_project
    prof_path = args.profile or os.path.join(here, "templates", "project-profile.yaml")
    profile = _load_profile(prof_path)
    print("== sage doctor ==")
    if profile is None:
        print(f"  (profile 로드 실패/pyyaml 미설치: {prof_path}) — 기본값 가정")
        profile = {"runtime": {"host": "claude"}, "options": {"cross_model": False}}

    # 옵션 의존성
    gstack_avail = bool(shutil.which("gstack")) or bool((profile.get("capabilities", {}) or {}).get("gstack"))
    opts = profile.get("options", {}) or {}
    vault = (profile.get("knowledge_capture", {}) or {}).get("vault_path", "")
    print("## 옵션 의존성")
    print(f"  cross_model : {opts.get('cross_model', False)}")
    print(f"  gstack      : {'available' if gstack_avail else 'unavailable'} (PATH which gstack | capabilities.gstack)")
    print(f"  codegraph   : {opts.get('codegraph', 'optional')} (MCP 필요 — 미연결 시 rg/read degrade)")
    print(f"  obsidian    : vault_path={'set' if vault else 'empty → 기능 OFF(N/A)'}")

    # reviewer resolution
    rr = reviewer_resolution(profile, {"gstack": gstack_avail})
    print("## Phase 05 reviewer")
    print(f"  mode    : {rr['reviewer_mode']} (runtime={rr['reviewer_runtime']})")
    print(f"  notice  : {rr['notice']}")
    if rr["reviewer_degraded"]:
        print(f"  ⚠️  L3 REVIEW DEGRADED: {rr['reviewer_degrade_reason']}")
    return 0
