"""판정 계층이 돌려주는 **언어 중립 진단**.

이 모듈은 catalog 를 import 하지 않는다. hook 이 닿는 판정 모듈(`hook_entry`·`context_packet`·
`feedback`)이 여기에만 의존하므로, 여기서 `sage.i18n` 을 끌어오는 순간 설치된 hook 이 엔진 없이
못 도는 물건이 된다. 그건 B6 이 세운 계약을 무너뜨리는 유일한 경로다.

판정은 **무엇이 잘못됐는지**만 말하고, 어떤 언어의 어떤 문장으로 보일지는 호출부가 정한다.
같은 `code` 가 CLI 에서는 `cli.<code>`, hook 에서는 `hook.<code>` 로 렌더된다 — 공통 code 는
판정 계약이고 catalog key 는 출력 도메인의 소유다.

`evidence` 는 외부 도구가 돌려준 원문이다. **번역하지 않는다.** 번역하면 사용자가 검색할 수 있는
원문이 사라지고, 같은 오류가 언어마다 다른 문자열로 보여 대조가 불가능해진다.
"""
from __future__ import annotations


class Diagnostic:
    """(code, arguments, evidence). 완성 문장을 담지 않는다.

    `arguments` 는 catalog template 에 넘길 named argument 다. 위치 인자를 쓰지 않는 이유는
    어순이 다른 언어에서 반드시 깨지기 때문이고, 깨진 뒤에는 어느 조각이 원인인지 보이지 않는다.
    """

    __slots__ = ("code", "arguments", "evidence")

    def __init__(self, code: str, /, evidence: str = "", **arguments):
        self.code = code
        self.arguments = arguments
        self.evidence = evidence

    def __repr__(self):
        return (f"Diagnostic(code={self.code!r}, arguments={self.arguments!r}, "
                f"evidence={self.evidence!r})")

    def __str__(self):
        """렌더를 거치지 않고 문자열에 섞여도 code 는 남는다 — 바닥값이지 정상 경로가 아니다.

        이행 중에는 진단이 아직 이관되지 않은 f-string 안으로 들어갈 수 있다. 그때 `repr` 이
        화면에 나가면 사용자는 무엇이 잘못됐는지 읽을 수 없다. 최소한 code 는 남겨서, 화면이
        덜 친절해질지언정 원인이 사라지지는 않게 한다.
        """
        return f"{self.code}: {self.evidence}" if self.evidence else self.code

    def __eq__(self, other):
        return (isinstance(other, Diagnostic) and other.code == self.code
                and other.arguments == self.arguments and other.evidence == self.evidence)

    def __hash__(self):
        return hash((self.code, tuple(sorted(self.arguments.items())), self.evidence))


def render(diagnostic, translate, prefix):
    """진단 하나를 사람이 읽는 한 줄로. `translate(key, **arguments) -> str` 를 받는다.

    catalog 를 여기서 고르지 않고 호출부가 넘긴 `translate` 를 쓰는 이유는, 이 모듈이 어느
    도메인의 catalog 도 알면 안 되기 때문이다. 아는 순간 hook 경로에 그 import 가 따라 들어온다.

    evidence 는 문장 뒤에 원문 그대로 붙인다 — 번역 대상이 아니고, 사용자가 그대로 검색할 수
    있어야 한다.
    """
    if not isinstance(diagnostic, Diagnostic):
        return str(diagnostic)          # 이행 중 남은 문자열도 화면에서 사라지지 않게 한다
    # 하부 판정이 낸 진단을 상위 판정이 인자로 실어 올릴 수 있다(`이유: <하부 진단>`). 중첩된
    # 진단을 여기서 함께 렌더하지 않으면 상위 문장만 번역되고 안쪽은 code 로 남는다 — 한 줄에
    # 두 언어가 섞인다. 조립은 판정이 아니라 렌더의 일이다.
    arguments = {name: render(value, translate, prefix) if isinstance(value, Diagnostic) else value
                 for name, value in diagnostic.arguments.items()}
    text = translate(f"{prefix}.{diagnostic.code}", **arguments)
    return f"{text}: {diagnostic.evidence}" if diagnostic.evidence else text


def codes(diagnostics):
    """진단 목록의 code 집합. catalog 완전성 oracle 이 쓴다."""
    return {item.code for item in diagnostics if isinstance(item, Diagnostic)}
