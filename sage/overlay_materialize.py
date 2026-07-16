"""CORE 렌더 오버레이 물리화(materialize) + drift 검사 — 단일 소스.

install(합성 쓰기)·sync(재합성)·session-start L1(블록 재수렴)·validate(drift 게이트)가 모두
이 모듈을 경유한다. 분류를 우회하는 합성 경로가 없도록(§overlay_classify) render_targets 열거와
expected_block 적용을 한 곳에 둔다.

앵커(base drift 영수증): install 이 각 CORE 렌더의 canonical base 해시 + sage_version 을
manifest.core_renders 에 기록한다. 이것은 tamper-proof 앵커가 아니라 accidental-drift 영수증
(로컬이라 위조 가능) — 진짜 권위는 CI-pinned canonical 로 재계산하는 것이다. base 무결성 검사는
(c) 포함 모든 CORE 렌더에 적용해, (c) 렌더에 overlay-read 지시를 심는 변조도 잡는다.
"""
import hashlib
import json
import os

import yaml

from sage import __version__
from sage import overlay_classify as _cls
from sage import overlay_common as _oc


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def anchor_key(host, kind, id):
    return f"{host}/{kind}/{id}"


def render_targets(dest, host):
    """이 host 의 CORE 렌더 대상 [(kind, id, path)] 열거. base 무결성 앵커·물리화 대상.

    - agents: 양 host. claude=.claude/agents/<id>.md, codex=.codex/agents/<id>.md.
    - skills: claude 만(codex 는 전역 $CODEX_HOME 이라 repo-scoped 합성 시 프로젝트 간 누출 → 제외).
    - framework: 공통 AGENT_GUIDE + host wrapper + codex AGENTS router. SD-4 domain_refs 계약을
      통과한 framework override 만 물리화한다.
    """
    targets = []
    agents_dir = os.path.join(dest, ".claude" if host == "claude" else ".codex", "agents")
    for aid in sorted(_cls.CORE_IDS["agents"]):
        targets.append(("agents", aid, os.path.join(agents_dir, f"{aid}.md")))
    if host == "claude":
        for sid in sorted(_cls.CORE_IDS["skills"]):
            targets.append(("skills", sid, os.path.join(dest, ".claude", "skills", sid, "SKILL.md")))
    targets.append(("framework", "AGENT_GUIDE", os.path.join(dest, "AGENT_GUIDE.md")))
    if host == "claude":
        targets.append(("framework", "CLAUDE", os.path.join(dest, "CLAUDE.md")))
    else:
        targets.append(("framework", "CODEX", os.path.join(dest, "CODEX.md")))
        targets.append(("framework", "AGENTS", os.path.join(dest, "AGENTS.md")))
    return targets


def _load_profile(dest):
    for rel in ("sage/project-profile.json", "sage/project-profile.yaml"):
        path = os.path.join(dest, rel)
        if not os.path.isfile(path):
            continue
        try:
            text, err = _oc.read_text_lf(path)
            if err:
                return {}, err
            profile = json.loads(text) if rel.endswith(".json") else yaml.safe_load(text)
            return profile if isinstance(profile, dict) else {}, None
        except Exception as e:
            return {}, f"profile 로드 실패({rel}): {e}"
    return {}, None


def _materialized_render(installed_text, kind, id, dest):
    """설치본 → (물리화된 렌더, canonical base, error). 마커 구간을 expected_block 으로 수렴.

    (a)/(b)=오버레이 블록 삽입/갱신, (c)/미분류=expected_block=''→기존 블록 제거(스트립).
    base 영역은 절대 재작성하지 않는다.
    """
    base, berr = _oc.base_of(installed_text)
    if berr:
        return None, None, berr
    block, cerr = _cls.expected_block(kind, id, dest)
    if cerr:
        return None, base, cerr
    new_text, ierr = _oc.insert_block(base, block)
    if ierr:
        return None, base, ierr
    return new_text, base, None


def plan_materialize(dest, host):
    """모든 CORE 렌더의 물리화 계획과 앵커를 쓰기 없이 계산한다.

    반환 (core_renders, plans, errors). plans 항목은
    ``(path, new_text, installed_text)`` 이며, 여러 host를 하나의 transaction-like
    preflight로 묶어야 하는 호출자는 모든 계획이 성공한 뒤 apply_materialization을 호출한다.
    """
    core_renders, errors, plans = {}, [], []

    profile, profile_error = _load_profile(dest)
    if profile_error:
        errors.append((os.path.join(dest, "sage", "project-profile.yaml"), profile_error))
    from sage.overlay_lint import scan_domain_contract
    for _check_id, relpath, message in scan_domain_contract(dest, profile):
        errors.append((os.path.join(dest, relpath), message))

    # 쓰기 전에 실제 오버레이 파일을 전부 검사한다. render_targets 는 유효 CORE id 만 열거하므로
    # 오타 파일과 blocked 자산은 별도 선스캔이 없으면 뒤늦게 발견되어 부분 물리화가 생길 수 있다.
    for kind, id, path in _cls.overlay_files(dest):
        if not _cls.is_core(kind, id):
            errors.append((path, f"미지/오타 CORE 자산 오버레이: '{id}' 는 CORE {kind} 아님"))
            continue
        if _cls.classify(kind, id) == "blocked":
            errors.append((path, f"{kind}/{id} 는 오버레이 미지원(SD-8 전까지 blocked)"))
            continue
        text, rerr = _oc.read_text_lf(path)
        if rerr:
            errors.append((path, rerr))
            continue
        verr = _oc.validate_overlay(text)
        if verr:
            errors.append((path, verr))

    for kind, id, path in render_targets(dest, host):
        if not os.path.isfile(path):
            continue
        installed, rerr = _oc.read_text_lf(path)
        if rerr:
            errors.append((path, rerr))
            continue
        new_text, base, merr = _materialized_render(installed, kind, id, dest)
        if merr:
            errors.append((path, merr))
            continue
        plans.append((path, new_text, installed))
        core_renders[anchor_key(host, kind, id)] = {
            "base_sha256": _sha256(base),
            "sage_version": __version__,
        }

    if errors:
        return {}, [], errors
    return core_renders, plans, []


