"""`sage status [--json]` — 지금 이 프로젝트에서 SAGE 를 쓸 수 있는가.

## 무엇을 하지 않는가

전체 자산 hash 도, regression 도, peer CLI 호출도, 네트워크 접근도 하지 않는다. 그 검사들은
`sage validate` 와 `sage doctor` 가 이미 소유하고 있고, 여기서 다시 하면 "빠른 요약" 이라는
이 명령의 존재 이유가 사라진다. 문제를 발견하면 그 명령으로 **연결**하되 그 결과를 대신
만들어내지 않는다.

읽기 전용이다. tracked 파일과 `.sage` 를 바이트 하나 바꾸지 않고, 복구 명령을 자동 실행하지
않는다.

## READY 는 약속이다

읽지 못한 필수 입력을 "없음" 으로 처리하면 READY 가 거짓말이 된다. 그래서 판독 실패는 BLOCK
이거나 tool error 이고, 절대 조용한 통과가 아니다.
"""
import json
import os
import sys

from sage import __version__
from sage.diagnostic_contract import (BLOCK, TOOL_FAILURE, WARN, Finding, order,
                                     render_recovery, severity_of)
from sage.diagnostics import render as render_diagnostic
from sage.i18n import language_of, tr
from sage import diagnostic_collectors as collectors

SCHEMA_VERSION = 1

# 승인 설계는 "불가피한 child process 에 5초 timeout" 을 요구했다. 실제 구현에는 **child
# process 자체가 없다** — root 탐색도 profile·manifest 판독도 전부 이 프로세스 안의
# 파일시스템 읽기다. 그래서 timeout 상수를 두지 않는다. 쓰이지 않는 상수는 읽는 사람에게
# "어딘가 상한이 걸려 있다" 는 잘못된 안심을 준다.
#
# 대신 그 사실을 검사로 고정한다(`test_status_spawns_no_child_process`). 나중에 누가 child
# process 를 들이면 그 테스트가 실패하고, 그때 timeout 을 함께 들이게 된다.
#
# 1~2초는 정상 로컬 저장소의 성능 목표이지 전체 wall time 보장이 아니다 — 파일시스템이
# 멈추면 어떤 상한도 그걸 넘지 못한다.


def register(sub, context):
    p = sub.add_parser("status", help=tr(context, "cli.status.status"))
    p.add_argument("--json", action="store_true", help=tr(context, "cli.status.json"))
    p.add_argument("--root", default=None)
    p.set_defaults(func=run)


def resolve_root(args):
    explicit = getattr(args, "root", None)
    if explicit:
        return os.path.abspath(explicit)
    from sage import _resources
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    for path in (os.path.join(hooks, "runtime"), hooks):
        if path not in sys.path:
            sys.path.insert(0, path)
    try:
        import cycle_state
        found = cycle_state.find_project_root(os.getcwd())
    except Exception:
        found = None
    # 못 찾았으면 `None` 이다. cwd 로 대체하면 SAGE 와 무관한 디렉터리를 프로젝트로 삼아
    # "설치되지 않았다" 같은 사실을 그 디렉터리의 상태인 것처럼 보고한다 — root 미확정은
    # 판정이 아니라 도구 오류(FR-C09 exit 2)이고, 그 구분이 사라진다.
    return found


def _profile(root):
    from sage.commands._common import _load_profile_yaml
    loaded = _load_profile_yaml(os.path.join(root, "sage", "project-profile.yaml"))
    return loaded if isinstance(loaded, dict) else {}


# 한 영역이 무너져도 나머지 영역의 결과는 살린다. 전체를 감싼 그물 하나만 있으면 예외
# 하나가 이미 수집한 사실·code·복구를 전부 지우고 예외 class 이름만 남긴다 — 사용자는
# 무엇이 왜 막혔는지 알 수 없고, 그게 이 명령이 없애려던 상태다.
_AREA_DEFAULTS = {
    "project": {"installed": False},
    "version": {"required": None, "runtime": None, "installed": None, "generated": None},
    "runtime_api": {"current": None, "required": None, "compatible": None},
    "profile": {},
    "host": {"active": None, "configured": ()},
    "cycle": {"stem": None, "mode": None, "risk": None},
    "gate": {"required_phases": None, "present": (), "missing": (),
             "fast_cycle_error": None},
}


def _area(name, call, facts, findings):
    try:
        area_facts, area_findings = call()
    except Exception as exc:
        facts[name] = dict(_AREA_DEFAULTS[name])
        findings.append(Finding("status.area_unavailable",
                                evidence={"area": name, "error": type(exc).__name__},
                                arguments={"area": name, "error": type(exc).__name__}))
        return facts[name]
    facts[name] = area_facts
    findings.extend(area_findings)
    return area_facts


