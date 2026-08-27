"""`sage audit show [--json]` — 여섯 감사 출처를 한 화면에서 읽는다.

## 무엇을 하지 않는가

새 감사 정본을 만들지 않고, 기존 파일을 고치지 않고, 어떤 게이트의 입력도 되지 않는다.
이것은 **읽기 전용 투영**이다. 조회가 `invalid` 를 발견해도 hook 이 새로 차단하지 않고,
반대로 기존이 fail-closed 하는 source 를 조회가 WARN 으로 낮추지도 않는다.

lock 을 만들지도 획득하지도 않는다. 그래서 진행 중인 append 중간을 볼 수 있고, 그 상태는
감춰지지 않고 `audit.source.concurrent_change` 로 표면화된다.

## 보증을 올려 말하지 않는다

여섯 출처의 무결성 보증은 서로 다르다. review·fast 는 hash chain 이 있고, acceptance 는
의미 검증만 있으며, override·feedback 에는 아무 검증도 없다. 화면은 그 차이를 `method` 와
`status` 두 축으로 그대로 낸다. 하나로 뭉뚱그리면 조회 화면이 원본보다 강한 보증을 하게 되고,
그 순간 이 기능은 가시성 개선이 아니라 거짓 보증 신설이다.

## 왜 로컬 두 종이 기본에서 빠지는가

`retro`·`feedback` 은 개인 작업 흔적이고 vault 경로 같은 로컬 사정이 섞인다. 기본 출력에
넣으면 화면을 공유하는 것만으로 그것들이 함께 나간다. 관문은 `--include-local` **하나** 다 —
로컬 source 를 `--source` 로 지목했는데 그 관문이 없으면 조용히 빈 결과를 내지 않고 usage
오류로 끝낸다. 빈 결과는 "그 source 에 기록이 없다" 로 읽힌다.
"""
import json
import os
import sys

from sage import audit_sources, audit_view
from sage.diagnostic_contract import (BLOCK, TOOL_FAILURE, WARN, Finding, order,
                                      render_recovery, severity_of)
from sage.diagnostics import render as render_diagnostic
from sage.i18n import language_of, tr

SCHEMA_VERSION = audit_view.SCHEMA_VERSION

# 계약 자체는 `audit_view` 가 갖는다. 여기서 값을 다시 적으면 두 자리가 갈릴 수 있다.
DEFAULT_LIMIT = audit_view.LIMIT_DEFAULT


def register(sub, context):
    parser = sub.add_parser("audit", help=tr(context, "cli.audit.audit"))
    actions = parser.add_subparsers(dest="audit_action")
    show = actions.add_parser("show", help=tr(context, "cli.audit.show"))
    show.add_argument("--source", action="append", default=None,
                      help=tr(context, "cli.audit.source"))
    show.add_argument("--include-local", action="store_true",
                      help=tr(context, "cli.audit.include_local"))
    show.add_argument("--cycle-stem", default=None, help=tr(context, "cli.audit.cycle_stem"))
    show.add_argument("--run-id", default=None, help=tr(context, "cli.audit.run_id"))
    show.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                      help=tr(context, "cli.audit.limit"))
    show.add_argument("--json", action="store_true", help=tr(context, "cli.audit.json"))
    show.add_argument("--root", default=None)
    show.set_defaults(func=run_show)
    parser.set_defaults(func=_no_action)


def _no_action(args):
    print(tr(language_of(args), "cli.audit.no_action"), file=sys.stderr)
    return 2


