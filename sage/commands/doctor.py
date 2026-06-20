"""sage doctor — 옵션 의존성 점검 + reviewer_resolution 노출 (step10).

Codex 2R 합의: cross-invocation 경로(§12 미해결, codex-host→Claude)를 v1 에서 fallback 으로 닫음.
reviewer_resolution 은 순수 판정 함수, doctor 가 옵션 의존성(gstack/codegraph/vault) + reviewer mode 를 정보성 출력.
gstack 가용성 = profile requires/capabilities + PATH which (개인경로 의존 금지).
exit: 정상/degraded/의존성미설치 = 0, profile YAML 파싱 오류(설정 무시됨) = 1 (Codex P1: 실패 원인 구분).
"""

import os
import platform
import shutil
import sys


def register(sub):
    p = sub.add_parser("doctor", help="SAGE 실행에 필요한 도구와 리뷰 설정을 점검합니다")
    p.add_argument("--profile", default=None, help="project-profile.yaml 경로 (없으면 templates 기본)")
    p.set_defaults(func=run)


def reviewer_resolution(profile: dict, caps: dict) -> dict:
    """Phase 05 reviewer 해석 (순수). caps={'gstack':bool} 는 doctor 가 주입.

    결정표(Codex 2R 합의 + P2-8 대칭 능력게이팅):
    - cross_model off                              → clean_context_same_runtime (의도적, degraded=false)
    - cross on, claude-host, claude_host설정 + gstack가용 → opposite_runtime(codex)
    - cross on, claude-host, gstack 불가            → clean_context fallback (degraded, gstack_unavailable)
    - cross on, codex-host, codex_host설정 + claude가용  → opposite_runtime(claude)
    - cross on, codex-host, codex_host설정 + claude불가  → clean_context fallback (degraded, claude_cli_unavailable, §12)
    - cross on, codex-host, codex_host 미설정        → clean_context fallback (degraded, codex_host_claude_invocation_unresolved, §12)

    P2-8(역방향 스텁 제거): 이전엔 codex-host 가 codex_host 필드만 있으면 능력검증 없이 opposite 를
    맹신했다(claude-host 는 gstack 능력을 요구하는데 비대칭). codex-host→Claude 도 claude CLI 능력
    (caps.claude)을 요구해 대칭화 — 경로 설정 + 실제 호출가능성 둘 다 확인. 실행 명령 자체는 런타임
    config(invocation.codex_host)가 정의(doctor 는 진단만)."""
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
        if caps.get("claude"):
            return res("opposite_runtime", "claude", False, False, None,
                       "codex-host → Claude (경로 설정 + claude CLI 가용)")
        return res("clean_context_same_runtime", "codex", True, True, "claude_cli_unavailable",
                   "codex-host→Claude 경로 설정됐으나 claude CLI 미가용 → clean-context fallback (§12)")
    return res("clean_context_same_runtime", "codex", True, True, "codex_host_claude_invocation_unresolved",
               "codex-host→Claude 호출 경로 미확정(§12) → v1 fallback")


_DEFAULT_PROFILE = {"runtime": {"host": "claude"}, "options": {"cross_model": False}}


def _load_profile(path):
    """반환 (profile|None, status). status 로 실패 원인 구분(Codex P1):
    'ok' | 'missing_file' | 'missing_pyyaml' | 'parse_error:<예외명>'.
    (이전엔 셋 다 None 으로 뭉개 사용자가 설정 무시 여부를 알 수 없었음.)"""
    if not os.path.exists(path):
        return None, "missing_file"
    try:
        import yaml  # pyyaml (선언 의존성)
    except ImportError:
        return None, "missing_pyyaml"
    try:
        with open(path, encoding="utf-8") as f:
            return (yaml.safe_load(f) or {}), "ok"
    except Exception as e:
        return None, f"parse_error:{type(e).__name__}"


def run(args):
    from sage import _resources
    prof_path = args.profile or os.path.join(_resources.templates_dir(), "project-profile.yaml")
    profile, status = _load_profile(prof_path)
    print("== sage doctor ==")
    rc = 0
    if status == "ok":
        pass  # profile 정상 로드
    elif status == "missing_file":
        print(f"  ℹ️  profile 없음 ({prof_path}) — 기본값 가정 (sage install 후 값 채움)")
        profile = dict(_DEFAULT_PROFILE)
    elif status == "missing_pyyaml":
        print(f"  ⚠️  WARN pyyaml 미설치 → profile 검사 불가, 기본값 가정. `pip install pyyaml` (선언 의존성)")
        profile = dict(_DEFAULT_PROFILE)
    elif status.startswith("parse_error"):
        rc = 1  # profile 이 존재하나 깨짐 = 실제 오류(설정이 조용히 무시되는 것 방지)
        print(f"  ❌ FAIL profile YAML 파싱 오류({status.split(':', 1)[1]}): {prof_path}")
        print(f"        → 선언한 설정이 무시됩니다. YAML 수정 필요.")
        profile = dict(_DEFAULT_PROFILE)

    # 실행 환경(P3-11 이식성): OS / python / bash 점검. 어댑터는 bash + python3(SAGE_PYTHON override)이라
    # Windows 네이티브는 Git Bash/WSL + python(3) 필요 → 가시화. bash 부재 = 어댑터 구동 불가(치명).
    bash_path = shutil.which("bash")
    print("## 실행 환경")
    print(f"  OS       : {platform.system()} ({os.name})")
    print(f"  python   : {platform.python_version()} (sys.executable={sys.executable})")
    print(f"  bash     : {bash_path or 'NOT FOUND'}" + ("" if bash_path else "  ⚠️  어댑터(.sh) 구동 불가 — Git Bash/WSL 필요"))
    if os.name == "nt" or platform.system() == "Windows":
        print("  ⚠️  Windows 네이티브: 어댑터는 Git Bash/WSL 에서만 동작. python3 부재 시 SAGE_PYTHON=python 설정.")

    # 옵션 의존성
    caps_prof = profile.get("capabilities", {}) or {}
    gstack_avail = bool(shutil.which("gstack")) or bool(caps_prof.get("gstack"))
    claude_avail = bool(shutil.which("claude")) or bool(caps_prof.get("claude"))   # P2-8: 역방향 능력 검증
    opts = profile.get("options", {}) or {}
    vault = (profile.get("knowledge_capture", {}) or {}).get("vault_path", "")
    print("## 옵션 의존성")
    print(f"  cross_model : {opts.get('cross_model', False)}")
    print(f"  gstack      : {'available' if gstack_avail else 'unavailable'} (PATH which gstack | capabilities.gstack)")
    if (profile.get("runtime", {}) or {}).get("host") == "codex":   # 역방향(codex→claude) 진단 시에만 노출
        print(f"  claude CLI  : {'available' if claude_avail else 'unavailable'} (PATH which claude | capabilities.claude)")
    print(f"  codegraph   : {opts.get('codegraph', 'optional')} (MCP 필요 — 미연결 시 rg/read degrade)")
    print(f"  obsidian    : vault_path={'set' if vault else 'empty → 기능 OFF(N/A)'}")

    # reviewer resolution
    rr = reviewer_resolution(profile, {"gstack": gstack_avail, "claude": claude_avail})
    print("## Phase 05 reviewer")
    print(f"  mode    : {rr['reviewer_mode']} (runtime={rr['reviewer_runtime']})")
    print(f"  notice  : {rr['notice']}")
    if rr["reviewer_degraded"]:
        print(f"  ⚠️  L3 REVIEW DEGRADED: {rr['reviewer_degrade_reason']}")
    return rc
