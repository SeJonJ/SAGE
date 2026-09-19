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
import threading
import time

from sage.diagnostics import Diagnostic

# 통제 플래그를 실측으로 확인한 최소 버전. 이보다 낮다고 **확인된** 경우에만 통제 없이 실행한다.
# 버전을 못 읽으면 통제를 건다 — 모르는 플래그면 peer 가 명시적으로 거부하므로(`peer_flags_rejected`)
# 조용히 통제 없이 도는 경로가 생기지 않는다.
MIN_CONTROLLED_VERSION = {"claude": (2, 1, 275), "codex": (0, 155, 1)}

# 통제가 **불가능하게 만든** 행동. 관측되면 리뷰 내용과 무관하게 통제가 실패한 것이다.
# claude: `--restricted` 가 Bash 계열을, `--disallowedTools` 가 하위 에이전트를 없앤다.
_CLAUDE_FORBIDDEN_TOOLS = frozenset({"Bash", "BashOutput", "KillShell", "Agent", "Task"})

# codex 는 셸이 유일한 도구라 테스트·빌드 실행을 옵션으로 막을 수 없다. 사후에 명령을 분류해 경고한다.
_BUILD_OR_TEST = re.compile(
    r"\b(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?(?:test|build)\b|\bgradlew?\b|\bmvn\b|\bpytest\b"
    r"|\bpython\d*(?:\.\d+)?\s+-m\s+(?:pytest|unittest)\b|\bgo\s+(?:test|build)\b"
    r"|\bcargo\s+(?:test|build)\b|\bmake\b|run-all\.sh")

