"""Host boundary for the root skill catalog; never an approval oracle.

Import the package validator lazily so pure gates remain standalone. An
installed project without that validator is an error, not a silent fallback.
"""
import json
import os

MARKERS = ('sage/project-profile.yaml', 'sage/project-profile.json',
           'docs/sage_harness/.manifest.json')


def installed(root):
    return any(os.path.lexists(os.path.join(root, path)) for path in MARKERS)


def role_for(raw):
    """Use an explicit packet role; generic child metadata never selects a role."""
    role = os.environ.get('SAGE_OVERLAY_ROLE', '')
    if role:
        return role
    if any(raw.get(key) for key in ('agent_id', 'parent_session_id', 'parent_thread_id')):
        return 'child'
    return 'root'


def _issue(exc):
    code = getattr(exc, 'code', 'overlay_delivery.validator_unavailable')
    path = getattr(exc, 'path', '')
    message = str(code) + (f' path={path}' if path else '')
    observed, limit = getattr(exc, 'observed', None), getattr(exc, 'limit', None)
    if type(observed) is int and type(limit) is int:
        message += f' observed={observed} limit={limit} unit=utf16_code_units'
    return message


def output_issue(text, runtime):
    """Check the decoded event string, including reentry and risk notices."""
    try:
        from sage.overlay_delivery import check_host_context
        check_host_context(text, runtime)
        return None
    except Exception as exc:
        return _issue(exc)


def current(root, raw_text, *, runtime='claude', validate_materialization=True,
            empty_if_absent=False):
    """Return (context, body-free error), validating children without injecting."""
    active = installed(root)
    if not active and not empty_if_absent:
        return '', None
    try:
        raw = json.loads(raw_text or '{}')
        if not isinstance(raw, dict):
            return '', 'overlay_delivery.invalid_event'
    except (ValueError, TypeError):
        return '', 'overlay_delivery.invalid_event'
    try:
        from sage.overlay_delivery import collect_catalog, render_catalog
        role = role_for(raw)
        if not active:
            if role != 'root':
                return '', None
            # An installed host moved to an absent catalog boundary. Reuse the
            # existing schema/hash/render path with an explicitly empty inventory;
            # do not discover non-SAGE input or inherit the policy owner's bodies.
            from sage.overlay_delivery import _collect
            root = os.path.realpath(root)
            if not os.path.isdir(root):
                return '', 'overlay_delivery.invalid_root'
            catalog = _collect(root, role, [])
            if installed(root):
                return '', 'overlay_delivery.unstable_snapshot'
        else:
            catalog = collect_catalog(root, role=role)
        if active and validate_materialization:
            # Source validity alone cannot clear a failed SessionStart L1. Check
            # the current installed state without writes or a session error latch.
            from sage.overlay_materialize import plan_materialize
            _anchors, plans, errors = plan_materialize(
                root, runtime, context_validated=True)
            if errors:
                issue = errors[0][1]
                return '', getattr(issue, 'code', 'overlay_delivery.render_invalid')
            if any(new != old for _path, new, old in plans):
                return '', 'overlay_delivery.render_sync_required'
        return (render_catalog(catalog, runtime=runtime) if role == 'root' else ''), None
    except Exception as exc:
        # Do not format exception text: decoder/read/lint errors can quote input.
        return '', _issue(exc)


def _profile_repair_target(root):
    """기존 설치 영수증만 사용한다. 불명확하면 host를 추측하지 않는다."""
    unknown = '<claude|codex|both>'
    if root is None:
        return unknown
    try:
        for rel in ('docs', 'docs/sage_harness', 'docs/sage_harness/.manifest.json'):
            if os.path.islink(os.path.join(root, rel)):
                return unknown
        with open(os.path.join(root, 'docs/sage_harness/.manifest.json'), encoding='utf-8') as handle:
            manifest = json.load(handle)
        if not isinstance(manifest, dict):
            return unknown
        if 'installed_hosts' in manifest:
            hosts = manifest['installed_hosts']
        else:
            hosts = [manifest.get('host_runtime')]
        if (not isinstance(hosts, list) or not hosts
                or any(host not in ('claude', 'codex') for host in hosts)):
            return unknown
        selected = set(hosts)
        return 'both' if len(selected) == 2 else next(iter(selected))
    except Exception:
        return unknown


def error_message(issue, root=None):
    """대상 root의 hook 메시지 소유자에서 표시 언어만 적용한다."""
    import i18n
    language = i18n.DEFAULT_LANGUAGE
    if root is not None:
        try:
            language = i18n.context.resolve(root)[0]
        except Exception:
            # 표시 설정 손상이나 예외 원문이 입력 오류의 안전한 진단을 막지 않는다.
            pass
    code = issue.split(' ', 1)[0] if isinstance(issue, str) else ''
    message_key = {
        'materialize.profile_yaml_json_mismatch': 'hook.overlay_delivery.repair_profile',
        'overlay_delivery.render_sync_required': 'hook.overlay_delivery.repair_render',
        'overlay.context_upgrade_required': 'hook.overlay_delivery.repair_upgrade',
    }.get(code, 'hook.overlay_delivery.input_error')
    template = i18n.frag(language, message_key)
    arguments = {'issue': issue}
    if message_key == 'hook.overlay_delivery.repair_profile':
        arguments['target'] = _profile_repair_target(root)
    return template.format(**arguments)


def merge_output(captured, context):
    """Fold legacy risk/reentry renderings into one native context envelope."""
    parts = []
    for line in captured.splitlines():
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            parts.append(line)
            continue
        specific = doc.get('hookSpecificOutput') if isinstance(doc, dict) else None
        if isinstance(specific, dict) and isinstance(specific.get('additionalContext'), str):
            parts.append(specific['additionalContext'])
        else:
            raise ValueError('unexpected context output')
    if context:
        parts.append(context)
    return '\n\n'.join(parts)
