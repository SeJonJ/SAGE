"""진단 code 의 severity 와 복구 순서 — code 에 붙는 계약.

## 왜 `Diagnostic` 에 필드를 더하지 않았는가

`sage/diagnostics.py` 의 `Diagnostic(code, evidence, **arguments)` 는 이 저장소에서 439 곳이
쓰는 시그니처다. 여기에 `severity`·`recovery` 를 필수 필드로 밀어 넣으면 그 전부가 개수 대상이
되고, 더 나쁘게는 **recovery 의 소유권이 439 곳으로 흩어진다.** 그러면 "같은 recovery id 는 같은
명령을 낸다" 를 강제할 구조적 수단이 사라진다 — 검사로 뒤늦게 잡을 수는 있어도, 애초에 갈릴 수
없는 자리에 두는 편이 낫다.

그래서 둘 다 여기 있다. 그리고 둘 다 **진단 인스턴스의 속성이 아니라 code 의 속성**이다. 같은
code 가 어떤 호출부에서는 WARN 이고 다른 곳에서는 BLOCK 이면 그 code 는 안정 식별자이길
그만둔다.

## 왜 자기 검사가 import 시점이 아닌가

`contract_issues()` 는 계약 위반을 돌려주지만 import 할 때 raise 하지 않는다. catalog 나 매핑이
깨진 사용자의 CLI 가 통째로 죽으면, 진단 도구가 진단 불가로 죽는 가장 나쁜 실패 모드가 된다.
위반은 테스트가 잡고, 런타임은 안전한 fallback 으로 내려간다.

## `Finding` 이 따로 있는 이유

`Diagnostic.evidence` 는 문자열이다 — 외부 도구가 돌려준 원문을 번역 없이 화면에 붙이기 위한
것이다. 반면 JSON 이 실어야 하는 evidence 는 기계가 읽는 **구조화된 사실**이다. 둘은 다른
물건이라 같은 필드에 넣을 수 없고, `Diagnostic` 을 바꿀 수도 없다. `Finding` 은 조회 명령
계층(`status`·`explain`)이 쓰는 표현이고, 렌더가 필요할 때 `.diagnostic()` 으로 기존 경로에
그대로 얹힌다.
"""
from __future__ import annotations

import re

from sage.diagnostics import Diagnostic

INFO = "INFO"
WARN = "WARN"
BLOCK = "BLOCK"

_RANK = {BLOCK: 0, WARN: 1, INFO: 2}


class RecoveryStep:
    """복구 한 단계.

    `command` 가 `None` 이면 사람이 직접 해야 하는 일이고 렌더에서 `Action:` 으로 갈라진다.
    `Next:` 는 실행 가능한 명령만 받는다 — 붙여넣을 수 없는 문장을 `Next:` 로 내면 그 토큰은
    "다음에 칠 것" 이라는 의미를 잃는다.
    """

    __slots__ = ("id", "command", "description_key", "arguments", "mutating")

    def __init__(self, id, command, description_key, /, *, mutating, **arguments):
        self.id = id
        self.command = command
        self.description_key = description_key
        self.arguments = arguments
        self.mutating = mutating

    def __repr__(self):
        return f"RecoveryStep(id={self.id!r}, command={self.command!r}, mutating={self.mutating!r})"

    def to_json(self):
        return {"id": self.id, "command": self.command, "mutating": self.mutating}


class Finding:
    """조회 계층의 진단 한 건 — (code, 구조화 evidence, 렌더 인자).

    severity 와 recovery 를 자기 필드로 갖지 않는다. 둘 다 code 에서 조회한다.
    """

    __slots__ = ("code", "evidence", "arguments")

    def __init__(self, code, /, evidence=None, arguments=None):
        self.code = code
        self.evidence = dict(evidence or {})
        self.arguments = dict(arguments or {})

    def __repr__(self):
        return f"Finding(code={self.code!r}, evidence={self.evidence!r})"

    @property
    def severity(self):
        return severity_of(self.code)

    def diagnostic(self):
        """기존 렌더 경로에 얹기 위한 변환. catalog key 는 여전히 `prefix + code` 다."""
        return Diagnostic(self.code, **self.arguments)

    def to_json(self):
        return {
            "code": self.code,
            "severity": self.severity,
            "evidence": self.evidence,
            "recovery": [step.to_json() for step in recovery_for(self.code)],
        }


