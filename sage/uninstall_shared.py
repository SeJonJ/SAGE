"""공유 파일에서 SAGE 부분만 떼어내는 **순수 판정**.

## 왜 순수인가

`.gitignore` 와 host JSON 은 SAGE 가 만든 파일이 아니다. 프로젝트가 소유하고 SAGE 가 자기
구역만 얹어 둔 파일이라, 지울 때도 **얹은 것만** 떼야 한다. 그 판단에 파일시스템이 끼어들면
"읽어 보니 이럴 것 같다" 가 판정에 섞인다. 그래서 여기 있는 함수는 전부 bytes → 판정이고,
무엇을 읽을지 어디에 쓸지는 호출자가 정한다.

## 판정 권위는 하나다

한때 이 질문에 답하는 코드가 다섯 벌 있었다 — 계획이 등록을 세는 파서, 계획이 제거 가능성을
보는 파서, 흔적을 세는 파서, 손상을 세는 파서, 실행 층이 쓰기 직전에 도는 파서. 다섯이 같은
파일을 조금씩 다르게 읽었고, 그 어긋남이 곧 **하지 않은 일을 했다고 보고하는 자리**가 됐다.
문법이 깨진 JSON 을 한 파서는 "등록 없음" 으로 읽고 다른 파서는 아예 보지 않아서, 첫 실행이
설치 증거(manifest)까지 지우고 두 번째 실행이 손상 파일을 남긴 채 `COMPLETE` 를 냈다.

그래서 지금은 `classify_host_bytes` 하나가 답한다. 계획도 흔적도 실행도 이 함수를 부른다.

## 세 가지 상태를 접지 않는다

등록이 **있다**(`PRESENT`)와 **없다**(`ABSENT`)와 **알 수 없다**(`UNKNOWN`)는 서로 다른
사실이다. 읽기 실패·인코딩 오류·문법 오류를 "없다" 로 접으면 부재가 곧 통과가 되고, 통과는
삭제로 이어진다. 모르는 것은 모른다고 말해야 호출자가 manifest 같은 다른 증거를 찾는다.

## 손상은 고치지 않는다. 대신 **어디가** 손상인지 말한다

추측해서 고치면 사용자 내용이 사라질 수 있고, 사라진 사실이 보고되지도 않는다. 그렇다고
"구조가 손상됐습니다" 한 문장만 내면 사용자는 무엇을 고쳐야 할지 모른 채 같은 화면을 반복해서
받는다. 그래서 위치·기대 타입·실제 타입·행·열·바이트 위치·errno 를 **구조화된 사실**로 낸다.

동시에 **내용은 절대 싣지 않는다.** 설정값·command 원문·주변 JSON·OS 예외 원문은 사용자의
것이고 로그·이슈·CI 출력으로 흘러간다. 우리가 내는 것은 좌표와 타입 이름뿐이다.
"""
import copy
import errno as _errno
import json
import re

# --- 등록 상태 ---------------------------------------------------------------

PRESENT = "present"
ABSENT = "absent"
UNKNOWN = "unknown"

# install 이 얹는 두 managed block. 시작·끝 marker 가 정확히 한 쌍이어야 한다.
GITIGNORE_BLOCKS = (
    ("SAGE LOCAL PROFILE", "# >>> SAGE LOCAL PROFILE", "# <<< SAGE LOCAL PROFILE"),
    ("SAGE LOCAL STATE", "# >>> SAGE LOCAL STATE", "# <<< SAGE LOCAL STATE"),
)

# JSON pointer 에 그대로 실어도 되는 key 모양. 식별자꼴이고 길이가 묶여 있어서 경로·URL·
# command 줄·공백을 담은 문자열은 통과하지 못한다. host event 이름은 이 모양이고, 사용자가
# 넣은 임의 key 는 대개 아니다 — 아니면 좌표를 포기하고 가린다. **가려서 잃는 것은 편의고
# 실어서 잃는 것은 사용자 데이터라, 둘 중에서는 언제나 앞을 버린다.**
_SAFE_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}\Z")
REDACTED_SEGMENT = "~"


