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
from sage.diagnostic_contract import render_recovery
from sage.diagnostics import Diagnostic

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


def _project_hook_state(root, hook):
    """Return unknown|project|damaged for a non-built-in manifest entry."""
    path = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    if not os.path.exists(path):
        return "unknown"
    try:
        with open(path, encoding="utf-8") as stream:
            manifest = json.load(stream)
    except Exception:
        return "damaged"
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), dict):
        return "damaged"
    key = f"hooks/{hook}"
    if key not in manifest["assets"]:
        return "unknown"
    entry = manifest["assets"][key]
    if (not isinstance(entry, dict) or entry.get("origin") != "project"
            or entry.get("form") != "core_adapter"):
        return "damaged"
    return "project"


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
        return Diagnostic("entry.profile_missing_damaged")
    # codex 의 hook 등록은 `.codex/hooks.json` 이다(`config.toml` 은 MCP managed-block 소유).
    # 안내가 엉뚱한 파일을 가리키면 사용자가 지워도 차단이 안 풀린다.
    settings = {"claude": ".claude/settings.json", "codex": ".codex/hooks.json"}.get(runtime)
    return Diagnostic("entry.not_an_install_target", settings=settings or "")



# --- 표시 언어 -------------------------------------------------------------
#
# `sage.i18n` 을 import 하지 않는다. 이 파일은 설치된 hook 의 진입점이고, 엔진 catalog 를
# 끌어오면 hook 이 엔진 없이는 못 도는 물건이 된다. 대신 `run_hook` 을 찾는 것과 같은 방식으로
# **core_dir 의 hook catalog** 를 찾는다 — 출력 도메인이 hook 이므로 catalog 도 hook 것이다.

def _hook_locale(core_dir, root):
    """(translate, language). catalog 를 못 찾아도 hook 은 서야 하므로 절대 예외를 올리지 않는다."""
    def fallback(key, **arguments):
        return f"[SAGE] message_key={key}"

    try:
        runtime_dir = os.path.join(core_dir, "runtime")
        for candidate in (runtime_dir, core_dir):
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
        import i18n as hook_i18n
        language = hook_i18n.context.resolve(root)[0]

        def translate(key, **arguments):
            text = hook_i18n.frag(language, key)
            if not text:
                return f"[SAGE] message_key={key}"
            try:
                return text.format(**arguments)
            except (KeyError, IndexError, ValueError):
                return f"[SAGE] message_key={key}"

        return translate, language
    except Exception:
        return fallback, "ko"


def _say(core_dir, root, diagnostic):
    """진단 하나를 사람이 읽는 한 줄로. 문자열이 오면 그대로 통과시킨다(이행 중 경로)."""
    from sage.diagnostics import render
    translate, _ = _hook_locale(core_dir, root)
    return render(diagnostic, translate, "hook")


def _prepare_gate_profile(root, hook, runtime=None, project_hook=False):
    """Inject the compiled profile for every consumer; safety hooks fail closed on drift."""
    if hook not in _PROFILE_HOOKS and not project_hook:
        return None
    # Hook subprocess가 상위 shell의 다른 프로젝트 profile을 상속하더라도 현재 root의 정책만 사용한다.
    os.environ.pop("SAGE_PROFILE", None)
    required = hook in _PROFILE_REQUIRED_HOOKS or project_hook

    yaml_path = os.path.join(root, "sage", "project-profile.yaml")
    json_path = os.path.join(root, "sage", "project-profile.json")
    if hook in _BASELINE_HOOKS and not os.path.exists(yaml_path) and not os.path.exists(json_path):
        return None
    try:
        with open(yaml_path, encoding="utf-8") as fh:
            yaml_profile = yaml.safe_load(fh) or {}
    except Exception as e:
        message = Diagnostic("entry.profile_yaml_unreadable", path=yaml_path,
                             evidence=f"{type(e).__name__}: {e}")
        if isinstance(e, FileNotFoundError):
            message = (message, _missing_profile_hint(root, runtime))
        return message if required else None
    try:
        with open(json_path, encoding="utf-8") as fh:
            json_profile = json.load(fh)
    except Exception as e:
        message = Diagnostic("entry.compiled_profile_unreadable", path=json_path,
                             evidence=f"{type(e).__name__}: {e}")
        return message if required else None

    if not isinstance(yaml_profile, dict) or not isinstance(json_profile, dict):
        message = Diagnostic("entry.profile_not_mapping")
        return message if required else None
    from sage.profile_compile import ProfileCompileError, materialize_profile
    try:
        expected_profile = materialize_profile(yaml_profile)
    except ProfileCompileError as e:
        message = Diagnostic("entry.raw_risk_type", evidence=str(e))
        return message if required else None
    if expected_profile != json_profile:
        message = Diagnostic("entry.profile_pair_mismatch")
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


