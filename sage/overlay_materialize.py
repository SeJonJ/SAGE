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
import stat

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
    - skills: claude repo scope와 존재하는 codex project-local scope. Codex global scope는 프로젝트 간
      누출을 막기 위해 제외한다.
    - framework: 공통 AGENT_GUIDE + host wrapper + codex AGENTS router. base receipt 대상에는
      포함하지만 독립 gate oracle이 없어 project overlay composition은 blocked다.
    """
    targets = []
    agents_dir = os.path.join(dest, ".claude" if host == "claude" else ".codex", "agents")
    for aid in sorted(_cls.CORE_IDS["agents"]):
        targets.append(("agents", aid, os.path.join(agents_dir, f"{aid}.md")))
    codex_local_skills = (host == "codex"
                          and os.path.isdir(os.path.join(dest, ".codex", "skills")))
    if host == "claude" or codex_local_skills:
        for sid in sorted(_cls.CORE_IDS["skills"]):
            host_dir = ".claude" if host == "claude" else ".codex"
            targets.append(("skills", sid, os.path.join(dest, host_dir, "skills", sid, "SKILL.md")))
    targets.append(("framework", "AGENT_GUIDE", os.path.join(dest, "AGENT_GUIDE.md")))
    if host == "claude":
        targets.append(("framework", "CLAUDE", os.path.join(dest, "CLAUDE.md")))
    else:
        targets.append(("framework", "CODEX", os.path.join(dest, "CODEX.md")))
        targets.append(("framework", "AGENTS", os.path.join(dest, "AGENTS.md")))
    return targets


def _project_path_issue(dest, path, leaf_kind=None):
    """Validate a project-owned input without following a symlink below dest."""
    root = os.path.abspath(dest)
    target = os.path.abspath(path)
    try:
        if os.path.commonpath((root, target)) != root:
            return f"project input path가 root 밖임: {target}"
    except ValueError:
        return f"project input path와 root의 filesystem이 다름: {target}"

    cursor = root
    parts = os.path.relpath(target, root)
    parts = () if parts == "." else parts.split(os.sep)
    for index, part in enumerate(parts):
        cursor = os.path.join(cursor, part)
        is_leaf = index == len(parts) - 1
        try:
            mode = os.lstat(cursor).st_mode
        except FileNotFoundError:
            return None
        except OSError as exc:
            return f"project input path 상태 확인 실패: {cursor} ({exc})"
        if stat.S_ISLNK(mode):
            return f"project input symlink는 허용되지 않음: {cursor}"
        if not is_leaf and not stat.S_ISDIR(mode):
            return f"project input ancestor가 directory가 아님: {cursor}"
        if is_leaf and leaf_kind == "file" and not stat.S_ISREG(mode):
            return f"project input이 regular file이 아님: {cursor}"
        if is_leaf and leaf_kind == "dir" and not stat.S_ISDIR(mode):
            return f"project input이 directory가 아님: {cursor}"
    return None


def _exact_data_equal(left, right):
    """Compare JSON/YAML data without Python's bool/int or int/float coercion."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        if len(left) != len(right):
            return False
        unmatched = list(right.items())
        for left_key, left_value in left.items():
            for index, (right_key, right_value) in enumerate(unmatched):
                if (type(left_key) is type(right_key) and left_key == right_key
                        and _exact_data_equal(left_value, right_value)):
                    unmatched.pop(index)
                    break
            else:
                return False
        return not unmatched
    if isinstance(left, list):
        return (len(left) == len(right)
                and all(_exact_data_equal(a, b) for a, b in zip(left, right)))
    return left == right


def load_profile(dest):
    candidates = {}
    for rel in ("sage/project-profile.yaml", "sage/project-profile.json"):
        path = os.path.join(dest, rel)
        if os.path.lexists(path):
            issue = _project_path_issue(dest, path, leaf_kind="file")
            if issue:
                return {}, issue
            candidates[rel] = path
    if not candidates:
        return {}, None

    try:
        yaml_profile = None
        yaml_rel = "sage/project-profile.yaml"
        if yaml_rel in candidates:
            text, err = _oc.read_text_lf(candidates[yaml_rel])
            if err:
                return {}, err
            yaml_profile = yaml.safe_load(text)
            if yaml_profile is None:
                yaml_profile = {}
            if not isinstance(yaml_profile, dict):
                return {}, f"profile 최상위가 mapping이 아님: {yaml_rel}"
            from sage.profile_compile import ProfileCompileError, materialize_profile
            try:
                compiled_yaml = materialize_profile(yaml_profile)
            except ProfileCompileError as exc:
                return {}, f"profile materialize 실패({yaml_rel}): {exc}"
        else:
            compiled_yaml = None

        json_rel = "sage/project-profile.json"
        if json_rel in candidates:
            text, err = _oc.read_text_lf(candidates[json_rel])
            if err:
                return {}, err
            json_profile = json.loads(text)
            if not isinstance(json_profile, dict):
                return {}, f"profile 최상위가 mapping이 아님: {json_rel}"
            if compiled_yaml is not None and not _exact_data_equal(json_profile, compiled_yaml):
                return {}, "project-profile.yaml과 project-profile.json이 다름; sage generate 재실행 필요"
            return json_profile, None
        return compiled_yaml, None
    except Exception as exc:
        return {}, f"profile 로드 실패: {exc}"


def _load_profile(dest):
    """Compatibility alias for callers/tests that still use the former private helper."""
    return load_profile(dest)


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


