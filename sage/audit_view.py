"""통합 감사 조회의 순수부 — registry·envelope·allowlist·redaction·정렬.

## 이 모듈이 파일을 모르는 이유

조회 기능의 판정 대부분은 "이 레코드에서 무엇을 내보내도 되는가" 이고, 그 질문은 디스크와
아무 상관이 없다. 파일 읽기와 섞어 두면 allowlist 하나를 검사하려고 임시 디렉터리와 fixture
파일을 만들어야 하고, 그러면 전수로 돌려야 할 표가 몇 개만 표본으로 검사된다.

그래서 여기에는 부작용이 없다. `os` 도 import 하지 않는다 — 경로 판정조차 문자열 규칙으로
한다. 실제 파일 접근은 `sage.audit_sources` 가 전부 소유한다.

## 왜 allowlist 인가

`data` 에 실을 key 를 **통과 목록**으로 고정한다. 금지 목록으로 만들면 새 필드가 생길 때마다
아무도 손대지 않아도 조용히 새어 나가고, 새어 나간 뒤에야 알게 된다. 통과 목록이면 새 필드는
기본적으로 나오지 않고, 필요하면 이 표에 한 줄을 더해 **명시적으로** 나온다.

## 왜 redaction 이 두 겹인가

1층은 경로 필드를 검증한다. `note_path` 처럼 경로가 오기로 된 자리가 절대경로거나 저장소를
벗어나면 값을 숨긴다.

2층은 envelope **전체**의 모든 문자열을 본다. allowlist 에는 `reason`·`scope`·
`remaining_evidence`·`note` 같은 자유 문자열이 있고 사용자가 거기에 절대경로를 직접 적을 수
있다. 특히 retro 의 `reason` 은 이 source 를 로컬로 분류하게 만든 vault 경로와 같은 자리다.

훑는 범위가 `data` 가 아니라 envelope 전체인 것이 중요하다. `run_id`·`cycle_stem`·
`occurred_at`·`event` 도 레코드에서 그대로 온 값이고, 감사 파일을 쓸 수 있는 쪽이면 무엇이든
넣을 수 있다. 어느 key 를 훑을지 고르기 시작하면 새 key 가 생길 때마다 다시 샌다 — 2층은
필드 이름을 보지 않는다.
"""
from __future__ import annotations

import re

SCHEMA_VERSION = 1

# 치환 표기는 고정 토큰 하나다. 앞부분을 남기고 자르지 않는 이유는 남긴 조각으로 경로를
# 복원할 수 있고 어디서 자를지 정하는 규칙 자체가 새 누출 표면이기 때문이다. 완전히 지우지
# 않는 이유는 그러면 "값이 있었다" 와 "원래 없었다" 가 구분되지 않아 조용한 데이터 손실처럼
# 보이기 때문이다.
REDACTED = "<redacted-path>"

VISIBILITY_SHARED = "shared"
VISIBILITY_LOCAL = "local"

# 무결성 보증의 종류. 이 값은 **실제로 검증되는 것** 만 말한다. 올려 말하면 조회 화면이
# 원본보다 강한 보증을 하는 것이고, 그 순간 이 기능은 가시성 개선이 아니라 거짓 보증이 된다.
METHOD_STRICT_CHAIN = "strict_chain"   # append 순 hash chain 검증
METHOD_SEMANTIC = "semantic"           # 레코드 간 의미 규칙 검증 (위변조 내성 아님)
METHOD_STRUCTURAL = "structural"       # 구조 파싱만
METHOD_NONE = "none"                   # 아무 검증도 없음

# 무결성 판정 결과.
STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
STATUS_LEGACY = "legacy"               # 보증 필드가 없는 과거 run — 실패가 아니다
STATUS_UNREADABLE = "unreadable"
STATUS_NOT_APPLICABLE = "not_applicable"   # method 가 none — 판정할 것이 없다


class Source:
    """registry 한 행. 데이터이지 코드 분기가 아니다."""

    __slots__ = ("id", "rel", "visibility", "method", "tracking_policy", "caveat")

    def __init__(self, id, rel, visibility, method, tracking_policy, caveat=None):
        self.id = id
        self.rel = rel
        self.visibility = visibility
        self.method = method
        self.tracking_policy = tracking_policy
        # 사용자에게 **항상** 보여야 하는 이 source 의 한계. catalog key 이고 없으면 None.
        self.caveat = caveat

    @property
    def local(self):
        return self.visibility == VISIBILITY_LOCAL


