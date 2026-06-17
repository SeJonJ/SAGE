"""override_audit — 게이트 BLOCK 합법 우회 + append-only 감사 (외부검토 P1-5).

게이트(pre-implementation-gate · pre-phase4-checklist-gate)의 BLOCK 을 운영자가 사유·기한과 함께
명시적으로 우회한다. 이전엔 메시지에 "(override required)" 문구만 있고 실제 우회 수단이 없었다(P1-5).

설계:
- 상태=감사로그 단일소스: 활성 override = .sage/override.jsonl 의 grant 레코드 중 미만료분.
  별도 토큰 파일 없음 → grant 기록이 곧 권한이고 곧 감사. append-only(수정/삭제 안 함).
- grant 와 그 권한이 실제로 막힌 BLOCK 을 통과시킨 bypass 를 모두 기록 → 사후 추적 가능
  ("override X 가 게이트 Y 의 파일 Z 수정을 통과시킴").
- TTL 만료로 권한 자동 회수(상시 우회 = Pattern A 방지). wall-clock 기준이라 세션 교차에도 일관.
- gate 스코프: 특정 게이트 id 또는 "all". 우회는 grant.gate ∈ {요청 gate, "all"} 일 때만.

엔진 모듈(도메인값 0): 게이트 id 는 호출자가 주입, 경로/시간만 여기서 결정.
"""
import json
import os
import time

AUDIT_REL = os.path.join(".sage", "override.jsonl")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def audit_path(root):
    return os.path.join(root, AUDIT_REL)


def parse_ttl(s):
    """'30m' | '2h' | '1d' | '90s' | '1800'(초) → seconds(int). 음수/0/무효 → None."""
    s = (s or "").strip().lower()
    if not s:
        return None
    try:
        if s[-1] in _UNITS:
            secs = int(float(s[:-1]) * _UNITS[s[-1]])
        else:
            secs = int(float(s))
    except (ValueError, IndexError):
        return None
    return secs if secs > 0 else None


def _iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _append(root, record):
    p = audit_path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_records(root):
    """감사로그 전 레코드(파싱 실패 줄 skip). 부재 → []."""
    p = audit_path(root)
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def grant(root, reason, ttl_seconds, gate="all", user=None, now=None):
    """override grant 1건 기록 → 레코드 반환. reason·ttl 필수(상위에서 검증)."""
    t = time.time() if now is None else now
    rec = {"event": "grant", "ts": _iso(t), "epoch": int(t),
           "expires_epoch": int(t) + int(ttl_seconds), "expires_at": _iso(t + ttl_seconds),
           "ttl_seconds": int(ttl_seconds), "gate": gate, "reason": reason,
           "user": user or os.environ.get("USER") or "unknown"}
    _append(root, rec)
    return rec


def active_grants(root, gate=None, now=None):
    """미만료 grant 레코드. gate 지정 시 grant.gate ∈ {gate, 'all'} 만. 최신순."""
    t = time.time() if now is None else now
    out = []
    for r in read_records(root):
        if r.get("event") != "grant":
            continue
        if r.get("expires_epoch", 0) <= t:
            continue
        if gate is not None and r.get("gate") not in (gate, "all"):
            continue
        out.append(r)
    return sorted(out, key=lambda r: r.get("epoch", 0), reverse=True)


def is_override_active(root, gate, now=None):
    return bool(active_grants(root, gate=gate, now=now))


def record_bypass(root, gate, files, message_key, grant_rec, now=None):
    """grant 가 실제로 BLOCK 을 통과시킨 사실 기록 — 무엇을(message_key) 어느 파일에 적용했는지 추적."""
    t = time.time() if now is None else now
    _append(root, {"event": "bypass", "ts": _iso(t), "epoch": int(t), "gate": gate,
                   "message_key": message_key, "files": files or [],
                   "grant_ts": (grant_rec or {}).get("ts"),
                   "reason": (grant_rec or {}).get("reason")})
