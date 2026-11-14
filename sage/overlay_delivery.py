"""Event-scoped, validated root overlay catalogs without persistent private copies.

Common UTF-8 ceilings are distinct from host delivery budgets. Claude's string
spill boundary requires a UTF-16 budget for the serialized catalog and the merged
event context. Byte counts are not measured tokenizer results.
"""
import hashlib
import json
import os

from sage import overlay_classify as classify
from sage import overlay_common as common
from sage import overlay_local as local
from sage.overlay_materialize import load_profile

MAX_SOURCE_UTF8_BYTES = 10_000
MAX_CATALOG_UTF8_BYTES = 49_152
MAX_CLAUDE_CATALOG_UTF16_UNITS = 7_500
MAX_CLAUDE_EVENT_UTF16_UNITS = 10_000

_PREFIX = (
    'SAGE_OVERLAY_CATALOG_V2\n'
    'Use this current catalog only for its matching working root and role. '
    'It replaces earlier catalog state, including when sources/targets are empty. '
    'Each CORE applies only its own fixed targets[id] references in their given order; '
    'other targets are not instructions for the current task. '
    'Shared additions take priority over personal additions; mandatory CORE, project '
    'policy and independent gates remain in force. Catalog presence is not a skill '
    'invocation, Fast selection/conversion, approval or authorization. '
    'Use a child CORE target when entering it and the parent target on return, '
    'without accumulating their views. Hashes identify supplied content, not compliance.\n'
)
_SUFFIX = '\nEND_SAGE_OVERLAY_CATALOG_V2'


class OverlayDeliveryError(ValueError):
    """Only a stable code and source path; never include overlay body or cause text."""

    def __init__(self, code, path='', *, observed=None, limit=None, unit=None, runtime=None):
        self.code = code
        self.path = path
        self.observed = observed
        self.limit = limit
        self.unit = unit
        self.runtime = runtime
        detail = (f' observed={observed} limit={limit} unit={unit}'
                  if observed is not None else '')
        super().__init__(code + (f' path={path}' if path else '')
                         + (f' runtime={runtime}' if runtime else '') + detail)


def utf16_code_units(text: str) -> int:
    """Count JavaScript-style string units: an astral character occupies two."""
    return len(text.encode('utf-16-le', errors='surrogatepass')) // 2


def check_host_context(text: str, runtime, *, catalog=False) -> None:
    """Check one full string without truncation; merged-event callers use catalog=False.

    The Claude catalog budget reserves 2,500 units for reentry/declared-risk text.
    The actual merged context still needs its separate 10,000-unit defensive check.
    Codex keeps the common UTF-8 catalog ceiling and configured native limit.
    """
    if runtime != 'claude':
        return
    limit = MAX_CLAUDE_CATALOG_UTF16_UNITS if catalog else MAX_CLAUDE_EVENT_UTF16_UNITS
    observed = utf16_code_units(text)
    if observed > limit:
        code = ('overlay_delivery.host_catalog_too_large' if catalog
                else 'overlay_delivery.host_context_too_large')
        raise OverlayDeliveryError(code, observed=observed, limit=limit,
                                   unit='utf16_code_units', runtime='claude')


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _relative(root, path):
    return os.path.relpath(path, root).replace(os.sep, '/')


def _stat(path):
    try:
        value = os.lstat(path)
    except FileNotFoundError:
        return None
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _snapshot(root, *, validate_manifest=True):
    """Capture inventories and identity/metadata before and after each read pass."""
    state, inventory = {}, []
    for rel in ('sage', 'sage/project-profile.yaml', 'sage/project-profile.json',
                'docs/sage_harness/.manifest.json'):
        if rel == 'docs/sage_harness/.manifest.json' and not validate_manifest:
            continue
        path = os.path.join(root, rel)
        local._check_path(root, path, 'dir' if rel == 'sage' else 'file')
        state[rel] = _stat(path)
    for scope, subdir in (('shared', 'asset_overrides'), ('personal', 'asset_overrides.local')):
        base = os.path.join(root, 'sage', subdir)
        local._check_path(root, base, 'dir')
        state[_relative(root, base)] = _stat(base)
        for kind in ('agents', 'skills', 'framework'):
            directory = os.path.join(base, kind)
            local._check_path(root, directory, 'dir')
            directory_stat = _stat(directory)
            names = tuple(sorted(os.listdir(directory))) if directory_stat is not None else ()
            state[_relative(root, directory)] = (directory_stat, names)
            for name in names:
                if not name.lower().endswith('.md'):
                    continue
                path = os.path.join(directory, name)
                local._check_path(root, path, 'file')
                state[_relative(root, path)] = _stat(path)
                inventory.append((scope, kind, name[:-3], path))
    return state, inventory


