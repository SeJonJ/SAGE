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
_FAIL_CLOSED_HOOKS = _GATE_HOOKS | {"generated-artifact-write-guard"}
_BASELINE_HOOKS = {
    "capture-declared-risk",
    "session-start-snapshot",
}
_PROFILE_HOOKS = _GATE_HOOKS | _BASELINE_HOOKS | {"post-tool-logger"}
_PROFILE_REQUIRED_HOOKS = _GATE_HOOKS | _BASELINE_HOOKS


def _harden_io_encoding():
    """Keep enforcement/report output alive on legacy Windows console encodings."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


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


def _missing_profile_hint(root, runtime):
    """프로필이 아예 없을 때의 복구 안내.

    게이트는 그대로 fail-closed 로 막는다(설치 마커 유무로 게이트를 통과시키면
    마커 하나만 지워도 게이트가 사라지는 우회로가 생긴다). 다만 원인이
    '설치가 깨짐' 인지 '애초에 SAGE 설치 대상이 아닌 디렉터리' 인지에 따라
    할 일이 정반대라, 안내 문구만 갈라준다.
    """
    manifest = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    if os.path.exists(manifest):
        return ("설치 흔적(manifest)은 있으나 프로필이 없다 — 설치가 손상됐다. "
                "`sage install --force` 로 복구한 뒤 `sage doctor` 로 확인하라.")
    # codex 의 hook 등록은 `.codex/hooks.json` 이다(`config.toml` 은 MCP managed-block 소유).
    # 안내가 엉뚱한 파일을 가리키면 사용자가 지워도 차단이 안 풀린다.
    settings = {"claude": ".claude/settings.json", "codex": ".codex/hooks.json"}.get(runtime, "hook 설정")
    return (f"설치 흔적(manifest)도 없다 — 이 디렉터리는 SAGE 설치 대상이 아닐 수 있다. "
            f"의도한 설치라면 `sage install` 을, 아니라면 {settings} 의 sage-hook 등록을 제거하라 "
            f"(설치 대상이 아닌 곳에 hook 만 남으면 모든 편집이 이렇게 차단된다).")


def _prepare_gate_profile(root, hook, runtime=None):
    """Inject the compiled profile for every consumer; safety hooks fail closed on drift."""
    if hook not in _PROFILE_HOOKS:
        return None
    # Hook subprocess가 상위 shell의 다른 프로젝트 profile을 상속하더라도 현재 root의 정책만 사용한다.
    os.environ.pop("SAGE_PROFILE", None)
    required = hook in _PROFILE_REQUIRED_HOOKS

    yaml_path = os.path.join(root, "sage", "project-profile.yaml")
    json_path = os.path.join(root, "sage", "project-profile.json")
    if hook in _BASELINE_HOOKS and not os.path.exists(yaml_path) and not os.path.exists(json_path):
        return None
    try:
        with open(yaml_path, encoding="utf-8") as fh:
            yaml_profile = yaml.safe_load(fh) or {}
    except Exception as e:
        message = f"프로필 YAML 로드 실패({yaml_path}): {type(e).__name__}: {e}"
        if isinstance(e, FileNotFoundError):
            message = f"{message}\n  → {_missing_profile_hint(root, runtime)}"
        return message if required else None
    try:
        with open(json_path, encoding="utf-8") as fh:
            json_profile = json.load(fh)
    except Exception as e:
        message = f"컴파일 프로필 로드 실패({json_path}): {type(e).__name__}: {e}"
        return message if required else None

    if not isinstance(yaml_profile, dict) or not isinstance(json_profile, dict):
        message = "프로필 루트는 객체(mapping)여야 합니다."
        return message if required else None
    from sage.profile_compile import ProfileCompileError, materialize_profile
    try:
        expected_profile = materialize_profile(yaml_profile)
    except ProfileCompileError as e:
        message = f"프로필 raw risk 필드 타입 오류: {e}"
        return message if required else None
    if expected_profile != json_profile:
        message = "project-profile.yaml과 project-profile.json이 다릅니다. sage generate를 다시 실행하세요."
        return message if required else None

    os.environ["SAGE_PROFILE"] = json_path
    return None


def _is_stop_retry(hook, raw_text):
    """Stop 재시도(`stop_hook_active`)인가 — 프로필 preflight 차단을 풀어야 하는 유일한 경우.

    플랫폼은 Stop hook 이 한 번 막으면 다음 Stop 입력에 `stop_hook_active: true` 를 실어 보낸다.
    거기서도 막으면 에이전트가 영원히 종료하지 못한다. 프로필 부재는 **재시도해도 저절로 낫지
    않는** 조건이라, 여기서 계속 막으면 그 무한루프가 확정된다. 그래서 재시도 1회는 통과시키되
    조용히 넘기지 않고 stderr 로 원인을 남긴다(다른 게이트들의 재시도 degrade 와 같은 방향).

    판정은 runtime 의 `_stop_hook_active` 와 같은 규칙 — bool True 와 문자열 "true" 만 active.
    `bool("false")` 가 True 라 문자열 "false" 를 재시도로 오인하면 첫 차단이 사라진다.
    """
    if hook != "stop-compliance-report":
        return False
    try:
        raw = json.loads(raw_text or "{}")
    except Exception:
        return False                      # 파싱 불가 = 재시도 근거 없음 → 첫 시도로 취급(teeth 보존)
    if not isinstance(raw, dict):
        return False
    value = raw.get("stop_hook_active")
    if value is True:
        return True
    return isinstance(value, str) and value.strip().lower() == "true"


def _render_bootstrap_block(runtime, hook, message):
    text = f"[sage-hook] {hook} 차단: {message}"
    if runtime == "codex" and hook == "stop-compliance-report":
        print(json.dumps({"decision": "block", "reason": text}, ensure_ascii=False))
        return 0
    print(text, file=sys.stderr)
    return 2


def _notify_version_contract(root, hook):
    if hook != "session-start-snapshot":
        return
    yaml_path = os.path.join(root, "sage", "project-profile.yaml")
    manifest_path = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    try:
        with open(yaml_path, encoding="utf-8") as fh:
            profile = yaml.safe_load(fh) or {}
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"[sage-version] WARN source=shared-profile unreadable error={type(exc).__name__}", file=sys.stderr)
        return
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"[sage-version] WARN source=manifest unreadable error={type(exc).__name__}", file=sys.stderr)
        return
    if not isinstance(profile, dict):
        print("[sage-version] WARN source=shared-profile unreadable error=NonObjectRoot", file=sys.stderr)
        return
    if not isinstance(manifest, dict):
        print("[sage-version] WARN source=manifest unreadable error=NonObjectRoot", file=sys.stderr)
        return

    from sage import __version__
    from sage.version_contract import version_axes, version_contract_issues

    issues = [issue for issue in version_contract_issues(profile, manifest, __version__)
              if issue.severity in ("WARN", "FAIL")]
    if not issues:
        return
    axes = version_axes(profile, manifest, __version__)
    remediations = list(dict.fromkeys(issue.remediation for issue in issues if issue.remediation))
    suffix = f"; 조치: {'; '.join(remediations)}" if remediations else ""
    print("[sage-version] WARN "
          f"required={axes.required} installed={axes.installed} "
          f"generated={axes.generated} runtime={axes.runtime}{suffix}", file=sys.stderr)


def main():
    _harden_io_encoding()
    ap = argparse.ArgumentParser(prog="sage-hook",
                                 description="SAGE hook 실행(크로스플랫폼, bash 비의존)")
    ap.add_argument("--runtime", required=True, choices=["claude", "codex"])
    ap.add_argument("--hook", required=True)
    ap.add_argument("--root", default=None, help="프로젝트 루트(기본: env/git/cwd 자동 해석)")
    ap.add_argument("--core-dir", default=None, help="hook 코어 경로(기본: 프로젝트 로컬→번들)")
    ap.add_argument("--path", default=None,
                    help="write-guard 직접호출 호환 경로(stdin JSON보다 우선)")
    a = ap.parse_args()
    root = _resolve_root(a.runtime, a.root)
    os.environ.setdefault(_PROJECT_ROOT_ENV, root)
    core_dir = _resolve_core_dir(root, a.core_dir)
    raw_text = sys.stdin.read() if not sys.stdin.isatty() else ""
    _notify_version_contract(root, a.hook)
    profile_error = _prepare_gate_profile(root, a.hook, a.runtime)
    if profile_error:
        if _is_stop_retry(a.hook, raw_text):
            print(f"[sage-hook] {a.hook} 재시도(stop_hook_active) — 프로필 문제로 차단하지 않고 통과: "
                  f"{profile_error}", file=sys.stderr)
            return 0
        return _render_bootstrap_block(a.runtime, a.hook, profile_error)
    try:
        run_hook = _load_run_hook(core_dir)
    except Exception as e:
        # 코어 로드 실패 = hook 무력화 → 조용히 통과 말고 surface(gate-disable 은 시끄럽게).
        print(f"⛔ [sage-hook] hook 코어 로드 실패({core_dir}) → {type(e).__name__}: {e}", file=sys.stderr)
        return 2 if a.hook in _FAIL_CLOSED_HOOKS else 0
    try:
        if a.path is None:
            return run_hook.dispatch(a.runtime, a.hook, root, core_dir, raw_text)
        return run_hook.dispatch(
            a.runtime, a.hook, root, core_dir, raw_text, direct_path=a.path)
    except Exception as e:
        print(f"⛔ [sage-hook] hook dispatch 실패({a.hook}) → "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return 2 if a.hook in _FAIL_CLOSED_HOOKS else 0


if __name__ == "__main__":
    sys.exit(main())
