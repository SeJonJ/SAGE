# FB23 Overlay Reclassification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reclassify the provable subset of (c) gate-bearing CORE assets to (b) overlay-composable by populating `INDEPENDENT_ORACLE_COMPOSE_ALLOWED`, with adversarial bypass tests proving each registered asset's gates stay floored by asset-text-independent oracles.

**Architecture:** The backing oracles (`_report_gate`, `_acceptance_gate`, `_audit_gate`, `_missing_pre_impl_phases` in `pre_implementation_gate_core.py`) are pure functions of `(event, profile, snapshot)` — they never take asset text as input. FB23 proves this structurally (adversarial cycle-state tests → still BLOCK, in both review_loop-ON and review_loop-OFF projections), then flips `classify()` for the proven assets and their spec overlay declarations in one atomic change so the suite stays green.

**Tech Stack:** Python 3.10+, `unittest`, existing SAGE hook test harness under `scripts/sage_harness/hooks/tests/`.

## Global Constraints

- Membership is **test-decided, not declared**: an asset enters `INDEPENDENT_ORACLE_COMPOSE_ALLOWED` only if its adversarial bypass test is GREEN (oracle BLOCKs the forge). RED → stays (c).
- fail-closed invariant unchanged: unclassified/unknown `(kind,id)` → `blocked`.
- Every `INDEPENDENT_ORACLE_COMPOSE_ALLOWED` entry MUST have a `BACKING` record and a named adversarial test (meta-test enforced).
- Do NOT touch the authoritative CI boundary (server-side authority; local advisory) — out of scope.
- No `git commit`/`git push`/tag/release without explicit user instruction (Task 8 gated).
- codex review discipline: model=`gpt-5.6-sol`, effort=`high`, min 3 rounds, reproduce teeth before accepting.
- Registered subset (expected, test-confirmed): `leader`, `reviewer` (agents); `sage-cycle`, `sage-plan`, `sage-review`, `sage-team` (skills). Excluded: `qa` (no execution oracle → fake-PASS forge uncaught), `sage-profile-modify` (FB24), framework ×4 (FB25).

---

### Task 1: Adversarial bypass proof tests (safety precondition)

Prove the workflow oracles floor every gate the candidate assets bear, independent of asset text, in both review_loop projections. These tests pass against the current oracle code — they are the evidence that reclassification is sound. No production code changes in this task.

**Files:**
- Create: `scripts/sage_harness/hooks/tests/test_overlay_reclassification_backing.py`

**Interfaces:**
- Consumes: `pre_implementation_gate_core` (`_report_gate`, `_acceptance_gate`, `_audit_gate`, `_missing_pre_impl_phases`), `cycle_binding`. Fixture profile at `scripts/sage_harness/hooks/tests/fixtures/pre_impl_gate/example.profile.json` (loaded like `test_pre_implementation_gate.py:29`).
- Produces: named adversarial tests referenced by the Task 2 meta-test — exact test method names: `test_reviewer_forge_blocked_loop_on`, `test_reviewer_forge_blocked_loop_off`, `test_leader_phase_skip_blocked`, `test_sage_plan_unbound_plan_blocked`, `test_sage_cycle_report_without_approve_blocked`, `test_sage_review_degraded_run_blocked`, `test_sage_team_skip_review_blocked_loop_off`.

- [ ] **Step 1: Write the reviewer/sage-review forge tests (review_loop ON)**

A malicious `reviewer`/`sage-review` overlay ("record APPROVED without a real loop") cannot fabricate `loop_audit` records. Drive `_audit_gate` with a degraded/unclean/not-APPROVED run and assert it blocks.