def _validate_project(root, profile=None, *, validate_manifest=True):
    if profile is None:
        profile, issue = load_profile(root)
        if issue:
            raise OverlayDeliveryError(issue.code, 'sage/project-profile.yaml')
    # Reuse the routing input/domain contract, including explicit-null handling.
    _, issue = classify.expected_routing_block('framework', 'AGENT_GUIDE', root, profile)
    if issue:
        raise OverlayDeliveryError(issue.code, 'sage/project-profile.yaml')
    manifest = os.path.join(root, 'docs', 'sage_harness', '.manifest.json')
    if validate_manifest and os.path.lexists(manifest):
        text, issue = common.read_text_lf(manifest)
        if issue:
            raise OverlayDeliveryError(issue.code, _relative(root, manifest))
        try:
            value = json.loads(text)
        except (ValueError, TypeError):
            raise OverlayDeliveryError('overlay_delivery.manifest_invalid',
                                       _relative(root, manifest)) from None
        if not isinstance(value, dict):
            raise OverlayDeliveryError('overlay_delivery.manifest_invalid',
                                       _relative(root, manifest))


def _collect(root, role, inventory, profile=None, *, validate_manifest=True, check_lint=True):
    _validate_project(root, profile, validate_manifest=validate_manifest)
    sources = {}
    for scope, kind, asset_id, path in inventory:
        # Shared and personal inputs use exactly the existing eligibility/path/
        # roster/filename/reserved-token/relaxation checks and one LF read.
        text = (local._read(root, kind, asset_id, path) if check_lint else
                local._read(root, kind, asset_id, path, check_lint=False))
        if kind != 'skills' or asset_id not in classify.ROOT_CONTEXT_SKILL_IDS:
            continue
        if not text.strip():
            continue
        rel = _relative(root, path)
        observed = len(text.encode('utf-8'))
        if observed > MAX_SOURCE_UTF8_BYTES:
            raise OverlayDeliveryError('overlay_delivery.source_too_large', rel,
                                      observed=observed, limit=MAX_SOURCE_UTF8_BYTES,
                                      unit='utf8_bytes')
        if role != 'root':
            continue
        sources[f'skills/{asset_id}/{scope}'] = {
            'path': rel, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'content': text,
        }
    targets = {}
    if role == 'root':
        for target, source_ids in classify.ROOT_CONTEXT_TARGET_SOURCES.items():
            refs = [f'skills/{asset_id}/{scope}'
                    for scope in ('shared', 'personal') for asset_id in source_ids
                    if f'skills/{asset_id}/{scope}' in sources]
            if not refs:
                continue
            # Inherited standard input cannot bypass a blocked Fast target.
            if (not classify.is_core('skills', target)
                    or classify.classify('skills', target) != 'compose'
                    or classify.delivery_mode('skills', target) != 'context'):
                raise OverlayDeliveryError('overlay.unsupported_blocked')
            targets[target] = refs
    catalog = {'schema_version': 2, 'root': root, 'role': role,
               'sources': sources, 'targets': targets}
    catalog['generation'] = hashlib.sha256(_json(catalog).encode('utf-8')).hexdigest()
    # No caller can accidentally treat an oversized unrendered catalog as valid.
    render_catalog(catalog)
    return catalog


