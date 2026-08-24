"""`sage explain --path <path>` — 이 경로가 왜 그런 요구를 받는가.

## 이 명령이 약속하지 않는 것

**실제 write 가 허용된다고 말하지 않는다.** 최종 결과에 `ALLOW` 가 없는 것은 문구 선택이 아니라
구조다 — 출력 계약에 `verdict` 필드 자체를 두지 않는다. 두는 순간 그 자리에 `ALLOW` 가 들어갈 수
있고, 한 번 들어가면 사용자는 그것을 보증으로 읽는다.

실제 게이트 판정은 경로 외에 세 가지를 더 본다. 앞으로 쓸 **내용**의 키워드, 현재 세션에서
포착한 **risk 선언**, host 가 한 번에 넘기는 **다중 변경 목록**. `--path` 하나로는 셋 다 복원할
수 없다. 그래서 그 셋은 판정하지 않고 `dynamic_checks` 로 이름을 밝힌다.

## 왜 기존 파일 내용을 읽지 않는가

읽을 수는 있다. 읽으면 안 되는 이유는 그게 **사용자가 쓰려는 내용이 아니기** 때문이다. 현재
내용으로 계산한 위험도는 정확해 보이지만 실제 write 와 다르고, 다르다는 사실이 화면에 드러나지
않는다. 존재하지 않는 경로도 설명할 수 있어야 한다는 요구와 같은 뿌리다.
"""
import json
import os
import sys

from sage import _resources
from sage.diagnostic_contract import Finding, order, render_recovery, severity_of, BLOCK
from sage.i18n import language_of, tr
from sage.diagnostics import render as render_diagnostic

# `--path` 만으로는 복원할 수 없는 입력. 목록이 늘면 여기서 함께 늘린다.
DYNAMIC_CHECKS = ("content_keywords", "session_declared_risk", "multi_file_maximum")


def register(sub, context):
    p = sub.add_parser("explain", help=tr(context, "cli.explain.explain"))
    p.add_argument("--path", required=True, help=tr(context, "cli.explain.path"))
    p.add_argument("--json", action="store_true", help=tr(context, "cli.explain.json"))
    p.add_argument("--root", default=None)
    p.set_defaults(func=run)


def _load(module):
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    for path in (os.path.join(hooks, "runtime"), hooks):
        if path not in sys.path:
            sys.path.insert(0, path)
    return __import__(module)


class PathRefused(Exception):
    """경로를 해석할 수 없거나 root 밖이다. 이 경우 그 경로를 **읽지 않는다**."""

    def __init__(self, code, **evidence):
        super().__init__(code)
        self.code = code
        self.evidence = evidence


def contain(root, raw):
    """project root 안의 상대 POSIX 경로로 정규화한다.

    `..` 이탈과 경로 중간·leaf symlink 는 거부한다. symlink 를 따라가면 root 안의 이름으로
    root 밖 파일을 설명하게 되고, 그건 게이트가 막는 바로 그 형태다.

    거부할 때 그 경로를 stat 하거나 열지 않는다 — 읽지 않는 것이 계약이다.
    """
    if not raw or not str(raw).strip():
        raise PathRefused("explain.path_empty")
    candidate = os.path.join(root, raw) if not os.path.isabs(raw) else raw
    normalized = os.path.normpath(candidate)
    root_normalized = os.path.normpath(root)
    if normalized != root_normalized and not normalized.startswith(root_normalized + os.sep):
        raise PathRefused("explain.path_outside_root")

    # 존재하는 조상 구간만 검사한다. 아직 없는 경로도 설명해야 하므로 부재는 거부 사유가 아니다.
    relative = os.path.relpath(normalized, root_normalized)
    walked = root_normalized
    for part in relative.split(os.sep):
        if part in ("", "."):
            continue
        walked = os.path.join(walked, part)
        if os.path.islink(walked):
            raise PathRefused("explain.path_symlink",
                              segment=os.path.relpath(walked, root_normalized))
    return relative.replace(os.sep, "/")


def component_of(relative, profile):
    """이 경로를 소유한 component id. profile 이 선언하지 않았으면 None."""
    path_risk = _load("path_risk")
    for component in (profile.get("components") or []):
        if not isinstance(component, dict):
            continue
        for glob in component.get("paths") or []:
            if path_risk.imatch(relative, glob):
                return component.get("id")
    return None


def required_phases(profile, risk):
    """이 위험도가 구현 전에 요구하는 phase id 목록. pdca 비활성이면 None."""
    pdca = profile.get("pdca") or {}
    if not pdca.get("enabled") or not pdca.get("phases"):
        return None
    return list((pdca.get("pre_implementation_required") or {}).get(risk) or [])


def phase_readiness(root, profile, stem, required):
    """요구 phase 중 이 stem 으로 결속되는 문서가 있는 것과 없는 것.

    문서 선택은 `cycle_binding.select_document` 를 그대로 쓴다 — 게이트가 결속을 판정하는 함수와
    같은 것이어야, 여기서 "있다" 고 한 문서를 게이트가 "다른 사이클" 로 거부하는 일이 없다.
    """
    if not required:
        return [], []
    if not stem:
        return [], list(required)
    import glob as globlib
    cycle_binding = _load("cycle_binding")
    phases = {str(entry.get("id")): entry for entry in (profile.get("pdca") or {}).get("phases", [])
              if isinstance(entry, dict)}
    present, missing = [], []
    for pid in required:
        pattern = (phases.get(pid) or {}).get("glob")
        candidates = []
        for path in (globlib.glob(os.path.join(root, pattern), recursive=True)
                     if pattern else []):
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding="utf-8") as handle:
                    content = handle.read()
            except OSError:
                continue
            # phase 문서의 내용을 읽는 것은 대상 경로의 내용을 읽는 것과 다르다. 결속 판정이
            # 문서 안의 Cycle-Stem 선언을 요구하고, 게이트도 같은 것을 읽는다.
            candidates.append({"path": os.path.relpath(path, root).replace(os.sep, "/"),
                               "content": content})
        document, error = cycle_binding.select_document(candidates, stem)
        (missing if (error or not document) else present).append(pid)
    return present, missing