def collect(root, source_ids, cycle_stem, run_id):
    """(sources, events, findings). 어느 adapter 도 파일을 쓰지 않는다."""
    sources, events, findings = [], [], []
    for source_id in source_ids:
        source = audit_view.source_of(source_id)
        try:
            loaded = audit_sources.load_source(root, source)
        except Exception as exc:
            # 한 source 가 무너져도 나머지는 살린다. 전체를 감싼 그물 하나만 있으면 예외
            # 하나가 이미 수집한 사실을 전부 지우고 class 이름만 남긴다.
            findings.append(Finding("audit.source.unavailable",
                                    evidence={"source": source_id, "error": type(exc).__name__},
                                    arguments={"source": source_id, "error": type(exc).__name__}))
            # 상태 dict 는 `audit_sources` 가 짓는다. 여기서 다시 지으면 두 모양이 갈리고,
            # 갈린 쪽이 하필 예외 경로라 평소에는 아무도 보지 못한다.
            entry = audit_sources.state_of(source)
            # `present` 만 `None` 이다. 부재(`False`)도 존재(`True`)도 아니라 **판정하지 못한**
            # 상태이고, 셋을 구분하지 않으면 도구 실패가 "기록 없음" 으로 읽힌다.
            entry["present"] = None
            entry["integrity"]["status"] = audit_view.STATUS_UNREADABLE
            sources.append(entry)
            continue
        for code, arguments in loaded.pop("issues"):
            findings.append(Finding(code, evidence=dict(arguments), arguments=dict(arguments)))
        for item in loaded.pop("events"):
            if audit_view.matches(item, cycle_stem, run_id):
                events.append(item)
        sources.append(loaded)

    # 없는 파일의 추적 상태는 묻지 않는다. `git ls-files` 는 부재 파일을 나열하지 않으므로
    # 물으면 전부 `untracked` 로 돌아오고, 화면은 "커밋되지 않았다" 고 말하게 된다 — 실제로는
    # 아직 아무것도 기록되지 않았을 뿐이다.
    rels = [entry["path"] for entry in sources if entry["present"]]
    tracking = audit_sources.tracking_of(root, rels)
    for entry in sources:
        if not entry["present"]:
            entry["tracking"] = None
            continue
        entry["tracking"] = tracking.get(entry["path"], "unavailable")
        policy = audit_view.source_of(entry["id"]).tracking_policy
        if entry["tracking"] == "unavailable":
            findings.append(Finding("audit.source.tracking_unavailable",
                                    evidence={"source": entry["id"]},
                                    arguments={"source": entry["id"]}))
        elif policy == "tracked" and entry["tracking"] != "tracked":
            # 정책과 실제가 다르다는 사실만 말한다. 고쳐 주지 않는다 — 자동 `git add` 는
            # 조회 명령이 사용자의 저장소를 바꾸는 것이고, 그건 이 명령의 계약 밖이다.
            findings.append(Finding("audit.source.tracking_policy",
                                    evidence={"source": entry["id"], "actual": entry["tracking"]},
                                    arguments={"source": entry["id"], "actual": entry["tracking"]}))
    return sources, audit_view.order_events(events), tuple(order(findings))


def aggregate(findings):
    """(status, exit_code). 부재를 통과로 읽지 않는다.

    도구 실패와 정책 차단을 같은 토큰으로 내지 않는다. 둘을 섞으면 사용자는 감사를 고치러
    가고, 고칠 것이 없어 되돌아온다.
    """
    if any(finding.code in TOOL_FAILURE for finding in findings):
        return "ERROR", 2
    severities = {severity_of(finding.code) for finding in findings}
    if BLOCK in severities:
        return "ISSUES", 1
    if WARN in severities:
        return "ATTENTION", 0
    return "OK", 0


def _flat(value):
    """화면용 한 조각. 목록은 쉼표로 잇는다 — Python repr 을 사용자에게 보이지 않는다."""
    if isinstance(value, (list, tuple)):
        return ",".join(_flat(item) for item in value)
    return str(value)


def _shown(events, limit):
    """(보이는 것, 생략된 수). `limit` 은 `check_limit` 을 이미 통과한 범위 안의 정수다."""
    if limit >= len(events):
        return events, 0
    return events[:limit], len(events) - limit


def _present_token(value):
    """`present` 는 세 상태다. `None` 은 부재가 아니라 **판정하지 못함** 이다.

    둘로 접으면 도구 실패가 화면에서 "기록 없음" 으로 읽힌다. JSON 은 이미 `null` 로 셋을
    구분하므로, text 만 접으면 같은 실행이 두 형식에서 다른 사실을 말하게 된다.
    """
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _print_text(status, selection, sources, events, omitted, findings, language):
    say = lambda key, **kw: tr(language, key, **kw)                     # noqa: E731
    # 상태 토큰과 enum 은 번역하지 않는다 — 화면에서 검색하고 로그에서 수집하는 조각이라
    # 언어를 타면 안 된다. 설명만 표시 언어를 따른다.
    print(f"SAGE audit: {status}")
    # 필터가 걸렸으면 무엇이 걸렸는지 함께 낸다. 안 내면 0건 결과를 "기록이 없다" 로 읽는다.
    # 두 renderer 가 같은 `selection` 을 읽으므로 정화도 한 자리에서 끝난다.
    if selection["cycle_stem"] or selection["run_id"]:
        print(say("cli.audit.line_selection",
                  cycle_stem=selection["cycle_stem"] or "-",
                  run_id=selection["run_id"] or "-",
                  limit=selection["limit"]))
    print()
    for entry in sources:
        integrity = entry["integrity"]
        print(say("cli.audit.line_source", source=entry["id"],
                  present=_present_token(entry["present"]),
                  records=entry["record_count"],
                  method=integrity["method"], status=integrity["status"],
                  tracking=entry["tracking"] or "-"))
        if entry["caveat"]:
            # source 의 한계는 **항상** 나간다. 조건부로 숨기면 그 조건이 언젠가 참이 되고,
            # 그때 사용자는 보증이 없는 기록을 보증된 것으로 읽는다.
            print("    " + say(f"cli.{entry['caveat']}"))

    print()
    if events:
        print(say("cli.audit.events_header", shown=len(events), dropped=omitted))
        for item in events:
            # 문장은 human 만 만든다. `summary_code` 는 JSON 의 안정 계약이고 여기서는 그 code 로
            # catalog 문장을 찾는다 — 두 renderer 가 같은 result 를 읽되 문장은 한쪽만 붙인다.
            print(say("cli.audit.line_event",
                      occurred_at=item["occurred_at"] or "-",
                      source=item["source"], event=item["event"] or "-",
                      summary=say(f"cli.{item['summary_code']}")))
            detail = " ".join(f"{key}={_flat(value)}"
                              for key, value in sorted(item["data"].items()))
            if item["run_id"]:
                detail = f"run={item['run_id']}" + (f" {detail}" if detail else "")
            if detail:
                print("    " + detail)
        print()
        # 이 고지가 없으면 사용자는 교차 source 시간순을 인과관계로 읽는다. 여섯 출처는
        # 서로 다른 writer 가 서로 다른 시점에 쓴 것이고, 조회는 그 사이의 순서를 증명하지
        # 못한다 — 화면 순서일 뿐이다.
        print(say("cli.audit.ordering_note"))
    else:
        print(say("cli.audit.no_events"))

    for finding in findings:
        print()
        print(f"[{finding.code}] "
              + render_diagnostic(finding.diagnostic(),
                                  lambda key, **kw: tr(language, key, **kw), "cli"))
        if severity_of(finding.code) != BLOCK:
            continue
        for line in render_recovery(finding.code,
                                    lambda key, **kw: tr(language, key, **kw), "cli"):
            print(line)


