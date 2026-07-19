"""sage knowledge — Obsidian knowledge scan/write-back helpers.

This command makes `knowledge_capture.scan_before_dev` and `update_after_dev`
operational. It is still explicit: host skills invoke it at PDCA boundaries; the
CLI does not mutate the vault behind the user's back.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path

from sage.commands import _vault
from sage.profile_layers import load_profile_layers


def register(sub):
    p = sub.add_parser("knowledge", help="Obsidian vault 사전조회/개발후 갱신을 실행합니다")
    sp = p.add_subparsers(dest="action", metavar="<action>")
    sp.required = True

    ps = sp.add_parser("scan", help="개발 전 vault 관련 노트를 조회하고 .sage/knowledge_scan.md 를 갱신합니다")
    ps.add_argument("--query", default="", help="조회할 작업/기능 설명")
    ps.add_argument("--query-file", default=None, help="조회 문구를 읽을 파일(자유문자 shell 인자 주입 방지)")
    ps.add_argument("--profile", default=None, help="project-profile.yaml 경로")
    ps.add_argument("--vault", nargs="?", const="", default=None,
                    help="vault 경로 override. 경로 생략 시 profile.knowledge_capture.vault_path 사용")
    ps.add_argument("--limit", type=int, default=8, help="최대 결과 수(기본 8)")
    ps.add_argument("--root", default=None, help="프로젝트 루트 override")
    ps.set_defaults(func=_run_scan)

    pw = sp.add_parser("write-back", help="개발 완료 후 vault 노트와 wiki/log.md 를 갱신합니다")
    pw.add_argument("--title", required=True, help="작성할 노트 제목")
    pw.add_argument("--summary", default="", help="요약 본문")
    pw.add_argument("--summary-file", default=None, help="요약 본문을 읽을 파일(자유문자 shell 인자 주입 방지)")
    pw.add_argument("--profile", default=None, help="project-profile.yaml 경로")
    pw.add_argument("--vault", nargs="?", const="", default=None,
                    help="vault 경로 override. 경로 생략 시 profile.knowledge_capture.vault_path 사용")
    pw.add_argument("--prefix", default="TECH", help="노트 prefix(기본 TECH)")
    pw.add_argument("--tags", default=None,
                    help="쉼표구분 태그(벌트 작성 가이드대로 host 가 제공; 미지정 시 기본 tech,sage,knowledge-capture)")
    pw.add_argument("--append-log", action="store_true", help="wiki/log.md 에 wikilink 라인 추가")
    pw.add_argument("--skip-structure-check", action="store_true",
                    help="required_structure advisory 골격 검증을 끈다(L1 사소 노트·기획 인터뷰 등 심층 골격 대상이 아닌 노트용). "
                         "risk tier·노트 종류 판단은 host 가 하고 CLI 는 그 결과만 결정론으로 반영한다(SAGE 경계)")
    pw.add_argument("--root", default=None, help="프로젝트 루트 override")
    pw.set_defaults(func=_run_write_back)


def _find_project_root(start):
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(cur, "sage", "project-profile.yaml")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def _root(args):
    return os.path.abspath(args.root) if getattr(args, "root", None) else _find_project_root(os.getcwd())


def _profile_path(args, root):
    return os.path.abspath(args.profile) if getattr(args, "profile", None) else os.path.join(root, "sage", "project-profile.yaml")


def _load_profile(path):
    layers = load_profile_layers(path)
    if layers.has_fail:
        detail = "; ".join(message for severity, message in layers.issues if severity == "FAIL")
        return {}, f"profile load error: {detail}"
    return layers.effective, None


def _text_arg(value, file_path):
    if file_path:
        return Path(file_path).read_text(encoding="utf-8")
    return value or ""


def _kc_gate(profile, flag, vault_override, root=None):
    kc = profile.get("knowledge_capture") if isinstance(profile, dict) else {}
    kc = kc if isinstance(kc, dict) else {}
    if kc.get(flag) is not True:
        return None, None, f"knowledge_capture.{flag}=false_or_unset"
    override = vault_override or None
    vault, folder = _vault.vault_target(profile, override, root)
    if not vault:
        return None, None, "vault_path empty"
    return vault, folder, None


def _scan_path(root):
    return os.path.join(root, ".sage", "knowledge_scan.md")


def _inside_or_root(root, child):
    try:
        if root == child or os.path.commonpath([root, child]) == root:
            return child
    except ValueError:
        pass
    return root


def _write_scan_report(root, status, query, vault, matches, reason=None):
    os.makedirs(os.path.join(root, ".sage"), exist_ok=True)
    now = _dt.datetime.now().isoformat(timespec="seconds")
    lines = [
        "---",
        f"status: {status}",
        f"generated_at: {now}",
        f"query: {_yaml_scalar(query)}",
        f"vault: {_yaml_scalar(vault or '')}",
        f"reason: {_yaml_scalar(reason or '')}",
        "---",
        "",
        "# SAGE Knowledge Scan",
        "",
        f"- status: `{status}`",
        f"- query: `{_md_inline(query)}`",
    ]
    if reason:
        lines.append(f"- reason: {reason}")
    lines += ["", "## Matches"]
    if matches:
        for m in matches:
            lines += [
                "",
                f"### {m['relpath']}",
                f"- score: {m['score']}",
                f"- modified: {m['mtime']}",
                "",
                "```text",
                m["snippet"],
                "```",
            ]
    else:
        lines.append("")
        lines.append("(no matches)")
    Path(_scan_path(root)).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _md_inline(value):
    return str(value).replace("`", "\\`")


def _yaml_scalar(value):
    s = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{s}"'


def _tokens(query):
    toks = []
    for raw in re.split(r"[\s,.;:()\[\]{}<>/\\\"'`|]+", query.casefold()):
        raw = raw.strip()
        if len(raw) >= 2:
            toks.append(raw)
    return sorted(set(toks))


def _snippet(text, toks):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        low = line.casefold()
        if any(t in low for t in toks):
            start = max(0, i - 1)
            end = min(len(lines), i + 3)
            return "\n".join(lines[start:end])[:1200]
    return "\n".join(lines[:6])[:1200]


def _scan_vault(vault, folder, query, limit):
    root = os.path.realpath(vault)
    base = _inside_or_root(root, os.path.realpath(os.path.join(root, folder)))
    toks = _tokens(query)
    if not os.path.isdir(base):
        return []
    out = []
    for dirpath, dirs, files in os.walk(base):
        dirs[:] = sorted([d for d in dirs if not d.startswith(".")])
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                text = Path(path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            low = text.casefold()
            rel = os.path.relpath(path, root)
            score = sum(low.count(t) for t in toks) + sum(rel.casefold().count(t) * 3 for t in toks)
            if score <= 0 and toks:
                continue
            if not toks and fn not in ("index.md", "log.md"):
                continue
            stat = os.stat(path)
            out.append({
                "score": score,
                "relpath": rel,
                "mtime": _dt.datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "snippet": _snippet(text, toks),
            })
    out.sort(key=lambda m: (-m["score"], m["relpath"]))
    return out[:max(0, limit)]


def _run_scan(args):
    root = _root(args)
    profile, err = _load_profile(_profile_path(args, root))
    query = _text_arg(args.query, args.query_file).strip()
    if err:
        _write_scan_report(root, "error", query, None, [], err)
        print(f"[sage knowledge scan] {err} → {_scan_path(root)}")
        return 0
    vault, folder, reason = _kc_gate(profile, "scan_before_dev", args.vault, root)
    if reason:
        _write_scan_report(root, "n/a", query, None, [], reason)
        print(f"[sage knowledge scan] N/A — {reason} → {_scan_path(root)}")
        return 0
    try:
        matches = _scan_vault(vault, folder, query, args.limit)
        _write_scan_report(root, "ran", query, vault, matches)
        print(f"[sage knowledge scan] {len(matches)} match(es) → {_scan_path(root)}")
        return 0
    except Exception as e:
        _write_scan_report(root, "error", query, vault, [], type(e).__name__)
        print(f"[sage knowledge scan] error({type(e).__name__}) → {_scan_path(root)}")
        return 0


def _safe_title(title):
    s = re.sub(r"[\r\n\\/]+", "-", title).strip(" .-")
    return s or "SAGE update"


def _note_convention(profile):
    """profile.knowledge_capture.note_convention 을 dict 로 안전 반환(비-dict/부재는 {}).

    note_convention 이 손상(list/str 등)이면 `(kc or {}).get("note_convention") or {}` 패턴이 그 손상값을
    그대로 물려 이후 .get() 에서 크래시한다 — write-back 전체 abort. 정규화를 단일 지점으로 모아 fail-open."""
    kc = profile.get("knowledge_capture") if isinstance(profile, dict) else None
    conv = kc.get("note_convention") if isinstance(kc, dict) else None
    return conv if isinstance(conv, dict) else {}


def _note_filename(profile, prefix, title):
    conv = _note_convention(profile)
    pattern = conv.get("filename_pattern") or "{prefix} - {title}.md"
    name = pattern.replace("{prefix}", _safe_title(prefix)).replace("{title}", _safe_title(title))
    if not name.endswith(".md"):
        name += ".md"
    return os.path.basename(name)


def _append_link_once(vault, folder, target_file, note_stem, title):
    """vault/folder/<target_file> 에 `- <date> [[note]] - title` 한 줄을 멱등 append(이미 링크되면 skip).
    log.md(이력)·index(목차) 공용(7차 배치2 4-3). target_file 는 basename 만(경로 탈출 방지)."""
    root = os.path.realpath(vault)
    d = _inside_or_root(root, os.path.realpath(os.path.join(root, folder)))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, os.path.basename(target_file))
    if os.path.islink(path):
        # symlink escape 방지(기존 설계): 따라가지 않고 끊은 뒤 vault 내부 일반파일로 대체(외부 타깃 내용 보존).
        # 비silent 화(codex 중R2): 의도된 심링크 목차/로그였다면 따라가지 않음을 알린다.
        print(f"[sage knowledge write-back] ⚠️  {os.path.basename(path)} 가 심링크 — 보안상 따라가지 않고 "
              f"vault 내부 일반파일로 대체합니다(외부 타깃 내용은 보존, append 는 내부 파일에 기록).")
        os.unlink(path)
    line = f"- {_dt.date.today().isoformat()} [[{note_stem}]] - {title}\n"
    body = ""
    if os.path.exists(path):
        body = Path(path).read_text(encoding="utf-8")
        if f"[[{note_stem}]]" in body:
            return path, False
    with open(path, "a", encoding="utf-8") as f:
        if body and not body.endswith("\n"):
            f.write("\n")
        f.write(line)
    return path, True


def _append_log_once(vault, folder, note_stem, title):
    return _append_link_once(vault, folder, "log.md", note_stem, title)


def _note_tags_style(profile):
    """note_convention.tags_style → frontmatter(기본) | inline | none. 무효값은 frontmatter 폴백.
    vault 규칙을 따르도록 profile 주입(7차 배치2 4-2): frontmatter 안 쓰는 vault 는 inline/none 선택."""
    conv = _note_convention(profile)
    style = conv.get("tags_style") or "frontmatter"
    return style if style in ("frontmatter", "inline", "none") else "frontmatter"


def _index_name(profile):
    """note_convention.index → 목차 파일명(예: index.md). 비면 '' = index 갱신 안 함(기본 — index 없는 vault 존중).
    basename 후 ''/'.'/'..' 는 무효 처리(codex 중R1 P1): 그대로 두면 _append_link_once 가 폴더/상위를 열어
    IsADirectoryError 로 write-back 전체가 abort 된다."""
    conv = _note_convention(profile)
    name = os.path.basename(str(conv.get("index") or "")).strip()
    return name if name not in ("", ".", "..") else ""


def _required_structure(profile, prefix):
    """note_convention.required_structure[PREFIX] → 필수 마커(라인 시작 문자열) 목록, 없으면 [].

    advisory 구조 검증용. 이 매핑이 비었거나 없으면(기본) 검증하지 않는다 — 동작 불변, 옵트인. authoring
    guide 가 PREFIX 별로 요구하는 구조(예: BUG=[!summary]+증상/원인/수정/재발방지)의 **존재**만 결정론으로
    확인한다(내용 깊이는 게이트 대상 아님 — skill 지침·host depth self-review 영역).

    PREFIX 조회는 정확 일치 우선, 없으면 대소문자 무시 폴백 — `--prefix` 기본값 'TECH' 와 vault 규칙의
    'tech' 표기 차이로 검증이 조용히 건너뛰는 것을 막는다(폴백은 파일 순서상 첫 매칭, 결정론). 노트 파일명의
    prefix 표기는 손대지 않는다(원본 vault 규칙 소유). 손상 설정(비-dict/비-list)은 fail-open([]) — advisory 가
    write-back 을 깨면 안 된다."""
    table = _note_convention(profile).get("required_structure")
    if not isinstance(table, dict):
        return []
    markers = table.get(prefix)
    if markers is None:
        low = prefix.casefold()
        for k, v in table.items():
            if isinstance(k, str) and k.casefold() == low:
                markers = v
                break
    if not isinstance(markers, list):
        return []
    return [m for m in markers if isinstance(m, str) and m.strip()]


def _line_marker_match(line, marker):
    """라인이 마커를 충족하는가. strip 후 마커와 정확히 같거나 '마커 '(공백)로 시작해야 한다 —
    단순 startswith 는 '## 증상들' 이 필수 마커 '## 증상' 을 충족한 것으로 오판(false pass)한다.
    제목 붙은 헤더/콜아웃('> [!summary] 핵심', '## 증상 및 원인')은 공백 경계로 정상 인정된다."""
    s = line.strip()
    return s == marker or s.startswith(marker + " ")


def _fence_live_flags(lines):
    """각 라인이 펜스 코드블록 밖(True)인지의 리스트. ``` / ~~~ 토글, 펜스 경계 줄 자체도 False.

    마커 판정이 예시 코드블록에 낚이지 않게 한다 — 노트 본문의 ```예시``` 안에 든 '## 증상' 같은
    문자열을 실제 섹션 헤더로 오인해 _missing_structure 가 present 로, _hollow_sections 가 경계로
    잘못 보는 것을 막는다."""
    flags = []
    in_fence = None   # None 또는 연 펜스 마커("```"/"~~~") — 같은 종류로만 닫는다(혼합 펜스 우회 방지)
    for ln in lines:
        s = ln.lstrip()
        fence = "```" if s.startswith("```") else ("~~~" if s.startswith("~~~") else None)
        if in_fence is not None:
            flags.append(False)
            if fence == in_fence:
                in_fence = None
        elif fence is not None:
            flags.append(False)
            in_fence = fence
        else:
            flags.append(True)
    return flags


