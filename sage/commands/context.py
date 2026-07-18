"""sage context: explicit PDCA context snapshot and verified restore."""
import sys

from sage.context_packet import ContextError, create_snapshot, restore_snapshot


def register(sub):
    parser = sub.add_parser("context", help="phase 경계 context packet을 저장하고 검증 복원합니다")
    actions = parser.add_subparsers(dest="action", metavar="<action>")
    actions.required = True

    snapshot = actions.add_parser("snapshot", help="완료 phase의 구조화 context packet 저장")
    snapshot.add_argument("--cycle-stem", required=True)
    snapshot.add_argument("--phase", required=True, help="profile pdca.phases에 선언된 완료 phase id")
    snapshot.add_argument("--root", default=None)
    snapshot.set_defaults(func=_run_snapshot)

    restore = actions.add_parser("restore", help="packet/source 결속 검증 후 resume briefing 생성")
    restore.add_argument("--snapshot", required=True, help="managed snapshot JSON 경로")
    restore.add_argument("--root", default=None)
    restore.set_defaults(func=_run_restore)


def _run_snapshot(args):
    try:
        result = create_snapshot(args.root or ".", args.cycle_stem, args.phase)
    except (ContextError, OSError) as exc:
        print(f"[sage context snapshot] rejected: {exc}", file=sys.stderr)
        return 2
    print(result["path"])
    print(f"snapshot_id={result['snapshot_id']} phase={args.phase}")
    return 0


def _run_restore(args):
    try:
        result = restore_snapshot(args.root or ".", args.snapshot)
    except (ContextError, OSError) as exc:
        print(f"[sage context restore] rejected: {exc}", file=sys.stderr)
        return 2
    print(result["path"])
    print(f"snapshot_id={result['snapshot_id']} host={result['from_host']}->{result['to_host']} "
          f"next_phase={result['next_phase'] or 'N/A'}")
    return 0
