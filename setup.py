"""setuptools 명령 확장 — wheel 빌드 시 엔진 리소스를 sage/_bundle/ 로 번들 (P2-10 wheel 패키징).

메타데이터는 pyproject.toml [project] 가 소유. 본 파일은 cmdclass(build_py) 만 제공한다.

배경: install/validate 가 읽는 엔진 리소스(templates·schema·scripts/sage_harness·docs/sage_harness)는
sage 패키지 *밖*에 있어 순수 wheel 에 안 들어갔다(clone/editable/sdist 만 동작). dual-use 인
scripts/sage_harness 는 테스트가 colocated 라 소스 이전이 catastrophic → **소스는 그대로 두고
빌드 시점에만** build_lib/sage/_bundle/ 로 복사해 wheel 에 포함시킨다. 런타임은 sage/_resources.py 가
번들(sage/_bundle)을 감지(env > 번들 > repo fallback). editable 은 _bundle 미생성 → repo fallback(불변).
"""
import os
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py

# install/validate 가 _resources 로 읽는 트리(레포 루트 상대) — sage_root() 가 가리키는 레이아웃 그대로.
_BUNDLE_TREES = ["templates", "schema", "scripts/sage_harness", "docs/sage_harness"]


class BundleResources(build_py):
    def run(self):
        super().run()
        bundle = os.path.join(self.build_lib, "sage", "_bundle")
        for tree in _BUNDLE_TREES:
            if os.path.isdir(tree):
                dst = os.path.join(bundle, tree)
                shutil.copytree(tree, dst, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                self.announce(f"[sage bundle] {tree} → sage/_bundle/{tree}", level=2)

    def get_outputs(self, *a, **k):
        # bdist_wheel 이 번들 파일을 wheel 에 포함하도록 산출물 목록에 추가.
        outs = list(super().get_outputs(*a, **k))
        bundle = os.path.join(self.build_lib, "sage", "_bundle")
        for root, _dirs, files in os.walk(bundle):
            for fn in files:
                outs.append(os.path.join(root, fn))
        return outs


setup(cmdclass={"build_py": BundleResources})
