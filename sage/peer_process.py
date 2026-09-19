"""Phase 05 peer 리뷰어 프로세스 — 실행·비용 통제·사용량 수집·행동 감사.

`sage cross-check`/`sage review` 가 리뷰어를 headless 프로세스(`codex exec`/`claude -p`)로 띄울 때
여기를 거친다. 리뷰 기준은 호스트와 같은데 peer 만 저장소를 재탐색·테스트 재실행·하위 에이전트
생성으로 토큰을 수백만 단위로 써서 한도·제한 시간에 끊겼다. 프롬프트로 금지해도 지켜지지 않았으므로
프로세스 경계에서 막는다.

두 CLI 의 강제 수단은 서로 반대 방향으로 비대칭이다. claude 는 도구를 제거할 수 있고(`--restricted`
가 Bash 계열을 없앤다) codex 는 셸이 유일한 도구라 제거가 불가능하다. 그래서 목표는 "같은 플래그"가
아니라 "같은 상한"이고, 옵션으로 못 막는 쪽은 사후 감사로 드러낸다.

peer 는 저장소 밖 빈 임시 디렉터리에서 띄운다. 두 CLI 모두 작업 디렉터리 기준으로 프로젝트 지침
(CLAUDE.md/AGENTS.md)을 자동 주입하고 SAGE hook 을 발동시키는데, 리뷰어에게는 둘 다 필요 없는 맥락이다.
저장소는 절대경로로 읽힌다(claude 는 `--add-dir` 로 읽기를 허용한다).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time

from sage.diagnostics import Diagnostic

# 통제 플래그를 실측으로 확인한 최소 버전. 이보다 낮다고 **확인된** 경우에만 통제 없이 실행한다.
# 버전을 못 읽으면 통제를 건다 — 모르는 플래그면 peer 가 명시적으로 거부하므로(`peer_flags_rejected`)
# 조용히 통제 없이 도는 경로가 생기지 않는다.
MIN_CONTROLLED_VERSION = {"claude": (2, 1, 275)}

# 통제가 **불가능하게 만든** 행동. 관측되면 리뷰 내용과 무관하게 통제가 실패한 것이다.
# claude: `--restricted` 가 Bash 계열을, `--disallowedTools` 가 하위 에이전트를 없앤다.
_CLAUDE_FORBIDDEN_TOOLS = frozenset({"Bash", "BashOutput", "KillShell", "Agent", "Task"})

# 리뷰어가 따라야 할 탐색·출력 계약. 모든 프로젝트에서 같으므로 패킷 작성자(호스트 AI)에게 맡기지
# 않고 여기서 붙인다 — 빠지거나 바뀌어 쓰일 여지를 없앤다.
REVIEW_CONTRACT = """\
# SAGE reviewer contract (prepended by `sage cross-check` — do not ignore)

Repository root (read files by absolute path under it): {root}
Your working directory is an empty scratch directory on purpose.

## Exploration budget
- Judge from this packet first. Draft your verdict before reading any file.
- Then read only what a specific claim needs: files named in the packet's context map and
  their direct callers/callees. Use `rg -n` and ranged reads (at most ~150 lines per read).
- Hard limit: {max_lookups} file lookups for this review. When you reach it, stop exploring,
  list what you could not check under UNEXPLORED, and output.
- Do NOT: re-read rule/profile/skill/memory documents, run tests or builds, spawn sub-agents,
  inspect git history, or dump whole files. Verification evidence in the packet is authoritative.

## Output contract
- Emit each finding as soon as you confirm it, as its own message, starting with `FINDING:`
  (severity P0-P3, file:line, claim, evidence, whether you looked outside the packet).
  A review cut off by the time limit keeps whatever findings were already emitted.
- Final message: proposition verdicts (true/false/unverified with file:line), the full finding
  list, coverage (lens x file, files read, UNEXPLORED), then the verdict line.

---