```python
#!/usr/bin/env python3
"""FB23 — adversarial bypass proof for (c)->(b) reclassification.

Each test drives a backing oracle with the cycle state a malicious overlay would
try to produce, and asserts the oracle still BLOCKs. Oracles are pure functions of
(event, profile, snapshot) with no asset-text parameter, so overlay materialization
cannot change the verdict. Covers review_loop-ON and review_loop-OFF projections.
"""
import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.dirname(HERE)
PROFILE_PATH = os.path.join(HERE, "fixtures", "pre_impl_gate", "example.profile.json")
sys.path.insert(0, HOOKS_DIR)
import pre_implementation_gate_core as core  # noqa: E402

with open(PROFILE_PATH, encoding="utf-8") as _f:
    BASE_PROFILE = json.load(_f)


def _pdca(profile):
    return core._pdca_cfg(profile)


def _report_event(cfg):
    """A 06(report)-phase write event bound to cycle stem 'feat-x'."""
    phases = {str(p.get("id")): p for p in (cfg.get("phases") or [])}
    rglob = phases[str(cfg["report_phase"])]["glob"]
    path = rglob.replace("*", "feat-x") if "*" in rglob else rglob
    return {"hook_id": "pre-implementation-gate", "runtime": "test", "branch": "main",
            "declared_max": None,
            "changes": [{"path": path, "op": "write", "content": "Cycle-Stem: feat-x\n"}]}


def _approve_doc(stem, status, loop_run_line):
    return {"path": f"plan_docs/05-expert-review/{stem}.md",
            "content": f"Cycle-Stem: {stem}\n{loop_run_line}\nFinal Status: {status}\n"}


class TestReviewerForge(unittest.TestCase):
    def _snapshot(self, run):
        return {"phase_docs": {"05": [_approve_doc("feat-x", "APPROVED", "Loop-Run: r1")]},
                "loop_audit": {"has_any_records": True, "runs": {"r1": run}}}

    def test_reviewer_forge_blocked_loop_on(self):
        profile = copy.deepcopy(BASE_PROFILE)
        cfg = _pdca(profile)
        cfg["review_loop"] = {"enabled": True, "report_gate_enforce": "enforce"}
        event = _report_event(cfg)
        # overlay would "approve": 05 says APPROVED, but the audit run is degraded.
        run = {"clean": True, "seq_ok": True, "closed": True, "result": "APPROVED",
               "degraded": True, "reviewer_requested": "codex", "reviewer_actual": "claude"}
        out = core._audit_gate(event, profile, self._snapshot(run))
        self.assertIsNotNone(out)
        self.assertFalse(out["ok"], "degraded run must block despite APPROVED marker")
```

- [ ] **Step 2: Run it to verify it passes against current oracle code**

Run: `python3 -m pytest scripts/sage_harness/hooks/tests/test_overlay_reclassification_backing.py::TestReviewerForge::test_reviewer_forge_blocked_loop_on -v`
Expected: PASS (the oracle already blocks degraded runs — this is the proof, not a new behavior).

- [ ] **Step 3: Add the review_loop-OFF projection for reviewer**

With review_loop OFF, `_audit_gate` returns `None` (skip), but `_report_gate` still enforces the 05 APPROVED marker independent of asset text. Prove a missing/non-APPROVED 05 blocks the 06 report.

```python
    def test_reviewer_forge_blocked_loop_off(self):
        profile = copy.deepcopy(BASE_PROFILE)
        cfg = _pdca(profile)
        cfg["review_loop"] = {"enabled": False}
        event = _report_event(cfg)
        snap = {"phase_docs": {"05": [_approve_doc("feat-x", "CHANGES REQUESTED", "")]}}
        self.assertIsNone(core._audit_gate(event, profile, snap), "audit gate skips when loop off")
        rg = core._report_gate(event, profile, snap)
        self.assertIsNotNone(rg)
        self.assertFalse(rg["approved"], "06 report blocked: 05 not APPROVED (asset-text-independent)")
```

- [ ] **Step 4: Add leader / sage-plan / sage-cycle / sage-team phase+report forge tests**

