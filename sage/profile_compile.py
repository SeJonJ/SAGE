"""Compile authoring profile fields into the dependency-free hook runtime profile."""

from copy import deepcopy


def _dedupe(values):
    return list(dict.fromkeys(values))


def materialize_profile(profile):
    compiled = deepcopy(profile)
    risk = compiled.get("risk")
    if not isinstance(risk, dict):
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
    for domain in risk.get("domains") or []:
        if not isinstance(domain, dict):
            continue
        level = domain.get("risk_level")
        if level in path_by_level:
            path_by_level[level].extend(domain.get("path_globs") or [])
        if level in content_by_level:
            content_by_level[level].extend(domain.get("content_keywords") or [])

    # Equal triggers are owned by their highest level. L0 remains an independent
    # early-return carve-out in the classifier and is intentionally untouched.
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
    return compiled
