"""CLI 표시 언어 — context 결정과 catalog 렌더.

판정은 언어 중립 결과(`message_key` + named argument)를 만들고, 렌더는 그 뒤에만 일어난다.
그래서 이 package 를 import 하지 않아도 모든 판정이 성립해야 하며, 설치된 hook runtime 은
실제로 import 하지 않는다(소비 프로젝트에서 main package 없이 단독 실행되어야 하므로).
"""
from sage.i18n import en as _en
from sage.i18n import ko as _ko
from sage.i18n.context import (DEFAULT_LANGUAGE, LanguageContext, resolve, supported)

CATALOGS = {"ko": _ko.MESSAGES, "en": _en.MESSAGES}

__all__ = ["CATALOGS", "DEFAULT_LANGUAGE", "LanguageContext", "resolve", "supported", "tr"]


def tr(context: LanguageContext | str | None, key: str, **arguments) -> str:
    """선택 언어로 `key` 를 렌더한다. 실패해도 판정과 exit code 는 건드리지 않는다.

    누락 시 한국어로 폴백하고, 한국어에도 없으면 언어 중립 최소 메시지를 낸다. 알 수 없는 key 를
    조용히 버리면 화면에서 문장 하나가 사라진 채 성공처럼 보인다 — 그건 부재가 통과로 떨어지는
    바로 그 형태라, 무엇이 없었는지 key 이름을 그대로 드러낸다.
    """
    language = getattr(context, "language", context) or DEFAULT_LANGUAGE
    template = CATALOGS.get(language, {}).get(key)
    if template is None:
        template = CATALOGS[DEFAULT_LANGUAGE].get(key)
    if template is None:
        return f"[SAGE] message_key={key}"
    try:
        return template.format(**arguments)
    except (KeyError, IndexError, ValueError):
        # 인자 불일치는 build gate 가 잡아야 할 결함이다. 런타임에서는 문장을 포기하되
        # 무엇을 렌더하려다 실패했는지 남긴다.
        return f"[SAGE] message_key={key}"