# source 6종. 새 source 가 생기면 코드가 아니라 이 표에 행을 더한다.
#
# `override` 의 caveat 이 비어 있지 않은 것이 이 표의 요점이다. `.sage/override.jsonl` 은
# 추적 사본이고 집행 정본은 state home 의 `grants/<root_key>.jsonl` 이다. 둘은 갈릴 수 있는데
# — revoke 는 집행을 먼저 쓰고 추적을 나중에 쓰므로 그 사이에 중단되면 집행됐지만 추적에 없는
# 상태가 남는다 — 조회는 추적본만 본다. 그 사실을 화면에서 지우면 사용자는 집행 정본을 보고
# 있다고 믿게 되고, 그게 이 기능이 만들 수 있는 가장 나쁜 오해다.
SOURCES = (
    Source("override", ".sage/override.jsonl", VISIBILITY_SHARED, METHOD_NONE,
           "tracked", caveat="audit.caveat.override_tracking_copy"),
    Source("acceptance", ".sage/acceptance-waivers.jsonl", VISIBILITY_SHARED, METHOD_SEMANTIC,
           "tracked", caveat="audit.caveat.semantic_only"),
    Source("review", ".sage/loop_audit.jsonl", VISIBILITY_SHARED, METHOD_STRICT_CHAIN,
           "tracked"),
    Source("fast", ".sage/fast_cycle.jsonl", VISIBILITY_SHARED, METHOD_STRICT_CHAIN,
           "tracked"),
    Source("retro", ".sage/retro_audit.jsonl", VISIBILITY_LOCAL, METHOD_STRUCTURAL,
           "local", caveat="audit.caveat.structural_only"),
    Source("feedback", ".sage/feedback.jsonl", VISIBILITY_LOCAL, METHOD_NONE,
           "local", caveat="audit.caveat.unverified"),
)

SOURCE_IDS = tuple(source.id for source in SOURCES)
_BY_ID = {source.id: source for source in SOURCES}
LOCAL_SOURCE_IDS = tuple(source.id for source in SOURCES if source.local)


def source_of(source_id):
    return _BY_ID.get(source_id)


# --- allowlist --------------------------------------------------------------
#
# (source, event) -> 내보내도 되는 `data` key. 여기 없는 key 는 나가지 않는다.
#
# review 의 `cfg`(profile 스냅샷 전체)와 fast 의 `profile_hash` 이후 필드들이 여기 없는 것이
# 의도다. 전자는 프로젝트 설정을 통째로 싣고, 후자는 조회로 얻을 것이 없는 내부 담보다.
_ALLOWLIST = {
    ("override", "grant"): ("grant_id", "gate", "reason", "ttl_seconds", "expires_at", "user"),
    ("override", "revoke"): ("grant_id", "gate", "reason", "user"),
    ("override", "bypass"): ("grant_id", "gate", "message_key", "files", "reason",
                             "user", "grant_user"),
    ("override", "cycle_stem_declared"): ("gate", "origin", "status", "user"),

    ("acceptance", "grant"): ("waiver_id", "acceptance_id", "reason", "scope",
                              "remaining_evidence", "confirmed_by", "ttl_seconds",
                              "expires_at", "attestation"),
    ("acceptance", "revoke"): ("waiver_id", "reason", "confirmed_by"),
    ("acceptance", "use"): ("waiver_id", "acceptance_id", "report_path"),

    ("review", "loop_open"): ("risk", "reviewer_requested", "lenses"),
    ("review", "round"): ("iteration", "found", "survived", "accepted", "arch",
                          "survived_by_severity"),
    ("review", "loop_close"): ("result", "reason", "iterations", "reviewer_actual",
                               "review_assurance", "completed_rounds",
                               "configured_max_iterations", "survived_by_severity"),

    ("fast", "fast_open"): ("entry_mode", "actual_risk_open", "fast_review_level", "reason",
                            "minimum_rounds", "lens_count", "lenses"),
    ("fast", "fast_convert"): ("entry_mode", "actual_risk_open", "fast_review_level", "reason",
                               "confirmed_by", "attestation", "current_phase",
                               "minimum_rounds", "lens_count", "lenses"),
    ("fast", "fast_review"): ("loop_run_id", "actual_risk_review", "rounds", "result"),
    ("fast", "fast_close"): ("loop_run_id", "actual_risk_final", "result", "report_path"),
    ("fast", "fast_abort"): ("reason", "stage", "actual_risk_at_abort"),

    # retro 는 통과시키는 원본 key 가 거의 없다. `note_path` 와 `digest` 는 아래 `_DERIVED` 가
    # boolean 으로 바꿔 낸다 — 이 자리에 원본을 두면 통과 목록이 곧 노출 목록이 된다.
    ("retro", "retro_check_ok"): (),
    ("retro", "retro_check_missing"): (),
    ("retro", "retro_check_skipped"): ("reason",),

    ("feedback", "feedback"): ("path", "line", "blocking", "verdict", "resolved",
                               "note", "marker_text"),
}