class Outcome:
    """공유 파일 하나에 대한 판정. **이 타입이 유일한 답이다.**

    `body` 는 쓸 본문 그대로다. 호출자가 다시 직렬화하면 계획이 본 것과 실행이 쓰는 것이
    달라질 수 있으므로, 직렬화까지 여기서 끝낸다.

    `damage` 는 언어를 타지 않는 dict 들이다. 화면 문장과 `--json` 이 **같은 값**을 소비해야
    둘이 다른 말을 하지 않는다.
    """

    __slots__ = ("state", "damage", "body")

    def __init__(self, state, damage=(), body=None):
        self.state = state
        self.damage = tuple(damage)
        self.body = body

    @property
    def strippable(self):
        """SAGE 것만 실제로 뺄 수 있는가. 손상이 하나라도 있으면 거짓이다."""
        return self.state == PRESENT and not self.damage and self.body is not None

    def as_json(self):
        return [dict(item) for item in self.damage]

    def __repr__(self):
        return f"Outcome({self.state!r}, {len(self.damage)} damage)"


# --- 구조화된 손상 사실 ------------------------------------------------------

def damage_type(pointer, expected, actual):
    """기대한 타입이 아니다. 위치는 JSON pointer, 타입은 JSON 타입 이름이다."""
    return {"kind": "type", "pointer": pointer, "expected": expected, "actual": actual}


def damage_syntax(line, column):
    return {"kind": "json_syntax", "line": line, "column": column}


def damage_encoding(byte_offset):
    return {"kind": "encoding", "byte_offset": byte_offset}


def damage_io(errno_name):
    """읽기 실패. **errno 이름만** 싣는다 — OS 예외 원문에는 경로와 사용자 환경이 붙는다."""
    return {"kind": "io", "errno": errno_name}


def damage_marker(code, block):
    return {"kind": "marker", "code": code, "block": block}


def damage_missing(pointer_text):
    """있어야 할 자리가 비었다. 타입 불일치와 나눠 두는 이유는 사용자가 할 일이 다르기 때문이다 —
    하나는 값을 고치는 일이고 하나는 값을 채우는 일이다."""
    return {"kind": "missing", "pointer": pointer_text}


def damage_unknown_kind(pointer_text):
    """host 가 정의하지 않은(또는 우리가 모르는) handler 종류.

    모르는 것을 정상이라고 부르면 그 항목을 우리 규칙으로 다시 쓰게 되고, 모르는 것을 손상이라고
    부르면 정상 설정이 막힌다. 둘 중에서는 **다시 쓰지 않는 쪽**을 고른다 — 막힌 것은 사용자가
    보고 풀 수 있지만 조용히 바뀐 파일은 아무도 보지 못한다.
    """
    return {"kind": "unknown_kind", "pointer": pointer_text}


def damage_unsupported_kind(pointer_text, kind):
    """host 가 이 event 에서 받지 않는 handler 종류. 종류 이름은 host 어휘라 실어도 안전하다."""
    return {"kind": "unsupported_kind", "pointer": pointer_text, "handler": kind}


def damage_unknown_event(pointer_text):
    """계약표를 옮겨 둔 host 인데 그 표에 없는 event. 무엇이 허용인지 모르므로 판정하지 않는다."""
    return {"kind": "unknown_event", "pointer": pointer_text}


def damage_duplicate_key(pointer_text):
    """같은 key 가 한 object 에 두 번 있다.

    `json.loads` 는 조용히 **뒤엣것**을 남긴다. 그러면 우리가 읽은 문서와 파일에 적힌 문서가
    다르고, 그 상태로 다시 쓰면 사용자가 적어 둔 한쪽이 사라진다. 어느 쪽이 진짜인지는 우리가
    정할 일이 아니다.
    """
    return {"kind": "json_duplicate_key", "pointer": pointer_text}


def damage_constant(name):
    """`NaN`·`Infinity` 는 표준 JSON 이 아니다. host 가 어떻게 읽을지 우리가 알 수 없다."""
    return {"kind": "json_constant", "name": name}


DAMAGE_KINDS = ("type", "missing", "unknown_kind", "unsupported_kind", "unknown_event",
                "json_syntax", "encoding", "io", "marker", "json_duplicate_key",
                "json_constant")


