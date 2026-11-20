"""sage plan-review: one optional, fresh-context plan review; never an approval."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

from sage.i18n import language_of, render_issue, tr
from sage.peer_process import run_peer
from sage.plan_review import (CONTRACT, DEFAULT_MAX_INPUT_BYTES, DEFAULT_TIMEOUT, InputError,
                              add_inputs, changed_inputs, make_prompt, plan_identity)
from sage.profile_layers import load_profile_layers
from sage.profile_validate import validate_profile
from sage.runtime_hosts import declared_active_host, detect_current_host, peer_env

EXIT_CODES = {'COMPLETE': 0, 'SKIPPED': 0, 'INVALID_INPUT': 2,
              'UNSUPPORTED': 3, 'PARTIAL': 3, 'FAILED': 3, 'STALE': 3}


def register(sub, context):
    p = sub.add_parser('plan-review', help=tr(context, 'cli.plan_review.help'))
    for name in ('root', 'stem'):
        p.add_argument('--' + name, required=True, help=tr(context, 'cli.plan_review.' + name))
    p.add_argument('--host', required=True, choices=['claude', 'codex'],
                   help=tr(context, 'cli.plan_review.host'))
    p.add_argument('--plan', action='append', required=True,
                   help=tr(context, 'cli.plan_review.plan'))
    p.add_argument('--source', action='append', default=[],
                   help=tr(context, 'cli.plan_review.source'))
    p.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT,
                   help=tr(context, 'cli.plan_review.timeout'))
    p.add_argument('--max-input-bytes', type=int, default=DEFAULT_MAX_INPUT_BYTES,
                   help=tr(context, 'cli.plan_review.max_input_bytes'))
    p.add_argument('--output', help=tr(context, 'cli.plan_review.output'))
    p.add_argument('--json', action='store_true', help=tr(context, 'cli.plan_review.json'))
    p.set_defaults(func=run)


def now():
    return datetime.now(timezone.utc).isoformat()


def output_target(root, stem, requested):
    base = root / '.sage' / 'plan-reviews'
    slug = 'cycle-' + hashlib.sha256(stem.encode('utf-8')).hexdigest()[:16]
    path = Path(requested) if requested else base / slug / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex + '.json')
    if not path.is_absolute():
        path = root / path
    # Reject aliases rather than resolving a symlink to a different storage location.
    if '..' in path.parts or not path.is_relative_to(base) or path.suffix != '.json':
        raise InputError('output_path', 'output must be a new .json file under .sage/plan-reviews/')
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise InputError('output_path', f'symlink in output path: {parent}')
    if path.exists():
        raise InputError('output_exists', 'output already exists; refusing to overwrite')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InputError('output_path', str(exc)) from exc
    return path


def save_result(path, result):
    """Create exclusively: never overwrite another result, even if it appeared after preflight."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(result, stream, ensure_ascii=True, indent=2)
            stream.write('\n')
    except BaseException:
        # Only remove the incomplete file created by this call, never an existing result.
        path.unlink(missing_ok=True)
        raise