"""


class PeerRun:
    """peer 1회 실행의 결과. `reason` 은 기계 판독용 실패 사유(성공이면 None)."""

    __slots__ = ("peer", "ok", "review", "error", "reason", "partial", "usage", "tool_calls",
                 "violations", "controls", "wall_s", "rate_limited")

    def __init__(self, peer, ok=False, review=None, error=None, reason=None, partial=None,
                 usage=None, tool_calls=None, violations=(), controls="none", wall_s=None,
                 rate_limited=False):
        self.peer = peer
        self.ok = ok
        self.review = review
        self.error = error
        self.reason = reason
        self.partial = partial
        self.usage = usage
        self.tool_calls = tool_calls
        self.violations = list(violations)
        self.controls = controls
        self.wall_s = wall_s
        self.rate_limited = rate_limited

    @classmethod
    def from_legacy(cls, peer, ok, review, error):
        """monkeypatch/어댑터가 돌려준 `(ok, review, err)` — 사용량·감사는 알 수 없다(0 이 아니다)."""
        reason = None
        if not ok:
            code = getattr(error, "code", "") or ""
            reason = code[len("review.peer_"):] if code.startswith("review.peer_") else "unknown"
        return cls(peer, ok=ok, review=review, error=error, reason=reason, controls="unknown")

    def tokens_line(self):
        """`REVIEWER_TOKENS:` 값. 측정값이 없으면 `unknown` — 0 으로 쓰면 예산 게이트가 여유로 읽는다."""
        if not self.usage:
            return "unknown"
        u = self.usage
        parts = [f"{k}={u[k]}" for k in ("new_input", "cached_input", "output") if u.get(k) is not None]
        if not parts:
            return "unknown"
        if u.get("turns") is not None:
            parts.append(f"turns={u['turns']}")
        if self.tool_calls is not None:
            parts.append(f"tool_calls={self.tool_calls}")
        if self.wall_s is not None:
            parts.append(f"wall_s={int(round(self.wall_s))}")
        if u.get("cost_usd") is not None:
            parts.append(f"cost_usd={u['cost_usd']}")
        return " ".join(parts)


# ---- 버전 ----

def parse_version(text):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def cli_version(peer):
    """peer CLI 버전 튜플. 못 읽으면 None."""
    try:
        r = subprocess.run([peer, "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
    except Exception:
        return None
    return parse_version(r.stdout) or parse_version(r.stderr)


def controls_supported(peer, version):
    """통제 플래그를 붙일지. 최소 버전 미만으로 **확인된** 경우만 False."""
    floor = MIN_CONTROLLED_VERSION.get(peer)
    if floor is None:
        return False            # 통제 조합이 아직 확정되지 않은 peer
    return version is None or version >= floor


# ---- argv ----

def peer_command(peer, effort=None, model=None, root=None, controlled=False):
    """peer 리뷰 argv(프롬프트 제외 — stdin 으로 넘긴다)."""
    if peer == "codex":
        cmd = ["codex", "exec", "--json", "-s", "read-only"]
        if effort:
            cmd += ["-c", f'model_reasoning_effort="{effort}"']
        if model:
            cmd += ["-m", model]
        return cmd
    if peer == "claude":
        if not controlled:
            cmd = ["claude", "-p", "--output-format", "json"]
        else:
            # stream-json: 중간 이벤트가 흘러야 제한 시간에 끊겨도 확인된 finding 이 남는다.
            # -p 에서 stream-json 은 --verbose 가 필수다(없으면 exit 1).
            cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose",
                   "--restricted",
                   "--disallowedTools", "Agent", "Task",
                   "--setting-sources", "",
                   "--strict-mcp-config", "--disable-slash-commands",
                   "--no-session-persistence"]
            if root:
                cmd += ["--add-dir", root]
        if effort:
            cmd += ["--effort", effort]
        if model:
            cmd += ["--model", model]
        return cmd
    raise ValueError(f"unknown peer runtime: {peer!r}")


# ---- 출력 파싱 ----

def parse_codex_jsonl(text):
    """codex exec --json stdout → 마지막 agent_message 텍스트(없으면 None)."""
    last = None
    for o in _json_lines(text):
        it = o.get("item") or {}
        if o.get("type") == "item.completed" and it.get("type") == "agent_message" and it.get("text"):
            last = it["text"]
    return last


def parse_claude_json(text):
    """claude -p --output-format json stdout → 결과 텍스트. is_error 면 None(에러를 리뷰로 오인 금지)."""
    try:
        o = json.loads(text)
    except Exception:
        return None
    if isinstance(o, dict) and not o.get("is_error"):
        r = o.get("result")
        if isinstance(r, str) and r.strip():
            return r
    return None


def _json_lines(text):
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if isinstance(o, dict):
            yield o


def summarize_claude_stream(text):
    """claude stream-json → dict(review, partial, usage, tool_calls, violations, rate_limited).

    `review` 는 is_error 가 아닌 result 이벤트의 본문만. 끊긴 스트림이면 None 이고, 그때까지 나온
    assistant 텍스트가 `partial` 로 남는다.
    """
    texts, tool_calls, violations = [], 0, []
    result = None
    rate_limited = False
    for o in _json_lines(text):
        t = o.get("type")
        if t == "assistant":
            for c in (o.get("message") or {}).get("content") or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text" and c.get("text"):
                    texts.append(c["text"])
                elif c.get("type") == "tool_use":
                    tool_calls += 1
                    name = c.get("name")
                    if name in _CLAUDE_FORBIDDEN_TOOLS:
                        violations.append(f"forbidden_tool:{name}")
        elif t == "rate_limit_event":
            info = o.get("rate_limit_info") or {}
            if info.get("status") not in (None, "allowed", "allowed_warning"):
                rate_limited = True
        elif t == "result":
            result = o
    review = None
    usage = None
    if result is not None:
        if not result.get("is_error"):
            r = result.get("result")
            if isinstance(r, str) and r.strip():
                review = r
        u = result.get("usage") or {}
        if isinstance(u, dict) and u:
            # new_input = 캐시 밖 입력(신규 + 캐시 기록). 캐시 읽기는 따로 — 제공자 한도가 캐시를 어떻게
            # 세는지 모르므로 두 해석 모두에서 판단할 수 있게 나눠 둔다.
            new_input = (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
            usage = {"new_input": new_input,
                     "cached_input": u.get("cache_read_input_tokens") or 0,
                     "output": u.get("output_tokens") or 0,
                     "turns": result.get("num_turns"),
                     "cost_usd": result.get("total_cost_usd")}
        spawned = ((result.get("subagent_stats") or {}).get("spawned") or 0)
        if spawned:
            violations.append(f"subagent_spawned:{spawned}")
        if result.get("is_error") and re.search(r"(?i)usage limit|rate limit", str(result.get("result") or "")):
            rate_limited = True
    return {"review": review, "partial": "\n\n".join(texts) or None, "usage": usage,
            "tool_calls": tool_calls, "violations": violations, "rate_limited": rate_limited}


# ---- 프로세스 ----

def _popen_kwargs():
    # peer 가 띄운 셸 명령(npm test 등)까지 함께 끝내려면 peer 를 새 프로세스 그룹의 리더로 띄워야
    # 한다. peer 만 죽이면 자식은 고아로 남아 계속 돈다(실측: codex 강제 종료 후 `sleep 60` 생존).
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _kill_tree(proc):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=30)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def run_process(cmd, prompt, timeout, env=None, cwd=None):
    """(returncode|None, stdout, stderr, timed_out, wall_s). timeout 이면 프로세스 트리를 끝내고
    그때까지의 출력을 돌려준다."""
    # 프롬프트는 stdin 으로 넘긴다. positional arg 로 넘기면 큰 diff 가 OS ARG_MAX 를 넘겨 대형 리뷰가
    # 전부 실패한다. encoding 을 명시하지 않으면 locale 인코딩을 써서 C-locale 호스트에서 한글 패킷이
    # UnicodeEncodeError 로 매번 실패한다(패킷 파일도 utf-8 로 읽으므로 대칭).
    start = time.monotonic()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, cwd=cwd, text=True,
                            encoding="utf-8", errors="replace", **_popen_kwargs())
    try:
        out, err = proc.communicate(input=prompt, timeout=timeout)
        return proc.returncode, out or "", err or "", False, time.monotonic() - start
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=30)
        except Exception:
            out, err = "", ""
        return None, out or "", err or "", True, time.monotonic() - start


def _flags_rejected(peer, stderr):
    s = stderr or ""
    if peer == "claude":
        return "unknown option" in s or "error: option" in s
    return "unexpected argument" in s or "Unknown feature flag" in s


def run_peer(peer, prompt, timeout, effort=None, model=None, root=None, env=None):
    """peer 리뷰 1회 → PeerRun."""
    if not shutil.which(peer):
        return PeerRun(peer, error=Diagnostic("review.peer_cli_missing", peer=peer),
                       reason="cli_missing")
    version = cli_version(peer)
    controlled = controls_supported(peer, version)
    cmd = peer_command(peer, effort, model, root=root, controlled=controlled)
    if controlled:
        prompt = REVIEW_CONTRACT.format(root=root or os.getcwd(), max_lookups=12) + prompt
    workdir = tempfile.mkdtemp(prefix="sage-peer-") if controlled else None
    try:
        code, out, err, timed_out, wall = run_process(cmd, prompt, timeout, env=env, cwd=workdir)
    except Exception as e:
        return PeerRun(peer, error=Diagnostic("review.peer_exception", evidence=str(e), peer=peer),
                       reason="exception", controls="full" if controlled else "none")
    finally:
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)
    run = PeerRun(peer, controls="full" if controlled else "none", wall_s=wall)
    if peer == "claude" and controlled:
        s = summarize_claude_stream(out)
        run.review, run.partial, run.usage = s["review"], s["partial"], s["usage"]
        run.tool_calls, run.violations, run.rate_limited = s["tool_calls"], s["violations"], s["rate_limited"]
    else:
        run.review = parse_codex_jsonl(out) if peer == "codex" else parse_claude_json(out)
    if timed_out:
        run.reason = "timeout"
        run.error = Diagnostic("review.peer_timeout", peer=peer, timeout=timeout)
        run.review = None
        return run
    if code != 0:
        if _flags_rejected(peer, err):
            run.reason = "flags_rejected"
            run.error = Diagnostic("review.peer_flags_rejected", evidence=(err or "").strip()[:200],
                                   peer=peer, code=code)
        else:
            run.reason = "usage_limit" if run.rate_limited else "exit_nonzero"
            run.error = Diagnostic("review.peer_exit_nonzero", evidence=(err or "").strip()[:200],
                                   peer=peer, code=code)
        run.review = None
        return run
    if not run.review:
        run.reason = "usage_limit" if run.rate_limited else "parse_failed"
        run.error = Diagnostic("review.peer_parse_failed", peer=peer)
        return run
    run.ok = True
    return run
