"""sage review / sage cross-check — Phase 05 리뷰 오케스트레이션 (7차 배치2).

두 명령은 sage-team 이 Phase 05 에서 profile.options.cross_model 에 따라 택일 호출한다:
- cross_model=false → `sage review`      : host AI 자신이 clean-context 리뷰(same-runtime). peer 호출 없음.
- cross_model=true  → `sage cross-check`  : 반대 런타임 CLI 를 **직접 호출**해 독립 리뷰 획득(cross-model).

둘 다 표준 마지막 줄 `REVIEWER_ACTUAL: <mode>` 를 출력한다 — sage-team 이 이를 캡처해
`sage review-loop close --reviewer-actual <mode>` 로 넘기면 의도(open 의 --reviewer-requested)와 대조해
degraded 가 판정된다(배치3). cross-model 요청이 peer 미도달로 same-runtime 으로 떨어지면 침묵하지 않고
REVIEWER_ACTUAL: same_runtime 으로 표면화 → 게이트가 degraded 로 차단/경고한다(6차 폴백 침묵 버그 수정).

gstack 의존 없음: claude-host→`codex exec`, codex-host→`claude -p` 를 SAGE 가 직접 호출(gstack wrapper
기법만 차용 — read-only 샌드박스·stdin 차단·timeout·--json 최종 메시지 파싱).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

from sage.commands import doctor as _doctor

_DEFAULT_TIMEOUT = 540   # codex/claude 비대화 1턴 상한(초). gstack /codex 의 330~600 대역과 정합.


def register(sub):
    pr = sub.add_parser("review", help="Phase 05 same-runtime 리뷰(cross_model=false 경로)")
    pr.add_argument("--root", default=None)
    # 마이그레이션 shim(codex 배치2 R3 P1): `sage review` 는 자산분류→Phase05 리뷰로 의미가 바뀌었다.
    # 구 자산분류 플래그를 hidden 으로 받아, 쓰이면 친절히 `sage asset-check` 로 안내(암호적 argparse 실패 방지).
    # 동작은 넘기지 않는다(유저 결정: review=same-runtime). SAGE 가 PyPI 배포라 다운스트림 CI 충격 완화용.
    pr.add_argument("--kind", help=argparse.SUPPRESS)
    pr.add_argument("--batch", action="store_true", help=argparse.SUPPRESS)
    pr.add_argument("--gate", action="store_true", help=argparse.SUPPRESS)
    pr.set_defaults(func=run_review)

    pc = sub.add_parser("cross-check", help="Phase 05 cross-model 리뷰 — 반대 런타임 CLI 직접 호출")
    pc.add_argument("--packet-file", required=True,
                    help="리뷰 패킷(변경 diff + 05 맥락) 파일 — peer 에게 전달할 프롬프트")
    pc.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT, help=f"peer 호출 상한 초(기본 {_DEFAULT_TIMEOUT})")
    pc.add_argument("--strict", action="store_true",
                    help="cross-model 미수행(폴백) 시 exit 3 (stdout 센티넬을 놓치는 자동 caller/CI 용). 기본 off")
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
# peer/on_unavailable 은 엔진이 값으로 분기하지 않는다 — reviewer_resolution 이 host 의 반대 런타임을
# 계산하고, peer 미가용이면 항상 clean-context 로 폴백한다. 즉 이 키들은 그 동작을 *서술*할 뿐이다.
# 다른 값을 쓰면(`on_unavailable: block`) 안전정책처럼 보이지만 아무 일도 안 하므로 FAIL 로 막는다.
CROSS_MODEL_FIXED = {"peer": "opposite_runtime", "on_unavailable": "clean_context_same_runtime"}


def intended_peer(profile):
    """검증 대상 peer = host 의 반대 런타임. peer CLI 도달 가능성과 무관하다 —
    peer 가 마침 미가용이면 잘못된 설정이 검증 없이 통과해버린다."""
    from sage.runtime_hosts import opposite_host
    return opposite_host(profile)


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

    두 곳이 서로 다른 규칙을 쓰면, cross-check 가 `effrot: xhigh` 나 `on_unavailable: block` 을
    조용히 무시한 채 기본값으로 돌면서 설정대로 돈 것처럼 보인다(codex 7R).
    """
    cm = profile.get("cross_model") if isinstance(profile, dict) else None
    if cm in (None, ""):
        return []
    if not isinstance(cm, dict):
        # jsonschema 는 선택 의존성 → 구조검증이 skip 되는 환경에서 여기가 유일한 관문이다.
        return [("FAIL", f"cross_model 은 매핑이어야 함 (받음: {type(cm).__name__})")]
    issues = []
    unknown = [k for k in cm if k not in CROSS_MODEL_KEYS]
    if unknown:
        # `effrot: max` 가 조용히 무시되면 기본값으로 돌면서 설정대로 돈 것처럼 보인다.
        issues.append(("FAIL", f"cross_model 의 알 수 없는 키: {', '.join(sorted(str(k) for k in unknown))} "
                               f"(허용: {', '.join(sorted(CROSS_MODEL_KEYS))})"))
    policy = cm.get("policy")
    if policy not in (None, "", "required", "recommended", "off"):
        issues.append(("FAIL", f"cross_model.policy={policy!r} — required, recommended, off 중 하나여야 함"))
    for key, only in CROSS_MODEL_FIXED.items():
        val = cm.get(key)
        if val not in (None, "") and val != only:
            issues.append(("FAIL", f"cross_model.{key}={val!r} 는 엔진이 구현하지 않는 값 — "
                                   f"`{only}` 만 지원합니다(다른 값은 무동작이라 안전정책으로 오인됩니다)"))
    effort, configured = resolve_effort(profile)
    if configured is not None:
        issue = effort_issue(intended_peer(profile), effort)
        if issue:
            issues.append(("FAIL", issue))
    from sage.model_routing import reviewer_issues
    issues.extend(reviewer_issues(profile))
    return issues


