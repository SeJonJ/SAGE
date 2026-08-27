#!/usr/bin/env python3
"""no-vault Golden E2E — Obsidian 없이도 SAGE 가 온전히 돈다.

## 왜 격리가 본체인가

"vault 없이도 된다" 는 주장은 개발자 머신에서 확인할 수 없다. 그 머신에는 이미 vault 가 있고,
HOME 에 상태가 쌓여 있으며, Obsidian 환경변수가 떠 있을 수 있다. 그 상태에서 통과한 테스트는
"내 머신에서 잘 된다" 의 다른 이름이다.

그래서 이 스위트는 임시 `HOME`·`XDG_STATE_HOME`·`CODEX_HOME`·`SAGE_STATE_HOME` 아래에서 돌고,
vault 디렉터리를 만들지 않으며, Obsidian 관련 환경변수를 전부 지운다.

## 무엇을 증명하는가

1. `vault_path: ""` 는 **정상 OFF** 다. 설정 오류가 아니고 경고를 만들지 않는다.
2. 경로가 설정됐는데 없는 것은 **다른 상태**다. 둘을 같은 분기로 처리하면 정상 OFF 가 오류로
   승격되거나 오류가 조용히 무시된다.
3. vault 가 없어도 감사 정본은 `.sage/` 에 남고 `sage audit show` 가 그것을 읽는다.
4. 프로젝트와 상태 홈 **밖** 의 sentinel 트리가 바이트 하나 바뀌지 않는다. 이것이 "vault 밖에
   쓰지 않는다" 를 증명하는 유일한 수단이다.
5. Claude·Codex 양 host 에서 같다.

## 무엇을 증명하지 못하는가

이 스위트는 엔진 저장소 파일을 import path 에 두고 돈다(`PYTHONPATH=REPO`). 순수 wheel 소비
프로젝트에서의 판정은 `scripts/ci/wheel_smoke.sh` 가 소유한다 — 엔진 트리에서 안 막히는 것은
증거가 아니라는 계약이 여기에도 적용된다.

격리 대상은 vault 와 상태 홈이지 **의존성 해석 경로가 아니다**. 자식의 `HOME` 을 바꾸면
user-site(`~/Library/Python/...`, `~/.local/...`)가 통째로 사라지므로, 부모 런타임이 거기서
찾던 PyYAML 같은 의존성을 자식은 찾지 못한다. 그래서 `HOME` 에 매인 부모의 import 경로는
자식에게 그대로 물려준다. 이것은 격리를 푸는 것이 아니다 — 의존성 경로는 vault 를 만들지
않고, 프로젝트·상태 홈 밖 sentinel 검사가 그대로 남아 경계를 잰다.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

# Obsidian·vault 를 가리킬 수 있는 환경변수는 전부 지운다. 남겨 두면 이 스위트가 증명하려는
# 바로 그 조건(vault 가 없다)이 성립하지 않는다.
_STRIPPED = ("OBSIDIAN_VAULT", "OBSIDIAN_HOME", "SAGE_VAULT", "SAGE_VAULT_PATH")


def inherited_import_paths():
    """자식이 잃어버리면 안 되는 부모의 의존성 경로.

    자식은 임시 `HOME` 아래에서 돌고 `PYTHONPATH` 도 통째로 덮어쓴다. 그래서 `HOME` 에
    매인 import 경로(user-site)와 부모가 쓰던 `PYTHONPATH` 항목이 함께 사라진다. 의존성이
    거기 깔린 머신에서는 이 스위트가 격리를 재는 대신 ImportError 로 무너진다 — 기능 실패가
    아니라 재현성 결함이다. 엔진 트리(`REPO`) 아래 항목은 어차피 맨 앞에 따로 붙으므로 뺀다.
    """
    home = os.path.realpath(os.path.expanduser("~"))
    repo = os.path.realpath(REPO)
    kept = []

    def keep(entry):
        if not entry:
            return
        full = os.path.realpath(entry)
        if full == repo or full.startswith(repo + os.sep):
            return
        if not os.path.isdir(full) or full in kept:
            return
        kept.append(full)

    for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        keep(entry)
    for entry in sys.path:
        if not entry:
            continue
        full = os.path.realpath(entry)
        if full == home or full.startswith(home + os.sep):
            keep(entry)
    return kept


# 엔진 트리가 맨 앞이다 — 소비 프로젝트가 아니라 이 저장소의 코드를 재는 스위트다.
IMPORT_PATH = os.pathsep.join([REPO, *inherited_import_paths()])

PROFILE = """project:
  name: "novault"
  prefix: "nv"