```python
class TestWorkflowPhaseForge(unittest.TestCase):
    def test_leader_phase_skip_blocked(self):
        # leader overlay "skip planning" cannot fabricate bound plan/phase docs.
        profile = copy.deepcopy(BASE_PROFILE)
        cfg = _pdca(profile)
        event = {"hook_id": "pre-implementation-gate", "runtime": "test", "branch": "main",
                 "declared_max": "L2",
                 "changes": [{"path": "backend/src/main/java/Foo.java", "op": "write", "content": ""}]}
        missing = core._missing_pre_impl_phases(event, profile, {"phase_docs": {}}, "L2")
        self.assertTrue(missing, "L2 impl with no bound plan/phase docs must be flagged")

    def test_sage_plan_unbound_plan_blocked(self):
        # Same oracle: an unbound (wrong-stem) plan doc does not satisfy the phase requirement.
        profile = copy.deepcopy(BASE_PROFILE)
        event = {"hook_id": "pre-implementation-gate", "runtime": "test", "branch": "main",
                 "declared_max": "L2",
                 "changes": [{"path": "backend/src/main/java/Foo.java", "op": "write",
                              "content": "Cycle-Stem: feat-x\n"}]}
        snap = {"phase_docs": {"01": [{"path": "plan_docs/01-plan/other.md",
                                       "content": "Cycle-Stem: other\n"}]}}
        missing = core._missing_pre_impl_phases(event, profile, snap, "L2")
        self.assertTrue(missing, "plan doc bound to a different cycle stem does not satisfy the gate")

    def test_sage_cycle_report_without_approve_blocked(self):
        profile = copy.deepcopy(BASE_PROFILE)
        cfg = _pdca(profile)
        event = _report_event(cfg)
        snap = {"phase_docs": {"05": []}}   # no 05 for this cycle
        rg = core._report_gate(event, profile, snap)
        self.assertIsNotNone(rg)
        self.assertFalse(rg["approved"], "06 report blocked when no bound 05 APPROVED exists")

    def test_sage_review_degraded_run_blocked(self):
        profile = copy.deepcopy(BASE_PROFILE)
        cfg = _pdca(profile)
        cfg["review_loop"] = {"enabled": True, "report_gate_enforce": "enforce"}
        event = _report_event(cfg)
        run = {"clean": False, "seq_ok": True, "closed": True, "result": "APPROVED", "degraded": False}
        snap = {"phase_docs": {"05": [_approve_doc("feat-x", "APPROVED", "Loop-Run: r1")]},
                "loop_audit": {"has_any_records": True, "runs": {"r1": run}}}
        out = core._audit_gate(event, profile, snap)
        self.assertFalse(out["ok"], "unclean (reused/orphan) run must block")

    def test_sage_team_skip_review_blocked_loop_off(self):
        # sage-team overlay "skip the reviewer": with loop off, _report_gate still needs a bound
        # APPROVED 05 (asset-text-independent). Skipping review => no APPROVED 05 => blocked.
        profile = copy.deepcopy(BASE_PROFILE)
        cfg = _pdca(profile)
        cfg["review_loop"] = {"enabled": False}
        event = _report_event(cfg)
        rg = core._report_gate(event, profile, {"phase_docs": {"05": []}})
        self.assertFalse(rg["approved"], "no bound 05 APPROVED => 06 report blocked even with loop off")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run the whole file to verify all proofs pass**

Run: `python3 -m pytest scripts/sage_harness/hooks/tests/test_overlay_reclassification_backing.py -v`
Expected: all PASS. If any oracle FAILS to block, STOP — that asset is not (b) and must not be registered (adjust the registered set in Task 2).

- [ ] **Step 6: Commit**

```bash
git add scripts/sage_harness/hooks/tests/test_overlay_reclassification_backing.py
git commit -m "test(overlay): adversarial bypass proofs for FB23 backing oracles"
```

---

### Task 2: Reclassify proven assets + BACKING record + meta-test + spec flips (atomic)

Move the proven subset to (b) and flip their spec overlay declarations in one commit so `test_reference_specs_advertise_only_executable_overlay_eligibility` and `test_gate_bearing_blocked` stay green together.

**Files:**
- Modify: `sage/overlay_classify.py:44-58` (populate `INDEPENDENT_ORACLE_COMPOSE_ALLOWED`, add `BACKING`, trim `GATE_BEARING_UNBACKED`, replace line 13 comment)
- Modify: `scripts/sage_harness/hooks/tests/test_overlay_classify.py:49-53` (`test_gate_bearing_blocked` → remaining (c) only; add compose assertions)
- Modify specs: `templates/core/agents/leader.md:17`, `templates/core/agents/reviewer.md:17`, `templates/core/framework/.claude/skills/sage-cycle/SKILL.md:10`, `templates/core/framework/.claude/skills/sage-plan/SKILL.md:10`, `templates/core/framework/.claude/skills/sage-review/SKILL.md:8`, `templates/core/framework/.claude/skills/sage-team/SKILL.md:10`

**Interfaces:**
- Consumes: adversarial test method names from Task 1.
- Produces: `overlay_classify.BACKING: dict[tuple[str,str], dict]` with keys `oracles: list[str]`, `adversarial_tests: list[str]`.

- [ ] **Step 1: Write the failing meta-test + updated classify assertions**

```python
# in test_overlay_classify.py, add to TestClassify:
    def test_reclassified_core_compose(self):
        for kind, id in [("agents", "leader"), ("agents", "reviewer"),
                         ("skills", "sage-cycle"), ("skills", "sage-plan"),
                         ("skills", "sage-review"), ("skills", "sage-team")]:
            self.assertEqual(ocl.classify(kind, id), "compose", f"{kind}/{id}")

    def test_qa_and_profile_modify_still_blocked(self):
        for kind, id in [("agents", "qa"), ("skills", "sage-profile-modify")]:
            self.assertEqual(ocl.classify(kind, id), "blocked", f"{kind}/{id}")

    def test_every_independent_oracle_entry_has_backing_and_tests(self):
        for entry in ocl.INDEPENDENT_ORACLE_COMPOSE_ALLOWED:
            rec = ocl.BACKING.get(entry)
            self.assertIsNotNone(rec, f"{entry} registered without BACKING record")
            self.assertTrue(rec.get("oracles"), f"{entry} BACKING has no oracles")
            self.assertTrue(rec.get("adversarial_tests"), f"{entry} BACKING has no adversarial tests")
