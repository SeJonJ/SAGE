#!/usr/bin/env python3
"""hook 트리의 standalone 계약을 기계가 지킨다.

## 왜 이 파일이 있는가

hook 런타임은 여러 주석에서 스스로 엔진 비의존을 선언해 왔다("`sage.i18n` 을 import 할 수 없어
— 엔진 없이 단독 실행"). 그런데 실제로는 `pre_implementation_gate_core` 가 모듈 최상단에서
`sage.done_criteria_contract` 를 import 했고, 실패하면 "hooks/ 기준 3단계 위에 sage 패키지가
있다" 는 폴백을 탔다. 그 가정은 **엔진 저장소에서만** 참이다. 소비 프로젝트에서 3단계 위는
프로젝트 루트이고 거기 있는 `<project>/sage/` 는 `.py` 가 0개인 설정 디렉터리다.

`.py` 가 없어도 PEP 420 namespace package 로 잡히므로 `import sage` 자체는 성공하고 실패는
서브모듈에서 난다. 그리고 그 두 번째 실패를 잡는 `except` 가 없었다.

결과는 테스트 실패가 아니라 **게이트 무력화**였다. 정상 구성된 소비 프로젝트에서 L3 변경을
주입하면 게이트가 트레이스백과 함께 종료코드 1로 죽었고, SAGE 의 차단 계약은 2이므로 1은
통과로 읽힌다. 막아야 할 변경을 막는 대신 죽으면서 통과시켰다.

**주석은 이것을 막지 못했다.** 그래서 검사로 바꾼다.

## 왜 grep 이 아니라 AST 인가

문서·주석·문자열 안의 `import sage` 를 오탐하면 검사가 곧 무시된다. 그리고 이 파일 자신의
docstring 이 그 오탐의 첫 번째 사례가 된다.
"""
import ast
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.dirname(HERE)


def _hook_sources():
    """비테스트 hook 소스 전체. 테스트는 엔진을 불러도 된다 — 물리화 대상이 아니다."""
    for directory, _subdirs, files in os.walk(HOOKS):
        if "tests" in directory.split(os.sep):
            continue
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(directory, name)


def _sage_imports(path):
    """(lineno, module, guarded). guarded = `try` 본문 안에 있는가."""
    found = []

    def walk(node, depth):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Try):
                for statement in child.body:
                    walk(statement, depth + 1)
                for statement in child.handlers + child.orelse + child.finalbody:
                    walk(statement, depth)
                continue
            names = []
            if isinstance(child, ast.Import):
                names = [alias.name for alias in child.names]
            elif isinstance(child, ast.ImportFrom):
                names = [child.module or ""]
            for name in names:
                if name == "sage" or name.startswith("sage."):
                    found.append((child.lineno, name, depth > 0))
            walk(child, depth)

    with open(path, encoding="utf-8") as handle:
        walk(ast.parse(handle.read(), path), 0)
    return found


class HookTreeHasNoEngineDependency(unittest.TestCase):
    def test_no_unguarded_sage_import(self):
        """보호되지 않은 `sage` import 는 0건이어야 한다.

        보호된 것까지 금지하지는 않는다. `hook_runtime` 의 `sage.diagnostics`·
        `overlay_materialize` 는 **엔진이 있을 때만 도는 편의 레이어**이며, 없으면 명시적으로
        skip 하도록 이미 설계돼 있다. 금지 대상은 엔진 부재를 예외로 처리하지 않는 import 다 —
        그것만이 프로세스를 죽인다.
        """
        offenders = []
        for path in _hook_sources():
            for lineno, module, guarded in _sage_imports(path):
                if not guarded:
                    offenders.append(f"{os.path.relpath(path, HOOKS)}:{lineno} {module}")
        self.assertEqual(offenders, [], "보호되지 않은 엔진 import:\n  " + "\n  ".join(offenders))

    def test_no_source_root_path_guess(self):
        """저장소 구조를 추정하는 경로 폴백을 남기지 않는다.

        "몇 단계 위에 패키지가 있다" 는 가정은 물리화된 사본에서 반드시 깨지고, 레이아웃이
        바뀔 때마다 단계 수가 또 바뀐다. 단계 수를 고치는 것은 답이 아니다.
        """
        offenders = []
        for path in _hook_sources():
            with open(path, encoding="utf-8") as handle:
                body = handle.read()
            if "_SOURCE_ROOT" in body:
                offenders.append(os.path.relpath(path, HOOKS))
        self.assertEqual(offenders, [], f"경로 추정 폴백 잔존: {offenders}")


class HookTreeImportsWithoutEngine(unittest.TestCase):
    """정적 검사가 놓치는 경로(동적 import, `sys.path` 조작)를 실제 실행으로 잡는다."""

    def test_every_module_imports_in_isolation(self):
        with tempfile.TemporaryDirectory() as workspace:
            tree = os.path.join(workspace, "hooks")
            subprocess.run([sys.executable, "-c",
                            "import shutil,sys;shutil.copytree(sys.argv[1],sys.argv[2],"
                            "ignore=shutil.ignore_patterns('tests','__pycache__'))",
                            HOOKS, tree], check=True)
            modules = sorted(
                os.path.splitext(name)[0]
                for directory in (tree, os.path.join(tree, "runtime"))
                for name in os.listdir(directory)
                if name.endswith(".py") and not name.startswith("_"))
            program = ("import sys;sys.path[:0]=['.','runtime'];"
                       "import importlib;\n"
                       "[importlib.import_module(m) for m in %r]" % modules)
            # 부모 환경이 엔진을 잡아 주면 검사가 거짓 통과한다. PYTHONPATH 를 비우고,
            # cwd 도 복사본으로 옮겨 저장소가 우연히 보이지 않게 한다.
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            completed = subprocess.run([sys.executable, "-c", program], cwd=tree,
                                       env=environment, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0,
                             f"엔진 없이 import 실패:\n{completed.stderr}")

    def test_engine_is_actually_absent_in_that_environment(self):
        """앞 검사가 의미를 가지려면 그 환경에 엔진이 정말 없어야 한다.

        이 검사가 없으면, 엔진이 우연히 보이는 환경에서 앞 검사가 통과하면서 계약이 지켜진다고
        보고한다. 부재를 확인하지 않은 통과는 통과가 아니다.
        """
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as workspace:
            completed = subprocess.run(
                [sys.executable, "-c", "import sage.done_criteria_contract"],
                cwd=workspace, env=environment, capture_output=True, text=True)
        self.assertNotEqual(completed.returncode, 0,
                            "엔진이 격리 환경에서도 보인다 — standalone 검사가 무의미해진다")


if __name__ == "__main__":
    unittest.main(verbosity=2)