def collect(root):
    """(facts, findings). 어떤 collector 도 파일을 쓰지 않는다."""
    manifest, manifest_error = collectors.read_manifest(root)
    profile = _profile(root)

    facts, findings = {}, []
    _area("project", lambda: collectors.collect_project(root, manifest, manifest_error),
          facts, findings)
    _area("version", lambda: collectors.collect_version(profile, manifest, __version__),
          facts, findings)
    _area("runtime_api", lambda: collectors.collect_runtime_api(manifest), facts, findings)
    _area("profile", lambda: collectors.collect_profile(root), facts, findings)
    _area("host", lambda: collectors.collect_host(profile, manifest), facts, findings)
    cycle = _area("cycle", lambda: collectors.collect_cycle(root), facts, findings)
    # gate 는 cycle 의 stem·risk 를 받아야 무엇을 요구하는지 알 수 있으므로 뒤에 선다.
    _area("gate", lambda: collectors.collect_gate(root, profile, cycle.get("risk"),
                                                  cycle.get("stem")),
          facts, findings)
    return facts, tuple(order(findings))


def aggregate(findings):
    """(status, exit_code). 부재를 통과로 읽지 않는다."""
    if any(f.code in TOOL_FAILURE for f in findings):
        # 도구가 자기 일을 못 한 것이지 프로젝트 정책이 차단한 것이 아니다. 둘을 같은
        # 토큰으로 내면 사용자는 정책을 고치러 가고, 고칠 것이 없어 되돌아온다.
        #
        # 목록을 여기서 손으로 세지 않는다. `status.area_unavailable` 하나만 특례로 적어
        # 뒀을 때, 나중에 추가한 도구 실패 code 들이 조용히 정책 차단(BLOCKED/rc 1)과
        # 무경고(ATTENTION/rc 0)로 흘러갔다.
        return "ERROR", 2
    severities = {severity_of(f.code) for f in findings}
    if BLOCK in severities:
        return "BLOCKED", 1
    if WARN in severities:
        return "ATTENTION", 0
    return "READY", 0


def _print_text(status, facts, findings, language):
    say = lambda key, **kw: tr(language, key, **kw)                     # noqa: E731
    # `SAGE status` 와 상태 토큰은 번역하지 않는다 — 화면에서 검색하고 로그에서 수집하는
    # 조각이라 언어를 타면 안 된다. 설명만 표시 언어를 따른다.
    print(f"SAGE status: {status}")
    host = facts["host"]
    print(say("cli.status.line_host", active=host["active"] or "-",
              configured=", ".join(host["configured"]) or "-"))
    cycle = facts["cycle"]
    print(say("cli.status.line_cycle", stem=cycle.get("stem") or "-",
              mode=cycle.get("mode") or "-", risk=cycle.get("risk") or "-"))
    gate = facts["gate"]
    required = gate.get("required_phases")
    print(say("cli.status.line_gate",
              required="-" if required is None else (", ".join(required) or "-"),
              missing=", ".join(gate.get("missing") or ()) or "-"))
    version = facts["version"]
    print(say("cli.status.line_version", required=version["required"],
              runtime=version["runtime"], installed=version["installed"],
              generated=version["generated"]))
    api = facts["runtime_api"]
    print(say("cli.status.line_runtime_api", current=api["current"],
              required=api["required"] if api["required"] is not None else "-"))
    for finding in findings:
        print()
        print(f"[{finding.code}] "
              + render_diagnostic(finding.diagnostic(), lambda k, **kw: tr(language, k, **kw),
                                  "cli"))
        if severity_of(finding.code) != BLOCK:
            # INFO/WARN 에 강제 Next 를 붙이지 않는다. 모든 줄에 붙기 시작하면 `Next:` 가
            # "지금 해야 할 일" 이라는 뜻을 잃는다.
            continue
        for line in render_recovery(finding.code, lambda k, **kw: tr(language, k, **kw), "cli",
                                    host=facts["host"]["active"] or "<host>"):
            print(line)
    if not findings:
        print()
        print(say("cli.status.all_clear"))


def run(args):
    language = language_of(args)
    root = resolve_root(args)
    if root is None or not os.path.isdir(root):
        print(tr(language, "cli.status.root_unresolved"), file=sys.stderr)
        return 2
    try:
        facts, findings = collect(root)
    except Exception as exc:
        # collector 가 예외를 올리면 안 되지만, 올라오더라도 status 가 통째로 죽지는 않는다.
        # 죽으면 사용자는 아무 다음 행동도 받지 못한다.
        print(tr(language, "cli.status.collect_failed", error=type(exc).__name__),
              file=sys.stderr)
        return 2
    status, exit_code = aggregate(findings)

    if args.json:
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "exit_code": exit_code,
            **facts,
            "diagnostics": [f.to_json() for f in findings],
        }, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(status, facts, findings, language)
    return exit_code
