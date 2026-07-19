"""CLI for explicit, exact-scope L3 acceptance waivers."""
import glob
import os
import sys

from sage import _resources


def _load_runtime_modules():
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    runtime = os.path.join(hooks, "runtime")
    for path in (runtime, hooks):
        if path not in sys.path:
            sys.path.insert(0, path)
    import acceptance_waiver as aw
    import cycle_binding
    import pre_implementation_gate_core as gate_core
    return aw, cycle_binding, gate_core


def register(sub):
    p = sub.add_parser("acceptance-waiver", help="특정 L3 acceptance의 운영 검증 유예를 명시적으로 기록합니다")
    actions = p.add_subparsers(dest="action", metavar="<action>")
    actions.required = True

    grant = actions.add_parser("grant", help="exact cycle/required acceptance ID waiver 발급")
    grant.add_argument("--cycle-stem", required=True)
    grant.add_argument("--acceptance-id", required=True)
    grant.add_argument("--reason", required=True)
    grant.add_argument("--scope", required=True)
    grant.add_argument("--remaining-evidence", required=True)
    grant.add_argument("--confirm-user", required=True,
                       help="명시 승인한 사용자 표시(로컬 self-asserted audit이며 원격 신원 증명 아님)")
    grant.add_argument("--ttl", default="24h", help="유효기간, 최대 24h (기본 24h)")
    grant.add_argument("--root", default=None)
    grant.set_defaults(func=_run_grant)

    listing = actions.add_parser("list", help="waiver audit와 현재 active grant 조회")
    listing.add_argument("--root", default=None)
    listing.set_defaults(func=_run_list)

    revoke = actions.add_parser("revoke", help="active waiver 명시 회수")
    revoke.add_argument("--waiver-id", required=True)
    revoke.add_argument("--reason", required=True)
    revoke.add_argument("--confirm-user", required=True)
    revoke.add_argument("--root", default=None)
    revoke.set_defaults(func=_run_revoke)


def _root(args):
    return os.path.abspath(args.root or os.getcwd())


def _load_profile(root):
    path = os.path.join(root, "sage", "project-profile.yaml")
    try:
        import yaml
        with open(path, encoding="utf-8") as fh:
            profile = yaml.safe_load(fh)
    except Exception as exc:
        raise ValueError(f"project profile load failed: {type(exc).__name__}: {exc}")
    if not isinstance(profile, dict):
        raise ValueError("project profile must be a mapping")
    acceptance = ((profile.get("verification") or {}).get("acceptance") or {})
    if not isinstance(acceptance, dict) or ((acceptance.get("waiver") or {}).get("enabled") is not True):
        raise ValueError("verification.acceptance.waiver.enabled=true is required")
    return profile


def _assert_required_acceptance(root, profile, cycle_stem, acceptance_id):
    _, cycle_binding, gate_core = _load_runtime_modules()
    pdca = profile.get("pdca") or {}
    phase = next((p for p in (pdca.get("phases") or []) if str(p.get("id") or "") == "01"), None)
    pattern = (phase or {}).get("glob") or ""
    if not pattern or os.path.isabs(pattern) or ".." in pattern.split("/"):
        raise ValueError("safe Phase 01 glob is required in pdca.phases")
    docs = []
    for path in glob.glob(os.path.join(root, pattern), recursive=True):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="ignore") as fh:
            docs.append({"path": os.path.relpath(path, root).replace(os.sep, "/"), "content": fh.read()})
    selected, error = cycle_binding.select_document(docs, cycle_stem)
    if error:
        raise ValueError(f"Phase 01 exact cycle selection failed: {error}")
    matrix = gate_core._acceptance_matrix(selected.get("content") or "")
    if matrix["invalid"] or matrix["duplicates"]:
        raise ValueError("Phase 01 acceptance matrix is malformed or duplicated")
    if acceptance_id not in matrix["required"]:
        raise ValueError(f"{acceptance_id!r} is not an exact required acceptance ID for cycle {cycle_stem!r}")


def _run_grant(args):
    root = _root(args)
    aw, _, _ = _load_runtime_modules()
    ttl = aw.parse_ttl(args.ttl)
    if ttl is None or ttl > aw.MAX_TTL_SECONDS:
        print("[sage acceptance-waiver] --ttl must be positive and at most 24h", file=sys.stderr)
        return 2
    try:
        profile = _load_profile(root)
        _assert_required_acceptance(root, profile, args.cycle_stem, args.acceptance_id)
        record = aw.grant(root, args.cycle_stem, args.acceptance_id, args.reason, args.scope,
                          args.remaining_evidence, args.confirm_user, ttl_seconds=ttl)
    except (ValueError, OSError) as exc:
        print(f"[sage acceptance-waiver] grant rejected: {exc}", file=sys.stderr)
        return 2
    print(record["waiver_id"])
    print(f"cycle={record['cycle_stem']} acceptance={record['acceptance_id']} expires={record['expires_at']}")
    print(f"audit={aw.audit_path(root)} attestation={record['attestation']}")
    return 0


def _run_list(args):
    root = _root(args)
    aw, _, _ = _load_runtime_modules()
    summary = aw.audit_summary(root)
    if not summary["valid"]:
        print("[sage acceptance-waiver] invalid audit: " + "; ".join(summary["issues"]), file=sys.stderr)
        return 2
    print(f"audit={aw.audit_path(root)} active={len(summary['active'])}")
    for grant in summary["active"]:
        print(f"{grant['waiver_id']} cycle={grant['cycle_stem']} acceptance={grant['acceptance_id']} "
              f"expires={grant['expires_at']} confirmed_by={grant['confirmed_by']}")
    return 0


def _run_revoke(args):
    root = _root(args)
    aw, _, _ = _load_runtime_modules()
    try:
        record = aw.revoke(root, args.waiver_id, args.reason, args.confirm_user)
    except (ValueError, OSError) as exc:
        print(f"[sage acceptance-waiver] revoke rejected: {exc}", file=sys.stderr)
        return 2
    if record is None:
        print(f"[sage acceptance-waiver] active waiver not found: {args.waiver_id}", file=sys.stderr)
        return 2
    print(f"revoked {args.waiver_id}")
    return 0