def _missing_structure(note_path, markers):
    """note 에서 빠진 필수 마커 목록. 마커는 펜스 밖 라인에서만 인정한다(예시 블록의 동명 문자열을
    실제 헤더로 오인 방지). 읽기 실패는 빈 목록(fail-open — advisory 가 예외로 write-back 을 깨지 않는다)."""
    try:
        lines = Path(note_path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    live = _fence_live_flags(lines)
    return [m for m in markers
            if not any(live[i] and _line_marker_match(ln, m) for i, ln in enumerate(lines))]


def _hollow_sections(note_path, markers):
    """존재하는 필수 마커 중 '빈 헤더' 섹션 목록 — 마커 라인에 인라인 내용도 없고, 다음 필수 마커(또는
    EOF) 전까지 본문 라인도 하나 없는 경우. 마커 부재는 _missing_structure 소관이라 존재하는 마커만 본다.

    섹션 경계는 **다음 필수 마커(펜스 밖)만** 본다 — 일반 하위 헤딩(`### ...`)이나 펜스 코드블록은 섹션
    본문으로 인정한다(그렇지 않으면 하위 섹션·코드 예시로 채운 정상 섹션을 hollow 로 오판한다). 내용의
    *질/깊이*는 판정하지 않는다(skill·host self-review 영역, false-assurance 회피) — 순수 구조적 hollow
    (헤더만 있고 내용 0)만 결정론으로 잡는다. 읽기 실패는 빈 목록(fail-open)."""
    try:
        lines = Path(note_path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return []
    live = _fence_live_flags(lines)

    def _marker_at(i):
        return live[i] and any(_line_marker_match(lines[i], mk) for mk in markers)

    hollow = []
    for m in markers:
        idx = next((i for i in range(len(lines)) if live[i] and _line_marker_match(lines[i], m)), None)
        if idx is None:
            continue   # 부재(또는 펜스 안에만 존재) 마커는 _missing_structure 소관
        head = lines[idx].strip()
        # 인라인 내용 인정은 **콜아웃 마커**('> [!summary] 요약')에 한정한다. 헤딩 마커의 접미사
        # ('## 검증 (details)')는 섹션 제목이지 본문이 아니므로 본문 라인을 별도로 요구한다.
        if m.strip().startswith(">") and head != m and head.startswith(m) and head[len(m):].strip():
            continue
        has_body = False
        in_comment = False   # 여러 줄 HTML 주석('<!--' … 다음 줄들 … '-->') 추적
        for j in range(idx + 1, len(lines)):
            s = lines[j].strip()
            if not s:
                continue
            if in_comment:
                # 주석 종료 줄. '-->' 뒤에 실내용이 붙어 있으면 본문으로 인정.
                if "-->" in s:
                    in_comment = False
                    if s.split("-->", 1)[1].strip():
                        has_body = True
                        break
                continue
            # 콜아웃 빈 계속줄('>' 또는 '> ')은 본문이 아니다 — 빈 Obsidian 콜아웃을 통과시키지 않는다.
            if s == ">" or (s.startswith(">") and not s[1:].strip()):
                continue
            # HTML 주석 자리표시자('<!-- TODO -->' 및 여러 줄 주석)는 본문이 아니다 — 빈 골격을
            # 주석 placeholder 로 통과시키지 않는다(hollow lint 의 취지). 한 줄에서 닫히면 '-->' 뒤
            # 잔여 실내용만 본문으로 보고, 여는 줄에 '-->'가 없으면 여러 줄 주석으로 이후 줄을 건너뛴다.
            if s.startswith("<!--"):
                if "-->" in s:
                    if s.split("-->", 1)[1].strip():
                        has_body = True
                        break
                    continue
                in_comment = True
                continue
            if _marker_at(j):
                break   # 다음 필수 마커 = 섹션 경계, 본문 없음
            has_body = True   # 하위 헤딩·코드블록 포함 어떤 실내용이든 본문으로 인정
            break
        if not has_body:
            hollow.append(m)
    return hollow


def _note_path(vault, folder, filename):
    root = os.path.realpath(vault)
    d = _inside_or_root(root, os.path.realpath(os.path.join(root, folder)))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, os.path.basename(filename))


def _write_or_append_note(vault, folder, filename, frontmatter, note_stem, summary, tag_line=""):
    import hashlib
    marker = "SAGE-KNOWLEDGE-WRITEBACK:" + hashlib.sha256(summary.encode("utf-8")).hexdigest()[:16]
    section = (f"\n\n<!-- {marker} -->\n\n"
               f"## SAGE Write-back ({_dt.date.today().isoformat()})\n\n"
               f"{summary or '(summary not provided)'}\n")
    path = _note_path(vault, folder, filename)
    if os.path.islink(path):
        os.unlink(path)
    if os.path.exists(path):
        # 기존(사람 저작) 노트에는 pass-through 계약(신규 노트 전용)을 적용하지 않고, host 본문을 정본
        # '## SAGE Write-back' H2 섹션으로 감싸 non-destructive append 한다 — 사람 본문을 덮어쓰지 않기
        # 위한 의도된 예외. 그래서 이 경로는 created=False 로 반환되어 구조 advisory 검증도 건너뛴다.
        body = Path(path).read_text(encoding="utf-8")
        if marker not in body:
            addition = section.lstrip("\n")
            # inline 스타일인데 기존 노트에 태그줄이 없으면 추가(codex 중R1 P2): 신규 노트에만 태그가
            # 들어가던 비일관 해소. 임의 노트의 제목 위치 파싱은 취약하므로 append 섹션 앞에 1회 보장.
            if tag_line and tag_line not in body:
                addition = f"{tag_line}\n\n" + addition
            with open(path, "a", encoding="utf-8") as f:
                if body and not body.endswith("\n"):
                    f.write("\n")
                f.write(addition)
        return path, False   # 기존 노트 append — 신규 본문을 CLI 가 저작한 게 아니라 구조검증 대상 아님
    # tag_line(인라인 태그 스타일)은 제목 바로 아래에 둔다(frontmatter/none 이면 빈 문자열).
    head = f"# {note_stem}\n\n"
    if tag_line:
        head += f"{tag_line}\n\n"
    body = head + _summary_section(summary)
    written = _vault.write_note(vault, folder, filename, frontmatter, body, create_only=True)
    # write_note 는 create_only 충돌(경쟁 생성) 시 None 반환 → 신규 저작 아님(구조검증 대상 아님).
    return written, written is not None


def _summary_section(summary):
    """host 가 저작한 본문을 선행 BOM 만 제거하고 그대로 통과시킨다(CLI 정본 헤더 강제 없음).

    vault 마다 리드 섹션 규칙이 다르다(예: '> [!abstract] 핵심 Takeaway' 콜아웃 vs '## Summary'). CLI 가
    특정 헤더를 강제하면 vault authoring guide 와 충돌하고 이중 헤더를 만든다. 본문 형식·깊이는 vault
    guide + skill 지침 소유(SAGE 결정론 경계: CLI=배치·frontmatter·제목, host=본문 내용). vault 규칙 준수는
    note_convention.required_structure advisory 로 확인한다.

    양끝 공백/개행 정규화는 진입점 `_run_write_back` 이 이미 `.strip()` 으로 한 번 수행하므로 여기선
    반복하지 않는다(이중 strip 이 trailing hard-break 등 본문을 두 번 건드리는 것을 피함). 남는 것은 오직
    선행 BOM — 이게 있으면 첫 콜아웃/헤더가 라인 시작에 오지 못해 마커 매칭이 빗나가므로 제거한다.
    빈 요약만 placeholder 로 방어."""
    text = (summary or "").lstrip("﻿")   # 선행 BOM 만 제거(양끝 공백은 호출부에서 이미 정규화)
    return (text or "(summary not provided)") + "\n"


def _run_write_back(args):
    root = _root(args)
    profile, err = _load_profile(_profile_path(args, root))
    # 선행 BOM 과 모든 유니코드 공백(NBSP·전각공백 포함)의 반복 조합을 제거한 뒤 후행 공백을 정리한다 —
    # 원래 `.strip()` 이 처리하던 공백 범위를 유지(회귀 방지)하면서 BOM 까지 처리해, BOM·공백이 어떤
    # 순서로 섞여도 첫 마커가 라인 시작에 오게 한다. `.strip()` 단독은 BOM 을 공백으로 보지 않아 그
    # 지점에서 멈춰 들여쓰기가 남는다(BOM 은 `\s` 에도 미포함이라 `[\s﻿]` 로 명시 결합).
    summary = re.sub(r"^[\s﻿]+", "", _text_arg(args.summary, args.summary_file)).rstrip()
    if err:
        print(f"[sage knowledge write-back] FAIL — {err}")
        return 1
    vault, folder, reason = _kc_gate(profile, "update_after_dev", args.vault, root)
    if reason:
        print(f"[sage knowledge write-back] N/A — {reason}")
        return 0
    title = _safe_title(args.title)
    filename = _note_filename(profile, args.prefix, title)
    note_stem = filename[:-3] if filename.endswith(".md") else filename
    # tags_style(4-2): vault 규칙에 맞춰 frontmatter(기본) / inline(본문 태그줄) / none(태그 없음).
    # 태그 값: host 가 벌트 작성 가이드를 읽고 --tags 로 전달(판단=host). 정규화(strip·빈값제거·순서보존 dedupe)
    # 후 비면 기본값 fallback — `--tags ",,"` 로 빈 `tags: []`/빈 태그줄이 나가지 않도록.
    _default_tags = ["tech", "sage", "knowledge-capture"]
    if args.tags:
        _seen = set()
        tags = [t for t in (x.strip() for x in args.tags.split(","))
                if t and not (t in _seen or _seen.add(t))] or _default_tags
    else:
        tags = _default_tags
    style = _note_tags_style(profile)
    fm = {"date": _dt.date.today().isoformat(), "source": "sage knowledge write-back"}
    tag_line = ""
    if style == "frontmatter":
        fm["tags"] = tags
    elif style == "inline":
        tag_line = "태그: " + " ".join(f"#{t}" for t in tags)
    try:
        path, created = _write_or_append_note(vault, folder, filename, fm, note_stem, summary, tag_line=tag_line)
        if path is None:
            # write_note 가 create_only 충돌(경쟁 생성)로 None 반환 — "note written: None" 오보 대신 정확 보고.
            print(f"[sage knowledge write-back] note already exists (동시 생성) — 신규 작성 skip: {filename}")
        else:
            print(f"[sage knowledge write-back] note written: {path}")
        # advisory 구조 검증(옵트인): authoring guide 가 요구하는 PREFIX 별 필수 마커의 존재만 확인.
        # 결정론으로 잡히는 형식 누락을 표면화하되 차단하지 않는다(내용 깊이는 게이트 밖 — skill 지침·host depth self-review).
        # 신규 노트만 대상 — 기존 노트 append 는 사람이 저작한 본문이라 구조 미준수를 WARN 하면 소음.
        # --skip-structure-check: L1 사소 노트·기획 인터뷰 등 심층 골격 대상이 아닌 노트는 host 가 검사를 끈다
        # (심층 골격은 L2/L3 최종 요약 노트에만 요구 — risk/kind 판단은 host, CLI 는 플래그로 받아 결정론 실행).
        markers = _required_structure(profile, args.prefix) if created and not args.skip_structure_check else []
        if markers:
            missing = _missing_structure(path, markers)
            if missing:
                print(f"[sage knowledge write-back] ⚠️  advisory: authoring guide 필수 구조 누락 "
                      f"({args.prefix}) — {', '.join(missing)}")
            # 존재하는 마커 중 '빈 헤더'(내용 0) 섹션도 표면화 — 마커 존재만으론 hollow 골격을 통과시킨다.
            hollow = _hollow_sections(path, markers)
            if hollow:
                print(f"[sage knowledge write-back] ⚠️  advisory: 필수 섹션이 빈 헤더 "
                      f"({args.prefix}) — {', '.join(hollow)} (헤더만 있고 본문 없음 → depth self-review 로 채우세요)")
            if not missing and not hollow:
                print(f"[sage knowledge write-back] ✅ 골격 마커 존재+본문 확인 ({args.prefix}) — "
                      f"내용 깊이(질)는 미검증(skill 지침·host depth self-review 영역)")
        if args.append_log:
            log_path, added = _append_log_once(vault, folder, note_stem, title)
            print(f"[sage knowledge write-back] log {'updated' if added else 'already linked'}: {log_path}")
        # index(4-3): note_convention.index 설정 시에만 목차에 멱등 append(없는 vault 존중 — 기본 off).
        idx = _index_name(profile)
        if idx:
            idx_path, idx_added = _append_link_once(vault, folder, idx, note_stem, title)
            print(f"[sage knowledge write-back] index {'updated' if idx_added else 'already linked'}: {idx_path}")
        return 0
    except Exception as e:
        print(f"[sage knowledge write-back] FAIL — {type(e).__name__}: {e}")
        return 1
