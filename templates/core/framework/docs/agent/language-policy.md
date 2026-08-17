# Language Policy

Single source of truth for which language SAGE writes in, and for the rule that separates a
translatable sentence from a token that must never change. Every other document links here
instead of restating it.

The governing principle is one line:

> **Language changes presentation. It never changes a judgement or its evidence.**

Given the same input, `ko` and `en` must produce the same decision, status, exit code,
`message_key`, named arguments, JSON structure, generated files, audit records and profile hash.
Only the human-readable sentence differs.

## Which language applies where

| Surface | Language | Why |
|---|---|---|
| CLI output, hook messages, CORE skill conversation | the selected language | what a user reads |
| Rules, contracts and procedures (SSOT Markdown) | English | one language for the semantic source every reviewer reads |
| Hook specs, CORE skill and agent specs | English | same — these are the contract, not the conversation |
| Code comments and internal docstrings | Korean | the developers who maintain this code work in Korean; this is the default, not an exception |
| User-facing documentation | Korean authoring source, reviewed English mirror | the mirror records a normalized source hash for sync, not a quality approval |
| Phase 00–06 documents | fixed once per cycle, see below | a cycle whose documents change language mid-run cannot be reviewed |
| Historical plan, review, report and audit evidence | left in its original language | translating it would break the hashes and audit bindings that make it evidence |

Code comments being Korean is a deliberate decision, not a gap awaiting translation. What *is*
still required of a comment is unrelated to its language: a comment that merely repeats the code,
describes behavior that no longer exists, records change history, or is commented-out code should
be deleted regardless of what language it is written in.

## Choosing the language

Supported values are exactly the lowercase strings `ko` and `en`. Absent configuration means
`ko`, so an existing project keeps working with no change.

The persistent setting lives in `sage/project-profile.local.yaml`, which Git ignores:

```yaml
interface:
  language: en
```

It never appears in `sage/project-profile.yaml`, the compiled `project-profile.json`, a manifest,
a generated artifact, or the profile hash. A language preference is a property of the person at
the keyboard, not of the project's governance.

| Entry point | Resolution order |
|---|---|
| Ordinary CLI and help | explicit `--lang` → the target project's local profile → `ko` |
| SAGE hook | the target project's local profile → `ko` |
| CORE skill | the skill invocation's `--lang` → local profile → `ko` |
| Bare `sage` | bilingual, Korean and English together |
| `sage --version` | language-neutral |

The CLI grammar places `--lang` before the subcommand:

```text
sage [--lang {ko,en}] <command> [command options]
```

`sage doctor --lang en` is not the supported form. `$sage-init --lang en` and
`$sage-review --lang en` are skill arguments interpreted by the AI runtime, not subcommands of
the `sage` executable.

Only `sage-init` and `sage-init-local` may persist a language preference, only to the local
profile, and only after explicit user approval. Every other skill applies `--lang` to that one
invocation.

**An AI runtime resolves this before its first user-visible line.** A skill's resolver runs when
the skill starts, which is already too late for the greeting, the "reading the profile" note and
the progress line a session prints on the way there — those land in the default language while the
setting says otherwise, and the user reads a Korean session that was configured as English.
So the session entrypoints (`CLAUDE.md`, `AGENTS.md`) read the local profile silently before any
output, and emit nothing until they have. Switching mid-session does not repair a first line
already sent in the wrong language. Once resolved, the language holds for every question, progress
note, warning, error and closing summary in that session, including turns after a tool failure, a
resume or a compaction.

An unsupported explicit language is a bilingual error on stderr with exit 2. An invalid value in
the local profile falls back to `ko` with a bilingual diagnostic; `sage validate` reports it as a
configuration failure, but a hook's verdict and exit code do not change.

## Phase 00–06 document language

A cycle decides its document language once, at the start, in this order: an explicit `--lang` on
the cycle-opening skill, then the local profile, then `ko`.

- Phase 00 records exactly one `Document-Language: ko|en` line outside any code fence. **That
  line is the durable source of truth.**
- `.sage/cycle.json` mirrors it as `document_language` for resume and cross-host handoff. A
  mirror that disagrees with Phase 00 is a hard conflict, not a tiebreak — neither side is
  repaired automatically.
- Every Phase 01–06 document of the same `Cycle-Stem` carries the identical marker and its prose
  in that language.
- **Prose includes the human-facing structure**, not just paragraphs: section headings, list
  labels, table headers and checklist text. A Korean document under English headings is the
  mixed state this rule exists to prevent, and the gate's prose sampling does not catch it.
  The exceptions are the marker lines above and the two headings a parser reads by their exact
  string — `## 5. Done Criteria` and `## 6. Done Criteria Revision Log`. Translating either one
  reads to `done_criteria_contract` as a missing heading, so both stay English in every language.
- Changing the local preference mid-cycle, or passing a conflicting `--lang`, does not change an
  active cycle. The conflict is reported and the declared language continues to apply.
- A mismatch between Phase 00, the cycle state, the context packet, or two documents of the same
  stem fails closed before any write, review or completion.
- A cycle with no marker is read as `ko`. Its historical documents are never rewritten; the
  marker and Korean prose start from the first document written after the resume.

## Never translated

These are machine vocabulary. They read the same in every language, and changing one changes
behavior rather than presentation:

```text
APPROVED, BLOCKED, FAIL, PASS, WARN, NOT TESTED, N/A
L0, L1, L2, L3
Cycle-Stem, Document-Language, Risk Level, Done-Criteria-Revision, Final Status, Loop-Run, Phase00-Hash
message_key, run_id, cycle_stem, phase00_hash
commands, options, paths, filenames, YAML and JSON keys, enum values, IDs, hashes
```

Three further cases are Korean by necessity and must survive untouched:

- **Skill trigger phrases** — the literal strings a Korean user types to invoke a skill. Translate
  one and the skill stops responding to the phrase its users know.
- **Parser-visible section markers** — the vault note headings checked by
  `note_convention.required_structure`, and `## 요약` and `## 제안`, which `sage retro --check`
  parses directly. A translated heading reads to the parser as a missing heading.
- **Korean matched by a regex or emitted verbatim** — the risk-declaration clear phrase, the
  sentence-final endings the capture filter inspects, and the declaration-origin labels a hook
  prints. A spec quoting these quotes them exactly.

In JSON, keys, enums and statuses are never translated. Only a human-readable `message`, or a
`reason` a host contract defines as prose, is rendered in the selected language. Automation must
key off `status` and `message_key`, never off prose.

## Adding a message

A user-facing sentence belongs in a catalog, never hard-coded at the emit site.

- CLI keys live in `sage/i18n/{ko,en}.py` under the `cli.` namespace.
- Hook keys live in the installed hook runtime's own locale module. That runtime must remain
  independently executable in a consumer project and must never import the main `sage` package.
- The two domains hold different key sets. An existing hook-compatible key such as `ok_l1` or
  `ok_l0` stays in the hook domain and is not duplicated into the CLI.
- `sage/i18n/validation.py` owns the whole build-time check: `ko` and `en` must carry identical
  key sets and identical named placeholders within each domain, the two domains must not collide,
  every template must format safely, and every hook key the code can emit must exist in both hook
  catalogs.
- Write whole sentences. Concatenating translated fragments produces text that is correct in
  neither language.
- A missing key in the selected language falls back to Korean with a diagnostic; a key missing in
  Korean too prints the language-neutral `[SAGE] message_key=<key>`. In every case the verdict and
  the exit code are preserved, and an unknown key is never dropped in silence.