def errno_name(exc):
    """예외에서 errno 이름을 뽑는다. 알 수 없으면 `UNKNOWN`."""
    number = getattr(exc, "errno", None)
    if number is None:
        return "UNKNOWN"
    return _errno.errorcode.get(number, "UNKNOWN")


def io_outcome(exc):
    """읽지 못했다. 등록이 있는지 **알 수 없다** — 없다고 말하지 않는다."""
    return Outcome(UNKNOWN, [damage_io(errno_name(exc))])


def json_type(value):
    """JSON 타입 이름. 값이 아니라 타입만 낸다."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return "unknown"


def pointer(*segments):
    """안전한 JSON pointer. 위험한 key 는 좌표를 잃는 대신 가린다."""
    parts = []
    for segment in segments:
        if isinstance(segment, int):
            parts.append(str(segment))
            continue
        if _SAFE_KEY.match(segment):
            parts.append(segment.replace("~", "~0").replace("/", "~1"))
        else:
            parts.append(REDACTED_SEGMENT)
    return "".join(f"/{part}" for part in parts)


# --- host JSON ---------------------------------------------------------------

def host_body(document):
    """host JSON 을 쓸 본문으로. install 이 쓰는 모양과 같아야 한다."""
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


# host 가 정의한 handler 종류와 **그 종류가 요구하는 문자열 필드**.
#
# 한때 여기는 모든 handler 에 `command` 가 있어야 한다고 가정했다. 그건 `command` handler 하나의
# 규칙이고, 정상 `prompt` hook 을 나란히 둔 사용자는 자기 설정이 손상으로 보고되고 uninstall 이
# 영원히 `PARTIAL` 로 끝나는 것을 보게 됐다. **우리가 모르는 것을 손상이라고 부른 것**이다.
HANDLER_REQUIRED = {
    "command": ("command",),
    "http": ("url",),
    "mcp_tool": ("server", "tool"),
    "prompt": ("prompt",),
    "agent": ("prompt",),
}

# host 마다, 그리고 event 마다 **허용되는 handler 종류**.
#
# ## 왜 host 를 함께 받는가
#
# `.claude/settings.json` 과 `.codex/hooks.json` 은 서로 다른 host 의 계약이다. 한 표로 섞어 두면
# 한쪽에서만 참인 규칙이 다른 쪽 사용자를 막는다. 그래서 판정 함수가 host 를 받고, 표도 host 로
# 먼저 갈린다.
#
# ## claude 표는 공식 hooks reference 를 그대로 옮긴 것이다
#
# > "Not all events support every hook type."
#
# 한때 여기는 비어 있었다. 근거를 확인한다면서 문서 **요약**을 읽었고, 그 요약이 이 문장과 아래
# 세 목록을 통째로 놓쳤다. 원문을 직접 열어 보지 않은 채 "제한이 없다" 고 적었고, 그동안
# `SessionStart` 의 prompt hook 이 손상 없이 통과해 문서가 그대로 다시 쓰였다.
#
# 값을 손으로 고쳐 쓰지 않고 세 그룹을 그대로 둔다 — 문서가 바뀌면 이 표만 고치면 되고, 어느
# 그룹에 속하는지가 곧 근거다.
_ALL_KINDS = ("command", "http", "mcp_tool", "prompt", "agent")
_NO_LLM_KINDS = ("command", "http", "mcp_tool")
_EARLY_KINDS = ("command", "mcp_tool")

# 다섯 종류를 모두 지원하는 event.
_CLAUDE_FULL_EVENTS = (
    "PermissionDenied", "PermissionRequest", "PostToolBatch", "PostToolUse",
    "PostToolUseFailure", "PreToolUse", "Stop", "SubagentStop", "TaskCompleted",
    "TaskCreated", "TeammateIdle", "UserPromptExpansion", "UserPromptSubmit",
)

# `command`·`http`·`mcp_tool` 은 되지만 `prompt`·`agent` 는 안 되는 event.
_CLAUDE_NO_LLM_EVENTS = (
    "ConfigChange", "CwdChanged", "DirectoryAdded", "Elicitation", "ElicitationResult",
    "FileChanged", "InstructionsLoaded", "MessageDisplay", "Notification", "PostCompact",
    "PostModelSwitch", "PreCompact", "PreModelSwitch", "SessionEnd", "StopFailure",
    "SubagentStart", "WorktreeCreate", "WorktreeRemove",
)

# `command`·`mcp_tool` 만 되는 event. 세션이 서기 전에 발화하는 둘이다.
_CLAUDE_EARLY_EVENTS = ("SessionStart", "Setup")

EVENT_HANDLER_KINDS = {
    "claude": dict(
        [(event, _ALL_KINDS) for event in _CLAUDE_FULL_EVENTS]
        + [(event, _NO_LLM_KINDS) for event in _CLAUDE_NO_LLM_EVENTS]
        + [(event, _EARLY_KINDS) for event in _CLAUDE_EARLY_EVENTS]),
    # codex 의 event 별 계약은 별도 문서다. **claude 표를 복사하지 않는다** — 복사하면 한쪽에서만
    # 참인 규칙이 다른 쪽 사용자를 막고, 그 순간 이 표는 두 host 를 섞은 하나가 된다.
    "codex": {},
}


UNKNOWN_EVENT = None


def allowed_handler_kinds(host, event):
    """이 host 의 이 event 에서 허용되는 handler 종류. 모르면 `UNKNOWN_EVENT`.

    **공식 계약표를 옮겨 둔 host(지금은 claude)에서 표에 없는 event 를 만나면 "전부 허용" 으로
    추정하지 않는다.** 추정하면 문서가 늘어난 event 하나가 조용히 규칙 밖으로 빠지고, 그 자리가
    곧 우리가 이해하지 못한 문서를 다시 쓰는 통로가 된다. 모르는 것은 모른다고 말하고 보존한다.

    표가 비어 있는 host(지금은 codex)와 아예 모르는 host 는 종류 전부를 허용한다 — 그 host 의
    계약을 우리가 아직 갖고 있지 않다는 뜻이고, 갖고 있지 않은 계약을 근거로 남의 설정을 막는
    것이야말로 추정이다. codex 는 claude 표를 공유하지 않고 별도 계약으로 관리한다.
    """
    per_event = EVENT_HANDLER_KINDS.get(host)
    if per_event is None:
        return frozenset(HANDLER_REQUIRED)
    if not per_event:
        # 표가 비어 있는 host 는 아직 계약을 옮기지 않은 것이다. 있는 척하지 않는다.
        return frozenset(HANDLER_REQUIRED)
    allowed = per_event.get(event)
    if allowed is None:
        return UNKNOWN_EVENT
    return frozenset(allowed)


def handler_damage(entry, place, damage, host=None, event=None):
    """handler 하나를 그 **종류의 계약**으로 본다. 손상이면 참.

    type 을 먼저 확정하고 종류별로 갈라야 한다. 모르는 type 은 fail-closed 다 — 우리가 그
    항목을 이해하지 못한다는 뜻이고, 이해하지 못한 문서를 다시 쓰면 최종 모양을 정하는 것은
    원본이 아니라 우리 파서다. 아는 종류의 사용자 handler 는 **그대로 보존**한다.
    """
    kind = entry.get("type")
    if "type" not in entry:
        damage.append(damage_missing(f"{place}/type"))
        return True
    if not isinstance(kind, str):
        damage.append(damage_type(f"{place}/type", "string", json_type(kind)))
        return True
    required = HANDLER_REQUIRED.get(kind)
    if required is None:
        damage.append(damage_unknown_kind(f"{place}/type"))
        return True
    allowed = allowed_handler_kinds(host, event)
    if allowed is UNKNOWN_EVENT:
        # 계약표가 있는 host 인데 그 표에 없는 event 다. 무엇이 허용인지 모르므로 판정하지 않는다.
        damage.append(damage_unknown_event(f"{place}/type"))
        return True
    if kind not in allowed:
        # 종류 자체는 아는데 **이 event 에서는 host 가 받지 않는다.** 우리가 이해하지 못하는
        # 문서이므로 다시 쓰지 않는다.
        damage.append(damage_unsupported_kind(f"{place}/type", kind))
        return True
    broken = False
    for field in required:
        if field not in entry:
            damage.append(damage_missing(f"{place}/{field}"))
            broken = True
        elif not isinstance(entry[field], str):
            damage.append(damage_type(f"{place}/{field}", "string", json_type(entry[field])))
            broken = True
    return broken


def scan_host_hooks(hooks, sage_commands, host=None):
    """**1단계 — 전수 검증과 존재 확인.** `(손상 전부, 우리 command 개수)`. 아무것도 바꾸지 않는다.

    끝까지 훑는 것이 이 함수의 전부다. 한때 여기는 손상된 블록을 만나면 그 event 의 나머지를
    `break` 로 버렸고, 그래서 **손상 뒤에 있는 우리 등록이 보이지 않았다.** 안 보이면 상태가
    `UNKNOWN` 이 되고, `UNKNOWN` 은 manifest 증거가 없으면 잔재로 세지 않는다 — 우리가 남긴
    등록이 우리 눈에만 안 보이는 채로 조용히 넘어간다.

    hooks 배열 안의 비객체 항목도 손상이다. 예전에는 그것을 그냥 "우리 것이 아닌 항목" 으로
    보고 통과시켜 파일을 다시 썼다. 우리가 이해하지 못하는 모양을 **읽어서 다시 직렬화하는
    것**은 보존이 아니다 — 그 순간 파일의 최종 모양을 정하는 것은 원본이 아니라 우리 파서다.
    """
    damage = []
    present = 0
    for event in sorted(hooks):
        blocks = hooks[event]
        base = pointer("hooks", event)
        if not isinstance(blocks, list):
            damage.append(damage_type(base, "array", json_type(blocks)))
            continue
        for index, block in enumerate(blocks):
            spot = f"{base}/{index}"
            if not isinstance(block, dict):
                damage.append(damage_type(spot, "object", json_type(block)))
                continue
            entries = block.get("hooks")
            if not isinstance(entries, list):
                damage.append(damage_type(f"{spot}/hooks", "array", json_type(entries)))
                continue
            if "matcher" in block and not isinstance(block["matcher"], str):
                # matcher 는 어떤 event 에서는 아예 없다. 없는 것은 정상이고, **있는데 문자열이
                # 아닌 것**은 우리가 이해하지 못하는 모양이다.
                damage.append(damage_type(f"{spot}/matcher", "string",
                                          json_type(block["matcher"])))
            for position, entry in enumerate(entries):
                place = f"{spot}/hooks/{position}"
                if not isinstance(entry, dict):
                    damage.append(damage_type(place, "object", json_type(entry)))
                    continue
                broken_entry = handler_damage(entry, place, damage, host, event)
                if broken_entry:
                    continue
                # **소유권 비교는 `command` handler 에만 적용된다.** prompt·agent handler 도
                # `command` 라는 이름의 property 를 가질 수 있고, 그 값이 우연히 우리 command 와
                # 같다고 해서 그 항목이 우리 것이 되지는 않는다. type 을 먼저 보지 않으면
                # 남의 hook 을 우리 것으로 세고, 세는 순간 지울 근거가 생긴다.
                if entry["type"] == "command" and entry["command"] in sage_commands:
                    present += 1
    return damage, present


def _project_clean_hooks(document, sage_commands):
    """**2단계 — 깨끗한 문서에서 우리 것만 뺀다.**

    1단계가 손상 0 을 확인한 뒤에만 불린다. 그래서 여기서는 타입을 다시 묻지 않는다 — 물어야
    한다면 그건 1단계가 놓쳤다는 뜻이고, 그 경우 고칠 자리는 여기가 아니라 저기다. 검증과
    투영을 한 반복문에서 같이 하면 "검사하면서 고치는" 코드가 되고, 그러면 손상을 발견한
    시점에 이미 절반은 바뀌어 있다.
    """
    events = document["hooks"]
    for event in sorted(events):
        kept_blocks = []
        for block in events[event]:
            entries = block["hooks"]
            # 스캔이 센 것과 **글자 하나까지 같은 조건**이어야 한다. 조건이 갈라지면 계획이
            # 말한 것과 실제로 빠지는 것이 달라진다.
            kept = [entry for entry in entries
                    if not (entry["type"] == "command"
                            and entry["command"] in sage_commands)]
            if kept:
                kept_blocks.append(dict(block, hooks=kept))
            elif not entries:
                # 원래 비어 있던 블록은 우리 것이 아니다. 그대로 둔다.
                kept_blocks.append(block)
        if kept_blocks:
            events[event] = kept_blocks
        else:
            del events[event]
    if not events:
        # `hooks` 가 비면 key 자체를 지운다. 빈 dict 를 남기면 다음 install 이 "등록이 있었다"
        # 와 "없었다" 를 구분하지 못한다.
        del document["hooks"]


def classify_host_document(document, sage_commands, host=None):
    """이미 파싱된 host 문서 하나의 판정.

    한 자리가 이상하다고 즉시 포기하지 않는다. 문서 전체를 훑어서 **우리 command 가 실제로
    보이는지**까지 확인한 뒤에야 상태를 정한다 — 보이면 `PRESENT`(손상이라 못 뺀다), 안 보이고
    이상한 자리가 있으면 `UNKNOWN`(있는지 없는지 모른다)이다. 이 구별이 있어야 호출자가
    "우리 것이 남았다" 와 "볼 수 없었다" 에 다르게 대응할 수 있다.

    단계가 둘로 나뉜 것이 요점이다. 손상이 하나라도 있으면 2단계에 **닿지 않으므로**, 손상된
    문서가 우리 손으로 다시 쓰이는 경로 자체가 없다.
    """
    if not isinstance(document, dict):
        return Outcome(UNKNOWN, [damage_type("", "object", json_type(document))])
    if "hooks" not in document:
        # key 자체가 없다. 문서는 멀쩡하고 등록은 없다 — 이건 아는 사실이다.
        return Outcome(ABSENT)
    hooks = document["hooks"]
    if not isinstance(hooks, dict):
        return Outcome(UNKNOWN, [damage_type(pointer("hooks"), "object", json_type(hooks))])

    damage, present = scan_host_hooks(hooks, sage_commands, host)
    if damage:
        # 손상이 있으면 어떤 경우에도 쓰지 않는다. 상태만 최대한 정확히 말한다.
        return Outcome(PRESENT if present else UNKNOWN, damage)
    if not present:
        return Outcome(ABSENT)
    result = copy.deepcopy(document)
    _project_clean_hooks(result, sage_commands)
    return Outcome(PRESENT, (), host_body(result))


class _DuplicateKey(ValueError):
    def __init__(self, key):
        super().__init__(key)
        self.key = key


class _NonStandardConstant(ValueError):
    def __init__(self, name):
        super().__init__(name)
        self.name = name


def _reject_duplicate_keys(pairs):
    """object 하나에 같은 key 가 두 번 나오면 멈춘다.

    `json.loads` 의 기본 동작은 조용히 뒤엣것을 남기는 것이다. 그 문서를 우리가 다시 쓰면
    사용자가 적어 둔 한쪽이 사라지고, 사라졌다는 사실도 보고되지 않는다.
    """
    seen = set()
    for key, _value in pairs:
        if key in seen:
            raise _DuplicateKey(key)
        seen.add(key)
    return dict(pairs)


def _reject_constant(name):
    raise _NonStandardConstant(name)


def parse_host_json(text):
    """host JSON 하나를 **fail-closed** 로 읽는다. 손상이면 `Outcome`, 아니면 문서를 돌려준다.

    표준 JSON 이 아닌 입력을 관대하게 읽어 주면, 우리가 읽은 문서와 host 가 읽는 문서가 다를 수
    있다. 지우는 명령에서 그 차이는 곧 "지운다고 말한 것과 지운 것이 다르다" 가 된다.
    """
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys,
                          parse_constant=_reject_constant)
    except _DuplicateKey as exc:
        # 좌표는 key 이름 하나뿐이다 — 중첩 위치는 hook 이 알지 못한다. 부분 좌표라도 사용자가
        # 찾을 수 있는 이름이고, 위험한 key 는 여기서도 가린다.
        return Outcome(UNKNOWN, [damage_duplicate_key(pointer(exc.key))])
    except _NonStandardConstant as exc:
        return Outcome(UNKNOWN, [damage_constant(exc.name)])
    except json.JSONDecodeError as exc:
        return Outcome(UNKNOWN, [damage_syntax(exc.lineno, exc.colno)])
    except ValueError:
        return Outcome(UNKNOWN, [damage_syntax(None, None)])


def classify_host_bytes(raw, sage_commands, host=None):
    """host 파일 bytes 하나의 판정. **모든 호출자의 유일한 입구다.**"""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return Outcome(UNKNOWN, [damage_encoding(exc.start)])
    document = parse_host_json(text)
    if isinstance(document, Outcome):
        return document
    return classify_host_document(document, sage_commands, host)


# --- .gitignore --------------------------------------------------------------

def _all_indexes(text, needle):
    found = []
    cursor = text.find(needle)
    while cursor != -1:
        found.append(cursor)
        cursor = text.find(needle, cursor + 1)
    return found


def _block_span(text, start_marker, end_marker):
    """(시작, 끝) 인덱스, `None`, 또는 손상 dict. marker 가 정확히 한 쌍일 때만 성공한다."""
    starts = _all_indexes(text, start_marker)
    ends = _all_indexes(text, end_marker)
    if not starts and not ends:
        return None
    if len(starts) != 1 or len(ends) != 1:
        # 중복은 install 이 만들 수 없는 모양이다. 손으로 편집됐다는 뜻이고, 어느 쪽이 진짜
        # 관리 구역인지 알 수 없다.
        return "gitignore_marker_duplicate"
    if ends[0] < starts[0]:
        return "gitignore_marker_reversed"
    return starts[0], ends[0] + len(end_marker)


def classify_gitignore_text(text):
    """SAGE managed block 둘만 제거한 본문, 또는 손상 판정.

    한쪽 marker 만 있는 경우도 손상이다 — install 은 언제나 쌍으로 쓰므로, 한쪽만 남은 것은
    누군가 반쯤 지웠다는 뜻이다. 나머지 한쪽을 우리가 추측해서 지우면 그 아래 사용자 규칙이
    함께 날아간다. marker 가 보였다는 사실 자체는 우리 구역이 **있다**는 증거이므로 상태는
    `PRESENT` 이고, 다만 손상이라 뺄 수 없다.
    """
    for label, start_marker, end_marker in GITIGNORE_BLOCKS:
        opened = len(_all_indexes(text, start_marker))
        closed = len(_all_indexes(text, end_marker))
        if bool(opened) != bool(closed):
            return Outcome(PRESENT, [damage_marker("gitignore_marker_unpaired", label)])

    result = text
    removed = 0
    for label, start_marker, end_marker in GITIGNORE_BLOCKS:
        span = _block_span(result, start_marker, end_marker)
        if span is None:
            continue
        if isinstance(span, str):
            return Outcome(PRESENT, [damage_marker(span, label)])
        start, end = span
        # **이음매만 다룬다.** install 은 `<앞 내용>` + 빈 줄 하나 + `<블록>\n` 을 썼으므로,
        # 그 셋만 정확히 되돌린다.
        before, after = result[:start], result[end:]
        if after.startswith("\n"):
            after = after[1:]            # 블록을 끝낸 개행 — 우리 것이다
        if before.endswith("\n\n"):
            before = before[:-1]         # install 이 넣은 빈 줄 하나 — 역시 우리 것이다
        result = before + after
        removed += 1

    if not removed:
        return Outcome(ABSENT)

    # 파일 전체를 정규화하지 않는다. 연속 빈 줄을 뭉치거나 앞뒤 개행을 다듬으면 우리가 쓰지
    # 않은 줄까지 바뀌고, 사용자는 제거와 무관한 diff 를 받는다. 의미가 보존되는 것과 바이트를
    # 건드리지 않는 것은 다른 약속이고, 공유 파일에서는 뒤엣것을 지켜야 한다.
    return Outcome(PRESENT, (), result)


def classify_gitignore_bytes(raw):
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return Outcome(UNKNOWN, [damage_encoding(exc.start)])
    return classify_gitignore_text(text)


# --- 소유권 근거 -------------------------------------------------------------

def canonical_hook_commands(hook_ids, command_template):
    """CORE hook id → 등록 command 문자열 집합.

    소유권 근거는 이름이 아니라 **command 문자열**이다. 사용자가 같은 event 에 자기 hook 을
    등록할 수 있으므로, 우리가 쓴 것과 글자 하나까지 같은 항목만 우리 것이다.
    """
    return {command_template(hook_id) for hook_id in hook_ids}