def effort_issue(peer, effort):
    """cross_model.effort 검증 → 문제 문자열(없으면 None). validate/doctor/cross-check 공용."""
    if effort in (None, ""):
        return None
    if peer not in PEER_EFFORTS:
        return f"cross_model.effort: 알 수 없는 peer {peer!r}"
    if effort not in PEER_EFFORTS[peer]:
        return (f"cross_model.effort={effort!r} 는 {peer} 가 모르는 값 "
                f"(허용: {', '.join(PEER_EFFORTS[peer])}). {peer} 는 모르는 값을 조용히 무시하므로 차단합니다")
    return None


def _peer_command(peer, effort=None, model=None):
    """peer 런타임 비대화 리뷰 argv(프롬프트 제외). shell 미경유(주입 안전).
    프롬프트는 **stdin** 으로 전달한다(codex R1 P1): positional arg 로 넘기면 큰 diff 가 OS ARG_MAX 를
    넘겨 모든 대형 리뷰가 same_runtime 으로 degrade. codex exec/claude -p 둘 다 prompt 부재 시 stdin 을 읽는다.

    model 은 지정하지 않는다 — peer CLI 자신의 설정이 고른 모델을 존중한다. effort 는 호출자가
    해석한 값(profile `cross_model.effort` 또는 DEFAULT_EFFORT)을 넘긴다. None 이면 argv 에 아무것도
    붙이지 않아 peer CLI 기본값이 된다."""
    if peer == "codex":
        # codex exec: 비대화 1턴, read-only 샌드박스. PROMPT 생략 → stdin 읽기.
        cmd = ["codex", "exec", "--json", "-s", "read-only"]
        if effort:
            cmd += ["-c", f'model_reasoning_effort="{effort}"']
        if model:
            cmd += ["-m", model]
        return cmd
    if peer == "claude":
        cmd = ["claude", "-p", "--output-format", "json"]
        if effort:
            cmd += ["--effort", effort]
        if model:
            cmd += ["--model", model]
        return cmd
    raise ValueError(f"unknown peer runtime: {peer!r}")


def _parse_codex_jsonl(text):
    """codex exec --json stdout(JSONL) → 최종 agent_message 텍스트(없으면 None).
    item.completed 이벤트 중 item.type=='agent_message' 의 마지막 text."""
    last = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        it = o.get("item") or {}
        if o.get("type") == "item.completed" and it.get("type") == "agent_message" and it.get("text"):
            last = it["text"]
    return last