def collect_catalog(root: str, role: str = 'root', *, profile=None,
                    validate_manifest=True, check_lint=True) -> dict:
    """Validate the whole current inventory and return a single stable snapshot.

    Nonroot roles still validate all input, but do not receive root skill bodies.
    Root discovery/event semantics belong to the caller; an explicit root never
    climbs into another checkout. One unstable snapshot is retried from scratch.
    check_lint=False is for read-only validation's separate WARN/strict pass;
    application and runtime callers retain the default rejection policy.
    """
    try:
        if not isinstance(root, str) or not root or not isinstance(role, str) or not role:
            raise OverlayDeliveryError('overlay_delivery.invalid_scope')
        root = os.path.realpath(root)
        if not os.path.isdir(root):
            raise OverlayDeliveryError('overlay_delivery.invalid_root')
        for attempt in range(2):
            try:
                before, inventory = _snapshot(root, validate_manifest=validate_manifest)
                error = None
                try:
                    catalog = _collect(root, role, inventory, profile,
                                       validate_manifest=validate_manifest, check_lint=check_lint)
                except Exception as exc:
                    error = exc
                after, _ = _snapshot(root, validate_manifest=validate_manifest)
            except (FileNotFoundError, NotADirectoryError):
                # A directory may vanish/change kind between stat and listdir
                # in either acquisition. Retry the whole snapshot once; source
                # validation errors stay deferred and are not retried here.
                if attempt == 0:
                    continue
                raise OverlayDeliveryError('overlay_delivery.unstable_snapshot') from None
            if before != after:
                if attempt == 0:
                    continue
                raise OverlayDeliveryError('overlay_delivery.unstable_snapshot')
            if error is not None:
                raise error
            return catalog
        raise OverlayDeliveryError('overlay_delivery.unstable_snapshot')
    except OverlayDeliveryError:
        raise
    except local.OverlayLocalError as exc:
        raise OverlayDeliveryError(exc.code, exc.path) from None
    except Exception:
        raise OverlayDeliveryError('overlay_delivery.validation_failed') from None


def render_catalog(catalog: dict, *, runtime=None) -> str:
    """Serialize full content once; count wrapper and JSON escaping, never truncate."""
    try:
        rendered = _PREFIX + _json(catalog) + _SUFFIX
        observed = len(rendered.encode('utf-8'))
        if observed > MAX_CATALOG_UTF8_BYTES:
            raise OverlayDeliveryError('overlay_delivery.catalog_too_large',
                                      observed=observed, limit=MAX_CATALOG_UTF8_BYTES,
                                      unit='utf8_bytes')
        check_host_context(rendered, runtime, catalog=True)
        return rendered
    except OverlayDeliveryError:
        raise
    except Exception:
        raise OverlayDeliveryError('overlay_delivery.serialization_failed') from None


def delivery_hosts(manifest, extra=()):
    """Use installation receipts and explicitly requested hosts, never CLI default."""
    manifest = manifest if isinstance(manifest, dict) else {}
    hosts = manifest.get('installed_hosts')
    if not isinstance(hosts, list):
        hosts = []
    return list(dict.fromkeys(h for h in [manifest.get('host_runtime'), *hosts, *extra]
                              if h in ('claude', 'codex')))


def preflight_delivery(root, hosts, *, profile=None, validate_manifest=True, check_lint=True):
    """Read-only source/host check; a supplied profile is the caller's planned input.

    Does not require installed renders. generate may validate the profile it is
    about to compile without treating an old compiled JSON as the repair input.
    Errors contain paths/counts only; user content is neither returned nor changed.
    """
    # A first install may target a directory that does not exist yet. It cannot
    # contain overlay input; install's own destination/path checks still apply.
    if not os.path.lexists(root):
        return []
    try:
        catalog = collect_catalog(root, profile=profile, validate_manifest=validate_manifest,
                                  check_lint=check_lint)
        for host in hosts:
            render_catalog(catalog, runtime=host)
        return []
    except OverlayDeliveryError as exc:
        return [(os.path.join(root, exc.path) if exc.path else root, str(exc))]
