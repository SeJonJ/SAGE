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

_ACTIONS = ("set", "show", "clear")
_RISKS = ("L1", "L2", "L3")
_GLOB_MAGIC = re.compile(r"[*?[]")


class CycleUsageError(ValueError):
    """User-facing cycle command contract failure."""


def register(sub):
    parser = sub.add_parser("cycle", help="지금 작업 중인 사이클을 게이트에 알려줍니다")
    parser.add_argument("action", metavar="{set,show,clear}",
                        help="set <stem> | show | clear")
    parser.add_argument("stem", nargs="?", default=None, help="set 할 Cycle-Stem")
    parser.add_argument("extra", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("--create", action="store_true",
                        help="Phase 00 뼈대를 만든 뒤 stem 을 선언합니다")
    parser.add_argument("--risk", default=None, metavar="L1|L2|L3",
                        help="--create 로 만들 Phase 00의 위험도")
    parser.add_argument("--path", default=None, metavar="DIR",
                        help="Phase 00을 만들 프로젝트 root 상대 디렉터리")
    parser.add_argument("--root", default=None,
                        help="대상 프로젝트 루트 (기본: cwd 에서 가장 가까운 SAGE 설치본)")
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


def _active_fast_runs(root):
    """Return active Fast runs; unreadable audit is a blocking integrity error."""
    audit = _load_fast_cycle_audit()
    path = audit.audit_path(root)
    if not os.path.lexists(path):
        return [], None
    summary = audit.audit_summary(root)
    issues = audit.integrity_issues(root)
    if not summary.get("file_ok") or issues:
        return [], "Fast Cycle audit 무결성 실패: " + "; ".join(issues[:3] or summary.get("file_issues", [])[:3])
    return [(run_id, summary["runs"][run_id]) for run_id in summary.get("active", [])], None


def _resolve_root(cs, explicit):
    """Resolve the declaration root without silently falling back to cwd."""
    if explicit:
        return os.path.abspath(explicit)
    root = cs.find_project_root(os.getcwd())
    if root is None:
        raise cs.DeclarationRootError(
            f"여기는 SAGE 프로젝트가 아닙니다 — '{cs.MARKER_REL}' 를 가진 상위 디렉터리를 "
            f"찾지 못했습니다 (cwd: {os.getcwd()}).\n"
            f"→ SAGE 설치본 안에서 실행하거나 `--root <경로>` 로 지정하세요.")
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


def _warnings(root, path):
    lines = []
    ignored = _ignored_by_git(root, path)
    if ignored is False:
        lines.append("⚠️  이 파일이 git 에 무시되지 않습니다 — 커밋되면 남의 clone 에서 "
                     "엉뚱한 사이클에 결속됩니다.")
        lines.append("    → `sage install --force` 로 .gitignore 관리 블록을 복구하세요.")
    elif ignored is None:
        lines.append("ℹ️  git 무시 여부를 확인하지 못했습니다 (저장소가 아니거나 git 부재).")
    if _profile_missing(root):
        lines.append("⚠️  sage/project-profile.{yaml,json} 이 없습니다 — 설치는 있으나 게이트가 "
                     "아직 이 선언을 읽지 않습니다.")
    return lines


def _env_stem():
    return (os.environ.get("SAGE_CYCLE_STEM") or "").strip()


def _location(root, path):
    return [f"   프로젝트 루트: {root}", f"   선언 파일:     {path}"]


def _syntax_issue(args):
    action = args.action
    if action == "use":
        return ("`use` 는 `set` 으로 이름이 바뀌었습니다.\n"
                f"   → sage cycle set {args.stem or '<stem>'}")
    if action not in _ACTIONS:
        return (f"알 수 없는 동작입니다: {action!r}\n"
                "   → sage cycle set <stem> | sage cycle show | sage cycle clear")
    if action == "set":
        if not args.stem:
            return "set 에는 stem 이 필요합니다.\n   → sage cycle set <stem>"
        if args.extra:
            return (f"set 은 stem 을 하나만 받습니다: {args.extra!r}\n"
                    f"   → sage cycle set {args.stem}")
        if args.risk is not None and args.risk not in _RISKS:
            return ("--risk 는 L1|L2|L3 중 하나여야 합니다.\n"
                    f"   → sage cycle set {args.stem} --create --risk L1|L2|L3")
        if not args.create and args.risk is not None:
            return ("--risk 는 --create 로 만들 Phase 00에 쓰는 값입니다.\n"
                    f"   → sage cycle set {args.stem} --create --risk {args.risk}")
        if not args.create and args.path is not None:
            return ("--path 는 --create 와 함께만 사용할 수 있습니다.\n"
                    f"   → sage cycle set {args.stem} --create --risk L1|L2|L3 "
                    f"--path {args.path}")
        if args.create and args.risk is None:
            return ("--create 에는 --risk 가 필요합니다.\n"
                    f"   → sage cycle set {args.stem} --create --risk L1|L2|L3")
        return None
    if args.stem or args.extra or args.create or args.risk is not None or args.path is not None:
        return f"{action} 는 stem·--create·--risk·--path 를 받지 않습니다.\n   → sage cycle {action}"
    return None


def run(args):
    issue = _syntax_issue(args)
    if issue:
        print(f"⛔ [sage cycle] {issue}", file=sys.stderr)
        return 2
    cs = _load_cycle_state()
    try:
        root = _resolve_root(cs, args.root)
    except cs.DeclarationRootError as exc:
        print(f"⛔ [sage cycle] {exc}", file=sys.stderr)
        return 2
    path = cs.declaration_path(root)
    try:
        active_fast, fast_error = _active_fast_runs(root)
    except Exception as exc:
        active_fast, fast_error = [], f"Fast Cycle audit 읽기 실패({type(exc).__name__}: {exc})"
    if fast_error:
        print(f"⛔ [sage cycle] {fast_error}", file=sys.stderr)
        return 2
    if active_fast and args.action == "clear":
        run_id, state = active_fast[0]
        print(f"⛔ [sage cycle] 활성 Fast run {run_id} (stem={state.get('cycle_stem')})이 있어 clear 할 수 없습니다.\n"
              f"   → sage fast-cycle close --run-id {run_id}\n"
              f"   → 또는 sage fast-cycle abort --run-id {run_id} --reason <사유>", file=sys.stderr)
        return 2
    if active_fast and args.action == "set":
        mismatched = [(run_id, state) for run_id, state in active_fast
                      if state.get("cycle_stem") != args.stem]
        if mismatched:
            run_id, state = mismatched[0]
            print(f"⛔ [sage cycle] 활성 Fast run {run_id}의 stem={state.get('cycle_stem')} — "
                  f"다른 stem {args.stem!r}으로 전환할 수 없습니다.", file=sys.stderr)
            return 2
    if args.action == "set":
        return _set(cs, args, root, path)
    if args.action == "clear":
        return _clear(cs, root, path)
    return _show(cs, root, path)


def _normalized_stem(cs, value):
    normalized = cs.cycle_binding.normalize_stem(value)
    if normalized is None:
        raise CycleUsageError(
            f"cycle stem 형식 오류: {value!r} — 경로 구분자·제어문자 없이 160자 이하여야 합니다")
    try:
        normalized.encode("utf-8")
    except UnicodeEncodeError:
        raise CycleUsageError(
            f"cycle stem 형식 오류: {value!r} — UTF-8로 기록할 수 있는 문자만 허용됩니다")
    if any(ch in normalized for ch in ("\u0085", "\u2028", "\u2029")):
        raise CycleUsageError(
            f"cycle stem 형식 오류: {value!r} — 줄 구분 문자는 사용할 수 없습니다")
    return normalized


def _read_yaml_profile(root):
    path = os.path.join(root, "sage", "project-profile.yaml")
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CycleUsageError(f"YAML profile 이 없습니다: {path}")
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise CycleUsageError(f"YAML profile 을 읽지 못했습니다: {path} ({type(exc).__name__})")
    if not isinstance(value, dict):
        raise CycleUsageError(f"YAML profile 최상위는 mapping 이어야 합니다: {path}")
    return value, path


def _phase_globs(profile):
    pdca = profile.get("pdca")
    phases = pdca.get("phases") if isinstance(pdca, dict) else None
    if not isinstance(phases, list):
        raise CycleUsageError("profile pdca.phases 는 list 여야 합니다")
    phase00_entries = [item for item in phases
                       if isinstance(item, dict) and item.get("id") == "00"]
    if len(phase00_entries) != 1:
        raise CycleUsageError(
            f"profile pdca.phases 에 id '00' 항목이 정확히 하나여야 합니다 "
            f"(found {len(phase00_entries)})")
    phase00 = phase00_entries[0].get("glob")
    if not isinstance(phase00, str) or not phase00.strip():
        raise CycleUsageError("profile pdca.phases id '00'의 glob 은 비어 있지 않은 문자열이어야 합니다")

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
        raise CycleUsageError(
            f"compiled profile 을 읽지 못했습니다: {json_path} ({type(exc).__name__})")
    if not isinstance(compiled, dict):
        raise CycleUsageError(f"compiled profile 최상위는 mapping 이어야 합니다: {json_path}")
    compiled00, _ = _phase_globs(compiled)
    if compiled00 != phase00:
        raise CycleUsageError(
            "YAML 과 compiled JSON 의 phase 00 glob 이 다릅니다.\n"
            "   → sage generate --kind hook --write")
    return phase00, all_globs, yaml_path, json_path, False


def _canonical_rel(value):
    if not isinstance(value, str) or not value.strip():
        raise CycleUsageError("--path 는 비어 있지 않은 프로젝트 root 상대 디렉터리여야 합니다")
    raw = value.strip().replace("\\", "/")
    drive, _ = ntpath.splitdrive(raw)
    if drive or os.path.isabs(raw) or ntpath.isabs(raw):
        raise CycleUsageError(f"--path 는 프로젝트 root 상대경로여야 합니다: {value!r}")
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise CycleUsageError(f"--path 에 '..' 또는 빈 경로를 사용할 수 없습니다: {value!r}")
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
        raise CycleUsageError(
            f"phase 00 glob 에서 생성 디렉터리를 유도할 수 없습니다: {pattern!r}\n"
            "   → --path <프로젝트-root-상대-디렉터리> 를 지정하세요")
    return "/".join(literal)


def _target_for(root, directory, stem, pattern, cs):
    rel_dir = _canonical_rel(directory)
    target_dir = os.path.join(root, *rel_dir.split("/"))
    if not _contained(root, target_dir):
        raise CycleUsageError(
            f"--path 가 symlink 를 통해 프로젝트 root 밖으로 나갑니다: {directory!r}")
    rel_target = f"{rel_dir}/{stem}.md"
    if not cs.cycle_binding.matches_glob(rel_target, pattern):
        raise CycleUsageError(
            f"생성 대상이 phase 00 glob 에 매치하지 않습니다: {rel_target!r} vs {pattern!r}\n"
            "   → --path 에 phase 00 glob 안의 디렉터리를 지정하세요")
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


def _phase00_skeleton(stem, risk):
    return (
        "<!-- SAGE Phase 00 skeleton: fill the plan before governed source edits. -->\n"
        f"# [Base Plan] {stem}\n\n"
        f"Cycle-Stem: `{stem}`\n"
        f"Risk Level: {risk}\n"
        "Status: DRAFT\n"
        "Done-Criteria-Revision: 1\n\n"
        "## 1. Context\n\n"
        "TODO: describe the problem and constraints.\n\n"
        "## 2. Goal\n\n"
        "TODO: define the intended outcome.\n\n"
        "## 3. Acceptance Criteria\n\n"
        "TODO: define requirement-level acceptance evidence.\n\n"
        "## 4. Final Conclusion & UX Guide\n\n"
        "TODO: summarize the selected direction.\n\n"
        "## 5. Done Criteria\n\n"
        "- [ ] TODO: replace with a concrete completion criterion\n\n"
        "## 6. Done Criteria Revision Log\n\n"
        "Initial revision 1. No replanning record.\n"
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

    CLI 가 실은 LanguageContext 를 쓰되, 없으면 기본값이다 — 언어 배선 없이 호출되는 경로
    (테스트·직접 호출)가 여기서 죽으면 사이클 선언 자체가 언어 기능에 묶인다.
    """
    context = getattr(args, "_language_context", None)
    language = getattr(context, "language", None)
    return language if language in cs.DOCUMENT_LANGUAGES else "ko"


def _set(cs, args, root, declaration_path):
    try:
        stem = _normalized_stem(cs, args.stem)
    except CycleUsageError as exc:
        print(f"⛔ [sage cycle] {exc}", file=sys.stderr)
        return 2
    if args.create:
        return _create_and_set(cs, args, root, declaration_path, stem)

    try:
        profile, profile_path = _read_yaml_profile(root)
        phase00, _ = _phase_globs(profile)
        valid, candidates = _valid_phase00_docs(root, phase00, stem, cs)
        if len(valid) != 1:
            print(f"⚠️  Cycle-Stem '{stem}' 에 정확히 결속되는 Phase 00이 {len(valid)}개입니다.")
            print(f"   검색 glob: {phase00}")
            for candidate in candidates:
                print(f"   - {candidate}")
            print("   선언은 계속하지만 실제 소스 편집 전에 Phase 00 결속을 확인하세요.")
        print(f"   profile:       {profile_path}")
    except CycleUsageError as exc:
        print(f"⚠️  Phase 00 존재 여부를 확인하지 못했습니다: {exc}")
        print("   선언은 계속하지만 실제 소스 편집 전에 profile과 Phase 00을 확인하세요.")

    try:
        cs.write_declaration(root, stem, document_language=_document_language(cs, args))
    except OSError as exc:
        print(f"⛔ [sage cycle] 선언을 쓰지 못했습니다: {declaration_path} "
              f"({type(exc).__name__})", file=sys.stderr)
        return 2
    return _report_set(cs, root, declaration_path, stem)


def _create_and_set(cs, args, root, declaration_path, stem):
    try:
        phase00, all_globs, yaml_path, json_path, compiled_missing = _load_create_profile(root)
        directory = args.path if args.path is not None else _derive_directory(phase00)
        target_dir, target, rel_target = _target_for(root, directory, stem, phase00, cs)
    except CycleUsageError as exc:
        print(f"⛔ [sage cycle] {exc}", file=sys.stderr)
        return 2

    collisions = _same_basename_candidates(root, phase00, stem, target)
    if collisions:
        print(f"⛔ [sage cycle] Cycle-Stem '{stem}' 와 충돌하는 Phase 00 후보가 있습니다.",
              file=sys.stderr)
        for candidate in collisions:
            print(f"  - {candidate}", file=sys.stderr)
        print("\n기존 사이클을 계속하려면 중복을 정리한 뒤:", file=sys.stderr)
        print(f"  → sage cycle set {stem}", file=sys.stderr)
        suggestions = _available_stems(root, all_globs, stem, cs)
        if suggestions:
            print("\n새 사이클에 사용할 수 있는 충돌 없는 후보:", file=sys.stderr)
            for candidate in suggestions:
                print(f"  - {candidate}", file=sys.stderr)
        else:
            print("\n새 사이클에는 160자 이하의 다른 stem 을 정하세요.", file=sys.stderr)
        return 2

    try:
        os.makedirs(target_dir, exist_ok=True)
        if not _contained(root, target_dir):
            raise CycleUsageError("생성 디렉터리가 프로젝트 root 밖으로 바뀌었습니다")
        _write_phase00_exclusive(target, _phase00_skeleton(stem, args.risk).encode("utf-8"))
    except FileExistsError:
        print(f"⛔ [sage cycle] 대상 엔트리가 이미 존재해 덮지 않습니다: {rel_target}",
              file=sys.stderr)
        return 2
    except (OSError, CycleUsageError) as exc:
        print(f"⛔ [sage cycle] Phase 00을 만들지 못했습니다: {rel_target} "
              f"({type(exc).__name__})", file=sys.stderr)
        return 2

    print(f"✅ Phase 00 생성됨: {rel_target}")
    print("   이 파일은 뼈대입니다. 실제 소스 편집 전에 TODO 내용을 채우세요.")
    print(f"   YAML profile:  {yaml_path}")
    print(f"   compiled JSON: {json_path}")
    if compiled_missing:
        print("⚠️  compiled profile 이 없습니다. 실제 소스 편집 전에 반드시 생성하세요:")
        print("   → sage generate --kind hook --write")

    try:
        cs.write_declaration(root, stem, document_language=_document_language(cs, args))
    except OSError as exc:
        print(f"⛔ [sage cycle] 선언을 쓰지 못했습니다: {declaration_path} "
              f"({type(exc).__name__})", file=sys.stderr)
        print(f"→ Phase 00은 그대로 있습니다. `sage cycle set {stem}` 로 선언만 다시 하세요.",
              file=sys.stderr)
        return 2
    return _report_set(cs, root, declaration_path, stem)


def _report_set(cs, root, path, stem):
    effective, origin, _error = cs.resolve_stem(root)
    print(f"✅ 사이클 선언 — {stem}")
    for line in _location(root, path):
        print(line)
    if origin == "env":
        print(f"⚠️  지금은 SAGE_CYCLE_STEM='{effective}' 이 이깁니다 — 파일 선언을 쓰려면 "
              f"`unset SAGE_CYCLE_STEM` 하세요.")
    for line in _warnings(root, path):
        print(line)
    print("   (해제: sage cycle clear)")
    return 0


def _clear(cs, root, path):
    try:
        existed = cs.clear_declaration(root)
    except OSError as exc:
        print(f"⛔ [sage cycle] 선언을 지우지 못했습니다: {path} ({type(exc).__name__})",
              file=sys.stderr)
        return 2
    print(f"✅ 사이클 선언 해제 — {path}" if existed
          else f"[sage cycle] 선언이 없습니다 — {path}")
    env = _env_stem()
    if env:
        print(f"⚠️  SAGE_CYCLE_STEM='{env}' 은 그대로 남아 있습니다 — "
              f"`unset SAGE_CYCLE_STEM` 으로 지우세요.")
    return 0


def _show(cs, root, path):
    stem, origin, error = cs.resolve_stem(root)
    print("== sage cycle show ==")
    for line in _location(root, path):
        print(line)
    if error:
        print(f"⚠️  선언 파일을 읽지 못했습니다: {error}")
        print("    → 게이트는 선언 없음으로 진행합니다. `sage cycle set <stem>` 으로 다시 쓰세요.")
    if not stem:
        print("현재 선언: 없음 — 게이트는 브랜치 이름 마지막 조각에서 사이클을 추론합니다.")
    else:
        label = {"env": "SAGE_CYCLE_STEM", "cli": ".sage/cycle.json"}[origin]
        print(f"현재 선언: {stem}  ({label})")
        file_stem, _ = cs.read_declaration(root)
        if origin == "env" and file_stem:
            print(f"   (파일 선언 '{file_stem}' 은 env 에 밀려 쓰이지 않습니다)")
    for line in _warnings(root, path):
        print(line)
    return 0
