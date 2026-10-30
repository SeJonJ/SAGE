"""Read validated personal guidance without materializing it into shared assets.

No activation state is stored. References describe the exact normalized string
returned by this read; they are observations, not a complete execution audit.
"""
import hashlib
import os

from sage import overlay_classify as classify
from sage import overlay_common as common
from sage.overlay_lint import scan_text
from sage.overlay_materialize import _project_path_issue

LOCAL_SUBDIR = os.path.join('sage', 'asset_overrides.local')


class OverlayLocalError(ValueError):
    """Body-free diagnostic: do not expose read exceptions or private input."""

    def __init__(self, code, path=''):
        self.code = code
        self.path = path
        super().__init__(code)


def discover_root(root=None):
    """Explicit roots never climb; automatic discovery stops at a Git boundary."""
    from sage.commands.doctor import _is_repo_boundary
    current = os.path.realpath(root if root is not None else os.getcwd())
    while True:
        if (os.path.isfile(os.path.join(current, 'sage', 'project-profile.yaml'))
                or os.path.isfile(os.path.join(current, 'docs', 'sage_harness', '.manifest.json'))):
            return current
        if root is not None or _is_repo_boundary(current):
            raise OverlayLocalError('overlay_local.project_not_found')
        parent = os.path.dirname(current)
        if parent == current:
            raise OverlayLocalError('overlay_local.project_not_found')
        current = parent


def _check_path(root, path, leaf_kind):
    issue = _project_path_issue(root, path, leaf_kind=leaf_kind)
    if issue:
        raise OverlayLocalError(issue.code, os.path.relpath(path, root).replace(os.sep, '/'))


def _read(root, kind, asset_id, path):
    """Use the same eligibility, markers and relaxation checks as shared input."""
    rel = os.path.relpath(path, root).replace(os.sep, '/')
    _check_path(root, path, 'file')
    issue = classify.overlay_filename_error(kind, asset_id, path)
    if issue:
        raise OverlayLocalError(issue.code, rel)
    if not classify.is_core(kind, asset_id):
        raise OverlayLocalError('overlay.unknown_core_asset', rel)
    if classify.classify(kind, asset_id) != 'compose':
        raise OverlayLocalError('overlay.unsupported_blocked', rel)
    text, issue = common.read_text_lf(path)
    if issue:
        raise OverlayLocalError(issue.code, rel)
    issue = common.validate_overlay(text)
    if issue:
        raise OverlayLocalError(issue.code, rel)
    if scan_text(text):
        raise OverlayLocalError('overlay-gate-relaxation', rel)
    return text


def load_local(root, kind, asset_id):
    """Validate the known inventory and return only the requested asset, or None.

    Other malformed personal overlays are errors, never silent omissions. Files
    are read once; only the selected string is returned and hashed.
    """
    if not classify.is_core(kind, asset_id):
        raise OverlayLocalError('overlay.unknown_core_asset')
    if classify.classify(kind, asset_id) != 'compose':
        raise OverlayLocalError('overlay.unsupported_blocked')
    root = os.path.realpath(root)
    base = os.path.join(root, LOCAL_SUBDIR)
    _check_path(root, base, 'dir')
    selected = None
    for category in ('agents', 'skills', 'framework'):
        directory = os.path.join(base, category)
        _check_path(root, directory, 'dir')
        if not os.path.isdir(directory):
            continue
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            raise OverlayLocalError('overlay.read_failed', os.path.relpath(directory, root)) from None
        for name in names:
            if not name.lower().endswith('.md'):
                continue
            aid = name[:-3]
            path = os.path.join(directory, name)
            text = _read(root, category, aid, path)
            if (category, aid) == (kind, asset_id) and text.strip():
                selected = dict(kind=kind, id=asset_id,
                    path=os.path.relpath(path, root).replace(os.sep, '/'),
                    sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(), content=text)
    return selected


def reviewer_packet(root, prompt):
    """Append shared then personal reviewer additions, only when personal is active."""
    local = load_local(root, 'agents', 'reviewer')
    if local is None:
        return prompt, None
    shared_path = classify.overlay_path(root, 'agents', 'reviewer')
    _check_path(root, os.path.dirname(shared_path), 'dir')
    shared = _read(root, 'agents', 'reviewer', shared_path) if os.path.lexists(shared_path) else ''
    additions = []
    if shared.strip():
        additions.append('### Project reviewer additions\n' + shared)
    additions.append('### Personal reviewer additions\n' + local['content'])
    prompt += ('\n\n## Additional reviewer guidance\n'
               'Apply these additions within the existing mandatory project policies.\n'
               + '\n\n'.join(additions))
    return prompt, {key: value for key, value in local.items() if key != 'content'}
