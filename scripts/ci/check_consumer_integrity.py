#!/usr/bin/env python3
"""Independent wheel checks + isolated CLI product tests; never an engine approval.

Only the standard library is imported by this driver. Build and consumer subprocesses
run outside the source checkout, with private homes and without inherited SAGE/Python
overrides. Logs and the machine-readable report remain in --work-dir.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile


def engine_sentinels(source):
    paths = ["AGENTS.md", "CLAUDE.md", "AGENT_GUIDE.md", "ENGINE_AGENT_GUIDE.local.md",
             "sage/project-profile.yaml", "sage/project-profile.local.yaml",
             "sage/project-profile.json", "docs/sage_harness/.manifest.json",
             ".sage", ".claude", ".codex"]
    result = {}
    for name in paths:
        path = source / name
        entries = [path]
        if path.is_dir() and not path.is_symlink():
            entries += sorted(path.rglob("*"))
        for entry in entries:
            key = entry.relative_to(source).as_posix()
            if entry.is_symlink():
                result[key] = "symlink:" + os.readlink(entry)
            elif entry.is_file():
                result[key] = hashlib.sha256(entry.read_bytes()).hexdigest()
            else:
                result[key] = "directory" if entry.is_dir() else "absent"
    return result


def check_wheel_bundle(wheel):
    """Check required resources and RECORD bytes without importing SAGE."""
    required = (
        "sage/cli.py", "sage/overlay_delivery.py",
        "sage/_bundle/templates/core/framework/AGENT_GUIDE.md",
        "sage/_bundle/schema/manifest.schema.json",
        "sage/_bundle/docs/sage_harness/.manifest.json",
        "sage/_bundle/scripts/sage_harness/hooks/pre_implementation_gate_core.py",
        "sage/_bundle/scripts/sage_harness/hooks/runtime/overlay_context.py",
    )
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        missing = [name for name in required if name not in names]
        if missing:
            raise RuntimeError("wheel bundle resources missing: " + ", ".join(missing))
        if len(names) != len(set(names)):
            raise RuntimeError("wheel bundle contains duplicate paths")
        records = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(records) != 1:
            raise RuntimeError("wheel bundle requires exactly one RECORD")
        recorded = set()
        for name, digest, size in csv.reader(io.StringIO(archive.read(records[0]).decode())):
            recorded.add(name)
            if name == records[0] and not digest and not size:
                continue
            data = archive.read(name)
            actual = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
            if digest != actual or size != str(len(data)):
                raise RuntimeError("wheel bundle RECORD mismatch: " + name)
        if recorded != set(names):
            raise RuntimeError("wheel bundle RECORD does not cover archive")


def run_step(name, command, cwd, env, logs, report, expected=0):
    done = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300)
    (logs / (name + ".stdout.log")).write_text(done.stdout, encoding="utf-8")
    (logs / (name + ".stderr.log")).write_text(done.stderr, encoding="utf-8")
    report["steps"].append({"name": name, "command": command, "cwd": str(cwd),
                            "returncode": done.returncode, "expected": expected})
    if done.returncode != expected:
        raise RuntimeError(f"{name}: exit {done.returncode}, expected {expected}\n"
                           + done.stdout[-2000:] + done.stderr[-2000:])
    return done.stdout


def check(source, work):
    if source == work or source in work.parents or work in source.parents:
        raise RuntimeError("work directory must be outside the engine source checkout")
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise RuntimeError("work directory must be empty")
    before = engine_sentinels(source)
    report = {"status": "FAIL", "steps": [], "source": str(source),
              "engine_sentinels_unchanged": False, "wheel_resources_checked": False}
    logs = work / "logs"
    logs.mkdir()
    try:
        home = work / "home"
        home.mkdir()
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("SAGE_", "PYTHON", "PIP_", "CODEX_", "CLAUDE_"))
               and key not in ("VIRTUAL_ENV", "__PYVENV_LAUNCHER__")}
        env.update(HOME=str(home), USERPROFILE=str(home), XDG_CONFIG_HOME=str(home / "config"),
                   XDG_STATE_HOME=str(home / "state"), XDG_CACHE_HOME=str(home / "cache"),
                   APPDATA=str(home / "appdata"), LOCALAPPDATA=str(home / "localappdata"),
                   TMPDIR=str(work), TEMP=str(work), TMP=str(work), PYTHONDONTWRITEBYTECODE="1")
        copied = work / "source"
        shutil.copytree(source, copied, ignore=shutil.ignore_patterns(
            ".git", ".sage", "__pycache__", "*.pyc", "*.egg-info", "build", "dist", ".venv"))
        snapshot = {path.relative_to(copied).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted(copied.rglob("*")) if path.is_file()}
        snapshot_json = json.dumps(snapshot, sort_keys=True, indent=2) + "\n"
        (work / "source-snapshot.json").write_text(snapshot_json, encoding="utf-8")
        report["source_snapshot_sha256"] = hashlib.sha256(snapshot_json.encode()).hexdigest()
        wheels = work / "wheels"
        run_step("wheel-build", [sys.executable, "-I", "-m", "pip", "--isolated", "wheel",
                                 "--wheel-dir", str(wheels), str(copied) + "[schema]"],
                 work, env, logs, report)
        candidates = list(wheels.glob("sage_harness-*.whl"))
        if len(candidates) != 1:
            raise RuntimeError("expected exactly one candidate wheel")
        check_wheel_bundle(candidates[0])
        report["wheel_resources_checked"] = True
        report["wheel_sha256"] = hashlib.sha256(candidates[0].read_bytes()).hexdigest()
        venv_dir = work / "venv"
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = str(venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        env["PATH"] = str(Path(python).parent) + os.pathsep + os.defpath
        run_step("wheel-install", [python, "-I", "-m", "pip", "--isolated", "install",
                                   "--no-index", "--find-links", str(wheels), "sage-harness[schema]"],
                 work, env, logs, report)
        probe = ("from pathlib import Path; import sys, sage; from sage import _resources; "
                 "package=Path(sage.__file__).resolve(); bundle=Path(_resources.sage_root()).resolve(); "
                 "assert Path(sys.prefix).resolve() in package.parents, package; "
                 "assert bundle == package.parent / '_bundle', bundle; "
                 "print(package); print(bundle)")
        run_step("installed-import", [python, "-I", "-c", probe], work, env, logs, report)
        consumer = work / "consumer"
        consumer.mkdir()

        def cli(name, args, expected=0):
            return run_step(name, [python, "-I", "-m", "sage", *args], consumer,
                            env, logs, report, expected)

        cli("consumer-install", ["install", "--host", "claude", "--dest", str(consumer)])
        generate = ["generate", "--kind", "hook", "--write", "--root", str(consumer),
                    "--dest", str(consumer)]
        cli("bootstrap-block", generate, expected=2)
        profile = consumer / "sage/project-profile.yaml"
        text = profile.read_text(encoding="utf-8")
        if 'name: ""' not in text or 'l2_path_globs: []' not in text:
            raise RuntimeError("consumer bootstrap fixture no longer matches installed profile")
        profile.write_text(text.replace('name: ""', 'name: "consumer-integrity"', 1).replace(
            'l2_path_globs: []', 'l2_path_globs: ["src/**"]', 1), encoding="utf-8")
        cli("consumer-generate", generate)
        validate = ["validate", "--check", "--schema", "--root", str(consumer)]
        cli("validate-clean", validate)
        runtime = consumer / "sage_harness/hooks/runtime/overlay_context.py"
        with runtime.open("a", encoding="utf-8") as stream:
            stream.write("\n# deliberate consumer runtime drift probe\n")
        cli("validate-drift", validate, expected=3)
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        report["engine_sentinels_unchanged"] = before == engine_sentinels(source)
        if not report["engine_sentinels_unchanged"]:
            report["status"] = "FAIL"
            report["error"] = "engine sentinels changed"
        (work / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not report["engine_sentinels_unchanged"]:
            raise RuntimeError("engine sentinels changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    work = args.work_dir
    if work is None:
        base = source.parent / "overlay-context-phase04-ci"
        base.mkdir(exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="consumer-", dir=base))
    print("consumer evidence: " + str(work), flush=True)
    try:
        check(source, work.resolve())
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    print("PASS: isolated consumer product checks; engine sentinels unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