def execute(args):
    context = language_of(args)
    result = {'purpose': 'plan_context_review', 'schema_version': 1, 'cycle_stem': args.stem,
              'status': 'INVALID_INPUT', 'reason': None, 'host': args.host,
              'model_requested': None, 'model_observed': None, 'inputs': [],
              'review_text': None, 'partial_text': None, 'usage': None,
              'controls': 'unknown', 'audit': None, 'warnings': [], 'diagnostics': [],
              'started_at': now(), 'finished_at': None, 'source_changed': [], 'output_path': None}
    documents = []
    try:
        root = Path(args.root).resolve(strict=True)
        if not root.is_dir():
            raise InputError('root', 'root must be an existing project directory')
        if (type(args.timeout) is not int or not 30 <= args.timeout <= 1800
                or type(args.max_input_bytes) is not int or not 4096 <= args.max_input_bytes <= 4194304):
            raise InputError('limits', 'timeout: 30..1800 seconds; max-input-bytes: 4096..4194304')
        layers = load_profile_layers(str(root / 'sage/project-profile.yaml'))
        issues = layers.issues + validate_profile(layers.effective, str(root))
        failures = [render_issue(context, d) for severity, d in issues if severity == 'FAIL']
        if failures:
            raise InputError('profile', '\n'.join(failures))
        config = (layers.effective.get('pdca') or {}).get('plan_review', {})
        if not config.get('enabled', False):
            result.update(status='SKIPPED', reason='disabled')
            return result
        add_inputs(root, args.plan, 'plan', args.max_input_bytes, documents)
        identity = plan_identity(root, layers.effective, documents, args.stem)
        result.update(identity)
        if identity['risk'] not in config.get('levels', ['L2', 'L3']):
            result.update(status='SKIPPED', reason='level_excluded')
            return result
        active = detect_current_host() or declared_active_host(layers.effective)
        if active is not None and args.host != active:
            raise InputError('host_mismatch', f'explicit host {args.host} differs from active host {active}')
        add_inputs(root, args.source, 'source', args.max_input_bytes, documents)
        prompt = make_prompt(args.stem, identity, documents, args.max_input_bytes)
        target = output_target(root, args.stem, args.output)
        result['inputs'] = [{k: v for k, v in doc.items() if k != 'text'} for doc in documents]
        peer = run_peer(args.host, prompt, args.timeout, env=peer_env(args.host),
                        contract=CONTRACT, require_controls=True)
        result.update(review_text=peer.review, partial_text=peer.partial, usage=peer.usage,
                      model_observed=peer.model_observed,
                      controls=peer.controls, reason=peer.reason,
                      audit={'tool_calls': peer.tool_calls, 'violations': peer.violations,
                             'warnings': peer.warnings, 'wall_s': peer.wall_s},
                      warnings=list(peer.warnings))
        if peer.error:
            result['diagnostics'].append(render_issue(context, peer.error))
        violated = peer.violations or peer.warnings or (peer.tool_calls is not None and peer.tool_calls > 0)
        if peer.reason == 'controls_unsupported':
            result['status'] = 'UNSUPPORTED'
        elif violated or (peer.ok and peer.controls != 'full'):
            result.update(status='PARTIAL' if peer.review or peer.partial else 'FAILED',
                          reason='control_violation')
        elif not peer.ok or not peer.review:
            result['status'] = 'PARTIAL' if peer.partial else 'FAILED'
        else:
            result['status'] = 'COMPLETE'
        result['execution_status'] = result['status']
        result['execution_reason'] = result['reason']
        result['source_changed'] = changed_inputs(root, documents)
        if result['source_changed']:
            result.update(status='STALE', reason='source_changed')
        result.update(finished_at=now(), output_path=str(target))
        try:
            save_result(target, result)
        except OSError as exc:
            result.update(status='FAILED', reason='output_write_failed', output_path=None)
            result['diagnostics'].append(str(exc))
    except (OSError, ValueError, RuntimeError) as exc:
        result.update(status='INVALID_INPUT', reason=getattr(exc, 'reason', 'input'))
        result['diagnostics'].append(str(exc))
    finally:
        result['finished_at'] = result['finished_at'] or now()
    return result


def run(args):
    import sys
    result = execute(args)
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        context = language_of(args)
        print(tr(context, 'cli.plan_review.summary', status=result['status'], reason=result['reason']))
        print(tr(context, 'cli.plan_review.advisory'))
        if result['output_path']:
            print(result['output_path'])
        print(result['review_text'] or result['partial_text'] or '')
    for detail in result['diagnostics']:
        print(tr(language_of(args), 'cli.plan_review.diagnostic', detail=detail), file=sys.stderr)
    return EXIT_CODES[result['status']]