def _render_bootstrap_block(runtime, hook, message, core_dir=None, root=None):
    detail = message
    if isinstance(message, tuple):
        detail = " ".join(_say(core_dir, root, part) for part in message)
    else:
        detail = _say(core_dir, root, message)
    text = _say(core_dir, root, Diagnostic("entry.blocked", hook=hook, detail=detail))
    if runtime == "codex" and hook == "stop-compliance-report":
        print(json.dumps({"decision": "block", "reason": text}, ensure_ascii=False))
        return 0
    print(text, file=sys.stderr)
    return 2


def _required_sage_version(root):
    """shared profile 의 exact required_version. 못 읽으면 None — 안내용 값이지 판정값이 아니다.

    호환성 판정은 정수 API 가 소유한다. 이 문자열은 "그럼 어느 SAGE 를 깔아야 하나" 에만 답한다.
    그래서 읽기에 실패해도 판정을 바꾸지 않고 그 줄만 빠진다.
    """
    try:
        with open(os.path.join(root, "sage", "project-profile.yaml"), encoding="utf-8") as fh:
            profile = yaml.safe_load(fh) or {}
        value = profile.get("sage", {}).get("required_version")
        return value if isinstance(value, str) and value else None
    except Exception:
        return None


def _runtime_api_preflight(runtime, hook, root, core_dir, enforcing):
    """project core 를 import 하기 **전에** 정수 하나로 호환성을 닫는다.

    이 함수가 `_load_run_hook()` 앞에 서는 것 자체가 계약이다. 뒤로 밀리면 새 core 가
    아직 없는 `sage.*` 를 import 하면서 `ModuleNotFoundError` 가 먼저 나오고, 그 traceback 은
    host 에 따라 그냥 "hook 이 죽었다" 로 해석된다 — 정책을 실행해야 할 게이트가 조용히 빠진다.

    manifest 파일 자체를 못 읽는 경우는 여기서 다루지 않는다. 그건 이 검사의 소관이 아니라
    기존 부트스트랩 경로(`_prepare_gate_profile`)가 이미 소유한 상태다. 여기서 함께 처리하면
    같은 상태에 두 개의 다른 메시지가 생긴다.

    돌려주는 값이 `None` 이면 계속 진행한다. 정수면 그 값이 프로세스 exit code 다.
    """
    from sage.runtime_api import compatibility

    manifest_path = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        return None

    status, evidence = compatibility(manifest)
    if status in ("ok", "legacy"):
        return None

    if status == "too_old":
        code = "runtime.api_too_old"
    elif evidence.get("reason") in ("marker_missing", "marker_missing_version_unreadable"):
        code = "runtime.api_marker_missing"
    else:
        code = "runtime.api_marker_damaged"

    translate, _ = _hook_locale(core_dir, root)
    required_version = _required_sage_version(root)
    body = _say(core_dir, root, Diagnostic(
        code,
        required=evidence.get("required_api", "?"),
        current=evidence.get("current_api", "?"),
        reason=evidence.get("reason", "unknown")))
    # code 를 화면에 남긴다. 번역된 문장은 언어마다 다르지만 code 는 같다 — 사용자가 그대로
    # 검색할 수 있고 CI 가 수집할 수 있는 유일한 조각이다. 문장만 내면 그게 사라진다.
    tail = ([translate("hook.runtime.required_sage", version=required_version)]
            if required_version else [])
    tail.extend(render_recovery(code, translate, "hook", host=runtime))

    if not enforcing:
        # logger·baseline 하나의 비호환이 host 작업 전체를 막을 이유는 없다. 다만 조용히
        # 넘어가지도 않는다 — 실제 write 는 같은 preflight 를 통과한 gate 가 막는다.
        print("\n".join([f"[sage-runtime-api] WARN [{code}] {body}", *tail]), file=sys.stderr)
        return 0

    text = "\n".join([f"⛔ BLOCK [{code}]", body, *tail])

    if runtime == "codex" and hook == "stop-compliance-report":
        # Codex Stop 의 wire 계약은 stdout 단일 JSON + rc 0 이다. 진단 UX 를 이유로 모든 host
        # event 를 exit 2 로 통일하지 않는다 — 통일하는 순간 Stop 이 깨진다.
        print(json.dumps({"decision": "block", "reason": text}, ensure_ascii=False))
        return 0
    print(text, file=sys.stderr)
    return 2