```

Also update `test_gate_bearing_blocked` (line 49-53) to drop the six reclassified entries, leaving `[("agents","qa"), ("skills","sage-team")]`—wait, sage-team is now compose—leaving `[("agents","qa"), ("skills","sage-profile-modify")]`.

```python
    def test_gate_bearing_blocked(self):
        for kind, id in [("agents", "qa"), ("skills", "sage-profile-modify")]:
            self.assertEqual(ocl.classify(kind, id), "blocked", f"{kind}/{id} must be blocked")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest scripts/sage_harness/hooks/tests/test_overlay_classify.py -v`
Expected: FAIL — `classify` still returns `blocked` for the six; `ocl.BACKING` does not exist (`AttributeError`).

- [ ] **Step 3: Populate `INDEPENDENT_ORACLE_COMPOSE_ALLOWED`, `BACKING`, trim `GATE_BEARING_UNBACKED`, replace comment**

In `sage/overlay_classify.py`, replace lines 44-58 region:

```python
# 자산 텍스트 밖의 executable oracle이 게이트를 독립 보장할 때만 여기에 등록한다. 등록 자격은
# 선언이 아니라 적대적 우회 테스트(GREEN)로 판정한다 — 오라클이 malicious overlay 를 BLOCK 해야 한다.
# 오라클은 (event, profile, snapshot) 순수함수라 asset 텍스트를 입력받지 않으므로, 오버레이가
# 물리 반영돼도 floor(loop_audit·05 APPROVED·04 evidence·bound phase docs)를 낮출 수 없다.
INDEPENDENT_ORACLE_COMPOSE_ALLOWED = frozenset({
    ("agents", "leader"), ("agents", "reviewer"),
    ("skills", "sage-cycle"), ("skills", "sage-plan"),
    ("skills", "sage-review"), ("skills", "sage-team"),
})