# 경로가 오기로 된 자리. 1층 검증 대상이며, 값이 저장소 상대경로가 아니면 숨긴다.
#
# `files` 는 목록이라 원소마다 본다. 목록이라는 이유로 검사에서 빠지면 한 원소만 절대경로여도
# 그대로 나간다.
_PATH_FIELDS = {
    ("override", "bypass"): ("files",),
    ("acceptance", "use"): ("report_path",),
    ("fast", "fast_close"): ("report_path",),
    ("feedback", "feedback"): ("path",),
}

# 원본 key 를 통과시키는 대신 **유도한** 값. 존재 여부만 답하면 되는 질문에 위치를 답하지
# 않기 위한 자리다.
#
# retro 의 `note_path` 가 여기 있는 이유는, 그 값이 저장소 상대경로로 정상이어도 vault 안의
# 개인 노트를 어디에 두는지를 그대로 드러내기 때문이다. redaction 은 이탈만 가리므로 정상
# 상대경로는 그대로 통과한다 — 가려야 할 이유가 "이탈" 이 아니라 "그 값 자체" 인 자리는
# 가리기가 아니라 **투영**으로 푼다. 조회가 답할 질문은 "노트가 있었는가" 이지
# "노트가 어디 있는가" 가 아니다.
_DERIVED = {
    ("retro", "retro_check_ok"): (
        ("state", lambda record: "ok"),
        ("vault_note_present", lambda record: bool(_text_or_none(record.get("note_path")))),
        ("digest_present", lambda record: bool(_text_or_none(record.get("digest")))),
    ),
    ("retro", "retro_check_missing"): (
        ("state", lambda record: "missing"),
        ("vault_note_present", lambda record: bool(_text_or_none(record.get("note_path")))),
    ),
    ("retro", "retro_check_skipped"): (
        ("state", lambda record: "skipped"),
    ),
}


def allowed_keys(source_id, event):
    return _ALLOWLIST.get((source_id, event))


# --- redaction 1층: 경로 필드 -----------------------------------------------

_WINDOWS_DRIVE = re.compile(r"\A[A-Za-z]:")


