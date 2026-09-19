"""sage review / sage cross-check — Phase 05 리뷰 오케스트레이션 (7차 배치2).

두 명령은 sage-team 이 Phase 05 에서 profile.options.cross_model 에 따라 택일 호출한다:
- cross_model=false → `sage review`      : active host의 새 headless process에서 same-runtime 리뷰.
- cross_model=true  → `sage cross-check`  : 반대 런타임 CLI 를 **직접 호출**해 독립 리뷰 획득(cross-model).

둘 다 `REVIEWER_ACTUAL: <mode>` 줄을 출력하고 마지막 줄은 `REVIEWER_STATUS` 다 — sage-team 이 ACTUAL 을 캡처해
`sage review-loop close --reviewer-actual <mode>` 로 넘기면 의도(open 의 --reviewer-requested)와 대조해
degraded 가 판정된다(배치3). cross-model 요청이 peer에 도달하지 못하면 same-runtime으로 완화하지 않고
`REVIEWER_STATUS: BLOCKED`와 nonzero exit를 반환한다.

gstack 의존 없음: claude-host→`codex exec`, codex-host→`claude -p` 를 SAGE 가 직접 호출(gstack wrapper
기법만 차용 — read-only 샌드박스·stdin 차단·timeout·--json 최종 메시지 파싱).
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

from sage import peer_process as _peer
from sage.commands import doctor as _doctor
from sage.diagnostics import Diagnostic
from sage.i18n import language_of, render_issue, tr

_DEFAULT_TIMEOUT = 540   # codex/claude 비대화 1턴 상한(초). gstack /codex 의 330~600 대역과 정합.


def register(sub, context):
    pr = sub.add_parser("review", help=tr(context, "cli.review.review"))
    pr.add_argument("--packet-file",
                    help=tr(context, "cli.review.packet_file"))
    pr.add_argument("--host", choices=["claude", "codex"],
                    help=tr(context, "cli.review.host"))
    pr.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT,
                    help=tr(context, "cli.review.timeout", default=_DEFAULT_TIMEOUT))
    pr.add_argument("--root", default=None)
    # 마이그레이션 shim(codex 배치2 R3 P1): `sage review` 는 자산분류→Phase05 리뷰로 의미가 바뀌었다.
    # 구 자산분류 플래그를 hidden 으로 받아, 쓰이면 친절히 `sage asset-check` 로 안내(암호적 argparse 실패 방지).
    # 동작은 넘기지 않는다(유저 결정: review=same-runtime). SAGE 가 PyPI 배포라 다운스트림 CI 충격 완화용.
    pr.add_argument("--kind", help=argparse.SUPPRESS)
    pr.add_argument("--batch", action="store_true", help=argparse.SUPPRESS)
    pr.add_argument("--gate", action="store_true", help=argparse.SUPPRESS)
    pr.set_defaults(func=run_review)

    pc = sub.add_parser("cross-check", help=tr(context, "cli.review.cross_check"))
    pc.add_argument("--packet-file", required=True,
                    help=tr(context, "cli.review.packet_file_2"))
    pc.add_argument("--host", choices=["claude", "codex"],
                    help=tr(context, "cli.review.host_2"))
    pc.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT, help=tr(context, "cli.review.timeout_peer", default=_DEFAULT_TIMEOUT))
    pc.add_argument("--on-peer-failure", choices=["block", "same-runtime"], default="block",
                    help=tr(context, "cli.review.on_peer_failure"))
    pc.add_argument("--strict", action="store_true",
                    help=tr(context, "cli.review.strict"))
    pc.add_argument("--root", default=None)
    pc.set_defaults(func=run_cross_check)


# ---- 순수 헬퍼(테스트 직격) ----

# peer CLI 가 실제로 받는 reasoning effort 값(각 CLI 로 실증). 두 CLI 모두 어휘가 다르고,
# **codex 는 모르는 값을 조용히 무시**한다(오타 → 리뷰 강도가 말없이 기본값으로 떨어짐).
# 그래서 SAGE 가 fail-closed 로 먼저 거른다.
PEER_EFFORTS = {
    "codex":  ("minimal", "low", "medium", "high", "xhigh"),
    "claude": ("low", "medium", "high", "xhigh", "max"),
}
# cross_model.effort 미설정 시 SAGE 가 쓰는 값. 두 peer 어휘의 교집합에 있어 host 를 안 가린다.
# peer CLI 기본값에 맡기지 않는 이유: Phase 05 는 적대적 리뷰라 강도가 조용히 낮아지면 안 된다.
DEFAULT_EFFORT = "high"

CROSS_MODEL_KEYS = frozenset({"policy", "peer", "on_unavailable", "effort", "reviewer"})
# peer는 반대 런타임으로 고정하고, unavailable은 성공 완화 없이 fail-closed로 차단한다.
CROSS_MODEL_FIXED = {"peer": "opposite_runtime", "on_unavailable": "block"}


def intended_peer(profile):
    """검증 대상 peer = host 의 반대 런타임. peer CLI 도달 가능성과 무관하다 —
    peer 가 마침 미가용이면 잘못된 설정이 검증 없이 통과해버린다."""
    from sage.runtime_hosts import opposite_host
    return opposite_host(profile)


def possible_peers(profile):
    """정적으로 가능한 peer 후보 — active_host 가 pin 이면 1개, auto 면 설치된 host 전부.

    `auto` 는 실행 시점에야 peer 가 정해지므로 어느 쪽이 될지 미리 알 수 없다. 설정값(effort 등)이
    peer 어휘에 종속되면 후보 전부에서 유효해야 안전하다.
    """
    from sage.runtime_hosts import (HOSTS, declared_active_host, declared_installed_hosts,
                                    opposite_host)
    if declared_active_host(profile) is not None:
        return [opposite_host(profile)]
    installed = declared_installed_hosts(profile)
    return list(installed) if installed else list(HOSTS)


def resolve_effort(profile):
    """(effort, configured) — configured 가 None 이면 DEFAULT_EFFORT 를 쓴 것.
    `or` 로 미설정 판정하면 `effort: false` / `effort: 0` 이 조용히 기본값으로 흡수돼 fail-closed 가 깨진다."""
    cm = profile.get("cross_model") if isinstance(profile, dict) else None
    configured = cm.get("effort") if isinstance(cm, dict) else None
    if configured is None or configured == "":
        configured = None
    return (DEFAULT_EFFORT if configured is None else configured), configured


def cross_model_issues(profile):
    """profile.cross_model 검증 → [(severity, message)]. `sage validate`·`sage cross-check` **단일 소스**.

    두 곳이 서로 다른 규칙을 쓰면, cross-check 가 `effrot: xhigh` 나 `on_unavailable: clean_context_same_runtime` 을
    조용히 무시한 채 기본값으로 돌면서 설정대로 돈 것처럼 보인다(codex 7R).
    """
    cm = profile.get("cross_model") if isinstance(profile, dict) else None
    if cm in (None, ""):
        return []
    if not isinstance(cm, dict):
        # jsonschema 는 선택 의존성 → 구조검증이 skip 되는 환경에서 여기가 유일한 관문이다.
        return [("FAIL", Diagnostic("review.cross_model_not_mapping",
                                    received=type(cm).__name__))]
    issues = []
    unknown = [k for k in cm if k not in CROSS_MODEL_KEYS]
    if unknown:
        # `effrot: max` 가 조용히 무시되면 기본값으로 돌면서 설정대로 돈 것처럼 보인다.
        issues.append(("FAIL", Diagnostic(
            "review.cross_model_unknown_keys",
            keys=", ".join(sorted(str(k) for k in unknown)),
            allowed=", ".join(sorted(CROSS_MODEL_KEYS)))))
    policy = cm.get("policy")
    if policy not in (None, "", "required", "recommended", "off"):
        issues.append(("FAIL", Diagnostic("review.cross_model_policy_invalid",
                                          policy=repr(policy))))
    for key, only in CROSS_MODEL_FIXED.items():
        val = cm.get(key)
        if val not in (None, "") and val != only:
            # `key` 는 render 의 translate(key, **arguments) 와 충돌하는 예약 이름이다 — `field` 로 쓴다.
            issues.append(("FAIL", Diagnostic("review.cross_model_fixed_value",
                                              field=key, value=repr(val), only=only)))
    effort, configured = resolve_effort(profile)
    if configured is not None:
        # 정적으로 peer 를 하나로 좁힐 수 없으면(active_host: auto) 가능한 peer 전부에서 유효해야
        # 한다. 한쪽만 보고 통과시키면 실제 peer 가 반대로 정해졌을 때 강도가 조용히 떨어진다.
        for peer in possible_peers(profile):
            issue = effort_issue(peer, effort)
            if issue:
                issues.append(("FAIL", issue))
                break
    from sage.model_routing import reviewer_issues
    issues.extend(reviewer_issues(profile))
    return issues


def effort_issue(peer, effort):
    """cross_model.effort 검증 → Diagnostic(없으면 None). validate/doctor/cross-check 공용."""
    if effort in (None, ""):
        return None
    if peer not in PEER_EFFORTS:
        return Diagnostic("review.effort_unknown_peer", peer=repr(peer))
    if effort not in PEER_EFFORTS[peer]:
        return Diagnostic("review.effort_unknown_value", effort=repr(effort), peer=peer,
                          allowed=", ".join(PEER_EFFORTS[peer]))
    return None


def _peer_command(peer, effort=None, model=None):
    """통제 플래그 없는 peer argv(프롬프트 제외 — stdin). 실제 실행 argv 는 `peer_process.run_peer` 가
    버전에 따라 통제 플래그를 붙여 만든다. model 은 호출자가 넘길 때만 붙는다."""
    return _peer.peer_command(peer, effort, model)


def _parse_codex_jsonl(text):
    return _peer.parse_codex_jsonl(text)


def _parse_claude_json(text):
    return _peer.parse_claude_json(text)


def _parse_peer_output(peer, text):
    return _parse_codex_jsonl(text) if peer == "codex" else _parse_claude_json(text)


# ---- subprocess 경계(테스트는 이 함수를 monkeypatch) ----

def _invoke_peer(peer, prompt, timeout, effort=None, model=None):
    """peer 런타임을 비대화 실행 → (ok, review_text, err). 구 계약 — 테스트·어댑터가 갈아끼우는 자리다.
    실제 경로는 `_call_peer` 가 사용량·감사까지 담긴 PeerRun 으로 받는다."""
    run = _peer.run_peer(peer, prompt, timeout, effort, model, root=os.getcwd(),
                         env=_peer_env(peer))
    return run.ok, run.review, run.error


_INVOKE_PEER_DEFAULT = _invoke_peer


def _peer_env(peer):
    # peer 환경에서 부모 host 표식을 지운다. 자식은 부모 env 를 상속하므로, 그대로 두면 peer
    # 안에서 도는 SAGE hook 이 `CLAUDECODE` 같은 상속된 값을 보고 자기를 부모 host 로 오인한다
    # (실측: claude → codex exec 시 두 계열 표식이 동시에 관측됨).
    from sage.runtime_hosts import peer_env
    return peer_env(peer)


def _call_peer(peer, prompt, timeout, root, effort=None, model=None, legacy_effort=True):
    """peer 1회 실행 → PeerRun. `_invoke_peer` 가 갈아끼워져 있으면 그 구 계약 호출 모양을 그대로
    지킨다(사용량·감사는 unknown). `legacy_effort=False` 는 same-runtime 의 호출 모양이다."""
    if _invoke_peer is not _INVOKE_PEER_DEFAULT:
        if legacy_effort:
            ok, review, err = (_invoke_peer(peer, prompt, timeout, effort, model) if model
                               else _invoke_peer(peer, prompt, timeout, effort))
        else:
            ok, review, err = (_invoke_peer(peer, prompt, timeout, model=model) if model
                               else _invoke_peer(peer, prompt, timeout))
        return _peer.PeerRun.from_legacy(peer, ok, review, err)
    return _peer.run_peer(peer, prompt, timeout, effort, model, root=root, env=_peer_env(peer))


def _load_profile_caps(root):
    """profile + peer CLI 가용성 caps → (profile, caps, rr)."""
    profile, caps, rr, _ = _load_profile_layers_caps(root)
    return profile, caps, rr


def _load_profile_layers_caps(root, explicit_host=None):
    """Effective profile and layer diagnostics for Phase 05 routing."""
    path = os.path.join(root, "sage", "project-profile.yaml") if root else None
    profile = {}
    layers = None
    if path and os.path.exists(path):
        from sage.profile_layers import load_profile_layers
        layers = load_profile_layers(path)
        profile = layers.effective
    caps_prof = profile.get("capabilities", {}) or {}
    caps = {"codex": bool(shutil.which("codex")) or bool(caps_prof.get("codex")),
            "claude": bool(shutil.which("claude")) or bool(caps_prof.get("claude"))}
    from sage.runtime_hosts import running_host
    rr = _doctor.reviewer_resolution(profile, caps, running_host(profile, explicit_host))
    return profile, caps, rr, layers


def host_detection_notes(profile, detected):
    """실행 관측과 프로필 선언이 어긋난 지점 — 차단하지 않고 알리기만 한다.

    고치라고 요구하지 않는 이유가 있다. `active_host` 는 shared profile 에만 둘 수 있는데(local 이
    이 키를 덮지 못한다) 그 파일은 커밋되고 게이트 정책 소스라 L2 다. 불일치를 사용자에게 떠넘기면
    host 를 옮길 때마다 PDCA 게이트를 통과해 공유 파일을 고치라는 뜻이 된다.
    """
    from sage.runtime_hosts import configured_hosts, declared_active_host
    if detected is None:
        return []
    notes = []
    declared = declared_active_host(profile)
    if declared is not None and declared != detected:
        notes.append(Diagnostic("review.host_declared_mismatch",
                                declared=declared, detected=detected))
    installed = configured_hosts(profile)
    if detected not in installed:
        notes.append(Diagnostic("review.host_not_in_installed",
                                detected=detected, installed=installed))
    return notes


def _print_host_notes(command, profile, detected, language=None):
    # stdout 은 `REVIEWER_ACTUAL:` 기계 판독 계약이 쓰는 채널이라 섞으면 sage-team 캡처가 깨진다.
    for note in host_detection_notes(profile, detected):
        print(f"[{command}] ⚠️  {render_issue(language, note)}", file=sys.stderr)


def _model_for_peer(profile, peer, model):
    """(peer 에게 넘길 model, 경고문) — 다른 peer 용으로 고른 모델은 넘기지 않는다.

    model id 는 런타임 종속이다(`gpt-5.6-terra` 는 codex, `opus` 는 claude). 프로필이 어느 peer 를
    염두에 두고 고른 값인지는 `cross_model.reviewer.host` 가 말해준다. 실제 peer 가 그와 다르면
    그 모델은 이 peer 에서 의미가 없거나 존재하지 않으므로, 넘기지 않고 peer CLI 기본값에 맡긴다.
    """
    if not model:
        return None, None
    cross = profile.get("cross_model") if isinstance(profile, dict) else None
    reviewer = cross.get("reviewer") if isinstance(cross, dict) else None
    chosen_for = reviewer.get("host") if isinstance(reviewer, dict) else None
    if chosen_for in ("claude", "codex") and chosen_for != peer:
        return None, Diagnostic("review.model_for_other_peer",
                                model=repr(model), chosen_for=chosen_for, peer=peer)
    return model, None


def _blocking_layer_issues(layers):
    return ([message for severity, message in layers.issues if severity == "FAIL"]
            if layers is not None else [])


def _find_root(explicit):
    if explicit:
        return os.path.abspath(explicit)
    cur = os.getcwd()
    while True:
        if os.path.exists(os.path.join(cur, "sage", "project-profile.yaml")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.getcwd()
        cur = parent


def _read_packet(path, command, language=None):
    try:
        prompt = Path(path).read_text(encoding="utf-8")
    except Exception as exc:
        print(tr(language, 'cli.review.msg01', command=command, exc=exc), file=sys.stderr)
        return None
    if not prompt.strip():
        print(tr(language, 'cli.review.msg02', command=command), file=sys.stderr)
        return None
    return prompt


def _profile_active_host(profile):
    from sage.runtime_hosts import active_host
    runtime = profile.get("runtime") if isinstance(profile, dict) else None
    if not isinstance(runtime, dict):
        return active_host(profile)
    active = runtime.get("active_host")
    legacy = runtime.get("host")
    return active if active in ("claude", "codex") else (
        legacy if legacy in ("claude", "codex") else active_host(profile)
    )


def _same_runtime_model(profile):
    team = profile.get("team") if isinstance(profile, dict) else None
    core = team.get("core") if isinstance(team, dict) else None
    reviewer = core.get("reviewer") if isinstance(core, dict) else None
    runtime = reviewer.get("runtime") if isinstance(reviewer, dict) else None
    model = runtime.get("model") if isinstance(runtime, dict) else None
    return model if isinstance(model, str) and model.strip() else None


def _same_runtime_authorized(profile, layers):
    """True only when policy or an explicit local choice intentionally disables cross-model."""
    from sage.profile_layers import cross_model_policy
    policy = cross_model_policy(profile)
    if policy == "off":
        return True
    if policy == "recommended":
        local = layers.local if layers is not None else None
        cross_model = local.get("cross_model") if isinstance(local, dict) else None
        return isinstance(cross_model, dict) and cross_model.get("enabled") is False
    if policy == "required":
        return False
    options = profile.get("options") if isinstance(profile, dict) else None
    return not bool(options.get("cross_model")) if isinstance(options, dict) else True


def _review_process(host):
    return "codex exec" if host == "codex" else "claude -p"


def _blocked_review(command, message, status_code=3):
    print(f"[{command}] BLOCKED: {message}", file=sys.stderr)
    print("REVIEWER_STATUS: BLOCKED")
    return status_code


def _audit_line(run):
    if run.controls == "unknown":
        return "unknown"
    if run.controls != "full":
        # 통제 없이 돈 실행은 감사할 기준도 없다. `ok` 로 찍으면 검사한 적 없는 것이 통과로 읽힌다.
        return "not_audited"
    if run.violations:
        return "violation " + ",".join(run.violations)
    # 통제로 막을 수 없는 행동(codex 의 하위 에이전트·테스트 실행)은 강등하지 않고 경고로 드러낸다.
    return "warn " + ",".join(run.warnings) if run.warnings else "ok"


def _print_run_telemetry(run):
    """peer 사용량·통제·감사. 실패한 실행도 토큰은 썼으므로 BLOCKED 경로에서도 찍는다."""
    print(f"REVIEWER_TOKENS: {run.tokens_line()}")
    print(f"REVIEWER_CONTROLS: {run.controls}")
    print(f"REVIEWER_AUDIT: {_audit_line(run)}")


def _print_partial(run):
    if run.partial:
        print(f"===== {run.peer.upper()} PARTIAL REVIEW (cut off: {run.reason}) =====")
        print(run.partial)
        print(f"===== END {run.peer.upper()} PARTIAL REVIEW =====")


def _blocked_peer(command, run, language, message=None):
    """peer 실패 → BLOCKED(부분 결과가 있으면 PARTIAL). 사유는 stdout 에도 기계 판독용으로 남긴다 —
    미설치·한도·제한 시간·파싱 실패가 전부 같은 BLOCKED 면 사람이 대응을 고를 수 없다."""
    print(f"[{command}] BLOCKED: {message or render_issue(language, run.error)}", file=sys.stderr)
    _print_partial(run)
    print(f"REVIEWER_BLOCK_REASON: {run.reason}")
    _print_run_telemetry(run)
    # PARTIAL 은 완료가 아니다 — 확인된 finding 을 REWORK 입력으로 살리되 리뷰 완료로 세지 않는다.
    print(f"REVIEWER_STATUS: {'PARTIAL' if run.partial else 'BLOCKED'}")
    return 3


def _run_same_runtime(profile, host, packet_file, timeout, command="sage review", language=None,
                      root=None, fallback_from=None, fallback_reason=None, failed_run=None):
    prompt = _read_packet(packet_file, command, language)
    if prompt is None:
        return _blocked_review(command, tr(language, "cli.review.blocked_packet_required"), 2)
    model = _same_runtime_model(profile)
    run = _call_peer(host, prompt, timeout, root or os.getcwd(), model=model, legacy_effort=False)
    if not run.ok:
        if failed_run is not None:
            # 폴백까지 실패했다. 이 라운드에서 가장 많이 쓴 것은 먼저 실패한 peer 라, 폴백 몫만 남기면
            # 예산 게이트가 최악의 라운드를 적게 센다. 원래 사유와 합산을 함께 남긴다.
            print(f"REVIEWER_PEER_TOKENS: {failed_run.tokens_line()}")
            print(f"REVIEWER_FALLBACK_FROM: {fallback_from}")
            print(f"REVIEWER_FALLBACK_REASON: {fallback_reason}")
            run = _peer.PeerRun(run.peer, error=run.error, reason=run.reason, partial=run.partial,
                                usage=failed_run.combined_with(run).usage, controls=run.controls,
                                violations=run.violations)
        return _blocked_peer(command, run, language)
    print(f"===== {host.upper()} SAME-RUNTIME REVIEW =====")
    print(run.review)
    print(f"===== END {host.upper()} REVIEW =====")
    print(f"REVIEWER_PROCESS: {_review_process(host)}")
    print(f"REVIEWER_HOST: {host}")
    print(f"REVIEWER_MODEL: {model or 'cli-default'}")
    if failed_run is not None:
        # 라운드가 쓴 토큰은 실패한 peer 와 폴백의 합이다. 폴백 몫만 적으면 제한 시간까지 쓴 peer 의
        # 소비가 예산 게이트에서 사라진다. 내역은 따로 남긴다.
        print(f"REVIEWER_PEER_TOKENS: {failed_run.tokens_line()}")
        print(f"REVIEWER_FALLBACK_TOKENS: {run.tokens_line()}")
        print(f"REVIEWER_TOKENS: {failed_run.combined_with(run).tokens_line()}")
        print(f"REVIEWER_CONTROLS: {run.controls}")
        print(f"REVIEWER_AUDIT: {_audit_line(run)}")
    else:
        _print_run_telemetry(run)
    degraded = bool(run.violations)
    if fallback_from:
        # 완료된 리뷰라 BLOCK_REASON 이 아니다 — 그 줄을 차단 신호로 읽는 소비자가 오판하지 않게.
        print(f"REVIEWER_FALLBACK_FROM: {fallback_from}")
        print(f"REVIEWER_FALLBACK_REASON: {fallback_reason}")
    # 통제가 불가능하게 만든 행동이 관측됐다 = 통제가 실패했다. 요청한 리뷰어 모드와 다르게 기록해
    # ci_authority 가 강등으로 잡게 한다.
    print(f"REVIEWER_ACTUAL: same_runtime{'_degraded' if degraded else ''}")
    print(f"REVIEWER_STATUS: {'COMPLETE_DEGRADED' if (degraded or fallback_from) else 'COMPLETE'}")
    return 0


def run_review(args):
    """Run a clean-context headless review on the explicitly active host."""
    # 구 `sage review`(자산분류) 플래그 감지 → 친절한 이름변경 안내(codex 배치2 R3 P1).
    if getattr(args, "kind", None) is not None or getattr(args, "batch", False) or getattr(args, "gate", False):
        print(tr(language_of(args), "cli.review.msg03"),
              file=sys.stderr)
        return 2
    root = _find_root(args.root)
    profile, _, rr, layers = _load_profile_layers_caps(root)
    layer_failures = _blocking_layer_issues(layers)
    if layer_failures:
        for message in layer_failures:
            print(f"[sage review] TOOL ERROR: "
                  f"{render_issue(language_of(args), message)}", file=sys.stderr)
        print("REVIEWER_STATUS: BLOCKED")
        return 2
    from sage.runtime_hosts import profile_issues as runtime_profile_issues
    runtime_failures = [message for severity, message in runtime_profile_issues(profile) if severity == "FAIL"]
    if runtime_failures:
        for message in runtime_failures:
            print(f"[sage review] TOOL ERROR: "
                  f"{render_issue(language_of(args), message)}", file=sys.stderr)
        print("REVIEWER_STATUS: BLOCKED")
        return 2
    cross_failures = [message for severity, message in cross_model_issues(profile) if severity == "FAIL"]
    if cross_failures:
        for message in cross_failures:
            print(f"[sage review] TOOL ERROR: "
                  f"{render_issue(language_of(args), message)}", file=sys.stderr)
        print("REVIEWER_STATUS: BLOCKED")
        return 2
    host = getattr(args, "host", None)
    if host not in ("claude", "codex"):
        return _blocked_review("sage review",
                               tr(language_of(args), "cli.review.blocked_host_required"), 2)
    from sage.runtime_hosts import detect_current_host
    detected = detect_current_host()
    _print_host_notes("sage review", profile, detected, language_of(args))
    # 실행 관측이 있으면 그게 정본이다 — 선언과 달라도 지금 도는 프로세스가 사실이다.
    expected, source = ((detected, tr(language_of(args), "cli.review.source_detected_host"))
                        if detected is not None
                        else (_profile_active_host(profile), "profile active_host"))
    if expected is not None and expected != host:
        return _blocked_review(
            "sage review", tr(language_of(args), "cli.review.blocked_host_mismatch",
                              host=host, source=source, expected=expected), 2
        )
    from sage.profile_layers import cross_model_policy
    policy = cross_model_policy(profile)
    if policy == "required":
        return _blocked_review("sage review",
                               tr(language_of(args), "cli.review.blocked_policy_required"))
    if rr["reviewer_mode"] == "opposite_runtime":
        return _blocked_review("sage review",
                               tr(language_of(args), "cli.review.blocked_use_cross_check"))
    if not _same_runtime_authorized(profile, layers):
        reason = rr.get("reviewer_degrade_reason") or "cross-model reviewer unavailable"
        return _blocked_review(
            "sage review", tr(language_of(args), "cli.review.blocked_no_local_opt_out",
                              reason=reason)
        )
    return _run_same_runtime(profile, host, args.packet_file, args.timeout,
                             language=language_of(args), root=root)


def run_cross_check(args):
    """Cross-model 경로. peer를 직접 호출하고, 미가용/실패 시 BLOCKED를 표면화한다."""
    root = _find_root(args.root)
    explicit = getattr(args, "host", None)
    profile, _, rr, layers = _load_profile_layers_caps(root, explicit)
    from sage.runtime_hosts import detect_current_host, running_host
    _print_host_notes("sage cross-check", profile, detect_current_host(), language_of(args))
    current = running_host(profile, explicit)
    if current is None:
        # 지금 도는 host 를 모르면 어느 쪽을 빼야 할지도 모른다 — 추측해서 고르면 실행 중인 host 를
        # 리뷰어로 뽑을 수 있고(중첩 실행에서 실제로 그렇게 된다) 그건 독립 리뷰가 아니다.
        return _blocked_review(
            "sage cross-check",
            tr(language_of(args), "cli.review.blocked_ambiguous_running_host"), 2)
    layer_failures = _blocking_layer_issues(layers)
    if layer_failures:
        for message in layer_failures:
            print(f"[sage cross-check] TOOL ERROR: "
                  f"{render_issue(language_of(args), message)}", file=sys.stderr)
        print("REVIEWER_STATUS: BLOCKED")
        return 2
    from sage.runtime_hosts import profile_issues as runtime_profile_issues
    runtime_failures = [message for severity, message in runtime_profile_issues(profile) if severity == "FAIL"]
    if runtime_failures:
        for message in runtime_failures:
            print(f"[sage cross-check] TOOL ERROR: "
                  f"{render_issue(language_of(args), message)}", file=sys.stderr)
        print("REVIEWER_STATUS: BLOCKED")
        return 2

    # cross_model 검증은 폴백 판정보다 **먼저** — peer 가 마침 미가용이면 잘못된 설정이 통과해버린다.
    # `sage validate` 와 같은 규칙(cross_model_issues)을 쓴다: 다르면 한쪽이 조용히 무시된다.
    fails = [m for sev, m in cross_model_issues(profile) if sev == "FAIL"]
    if fails:
        for m in fails:
            print(f"[sage cross-check] TOOL ERROR: "
                  f"{render_issue(language_of(args), m)}", file=sys.stderr)
        print("REVIEWER_STATUS: BLOCKED")
        return 2
    effort, configured = resolve_effort(profile)
    from sage.model_routing import reviewer_selection
    _, reviewer_model = reviewer_selection(profile, current)

    if rr["reviewer_mode"] != "opposite_runtime":
        from sage.profile_layers import cross_model_policy
        policy = cross_model_policy(profile)
        enabled = bool((profile.get("options") or {}).get("cross_model"))
        if not enabled and policy != "required":
            host = _profile_active_host(profile)
            if host is None:
                return _blocked_review(
                    "sage cross-check",
                    tr(language_of(args), "cli.review.blocked_same_runtime_no_active_host"), 2)
            print(tr(language_of(args), "cli.review.msg04", host=host),
                  file=sys.stderr)
            return _run_same_runtime(profile, host, args.packet_file, args.timeout,
                                     command="sage cross-check", language=language_of(args),
                                     root=root)
        reason = rr.get("reviewer_degrade_reason") or "peer_unavailable"
        return _blocked_review("sage cross-check",
                               tr(language_of(args), "cli.review.blocked_reviewer_unavailable",
                                  reason=reason))

    peer = rr["reviewer_runtime"]

    # 모델·effort 는 peer 런타임에 종속된 값이다(`gpt-…`/`opus`, codex 는 max 를 모르고 claude 는
    # minimal 을 모른다). 프로필 기준 peer 와 실제 peer 가 갈릴 수 있으므로 실제 peer 로 다시 본다.
    issue = effort_issue(peer, effort) if configured else None
    if issue:
        print(f"[sage cross-check] TOOL ERROR: {render_issue(language_of(args), issue)}",
              file=sys.stderr)
        print("REVIEWER_STATUS: BLOCKED")
        return 2
    reviewer_model, model_note_suffix = _model_for_peer(profile, peer, reviewer_model)

    prompt = _read_packet(args.packet_file, "sage cross-check", language_of(args))
    if prompt is None:
        return _blocked_review("sage cross-check",
                               tr(language_of(args), "cli.review.blocked_packet_required"), 2)

    if model_note_suffix:
        print(f"[sage cross-check] ⚠️  {render_issue(language_of(args), model_note_suffix)}",
              file=sys.stderr)
    eff_note = f"effort={effort}" + ("" if configured
                                     else tr(language_of(args), "cli.review.effort_default_suffix"))
    model_note = reviewer_model or "peer CLI default"
    print(tr(language_of(args), "cli.review.msg05", peer=peer, args_timeout=args.timeout, eff_note=eff_note, model_note=model_note), file=sys.stderr)
    run = _call_peer(peer, prompt, args.timeout, root, effort, reviewer_model)
    if not run.ok:
        on_failure = getattr(args, "on_peer_failure", "block") or "block"
        if on_failure == "same-runtime" and run.reason in _FALLBACK_REASONS:
            return _fallback_same_runtime(args, profile, current, run, root)
        return _blocked_peer("sage cross-check", run, language_of(args),
                             tr(language_of(args), "cli.review.blocked_peer_review_failed",
                                peer=peer, err=render_issue(language_of(args), run.error)))

    # peer 리뷰 본문 = stdout(스킬이 05 문서/REWORK 입력으로 사용).
    print(f"===== {peer.upper()} CROSS-MODEL REVIEW =====")
    print(run.review)
    print(f"===== END {peer.upper()} REVIEW =====")
    print(f"REVIEWER_PROCESS: {_review_process(peer)}")
    print(f"REVIEWER_HOST: {peer}")
    print(f"REVIEWER_MODEL: {reviewer_model or 'cli-default'}")
    _print_run_telemetry(run)
    degraded = bool(run.violations)
    print(f"REVIEWER_ACTUAL: cross_model{'_degraded' if degraded else ''}")
    print(f"REVIEWER_STATUS: {'COMPLETE_DEGRADED' if degraded else 'COMPLETE'}")
    return 0


# 폴백 대상 실패 사유. peer 가 답했는데 수집에 실패한 경우(parse_failed)는 자체 리뷰로 덮을 일이
# 아니라 원인 조사 대상이고, 플래그 거부(flags_rejected)는 SAGE 가 붙인 인자의 문제라 고쳐야 한다.
# startup_failed 는 포함한다 — 사용자가 이 라운드에 폴백을 명시적으로 켰고, 폴백은 사유와 함께 강등으로 남는다.
_FALLBACK_REASONS = frozenset({"timeout", "usage_limit", "exit_nonzero", "startup_failed"})


def _fallback_same_runtime(args, profile, current, run, root):
    """peer 런타임 실패 → 실행 중인 host 의 새 프로세스로 1회만 리뷰(재귀 없음).

    프로필 키가 아니라 호출 단위 옵션인 이유: `cross_model.on_unavailable` 은 `block` 고정이 의도된
    설계다. 커밋되는 정책 파일에 상시 완화를 두지 않고, 완화는 그 라운드의 기록된 결정으로만 남긴다.
    강등은 REVIEWER_ACTUAL 이 요청과 달라 ci_authority 가 잡는다 — 교차 리뷰로 위장되지 않는다.
    """
    language = language_of(args)
    from sage.profile_layers import cross_model_policy
    if cross_model_policy(profile) == "required":
        return _blocked_peer("sage cross-check", run, language,
                             tr(language, "cli.review.fallback_policy_required",
                                err=render_issue(language, run.error)))
    # 폴백까지 합친 대기가 두 배가 되지 않게 절반으로 제한한다(하한을 두면 짧은 timeout 에서 절반을 넘는다).
    timeout = max(1, int(args.timeout) // 2)
    print(tr(language, "cli.review.fallback_same_runtime", peer=run.peer, host=current,
             reason=run.reason, timeout=timeout), file=sys.stderr)
    _print_partial(run)
    return _run_same_runtime(profile, current, args.packet_file, timeout,
                             command="sage cross-check", language=language, root=root,
                             fallback_from=run.peer, fallback_reason=run.reason, failed_run=run)