components:
  - { id: core, paths: ["app/core/**"] }
risk:
  l0_pass_globs: ["*.md", "plan_docs/*"]
  l1_path_globs: ["*ui/*.src"]
  l2_path_globs: ["*core/*.src"]
  l3_filename_globs: ["*secret*"]
  plan_glob: "plan_docs/00-base_plan/**/*.md"
  l3_review_strategy: "claude_grep_first"
  review_patterns: ["review"]
file_type_map:
  - { glob: "*core/*.src", type: core }
skip_untyped: true
compliance:
  plan_gate_code_types: [core]
pdca:
  enabled: true
  phases:
    - { id: "00", glob: "plan_docs/00-base_plan/**/*.md" }
    - { id: "01", glob: "plan_docs/01-plan/**/*.md" }
    - { id: "02", glob: "plan_docs/02-design/**/*.md" }
    - { id: "03", glob: "plan_docs/03-implementation/**/*.md" }
    - { id: "04", glob: "plan_docs/04-analyze/**/*.md" }
    - { id: "05", glob: "plan_docs/05-expert-review/**/*.md" }
    - { id: "06", glob: "plan_docs/06-report/**/*.md" }
  pre_implementation_required:
    L2: ["00", "01", "02"]
    L3: ["00", "01", "02"]
  report_phase: "06"
  approve_phase: "05"
  approve_marker: "APPROVED"
knowledge_capture:
  vault_path: "__VAULT__"
  provider: obsidian
  note_convention: { folder: "wiki", filename_pattern: "{prefix} - {title}.md", flat: true }