def safe_relpath(value):
    """저장소 상대경로로 인정되면 정규화한 값, 아니면 None.

    절대경로·drive·UNC·`~` 시작·`..` 세그먼트를 전부 거부한다. `..` 는 정규화해서 흡수하지
    않는다 — 흡수하면 `a/../../etc` 가 조용히 `../etc` 가 되고, 그건 이탈을 판정한 것이 아니라
    이탈의 흔적을 지운 것이다.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("\\", "/")
    if text.startswith("/") or text.startswith("~") or text.startswith("//"):
        return None
    if _WINDOWS_DRIVE.match(text):
        return None
    segments = [segment for segment in text.split("/") if segment not in ("", ".")]
    if not segments or any(segment == ".." for segment in segments):
        return None
    return "/".join(segments)


# --- redaction 2층: 값 기반 sanitizer ----------------------------------------
#
# 필드 이름을 보지 않고 값만 본다.
#
# 앞의 `(?<![:/\w])` 가 하는 일이 둘 있다. 하나는 `and/or`·`L2/L3` 같은 평범한 슬래시를
# 경로로 오인하지 않는 것이고, 다른 하나는 `https://host/path` 의 `//` 를 건드리지 않는 것이다.
# URL 은 파일시스템 경로 누출이 아닌데 함께 뭉개면 사용자가 자기 데이터를 잃는다.
_ABSOLUTE_PATH = re.compile(
    r"(?<![:/\w])"
    r"(?:"
    r"[A-Za-z]:[\\/][^\s\"'`,;)\]}]*"      # C:\... / C:/...
    r"|\\\\[^\s\\/][^\s\"'`,;)\]}]*"        # \\server\share
    r"|~[\\/][^\s\"'`,;)\]}]*"              # ~/...
    r"|/[^\s\"'`,;)\]}]+"                   # /abs/path
    r")")


def sanitize_text(value):
    """(치환된 문자열, 치환 건수). 경로처럼 생긴 토큰 전체를 고정 토큰으로 바꾼다."""
    if not isinstance(value, str):
        return value, 0
    replaced = _ABSOLUTE_PATH.subn(REDACTED, value)
    return replaced[0], replaced[1]


def sanitize_value(value):
    """중첩 구조 전체를 훑는다. (값, 치환 건수).

    dict 의 **key 도** 본다. 값만 보면 `{"/Users/me": 1}` 같은 모양으로 경로가 그대로 나간다.
    """
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        out, total = {}, 0
        for key, item in value.items():
            clean_key, key_hits = sanitize_text(key) if isinstance(key, str) else (key, 0)
            clean_item, item_hits = sanitize_value(item)
            out[clean_key] = clean_item
            total += key_hits + item_hits
        return out, total
    if isinstance(value, (list, tuple)):
        out, total = [], 0
        for item in value:
            clean_item, hits = sanitize_value(item)
            out.append(clean_item)
            total += hits
        return out, total
    return value, 0


# --- envelope ---------------------------------------------------------------

# 공통 필드는 좁게 고정한다. 부재는 `null` 이고 `data` 의 불필요 key 는 생략이다 — 이 비대칭을
# 명시해 두지 않으면 소비자가 "없는 key" 와 "null 인 key" 중 무엇을 봐야 하는지 추측한다.
ENVELOPE_FIELDS = ("source", "source_index", "event", "occurred_at", "epoch",
                   "run_id", "cycle_stem", "actor", "summary_code", "data")

_ACTOR_FIELDS = ("actor", "user", "confirmed_by")


def _text_or_none(value):
    return value if isinstance(value, str) and value else None


def _int_or_none(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _clean(value):
    """(정규화된 문자열 또는 None, 치환 건수). 문자열 자리 하나를 걸러서 받는다."""
    text = _text_or_none(value)
    if text is None:
        return None, 0
    return sanitize_text(text)


def envelope(source_id, index, record):
    """레코드 하나를 정규화 envelope 로. (envelope, issues).

    모르는 event 는 **버리지 않는다.** 버리면 조회가 감사보다 적게 말하게 되고, 사용자는
    그 줄이 없는 것과 안 보이는 것을 구분할 수 없다. 대신 `data` 를 비운다 — raw 를 그대로
    흘리는 경로를 두면 그것이 allowlist 의 우회로가 된다.
    """
    issues = []
    # `event` 만 미리 거르는 이유는, 이 값이 envelope 에 실리기 전에 **진단 인자**로도 나가기
    # 때문이다. 아래의 envelope 전체 sanitize 는 진단을 지나가지 않는다.
    event, meta_hits = _clean(record.get("event"))
    keys = allowed_keys(source_id, event) if event else None

    data = {}
    if keys is None:
        if event is None:
            issues.append(("audit.source.malformed", {"reason": "event_missing", "index": index}))
        else:
            issues.append(("audit.source.unknown_event", {"event": event, "index": index}))
    else:
        path_fields = _PATH_FIELDS.get((source_id, event), ())
        for key in keys:
            if key not in record:
                continue                      # 부재는 생략이다. `null` 로 채우지 않는다.
            value = record[key]
            if key in path_fields:
                value, hidden = _redact_path_field(value)
                if hidden:
                    issues.append(("audit.source.redacted",
                                   {"reason": "path_escaped", "field": key, "index": index}))
            data[key] = value
        for key, derive in _DERIVED.get((source_id, event), ()):
            data[key] = derive(record)

    actor = None
    for field in _ACTOR_FIELDS:
        actor = _text_or_none(record.get(field))
        if actor:
            break

    item = {
        "source": source_id,
        "source_index": index,
        "event": event,
        "occurred_at": _text_or_none(record.get("ts")),
        "epoch": _int_or_none(record.get("epoch")),
        "run_id": _text_or_none(record.get("run_id")),
        "cycle_stem": _text_or_none(record.get("cycle_stem")),
        "actor": actor,
        "summary_code": f"audit.event.{source_id}.{event}" if keys is not None else
                        "audit.event.unknown",
        "data": data,
    }

    # 여기가 이 층의 유일한 출구다. `data` 만 훑고 나머지를 믿는 대신 완성된 envelope 을 통째로
    # 훑는다 — 그래야 나중에 key 를 하나 더해도 그 key 가 새 누출 표면이 되지 않는다.
    # 치환은 멱등이라 이미 걸러진 `event` 를 두 번 세지 않는다.
    item, hits = sanitize_value(item)
    hits += meta_hits
    if hits:
        issues.append(("audit.source.redacted",
                       {"reason": "absolute_path_in_text", "count": hits, "index": index}))
    return item, issues


def _redact_path_field(value):
    """(값, 숨겼는가). 목록은 원소마다 본다."""
    if isinstance(value, list):
        out, hidden = [], False
        for item in value:
            safe = safe_relpath(item)
            if safe is None:
                hidden = True
                out.append(REDACTED)
            else:
                out.append(safe)
        return out, hidden
    safe = safe_relpath(value)
    return (REDACTED, True) if safe is None else (safe, False)


# --- selection·ordering -----------------------------------------------------


# `--limit` 계약. 기본과 범위를 코드 여기저기가 아니라 한 자리에 둔다.
LIMIT_DEFAULT = 100
LIMIT_MIN = 1
LIMIT_MAX = 10000


def check_limit(value):
    """범위를 벗어난 `--limit` 은 usage 오류다. 오류가 없으면 None.

    `0` 과 음수를 무제한으로 읽지 않는다. 그렇게 열어 두면 bounded 출력 계약이 옵션 하나로
    사라지고, 화면과 JSON 이 감사 전체를 싣는다 — 상한을 둔 이유가 그것이다. 조용히 값을
    범위 안으로 끌어당기지도 않는다. 끌어당기면 사용자가 요청한 것과 받은 것이 달라지고,
    화면 어디에도 그 사실이 남지 않는다.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        return ("limit_out_of_range", {"value": value, "min": LIMIT_MIN, "max": LIMIT_MAX})
    if value < LIMIT_MIN or value > LIMIT_MAX:
        return ("limit_out_of_range", {"value": value, "min": LIMIT_MIN, "max": LIMIT_MAX})
    return None