def _notify_version_contract(root, hook, core_dir=None):
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
    suffix = (_say(core_dir, root, Diagnostic("entry.remediation",
                                              actions="; ".join(remediations)))
              if remediations else "")
    print("[sage-version] WARN "
          f"required={axes.required} installed={axes.installed} "
          f"generated={axes.generated} runtime={axes.runtime}{suffix}", file=sys.stderr)


def main():
    _harden_io_encoding()
    # 도움말은 인자를 읽기 전에 만들어야 하므로 root/core-dir 을 아직 모른다. cwd 기준으로
    # 해석한다 — 표시 언어는 실행 하나의 성질이고, 이 화면이 가리키는 프로젝트도 cwd 다.
    help_say, _ = _hook_locale(_resolve_core_dir(os.getcwd(), None), os.getcwd())
    ap = argparse.ArgumentParser(prog="sage-hook",
                                 description=help_say("hook.entry.usage_description"))
    ap.add_argument("--runtime", required=True, choices=["claude", "codex"])
    ap.add_argument("--hook", required=True)
    ap.add_argument("--root", default=None, help=help_say("hook.entry.usage_root"))
    ap.add_argument("--core-dir", default=None, help=help_say("hook.entry.usage_core_dir"))
    ap.add_argument("--path", default=None, help=help_say("hook.entry.usage_path"))
    a = ap.parse_args()
    root = _resolve_root(a.runtime, a.root)
    os.environ.setdefault(_PROJECT_ROOT_ENV, root)
    core_dir = _resolve_core_dir(root, a.core_dir)
    raw_text = sys.stdin.read() if not sys.stdin.isatty() else ""
    _notify_version_contract(root, a.hook, core_dir)
    project_state = (_project_hook_state(root, a.hook)
                     if a.hook not in _FAIL_CLOSED_HOOKS else "unknown")
    fail_closed = a.hook in _FAIL_CLOSED_HOOKS or project_state in ("project", "damaged")
    # project core 를 import 하기 전에 선다. 이 위치가 계약이며 mutation test 가 고정한다.
    api_exit = _runtime_api_preflight(a.runtime, a.hook, root, core_dir, fail_closed)
    if api_exit is not None:
        return api_exit
    profile_error = _prepare_gate_profile(
        root, a.hook, a.runtime, project_hook=project_state == "project")
    if profile_error:
        if _is_stop_retry(a.hook, raw_text):
            detail = (" ".join(_say(core_dir, root, part) for part in profile_error)
                      if isinstance(profile_error, tuple)
                      else _say(core_dir, root, profile_error))
            print(_say(core_dir, root, Diagnostic("entry.stop_retry_pass",
                                                  hook=a.hook, detail=detail)),
                  file=sys.stderr)
            return 0
        return _render_bootstrap_block(a.runtime, a.hook, profile_error, core_dir, root)
    try:
        run_hook = _load_run_hook(core_dir)
    except Exception as e:
        # 코어 로드 실패 = hook 무력화 → 조용히 통과 말고 surface(gate-disable 은 시끄럽게).
        print(_say(core_dir, root, Diagnostic("entry.core_load_failed", path=core_dir,
                                              evidence=f"{type(e).__name__}: {e}")),
              file=sys.stderr)
        return 2 if fail_closed else 0
    try:
        if a.path is None:
            return run_hook.dispatch(a.runtime, a.hook, root, core_dir, raw_text)
        return run_hook.dispatch(
            a.runtime, a.hook, root, core_dir, raw_text, direct_path=a.path)
    except Exception as e:
        print(_say(core_dir, root, Diagnostic("entry.dispatch_failed", hook=a.hook,
                                              evidence=f"{type(e).__name__}: {e}")),
              file=sys.stderr)
        return 2 if fail_closed else 0


if __name__ == "__main__":
    sys.exit(main())