# --- 복구 단계 정본 ---------------------------------------------------------
#
# 같은 id 는 어디서든 같은 command 를 낸다. 그 보장을 얻으려고 step 을 여기서 한 번만 만들고
# 매핑이 그 객체를 공유한다 — 두 곳에서 따로 지으면 언젠가 갈린다.

_UPGRADE_PACKAGE = RecoveryStep(
    "upgrade-package", "pipx upgrade sage-harness", "recovery.upgrade_package", mutating=True)
_UPGRADE_CHECK = RecoveryStep(
    "upgrade-check", "sage upgrade --check", "recovery.upgrade_check", mutating=False)
_REINSTALL_HOST = RecoveryStep(
    "reinstall-host", "sage install --host {host} --force --dest .",
    "recovery.reinstall_host", mutating=True)
_REGENERATE_HOOK = RecoveryStep(
    "regenerate-hook", "sage generate --kind hook --write",
    "recovery.regenerate_hook", mutating=True)
_STATUS = RecoveryStep("status", "sage status", "recovery.status", mutating=False)
_VALIDATE = RecoveryStep(
    "validate", "sage validate --kind all --check --schema", "recovery.validate", mutating=False)

_DOCTOR = RecoveryStep("doctor", "sage doctor", "recovery.doctor", mutating=False)
_CYCLE_SHOW = RecoveryStep("cycle-show", "sage cycle show", "recovery.cycle_show", mutating=False)
_CYCLE_SET = RecoveryStep("cycle-set", "sage cycle set <stem>", "recovery.cycle_set", mutating=True)
# command 가 None 인 단계는 사람이 해야 하는 일이다 — 렌더에서 `Action:` 으로 갈린다.
_FIX_SAGE_SECTION = RecoveryStep("fix-sage-section", None, "recovery.fix_sage_section",
                                 mutating=False)
_FIX_REQUIRED_VERSION = RecoveryStep("fix-required-version", None,
                                     "recovery.fix_required_version", mutating=False)
_FIX_SHARED_PROFILE = RecoveryStep("fix-shared-profile", None, "recovery.fix_shared_profile",
                                   mutating=False)
_WRITE_PHASES = RecoveryStep("write-phases", None, "recovery.write_phases", mutating=False)
_FIX_CANONICAL_SPEC = RecoveryStep("fix-canonical-spec", None, "recovery.fix_canonical_spec",
                                   mutating=False)
_REGENERATE = RecoveryStep("regenerate", "sage generate --kind <kind> --write",
                           "recovery.regenerate", mutating=True)

# 안전한 직접 복구가 없을 때 내려앉는 바닥값. BLOCK 인데 매핑이 비어 있으면 렌더가 이걸 쓴다.
FALLBACK_RECOVERY = (_STATUS,)


# --- code → severity -------------------------------------------------------
#
# 등재되지 않은 code 는 INFO 다. 439 개 기존 진단이 등재돼 있지 않고, 등재되지 않았다는 이유로
# 화면이 바뀌면 안 되기 때문이다. severity 는 정렬·exit 집계·recovery 요구에만 쓰이고 렌더는
# 읽지 않는다.
#
# CLI 에는 "BLOCK 으로 종료" 라는 기존 규약이 없다. 그래서 대상을 관찰로 추론하지 않고 여기
# 등재로 **선언**한다. 등재되면 recovery 를 갖고 `Next:` 를 내야 하며, 등재되지 않으면 아니다.
# 기존 CLI 오류를 소급해 BLOCK 으로 올리지 않는다 — 승격은 사용자에게 보이는 exit 변경이다.