"""


def tree_digest(path):
    """디렉터리 전체의 (상대경로 -> sha256). 목록과 내용 둘 다 증거다."""
    found = {}
    for current, _dirs, files in os.walk(path):
        for name in sorted(files):
            full = os.path.join(current, name)
            try:
                with open(full, "rb") as handle:
                    found[os.path.relpath(full, path)] = hashlib.sha256(handle.read()).hexdigest()
            except OSError:
                found[os.path.relpath(full, path)] = "<unreadable>"
    return found


class Isolated:
    """임시 HOME·상태 홈·CODEX_HOME 을 가진 소비 프로젝트 하나."""

    def __init__(self, host, vault_path=""):
        self.base = tempfile.mkdtemp(prefix=f"sage-novault-{host}-")
        self.host = host
        self.home = os.path.join(self.base, "home")
        self.state = os.path.join(self.base, "state")
        self.codex_home = os.path.join(self.base, "codex")
        self.project = os.path.join(self.base, "project")
        # sentinel 은 프로젝트와 상태 홈 **밖** 이다. 안에 두면 "밖에 쓰지 않는다" 를 증명하지
        # 못한다 — 증명하려는 경계 안쪽을 재는 셈이 된다.
        self.sentinel = os.path.join(self.base, "sentinel")
        for path in (self.home, self.state, self.codex_home, self.project, self.sentinel):
            os.makedirs(path, exist_ok=True)
        with open(os.path.join(self.sentinel, "untouched.txt"), "w", encoding="utf-8") as handle:
            handle.write("this file must not change\n")
        self.vault_path = vault_path

    @property
    def env(self):
        env = dict(os.environ, PYTHONPATH=IMPORT_PATH, HOME=self.home,
                   XDG_STATE_HOME=self.state, SAGE_STATE_HOME=self.state,
                   CODEX_HOME=self.codex_home)
        for name in _STRIPPED:
            env.pop(name, None)
        return env

    def sage(self, *args):
        return subprocess.run([sys.executable, "-m", "sage", *args],
                              cwd=self.project, env=self.env, capture_output=True, text=True)

    def write_profile(self):
        path = os.path.join(self.project, "sage", "project-profile.yaml")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(PROFILE.replace("__VAULT__", self.vault_path))

    def cleanup(self):
        shutil.rmtree(self.base, ignore_errors=True)


def install(host, vault_path=""):
    instance = Isolated(host, vault_path)
    # codex 는 CORE skill 을 전역과 프로젝트 중 어디에 둘지 명시하라고 요구한다. 여기서는
    # `project-local` 이다 — 격리가 목적인데 전역에 심으면 임시 CODEX_HOME 밖으로 나갈 여지를
    # 스스로 만드는 셈이다.
    scope = ["--skill-scope", "project-local"] if host == "codex" else []
    instance.install = instance.sage("install", "--host", host, "--prefix", "nv",
                                     "--dest", instance.project, *scope)
    instance.write_profile()
    instance.generate = instance.sage("generate", "--kind", "hook", "--write")
    instance.validate = instance.sage("validate", "--check", "--schema")
    return instance


class VaultOff(unittest.TestCase):
    """`vault_path: ""` 는 정상 OFF 다."""

    @classmethod
    def setUpClass(cls):
        cls.instances = {host: install(host) for host in ("claude", "codex")}

    @classmethod
    def tearDownClass(cls):
        for instance in cls.instances.values():
            instance.cleanup()

    def test_pipeline_succeeds_on_both_hosts(self):
        for host, instance in self.instances.items():
            with self.subTest(host=host):
                self.assertEqual(instance.install.returncode, 0, instance.install.stderr)
                self.assertEqual(instance.generate.returncode, 0, instance.generate.stderr)
                self.assertEqual(instance.validate.returncode, 0,
                                 instance.validate.stdout + instance.validate.stderr)

    def test_no_vault_directory_is_created_anywhere(self):
        for host, instance in self.instances.items():
            with self.subTest(host=host):
                for current, dirs, _files in os.walk(instance.base):
                    for name in dirs:
                        self.assertNotIn(name.lower(), ("vault", "obsidian"),
                                         f"{os.path.join(current, name)} 가 생겼다")

    def test_off_is_not_reported_as_a_configuration_error(self):
        """정상 OFF 를 오류로 승격하면 Obsidian 을 안 쓰는 사용자가 매번 경고를 본다."""
        for host, instance in self.instances.items():
            with self.subTest(host=host):
                blob = instance.validate.stdout + instance.validate.stderr
                for line in blob.splitlines():
                    if "vault" in line.lower():
                        self.assertNotIn("FAIL", line, line)
                        self.assertNotIn("STALE", line, line)

    def test_audit_is_readable_without_a_vault(self):
        for host, instance in self.instances.items():
            with self.subTest(host=host):
                run_id = instance.sage("review-loop", "open", "--risk", "L3",
                                       "--cycle-stem", "nv-demo")
                self.assertEqual(run_id.returncode, 0, run_id.stderr)
                shown = instance.sage("audit", "show", "--json")
                self.assertIn(shown.returncode, (0, 1), shown.stderr)
                data = json.loads(shown.stdout)
                review = next(item for item in data["sources"] if item["id"] == "review")
                self.assertTrue(review["present"])
                self.assertTrue(review["record_count"] >= 1)

    def test_audit_show_writes_nothing(self):
        instance = self.instances["claude"]
        instance.sage("review-loop", "open", "--risk", "L3", "--cycle-stem", "nv-write")
        before = tree_digest(instance.base)
        instance.sage("audit", "show", "--include-local")
        self.assertEqual(before, tree_digest(instance.base),
                         "조회가 격리 트리를 바꿨다")

    def test_sentinel_outside_the_project_never_changes(self):
        for host, instance in self.instances.items():
            with self.subTest(host=host):
                before = tree_digest(instance.sentinel)
                instance.sage("review-loop", "open", "--risk", "L3", "--cycle-stem", "nv-sentinel")
                instance.sage("audit", "show", "--include-local")
                instance.sage("retro", "--no-vault")
                self.assertEqual(before, tree_digest(instance.sentinel),
                                 "프로젝트 밖 sentinel 이 바뀌었다")

    def test_audit_output_never_leaks_an_absolute_path(self):
        instance = self.instances["claude"]
        instance.sage("review-loop", "open", "--risk", "L3", "--cycle-stem", "nv-leak")
        for extra in ([], ["--json"]):
            shown = instance.sage("audit", "show", "--include-local", *extra)
            blob = shown.stdout + shown.stderr
            self.assertNotIn(instance.base, blob)
            self.assertNotIn(instance.home, blob)

    def test_json_is_identical_in_both_languages(self):
        instance = self.instances["claude"]
        instance.sage("review-loop", "open", "--risk", "L3", "--cycle-stem", "nv-locale")
        korean = instance.sage("--lang", "ko", "audit", "show", "--json")
        english = instance.sage("--lang", "en", "audit", "show", "--json")
        self.assertEqual(korean.stdout.encode("utf-8"), english.stdout.encode("utf-8"))

    def test_retro_without_a_vault_records_a_skip_the_audit_can_see(self):
        instance = self.instances["claude"]
        instance.sage("review-loop", "open", "--risk", "L3", "--cycle-stem", "nv-retro")
        instance.sage("retro", "--no-vault")
        shown = instance.sage("audit", "show", "--include-local", "--json")
        data = json.loads(shown.stdout)
        self.assertIn("retro", {entry["id"] for entry in data["sources"]})


class VaultMisconfigured(unittest.TestCase):
    """경로가 설정됐는데 없는 것은 정상 OFF 와 다른 상태다."""

    @classmethod
    def setUpClass(cls):
        cls.instance = install("claude", vault_path="/nonexistent/sage-test-vault")

    @classmethod
    def tearDownClass(cls):
        cls.instance.cleanup()

    def test_a_missing_configured_vault_does_not_block_the_core_pipeline(self):
        """자동 파생물 실패가 core 를 되돌리면 vault 설정 실수 하나로 감사가 사라진다."""
        self.assertEqual(self.instance.generate.returncode, 0, self.instance.generate.stderr)
        opened = self.instance.sage("review-loop", "open", "--risk", "L3",
                                    "--cycle-stem", "nv-broken")
        self.assertEqual(opened.returncode, 0, opened.stderr)
        shown = self.instance.sage("audit", "show", "--json")
        data = json.loads(shown.stdout)
        review = next(item for item in data["sources"] if item["id"] == "review")
        self.assertTrue(review["record_count"] >= 1, "core 감사가 남지 않았다")

    def test_an_explicit_vault_request_fails_loudly(self):
        """명시 요구는 조용히 N/A 가 되지 않는다. 그러면 사용자는 안 써진 줄 모른다."""
        self.instance.sage("review-loop", "open", "--risk", "L3", "--cycle-stem", "nv-explicit")
        asked = self.instance.sage("review-loop", "show", "--vault",
                                   "/nonexistent/sage-test-vault")
        self.assertNotEqual(asked.returncode, 0,
                            "없는 vault 에 명시적으로 쓰라고 했는데 성공으로 끝났다")

    def test_a_failed_dashboard_does_not_roll_back_the_close(self):
        """자동 파생물 실패가 core 감사를 되돌리면, vault 설정 실수 하나로 끝난 리뷰가 사라진다."""
        opened = self.instance.sage("review-loop", "open", "--risk", "L3",
                                    "--cycle-stem", "nv-close")
        run_id = opened.stdout.strip().split()[-1]
        self.instance.sage("review-loop", "round", "--run-id", run_id, "--iteration", "1",
                           "--found", "1", "--survived", "0", "--accepted", "1")
        closed = self.instance.sage("review-loop", "close", "--run-id", run_id,
                                    "--result", "APPROVED", "--reason", "CONVERGED",
                                    "--iterations", "1")
        self.assertEqual(closed.returncode, 0, closed.stderr)
        # 없는 vault 에 대시보드를 쓰라고 한다. 실패해야 하지만 close 를 되돌리면 안 된다.
        self.instance.sage("review-loop", "show", "--run-id", run_id,
                           "--vault", "/nonexistent/sage-test-vault")
        shown = self.instance.sage("audit", "show", "--run-id", run_id, "--json")
        data = json.loads(shown.stdout)
        events = {item["event"] for item in data["events"]}
        self.assertIn("loop_close", events, "대시보드 실패가 close 기록을 지웠다")

    def test_the_configured_path_never_appears_in_audit_output(self):
        self.instance.sage("review-loop", "open", "--risk", "L3", "--cycle-stem", "nv-path")
        shown = self.instance.sage("audit", "show", "--include-local", "--json")
        self.assertNotIn("/nonexistent", shown.stdout)


class EngineTreeIsNotEvidence(unittest.TestCase):
    """엔진 트리에서 실행은 허용되지만 그 성공은 소비자 증거가 아니다."""

    def test_the_wheel_smoke_owns_the_consumer_judgement(self):
        with open(os.path.join(REPO, "scripts", "ci", "wheel_smoke.sh"), encoding="utf-8") as f:
            smoke = f.read()
        self.assertIn("audit show", smoke,
                      "순수 wheel 소비 프로젝트에서 audit show 를 확인하는 단계가 없다")


# 손자 프로세스까지 내려가는 재현 스크립트. 부모가 user-site 에서만 찾을 수 있는 모듈을
# 자식도 여전히 찾는지 본다. 중간 프로세스가 필요한 이유는, 이 검사가 재는 조건("의존성이
# HOME 아래에 있다")이 검사를 돌리는 머신에 있을 수도 없을 수도 있기 때문이다. 그 머신을
# 임시 HOME 으로 만들어 놓고 재야 어느 머신에서든 같은 결론이 나온다.
_PROBE = """
import json, os, subprocess, sys
sys.path.insert(0, os.environ["SAGE_PROBE_TESTS"])
try:
    import sage_novault_probe
