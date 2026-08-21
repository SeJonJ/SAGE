"""sage context: explicit PDCA context snapshot and verified restore."""
import sys

from sage.context_packet import ContextError, create_snapshot, restore_snapshot
from sage.i18n import tr


def register(sub, context):
    parser = sub.add_parser("context", help=tr(context, "cli.context.context"))
    actions = parser.add_subparsers(dest="action", metavar="<action>")
    actions.required = True

    snapshot = actions.add_parser("snapshot", help=tr(context, "cli.context.snapshot"))
    snapshot.add_argument("--cycle-stem", required=True)
    snapshot.add_argument("--phase", required=True, help=tr(context, "cli.context.phase"))
    snapshot.add_argument("--root", default=None)
    snapshot.set_defaults(func=_run_snapshot)

    restore = actions.add_parser("restore", help=tr(context, "cli.context.restore"))
    restore.add_argument("--snapshot", required=True, help=tr(context, "cli.context.snapshot_2"))
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