# 리뷰어가 따라야 할 탐색·출력 계약. 모든 프로젝트에서 같으므로 패킷 작성자(호스트 AI)에게 맡기지
# 않고 여기서 붙인다 — 빠지거나 바뀌어 쓰일 여지를 없앤다.
REVIEW_CONTRACT = """\
# SAGE reviewer contract (prepended by `sage cross-check` — do not ignore)

Repository root (read files by absolute path under it): {root}
Your working directory is an empty scratch directory on purpose.

## Exploration budget
- Judge from this packet first. Draft your verdict before reading any file.
- Then read only what a specific claim needs: files named in the packet's context map and
  their direct callers/callees. Use your search tool and ranged reads (at most ~150 lines per
  read) — whichever search/read tools you actually have.
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
                 "violations", "warnings", "controls", "wall_s", "rate_limited")

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
        # 통제로 막을 수 없는 peer 에서 관측된 금지 행동(codex 의 하위 에이전트·테스트 실행). 강등하지 않고 드러낸다.
        self.warnings = []
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
        if u.get("measured"):
            parts.append(f"measured={u['measured']}")
        return " ".join(parts)

    def combined_with(self, other):
        """두 실행(실패한 peer + 폴백)의 사용량 합을 담은 PeerRun. 한쪽이라도 모르면 합도 모른다 —
        알려진 쪽만 적으면 예산 게이트가 실제보다 적게 읽는다."""
        total = PeerRun(self.peer, controls=self.controls)
        if not self.usage or not other.usage:
            return total
        usage = {}
        for key in ("new_input", "cached_input", "output", "turns", "cost_usd"):
            values = [r.usage.get(key) for r in (self, other)]
            if all(v is not None for v in values):
                usage[key] = values[0] + values[1]
        if any(r.usage.get("measured") for r in (self, other)):
            usage["measured"] = "partial"
        total.usage = usage
        if self.tool_calls is not None and other.tool_calls is not None:
            total.tool_calls = self.tool_calls + other.tool_calls
        if self.wall_s is not None and other.wall_s is not None:
            total.wall_s = self.wall_s + other.wall_s
        return total


# ---- 버전 ----

def parse_version(text):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def cli_version(peer):
    """peer CLI 버전 튜플. 못 읽으면 None."""
    try:
        r = subprocess.run([peer, "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
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
        if controlled:
            # 모르는 -c 키는 조용히 무시된다 — --strict-config 로 키 오타를 실패로 드러낸다(실측).
            # --ignore-user-config 는 쓰지 않는다: 사용자가 고른 리뷰 모델까지 codex 기본값으로 조용히
            # 바뀐다(실측). 비용 요소만 하나씩 끈다. 하위 에이전트는 0.155.1 에서 어떤 설정으로도 막히지
            # 않아(실측·codex 확인) 여기서 끄지 못하고 사후 감사로 드러낸다.
            cmd += ["--skip-git-repo-check", "--strict-config",
                    "-c", "project_doc_max_bytes=0",
                    "-c", "tool_output_token_limit=4000",
                    "-c", 'web_search="disabled"',
                    "-c", "mcp_servers={}",
                    "--disable", "multi_agent", "--disable", "multi_agent_v2",
                    "--disable", "memories", "--disable", "hooks"]
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
                   # 빈 값을 별도 인자("")로 넘기면 Windows 의 .cmd shim 이 떨어뜨려 다음 플래그를
                   # 값으로 삼킨다. 한 토큰으로 붙여 넘긴다(실측: 거부 없이 설정 미주입).
                   "--setting-sources=",
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


def codex_rate_limited(text):
    """codex --json 의 실패 이벤트가 사용 한도 때문인지. 실측: 한도 소진 시 stdout 에
    `{"type":"turn.failed","error":{"message":"You've hit your usage limit..."}}` 가 오고 exit 1, stderr 는 비어 있다."""
    for o in _json_lines(text):
        if o.get("type") in ("turn.failed", "error"):
            message = (o.get("error") or {}).get("message") if o.get("type") == "turn.failed" else o.get("message")
            if re.search(r"(?i)usage limit", str(message or "")):
                return True
    return False


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
    per_message = {}                    # message.id → usage. 한 메시지가 블록마다 이벤트로 나뉘어 반복된다
    result = None
    rate_limited = False
    for o in _json_lines(text):
        t = o.get("type")
        if t == "assistant":
            message = o.get("message") or {}
            if isinstance(message.get("usage"), dict):
                per_message[message.get("id") or len(per_message)] = message["usage"]
            for c in message.get("content") or []:
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
            usage = _claude_usage(u)
            usage.update(turns=result.get("num_turns"), cost_usd=result.get("total_cost_usd"))
        spawned = ((result.get("subagent_stats") or {}).get("spawned") or 0)
        if spawned:
            violations.append(f"subagent_spawned:{spawned}")
        if result.get("is_error") and re.search(r"(?i)usage limit|rate limit", str(result.get("result") or "")):
            rate_limited = True
    if usage is None and per_message:
        # 끊긴 실행에는 result 가 없다. 제한 시간에 걸린 실행이 가장 많이 쓴 실행이라, 여기서 unknown 을
        # 내면 예산 게이트가 정작 막아야 할 라운드를 못 본다. 메시지별 usage 합으로 대신하되, 출력 토큰은
        # 스트리밍 중간값이라 실제보다 작을 수 있어 `measured=partial` 로 표시한다.
        usage = {"new_input": 0, "cached_input": 0, "output": 0}
        for u in per_message.values():
            for key, value in _claude_usage(u).items():
                usage[key] += value
        usage["measured"] = "partial"
    return {"review": review, "partial": "\n\n".join(texts) or None, "usage": usage,
            "tool_calls": tool_calls, "violations": violations, "rate_limited": rate_limited}


def summarize_codex_stream(text):
    """codex exec --json → dict(review, partial, usage, tool_calls, warnings, thread_id, rate_limited)."""
    texts, commands, warnings = [], [], []
    usage, thread_id, collab = None, None, 0
    for o in _json_lines(text):
        t = o.get("type")
        it = o.get("item") or {}
        if t == "thread.started":
            thread_id = o.get("thread_id")
        elif t == "item.completed" and it.get("type") == "agent_message" and it.get("text"):
            texts.append(it["text"])
        elif t == "item.completed" and it.get("type") == "command_execution":
            commands.append(str(it.get("command") or ""))
        elif t == "item.started" and it.get("type") == "collab_tool_call":
            collab += 1
        elif t == "turn.completed" and isinstance(o.get("usage"), dict):
            # 실행 1회에 보통 한 번, 값은 그 턴의 모델 호출 누적(실측: 호출별 기록 합과 일치).
            usage = _add_usage(usage, _codex_usage(o["usage"]))
    builds = [c for c in commands if _BUILD_OR_TEST.search(c)]
    if builds:
        warnings.append(f"build_or_test_run:{len(builds)}")
    if collab:
        warnings.append(f"subagent_call:{collab}")
    return {"review": texts[-1] if texts else None, "partial": "\n\n".join(texts) or None,
            "usage": usage, "tool_calls": len(commands) + collab, "warnings": warnings,
            "collab_calls": collab, "thread_id": thread_id, "rate_limited": codex_rate_limited(text)}


def _codex_usage(u):
    # codex 의 input_tokens 는 캐시 적중분을 포함한다 — 캐시 밖 입력만 new_input 으로.
    total = u.get("input_tokens") or 0
    cached = u.get("cached_input_tokens") or 0
    return {"new_input": max(0, total - cached), "cached_input": cached,
            "output": u.get("output_tokens") or 0}


def _add_usage(a, b):
    if a is None:
        return dict(b)
    return {k: (a.get(k) or 0) + (b.get(k) or 0) for k in ("new_input", "cached_input", "output")}


def codex_sessions_dir():
    return os.path.join(os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex"), "sessions")


def _session_meta(path):
    try:
        with open(path, encoding="utf-8") as f:
            first = json.loads(f.readline() or "{}")
    except Exception:
        return {}
    payload = first.get("payload") if first.get("type") == "session_meta" else None
    return payload if isinstance(payload, dict) else {}


def _rollout_usage(path):
    """rollout 의 모델 호출별 token_usage_record 합(끊긴 실행도 호출 단위로 남는다)."""
    usage = None
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if '"token_usage_record"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                u = (o.get("payload") or {}).get("usage")
                if isinstance(u, dict):
                    usage = _add_usage(usage, _codex_usage(u))
    except Exception:
        return None
    return usage


def codex_session_family(thread_id, since, sessions_dir=None):
    """(부모 rollout 경로|None, 자손 rollout 경로 목록). 자손은 session_meta.parent_thread_id 를 재귀로 따라간다.

    하위 에이전트 생성은 stdout 에 이벤트가 안 남는 경우가 있어(실측) 세션 파일이 확실한 양성 증거다.
    파일이 없다고 생성되지 않았다는 증거는 아니다(codex 확인). since(epoch) 이후 수정된 파일만 본다.
    """
    root = sessions_dir or codex_sessions_dir()
    if not thread_id or not os.path.isdir(root):
        return None, []
    # 세션 디렉터리는 날짜별(YYYY/MM/DD)로 쌓인다. 전부 훑지 않고 실행 기간의 날짜 폴더만 본다
    # (지역 시각과 UTC 둘 다 — 자정 전후 실행도 놓치지 않게).
    days = set()
    t = since - 86400
    while t <= time.time() + 86400:
        for stamp in (time.localtime(t), time.gmtime(t)):
            days.add(os.path.join(root, time.strftime("%Y", stamp), time.strftime("%m", stamp),
                                  time.strftime("%d", stamp)))
        t += 43200
    candidates = []
    for day in sorted(d for d in days if os.path.isdir(d)):
        for name in os.listdir(day):
            if not (name.startswith("rollout-") and name.endswith(".jsonl")):
                continue
            path = os.path.join(day, name)
            try:
                if os.path.getmtime(path) < since - 5:
                    continue
            except OSError:
                continue
            candidates.append(path)
    parent = next((p for p in candidates if thread_id in os.path.basename(p)), None)
    metas = {p: _session_meta(p) for p in candidates}
    family, frontier = [], {thread_id}
    while frontier:
        found = [p for p, m in metas.items()
                 if m.get("parent_thread_id") in frontier and p not in family]
        family.extend(found)
        frontier = {metas[p].get("id") for p in found if metas[p].get("id")}
    return parent, family


def _claude_usage(u):
    # new_input = 캐시 밖 입력(신규 + 캐시 기록). 캐시 읽기는 따로 — 제공자 한도가 캐시를 어떻게
    # 세는지 모르므로 두 해석 모두에서 판단할 수 있게 나눠 둔다.
    return {"new_input": (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0),
            "cached_input": u.get("cache_read_input_tokens") or 0,
            "output": u.get("output_tokens") or 0}


# ---- 프로세스 ----

def _popen_kwargs():
    # peer 가 띄운 셸 명령(npm test 등)까지 함께 끝내려면 peer 를 새 프로세스 그룹의 리더로 띄워야
    # 한다. peer 만 죽이면 자식은 고아로 남아 계속 돈다(실측: codex 강제 종료 후 `sleep 60` 생존).
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _descendants(pid):
    """pid 의 자손 pid 목록(POSIX, ps 기반). codex 는 셸 명령마다 새 세션을 만들어(실측) 프로세스 그룹
    종료로는 닿지 않는다 — 부모가 살아 있을 때 ppid 체인으로 모아야 한다."""
    try:
        out = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True,
                             timeout=10).stdout
    except Exception:
        return []
    children = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    found, stack = [], [pid]
    while stack:
        for child in children.get(stack.pop(), []):
            found.append(child)
            stack.append(child)
    return found


def _kill_tree(proc, seen=()):
    if os.name != "nt":
        # 부모가 끝나면 자손은 init 으로 넘어가 ppid 체인이 끊긴다 — 도는 동안 모아 둔 목록을 함께 쓴다.
        for pid in set(_descendants(proc.pid)) | set(seen):
            for kill in (lambda: os.killpg(os.getpgid(pid), signal.SIGKILL),
                         lambda: os.kill(pid, signal.SIGKILL)):
                try:
                    kill()
                except Exception:
                    pass
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


def _reader(stream, sink):
    # 바이트로 읽고 끝에서 한 번에 디코딩한다. 텍스트 스트림의 read(n) 은 n 글자가 찰 때까지 붙잡고
    # 있어서, 파이프를 쥔 프로세스가 남으면 그때까지 받은 출력이 sink 에 들어오지 못한다.
    fd = stream.fileno()
    try:
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            sink.append(chunk)
    except Exception:
        pass


def _writer(stream, data):
    # 프롬프트 쓰기도 별도 스레드다. 패킷은 파이프 버퍼(64KB)보다 크므로, peer 가 stdin 을 읽기 전에
    # 멈추면 주 스레드의 write 가 끝나지 않고 timeout 도 시작되지 않는다.
    try:
        stream.write(data)
    except (BrokenPipeError, OSError):
        pass                            # peer 가 입력을 다 읽기 전에 끝났다 — 종료 코드가 말해준다
    finally:
        try:
            stream.close()
        except Exception:
            pass


def run_process(cmd, prompt, timeout, env=None, cwd=None):
    """(returncode|None, stdout, stderr, timed_out, wall_s). timeout 이면 그때까지의 출력을 돌려준다.

    출력은 별도 스레드가 모은다. `communicate` 는 파이프 EOF 까지 기다리는데, peer 가 백그라운드로 띄운
    명령이 파이프를 쥐고 있으면 peer 가 끝나도 EOF 가 오지 않아 끝난 리뷰가 timeout 으로 보고된다.
    그래서 peer 프로세스의 종료만 기다리고, 어떤 경로로 나가든 프로세스 그룹을 정리한다.
    """
    # 프롬프트는 stdin 으로 넘긴다. positional arg 로 넘기면 큰 diff 가 OS ARG_MAX 를 넘겨 대형 리뷰가
    # 전부 실패한다. encoding 을 명시하지 않으면 locale 인코딩을 써서 C-locale 호스트에서 한글 패킷이
    # UnicodeEncodeError 로 매번 실패한다(패킷 파일도 utf-8 로 읽으므로 대칭).
    start = time.monotonic()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, env=env, cwd=cwd, **_popen_kwargs())
    out, err = [], []
    threads = [threading.Thread(target=_reader, args=(proc.stdout, out), daemon=True),
               threading.Thread(target=_reader, args=(proc.stderr, err), daemon=True),
               threading.Thread(target=_writer, args=(proc.stdin, prompt.encode("utf-8")), daemon=True)]
    for t in threads:
        t.start()
    timed_out = False
    seen = set()
    try:
        deadline = time.monotonic() + timeout
        while True:
            # 자손을 도는 동안 표본으로 모은다. 끝나고 나서 찾으면, 새 세션으로 띄워져 부모가 바뀐
            # 자식(codex 의 셸 명령이 그렇다)은 이미 ppid 체인에서 사라진 뒤다.
            if os.name != "nt":
                seen.update(_descendants(proc.pid))
            try:
                proc.wait(timeout=min(2, max(0.05, deadline - time.monotonic())))
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
    finally:
        # 성공·timeout·예외(KeyboardInterrupt 포함) 어느 경로든 peer 가 남긴 자식까지 끝낸다.
        _kill_tree(proc, seen)
        for t in threads:
            t.join(timeout=10)

    def text(chunks):
        return b"".join(chunks).decode("utf-8", errors="replace")
    return (None if timed_out else proc.returncode, text(out), text(err), timed_out,
            time.monotonic() - start)


def _flags_rejected(peer, stderr):
    s = stderr or ""
    if peer == "claude":
        return "unknown option" in s or "error: option" in s
    return ("unexpected argument" in s or "Unknown feature flag" in s
            or "unknown configuration field" in s)


def _account_codex_sessions(run, thread_id, started_at, collab_calls=0):
    """세션 파일로 사용량·하위 에이전트를 보정한다. 끊긴 실행은 turn.completed 가 없어 부모 rollout 의
    호출별 기록을 쓰고, 하위 에이전트의 사용량은 부모 usage 에 없으므로(codex 확인) 더한다."""
    parent, family = codex_session_family(thread_id, started_at)
    if run.usage is None and parent:
        measured = _rollout_usage(parent)
        if measured:
            run.usage = dict(measured, measured="partial")
    if collab_calls and not family and run.usage is not None:
        # 하위 에이전트를 부른 흔적은 있는데 그 세션 기록을 못 찾았다 — 자식 사용량이 빠진 값이다.
        run.usage = dict(run.usage, measured="partial")
        run.warnings.append("subagent_usage_unmeasured")
    if family:
        run.warnings.append(f"subagent_spawned:{len(family)}")
        for path in family:
            child = _rollout_usage(path)
            if child and run.usage is not None:
                merged = _add_usage(run.usage, child)
                if run.usage.get("measured"):
                    merged["measured"] = run.usage["measured"]
                run.usage = merged


def run_peer(peer, prompt, timeout, effort=None, model=None, root=None, env=None):
    """peer 리뷰 1회 → PeerRun."""
    if not shutil.which(peer):
        return PeerRun(peer, error=Diagnostic("review.peer_cli_missing", peer=peer),
                       reason="cli_missing")
    # 통제 조합이 없는 peer 는 버전을 물을 이유가 없다 — 리뷰 시작만 늦춘다.
    version = cli_version(peer) if peer in MIN_CONTROLLED_VERSION else None
    controlled = controls_supported(peer, version)
    cmd = peer_command(peer, effort, model, root=root, controlled=controlled)
    if controlled:
        prompt = REVIEW_CONTRACT.format(root=root or os.getcwd(), max_lookups=12) + prompt
    workdir = tempfile.mkdtemp(prefix="sage-peer-") if controlled else None
    started_at = time.time()
    try:
        code, out, err, timed_out, wall = run_process(cmd, prompt, timeout, env=env, cwd=workdir)
    except Exception as e:
        return PeerRun(peer, error=Diagnostic("review.peer_exception", evidence=str(e), peer=peer),
                       reason="exception", controls="full" if controlled else "none")
    finally:
        if workdir:
            shutil.rmtree(workdir, ignore_errors=True)
    run = PeerRun(peer, controls="full" if controlled else "none", wall_s=wall)
    if peer == "codex" and controlled:
        c = summarize_codex_stream(out)
        run.review, run.partial, run.usage = c["review"], c["partial"], c["usage"]
        run.tool_calls, run.warnings, run.rate_limited = c["tool_calls"], c["warnings"], c["rate_limited"]
        _account_codex_sessions(run, c["thread_id"], started_at, c["collab_calls"])
    elif peer == "claude" and controlled:
        s = summarize_claude_stream(out)
        run.review, run.partial, run.usage = s["review"], s["partial"], s["usage"]
        run.tool_calls, run.violations, run.rate_limited = s["tool_calls"], s["violations"], s["rate_limited"]
    else:
        run.review = parse_codex_jsonl(out) if peer == "codex" else parse_claude_json(out)
        if peer == "codex":
            run.rate_limited = codex_rate_limited(out)
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
            # 이벤트를 하나도 내지 못하고 끝났다면 리뷰를 시작도 못 한 것이다(인자·설정·인증 문제).
            # 거부 문구가 버전마다 달라도 여기서 걸러, 매 라운드 조용히 폴백으로 흘러가지 않게 한다.
            started = any(True for _ in _json_lines(out))
            run.reason = ("usage_limit" if run.rate_limited
                          else "exit_nonzero" if started else "startup_failed")
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