def run_show(args):
    language = language_of(args)
    from sage.commands.status import resolve_root

    # root 해석 규칙은 `status` 가 이미 소유한다. 여기서 다시 만들면 같은 저장소에서 두 명령이
    # 서로 다른 root 를 고르는 상태가 생기고, 그때 어느 쪽이 옳은지 판정할 근거가 없다.
    root = resolve_root(args)
    if root is None or not os.path.isdir(root):
        print(tr(language, "cli.audit.root_unresolved"), file=sys.stderr)
        return 2

    source_ids, option_error = audit_view.select_sources(args.source, args.include_local)
    if option_error is None:
        # 범위 밖 `--limit` 도 조용히 고쳐 주지 않고 usage 오류로 끝낸다. 옵션 검증은 조회를
        # 시작하기 전에 전부 끝난다 — 파일을 읽은 뒤에 옵션을 거절하면 읽기가 헛수고가 된다.
        option_error = audit_view.check_limit(args.limit)
    if option_error:
        code, arguments = option_error
        print(tr(language, f"cli.audit.{code}", **arguments), file=sys.stderr)
        return 2

    # selection 을 먼저 확정한다. 화면에 실을 값과 대조에 쓸 값이 같아야 하기 때문이다.
    selection, selection_hits = audit_view.selection_of(
        source_ids, args.include_local, args.cycle_stem, args.run_id, args.limit)

    try:
        sources, events, findings = collect(
            root, source_ids, selection["cycle_stem"], selection["run_id"])
    except Exception as exc:
        print(tr(language, "cli.audit.collect_failed", error=type(exc).__name__), file=sys.stderr)
        return 2

    events, omitted = _shown(events, args.limit)
    findings = list(findings)
    if omitted:
        findings.append(Finding("audit.source.truncated",
                                evidence={"omitted": omitted},
                                arguments={"omitted": omitted, "limit": args.limit}))

    if selection_hits:
        # 정화를 조용히 삼키지 않는다. source 진단과 같은 원칙이고, 다만 이건 감사에서 온
        # 값이 아니라 사용자가 친 값이라 별도 code 를 쓴다.
        findings.append(Finding("audit.selection.redacted",
                                evidence={"count": selection_hits},
                                arguments={"count": selection_hits}))
    findings = list(order(findings))
    status, exit_code = aggregate(findings)

    if args.json:
        # JSON 에는 문장을 싣지 않는다. 안정 계약은 code 뿐이고, 문장을 실으면 `--lang` 에
        # 따라 byte 가 달라져 기계가 두 실행 결과를 대조할 수 없다.
        #
        # `truncated` 는 boolean 이고 생략 건수는 `omitted` 다. 하나로 겸하면 `0` 이 거짓과
        # "0건 생략" 을 동시에 뜻해 소비자가 둘을 구분할 수 없다.
        print(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "ok": exit_code == 0,
            "status": status,
            "exit_code": exit_code,
            "ordering": "display_order_only",
            "selection": selection,
            "sources": sources,
            "events": events,
            "returned": len(events),
            "omitted": omitted,
            "truncated": omitted > 0,
            # 진단의 정본은 여기 하나다. `sources[]` 에 사본을 두면 둘이 갈렸을 때 어느 쪽이
            # 옳은지 판정할 근거가 없어진다. source 결속은 `evidence.source` 로 한다.
            "diagnostics": [finding.to_json() for finding in findings],
        }, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text(status, selection, sources, events, omitted, findings, language)
    return exit_code
