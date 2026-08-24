"""project hook 이 요구하는 runtime API 와 현재 `sage-hook` 의 호환성 — 순수 판정.

## 왜 이 판정이 import 앞에 서는가

소비 프로젝트의 hook core 는 자기 저장소에 설치된 SAGE 가 만든 것이고, 그걸 실행하는
`sage-hook` 은 머신에 설치된 package 가 준다. 둘의 나이가 다를 수 있다. 새 core 가 아직 없는
`sage.*` 모듈을 import 하면 옛 `sage-hook` 은 `ModuleNotFoundError` 를 만나고, 그 traceback 은
host 에 따라 그냥 "hook 이 죽었다" 로 처리된다. 정책을 실행해야 할 게이트가 조용히 빠지는
경로다. 그래서 호환성은 **core 를 import 하기 전에** 정수 비교 하나로 닫는다.

## 왜 파일이 아니라 dict 를 받는가

이 모듈은 파일을 읽지 않는다. manifest dict 를 받아 판정만 한다. 결정표가 파일시스템 없이
전수로 돌아야 사각지대가 남지 않고, 읽기는 이미 manifest 를 열고 있는 호출부가 소유한다.

## 왜 marker 부재가 legacy 가 아닌가

부재를 legacy 로 처리하면 marker 와 version 을 함께 지운 downgrade 가 통과한다. 그래서 legacy 는
**적극적으로 증명**돼야 한다 — `generator_version` 이 유효한 SemVer 이고 major 가 0 일 때만.
그 외의 부재는 전부 손상이다. 부재는 안전한 방향이 아니다.
"""
from __future__ import annotations

import re

# 1.0 의 최초 API. 단조 증가하며, 다음 경우에만 올린다.
#   - project 에 설치되는 core/runtime 이 새 `sage.*` 모듈이나 새 callable contract 를 필수로 쓴다
#   - `sage-hook` dispatch·profile preflight 의 입력 계약이 비호환으로 바뀐다
#   - 기존 runtime 이 새 project hook 을 안전하게 실행할 수 없다
# 문구 변경, 새 진단 code, 호환 optional field 만으로는 올리지 않는다.
HOOK_RUNTIME_API = 1

# 요구 SAGE **버전** 의 정본은 여기가 아니라 shared profile 의 exact `sage.required_version` 이다.
# manifest 에 최소 버전을 함께 저장하지 않는 이유는 정본이 둘이 되면 갈렸을 때 판정할 근거가
# 없기 때문이다. 호환성은 정수 API 가 소유하고, 오류 메시지의 version 안내만 기존 계약에서 온다.

_SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:[-+][0-9A-Za-z.-]+)?$")


def _is_api_int(value) -> bool:
    """1 이상의 진짜 정수인가.

    `bool` 을 먼저 걷어내는 이유는 `True == 1` 이기 때문이다. 거르지 않으면
    `{"required": true}` 가 API 1 로 조용히 통과한다.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _generator_major(value):
    """유효한 SemVer 의 major. 아니면 None — 손상과 부재를 여기서 구분하지 않는다."""
    if not isinstance(value, str):
        return None
    match = _SEMVER_RE.match(value)
    return int(match.group(1)) if match else None


def compatibility(manifest):
    """(status, evidence) 를 돌려준다. status 는 `ok|too_old|legacy|damaged`.

    판정 **순서 자체가 계약**이다.

    1. manifest 가 mapping 이 아니면 손상.
    2. marker 가 있으면 marker 만 본다 — 정수 검사 후 `required <= current` 비교.
    3. marker 가 없을 때만 legacy 를 따진다. major 0 SemVer 일 때만 legacy, 그 외 전부 손상.

    3 을 2 보다 앞에 두면(= 부재를 먼저 legacy 로 보면) marker 와 version 을 함께 지운
    downgrade 가 통과한다. 이 순서를 바꾸는 변경은 테스트가 잡는다.
    """
    if not isinstance(manifest, dict):
        return "damaged", {"reason": "manifest_not_mapping"}

    if "runtime_api" in manifest:
        marker = manifest["runtime_api"]
        if not isinstance(marker, dict):
            return "damaged", {"reason": "marker_not_mapping"}
        if "required" not in marker:
            return "damaged", {"reason": "required_missing"}
        required = marker["required"]
        if not _is_api_int(required):
            return "damaged", {"reason": "required_not_positive_int"}
        if required <= HOOK_RUNTIME_API:
            return "ok", {"required_api": required, "current_api": HOOK_RUNTIME_API}
        return "too_old", {"required_api": required, "current_api": HOOK_RUNTIME_API}

    major = _generator_major(manifest.get("generator_version"))
    if major == 0:
        return "legacy", {"current_api": HOOK_RUNTIME_API, "reason": "pre_1_0_install"}
    if major is None:
        return "damaged", {"current_api": HOOK_RUNTIME_API, "reason": "marker_missing_version_unreadable"}
    return "damaged", {"current_api": HOOK_RUNTIME_API, "reason": "marker_missing"}


def is_enforcing_block(status: str) -> bool:
    """정책을 실행하는 hook(gate·project hook)이 이 status 에서 닫혀야 하는가."""
    return status in ("too_old", "damaged")
