"""sage-hook — hook 실행 콘솔 엔트리포인트 (W2b: bash 비의존 크로스플랫폼 진입).

기존 등록 command 는 `bash "<host>/hooks/<id>.sh"` 라 Windows(무 Git Bash/WSL)에서 실행이
막혔다. pip 이 설치하는 이 콘솔 스크립트(`sage-hook`/`sage-hook.exe`)를 등록 command 로 쓰면
bash·python 경로 추측 없이 어느 OS 에서도 동일하게 hook 이 돈다.

셸 어댑터가 하던 root/core-dir 해석을 여기로 이식하고, 실제 dispatch 는 core 트리의
`runtime/run_hook.py`(단일소스)를 재사용한다 — 프로젝트가 소유한 hook 코어 버전으로 동작.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys

import yaml

# 셸 어댑터와 동일: --root 없으면 host 별 env → git 루트 → cwd 순으로 프로젝트 루트 해석.
_ROOT_ENV = {"claude": "CLAUDE_PROJECT_DIR", "codex": "CODEX_PROJECT_ROOT"}
_PROJECT_ROOT_ENV = "SAGE_PROJECT_ROOT"
_GATE_HOOKS = {
    "pre-implementation-gate",
    "pre-phase4-checklist-gate",
    "stop-compliance-report",
}


def _resolve_root(runtime, explicit):
    if explicit:
        return os.path.abspath(explicit)
    env = os.environ.get(_PROJECT_ROOT_ENV) or os.environ.get(_ROOT_ENV.get(runtime, ""))
    if env:
        return os.path.abspath(env)
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True).stdout.strip()
        if top:
            return os.path.abspath(top)
    except Exception:
        pass
    return os.getcwd()


def _resolve_core_dir(root, explicit):
    """hook 코어 위치: 명시 → 프로젝트 로컬(설치본) → 패키지 번들 폴백.
    프로젝트 로컬을 우선해 '프로젝트가 자기 hook 코어를 소유' 모델을 보존한다."""
    if explicit:
        return os.path.abspath(explicit)
    local = os.path.join(root, "scripts", "sage_harness", "hooks")
    if os.path.isdir(os.path.join(local, "runtime")):
        return local
    from sage import _resources
    return _resources.hooks_src_dir()


def _load_run_hook(core_dir):
    """core-dir 의 runtime/run_hook.py 를 로드(top-level 이 hook_runtime/io_* 를 import 가능케 함)."""
    path = os.path.join(core_dir, "runtime", "run_hook.py")
    spec = importlib.util.spec_from_file_location("sage_run_hook", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _prepare_gate_profile(root, hook):
    """Gate hooks require a current compiled profile; advisory hooks stay fail-open."""
    if hook not in _GATE_HOOKS:
        return None

    yaml_path = os.path.join(root, "sage", "project-profile.yaml")
    json_path = os.path.join(root, "sage", "project-profile.json")
    try:
        with open(yaml_path, encoding="utf-8") as fh:
            yaml_profile = yaml.safe_load(fh) or {}
    except Exception as e:
        return f"프로필 YAML 로드 실패({yaml_path}): {type(e).__name__}: {e}"
    try:
        with open(json_path, encoding="utf-8") as fh:
            json_profile = json.load(fh)
    except Exception as e:
        return f"컴파일 프로필 로드 실패({json_path}): {type(e).__name__}: {e}"

    if not isinstance(yaml_profile, dict) or not isinstance(json_profile, dict):
        return "프로필 루트는 객체(mapping)여야 합니다."
    from sage.profile_compile import materialize_profile
    if materialize_profile(yaml_profile) != json_profile:
        return "project-profile.yaml과 project-profile.json이 다릅니다. sage generate를 다시 실행하세요."

    os.environ["SAGE_PROFILE"] = json_path
    return None


def _render_bootstrap_block(runtime, hook, message):
    text = f"[sage-hook] {hook} 차단: {message}"
    if runtime == "codex" and hook == "stop-compliance-report":
        print(json.dumps({"decision": "block", "reason": text}, ensure_ascii=False))
        return 0
    print(text, file=sys.stderr)
    return 2


def main():
    ap = argparse.ArgumentParser(prog="sage-hook",
                                 description="SAGE hook 실행(크로스플랫폼, bash 비의존)")
    ap.add_argument("--runtime", required=True, choices=["claude", "codex"])
    ap.add_argument("--hook", required=True)
    ap.add_argument("--root", default=None, help="프로젝트 루트(기본: env/git/cwd 자동 해석)")
    ap.add_argument("--core-dir", default=None, help="hook 코어 경로(기본: 프로젝트 로컬→번들)")
    a = ap.parse_args()
    root = _resolve_root(a.runtime, a.root)
    os.environ.setdefault(_PROJECT_ROOT_ENV, root)
    core_dir = _resolve_core_dir(root, a.core_dir)
    raw_text = sys.stdin.read() if not sys.stdin.isatty() else ""
    profile_error = _prepare_gate_profile(root, a.hook)
    if profile_error:
        return _render_bootstrap_block(a.runtime, a.hook, profile_error)
    try:
        run_hook = _load_run_hook(core_dir)
    except Exception as e:
        # 코어 로드 실패 = hook 무력화 → 조용히 통과 말고 surface(gate-disable 은 시끄럽게).
        print(f"⛔ [sage-hook] hook 코어 로드 실패({core_dir}) → {type(e).__name__}: {e}", file=sys.stderr)
        return 2 if a.hook in _GATE_HOOKS else 0
    return run_hook.dispatch(a.runtime, a.hook, root, core_dir, raw_text)


if __name__ == "__main__":
    sys.exit(main())
