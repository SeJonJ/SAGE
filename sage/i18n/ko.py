"""CLI 한국어 catalog.

한국어가 호환 기본값이다. 이 catalog 의 문장은 catalog 도입 **전의 출력을 그대로 재현**해야
하며, 새 문구를 쓰고 싶으면 그건 별개 변경이다 — 언어 배선과 문구 변경을 같은 커밋에 섞으면
회귀가 어느 쪽에서 왔는지 갈라낼 수 없다.

조각을 이어 붙이지 않고 완전한 문장 단위로 둔다. 조각 합성은 어순이 다른 언어에서 반드시
깨지고, 깨진 뒤에는 어느 조각이 원인인지 보이지 않는다.
"""

MESSAGES = {
    # 최초 발견 — 인자 없이 `sage` 를 쳤을 때. 유일하게 한영을 함께 내는 자리라 catalog 를
    # 거치지 않고 고정 문자열이지만, key 는 inventory 대조를 위해 여기에도 등록한다.
    "cli.root.description": (
        "SAGE는 Claude/Codex 프로젝트에 규칙 파일, hook, agent spec을 설치하고 검증하는 CLI입니다."
    ),
    "cli.root.epilog": (
        "기본 사용 순서:\n"
        "  1. sage install --host codex --skill-scope project-local\n"
        "                                     # 또는 --skill-scope global\n"
        "  2. sage generate --kind hook --write\n"
        "  3. sage validate\n"
        "\n"
        "각 명령의 자세한 옵션:\n"
        "  sage <command> --help\n"
    ),
    "cli.root.help_option": "도움말을 보여주고 종료합니다",
    "cli.root.version_option": "설치된 SAGE 버전을 보여줍니다",
    "cli.root.lang_option": "출력 언어를 고릅니다 (기본: ko)",
    "cli.root.positionals_title": "명령어",
    "cli.root.optionals_title": "옵션",
    "cli.root.switch_hint": "영어 도움말: sage --lang en --help",

    # 언어 선택 실패. 판정 이전 단계라 exit 2 로 끝나며 어떤 부작용도 남기지 않는다.
    "cli.lang.unsupported": "지원하지 않는 언어입니다: {value}. 사용 가능: {supported}",
    "cli.lang.missing_value": "--lang 에 값이 필요합니다. 사용 가능: {supported}",
    "cli.lang.duplicated": "--lang 은 한 번만 지정할 수 있습니다",
    "cli.lang.local_invalid": (
        "local profile 의 interface.language 를 읽을 수 없어 한국어로 표시합니다 — "
        "{path} 를 확인하세요"
    ),
}
