#!/usr/bin/env python3
"""acceptance waiver 대장의 Windows 분기를 실제 Windows 에서 확인하고 그 증거를 로그로 남긴다.

두 가지를 본다.

1. 회귀 스위트 `test_acceptance_waiver.py` 를 돌리고 통과·실패·skip 수를 찍는다. **skip 은 사유별로
   판정한다.** 전부 skip 된 실행도 unittest 에서는 성공이라, 수를 찍지 않으면 Windows native 검사가
   한 번도 돌지 않은 채 초록불이 된다. 설계상 허용한 skip 외에는 실패로 끝낸다.
2. 설치 없이 소스 트리의 CLI 로 `grant → list → audit show → record_use → revoke → list` 를 실제로
   돌려 출력을 그대로 남긴다. 대장 바이트가 LF 인지, `.lock` 이 생겼는지도 본다.

`--allow-non-windows` 는 이 스크립트 자체를 로컬에서 점검할 때만 쓴다. 그때는 POSIX 분기를
타므로 Windows 증거가 아니다.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TESTS = REPO / "scripts" / "sage_harness" / "hooks" / "tests"
RUNTIME = REPO / "scripts" / "sage_harness" / "hooks" / "runtime"

# 설계상 허용한 skip. 사유 문자열의 앞부분으로 대조한다.
ALLOWED_SKIPS = {
    # POSIX descriptor 경로 전용 테스트 — Windows 는 TestAcceptanceWaiverWindowsIo 가 맡는다.
    "descriptor-bound POSIX path",
    # 검사와 open 사이의 교체 경쟁은 수용한 잔여 위험이다.
    "검사와 open 사이의 .sage 교체 경쟁",
    # 개발자 모드가 아닌 러너에서는 symlink 생성 권한이 없다. reparse 거부는 대역 테스트가 본다.
    "symlink creation is not permitted here",
}

PROFILE = """verification:
  acceptance:
    enabled: true
    waiver: { enabled: true }
pdca:
  enabled: true
  phases:
    - { id: '01', glob: 'plan_docs/01-plan/**/*.md' }
"""

PHASE01 = """Cycle-Stem: `feature`
## Acceptance Matrix
| ID | Requirement | Required? |
|---|---|---|
| A1 | production check | yes |
"""


class SmokeFailure(RuntimeError):
    pass


def _harden_own_output():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def run_suite():
    print("== regression suite: test_acceptance_waiver.py", flush=True)
    sys.path[:0] = [str(REPO), str(RUNTIME), str(TESTS)]
    suite = unittest.defaultTestLoader.loadTestsFromName("test_acceptance_waiver")
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    allowed = set(ALLOWED_SKIPS)
    if os.name != "nt":
        allowed.add("real Windows filesystem")   # 로컬 점검용 실행에서만 — Windows 증거가 아니다
    unexpected = [(str(test), reason) for test, reason in result.skipped
                  if not any(reason.startswith(prefix) for prefix in allowed)]
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"summary: run={result.testsRun} passed={passed} failures={len(result.failures)} "
          f"errors={len(result.errors)} skipped={len(result.skipped)}")
    for test, reason in result.skipped:
        print(f"  skip: {test} — {reason}")
    if not result.wasSuccessful():
        raise SmokeFailure("regression suite failed")
    if unexpected:
        raise SmokeFailure(f"unexpected skips: {unexpected}")


def _sage(args, root):
    env = dict(os.environ, PYTHONPATH=str(REPO))
    done = subprocess.run([sys.executable, "-m", "sage", "--lang", "en", *args, "--root", str(root)],
                          cwd=str(REPO), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    print(f"$ sage {' '.join(args)}\nexit={done.returncode}\n{done.stdout}{done.stderr}", flush=True)
    if done.returncode != 0:
        raise SmokeFailure(f"sage {args[0]} {args[1] if len(args) > 1 else ''} exited {done.returncode}")
    return done.stdout


def run_cli_roundtrip():
    print("== CLI roundtrip", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sage").mkdir()
        (root / "plan_docs" / "01-plan").mkdir(parents=True)
        (root / "sage" / "project-profile.yaml").write_text(PROFILE, encoding="utf-8")
        (root / "plan_docs" / "01-plan" / "feature.md").write_text(PHASE01, encoding="utf-8")

        granted = _sage(["acceptance-waiver", "grant", "--cycle-stem", "feature", "--acceptance-id", "A1",
                         "--reason", "smoke", "--scope", "windows smoke",
                         "--remaining-evidence", "none", "--confirm-user", "ci"], root)
        waiver_id = granted.strip().splitlines()[0]
        if waiver_id not in _sage(["acceptance-waiver", "list"], root):
            raise SmokeFailure("granted waiver is not listed")

        shown = json.loads(_sage(["audit", "show", "--json", "--source", "acceptance"], root))
        source = next(item for item in shown["sources"] if item["id"] == "acceptance")
        if source["integrity"]["status"] != "valid" or source["record_count"] != 1:
            raise SmokeFailure(f"audit show did not read the waiver audit: {source}")

        # hook 이 쓰는 경로: 소비 기록과 스냅샷 조회
        sys.path[:0] = [str(RUNTIME)]
        import acceptance_waiver
        grant = next(r for r in acceptance_waiver.read_records(str(root)) if r["event"] == "grant")
        acceptance_waiver.record_use(str(root), grant, "plan_docs/06-report/feature.md")
        summary = acceptance_waiver.audit_summary(str(root))
        print(f"record_use + audit_summary: valid={summary['valid']} issues={summary['issues']}")
        if not summary["valid"]:
            raise SmokeFailure("audit invalid after record_use")

        _sage(["acceptance-waiver", "revoke", "--waiver-id", waiver_id, "--reason", "smoke done",
               "--confirm-user", "ci"], root)
        if "active=0" not in _sage(["acceptance-waiver", "list"], root):
            raise SmokeFailure("revoked waiver is still active")

        data = (root / ".sage" / "acceptance-waivers.jsonl").read_bytes()
        lock = root / ".sage" / "acceptance-waivers.jsonl.lock"
        lf, cr = data.count(b"\n"), data.count(b"\r")
        print(f"audit bytes={len(data)} lf={lf} cr={cr} lock={lock.is_file()}")
        if cr or lf != 3:
            raise SmokeFailure("audit is not three LF-terminated records")
        if os.name == "nt" and not lock.is_file():
            raise SmokeFailure("Windows lock file was not created")


def main(argv=None):
    _harden_own_output()
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-non-windows", action="store_true")
    args = parser.parse_args(argv)
    if os.name != "nt" and not args.allow_non_windows:
        print("this smoke is Windows evidence; refusing to run on a non-Windows host", file=sys.stderr)
        return 2
    print(f"python={sys.version.split()[0]} os.name={os.name}")
    try:
        run_suite()
        run_cli_roundtrip()
    except SmokeFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("OK: acceptance waiver Windows smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