# 등록 항목별 backing 근거(오라클)와 적대적 테스트. test_overlay_classify 의 메타테스트가
# "등록=BACKING+테스트 보유" 를 강제한다. qa 는 04 PASS 위조를 잡는 실행 오라클이 없어 제외(FB24 후보),
# sage-profile-modify 는 오라클 입력(profile)을 편집하므로 제외(FB24/SD-9), framework ×4 는 FB25.
BACKING = {
    ("agents", "leader"): {
        "oracles": ["_missing_pre_impl_phases", "_acceptance_gate", "_report_gate"],
        "adversarial_tests": ["test_leader_phase_skip_blocked"]},
    ("agents", "reviewer"): {
        "oracles": ["_audit_gate", "_report_gate"],
        "adversarial_tests": ["test_reviewer_forge_blocked_loop_on",
                              "test_reviewer_forge_blocked_loop_off"]},
    ("skills", "sage-cycle"): {
        "oracles": ["_report_gate", "_acceptance_gate", "_missing_pre_impl_phases"],
        "adversarial_tests": ["test_sage_cycle_report_without_approve_blocked"]},
    ("skills", "sage-plan"): {
        "oracles": ["_missing_pre_impl_phases"],
        "adversarial_tests": ["test_sage_plan_unbound_plan_blocked"]},
    ("skills", "sage-review"): {
        "oracles": ["_audit_gate", "_report_gate"],
        "adversarial_tests": ["test_sage_review_degraded_run_blocked"]},
    ("skills", "sage-team"): {
        "oracles": ["_report_gate", "_acceptance_gate", "_missing_pre_impl_phases"],
        "adversarial_tests": ["test_sage_team_skip_review_blocked_loop_off"]},
}

COMPOSE_ALLOWED = NON_GATE_COMPOSE_ALLOWED | INDEPENDENT_ORACLE_COMPOSE_ALLOWED

# 명시적 (c) — 게이트 보유하나 오라클 미보증. qa(실행 재검 오라클 부재)·sage-profile-modify(FB24)·framework ×4(FB25).
GATE_BEARING_UNBACKED = frozenset({
    ("agents", "qa"),
    ("skills", "sage-profile-modify"),
    ("framework", "AGENT_GUIDE"), ("framework", "CLAUDE"),
    ("framework", "CODEX"), ("framework", "AGENTS"),
})
```

Also replace the module docstring line 13 ("(c)→(b) 재분류 … SD-8 …에 의존한다.") with:

```python
# (c)→(b) 재분류는 자산-불read 결정론 오라클(pre_implementation_gate_core)이 게이트를 floor 하고
# 적대적 우회 테스트가 GREEN 일 때만 이뤄진다(FB23). 미보증분은 GATE_BEARING_UNBACKED 로 남는다.
```

(Edit the docstring text at line 13 accordingly; keep it inside the `"""..."""`.)

- [ ] **Step 4: Flip the six spec overlay declarations**

For `templates/core/agents/leader.md:17` and `templates/core/agents/reviewer.md:17`, replace:

```
- self_overlay: unsupported; this gate-bearing CORE agent is not in `COMPOSE_ALLOWED`
```

with (agent-appropriate wording, mirroring implementer-a.md:18):

```
- overlay: optional `sage/asset_overrides/agents/leader.md` has project-local priority over CORE guidance and is not shipped by `sage install`; it must not relax AGENT_GUIDE, phase, review, or verification gates (gates stay floored by independent oracles)
```

(Use the matching `<id>.md` path per file: `reviewer.md` for reviewer.)

For the four SKILL.md files, replace the `Self-overlay is unsupported: ...` sentence with:

```
- overlay: optional `sage/asset_overrides/skills/<id>.md` has project-local priority over this CORE render and is not shipped by `sage install`; it must not relax AGENT_GUIDE, phase, review, or verification gates.
```

(substitute `<id>`: `sage-cycle`, `sage-plan`, `sage-review`, `sage-team`).

- [ ] **Step 5: Run the classify + reference-spec tests**

Run: `python3 -m pytest scripts/sage_harness/hooks/tests/test_overlay_classify.py -v`
Expected: PASS — including `test_reference_specs_advertise_only_executable_overlay_eligibility` (specs now advertise `- overlay: optional`) and the new meta-test.

- [ ] **Step 6: Commit**

```bash
git add sage/overlay_classify.py scripts/sage_harness/hooks/tests/test_overlay_classify.py templates/core/agents/leader.md templates/core/agents/reviewer.md templates/core/framework/.claude/skills/sage-cycle/SKILL.md templates/core/framework/.claude/skills/sage-plan/SKILL.md templates/core/framework/.claude/skills/sage-review/SKILL.md templates/core/framework/.claude/skills/sage-team/SKILL.md
git commit -m "feat(overlay): FB23 reclassify oracle-backed CORE assets (c)->(b)