def select_sources(requested, include_local):
    """(source id 목록, 오류). 오류가 있으면 목록은 비어 있다.

    `--include-local` 없이 로컬 source 를 **지목한** 것은 조용히 빈 결과를 내지 않는다. 빈 결과를
    내면 사용자는 "그 source 에 기록이 없다" 로 읽고, 암묵적으로 포함하면 로컬 데이터로 가는
    관문이 둘이 된다. 관문은 `--include-local` 하나로 유지한다.
    """
    if not requested:
        chosen = [source.id for source in SOURCES
                  if include_local or not source.local]
        return chosen, None

    unknown = [name for name in requested if name not in _BY_ID]
    if unknown:
        return [], ("unknown_source", {"value": ", ".join(sorted(unknown)),
                                       "known": ", ".join(SOURCE_IDS)})
    blocked = [name for name in requested if _BY_ID[name].local and not include_local]
    if blocked:
        return [], ("local_without_optin", {"value": ", ".join(sorted(blocked))})
    return [name for name in SOURCE_IDS if name in set(requested)], None


def selection_of(source_ids, include_local, cycle_stem, run_id, limit):
    """화면·JSON 에 실을 선택 상태. (selection, 치환 건수).

    `cycle_stem` 과 `run_id` 는 사용자가 친 자유 문자열이고, 그대로 되비추면 감사에서 오지
    않은 경로가 출력에 들어온다.

    대조도 **이 정화된 값**으로 한다. envelope 의 `cycle_stem` 도 같은 sanitizer 를 지났기
    때문이다 — 한쪽만 정화하면 같은 값을 가리키는 두 문자열이 서로 다른 것이 되어 필터가
    자기 화면에 보이는 줄을 못 찾는다. 평범한 slug 는 sanitizer 를 그대로 통과하므로 이
    선택이 일상 동작을 바꾸지 않는다.
    """
    selection = {
        "sources": list(source_ids),
        "include_local": bool(include_local),
        "cycle_stem": _text_or_none(cycle_stem),
        "run_id": _text_or_none(run_id),
        "limit": limit,
    }
    return sanitize_value(selection)


def matches(item, cycle_stem, run_id):
    if cycle_stem is not None and item.get("cycle_stem") != cycle_stem:
        return False
    if run_id is not None and item.get("run_id") != run_id:
        return False
    return True


def order_events(items):
    """`epoch` 내림차순, 같은 초 안에서는 source id·source_index 오름차순.

    epoch 이 없는 레코드는 맨 뒤로 보낸다. 앞으로 보내면 시각을 모르는 줄이 최신인 것처럼
    보이고, 뒤섞어 두면 같은 저장소 상태가 실행마다 다른 순서를 낸다 — 기계가 대조할 수 없다.
    """
    return sorted(items, key=lambda item: (
        -(item["epoch"] if item["epoch"] is not None else -1),
        item["source"], item["source_index"]))