def apply_materialization(plans):
    """검증 완료된 물리화 계획을 적용하고 변경 경로를 반환한다."""
    changed = []
    for path, new_text, installed in plans:
        if new_text != installed:
            _oc.write_text_lf(path, new_text)
            changed.append(path)
    return changed


def materialize(dest, host):
    """단일 host의 CORE 렌더를 물리화(블록 수렴) + 앵커 계산.

    반환 (core_renders, changed_paths, errors).
      core_renders: {anchor_key: {base_sha256, sage_version}} — manifest 기록용(엔진 소유).
      changed_paths: 실제로 렌더가 바뀐 경로.
      errors: [(path, msg)] — 오버레이 토큰 주입/읽기 실패/malformed 마커 등.
    렌더 파일이 없으면 skip(앵커 없음) — install 이 base 를 먼저 쓰므로 정상 경로엔 다 존재.
    """
    core_renders, plans, errors = plan_materialize(dest, host)
    if errors:
        return {}, [], errors
    return core_renders, apply_materialization(plans), []


def check(dest, host, core_renders):
    """읽기 전용 drift 검사 → [(severity, key, msg)]. validate L2 게이트가 소비.

    severity ∈ {FAIL, STALE}. 검사:
      - 앵커 부재/손상 → FAIL(명시적 force-migration 예외는 호출측이 판단).
      - base 해시 불일치 → FAIL(변조/미물화, 로컬은 advisory·권위는 CI 재계산).
      - 마커 구간 != expected_block → FAIL(오버레이 미반영/stale, (c)=마커 0 이어야 통과).
      - (c)/미분류 자산에 오버레이 파일 존재 → FAIL("SD-8 전까지 미지원").
      - 앵커 sage_version != 실행 __version__ → STALE(업그레이드 안내).
    """
    findings = []
    core_renders = core_renders if isinstance(core_renders, dict) else {}
    # 오버레이 파일 선스캔 — 오타/미지 CORE id, 읽기 실패를 하드-리포트(R1 #5·#12). render_targets 는
    #   유효 CORE id 만 돌므로 여기서 별도로 실제 파일을 열어 typo 를 잡는다.
    for kind, id, opath in _cls.overlay_files(dest):
        if not _cls.is_core(kind, id):
            findings.append(("FAIL", f"{host}/{kind}/{id}",
                             f"미지/오타 CORE 자산 오버레이: {opath} ('{id}' 는 CORE {kind} 아님)"))
            continue
        _, rerr = _oc.read_text_lf(opath)
        if rerr:
            findings.append(("FAIL", f"{host}/{kind}/{id}", rerr))
    for kind, id, path in render_targets(dest, host):
        key = anchor_key(host, kind, id)
        # (c)/미분류에 오버레이 파일이 있으면 미지원 — 물화 여부와 무관한 저자 오류 신호.
        if _cls.classify(kind, id) == "blocked":
            op = _cls.overlay_path(dest, kind, id)
            if os.path.isfile(op):
                findings.append(("FAIL", key,
                                 f"{kind}/{id} 는 오버레이 미지원(SD-8 전까지 gate-classification blocked): {op} 삭제 필요"))
        if not os.path.isfile(path):
            findings.append(("FAIL", key, f"CORE 렌더 없음: {path}"))
            continue
        anchor = core_renders.get(key)
        if not isinstance(anchor, dict) or "base_sha256" not in anchor:
            findings.append(("FAIL", key, f"core_renders 앵커 부재/손상: {key}"))
            continue
        installed, rerr = _oc.read_text_lf(path)
        if rerr:
            findings.append(("FAIL", key, rerr))
            continue
        base, berr = _oc.base_of(installed)
        if berr:
            findings.append(("FAIL", key, f"{path}: {berr}"))
            continue
        if _sha256(base) != anchor["base_sha256"]:
            findings.append(("FAIL", key, f"base drift/변조: {path} (앵커 불일치)"))
            continue
        block, cerr = _cls.expected_block(kind, id, dest)
        if cerr:
            findings.append(("FAIL", key, f"{path}: {cerr}"))
            continue
        actual = _oc.extract_block(installed) or ""
        if actual != block:
            findings.append(("FAIL", key, f"오버레이 미반영/stale: {path} (`sage sync-overlays` 필요)"))
            continue
        if anchor.get("sage_version") != __version__:
            findings.append(("STALE", key,
                             f"{key} 는 SAGE {anchor.get('sage_version')} 로 설치됨(현재 {__version__}) — `sage install --force` 로 업그레이드"))
    return findings
