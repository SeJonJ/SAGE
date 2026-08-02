"""CLI loader for the dependency-free hook-runtime checklist contract."""

import importlib.util
import os


def _contract(root=None):
    if root:
        path = os.path.join(root, "scripts", "sage_harness", "hooks", "runtime",
                            "checklist_contract.py")
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
