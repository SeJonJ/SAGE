"""CLI loader for the dependency-free hook-runtime checklist contract."""

from sage import asset_paths

import importlib.util
import os


def _contract(root=None):
    if root:
        # 신 경로를 고정하면 이행 전 프로젝트에서 이 경로가 없고, 아래 폴백이 **조용히 엔진
        # 사본**을 쓴다. 크래시가 없어 눈에 띄지 않지만 프로젝트가 가진 계약이 무시된다 —
        # 부재가 오류가 아니라 다른 파일로 떨어지는 형태다.
        path = os.path.join(asset_paths.layout_hooks_dir(root, asset_paths.detect_layout(root)),
                            "runtime", "checklist_contract.py")
    else:
        path = ""
    if not os.path.isfile(path):
        from sage import _resources
        path = os.path.join(_resources.hooks_src_dir(), "runtime", "checklist_contract.py")
    spec = importlib.util.spec_from_file_location("sage_checklist_runtime_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unsafe_glob(value, root=None):
    return _contract(root).unsafe_glob(value)


def checklist_target_issues(profile, root=None):
    return _contract(root).checklist_target_issues(profile)