def _parse_claude_json(text):
    """claude -p --output-format json stdout → 최종 결과 텍스트(없으면 None).
    표준 형태는 {"is_error": bool, "result": "<text>", ...}.
    is_error=true(에러 응답)면 result 가 에러 메시지이므로 리뷰로 오인하지 않고 None(codex 배치2 R5 P1:
    에러 JSON 을 성공 cross-model 리뷰로 잘못 보고하면 degraded 게이트를 우회)."""
    try:
        o = json.loads(text)
    except Exception:
        return None
    if isinstance(o, dict) and not o.get("is_error"):
        r = o.get("result")
        if isinstance(r, str) and r.strip():
            return r
    return None


def _parse_peer_output(peer, text):
    return _parse_codex_jsonl(text) if peer == "codex" else _parse_claude_json(text)


# ---- subprocess 경계(테스트는 이 함수를 monkeypatch) ----

def _invoke_peer(peer, prompt, timeout, effort=None, model=None):
    """peer 런타임을 비대화 실행 → (ok, review_text, err). 미설치/타임아웃/비정상종료/파싱실패 = (False, None, 사유)."""
    if not shutil.which(peer):
        return False, None, f"{peer} CLI 미설치(PATH 없음)"
    cmd = _peer_command(peer, effort, model)
    try:
        # 프롬프트는 stdin 으로(ARG_MAX 회피, codex R1 P1). codex exec/claude -p 가 stdin 을 프롬프트로 읽음.
        # encoding 명시(codex R2 P2): text=True 만 두면 locale 인코딩 사용 → C-locale 호스트에서 한글
        # 패킷이 UnicodeEncodeError 로 매번 degrade. 패킷 파일도 utf-8 로 읽으므로 대칭 맞춤.
        r = subprocess.run(cmd, input=prompt, capture_output=True,
                           text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, None, f"{peer} 호출 timeout({timeout}s)"
    except Exception as e:
        return False, None, f"{peer} 호출 예외: {e}"
    if r.returncode != 0:
        return False, None, f"{peer} 비정상 종료(exit {r.returncode}): {(r.stderr or '').strip()[:200]}"
    review = _parse_peer_output(peer, r.stdout or "")
    if not review:
        return False, None, f"{peer} 출력에서 리뷰 메시지 파싱 실패"
    return True, review, None


def _load_profile_caps(root):
    """profile + peer CLI 가용성 caps → (profile, caps, rr)."""
    profile, caps, rr, _ = _load_profile_layers_caps(root)
    return profile, caps, rr


def _load_profile_layers_caps(root):
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
    rr = _doctor.reviewer_resolution(profile, caps)
    return profile, caps, rr, layers


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


def run_review(args):
    """same-runtime 경로. peer 호출 없음 — host AI 자신이 clean-context 로 리뷰한다(스킬이 수행).
    cross_model=true 인데 이 명령을 부르면 의도 불일치를 경고(스킬 라우팅 오류 방지)."""
    # 구 `sage review`(자산분류) 플래그 감지 → 친절한 이름변경 안내(codex 배치2 R3 P1).
    if getattr(args, "kind", None) is not None or getattr(args, "batch", False) or getattr(args, "gate", False):
        print("[sage review] 이 명령은 Phase 05 리뷰로 의미가 바뀌었습니다. 자산 자동승인 분류는 "
              "`sage asset-check` 로 이름이 변경됐습니다 — `sage asset-check --kind … [--batch] [--gate]`.",
              file=sys.stderr)
        return 2
    root = _find_root(args.root)
    _, _, rr, layers = _load_profile_layers_caps(root)
    layer_failures = _blocking_layer_issues(layers)
    if layer_failures:
        for message in layer_failures:
            print(f"[sage review] TOOL ERROR: {message}", file=sys.stderr)
        return 2
    if rr["reviewer_mode"] == "opposite_runtime":
        print("[sage review] ⚠️  profile.options.cross_model=true 이고 peer 가용 — cross-model 의도인데 "
              "same-runtime `sage review` 가 호출됨. cross_model=true 면 `sage cross-check` 를 사용하라.",
              file=sys.stderr)
    # bare `sage review` 는 옛 자산분류가 아니라 Phase 05 same-runtime 리뷰임을 명시(codex 배치2 R4 P1:
    # 무플래그 호출의 의미 변경을 silent 로 두지 않음. 자산분류는 sage asset-check 로 이전).
    print("[sage review] Phase 05 same-runtime 리뷰 — host 가 clean-context 로 FIND/REFUTE/TRIAGE/REWORK 수행. "
          "(자산 자동승인 분류는 `sage asset-check` 로 이전됨)", file=sys.stderr)
    print("REVIEWER_ACTUAL: same_runtime")
    return 0


def run_cross_check(args):
    """cross-model 경로. reviewer_resolution 으로 peer 결정 → 도달 가능하면 직접 호출, 아니면 폴백 표면화."""
    root = _find_root(args.root)
    profile, _, rr, layers = _load_profile_layers_caps(root)
    layer_failures = _blocking_layer_issues(layers)
    if layer_failures:
        for message in layer_failures:
            print(f"[sage cross-check] TOOL ERROR: {message}", file=sys.stderr)
        return 2

    # cross_model 검증은 폴백 판정보다 **먼저** — peer 가 마침 미가용이면 잘못된 설정이 통과해버린다.
    # `sage validate` 와 같은 규칙(cross_model_issues)을 쓴다: 다르면 한쪽이 조용히 무시된다.
    fails = [m for sev, m in cross_model_issues(profile) if sev == "FAIL"]
    if fails:
        for m in fails:
            print(f"[sage cross-check] TOOL ERROR: {m}", file=sys.stderr)
        return 2
    effort, configured = resolve_effort(profile)
    from sage.model_routing import reviewer_selection
    _, reviewer_model = reviewer_selection(profile)

    if rr["reviewer_mode"] != "opposite_runtime":
        # cross 미설정이거나 peer CLI 미가용 → same-runtime 폴백을 침묵시키지 않고 명시(degraded 근거).
        reason = rr.get("reviewer_degrade_reason") or "cross_model_off"
        print(f"[sage cross-check] ⚠️  cross-model 미수행 → same-runtime 폴백 ({reason}). "
              f"{rr['notice']}", file=sys.stderr)
        print("REVIEWER_ACTUAL: same_runtime")
        return 3 if getattr(args, "strict", False) else 0

    peer = rr["reviewer_runtime"]

    try:
        prompt = open(args.packet_file, encoding="utf-8").read()
    except Exception as e:
        print(f"[sage cross-check] TOOL ERROR: 패킷 파일 읽기 실패: {e}", file=sys.stderr)
        return 2
    if not prompt.strip():
        print("[sage cross-check] TOOL ERROR: 패킷이 비어 있음", file=sys.stderr)
        return 2

    eff_note = f"effort={effort}" + ("" if configured else " (기본값)")
    model_note = reviewer_model or "peer CLI default"
    print(f"[sage cross-check] {peer} 직접 호출 중(timeout {args.timeout}s, {eff_note}, model={model_note})…", file=sys.stderr)
    if reviewer_model:
        ok, review, err = _invoke_peer(peer, prompt, args.timeout, effort, reviewer_model)
    else:
        # Keep the legacy call shape for downstream monkeypatch/adapters when no model was configured.
        ok, review, err = _invoke_peer(peer, prompt, args.timeout, effort)
    if not ok:
        # peer 도달 실패 → 폴백을 침묵시키지 않음(6차 버그 수정). degraded 로 게이트가 잡게 한다.
        print(f"[sage cross-check] ⚠️  {peer} 리뷰 실패 → same-runtime 폴백: {err}", file=sys.stderr)
        print("REVIEWER_ACTUAL: same_runtime")
        return 3 if getattr(args, "strict", False) else 0

    # peer 리뷰 본문 = stdout(스킬이 05 문서/REWORK 입력으로 사용). 마지막 줄에 REVIEWER_ACTUAL.
    print(f"===== {peer.upper()} CROSS-MODEL REVIEW =====")
    print(review)
    print(f"===== END {peer.upper()} REVIEW =====")
    print("REVIEWER_ACTUAL: cross_model")
    return 0
