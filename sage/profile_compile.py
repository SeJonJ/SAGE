"""Compile authoring profile fields into the dependency-free hook runtime profile."""

from copy import deepcopy

from sage.diagnostics import Diagnostic


_RISK_STRING_LIST_FIELDS = (
    "l0_pass_globs",
    "l0_exclude_globs",
    "l1_path_globs",
    "l2_path_globs",
    "l3_filename_globs",
    "l2_content_keywords",
    "l3_content_keywords",
)


class ProfileCompileError(ValueError):
    """Raw profile cannot be safely materialized without coercing invalid values.

    `issues` 는 언어 중립 진단 목록이다. 이 모듈은 hook 이 닿는 경로(`hook_entry`)가 import 하므로
    어느 도메인의 catalog 도 알 수 없다 — 문장은 잡은 쪽이 만든다.

    `str(exc)` 는 code 를 낸다. 사람이 읽는 문장은 아니지만, 이 예외를 그대로 찍던 경로에서도
    무엇이 잘못됐는지가 사라지지 않는다.
    """

    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("; ".join(getattr(item, "code", str(item)) for item in self.issues))


def _string_list_issue(value, path):
    if not isinstance(value, list):
        return Diagnostic("compile.not_string_list", path=path, actual=type(value).__name__)
    bad = [idx for idx, item in enumerate(value)
           if not isinstance(item, str) or not item.strip()]
    if bad:
        return Diagnostic("compile.bad_string_items", path=path, indexes=bad)
    return None


def materialization_issues(profile):
    """Return deterministic raw-type issues for fields consumed by the compiler."""
    if not isinstance(profile, dict):
        return [Diagnostic("compile.profile_not_mapping", actual=type(profile).__name__)]
    if "risk" not in profile:
        return []
    risk = profile.get("risk")
    if not isinstance(risk, dict):
        return [Diagnostic("compile.risk_not_mapping", actual=type(risk).__name__)]

    issues = []
    for field in _RISK_STRING_LIST_FIELDS:
        if field in risk:
            issue = _string_list_issue(risk[field], f"risk.{field}")
            if issue:
                issues.append(issue)

    if "domains" not in risk:
        return issues
    domains = risk.get("domains")
    if not isinstance(domains, list):
        issues.append(Diagnostic("compile.domains_not_list", actual=type(domains).__name__))
        return issues
    for idx, domain in enumerate(domains):
        path = f"risk.domains[{idx}]"
        if not isinstance(domain, dict):
            issues.append(Diagnostic("compile.domain_not_mapping", path=path,
                                     actual=type(domain).__name__))
            continue
        level = domain.get("risk_level")
        if level not in ("L1", "L2", "L3"):
            issues.append(Diagnostic("compile.risk_level_invalid", path=path, actual=repr(level)))
        for field in ("path_globs", "content_keywords"):
            if field not in domain:
                continue
            issue = _string_list_issue(domain[field], f"{path}.{field}")
            if issue:
                issues.append(issue)
    return issues


def _dedupe(values):
    return list(dict.fromkeys(values))


def materialize_profile(profile):
    issues = materialization_issues(profile)
    if issues:
        raise ProfileCompileError(issues)
    compiled = deepcopy(profile)
    risk = compiled.get("risk")
    if risk is None:
        return compiled

    path_by_level = {
        "L1": list(risk.get("l1_path_globs") or []),
        "L2": list(risk.get("l2_path_globs") or []),
        "L3": list(risk.get("l3_filename_globs") or []),
    }
    content_by_level = {
        "L2": list(risk.get("l2_content_keywords") or []),
        "L3": list(risk.get("l3_content_keywords") or []),
    }
    l0_excludes = list(risk.get("l0_exclude_globs") or [])
    for domain in risk.get("domains") or []:
        level = domain.get("risk_level")
        if level in path_by_level:
            domain_paths = domain.get("path_globs") or []
            path_by_level[level].extend(domain_paths)
            l0_excludes.extend(domain_paths)
        if level in content_by_level:
            content_by_level[level].extend(domain.get("content_keywords") or [])

    # Equal triggers are owned by their highest level. Domain paths explicitly bypass
    # a broader L0 carve-out, then resolve to this compiled higher-risk owner.
    for level in ("L3", "L2", "L1"):
        higher = set().union(*(path_by_level[h] for h in ("L1", "L2", "L3")
                               if int(h[1]) > int(level[1])))
        path_by_level[level] = [value for value in _dedupe(path_by_level[level]) if value not in higher]
    content_by_level["L3"] = _dedupe(content_by_level["L3"])
    content_by_level["L2"] = [value for value in _dedupe(content_by_level["L2"])
                               if value not in set(content_by_level["L3"])]

    risk["l1_path_globs"] = path_by_level["L1"]
    risk["l2_path_globs"] = path_by_level["L2"]
    risk["l3_filename_globs"] = path_by_level["L3"]
    risk["l2_content_keywords"] = content_by_level["L2"]
    risk["l3_content_keywords"] = content_by_level["L3"]
    risk["l0_exclude_globs"] = _dedupe(l0_excludes)
    return compiled
