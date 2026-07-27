"""Static model routing contract shared by profile validation and runtime consumers."""
from __future__ import annotations

import re
from typing import Any

from sage.runtime_hosts import (HOSTS, active_host, configured_hosts, declared_active_host,
                                declared_installed_hosts, opposite_host)

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_COMPONENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_COMPONENT_KEYS = frozenset({"id", "paths", "model", "runtime_models"})
_REVIEWER_KEYS = frozenset({"host", "model"})


def _valid_model(value: Any) -> bool:
    return isinstance(value, str) and bool(_MODEL_RE.fullmatch(value))


def _valid_component_path(value: Any) -> bool:
    if (not isinstance(value, str) or not value.strip() or len(value) > 512
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        return False
    normalized = value.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        return False
    return all(part not in ("", ".", "..") for part in normalized.split("/"))


def component_model(component: dict[str, Any] | None, host: str) -> str | None:
    models = component.get("runtime_models") if isinstance(component, dict) else None
    value = models.get(host) if isinstance(models, dict) else None
    return value if _valid_model(value) else None


def peer_candidates(profile: dict[str, Any] | None,
                    current: str | None) -> list[str]:
    """리뷰를 맡길 수 있는 host — 설치된 것 중 현재 실행 중인 것을 뺀 나머지.

    현재 host 를 빼는 근거는 프로필 선언이 아니라 실행 중인 프로세스라는 사실이다. 독립 리뷰는
    "코드를 쓴 놈이 아닌 다른 놈이 본다" 이고, 그건 프로필에 뭐라 적혔든 바뀌지 않는다.
    host 가 2종뿐이라 결과는 항상 0개 또는 1개다.
    """
    hosts = configured_hosts(profile)
    return [host for host in hosts if host != current] if current else list(hosts)


def reviewer_selection(profile: dict[str, Any] | None,
                       current: str | None = None) -> tuple[str, str | None]:
    """(리뷰어 host, 모델) — current 는 실행 중인 host, None 이면 판별 불가.

    current 를 여기서 직접 감지하지 않는 이유는 순수성이다. env 를 읽으면 같은 입력이 실행 환경에
    따라 다른 답을 내고, 테스트도 어느 host 에서 돌리느냐에 좌우된다. 감지는 CLI 경계(review/doctor)가
    하고 이 함수는 주입받는다 — hook core/adapter 분리와 같은 규칙이다.

    current 가 주어지면 그 host 는 리뷰어가 되지 않는다. 명시된 `cross_model.reviewer.host` 도
    마찬가지다 — 그대로 쓰면 자기 자신이 자기 코드를 리뷰하게 되어 cross-model 의 의미가 사라진다.
    """
    candidates = peer_candidates(profile, current)
    if current is None:
        # 무엇을 빼야 할지 모르면 후보 목록은 근거가 못 된다 — installed_hosts 가 없을 때
        # configured_hosts 는 active_host 자신을 돌려주므로, 그대로 고르면 자기리뷰가 된다.
        # 독립성이 걸린 호출자는 여기까지 오기 전에 running_host() 로 판별 실패를 확인하고 막아야
        # 한다. 이 폴백은 진단·표시용이며 실행 host 를 보장하지 않는다.
        peer = opposite_host(profile)
    elif len(candidates) == 1:
        peer = candidates[0]
    else:
        # 후보가 0개(설치 1개)여도 현재 host 를 리뷰어로 되돌리지는 않는다. 반대쪽을 가리키면
        # 호출자의 CLI 가용성 검사가 걸러 BLOCKED 로 가고, 그게 자기리뷰보다 정직한 실패다.
        peer = "codex" if current == "claude" else "claude"
    cross = profile.get("cross_model") if isinstance(profile, dict) else None
    reviewer = cross.get("reviewer") if isinstance(cross, dict) else None
    if not isinstance(reviewer, dict):
        return peer, None
    host = reviewer.get("host")
    model = reviewer.get("model")
    chosen = host if host in HOSTS and host != current else peer
    return chosen, (model if _valid_model(model) else None)


def component_issues(profile: dict[str, Any] | None) -> list[tuple[str, str]]:
    if not isinstance(profile, dict):
        return []
    components = profile.get("components")
    if components is None:
        return []
    if not isinstance(components, list):
        return [("FAIL", f"components 는 배열이어야 함 (받음: {type(components).__name__})")]
    issues = []
    active = active_host(profile)
    installed = set(configured_hosts(profile))
    seen_ids = set()
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            issues.append(("FAIL", f"components[{index}]는 매핑이어야 함"))
            continue
        unknown_keys = sorted((key for key in component if key not in _COMPONENT_KEYS), key=str)
        if unknown_keys:
            issues.append(("FAIL", f"components[{index}]의 알 수 없는 키: {unknown_keys} "
                                   f"(허용: {sorted(_COMPONENT_KEYS)})"))
        cid = component.get("id")
        label = cid if isinstance(cid, str) and cid.strip() else f"index {index}"
        if not isinstance(cid, str) or not _COMPONENT_ID_RE.fullmatch(cid):
            issues.append(("FAIL", f"components[{index}].id={cid!r} — 경로 안전 토큰 "
                                   "[A-Za-z0-9][A-Za-z0-9_-]{0,79} 필요"))
        elif cid in seen_ids:
            issues.append(("FAIL", f"component id 중복: {cid!r}"))
        else:
            seen_ids.add(cid)
        paths = component.get("paths")
        if paths is not None and (not isinstance(paths, list)
                                  or any(not _valid_component_path(path) for path in paths)):
            issues.append(("FAIL", f"component {label} paths는 제어문자/절대경로/부모경로가 없는 "
                                   "512자 이하 repository-relative glob 배열이어야 함"))
        tier = component.get("model")
        if tier is not None and not _valid_model(tier):
            issues.append(("FAIL", f"component {label} model={tier!r} — 안전한 work-intensity/model 토큰 필요"))
        models = component.get("runtime_models")
        if models is None:
            continue
        if not isinstance(models, dict) or not models:
            issues.append(("FAIL", f"component {label} runtime_models는 non-empty host:model 매핑이어야 함"))
            continue
        unknown = sorted((host for host in models if host not in HOSTS), key=str)
        if unknown:
            issues.append(("FAIL", f"component {label} runtime_models의 알 수 없는 host: {unknown}"))
        for host, model in models.items():
            if host in HOSTS and not _valid_model(model):
                issues.append(("FAIL", f"component {label} runtime_models.{host}={model!r} — 유효한 model id 필요"))
            if host in HOSTS and host not in installed:
                issues.append(("WARN", f"component {label} runtime_models.{host}는 installed_hosts에 없는 host 설정"))
        if active not in models:
            issues.append(("WARN", f"component {label} runtime_models에 active_host={active} 선택 없음 — host 기본 모델 사용"))
    return issues


def reviewer_issues(profile: dict[str, Any] | None) -> list[tuple[str, str]]:
    if not isinstance(profile, dict):
        return []
    options = profile.get("options")
    enabled = options.get("cross_model") if isinstance(options, dict) else False
    cross = profile.get("cross_model")
    if cross is None:
        return ([('WARN', "options.cross_model=true 이지만 cross_model.reviewer host/model 미선택 "
                          "→ opposite runtime의 CLI 기본 모델 사용(인터뷰에서 명시 선택 권장)")]
                if enabled is True else [])
    if not isinstance(cross, dict):
        return []
    reviewer = cross.get("reviewer")
    if reviewer is None:
        return ([('WARN', "options.cross_model=true 이지만 cross_model.reviewer host/model 미선택 "
                          "→ opposite runtime의 CLI 기본 모델 사용(인터뷰에서 명시 선택 권장)")]
                if enabled is True else [])
    if not isinstance(reviewer, dict):
        return [("FAIL", f"cross_model.reviewer는 매핑이어야 함 (받음: {type(reviewer).__name__})")]
    issues = []
    unknown = sorted((key for key in reviewer if key not in _REVIEWER_KEYS), key=str)
    if unknown:
        issues.append(("FAIL", f"cross_model.reviewer의 알 수 없는 키: {unknown}"))
    # host 는 중복이 아니다 — model id 가 런타임 종속이라(`gpt-5.6-terra`=codex, `opus`=claude)
    # 어느 peer 를 위한 선택인지 알아야 한다. 실제 peer 가 다르면 그 model 은 적용하지 않는다.
    # (다만 "active_host 의 반대여야 한다" 는 옛 검사는 auto 에서 정적 판정이 불가능해 폐기했다.)
    if set(reviewer) & _REVIEWER_KEYS != _REVIEWER_KEYS:
        issues.append(("FAIL", "cross_model.reviewer는 host와 model을 모두 명시해야 함"))
        return issues
    host = reviewer.get("host")
    model = reviewer.get("model")
    if host is not None:
        declared = declared_active_host(profile)
        installed = declared_installed_hosts(profile)
        if host not in HOSTS:
            issues.append(("FAIL", f"cross_model.reviewer.host={host!r} — {list(HOSTS)} 중 하나여야 함"))
        elif installed is not None and host not in installed:
            # installed_hosts 미선언 프로필은 무엇이 깔렸는지 주장한 적이 없으므로 판정하지 않는다.
            # (선언이 없을 때 configured_hosts 는 active_host 하나로 폴백해서, 그걸 근거로 삼으면
            #  legacy 프로필의 정상적인 cross-model 설정이 전부 FAIL 이 된다.)
            issues.append(("FAIL", f"cross_model.reviewer.host={host!r}가 installed_hosts에 없음 — "
                                   "설치되지 않은 runtime 에는 리뷰를 맡길 수 없음"))
        elif host == declared:
            # auto(=declared None)면 실행 시점에만 정해지므로 여기서 판정하지 않는다.
            issues.append(("FAIL", f"cross_model.reviewer.host={host!r}가 active_host와 같음 — "
                                   "자기 자신은 독립 리뷰어가 될 수 없음"))
    if not _valid_model(model):
        issues.append(("FAIL", f"cross_model.reviewer.model={model!r} — 유효한 model id 필요"))
    if enabled is not True:
        issues.append(("WARN", "cross_model.reviewer가 설정됐지만 options.cross_model=false → reviewer 선택 무동작"))
    return issues


def profile_issues(profile: dict[str, Any] | None) -> list[tuple[str, str]]:
    return component_issues(profile) + reviewer_issues(profile)


def catalog_status(catalog: dict[str, Any], model: str) -> str:
    ids = {item.get("id") for item in catalog.get("candidates", []) if isinstance(item, dict)}
    if catalog.get("verification") == "cache-confirmed":
        return "confirmed" if model in ids else "not-in-local-catalog"
    if catalog.get("verification") == "syntax-only/account-unverified":
        return "syntax-only/account-unverified" if model in ids else "account-unverified"
    return "discovery-unavailable"