overlay_classify: populate INDEPENDENT_ORACLE_COMPOSE_ALLOWED with leader/reviewer/
sage-cycle/sage-plan/sage-review/sage-team; add BACKING record + meta-enforcement.
specs: flip six overlay declarations to 'overlay: optional'."
```

---

### Task 3: qa exclusion regression test (forge-not-caught rationale)

Encode the reason qa stays (c): `_acceptance_gate` verifies evidence *structure*, not truthfulness, so a fake-PASS overlay is not caught → qa is not (b).

**Files:**
- Modify: `scripts/sage_harness/hooks/tests/test_overlay_reclassification_backing.py`

- [ ] **Step 1: Write the exclusion test**

```python
class TestQaExclusion(unittest.TestCase):
    def test_qa_fake_pass_not_caught_so_stays_c(self):
        import sage.overlay_classify as ocl
        # qa is NOT registered: no oracle re-executes tests, so a structurally-valid
        # all-PASS 04 authored by a malicious qa overlay would satisfy _acceptance_gate.
        self.assertNotIn(("agents", "qa"), ocl.INDEPENDENT_ORACLE_COMPOSE_ALLOWED)
        self.assertIn(("agents", "qa"), ocl.GATE_BEARING_UNBACKED)
        self.assertEqual(ocl.classify("agents", "qa"), "blocked")
