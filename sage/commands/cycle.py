"""Manage the current PDCA cycle declaration and bootstrap a Phase 00 document."""

import argparse
import glob
import json
import ntpath
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from sage import _resources
from sage.diagnostics import Diagnostic
from sage.i18n import exception_text, language_of, render_issue, tr

_ACTIONS = ("set", "show", "clear")
_RISKS = ("L1", "L2", "L3")
_GLOB_MAGIC = re.compile(r"[*?[]")


class CycleUsageError(ValueError):
    """User-facing cycle command contract failure. Carries a language-neutral Diagnostic —
    rendered at the catch site via exception_text(), never a pre-formatted sentence."""

    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__(str(diagnostic))


def register(sub, context):
    parser = sub.add_parser("cycle", help=tr(context, "cli.cycle.cycle"))
    parser.add_argument("action", metavar="{set,show,clear}",
                        help="set <stem> | show | clear")
    parser.add_argument("stem", nargs="?", default=None, help=tr(context, "cli.cycle.stem"))
    parser.add_argument("extra", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("--create", action="store_true",
                        help=tr(context, "cli.cycle.create"))
    parser.add_argument("--risk", default=None, metavar="L1|L2|L3",
                        help=tr(context, "cli.cycle.risk"))
    parser.add_argument("--path", default=None, metavar="DIR",
                        help=tr(context, "cli.cycle.path"))
    parser.add_argument("--root", default=None,
                        help=tr(context, "cli.cycle.root"))
    parser.add_argument("--document-language", dest="document_language",
                        default=None, choices=("ko", "en"),
                        help=tr(context, "cli.cycle.document_language"))
    parser.set_defaults(func=run)


def _load_cycle_state():
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    for path in (os.path.join(hooks, "runtime"), hooks):
        if path not in sys.path:
            sys.path.insert(0, path)
    import cycle_state
    return cycle_state


def _load_fast_cycle_audit():
    runtime = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
    if runtime not in sys.path:
        sys.path.insert(0, runtime)
    import fast_cycle_audit
    return fast_cycle_audit


def _active_fast_runs(root, language=None):
    """Return active Fast runs; unreadable audit is a blocking integrity error."""
    audit = _load_fast_cycle_audit()
    path = audit.audit_path(root)
    if not os.path.lexists(path):
        return [], None
    summary = audit.audit_summary(root)
    issues = audit.integrity_issues(root)
    if not summary.get("file_ok") or issues:
        detail = issues[:3] or [{"code": "fast_cycle_audit.damaged", "arguments": {"detail": item}, "evidence": ""}
                                for item in summary.get("file_issues", [])[:3]]
        rendered = "; ".join(render_issue(language, item) for item in detail)
        return [], tr(language, "cli.cycle.msg30", rendered=rendered)
    return [(run_id, summary["runs"][run_id]) for run_id in summary.get("active", [])], None


def _resolve_root(cs, explicit):
    """Resolve the declaration root without silently falling back to cwd."""
    if explicit:
        return os.path.abspath(explicit)
    root = cs.find_project_root(os.getcwd())
    if root is None:
        raise cs.DeclarationRootError(
            Diagnostic("cycle.not_a_sage_project", marker_rel=cs.MARKER_REL, cwd=os.getcwd()))
    return root


def _ignored_by_git(root, path):
    try:
        proc = subprocess.run(["git", "-C", root, "check-ignore", "-q", path],
                              capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None


def _profile_missing(root):
    return not all(os.path.exists(os.path.join(root, "sage", f"project-profile.{ext}"))
                   for ext in ("yaml", "json"))


def _warnings(root, path, language=None):
    lines = []
    ignored = _ignored_by_git(root, path)
    if ignored is False:
        lines.append(tr(language, "cli.cycle.warn_not_gitignored"))
        lines.append(tr(language, "cli.cycle.warn_not_gitignored_fix"))
    elif ignored is None:
        lines.append(tr(language, "cli.cycle.warn_git_unknown"))
    if _profile_missing(root):
        lines.append(tr(language, "cli.cycle.warn_profile_missing"))
    return lines


def _env_stem():
    return (os.environ.get("SAGE_CYCLE_STEM") or "").strip()


def _location(root, path, language=None):
    return [tr(language, "cli.cycle.location_root", root=root),
            tr(language, "cli.cycle.location_declaration", path=path)]


def _syntax_issue(args, language=None):
    action = args.action
    if action == "use":
        return tr(language, "cli.cycle.syntax_use_renamed", stem=args.stem or "<stem>")
    if action not in _ACTIONS:
        return tr(language, "cli.cycle.syntax_unknown_action", action=repr(action))
    if action == "set":
        if not args.stem:
            return tr(language, "cli.cycle.syntax_set_needs_stem")
        if args.extra:
            return tr(language, "cli.cycle.syntax_set_one_stem",
                      extra=repr(args.extra), stem=args.stem)
        if args.risk is not None and args.risk not in _RISKS:
            return tr(language, "cli.cycle.syntax_bad_risk", stem=args.stem)
        if not args.create and args.risk is not None:
            return tr(language, "cli.cycle.syntax_risk_needs_create",
                      stem=args.stem, risk=args.risk)
        if not args.create and args.path is not None:
            return tr(language, "cli.cycle.syntax_path_needs_create",
                      stem=args.stem, path=args.path)
        if args.create and args.risk is None:
            return tr(language, "cli.cycle.syntax_create_needs_risk", stem=args.stem)
        return None
    if args.stem or args.extra or args.create or args.risk is not None or args.path is not None:
        return tr(language, "cli.cycle.syntax_extra_args_not_allowed", action=action)
    return None


def run(args):
    issue = _syntax_issue(args, language_of(args))
    if issue:
        print(f"⛔ [sage cycle] {issue}", file=sys.stderr)
        return 2
    cs = _load_cycle_state()
    language = language_of(args)
    try:
        root = _resolve_root(cs, args.root)
    except cs.DeclarationRootError as exc:
        print(f"⛔ [sage cycle] {exception_text(language, exc)}", file=sys.stderr)
        return 2
    path = cs.declaration_path(root)
    try:
        active_fast, fast_error = _active_fast_runs(root, language)
    except Exception as exc:
        active_fast, fast_error = [], tr(language, "cli.cycle.msg31",
                                         error_type=type(exc).__name__, exc=exc)
    if fast_error:
        print(f"⛔ [sage cycle] {fast_error}", file=sys.stderr)
        return 2
    if active_fast and args.action == "clear":
        run_id, state = active_fast[0]
        print(tr(language_of(args), "cli.cycle.msg01", run_id=run_id, state_get=state.get('cycle_stem'), run_id2=run_id, run_id3=run_id), file=sys.stderr)
        return 2
    if active_fast and args.action == "set":
        mismatched = [(run_id, state) for run_id, state in active_fast
                      if state.get("cycle_stem") != args.stem]
        if mismatched:
            run_id, state = mismatched[0]
            print(tr(language_of(args), "cli.cycle.msg02", run_id=run_id, state_get=state.get('cycle_stem'), arg=repr(args.stem)), file=sys.stderr)
            return 2
    if args.action == "set":
        return _set(cs, args, root, path)
    if args.action == "clear":
        return _clear(cs, root, path, language_of(args))
    return _show(cs, root, path, language_of(args))


def _normalized_stem(cs, value):
    normalized = cs.cycle_binding.normalize_stem(value)
    if normalized is None:
        raise CycleUsageError(Diagnostic("cycle.stem_bad_chars", value=repr(value)))
    try:
        normalized.encode("utf-8")
    except UnicodeEncodeError:
        raise CycleUsageError(Diagnostic("cycle.stem_bad_encoding", value=repr(value)))
    if any(ch in normalized for ch in ("\u0085", "\u2028", "\u2029")):
        raise CycleUsageError(Diagnostic("cycle.stem_bad_line_sep", value=repr(value)))
    return normalized


def _read_yaml_profile(root):
    path = os.path.join(root, "sage", "project-profile.yaml")
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CycleUsageError(Diagnostic("cycle.yaml_profile_missing", path=path))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise CycleUsageError(Diagnostic("cycle.yaml_profile_read_failed",
                                         path=path, error_type=type(exc).__name__))
    if not isinstance(value, dict):
        raise CycleUsageError(Diagnostic("cycle.yaml_profile_not_mapping", path=path))
    return value, path


def _phase_globs(profile):
    pdca = profile.get("pdca")
    phases = pdca.get("phases") if isinstance(pdca, dict) else None
    if not isinstance(phases, list):
        raise CycleUsageError(Diagnostic("cycle.phases_not_list"))
    phase00_entries = [item for item in phases
                       if isinstance(item, dict) and item.get("id") == "00"]
    if len(phase00_entries) != 1:
        raise CycleUsageError(Diagnostic("cycle.phase00_count", count=len(phase00_entries)))
    phase00 = phase00_entries[0].get("glob")
    if not isinstance(phase00, str) or not phase00.strip():
        raise CycleUsageError(Diagnostic("cycle.phase00_glob_empty"))

    items = []
    for item in phases:
        if not isinstance(item, dict):
            continue
        phase_id = item.get("id")
        pattern = item.get("glob")
        if isinstance(phase_id, str) and isinstance(pattern, str) and pattern.strip():
            items.append((phase_id, pattern.strip()))
    return phase00.strip(), [pattern for phase_id, pattern in items if phase_id in {
        "00", "01", "02", "03", "04", "05", "06"
    }]


def _load_create_profile(root):
    profile, yaml_path = _read_yaml_profile(root)
    phase00, all_globs = _phase_globs(profile)
    json_path = os.path.join(root, "sage", "project-profile.json")
    if not os.path.exists(json_path):
        return phase00, all_globs, yaml_path, json_path, True
    try:
        compiled = json.loads(Path(json_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise CycleUsageError(Diagnostic("cycle.compiled_profile_read_failed",
                                         json_path=json_path, error_type=type(exc).__name__))
    if not isinstance(compiled, dict):
        raise CycleUsageError(Diagnostic("cycle.compiled_profile_not_mapping", json_path=json_path))
    compiled00, _ = _phase_globs(compiled)
    if compiled00 != phase00:
        raise CycleUsageError(Diagnostic("cycle.glob_mismatch_yaml_json"))
    return phase00, all_globs, yaml_path, json_path, False


def _canonical_rel(value):
    if not isinstance(value, str) or not value.strip():
        raise CycleUsageError(Diagnostic("cycle.path_empty"))
    raw = value.strip().replace("\\", "/")
    drive, _ = ntpath.splitdrive(raw)
    if drive or os.path.isabs(raw) or ntpath.isabs(raw):
        raise CycleUsageError(Diagnostic("cycle.path_not_relative", value=repr(value)))
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise CycleUsageError(Diagnostic("cycle.path_dotdot", value=repr(value)))
    return "/".join(parts)


def _contained(root, path):
    root_real = os.path.realpath(root)
    path_real = os.path.realpath(path)
    try:
        return os.path.commonpath([root_real, path_real]) == root_real
    except ValueError:
        return False


def _derive_directory(pattern):
    raw = _canonical_rel(pattern)
    parts = raw.split("/")
    first_magic = next((i for i, part in enumerate(parts) if _GLOB_MAGIC.search(part)), None)
    if first_magic is None:
        literal = parts[:-1]
    else:
        literal = parts[:first_magic]
    if not literal:
        raise CycleUsageError(Diagnostic("cycle.dir_not_derivable", pattern=repr(pattern)))
    return "/".join(literal)


def _target_for(root, directory, stem, pattern, cs):
    rel_dir = _canonical_rel(directory)
    target_dir = os.path.join(root, *rel_dir.split("/"))
    if not _contained(root, target_dir):
        raise CycleUsageError(Diagnostic("cycle.path_escapes_root", directory=repr(directory)))
    rel_target = f"{rel_dir}/{stem}.md"
    if not cs.cycle_binding.matches_glob(rel_target, pattern):
        raise CycleUsageError(Diagnostic("cycle.target_glob_mismatch",
                                         rel_target=repr(rel_target), pattern=repr(pattern)))
    return target_dir, os.path.join(target_dir, f"{stem}.md"), rel_target


def _glob_entries(root, pattern):
    try:
        rel_pattern = _canonical_rel(pattern)
    except CycleUsageError:
        return []
    absolute = os.path.join(root, *rel_pattern.split("/"))
    found = []
    for path in glob.glob(absolute, recursive=True):
        if not os.path.lexists(path):
            continue
        try:
            rel = os.path.relpath(path, root).replace(os.sep, "/")
        except ValueError:
            continue
        found.append((rel, path))
    return found


def _same_basename_candidates(root, pattern, stem, target=None):
    wanted = f"{stem}.md"
    candidates = {rel for rel, path in _glob_entries(root, pattern)
                  if os.path.basename(path) == wanted}
    if target and os.path.lexists(target):
        candidates.add(os.path.relpath(target, root).replace(os.sep, "/"))
    return sorted(candidates)


def _valid_phase00_docs(root, pattern, stem, cs):
    valid = []
    candidates = []
    for rel, path in _glob_entries(root, pattern):
        if os.path.basename(path) != f"{stem}.md":
            continue
        candidates.append(rel)
        if not os.path.isfile(path) or not _contained(root, path):
            continue
        try:
            content = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        identity, error = cs.cycle_binding.document_identity({"path": rel, "content": content})
        if error is None and identity == stem:
            valid.append(rel)
    return sorted(valid), sorted(set(candidates))


def _available_stems(root, patterns, stem, cs):
    if len(stem) + 2 > 160:
        return []
    used = set()
    for pattern in patterns:
        for _rel, path in _glob_entries(root, pattern):
            candidate = cs.cycle_binding.path_stem(path)
            if candidate:
                used.add(candidate)
    result = []
    suffix = 2
    while len(result) < 3 and suffix < 100000:
        candidate = f"{stem}-{suffix}"
        if len(candidate) > 160:
            break
        if candidate not in used:
            result.append(candidate)
        suffix += 1
    return result


def _phase00_prose(document_language):
    """초안의 사람용 문구. **CLI 표시 언어가 아니라 문서 선언 언어**를 따른다.

    이 문자열들은 화면에 찍히지 않고 Phase 00 파일 안으로 들어간다. 그래서 `sage/i18n` 카탈로그
    (`--lang` 이 고르는 표시 언어)로 보내면 안 된다 — 표시가 ko 인 사용자가 `Document-Language: en`
    사이클을 열면 영어 문서에 한국어 heading 이 박힌다. 막으려는 혼용을 도구가 직접 만드는 셈이다.

    marker 만 ko 로 박고 heading 을 영어로 두면 사용자는 한국어 문서를 열자마자 영어 제목을 보고
    그 위에 한국어를 쓴다 — 혼용의 출발점이 초안 자신이 된다.

    `## 5. Done Criteria` 와 `## 6. Done Criteria Revision Log` 만은 **번역하지 않는다**.
    `done_criteria_contract` 가 이 문자열을 그대로 찾는 파서 가시 marker 라, 번역하면 파서에게는
    heading 이 사라진 것으로 읽힌다. 선언 줄과 `DRAFT`·`TODO` 도 기계 어휘다.
    """
    return {
        "en": {
            "note": "fill the plan before governed source edits",
            "title": "Base Plan",
            "sections": (
                ("## 1. Context", "TODO: describe the problem and constraints."),
                ("## 2. Goal", "TODO: define the intended outcome."),
                ("## 3. Acceptance Criteria", "TODO: define requirement-level acceptance evidence."),
                ("## 4. Final Conclusion & UX Guide", "TODO: summarize the selected direction."),
            ),
            "criterion": "TODO: replace with a concrete completion criterion",
            "revision": "Initial revision 1. No replanning record.",
        },
        "ko": {
            "note": "관리 대상 소스를 고치기 전에 계획을 채우세요",
            "title": "기본 계획",
            "sections": (
                ("## 1. 배경", "TODO: 문제와 제약 조건을 적으세요."),
                ("## 2. 목표", "TODO: 달성하려는 결과를 정의하세요."),
                ("## 3. 인수 기준", "TODO: 요구사항 수준의 인수 증거를 정의하세요."),
                ("## 4. 최종 결론 및 UX 가이드", "TODO: 선택한 방향을 요약하세요."),
            ),
            "criterion": "TODO: 구체적인 완료 기준으로 바꾸세요",
            "revision": "초기 revision 1. 재계획 기록 없음.",
        },
    }[document_language if document_language in ("ko", "en") else "ko"]


def _phase00_skeleton(stem, risk, document_language):
    # 마커를 여기서 함께 박는 것이 계약이다. 선언 미러만 쓰고 Phase 00 을 비워두면 `--create` 가
    # 자기 게이트가 경고할 상태(미러는 선언, 문서는 미선언)를 스스로 만든다.
    prose = _phase00_prose(document_language)
    body = "".join(f"{heading}\n\n{todo}\n\n" for heading, todo in prose["sections"])
    return (
        f"<!-- SAGE Phase 00 skeleton: {prose['note']}. -->\n"
        f"# [{prose['title']}] {stem}\n\n"
        f"Document-Language: {document_language}\n"
        f"Cycle-Stem: `{stem}`\n"
        f"Risk Level: {risk}\n"
        "Status: DRAFT\n"
        "Done-Criteria-Revision: 1\n\n"
        f"{body}"
        "## 5. Done Criteria\n\n"
        f"- [ ] {prose['criterion']}\n\n"
        "## 6. Done Criteria Revision Log\n\n"
        f"{prose['revision']}\n"
    )


def _remove_owned_incomplete(path, identity):
    try:
        current = os.lstat(path)
    except OSError:
        return
    if (current.st_dev, current.st_ino) != identity or os.path.islink(path):
        return
    try:
        os.unlink(path)
    except OSError:
        pass


def _write_phase00_exclusive(path, payload):
    """Create a Phase 00 once; remove only this inode when the write is incomplete."""
    fd = None
    identity = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        stat = os.fstat(fd)
        identity = (stat.st_dev, stat.st_ino)
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("Phase 00 short write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
    except BaseException:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if identity is not None:
            _remove_owned_incomplete(path, identity)
        raise


def _document_language(cs, args):
    """이 사이클이 00~06 내내 쓸 문서 언어. 시작 시 한 번만 정하고 이후 바뀌지 않는다.

    `--document-language` 가 정본이다. 표시 언어를 기본값으로만 쓰는 이유는 둘의 수명이 달라서다
    — 표시 언어는 실행 하나의 성질이고 문서 언어는 사이클 전체의 성질이다. 파생으로 **고정**하면
    영어 도움말을 한 번 본 사용자가 한국어로 쓰는 사이클에 `en` 을 박고, 다음 편집부터 게이트가
    자기가 만든 충돌로 막는다.

    표시 언어조차 없으면 `ko` 다 — 언어 배선 없이 호출되는 경로(테스트·직접 호출)가 여기서
    죽으면 사이클 선언 자체가 언어 기능에 묶인다.
    """
    explicit = getattr(args, "document_language", None)
    if explicit in cs.DOCUMENT_LANGUAGES:
        return explicit
    context = getattr(args, "_language_context", None)
    language = getattr(context, "language", None)
    return language if language in cs.DOCUMENT_LANGUAGES else "ko"


def _set(cs, args, root, declaration_path):
    try:
        stem = _normalized_stem(cs, args.stem)
    except CycleUsageError as exc:
        print(f"⛔ [sage cycle] {exception_text(language_of(args), exc)}", file=sys.stderr)
        return 2
    if args.create:
        return _create_and_set(cs, args, root, declaration_path, stem)

    try:
        profile, profile_path = _read_yaml_profile(root)
        phase00, _ = _phase_globs(profile)
        valid, candidates = _valid_phase00_docs(root, phase00, stem, cs)
        if len(valid) != 1:
            print(tr(language_of(args), "cli.cycle.msg03", stem=stem, count=len(valid)))
            print(tr(language_of(args), "cli.cycle.msg04", phase00=phase00))
            for candidate in candidates:
                print(f"   - {candidate}")
            print(tr(language_of(args), "cli.cycle.msg05"))
        print(f"   profile:       {profile_path}")
    except CycleUsageError as exc:
        print(tr(language_of(args), "cli.cycle.msg06", exc=exception_text(language_of(args), exc)))
        print(tr(language_of(args), "cli.cycle.msg07"))

    try:
        cs.write_declaration(root, stem, document_language=_document_language(cs, args))
    except OSError as exc:
        print(tr(language_of(args), "cli.cycle.msg08", declaration_path=declaration_path, arg=type(exc).__name__), file=sys.stderr)
        return 2
    return _report_set(cs, root, declaration_path, stem, language_of(args))


def _create_and_set(cs, args, root, declaration_path, stem):
    try:
        phase00, all_globs, yaml_path, json_path, compiled_missing = _load_create_profile(root)
        directory = args.path if args.path is not None else _derive_directory(phase00)
        target_dir, target, rel_target = _target_for(root, directory, stem, phase00, cs)
    except CycleUsageError as exc:
        print(f"⛔ [sage cycle] {exception_text(language_of(args), exc)}", file=sys.stderr)
        return 2

    collisions = _same_basename_candidates(root, phase00, stem, target)
    if collisions:
        print(tr(language_of(args), "cli.cycle.msg09", stem=stem),
              file=sys.stderr)
        for candidate in collisions:
            print(f"  - {candidate}", file=sys.stderr)
        print(tr(language_of(args), "cli.cycle.msg10"), file=sys.stderr)
        print(f"  → sage cycle set {stem}", file=sys.stderr)
        suggestions = _available_stems(root, all_globs, stem, cs)
        if suggestions:
            print(tr(language_of(args), "cli.cycle.msg11"), file=sys.stderr)
            for candidate in suggestions:
                print(f"  - {candidate}", file=sys.stderr)
        else:
            print(tr(language_of(args), "cli.cycle.msg12"), file=sys.stderr)
        return 2

    try:
        os.makedirs(target_dir, exist_ok=True)
        if not _contained(root, target_dir):
            raise CycleUsageError(Diagnostic("cycle.dir_escapes_root"))
        _write_phase00_exclusive(
            target,
            _phase00_skeleton(stem, args.risk, _document_language(cs, args)).encode("utf-8"))
    except FileExistsError:
        print(tr(language_of(args), "cli.cycle.msg13", rel_target=rel_target),
              file=sys.stderr)
        return 2
    except (OSError, CycleUsageError) as exc:
        print(tr(language_of(args), "cli.cycle.msg14", rel_target=rel_target, arg=type(exc).__name__), file=sys.stderr)
        return 2

    print(tr(language_of(args), "cli.cycle.msg15", rel_target=rel_target))
    print(tr(language_of(args), "cli.cycle.msg16"))
    print(f"   YAML profile:  {yaml_path}")
    print(f"   compiled JSON: {json_path}")
    if compiled_missing:
        print(tr(language_of(args), "cli.cycle.msg17"))
        print("   → sage generate --kind hook --write")

    try:
        cs.write_declaration(root, stem, document_language=_document_language(cs, args))
    except OSError as exc:
        print(tr(language_of(args), "cli.cycle.msg18", declaration_path=declaration_path, arg=type(exc).__name__), file=sys.stderr)
        print(tr(language_of(args), "cli.cycle.msg19", stem=stem),
              file=sys.stderr)
        return 2
    return _report_set(cs, root, declaration_path, stem, language_of(args))


def _report_set(cs, root, path, stem, language=None):
    effective, origin, _error = cs.resolve_stem(root)
    print(tr(language, "cli.cycle.msg20", stem=stem))
    for line in _location(root, path, language):
        print(line)
    if origin == "env":
        print(tr(language, "cli.cycle.msg21", effective=effective))
    for line in _warnings(root, path, language):
        print(line)
    print(tr(language, "cli.cycle.msg22"))
    return 0


def _clear(cs, root, path, language=None):
    try:
        existed = cs.clear_declaration(root)
    except OSError as exc:
        print(tr(language, "cli.cycle.msg23", path=path, arg=type(exc).__name__),
              file=sys.stderr)
        return 2
    print(tr(language, "cli.cycle.cleared" if existed else "cli.cycle.no_declaration",
             path=path))
    env = _env_stem()
    if env:
        print(tr(language, "cli.cycle.msg24", env=env))
    return 0


def _show(cs, root, path, language=None):
    stem, origin, error = cs.resolve_stem(root)
    print("== sage cycle show ==")
    for line in _location(root, path, language):
        print(line)
    if error:
        print(tr(language, "cli.cycle.msg25", error=render_issue(language, error)))
        print(tr(language, "cli.cycle.msg26"))
    if not stem:
        print(tr(language, "cli.cycle.msg27"))
    else:
        label = {"env": "SAGE_CYCLE_STEM", "cli": ".sage/cycle.json"}[origin]
        print(tr(language, "cli.cycle.msg28", stem=stem, label=label))
        file_stem, _ = cs.read_declaration(root)
        if origin == "env" and file_stem:
            print(tr(language, "cli.cycle.msg29", file_stem=file_stem))
    for line in _warnings(root, path, language):
        print(line)
    return 0