SEVERITY = {
    # --- runtime API -------------------------------------------------------
    "runtime.api_too_old": BLOCK,
    "runtime.api_marker_missing": BLOCK,
    "runtime.api_marker_damaged": BLOCK,
    "runtime.api_marker_absent_legacy": WARN,
    "version.runtime_mismatch": BLOCK,
    # --- version contract --------------------------------------------------
    # severity 의 정본은 `sage/version_contract.py` 다. 여기 값은 그 판정을 진단 어휘로 옮긴
    # 것이지 두 번째 판정이 아니다 — FAIL→BLOCK, WARN→WARN, INFO→INFO 로 정확히 대응하며
    # `test_status.py` 가 그 대응을 대조한다.
    "version.sage_section_not_mapping": BLOCK,
    "version.required_not_semver": BLOCK,
    "version.required_absent": INFO,
    "version.axis_malformed": WARN,
    "version.axis_unknown": WARN,
    "version.axis_differs": WARN,
    # --- project -----------------------------------------------------------
    "project.not_installed": WARN,
    "project.manifest_unreadable": BLOCK,
    "project.manifest_not_mapping": BLOCK,
    # --- profile -----------------------------------------------------------
    "profile.shared_missing": BLOCK,
    "profile.shared_invalid": BLOCK,
    "profile.layer_invalid": BLOCK,
    "profile.layer_warning": WARN,
    "profile.compiled_missing": BLOCK,
    "profile.compiled_unreadable": BLOCK,
    "profile.compiled_stale": WARN,
    "profile.compiled_uncomparable": WARN,
    # --- host --------------------------------------------------------------
    "host.profile_unreadable": BLOCK,
    "install.hook_registration_missing": BLOCK,
    # --- gate / guard ------------------------------------------------------
    "gate.phase_incomplete": BLOCK,
    "guard.generated_asset": BLOCK,
    "cycle.binding_missing": BLOCK,
    # --- cycle -------------------------------------------------------------
    "cycle.state_unavailable": BLOCK,
    "cycle.declaration_unreadable": BLOCK,
    "cycle.declaration_damaged": BLOCK,
}


RECOVERY = {
    # 순서가 계약이다 — 읽기 전용 확인 → mutation → 재검증.
    "runtime.api_too_old": (_UPGRADE_CHECK, _UPGRADE_PACKAGE, _REINSTALL_HOST, _REGENERATE_HOOK,
                            _STATUS),
    "runtime.api_marker_missing": (_STATUS, _REINSTALL_HOST, _REGENERATE_HOOK, _VALIDATE),
    "runtime.api_marker_damaged": (_STATUS, _REINSTALL_HOST, _REGENERATE_HOOK, _VALIDATE),
    "version.runtime_mismatch": (_UPGRADE_CHECK, _UPGRADE_PACKAGE, _STATUS),

    # `status` 가 내는 진단의 복구에는 `sage status` 를 넣지 않는다. 방금 그 명령을 실행한
    # 사람에게 그 명령을 다시 치라고 하는 것은 다음 행동이 아니다.
    "version.sage_section_not_mapping": (_FIX_SAGE_SECTION, _VALIDATE),
    "version.required_not_semver": (_FIX_REQUIRED_VERSION, _VALIDATE),
    "project.manifest_unreadable": (_DOCTOR, _REINSTALL_HOST, _VALIDATE),
    "project.manifest_not_mapping": (_DOCTOR, _REINSTALL_HOST, _VALIDATE),
    "profile.shared_missing": (_REINSTALL_HOST, _VALIDATE),
    "profile.shared_invalid": (_FIX_SHARED_PROFILE, _VALIDATE),
    "profile.layer_invalid": (_FIX_SHARED_PROFILE, _VALIDATE),
    "profile.compiled_missing": (_REGENERATE_HOOK, _VALIDATE),
    "profile.compiled_unreadable": (_REGENERATE_HOOK, _VALIDATE),
    "host.profile_unreadable": (_FIX_SHARED_PROFILE, _VALIDATE),
    "install.hook_registration_missing": (_DOCTOR, _REINSTALL_HOST, _VALIDATE),
    "cycle.state_unavailable": (_DOCTOR, _REINSTALL_HOST, _VALIDATE),
    "cycle.declaration_unreadable": (_CYCLE_SHOW, _CYCLE_SET, _VALIDATE),
    "cycle.declaration_damaged": (_CYCLE_SHOW, _CYCLE_SET, _VALIDATE),
    "cycle.binding_missing": (_CYCLE_SHOW, _CYCLE_SET),
    "gate.phase_incomplete": (_CYCLE_SHOW, _WRITE_PHASES),
    "guard.generated_asset": (_FIX_CANONICAL_SPEC, _REGENERATE, _VALIDATE),
}


def severity_of(code) -> str:
    return SEVERITY.get(code, INFO)


def recovery_for(code):
    return RECOVERY.get(code, ())


def order(findings, severity_of=severity_of):
    """`BLOCK → WARN → INFO`, 같은 severity 안에서는 code 오름차순.

    입력 순서에 의존하지 않는다. 의존하면 같은 저장소 상태가 실행마다 다른 JSON 을 내고, 그건
    기계가 대조할 수 없다.
    """
    return tuple(sorted(findings,
                        key=lambda f: (_RANK.get(severity_of(f.code), _RANK[INFO]), f.code)))