def preflight_overlays(dest, profile=None):
    """Validate all overlay/domain inputs without requiring installed CORE renders."""
    errors = []
    if profile is None:
        profile, profile_error = load_profile(dest)
        if profile_error:
            errors.append((os.path.join(dest, "sage", "project-profile.yaml"), profile_error))
    profile = profile if isinstance(profile, dict) else {}

    overlay_root = os.path.join(dest, "sage", "asset_overrides")
    unsafe_inventory = False
    if os.path.lexists(overlay_root):
        issue = _project_path_issue(dest, overlay_root, leaf_kind="dir")
        if issue:
            errors.append((overlay_root, issue))
            unsafe_inventory = True
    for kind in ("agents", "skills", "framework"):
        directory = os.path.join(overlay_root, kind)
        if not os.path.lexists(directory):
            continue
        issue = _project_path_issue(dest, directory, leaf_kind="dir")
        if issue:
            errors.append((directory, issue))
            unsafe_inventory = True
    if unsafe_inventory:
        return errors

    inventory = _cls.overlay_files(dest)
    for _kind, _id, path in inventory:
        path_issue = _project_path_issue(dest, path, leaf_kind="file")
        if path_issue:
            errors.append((path, path_issue))
    if errors:
        return errors

    from sage.overlay_lint import scan_domain_contract, scan_text
    for _check_id, relpath, message in scan_domain_contract(dest, profile):
        errors.append((os.path.join(dest, relpath), message))

    for kind, id, path in inventory:
        filename_error = _cls.overlay_filename_error(kind, id, path)
        if filename_error:
            errors.append((path, filename_error))
            continue
        if not _cls.is_core(kind, id):
            errors.append((path, f"미지/오타 CORE 자산 오버레이: '{id}' 는 CORE {kind} 아님"))
            continue
        if _cls.classify(kind, id) == "blocked":
            errors.append((path, f"{kind}/{id} 는 오버레이 미지원(SD-8 전까지 blocked)"))
            continue
        text, read_error = _oc.read_text_lf(path)
        if read_error:
            errors.append((path, read_error))
            continue
        validation_error = _oc.validate_overlay(text)
        if validation_error:
            errors.append((path, validation_error))
            continue
        relax_hits = scan_text(text)
        if relax_hits:
            details = "; ".join(f"{pattern_id}: {description}"
                                for pattern_id, description in relax_hits)
            errors.append((path, f"overlay-gate-relaxation: {details}"))
    return errors


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
    errors.extend(preflight_overlays(dest, profile))

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


def apply_materialization(plans, writer=None):
    """검증 완료된 물리화 계획을 적용하고 변경 경로를 반환한다."""
    changed = []
    for path, new_text, installed in plans:
        if new_text != installed:
            (writer or _oc.write_text_lf)(path, new_text)
            changed.append(path)
    return changed


def plan_blocked_cleanup(dest, host, path_guard=None):
    """blocked CORE 자산에 남은 SAGE managed block 제거 계획을 계산한다.

    FB12 이전에 materialize된 framework/gate-bearing block은 현재 overlay 파일의 오류 때문에
    일반 preflight가 중단돼도 실행 지침으로 남아서는 안 된다. SAGE 마커 구간만 제거하며 base와
    manifest 영수증은 건드리지 않는다. path_guard(path)가 오류 문자열 또는 `(오류, 증거)`를
    반환하면 파일을 읽기 전에 해당 target을 거부한다. 반환은 (plans, errors).
    """
    plans, errors = [], []
    for kind, id, path in render_targets(dest, host):
        if _cls.classify(kind, id) != "blocked":
            continue
        if path_guard is not None:
            path_issue = path_guard(path)
            if path_issue:
                message = path_issue[0] if isinstance(path_issue, tuple) else str(path_issue)
                errors.append((path, message))
                continue
        if not os.path.isfile(path):
            continue
        installed, rerr = _oc.read_text_lf(path)
        if rerr:
            errors.append((path, rerr))
            continue
        stripped, serr = _oc.insert_block(installed, "")
        if serr:
            errors.append((path, serr))
            continue
        if stripped != installed:
            plans.append((path, stripped, installed))
    return plans, errors


def materialize(dest, host):
    """단일 host의 CORE 렌더를 물리화(블록 수렴) + 앵커 계산.

    반환 (core_renders, changed_paths, errors).
      core_renders: {anchor_key: {base_sha256, sage_version}} — manifest 기록용(엔진 소유).
      changed_paths: 실제로 렌더가 바뀐 경로.
      errors: [(path, msg)] — 오버레이 토큰 주입/읽기 실패/malformed 마커 등.
    렌더 파일이 없으면 skip(앵커 없음) — install 이 base 를 먼저 쓰므로 정상 경로엔 다 존재.
    """
    cleanup_plans, cleanup_errors = plan_blocked_cleanup(dest, host)
    # 안전하게 경계를 식별한 다른 blocked managed block은 한 target의 malformed marker와
    # 독립적으로 제거한다. 제거 불가능한 target의 오류는 그대로 hard-stop으로 반환한다.
    cleanup_changed = apply_materialization(cleanup_plans)
    if cleanup_errors:
        return {}, cleanup_changed, cleanup_errors
    core_renders, plans, errors = plan_materialize(dest, host)
    if errors:
        return {}, cleanup_changed, errors
    return core_renders, cleanup_changed + apply_materialization(plans), []


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
        filename_error = _cls.overlay_filename_error(kind, id, opath)
        if filename_error:
            findings.append(("FAIL", f"{host}/{kind}/{id}", filename_error))
            continue
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
