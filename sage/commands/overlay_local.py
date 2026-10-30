"""Read-only JSON interface for validated per-checkout guidance."""
import json
import sys

from sage.i18n import language_of, tr
from sage.overlay_local import OverlayLocalError, discover_root, load_local


def register(sub, context):
    p = sub.add_parser('overlay-local', help=tr(context, 'cli.overlay_local.help'))
    p.add_argument('--kind', required=True, choices=['agent', 'skill'])
    p.add_argument('--id', required=True)
    p.add_argument('--root', default=None)
    p.set_defaults(func=run)


def run(args):
    try:
        root = discover_root(args.root)
        result = load_local(root, {'agent': 'agents', 'skill': 'skills'}[args.kind], args.id)
    except OverlayLocalError as error:
        print(tr(language_of(args), 'cli.overlay_local.error', code=error.code, path=error.path),
              file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0