# --- 자기 검사 --------------------------------------------------------------

# 기본 복구로 제시하면 안 되는 것들. 파괴적 명령, 감사 로그 삭제, 그리고 판정을 우회시키는
# generic override 다. 복구는 사용자를 정상 경로로 되돌리는 것이지, 막은 이유를 지우는 게 아니다.
_FORBIDDEN_COMMAND = re.compile(
    r"(^|[\s;&|])(rm|rmdir|shred|truncate)([\s;&|]|$)"
    r"|git\s+reset\s+--hard"
    r"|git\s+clean\b"
    r"|sage\s+override\b",
    re.IGNORECASE)


def contract_issues(severity=None, recovery=None):
    """계약 위반 목록. 빈 리스트가 통과다.

    인자를 받는 이유는 테스트가 가짜 매핑으로 검사 자체를 검사할 수 있어야 하기 때문이다.
    검사에 이빨이 있는지 확인하지 않으면, 검사가 통째로 무치여도 초록으로 보인다.
    """
    severity = SEVERITY if severity is None else severity
    recovery = RECOVERY if recovery is None else recovery
    issues = []

    for code, level in sorted(severity.items()):
        if level not in (INFO, WARN, BLOCK):
            issues.append(f"{code}: 알 수 없는 severity {level!r}")
        if level != BLOCK:
            continue
        steps = recovery.get(code, ())
        if not steps:
            issues.append(f"{code}: BLOCK 인데 recovery 가 없다")
            continue
        if not any(step.command for step in steps):
            issues.append(f"{code}: BLOCK 복구에 실행 가능한 명령이 하나도 없다")
        # 복구는 `확인 → mutation → 재검증` 세 국면이다. 그래서 읽기 전용이 mutation 뒤에
        # 오는 것은 정상이다 — 그게 재검증이다. 금지되는 것은 국면이 **섞이는** 것이다:
        # 고치고, 보고, 또 고치는 순서는 사용자가 어디까지 했는지 잃어버린다.
        blocks = 0
        previous = False
        for step in steps:
            if step.mutating and not previous:
                blocks += 1
            previous = step.mutating
        if blocks > 1:
            issues.append(f"{code}: mutation 단계가 {blocks} 덩어리로 흩어져 있다 — "
                          "확인·수정·재검증 세 국면으로 모으세요")

    for code in sorted(set(recovery) - set(severity)):
        issues.append(f"{code}: severity 등재 없이 recovery 만 있다")

    commands = {}
    for code, steps in sorted(recovery.items()):
        for step in steps:
            if step.command and _FORBIDDEN_COMMAND.search(step.command):
                issues.append(f"{code}: 복구 단계 {step.id!r} 가 금지된 명령을 제시한다 "
                              f"({step.command!r})")
            if step.id in commands and commands[step.id] != step.command:
                issues.append(f"recovery id {step.id!r} 가 서로 다른 명령을 낸다 — "
                              f"{commands[step.id]!r} vs {step.command!r}")
            commands.setdefault(step.id, step.command)

    return issues


def render_recovery(code, translate, prefix, **context):
    """복구 순서를 사람이 읽는 줄 목록으로.

    실행 가능한 명령은 `Next:`, 사람이 해야 하는 일은 `Action:` 으로 갈린다. 붙여넣을 수 없는
    문장을 `Next:` 로 내면 그 토큰이 "다음에 칠 것" 이라는 의미를 잃는다.

    `Next:` 와 `Action:` 토큰은 **번역하지 않는다.** 번역하면 사용자가 화면에서 검색할 수 없고,
    로그에서 자동 수집도 깨진다. 언어를 타는 것은 뒤에 붙는 설명뿐이다.

    BLOCK 인데 매핑이 비어 있으면 바닥값(`sage status`)으로 내려간다. catalog 나 매핑이 깨졌다는
    이유로 사용자에게 아무 다음 행동도 주지 않는 것이 가장 나쁜 실패다.
    """
    steps = recovery_for(code)
    if not steps and severity_of(code) == BLOCK:
        steps = FALLBACK_RECOVERY
    lines = []
    for step in steps:
        if step.command:
            try:
                command = step.command.format(**context)
            except (KeyError, IndexError, ValueError):
                command = step.command
            lines.append(f"Next: {command}")
        else:
            lines.append(f"Action: {translate(f'{prefix}.{step.description_key}', **step.arguments)}")
    return lines
