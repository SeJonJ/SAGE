"""표시 언어 결정 — 판정이 끝난 뒤에만 쓰이는 presentation context.

언어는 표현만 바꾸고 판단과 증거는 바꾸지 않는다. 그래서 이 모듈은 catalog 도, profile 의
거버넌스 값도 해석하지 않는다. 오직 "이 실행은 어느 언어로 보여줄 것인가" 하나만 정하고
immutable context 로 넘긴다.

우선순위를 여기 한 곳에만 두는 이유는, 각 command 가 자기 profile 을 다시 읽어 자기 순서를
만들면 같은 입력이 진입 경로마다 다른 언어로 렌더되기 때문이다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import yaml

from sage.profile_layers import INTERFACE_LANGUAGES, LOCAL_PROFILE_NAME

__all__ = ["DEFAULT_LANGUAGE", "INTERFACE_LANGUAGES", "LanguageContext", "read_local_language",
           "resolve", "supported"]

DEFAULT_LANGUAGE = "ko"

# 설정이 없으면 한국어. 이건 fallback 이 아니라 계약이다 — 기존 프로젝트는 아무것도 추가하지
# 않아도 지금과 같은 출력을 받아야 한다.
SOURCE_CLI = "cli"
SOURCE_LOCAL_PROFILE = "local_profile"
SOURCE_DEFAULT = "default"
SOURCE_CYCLE = "cycle"


@dataclass(frozen=True)
class LanguageContext:
    """무엇을 어떤 근거로 골랐는지. 진단이 "왜 영어가 아닌가"에 답할 수 있어야 한다."""

    language: str = DEFAULT_LANGUAGE
    source: str = SOURCE_DEFAULT
    fallback_used: bool = False

    @property
    def is_default(self) -> bool:
        return self.source == SOURCE_DEFAULT


def supported(value: object) -> bool:
    return value in INTERFACE_LANGUAGES


def local_profile_path(root: str) -> str:
    return os.path.join(root, "sage", LOCAL_PROFILE_NAME)


def read_local_language(root: str) -> tuple[str | None, bool]:
    """(언어, 손상됨). 읽을 수 없거나 값이 이상하면 (None, True) — 조용히 기본값으로 뭉개지 않는다.

    hook 과 CLI 가 같은 파일을 각자 읽으므로 여기서 파싱을 단일화한다. 실패를 부재와 구분하는
    이유는 그 둘의 사용자 안내가 다르기 때문이다 — 부재는 정상이고 손상은 고쳐야 한다.
    """
    path = local_profile_path(root)
    if not os.path.isfile(path):
        return None, False
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except Exception:
        return None, True
    if not isinstance(loaded, dict):
        return None, True
    interface = loaded.get("interface")
    if interface is None:
        return None, False
    if not isinstance(interface, dict) or "language" not in interface:
        return None, True
    language = interface["language"]
    if not supported(language):
        return None, True
    return language, False


def resolve(explicit: str | None = None, root: str | None = None) -> LanguageContext:
    """명시 `--lang` → 대상 프로젝트 local profile → `ko`.

    `explicit` 은 이미 지원 언어로 검증된 값만 들어온다. 검증은 bootstrap scan 이 담당하며,
    거기서 걸러야 잘못된 값이 전체 parser 를 만든 뒤에야 드러나는 일을 막는다.
    """
    if supported(explicit):
        return LanguageContext(language=explicit, source=SOURCE_CLI)
    if root:
        language, damaged = read_local_language(root)
        if supported(language):
            return LanguageContext(language=language, source=SOURCE_LOCAL_PROFILE)
        if damaged:
            return LanguageContext(language=DEFAULT_LANGUAGE, source=SOURCE_DEFAULT,
                                   fallback_used=True)
    return LanguageContext(language=DEFAULT_LANGUAGE, source=SOURCE_DEFAULT)
