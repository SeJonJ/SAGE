"""CLI English catalog.

Key set and named placeholders must match `ko.py` exactly; `validation.py` enforces that at
build time. A key present in one catalog and absent in the other is a build failure rather than
a runtime fallback, because a fallback would ship the gap to users instead of surfacing it.
"""

MESSAGES = {
    "cli.root.description": (
        "SAGE installs and verifies rule files, hooks and agent specs in a Claude or Codex project."
    ),
    "cli.root.epilog": (
        "Typical order:\n"
        "  1. sage install --host codex --skill-scope project-local\n"
        "                                     # or --skill-scope global\n"
        "  2. sage generate --kind hook --write\n"
        "  3. sage validate\n"
        "\n"
        "Options for a single command:\n"
        "  sage <command> --help\n"
    ),
    "cli.root.help_option": "show this help message and exit",
    "cli.root.version_option": "show the installed SAGE version",
    "cli.root.lang_option": "choose the output language (default: ko)",
    "cli.root.positionals_title": "commands",
    "cli.root.optionals_title": "options",
    "cli.root.switch_hint": "한국어 도움말: sage --help",

    "cli.lang.unsupported": "Unsupported language: {value}. Available: {supported}",
    "cli.lang.missing_value": "--lang needs a value. Available: {supported}",
    "cli.lang.duplicated": "--lang may be given only once",
    "cli.lang.local_invalid": (
        "The local profile's interface.language could not be read, so output stays in Korean — "
        "check {path}"
    ),

    # EH-13 drift 진단. 라벨만 번역하고 논리 경로·건수·구분자는 언어와 무관하게 같다 —
    # 값이 달라지면 같은 drift 가 언어마다 다른 증거로 보인다.
    "cli.drift.changed": "changed",
    "cli.drift.added": "added",
    "cli.drift.removed": "removed",
    "cli.drift.more": " and {count} more",
    "cli.drift.part": "{label} {count}: {shown}{more}",
}
