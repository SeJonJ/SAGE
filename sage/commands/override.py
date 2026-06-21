"""sage override — 게이트 BLOCK 의 시한부 합법 우회 grant·회수 + 감사.

게이트(pre-implementation-gate · pre-phase4-checklist-gate)가 BLOCK 하는데 운영상 정당한 우회가
필요할 때, 사유(--reason)와 기한(--ttl)을 명시해 시한부 권한을 grant 한다. 오발급한 권한은
--revoke 로 만료 전에 회수할 수 있다. 우회 이력(grant·bypass·revoke)은 커밋되는 감사 로그
<root>/.sage/override.jsonl 에 append-only 로 남아 사후 추적되고, TTL 만료로 자동 회수된다.

핵심 로직은 엔진 런타임 모듈(override_audit) 단일소스 — hook 과 CLI 가 같은 코드를 공유.
"""
import os
import sys
import time

from sage import _resources

_GATES = ["pre-implementation-gate", "pre-phase4-checklist-gate", "all"]


def register(sub):
    p = sub.add_parser("override", help="막힌 작업을 사유와 시간 제한을 남기고 임시로 허용합니다")
    p.add_argument("--reason", help="우회 사유 (grant 시 필수 — 감사 기록)")
    p.add_argument("--ttl", help="유효기간: 30m | 2h | 1d | 90s | 1800(초)")
    p.add_argument("--gate", default="all", help=f"대상 게이트 ({' | '.join(_GATES)}). 기본 all")
    p.add_argument("--list", action="store_true", help="활성 override + 최근 감사 요약")
    p.add_argument("--revoke", metavar="GRANT_ID", help="활성 grant 를 만료 전에 회수 (--list 의 id)")
    p.add_argument("--root", default=None, help="대상 프로젝트 루트 (기본 cwd)")
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

    if args.list:
        now = time.time()
        active = ov.active_grants(root, now=now)
        records = ov.read_records(root)
        grants = [r for r in records if r.get("event") == "grant"]
        bypasses = [r for r in records if r.get("event") == "bypass"]
        print(f"== sage override --list ({ov.audit_path(root)}) ==")
        print(f"활성 override: {len(active)}건")
        for g in active:
            print(f"   - id={g.get('grant_id')} | gate={g['gate']} | 만료 {g['expires_at']} | 사유: {g.get('reason')} | by {g.get('user')}")
        print(f"감사 총계: grant {len(grants)}건, bypass {len(bypasses)}건 (append-only)")
        for b in bypasses[-5:]:
            print(f"   · bypass {b.get('ts')} gate={b.get('gate')} {b.get('message_key')} 파일 {len(b.get('files') or [])}건")
        return 0

    # revoke 경로
    if args.revoke:
        rec = ov.revoke(root, args.revoke, reason=args.reason)
        if rec is None:
            print(f"[sage override] 활성 grant id '{args.revoke}' 없음 (이미 만료/회수됐거나 오타). --list 로 확인", file=sys.stderr)
            return 2
        print(f"✅ override 회수 — id={args.revoke} gate={rec['gate']} (이후 이 권한은 비활성)")
        return 0

    # grant 경로
    if not args.reason or not args.ttl:
        print("[sage override] grant 에는 --reason 과 --ttl 둘 다 필요 (또는 --list)", file=sys.stderr)
        return 2
    if args.gate not in _GATES:
        print(f"[sage override] --gate 는 {_GATES} 중 하나여야 함 (받음: {args.gate})", file=sys.stderr)
        return 2
    ttl = ov.parse_ttl(args.ttl)
    if ttl is None:
        print(f"[sage override] --ttl 형식 오류: '{args.ttl}' (예: 30m, 2h, 1d, 90s, 1800)", file=sys.stderr)
        return 2
    # 상한 초과는 거부 — 시한부가 무한정 길어지면 사실상 상시 우회가 된다(라이브러리도 ValueError 로 이중방어).
    if ttl > ov.MAX_TTL_SECONDS:
        print(f"[sage override] --ttl {ttl}s 가 상한 {ov.MAX_TTL_SECONDS}s(24h) 초과 — 더 짧게 grant 하거나 만료 후 재grant", file=sys.stderr)
        return 2

    rec = ov.grant(root, args.reason, ttl, gate=args.gate)
    print(f"✅ override grant — gate={rec['gate']} | 만료 {rec['expires_at']} (TTL {rec['ttl_seconds']}s)")
    print(f"   사유: {rec['reason']} | 감사: {ov.audit_path(root)}")
    print("   (만료 시 자동 회수. 우회가 BLOCK 을 통과시킬 때마다 bypass 가 append 됨)")
    return 0
