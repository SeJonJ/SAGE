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
    pr.set_defaults(func=run_review)

    pc = sub.add_parser("cross-check", help="Phase 05 cross-model 리뷰 — 반대 런타임 CLI 직접 호출")
    pc.add_argument("--packet-file", required=True,
                    help="리뷰 패킷(변경 diff + 05 맥락) 파일 — peer 에게 전달할 프롬프트")
    pc.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT, help=f"peer 호출 상한 초(기본 {_DEFAULT_TIMEOUT})")
    pc.add_argument("--root", default=None)
    pc.set_defaults(func=run_cross_check)


# ---- 순수 헬퍼(테스트 직격) ----

def _peer_command(peer, prompt):
    """peer 런타임 비대화 리뷰 argv. shell 미경유(주입 안전). stdin 은 호출부가 DEVNULL 로 차단."""
    if peer == "codex":
        # codex exec: 비대화 1턴. read-only 샌드박스 + 캐시 web_search 끔(결정성). PROMPT 는 positional.
        return ["codex", "exec", "--json", "-s", "read-only",
                "-c", 'model_reasoning_effort="high"', prompt]
    if peer == "claude":
        return ["claude", "-p", "--output-format", "json", prompt]
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
    표준 형태는 {..., "result": "<text>"}; 비표준이면 raw 반환 회피하고 None."""
    try:
        o = json.loads(text)
    except Exception:
        return None
    if isinstance(o, dict):
        r = o.get("result")
        if isinstance(r, str) and r.strip():
            return r
    return None


def _parse_peer_output(peer, text):
    return _parse_codex_jsonl(text) if peer == "codex" else _parse_claude_json(text)


# ---- subprocess 경계(테스트는 이 함수를 monkeypatch) ----

def _invoke_peer(peer, prompt, timeout):
    """peer 런타임을 비대화 실행 → (ok, review_text, err). 미설치/타임아웃/비정상종료/파싱실패 = (False, None, 사유)."""
    if not shutil.which(peer):
        return False, None, f"{peer} CLI 미설치(PATH 없음)"
    cmd = _peer_command(peer, prompt)
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=timeout)
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
    path = os.path.join(root, "sage", "project-profile.yaml") if root else None
    profile = {}
    if path and os.path.exists(path):
        try:
            import yaml
            profile = yaml.safe_load(open(path, encoding="utf-8")) or {}
            if not isinstance(profile, dict):
                profile = {}
        except Exception:
            profile = {}
    caps_prof = profile.get("capabilities", {}) or {}
    caps = {"codex": bool(shutil.which("codex")) or bool(caps_prof.get("codex")),
            "claude": bool(shutil.which("claude")) or bool(caps_prof.get("claude"))}
    rr = _doctor.reviewer_resolution(profile, caps)
    return profile, caps, rr


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
    root = _find_root(args.root)
    _, _, rr = _load_profile_caps(root)
    if rr["reviewer_mode"] == "opposite_runtime":
        print("[sage review] ⚠️  profile.options.cross_model=true 이고 peer 가용 — cross-model 의도인데 "
              "same-runtime `sage review` 가 호출됨. cross_model=true 면 `sage cross-check` 를 사용하라.",
              file=sys.stderr)
    print("[sage review] same-runtime Phase 05 — host 가 clean-context 로 FIND/REFUTE/TRIAGE/REWORK 수행.",
          file=sys.stderr)
    print("REVIEWER_ACTUAL: same_runtime")
    return 0


def run_cross_check(args):
    """cross-model 경로. reviewer_resolution 으로 peer 결정 → 도달 가능하면 직접 호출, 아니면 폴백 표면화."""
    root = _find_root(args.root)
    _, _, rr = _load_profile_caps(root)

    if rr["reviewer_mode"] != "opposite_runtime":
        # cross 미설정이거나 peer CLI 미가용 → same-runtime 폴백을 침묵시키지 않고 명시(degraded 근거).
        reason = rr.get("reviewer_degrade_reason") or "cross_model_off"
        print(f"[sage cross-check] ⚠️  cross-model 미수행 → same-runtime 폴백 ({reason}). "
              f"{rr['notice']}", file=sys.stderr)
        print("REVIEWER_ACTUAL: same_runtime")
        return 0

    peer = rr["reviewer_runtime"]
    try:
        prompt = open(args.packet_file, encoding="utf-8").read()
    except Exception as e:
        print(f"[sage cross-check] TOOL ERROR: 패킷 파일 읽기 실패: {e}", file=sys.stderr)
        return 2
    if not prompt.strip():
        print("[sage cross-check] TOOL ERROR: 패킷이 비어 있음", file=sys.stderr)
        return 2

    print(f"[sage cross-check] {peer} 직접 호출 중(timeout {args.timeout}s)…", file=sys.stderr)
    ok, review, err = _invoke_peer(peer, prompt, args.timeout)
    if not ok:
        # peer 도달 실패 → 폴백을 침묵시키지 않음(6차 버그 수정). degraded 로 게이트가 잡게 한다.
        print(f"[sage cross-check] ⚠️  {peer} 리뷰 실패 → same-runtime 폴백: {err}", file=sys.stderr)
        print("REVIEWER_ACTUAL: same_runtime")
        return 0

    # peer 리뷰 본문 = stdout(스킬이 05 문서/REWORK 입력으로 사용). 마지막 줄에 REVIEWER_ACTUAL.
    print(f"===== {peer.upper()} CROSS-MODEL REVIEW =====")
    print(review)
    print(f"===== END {peer.upper()} REVIEW =====")
    print("REVIEWER_ACTUAL: cross_model")
    return 0