except ImportError:
    print(json.dumps({"skip": "user-site 가 꺼진 런타임"}))
    raise SystemExit(0)
import test_no_vault_golden_e2e as suite
instance = suite.Isolated("claude")
try:
    child = subprocess.run(
        [sys.executable, "-c", "import sage_novault_probe; print(sage_novault_probe.MARK)"],
        env=instance.env, capture_output=True, text=True)
finally:
    instance.cleanup()
print(json.dumps({"rc": child.returncode, "out": child.stdout.strip(),
                  "err": child.stderr.strip()[-300:]}))
"""


class DependencyPathIsPreserved(unittest.TestCase):
    """`HOME` 을 바꿔도 부모가 쓰던 의존성 경로는 자식에 남는다.

    이 스위트는 격리를 위해 자식의 `HOME` 을 임시 디렉터리로 바꾼다. 그 순간 user-site 가
    통째로 사라져서, PyYAML 이 거기 깔린 머신에서는 vault 부재가 아니라 ImportError 로
    무너진다. 기능 결함이 아니라 재현성 결함이고, 그런 머신에서만 보이기 때문에 개발자
    머신에서는 초록으로 통과한다 — 이 스위트가 처음부터 경계하던 바로 그 함정이다.

    그래서 여기서는 그 머신을 만들어 놓고 잰다. 임시 `HOME` 의 user-site 에만 있는 모듈을
    심고, 그 `HOME` 아래에서 `Isolated.env` 를 만들어 자식이 같은 모듈을 여전히 import
    하는지 본다.
    """

    def test_a_user_site_only_dependency_survives_the_home_rewrite(self):
        base = tempfile.mkdtemp(prefix="sage-novault-usersite-")
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        version = f"{sys.version_info[0]}.{sys.version_info[1]}"
        # macOS 와 Linux 의 user-site 규약이 다르다. 둘 다 심어야 어느 쪽에서든 부모가 집는다.
        sites = (
            os.path.join(base, "Library", "Python", version, "lib", "python", "site-packages"),
            os.path.join(base, ".local", "lib", f"python{version}", "site-packages"),
        )
        for site_dir in sites:
            os.makedirs(site_dir, exist_ok=True)
            with open(os.path.join(site_dir, "sage_novault_probe.py"), "w", encoding="utf-8") as handle:
                handle.write("MARK = 'user-site'\n")

        env = dict(os.environ, HOME=base, SAGE_PROBE_TESTS=HERE)
        env.pop("PYTHONPATH", None)
        middle = subprocess.run([sys.executable, "-c", _PROBE], env=env,
                                capture_output=True, text=True)
        self.assertEqual(0, middle.returncode, middle.stderr)
        report = json.loads(middle.stdout.strip().splitlines()[-1])
        if "skip" in report:
            self.skipTest(report["skip"])
        self.assertEqual(0, report["rc"],
                         f"HOME 을 바꾸자 부모의 의존성 경로가 사라졌다: {report['err']}")
        self.assertEqual("user-site", report["out"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