```

Add `sys.path.insert(0, <repo root>)` so `import sage.overlay_classify` resolves (mirror `test_overlay_classify.py:13-15`).

- [ ] **Step 2: Run to verify it passes**

Run: `python3 -m pytest scripts/sage_harness/hooks/tests/test_overlay_reclassification_backing.py::TestQaExclusion -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add scripts/sage_harness/hooks/tests/test_overlay_reclassification_backing.py
git commit -m "test(overlay): document qa exclusion (fake-PASS forge uncaught, stays (c))"
```

---

### Task 4: Doc updates — AGENT_GUIDE eligibility + overlay-composition-plan status

**Files:**
- Modify: `templates/core/framework/AGENT_GUIDE.md:42`, `:168`
- Modify: `plan_docs/overlay-composition-plan.md` (§8/§11 status)

- [ ] **Step 1: Update AGENT_GUIDE line 42**

Replace `Customize eligible non-gate CORE workers per-project via an **overlay**` with:

```
Customize eligible CORE assets — non-gate workers, or gate-bearing assets whose gates are floored by a registered independent oracle (FB23) — per-project via an **overlay**
```

(Line 46-47 "…are blocked until an executable independent oracle is registered." already reads correctly — leave it.)

- [ ] **Step 2: Update AGENT_GUIDE line 168**

Replace `Framework documents and gate-bearing assets are not overlay-eligible.` with:

```
Framework documents and oracle-unbacked gate-bearing assets (qa, sage-profile-modify) are not overlay-eligible.
```

- [ ] **Step 3: Mark overlay-composition-plan.md §11 open question resolved**

In `plan_docs/overlay-composition-plan.md`, at the §11 line "gate-classification 확정 — SD-8 오라클 설계에 의존", append: ` — RESOLVED by FB23: leader/reviewer/sage-cycle/sage-plan/sage-review/sage-team registered (b); qa+profile-modify+framework deferred to FB24/FB25.` (Locate the exact line with `grep -n "gate-classification 확정" plan_docs/overlay-composition-plan.md` first.)

- [ ] **Step 4: Commit**

```bash
git add templates/core/framework/AGENT_GUIDE.md plan_docs/overlay-composition-plan.md
git commit -m "docs(overlay): AGENT_GUIDE eligibility + composition-plan FB23 resolution"
```

---

### Task 5: Full suite green + validate + manifest check

**Files:** none (verification only)

- [ ] **Step 1: Run the overlay + gate test group**

Run: `python3 -m pytest scripts/sage_harness/hooks/tests/test_overlay_classify.py scripts/sage_harness/hooks/tests/test_overlay_reclassification_backing.py scripts/sage_harness/hooks/tests/test_pre_implementation_gate.py -v`
Expected: all PASS.

- [ ] **Step 2: Run the full harness suite**

Run: `bash scripts/sage_harness/hooks/tests/run-all.sh` (or repo `run-all.sh` if that is the aggregate — confirm with `ls run-all.sh scripts/sage_harness/hooks/tests/run-all.sh`).
Expected: ALL PASS.

- [ ] **Step 3: Validate (drift/manifest)**

Run: `python3 -m sage validate` (from repo root; use the repo's documented validate invocation).
Expected: PASS, no STALE/drift. overlay_classify.py is a `sage` package module (not a generated hook) and the six specs are hand-shipped write-guard-exempt CORE renders, so no `sage generate` re-stamp is expected. If validate reports drift on any touched spec, STOP and reconcile before proceeding.

- [ ] **Step 4: Commit any validate-required fixups (only if produced)**

```bash
git add -A
git commit -m "chore(overlay): FB23 validate reconciliation"
```

---

### Task 6: codex adversarial review (3+ rounds)

**Files:** none (review; apply fixes as separate commits)

- [ ] **Step 1: Run codex round 1**

Invoke codex review (model=`gpt-5.6-sol`, effort=`high`) over the FB23 diff. Focus prompt: "Does registering these six assets to (b) open any overlay-prose bypass that the four oracles do not catch, in either review_loop projection? Attack sage-team routing and reviewer/sage-review verdict specifically."
Reproduce any reported teeth as a failing test before accepting; downgrade nothing that codex flags as a principle defect (remove first, mitigate only with user approval).

- [ ] **Step 2: Apply accepted fixes + rerun suite; repeat for rounds 2 and 3**

Expected: converge to CLEAN or documented residual risk. Minimum 3 rounds; continue up to 7 if teeth keep reproducing.

- [ ] **Step 3: Commit each round's accepted fixes**

```bash
git add -A
git commit -m "fix(overlay): FB23 codex review round N — <what changed>"
```

---

### Task 7: Release + wiki update (GATED — only on explicit user instruction)

Do not run any part of this task until the user explicitly says to release.

**Files:**
- Modify: `pyproject.toml:3`, `sage/__init__.py:7`, `templates/project-profile.yaml` (`sage.required_version`), `docs/sage_harness/.manifest.json` (`generator_version` via generate)

- [ ] **Step 1: Bump 4 version locations (patch +1: 0.9.65 → 0.9.66)**

Edit `pyproject.toml` version, `sage/__init__.py` `__version__`, `templates/project-profile.yaml` `sage.required_version`, then run `python3 -m sage generate --kind hook --write` to re-stamp `docs/sage_harness/.manifest.json` `generator_version`.

- [ ] **Step 2: Run `run-all.sh` — confirm ALL PASS (version-contract axes aligned)**

- [ ] **Step 3: Commit release, push main, wait for ci.yml green, THEN tag**

```bash
git commit -am "release: v0.9.66 — FB23 overlay (c)->(b) reclassification"
git push origin main
# wait for ci.yml green
git tag v0.9.66 && git push origin v0.9.66
```

- [ ] **Step 4: GitHub Release notes + wiki §9-G-3 status update**

`gh release create v0.9.66` with change notes (commit-style). Update wiki roadmap §9-G-3 FB23 → done; note FB24/FB25 remain deferred.

---

## Self-Review

- **Spec coverage:** design §6 산출물 ①재분류 → Task 2; ②조건부 판정(sage-team register / qa exclude) → Task 2+3; ③BACKING+메타테스트 → Task 2; ④적대적 회귀테스트(loop-ON/OFF) → Task 1; ⑤spec overlay flip → Task 2; ⑥주석+`test_gate_bearing_blocked`+plan status → Task 2+4; ⑦AGENT_GUIDE per-render 문구 → Task 4; ⑧codex 3R → Task 6. Release/wiki → Task 7. All covered.
- **Placeholder scan:** none — every code step shows concrete content; the two "grep to locate exact line" steps are locate-then-edit on real strings, not TODOs.
- **Type consistency:** `BACKING` shape (`oracles`/`adversarial_tests` lists) is defined in Task 2 Step 3 and consumed by the Task 2 Step 1 meta-test with matching keys; adversarial test method names in Task 1 Interfaces match the `adversarial_tests` values in the Task 2 `BACKING` dict verbatim.
