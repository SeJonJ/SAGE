"""sage override — 게이트 BLOCK 의 시한부 합법 우회 grant·회수 + 감사.

게이트(pre-implementation-gate · pre-phase4-checklist-gate)가 BLOCK 하는데 운영상 정당한 우회가
필요할 때, 사유(--reason)와 기한(--ttl)을 명시해 시한부 권한을 grant 한다. 오발급한 권한은
--revoke 로 만료 전에 회수할 수 있다. 우회 이력(grant·bypass·revoke)은 커밋되는 감사 로그
<root>/.sage/override.jsonl 에 append-only 로 남아 사후 추적되고, TTL 만료로 자동 회수된다.

활성 권한 자체는 감사와 분리해 **저장소 트리 밖**(SAGE_STATE_HOME > XDG_STATE_HOME > ~/.local/state)
에 둔다. 저장소 안에 두면 커밋돼서 남의 clone 에서 우회가 활성화된다(10-e). 위치는 --list 가 출력한다.

핵심 로직은 엔진 런타임 모듈(override_audit) 단일소스 — hook 과 CLI 가 같은 코드를 공유.
"""
import os
import sys
import time

from sage import _resources
from sage.i18n import language_of, tr

_GATES = ["pre-implementation-gate", "pre-phase4-checklist-gate", "all"]


def register(sub, context):
    p = sub.add_parser("override", help=tr(context, "cli.override.override"))
    p.add_argument("--reason", help=tr(context, "cli.override.reason"))
    p.add_argument("--ttl", help=tr(context, "cli.override.ttl"))
    p.add_argument("--gate", default="all", help=tr(context, "cli.override.gate", gates=" | ".join(_GATES)))
    p.add_argument("--list", action="store_true", help=tr(context, "cli.override.list"))
    p.add_argument("--revoke", metavar="GRANT_ID", help=tr(context, "cli.override.revoke"))
    p.add_argument("--root", default=None, help=tr(context, "cli.override.root"))
    p.set_defaults(func=run)


def _load_override_audit():
    rt = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    import override_audit as ov
    return ov


def run(args):
    root = os.path.abspath(args.root or os.getcwd())
    ov = _load_override_audit()
    try:
        return _run(args, root, ov)
    except ov.StateHomeError as exc:
        # 권한 캐시 위치를 안전하게 정할 수 없음 = 우회를 만들 수 없음. traceback 대신 안내한다.
        print(f"⛔ [sage override] {exc}", file=sys.stderr)
        return 2


def _run(args, root, ov):

    if args.list:
        now = time.time()
        active = ov.active_grants(root, now=now)
        records = ov.read_records(root)
        grants = [r for r in records if r.get("event") == "grant"]
        bypasses = [r for r in records if r.get("event") == "bypass"]
        # 선언 cycle stem 은 grant 없이 게이트를 통과시킬 수 있는 두 번째 축이라 같은 화면에 세운다 —
        # 감사 로그에만 쌓이고 뷰어가 안 보여주면 기록해도 아무도 안 본다.
        declared = [r for r in records if r.get("event") == "cycle_stem_declared"]
        print(f"== sage override --list ({ov.audit_path(root)}) ==")
        # 권한 캐시는 저장소 밖에 있어 `.sage/tmp` 삭제로 리셋되지 않는다 — 위치를 보여줘야
        # 운영자가 "왜 아직 활성이지"를 추적할 수 있다.
        print(tr(language_of(args), "cli.override.msg01", ov_grants_path=ov.grants_path(root)))
        print(tr(language_of(args), "cli.override.msg02", count=len(active)))
        for g in active:
            print(tr(language_of(args), "cli.override.msg03", g_get=g.get('grant_id'), arg=g['gate'], arg2=g['expires_at'], g_get2=g.get('reason'), g_get3=g.get('user')))
        print(tr(language_of(args), "cli.override.msg04", count=len(grants), count2=len(bypasses), count3=len(declared)))
        for b in bypasses[-5:]:
            print(tr(language_of(args), "cli.override.msg05", b_get=b.get('ts'), b_get2=b.get('gate'), b_get3=b.get('message_key'), count=len(b.get('files') or [])))
        for d in declared[-5:]:
            # 통로를 읽은 자리 그대로 적는다 — 통로가 둘(env / .sage/cycle.json)인데 한쪽 이름으로
            # 뭉치면 감사가 거짓을 말한다. 기원 필드가 없는 옛 레코드는 env 시절 기록이다.
            channel = {"env": "SAGE_CYCLE_STEM", "cli": ".sage/cycle.json"}.get(
                d.get("origin") or "", "SAGE_CYCLE_STEM")
            print(tr(language_of(args), "cli.override.msg06", channel=channel, d_get=d.get('ts'), d_get2=d.get('cycle_stem'), d_get3=d.get('status'), d_get4=d.get('user')))
        return 0

    # revoke 경로
    if args.revoke:
        rec = ov.revoke(root, args.revoke, reason=args.reason)
        if rec is None:
            print(tr(language_of(args), "cli.override.msg07", args_revoke=args.revoke), file=sys.stderr)
            return 2
        print(tr(language_of(args), "cli.override.msg08", args_revoke=args.revoke, arg=rec['gate']))
        return 0

    # grant 경로
    if not args.reason or not args.ttl:
        print(tr(language_of(args), "cli.override.msg09"), file=sys.stderr)
        return 2
    if args.gate not in _GATES:
        print(tr(language_of(args), "cli.override.msg10", gates=_GATES, args_gate=args.gate), file=sys.stderr)
        return 2
    ttl = ov.parse_ttl(args.ttl)
    if ttl is None:
        print(tr(language_of(args), "cli.override.msg11", args_ttl=args.ttl), file=sys.stderr)
        return 2
    # 상한 초과는 거부 — 시한부가 무한정 길어지면 사실상 상시 우회가 된다(라이브러리도 ValueError 로 이중방어).
    if ttl > ov.MAX_TTL_SECONDS:
        print(tr(language_of(args), "cli.override.msg12", ttl=ttl, ov_max_ttl_seconds=ov.MAX_TTL_SECONDS), file=sys.stderr)
        return 2

    rec = ov.grant(root, args.reason, ttl, gate=args.gate)
    print(tr(language_of(args), "cli.override.msg13", arg=rec['gate'], arg2=rec['expires_at'], arg3=rec['ttl_seconds']))
    print(tr(language_of(args), "cli.override.msg14", arg=rec['reason'], ov_audit_path=ov.audit_path(root)))
    print(tr(language_of(args), "cli.override.msg15"))
    return 0
