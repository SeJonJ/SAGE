"""Obsidian vault 출력 공용 헬퍼 — Loop A 감사 대시보드 / Loop C retro human-gate 노트.

마스터 게이트 = profile.knowledge_capture.vault_path (비면 vault 기능 전부 OFF = graceful N/A).
기존 knowledge_capture 정책(stop-compliance 의 vault freshness)과 동일한 게이트를 재사용하고,
note_convention.folder(기본 wiki) 아래에 노트를 쓴다. **스키마 키 추가 없음** — knowledge_capture 는
open object 라 기존 구조만 읽는다. --vault 오버라이드는 profile vault_path 보다 우선(테스트/임시 출력).
"""
import os
import re


def _safe_rel(folder):
    """folder 를 vault 안에 갇히는 안전 상대경로로 정규화(codex S5 P1) — 절대경로/`..`/선행 구분자 제거.
    note_convention.folder 는 프로필 config 라 `../../x`·`/tmp` 같은 경로 탈출을 막는다. 결과 없으면 'wiki'."""
    parts = [p for p in re.split(r"[\\/]+", str(folder or "")) if p and p not in ("..", ".")]
    return os.path.join(*parts) if parts else "wiki"


def vault_target(profile, override=None):
    """(vault_path, folder) 또는 (None, None)=비활성. folder 는 안전 상대경로로 정규화.

    게이트 계약(codex S5 명확화):
    - 기본(--vault 미지정): vault 출력 안 함.
    - `--vault`(경로 생략): profile.knowledge_capture.vault_path 마스터 게이트 — 비면 OFF.
    - `--vault PATH`: **명시적 opt-in 오버라이드** — profile 게이트와 무관하게 PATH 에 쓴다(테스트/1회 내보내기).
      사용자가 직접 경로를 타이핑한 것이 곧 opt-in 이므로 의도된 동작이다."""
    kc = (profile.get("knowledge_capture") or {}) if isinstance(profile, dict) else {}
    vault = (override or kc.get("vault_path") or "").strip()
    if not vault:
        return None, None
    folder = _safe_rel(((kc.get("note_convention") or {}).get("folder")) or "wiki")
    return vault, folder


def _fm_value(v):
    """frontmatter 스칼라/리스트 직렬화(기본 타입만 — bool/int/str/list)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        # 요소를 재귀로 직렬화 → 문자열은 따옴표로 감싸 일반 YAML-안전(`:`·`#`·`]`·콤마 포함도 OK, codex S5 P3).
        return "[" + ", ".join(_fm_value(x) for x in v) + "]"
    # 문자열은 따옴표(콜론/특수문자 안전) + 따옴표/개행 이스케이프(frontmatter 깨짐 방지).
    s = str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
    return f'"{s}"'


def write_note(vault, folder, filename, frontmatter, body, create_only=False):
    """vault/folder/filename 에 frontmatter+body 노트 작성 → 절대경로(또는 create_only 로 스킵 시 None).

    folder 는 vault_target 에서 정규화되나, 방어적으로 컨테인먼트를 재확인(escape 시 vault 루트로). filename 은
    basename 만(경로 주입 방지). create_only=True 면 기존 파일을 덮지 않는다(retro human-gate 상태 보존, codex S5 P2)."""
    # realpath: 심링크까지 해석해 containment 판정(codex S5 — abspath 는 심링크 escape 를 못 잡음).
    vault_abs = os.path.realpath(vault)
    d = os.path.realpath(os.path.join(vault_abs, folder))
    if vault_abs != d and os.path.commonpath([vault_abs, d]) != vault_abs:   # escape(심링크 포함) → vault 루트
        d = vault_abs
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, os.path.basename(filename))
    if create_only and os.path.exists(path):
        return None
    # leaf 심링크 차단(codex S5): open(w) 는 심링크를 따라가므로, 누군가 vault 안에 외부를 가리키는
    # 심링크를 심어두면 그 target 에 쓰게 된다. 심링크면 링크 자체만 제거(target 불변) 후 실제 파일 생성.
    if os.path.islink(path):
        os.unlink(path)
    # frontmatter 키도 안전 식별자만(codex S5) — 키에 개행/콜론이 있으면 구조 주입 가능. 값은 _fm_value 가 보호.
    fm = "---\n" + "".join(f"{_safe_key(k)}: {_fm_value(v)}\n" for k, v in frontmatter.items()) + "---\n\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(fm + body)
    return path


def _safe_key(k):
    """frontmatter 키를 안전 식별자로([A-Za-z0-9_-] 만). 키 주입(개행/콜론) 차단 — 일반 헬퍼 안전성."""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(k)) or "key"