def collect(root, raw_path, language=None):
    """(facts, findings). 파일을 쓰지 않고 대상 경로의 내용을 읽지 않는다."""
    from sage.commands._common import _load_profile_yaml

    relative = contain(root, raw_path)
    profile = _load_profile_yaml(os.path.join(root, "sage", "project-profile.yaml")) or {}
    if not isinstance(profile, dict):
        profile = {}

    path_risk = _load("path_risk")
    floor = path_risk.path_risk_floor(relative, profile)

    guard = _load("generated_artifact_write_guard_core")
    guarded = bool(guard.is_guarded(relative))

    cycle_state = _load("cycle_state")
    try:
        record = cycle_state.read_declaration_record(root)
        stem, cycle_error = (record.stem or None), record.error
    except Exception as exc:
        stem, cycle_error = None, type(exc).__name__

    required = required_phases(profile, floor.risk)
    present, missing = phase_readiness(root, profile, stem, required or [])

    facts = {
        "path": relative,
        "path_risk_floor": floor.risk,
        "matched_rule": (None if floor.matched_rule is None else
                         {"field": floor.matched_rule[0], "index": floor.matched_rule[1],
                          "glob": floor.matched_rule[2]}),
        "component": component_of(relative, profile),
        "cycle": {"stem": stem, "source": None if stem is None else ".sage/cycle.json"},
        "generated_asset": guarded,
        "required_phases": required,
        "phase_readiness": {"present": present, "missing": missing},
        "dynamic_checks": list(DYNAMIC_CHECKS),
    }

    findings = []
    if guarded:
        findings.append(Finding("guard.generated_asset", evidence={"path": relative},
                                arguments={"path": relative}))
    if cycle_error:
        findings.append(Finding("cycle.declaration_damaged",
                                evidence={"error": str(cycle_error)}))
    elif required and not stem:
        findings.append(Finding("cycle.binding_missing", evidence={"risk": floor.risk}))
    if missing:
        findings.append(Finding("gate.phase_incomplete",
                                evidence={"missing": list(missing), "risk": floor.risk},
                                arguments={"miss": ", ".join(missing)}))
    return facts, tuple(order(findings))


def _print_text(facts, findings, language):
    say = lambda key, **kw: tr(language, key, **kw)                     # noqa: E731
    print(say("cli.explain.line_path", path=facts["path"]))
    print(say("cli.explain.line_risk_floor", risk=facts["path_risk_floor"]))
    rule = facts["matched_rule"]
    if rule:
        print(say("cli.explain.line_matched_rule", field=rule["field"],
                  index=rule["index"], glob=rule["glob"]))
    if facts["component"]:
        print(say("cli.explain.line_component", component=facts["component"]))
    stem = facts["cycle"]["stem"]
    print(say("cli.explain.line_cycle", stem=stem, source=facts["cycle"]["source"])
          if stem else say("cli.explain.line_cycle_absent"))
    if facts["required_phases"] is None:
        print(say("cli.explain.line_pdca_disabled"))
    elif facts["required_phases"]:
        print(say("cli.explain.line_required_phases",
                  phases=", ".join(facts["required_phases"])))
        missing = facts["phase_readiness"]["missing"]
        print(say("cli.explain.line_readiness_blocked", missing=", ".join(missing))
              if missing else say("cli.explain.line_readiness_ok"))
    print(say("cli.explain.line_dynamic", checks=", ".join(facts["dynamic_checks"])))
    print()
    # 이 한 줄이 명령 전체의 계약이다. 위 내용은 경로와 현재 저장소 상태만 본 것이고,
    # 실제 write 는 내용·세션 선언·다중 변경에 따라 더 엄격해질 수 있다.
    print(say("cli.explain.not_a_verdict"))
    for finding in findings:
        print()
        print(f"[{finding.code}] "
              + render_diagnostic(finding.diagnostic(), lambda k, **kw: tr(language, k, **kw),
                                  "cli"))
        for line in render_recovery(finding.code, lambda k, **kw: tr(language, k, **kw), "cli"):
            print(line)


def run(args):
    language = language_of(args)
    from sage.commands.status import resolve_root

    root = resolve_root(args)
    if root is None:
        print(tr(language, "cli.status.root_unresolved"), file=sys.stderr)
        return 2
    try:
        facts, findings = collect(root, args.path, language)
    except PathRefused as refusal:
        print(f"[{refusal.code}] "
              + tr(language, f"cli.{refusal.code}", **refusal.evidence), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"schema_version": 1, **facts,
                          "diagnostics": [f.to_json() for f in findings]},
                         ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(facts, findings, language)
    # `explain` 은 설명이지 판정이 아니다. BLOCK 진단이 있어도 exit 1 로 끝내지 않는다 —
    # 그렇게 하면 "이 경로는 못 쓴다" 는 판정으로 읽히고, 그게 바로 이 명령이 하지 않는 말이다.
    return 0
