"""무엇을 지울지 **읽기만 해서** 정하는 층.

## 이 층이 지지 않는 책임

여기서는 파일을 만들지도 지우지도 바꾸지도 않는다. `os.remove` 도 `open(..., "w")` 도 없다.
계획을 만드는 일과 실행하는 일을 한 함수가 하면, 중간에 실패했을 때 어디까지 계획이고 어디부터
실행이었는지 아무도 모른다. 그래서 이 층의 출력은 **불변 plan** 하나이고, 실행 층은 그 plan 에
없는 경로를 건드릴 수 없다.

## 소유권을 추측하지 않는다

`DELETE` 는 SAGE 가 만들었다는 **증거가 있을 때만** 붙는다. 증거는 셋 중 하나다 — SAGE 전용
namespace 안에 있거나, manifest 가 배치를 기록했거나, 파일 자체가 SAGE marker 를 갖는다.
증거가 없으면 `PRESERVE` 다. 내용이 현재 번들과 같다는 사실은 증거가 아니다 — 사용자가 같은
내용을 직접 만들었을 수도 있고, 그 구별이 불가능한 것이 바로 이 명령이 조심해야 하는 이유다.

## scope 는 읽기까지 가른다

project 범위는 `$CODEX_HOME` 을 **읽지도 않는다.** 쓰기만 막으면 격리가 두 겹 규칙이 되고,
그 틈은 언젠가 쓰기로 넓어진다. 그래서 전역 경로를 만드는 함수는 global 을 포함한 범위에서만
호출된다 — 이 모듈에서 그 호출이 project 분기에 나타나면 그것 자체가 결함이다.
"""
import json
import os
import stat

from sage import _resources
from sage import install_transaction as _tx
from sage import manifest_contract as _contract
from sage import managed_assets as _managed
from sage import uninstall_shared as _shared
from sage.hook_launcher import command_template as hook_command_template

# --- 결과 어휘 ---------------------------------------------------------------

DELETE = "DELETE"
STRIP = "STRIP"
PRESERVE = "PRESERVE"
BLOCK = "BLOCK"

COMPLETE = "COMPLETE"
PARTIAL = "PARTIAL"
BLOCKED = "BLOCKED"
CANCELLED = "CANCELLED"

EXIT_CODES = {COMPLETE: 0, PARTIAL: 1, BLOCKED: 2, CANCELLED: 0}

SCOPE_PROJECT = "project"
SCOPE_GLOBAL = "global"
SCOPE_ALL = "all"


class Action:
    """계획된 처리 하나. 불변이다.

    `reason` 이 문장이 아니라 code 인 이유는, 판정이 언어를 타면 한국어와 영어 실행이 다른
    exit 를 낼 수 있기 때문이다. 문장은 renderer 가 만든다.
    """

    __slots__ = ("kind", "scope", "path", "reason", "detail", "group", "state")

    def __init__(self, kind, scope, path, reason, detail=None, group=None, state=None):
        self.kind = kind
        self.scope = scope
        self.path = path
        self.reason = reason
        # 구조화된 손상 사실들. 문장이 아니라 좌표·타입 이름·숫자라서 화면과 `--json` 이
        # **같은 값**을 소비한다. 둘이 각자 문장을 만들면 언젠가 서로 다른 말을 한다.
        self.detail = tuple(detail) if detail else None
        self.group = group
        # host 등록이 있는가 없는가 알 수 없는가. `None` 은 이 action 이 등록과 무관하다는 뜻.
        self.state = state

    def __repr__(self):
        return f"Action({self.kind}, {self.scope}, {self.path!r}, {self.reason!r})"

    def as_json(self, dest=None, global_root=None):
        item = {"action": self.kind, "scope": self.scope,
                "path": self.display_path(dest, global_root), "reason": self.reason}
        if self.detail is not None:
            item["detail"] = [dict(entry) for entry in self.detail]
        if self.group is not None:
            item["group"] = self.group
        if self.state is not None:
            item["registration_state"] = self.state
        return item

    def display_path(self, dest=None, global_root=None):
        """사람과 기계가 **함께 읽는** 경로 한 벌. 화면과 `--json` 이 같은 값을 쓴다."""
        return display_path(self.path, self.scope, dest, global_root)


class UninstallPlan:
    """실행 층이 받는 유일한 입력. 여기 없는 경로는 어떤 이유로도 처리 대상이 아니다.

    ## baseline 은 왜 plan 안에 있는가

    "확인 이후 바뀌었는가" 를 판정하려면 기준이 **사용자가 화면에서 본 그 순간**의 상태여야
    한다. 기준을 확인 뒤에 뜨면, 확인 prompt 가 열려 있는 동안 사용자가 고친 파일이 기준으로
    굳어 검사를 그대로 통과한다 — 방금 고친 파일이 조용히 지워진다. 그래서 baseline 은
    plan 과 같은 시점에 만들어져 plan 에 붙어 다니고, 실행 층은 이것을 **받지 않고 읽는다.**
    받으면 언젠가 누군가 새로 떠서 넘긴다.
    """

    __slots__ = ("scope", "dest", "actions", "status", "blocked_reason", "notices", "baseline",
                 "global_root", "root_baseline")

    def __init__(self, scope, dest, actions, status, blocked_reason=None, notices=(),
                 baseline=None, global_root=None, root_baseline=None):
        self.scope = scope
        self.dest = dest
        self.actions = tuple(actions)
        self.status = status
        self.blocked_reason = blocked_reason
        self.notices = tuple(notices)
        # 계획을 만든 그 시점의 기준. 실행 층은 이 값하고만 대조한다.
        self.baseline = dict(baseline) if baseline is not None else fingerprint(
            action.path for action in self.actions if action.kind in (DELETE, STRIP))
        # 전역 skill root. **global 을 포함한 범위에서만** 채워진다 — project 범위에서 이 값이
        # None 이 아니면 그것 자체가 scope 격리 위반의 증거다.
        self.global_root = global_root
        # write root 자체의 기준. 대상의 기준만 뜨면 **root 가 통째로 바뀐 경우**를 볼 수
        # 없다 — 바꿔치기된 root 아래에서는 상대 경로가 전부 새 root 안에서 성립하므로 대상
        # 지문은 "없음" 이 되고, 없음은 계획 밖으로 조용히 빠져나간다. root 를 여는 쪽이 이
        # 값과 대조해야 승인된 자리에서 여는지 확인할 수 있다.
        self.root_baseline = (dict(root_baseline) if root_baseline is not None
                              else {root: root_fingerprint(root)
                                    for root in self.lock_roots()})

    @property
    def exit_code(self):
        return EXIT_CODES[self.status]

    def of_kind(self, kind):
        return tuple(action for action in self.actions if action.kind == kind)

    def write_targets(self):
        """실행 층이 열어도 되는 경로 전체. `DELETE` 와 `STRIP` 만이다.

        `PRESERVE` 와 `BLOCK` 은 여기 절대 들어오지 않는다 — 보존 대상이 write target 목록에
        한 번이라도 실리면, 그 다음 실수는 목록을 잘못 읽는 것만으로 충분해진다.
        """
        return tuple(action.path for action in self.actions
                     if action.kind in (DELETE, STRIP))

    def root_for(self, action):
        """이 action 을 검사할 때 기준이 되는 write root."""
        if action.scope == SCOPE_GLOBAL:
            return self.global_root
        return self.dest

    def lock_roots(self):
        """실제로 쓰는 root 만 잠근다. 정렬해서 돌려주는 것이 계약이다.

        여러 root 를 잠그는 명령이 서로 다른 순서로 집으면 두 실행이 상대의 첫 lock 을 물고
        영원히 기다린다. 순서를 값으로 고정하면 그 교착 자체가 성립하지 않는다.

        계획에 **쓰기 대상이 있는 scope 만** 대상이다. 쓰지 않을 root 를 잠그면 무관한 실행을
        막게 되고, project 범위에서 전역을 잠그면 "전역을 건드리지 않는다" 는 계약도 깨진다.
        """
        roots = set()
        for action in self.actions:
            if action.kind not in (DELETE, STRIP):
                continue
            root = self.root_for(action)
            if root:
                roots.add(root)
        return tuple(sorted(roots))

    def as_json(self):
        return {
            "scope": self.scope,
            "status": self.status,
            "exit_code": self.exit_code,
            "blocked_reason": self.blocked_reason,
            "deleted": [a.as_json(self.dest, self.global_root) for a in self.of_kind(DELETE)],
            "stripped": [a.as_json(self.dest, self.global_root) for a in self.of_kind(STRIP)],
            "preserved": [a.as_json(self.dest, self.global_root) for a in self.of_kind(PRESERVE)],
            "blocked": [a.as_json(self.dest, self.global_root) for a in self.of_kind(BLOCK)],
            "notices": list(self.notices),
        }


# --- 상태 기준 ---------------------------------------------------------------

def root_fingerprint(path):
    """write root **하나**의 기준. 이름이 아니라 그 이름이 가리키는 디렉터리를 본다.

    ## 왜 대상 지문만으로는 부족한가

    대상의 지문은 root 아래 상대 경로에 붙는다. root 자체가 junction 이나 rename 으로 통째로
    바뀌면 그 상대 경로들은 **새 root 안에서 다시 성립하거나 전부 없어진다.** 없어진 것은
    계획에서 조용히 빠지고, 성립한 것은 남의 디렉터리에서 지워진다. 어느 쪽도 대상 지문
    대조로는 보이지 않는다 — 그 대조는 이미 바뀐 root 를 기준으로 도니까.

    ## 왜 `lstat` 이 아니라 `stat` 인가

    root 를 여는 쪽은 이름을 따라가서 연다(`O_DIRECTORY` · `NtCreateFile`). 기준을 `lstat` 으로
    뜨면 symlink 로 걸린 정상적인 프로젝트 경로가 언제나 어긋난 것으로 보인다. 우리가 묻는
    것은 "이 이름이 링크인가" 가 아니라 **"이 이름이 아까 그 디렉터리를 가리키는가"** 다.
    """
    info = os.stat(path)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("uninstall.boundary_changed")
    return (_tx._kind(info.st_mode), stat.S_IMODE(info.st_mode), info.st_dev, info.st_ino)


def fingerprint(paths):
    """확인 시점과 실행 직전의 상태가 같은지 볼 기준.

    ## 왜 직접 만들지 않는가

    `install_transaction` 이 이미 같은 질문에 답하는 지문을 갖고 있다. 두 벌을 두면 한쪽만
    강해지고, 약한 쪽을 쓰는 경로가 조용히 남는다.

    ## 왜 크기·mtime 으로는 부족한가

    처음에는 (종류·크기·mtime) 으로 충분하다고 봤다 — 답해야 하는 질문이 "같은 파일인가" 가
    아니라 "내가 계획을 세운 뒤 누가 건드렸는가" 이기 때문이다. 그 판단이 틀렸다. **같은 크기로
    내용을 바꾸고 mtime 을 되돌려 놓으면** 그 지문은 통과한다. 되돌릴 수 없는 삭제 앞에서 그
    통과는 사용자 데이터를 잃는다. 그래서 내용 해시·inode·읽는 동안의 전후 일관성까지 보는
    `path_fingerprint` 를 쓴다.

    디렉터리는 `tree_fingerprint` 로 **안까지** 본다. 디렉터리 `lstat` 하나로는 안에 있는 파일의
    수정이 보이지 않는다 — 디렉터리 mtime 은 항목이 늘거나 줄 때만 바뀌기 때문이다. 대상
    대부분이 tree 인 이 명령에서 얕은 지문은 지키는 척만 하고, 있다고 믿게 만드는 만큼 없는
    것보다 나쁘다.

    이 함수가 **읽기 전용 층에 사는** 이유는 기준을 뜨는 일이 읽기이기 때문이다. 실행 층에
    두면 실행 직전에 다시 뜨고 싶은 유혹이 생기고, 그렇게 뜬 기준은 아무것도 지키지 못한다.
    """
    targets = [os.path.abspath(path) for path in paths]
    trees = [path for path in targets
             if os.path.isdir(path) and not os.path.islink(path)]
    return _tx.capture_paths(targets, recursive=trees)


# --- 표시 경로 ---------------------------------------------------------------

# 전역 자산은 실경로가 아니라 **사용자가 설정한 이름**으로 보여준다. `$CODEX_HOME` 은 사용자가
# 직접 정한 값이라, 그 이름으로 말해야 "내 어느 설정이 이걸 만들었는가" 가 바로 읽힌다. 풀어서
# 낸 실경로는 CI 로그와 이슈에 실행 머신의 홈 경로를 그대로 싣기도 한다.
GLOBAL_DISPLAY_ROOT = "$CODEX_HOME/skills"

# 기준 밖을 가리키는 경로의 비식별 토큰. 경로를 보여 주는 대신 **밖이라는 사실**만 말한다.
OUTSIDE_PROJECT = "<outside-project>"

_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def escape_display(text):
    """제어문자를 눈에 보이는 형태로. **줄을 위조할 수 없게 만드는 것**이 목적이다.

    파일 이름에는 개행이 들어갈 수 있다. 그대로 찍으면 목록 한 줄이 두 줄이 되고, 그 두 번째
    줄은 우리가 쓴 것처럼 보인다 — 사용자가 만든 이름 하나로 "지웠습니다" 같은 문장을 화면에
    끼워 넣을 수 있다는 뜻이다. `--json` 은 자체 escape 가 있어 무사하지만 화면은 아니고, 둘이
    다른 값을 보이면 그때부터 어느 쪽이 진짜인지 말할 수 없다. 그래서 **같은 함수**를 통과한
    값 하나만 쓴다.

    POSIX 에서만 역슬래시를 escape 한다. Windows 에서는 그것이 경로 구분자라, escape 하면
    모든 경로가 읽기 어려워지고 얻는 것은 없다.
    """
    escape_backslash = os.sep == "/"
    out = []
    for char in text:
        if escape_backslash and char == "\\":
            out.append("\\\\")
        elif char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            out.append(f"\\x{ord(char):02x}")
        else:
            out.append(char)
    return "".join(out)


def display_path(path, scope, dest=None, global_root=None):
    """화면과 `--json` 이 **함께 쓰는** 경로 표기.

    project 자산은 저장소 기준 상대 경로, 전역 자산은 `$CODEX_HOME/skills/...` 다. 기준 밖으로
    나간 경로는 `OUTSIDE_PROJECT` 토큰 하나로만 보인다 — 그건 `path_escape` 로 걸린 항목이고,
    그 문자열은 우리가 만든 것이 아니라 **탈출을 시도한 쪽이 정한 값**이라 화면에 싣지 않는다.

    표기를 한 함수로 모으는 이유는 둘이 갈라진 적이 있기 때문이다. 화면은 절대 경로를 찍고
    `--json` 은 절대 경로에 상대 경로를 덧붙이는 상태였고, 그러면 소비자마다 무엇을 기준으로
    비교해야 하는지가 달라진다.
    """
    if scope == SCOPE_GLOBAL and global_root and within_root(global_root, path):
        relative = os.path.relpath(path, os.path.abspath(global_root))
        if relative == os.curdir:
            return escape_display(GLOBAL_DISPLAY_ROOT)
        return escape_display(f"{GLOBAL_DISPLAY_ROOT}/{relative.replace(os.sep, '/')}")
    if scope == SCOPE_PROJECT and dest and within_root(dest, path):
        return escape_display(os.path.relpath(path, os.path.abspath(dest)))
    if dest or global_root:
        # 기준을 알면서 그 밖을 가리키는 경로는 `path_escape` 로 걸린 항목이다. 전체를 찍어
        # 주고 싶지만, 그 값은 우리가 만든 것이 아니라 **탈출을 시도한 쪽이 정한 문자열**이고
        # 실행 머신의 실제 배치를 그대로 싣는다. 사용자가 볼 자리는 사유 code 와 손상 좌표이지
        # 남이 정한 절대 경로가 아니다.
        return OUTSIDE_PROJECT
    return escape_display(path)


# --- 안전 경계 ---------------------------------------------------------------

def _is_broad_path(path):
    """지우면 안 되는 넓은 경로인가.

    filesystem root, 드라이브 루트, 사용자 홈, 그리고 **root 직계 자식**(`/usr`·`/opt`·
    `/Users`)을 막는다. 여기서 한 번 통과하면 그 아래 전부가 대상이 되므로, "설마 그럴 리
    없다" 로 넘기지 않는다.

    한때 이 함수는 root 직계 자식을 막으려는 주석을 달고도 실제로는 통과시켰다 —
    `os.path.split("/usr")` 는 `("/", "usr")` 이고, 조건이 `tail` 이 **비었을 때만** 참이라
    root 자체 말고는 어떤 것도 걸리지 않았다. 주석이 말한 규칙과 코드가 지킨 규칙이 달랐고,
    그 차이는 조용했다. 그래서 지금은 depth 로 판정한다 — 셀 수 있는 것을 세는 편이
    "이 모양이면 위험하다" 를 손으로 적는 것보다 틀리기 어렵다.
    """
    resolved = os.path.abspath(path)
    drive, tail = os.path.splitdrive(resolved)
    roots = {os.path.abspath(os.sep)}
    if drive:
        # `C:\` 와 UNC 공유 루트. 드라이브가 붙은 경로에서 기준은 `/` 가 아니라 이쪽이다.
        roots.add(drive + os.sep)
    if resolved in roots or tail in ("", os.sep):
        return True
    if not drive and not resolved.strip(os.sep):
        # POSIX 는 앞 슬래시 둘(`//`)을 그대로 둔다. 모양은 달라도 가리키는 곳은 root 다.
        return True
    if resolved == os.path.abspath(os.path.expanduser("~")):
        return True
    parent = os.path.dirname(resolved.rstrip(os.sep) or resolved)
    return parent in roots


def symlink_component_below(root, path):
    """`root` **아래**에서 symlink 성분을 만나는가.

    막아야 하는 것은 write root 를 벗어나는 경로다. root 자체를 어떤 경로로 찾아왔는지는
    사용자의 파일시스템 구성이고 우리가 판정할 일이 아니다 — macOS 의 `/var` → `/private/var`
    처럼 흔한 구성을 위반으로 읽으면, 실제로 위험한 것을 막는 대신 정상 프로젝트를 통째로
    거부하게 된다. 그래서 root 는 먼저 실경로로 확정하고, **그 아래** 성분만 검사한다.

    leaf 가 symlink 인 것은 여기서 참이 아니다. leaf 는 따라가지 않고 link 자체만 처리하므로
    탈출이 성립하지 않는다 — 중간 성분이 바뀌는 것만이 root 밖으로 나가는 길이다.
    """
    root_abs = os.path.realpath(root)
    current = os.path.dirname(os.path.abspath(path))
    while True:
        if not within_root(root_abs, current) or current == root_abs:
            return False
        if os.path.islink(current):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def boundary_block(dest):
    """실행 전에 걸러야 할 경계 위반. 통과하면 `None`."""
    if _is_broad_path(dest):
        return "uninstall.dest_too_broad"
    if not os.path.isdir(dest):
        return "uninstall.dest_missing"
    if _resources.is_engine_source_tree(dest):
        return "uninstall.engine_source_tree"
    return None


def within_root(root, path):
    """`path` 가 `root` 안인가. `..` 와 절대경로 탈출을 함께 막는다."""
    root_abs = os.path.abspath(root)
    path_abs = os.path.abspath(path)
    return path_abs == root_abs or path_abs.startswith(root_abs + os.sep)


# --- 설치 증명 ---------------------------------------------------------------

def manifest_path(dest):
    return os.path.join(os.path.abspath(dest), "docs", "sage_harness", ".manifest.json")


def read_manifest(dest):
    """`(manifest dict 또는 None, 사유 code 또는 None, 구조 위반 또는 None)`.

    손상과 부재는 다른 사실이다. 손상을 부재로 접으면 "설치된 적 없다" 로 읽혀 흔적이 남은 채
    성공으로 끝난다.

    ## 최상위가 dict 라는 것으로는 부족하다

    한때 이 함수는 `isinstance(document, dict)` 까지만 봤다. 그래서 `{}` 도, `assets` 가
    문자열인 것도, `host_runtime` 이 없는 것도 정상 manifest 로 통과했다. 빈 manifest 는
    "설치는 증명됐고 배치 기록은 하나도 없다" 로 읽힌다 — 기록이 없으니 host agent 렌더도
    skill 도 후보에 오르지 않고, 그런데 SAGE 전용 tree 는 이름만으로 지워진다. 그 결과 **첫
    실행이 증거를 지우고**, 손상된 host JSON 이 그대로 남은 두 번째 실행이 `COMPLETE` 를 냈다.

    구조 판정은 `manifest_contract` 가 한다. install 도 같은 함수를 보므로, 쓰는 쪽이 거부하는
    모양을 읽는 쪽이 받아들이는 일이 성립하지 않는다.
    """
    path = manifest_path(dest)
    blocked = candidate_block(os.path.realpath(dest), path, following=False)
    if blocked:
        # manifest 를 못 믿으면 설치 증명 자체가 없다. 읽지 않고 차단한다.
        return None, blocked, None
    if not os.path.lexists(path):
        return None, None, None
    if not stat.S_ISREG(os.lstat(path).st_mode):
        return None, "uninstall.manifest_not_regular", None
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        return None, "uninstall.manifest_unreadable", [_shared.damage_io(
            _shared.errno_name(exc))]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, "uninstall.manifest_unreadable", [_shared.damage_encoding(exc.start)]
    # host JSON 과 **같은 fail-closed 파서**를 쓴다. 중복 key 를 조용히 접으면 우리가 읽은
    # 설치 기록과 파일에 적힌 기록이 달라지고, 그 기록이 곧 삭제 근거다.
    document = _shared.parse_host_json(text)
    if isinstance(document, _shared.Outcome):
        return None, "uninstall.manifest_unreadable", list(document.damage)
    structural = _contract.violation(document)
    if structural is not None:
        return None, "uninstall.manifest_contract_violation", [structural]
    return document, None, None


HOST_REGISTRATION_FILES = ((".claude", "settings.json", "claude"),
                           (".codex", "hooks.json", "codex"))


def canonical_commands(target):
    """이 host 에 SAGE 가 등록했을 command 문자열 집합."""
    return _shared.canonical_hook_commands(
        [hook_id for hook_id, _form in _managed.CORE_HOOKS],
        lambda hook_id: hook_command_template(target, hook_id, platform_name=os.name))


def read_host_outcome(path, target):
    """host 파일 하나에 대한 **유일한** 판정. 계획·흔적·실행이 전부 이것을 부른다.

    한때 이 자리에 파서가 다섯 벌 있었다 — 등록을 세는 것, 제거 가능성을 보는 것, 흔적을 세는
    것, 손상을 세는 것, 실행 층이 쓰기 직전에 도는 것. 다섯이 같은 파일을 조금씩 다르게 읽었고,
    문법이 깨진 JSON 을 어떤 것은 "등록 없음" 으로 접고 어떤 것은 보지도 않았다. 그래서 첫
    실행이 설치 증거까지 지우고, 손상 파일이 그대로 남은 두 번째 실행이 `COMPLETE` 를 냈다.

    읽기 실패를 **부재로 접지 않는 것**이 이 함수의 전부다. 못 읽었으면 못 읽었다고 말하고,
    등록이 있는지 없는지는 호출자가 manifest 같은 다른 증거로 판단한다.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        return _shared.io_outcome(exc)
    return _shared.classify_host_bytes(raw, canonical_commands(target), target)


def host_registration_files(dest):
    """(target, 경로) — 존재하는 host 등록 파일. 종류는 묻지 않는다.

    `isfile` 로 거르지 않는 이유는, 디렉터리나 끊어진 symlink 가 그 이름에 있는 것도 **읽을 수
    없다**는 사실이지 **없다**는 사실이 아니기 때문이다. 읽기를 시도해야 그 구별이 판정에 실린다.
    """
    found = []
    for host_dir, name, target in HOST_REGISTRATION_FILES:
        path = os.path.join(os.path.abspath(dest), host_dir, name)
        if os.path.lexists(path):
            found.append((target, path))
    return tuple(found)


def host_outcomes(dest):
    """(target, 경로, 판정) 전부."""
    return tuple((target, path, read_host_outcome(path, target))
                 for target, path in host_registration_files(dest))


def manifest_installed_hosts(manifest):
    """manifest 가 **설치를 증명하는** host 집합.

    파일을 읽을 수 없을 때 우리에게 남는 유일한 소유권 증거다. `installed_hosts` 가 정본이고,
    그 key 가 없던 시절의 설치를 위해 `host_runtime` 도 본다 — 구버전 설치를 증거 없음으로
    접으면 그 프로젝트에서는 손상 파일이 영원히 보고되지 않는다.
    """
    hosts = set()
    if not isinstance(manifest, dict):
        return hosts
    declared = manifest.get("installed_hosts")
    if isinstance(declared, list):
        hosts.update(item for item in declared if item in ("claude", "codex"))
    primary = manifest.get("host_runtime")
    if primary in ("claude", "codex"):
        hosts.add(primary)
    return hosts


def is_residual(target, outcome, installed_hosts):
    """이 host 파일이 **손대지 못한 채 남은 SAGE 잔재**인가.

    남았다면 설치 증거(manifest tree)를 함께 남겨야 한다. 증거를 지우고 잔재만 남기면, 다음
    실행은 무엇이 왜 남았는지 증명할 방법 없이 그 파일을 마주하게 된다 — 그때 할 수 있는 정직한
    행동은 "모르겠다" 뿐이고, 그건 사용자에게 아무 쓸모가 없다.

    `PRESENT` 는 우리 command 를 실제로 봤다는 뜻이라 그 자체가 증거다. `UNKNOWN` 은 보지
    못했다는 뜻이라, manifest 가 이 host 설치를 증명할 때만 잔재로 센다 — 증명 없이 남의
    읽을 수 없는 설정 파일을 "SAGE 잔재" 라고 부르면 그건 우리가 모르는 것을 주장하는 것이다.
    """
    if outcome.state == _shared.PRESENT:
        return True
    if outcome.state == _shared.UNKNOWN:
        return target in installed_hosts
    return False


def active_registrations(dest):
    """SAGE canonical hook 등록이 **실제로 살아 있는** host 파일들.

    파일 존재만으로 세지 않는다. `.claude/settings.json` 은 SAGE 없이도 있을 수 있는 사용자
    파일이고, 그것을 흔적으로 세면 SAGE 를 써 본 적 없는 프로젝트가 `BLOCKED` 를 받는다.
    """
    return tuple(path for _target, path, outcome in host_outcomes(dest)
                 if outcome.state == _shared.PRESENT)


def damaged_registrations(dest):
    """SAGE 등록이 **보이는데도** 골라낼 수 없는 host 파일들. `(경로, 판정)` 을 돌려준다.

    `UNKNOWN` 은 여기 들어오지 않는다. 이 함수는 manifest 가 없는 분기에서 쓰이고, 그 분기에는
    소유권 증거가 하나도 없다 — 읽지 못한 남의 설정 파일을 SAGE 잔재로 세면 SAGE 를 설치한 적
    없는 프로젝트가 매 실행 `PARTIAL` 을 받는다.
    """
    return tuple((path, outcome) for _target, path, outcome in host_outcomes(dest)
                 if outcome.state == _shared.PRESENT and outcome.damage)


def sage_traces(dest):
    """"SAGE 흔적" 의 정본 정의 — 네 tree 와 **active** canonical hook 등록.

    좁게 정의하는 것이 핵심이다. `plan_docs`·vault·보존된 최상위 문서를 흔적으로 세면 첫
    uninstall 직후 두 번째 실행이 `BLOCKED` 가 되고, 그러면 멱등 계약이 깨진다 — 정상적으로
    끝낸 사용자가 다음 실행에서 "안전한 계획을 만들 수 없다" 는 말을 듣는다.
    """
    found = [path for path in _managed.sage_tree_paths(dest) if os.path.isdir(path)]
    # **우리가 영원히 손대지 않을 파일은 흔적이 아니다.** 손상된 host JSON 은 언제나 보존이고,
    # 그것을 흔적으로 세면 첫 제거를 정상적으로 끝낸 사용자가 다음 실행마다 `BLOCKED` 를 받는다 —
    # 고칠 방법도 우리가 주지 않으면서. 흔적은 "증명만 있으면 처리할 것" 이어야 한다.
    damaged = {path for path, _outcome in damaged_registrations(dest)}
    found.extend(path for path in active_registrations(dest) if path not in damaged)
    return tuple(found)


# --- 소유권 판정 -------------------------------------------------------------

def candidate_block(root, path, *, following):
    """후보 하나를 읽거나 쓰기 **전에** 거는 관문. 통과하면 `None`.

    `following` 은 "leaf 를 따라가서 쓸 것인가" 다. `STRIP` 은 파일 내용을 다시 쓰므로 leaf 가
    symlink 면 **그 링크가 가리키는 남의 파일**을 고치게 된다 — 그래서 따라가지 않고 수렴시킨다.
    `DELETE` 는 link 자체만 옮기므로 leaf symlink 가 위반이 아니다.

    이 함수를 후보마다 부르는 이유는, 검사를 몇몇 자리에만 걸면 걸지 않은 자리가 곧 통로가
    되기 때문이다. manifest·host JSON·`.gitignore` 도 예외가 아니다.
    """
    if not within_root(root, path):
        return "uninstall.path_escape"
    if symlink_component_below(root, path):
        return "uninstall.symlink_component"
    if following and os.path.islink(path):
        return "uninstall.symlink_leaf_write"
    return None


def _has_sage_signature(skill_dir):
    """`SKILL.md` 가 SAGE hand-ship marker 를 갖는가.

    공유 공간에서 이름만 같은 사용자 skill 을 오삭제하지 않기 위한 유일한 근거다. 읽을 수
    없으면 근거가 없는 것이고, 근거가 없으면 지우지 않는다.
    """
    path = os.path.join(skill_dir, "SKILL.md")
    try:
        with open(path, encoding="utf-8") as handle:
            return _managed.LEGACY_SKILL_SIGNATURE in handle.read()
    except (OSError, ValueError):
        return False


def _profile_prefix(dest):
    """profile 의 `project.prefix`. 없거나 안전하지 않으면 `None`.

    빈 prefix 를 그대로 쓰면 `<prefix>-<aid>` 가 `-<aid>` 가 되어 전혀 다른 경로를 가리킨다.
    그 경로가 사용자 것일 수 있으므로 빈 값은 가족 전체를 포기하는 근거다.
    """
    import re

    path = os.path.join(os.path.abspath(dest), "sage", "project-profile.yaml")
    if not os.path.isfile(path):
        return None
    try:
        import yaml
        with open(path, encoding="utf-8") as handle:
            profile = yaml.safe_load(handle.read())
    except Exception:
        return None
    if not isinstance(profile, dict):
        return None
    prefix = str(((profile.get("project") or {}).get("prefix") or "")).strip()
    if not prefix or not re.fullmatch(r"[A-Za-z0-9_-]+", prefix):
        return None
    return prefix


def _manifest_agent_renders(manifest):
    """manifest 가 배치를 기록한 `<host>/agents/<id>` 목록.

    이 기록이 소유권 증명이다. 이름만으로 지우면 사용자가 직접 만든 `leader.md` 를 삼킬 수 있고,
    `.claude/agents/` 는 사용자도 자기 agent 를 두는 **공유 디렉터리**라 그 위험이 실재한다.

    roster 와 교집합을 잡는 것은 manifest 가 손상·조작됐을 때를 위한 두 번째 근거다. 증명이
    하나뿐이면 그 하나가 틀리는 순간 남의 파일을 지운다.
    """
    renders = manifest.get("core_renders")
    if not isinstance(renders, dict):
        return ()
    known = set(_managed.CORE_AGENTS) | set(_managed.LEGACY_CORE_AGENTS)
    found = []
    for key in sorted(renders):
        if not isinstance(key, str):
            continue
        parts = key.split("/")
        if len(parts) != 3 or parts[1] != "agents":
            continue
        host, _, agent_id = parts
        if host not in ("claude", "codex") or agent_id not in known:
            continue
        found.append((host, agent_id))
    return tuple(found)


def _manifest_skill_ids(manifest):
    """manifest 가 기록한 `skills/<aid>` 자산 id 집합.

    계약이 이미 key 문법을 막지만 여기서 **한 번 더** 거른다. 이 id 는 값이 아니라 전역 skill
    경로의 조각이 되므로, 계약을 지나오지 않은 호출이 하나라도 생기면 그 자리가 곧 경로 탈출
    통로다. 방어를 계약 하나에만 두면 그 계약을 안 거치는 경로가 생겼을 때 아무것도 남지 않는다.
    """
    assets = manifest.get("assets")
    if not isinstance(assets, dict):
        return set()
    found = set()
    for key in assets:
        if _contract.asset_key_violation(key) is not None:
            continue
        kind, asset_id = key.split("/", 1)
        if kind == "skills":
            found.add(asset_id)
    return found


def _same_bytes(left, right):
    try:
        with open(left, "rb") as a, open(right, "rb") as b:
            return a.read() == b.read()
    except OSError:
        return False


def conflicting_actions(actions):
    """같은 경로를 두 번 주장하는 action 들. 없으면 빈 tuple.

    ## 왜 이것이 P0 인가

    `--global` 자산에는 두 가족이 있다 — 이름이 CORE id 그대로인 것과 `<prefix>-<aid>` 로 렌더된
    것이다. 둘은 서로 다른 근거(marker / manifest·prefix·byte 일치)로 판정되는데, prefix 가
    `sage` 이고 manifest 에 `skills/init` 이 있으면 **둘 다 `$CODEX_HOME/skills/sage-init` 을
    가리킨다.**

    그때 사본이 다르면 같은 경로에 `DELETE` 와 `PRESERVE` 가 함께 생긴다. 실행은 지우고, 보고는
    양쪽에 같은 경로를 싣는다 — **보존한다고 말한 사용자 변경본을 지우는 것**이다. 사본이 같으면
    `DELETE` 가 둘이라 write target 에도 중복이 남는다.

    ## 왜 우선순위를 정하지 않는가

    한쪽을 이기게 하는 규칙은 "어느 근거가 더 강한가" 를 우리가 정하는 일이다. 그런데 여기서
    실제로 벌어진 일은 **두 근거가 같은 파일에 대해 서로 다른 결론을 냈다**는 것이고, 그건 우리가
    그 파일을 무엇으로 아는지 모른다는 뜻이다. 모르는 상태에서 되돌릴 수 없는 삭제를 고르는 것보다
    멈추는 편이 낫다. 마지막 action 으로 덮는 것은 더 나쁘다 — 순서가 판정이 된다.
    """
    seen = {}
    conflicts = []
    for action in actions:
        key = os.path.normcase(os.path.normpath(os.path.abspath(action.path)))
        if key in seen:
            conflicts.append((seen[key], action))
            continue
        seen[key] = action
    return tuple(conflicts)


# --- 계획 조립 ---------------------------------------------------------------

# 처리 순서. 등록을 실행 파일보다 먼저 지우고(J20), manifest 를 담은 tree 를 맨 마지막에
# 지운다(J21) — 중간에 실패해도 그때까지는 소유권을 다시 증명할 수 있어야 한다.
GROUP_ORDER = ("registration", "host-skill", "global-skill", "tree", "manifest-tree", "prune")


def _project_actions(dest, manifest):
    """`(actions, residual)`. `residual` 은 손대지 못한 채 남은 host 등록 파일들이다."""
    actions = []
    residual = []
    root = os.path.abspath(dest)
    installed_hosts = manifest_installed_hosts(manifest)

    for target, path in host_registration_files(root):
        blocked = candidate_block(root, path, following=True)
        if blocked:
            # 읽지 않았으므로 등록 상태를 주장하지 않는다. 그래도 manifest 가 이 host 설치를
            # 증명하면 우리 등록이 저 안에 남아 있을 수 있고, 그건 잔재다.
            actions.append(Action(PRESERVE, SCOPE_PROJECT, path, blocked,
                                  state=_shared.UNKNOWN))
            if target in installed_hosts:
                residual.append(path)
            continue
        outcome = read_host_outcome(path, target)
        if outcome.strippable:
            actions.append(Action(STRIP, SCOPE_PROJECT, path,
                                  "uninstall.strip_host_registration", group="registration",
                                  state=outcome.state))
            continue
        if outcome.state == _shared.ABSENT:
            # 문서는 멀쩡하고 우리 등록은 없다. 아는 사실이라 조용해도 된다.
            continue
        if outcome.state == _shared.PRESENT:
            # 우리 command 를 실제로 봤는데 골라낼 수 없다.
            reason = "uninstall.host_json_damaged"
        elif target in installed_hosts:
            # 보지는 못했지만 manifest 가 이 host 설치를 증명한다. 우리 것이 저 안에 있다고
            # 봐야 하고, 있다면 우리는 그것을 지우지 못한 채 끝나는 것이다.
            reason = "uninstall.host_json_damaged"
        else:
            # 증거가 하나도 없다. 못 읽었다는 사실만 말하고 SAGE 잔재라고 부르지 않는다.
            reason = "uninstall.host_json_unreadable"
        actions.append(Action(PRESERVE, SCOPE_PROJECT, path, reason, outcome.as_json(),
                              state=outcome.state))
        if is_residual(target, outcome, installed_hosts):
            residual.append(path)

    gitignore = os.path.join(root, ".gitignore")
    gitignore_block = (candidate_block(root, gitignore, following=True)
                       if os.path.lexists(gitignore) else None)
    if gitignore_block:
        actions.append(Action(PRESERVE, SCOPE_PROJECT, gitignore, gitignore_block))
    elif os.path.lexists(gitignore):
        # bytes 로 읽고 판정에 맡긴다. 계획 층에서 `open(..., encoding="utf-8")` 로 읽으면
        # 비 UTF-8 `.gitignore` 하나가 계획 자체를 traceback 으로 끝낸다 — 아무것도 지우지
        # 않는 `--check` 조차 결과를 못 내고, `--json` 소비자는 깨진 출력을 받는다.
        try:
            with open(gitignore, "rb") as handle:
                outcome = _shared.classify_gitignore_bytes(handle.read())
        except OSError as exc:
            outcome = _shared.io_outcome(exc)
        if outcome.strippable:
            actions.append(Action(STRIP, SCOPE_PROJECT, gitignore,
                                  "uninstall.strip_gitignore", group="registration"))
        elif outcome.state != _shared.ABSENT:
            actions.append(Action(PRESERVE, SCOPE_PROJECT, gitignore,
                                  "uninstall.gitignore_marker_damaged", outcome.as_json()))

    for host in ("claude", "codex"):
        for skill_id in list(_managed.all_skill_ids()) + list(_managed.LEGACY_CORE_SKILLS):
            path = _managed.project_skill_dir(root, host, skill_id)
            if not os.path.isdir(path):
                continue
            blocked = candidate_block(root, path, following=False)
            if blocked:
                actions.append(Action(PRESERVE, SCOPE_PROJECT, path, blocked))
                continue
            legacy = skill_id in _managed.LEGACY_CORE_SKILLS
            if legacy and not _has_sage_signature(path):
                actions.append(Action(PRESERVE, SCOPE_PROJECT, path,
                                      "uninstall.skill_signature_missing"))
                continue
            actions.append(Action(DELETE, SCOPE_PROJECT, path,
                                  "uninstall.core_skill", group="host-skill"))

    # host agent 렌더. manifest 가 배치를 기록한 것만 후보다 — `.claude/agents/` 는 사용자도
    # 자기 agent 를 두는 자리라, 기록 없이 이름만으로 지우면 남의 것을 지운다.
    for host, agent_id in _manifest_agent_renders(manifest):
        path = _managed.host_agent_render(root, host, agent_id)
        if not os.path.isfile(path):
            continue
        blocked = candidate_block(root, path, following=False)
        if blocked:
            actions.append(Action(PRESERVE, SCOPE_PROJECT, path, blocked))
            continue
        actions.append(Action(DELETE, SCOPE_PROJECT, path, "uninstall.core_agent",
                              group="host-skill"))

    manifest_tree = os.path.join(root, "docs", "sage_harness")
    for path in _managed.sage_tree_paths(root):
        if not os.path.isdir(path):
            continue
        blocked = candidate_block(root, path, following=False)
        if blocked:
            actions.append(Action(PRESERVE, SCOPE_PROJECT, path, blocked))
            continue
        if path == manifest_tree and residual:
            # **영수증은 잔재보다 오래 살아야 한다.** manifest 는 무엇이 설치됐는지에 대한
            # 유일한 증거이고, 손대지 못한 host 설정이 남은 채로 그것을 지우면 다음 실행은
            # 그 파일이 왜 거기 있는지 증명할 방법을 잃는다. 사용자가 JSON 을 고쳐서 우리가
            # 마지막 논리 자산까지 뺄 수 있게 됐을 때에만 이 tree 를 지운다.
            actions.append(Action(PRESERVE, SCOPE_PROJECT, path,
                                  "uninstall.receipt_retained_for_residual"))
            continue
        group = "manifest-tree" if path == manifest_tree else "tree"
        actions.append(Action(DELETE, SCOPE_PROJECT, path, "uninstall.sage_tree", group=group))

    # framework 배포본. 소유권 근거는 **manifest 가 배치를 기록했다** 는 사실이고, 내용이
    # 현재 번들과 같은지는 근거로 쓰지 않는다 — 사용자가 고친 배포본은 지우지 않아야 하므로
    # 여기서는 내용 일치를 **보존 조건**으로만 본다.
    bundle = os.path.join(_resources.core_dir(), "framework")
    agent_rel = [os.path.join("docs", "agent", name)
                 for name in _managed.framework_agent_docs(bundle)]
    for rel in tuple(_managed.FRAMEWORK_FILES) + tuple(agent_rel):
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        blocked = candidate_block(root, path, following=False)
        if blocked:
            actions.append(Action(PRESERVE, SCOPE_PROJECT, path, blocked))
            continue
        # 배포한 그대로일 때만 지운다. 불일치는 보존 근거이지만, **왜** 다른지는 우리가 모른다.
        # 사용자가 고쳤을 수도 있고 구버전으로 설치했을 수도 있다 — 설치 시점의 내용을 기록해
        # 두지 않았으므로 둘을 구별할 방법이 없다. 그래서 "사용자가 고쳤다" 고 말하지 않고
        # "현재 번들과 다르다" 는 아는 사실만 말한다. 보지 않은 것을 봤다고 하지 않는 것과
        # 같은 규칙이다.
        source = os.path.join(bundle, rel)
        if os.path.isfile(source) and not _same_bytes(source, path):
            actions.append(Action(PRESERVE, SCOPE_PROJECT, path, "uninstall.framework_content_differs"))
            continue
        actions.append(Action(DELETE, SCOPE_PROJECT, path, "uninstall.framework_asset",
                              group="tree"))
    for name in _managed.FRAMEWORK_DOCS:
        path = os.path.join(root, f"{name}.md")
        if os.path.isfile(path):
            actions.append(Action(PRESERVE, SCOPE_PROJECT, path,
                                  "uninstall.ownership_unprovable"))

    actions.extend(_prune_candidates(root, actions))
    return actions, residual


def _prune_candidates(root, actions):
    """처리 뒤 **실제로 빌** 부모만 정리 후보로 올린다.

    승인된 이름(`PRUNABLE_PARENTS`)만 대상이다. "비었으면 지운다" 를 모든 부모에 적용하면
    사용자가 그 자리에 의도적으로 둔 빈 디렉터리를 지우게 되고, 그건 우리가 만들지 않은 것을
    치우는 일이다.

    남는 것이 하나라도 있으면 후보에서 빠진다 — unknown sibling 이 있는 `docs/agent` 는
    정리 대상이 아니다. 판정은 **계획 시점의 예상**이고, 실행 층이 실제로 비었는지 다시 본다.
    """
    removed = {action.path for action in actions if action.kind == DELETE}
    candidates = []
    for rel in _managed.PRUNABLE_PARENTS:
        path = os.path.join(root, rel)
        if not os.path.isdir(path) or os.path.islink(path):
            continue
        if candidate_block(root, path, following=False):
            continue
        survivors = []
        for name in sorted(os.listdir(path)):
            child = os.path.join(path, name)
            if child in removed or child in candidates:
                continue
            survivors.append(name)
        if survivors:
            continue
        candidates.append(path)
    # 깊은 것부터 지워야 `docs/agent` → `docs` 순서가 성립한다.
    candidates.sort(key=lambda item: item.count(os.sep), reverse=True)
    return [Action(DELETE, SCOPE_PROJECT, path, "uninstall.empty_parent", group="prune")
            for path in candidates]


def _global_actions(dest, manifest, scope, root):
    """전역 자산. **`--global` 을 포함한 범위에서만 호출된다.**

    project 범위에서 이 함수가 불리면 `$CODEX_HOME` 을 읽게 되고, 그 순간 scope 격리가 깨진다.
    호출자가 분기를 지키는 것이 계약이라, root 도 호출자가 만들어 넘긴다 — 이 함수 안에서
    환경을 읽으면 분기를 지켜도 읽기가 새어 나간다.
    """
    actions = []
    if not os.path.isdir(root):
        return actions

    for skill_id in list(_managed.all_skill_ids()) + list(_managed.LEGACY_CORE_SKILLS):
        path = os.path.join(root, skill_id)
        blocked = candidate_block(root, path, following=False)
        if blocked:
            actions.append(Action(PRESERVE, SCOPE_GLOBAL, path, blocked))
            continue
        if not os.path.isdir(path):
            continue
        if not _has_sage_signature(path):
            actions.append(Action(PRESERVE, SCOPE_GLOBAL, path,
                                  "uninstall.skill_signature_missing"))
            continue
        actions.append(Action(DELETE, SCOPE_GLOBAL, path,
                              "uninstall.core_skill", group="global-skill"))

    # `<prefix>-<aid>` 가족은 `--all` 에서만, 그것도 넷을 모두 만족할 때만 지운다. 이 배포본은
    # 프로젝트 렌더라 SAGE marker 를 갖지 않으므로, 소유권 근거가 marker 가 아니라 **범위 ·
    # manifest 기록 · 안전한 prefix · 프로젝트 사본과의 byte 일치** 의 결합이다.
    if scope != SCOPE_ALL:
        return actions
    prefix = _profile_prefix(dest)
    if prefix is None:
        return actions
    for aid in sorted(_manifest_skill_ids(manifest)):
        path = os.path.join(root, f"{prefix}-{aid}")
        # **조회 전에** 경계를 본다. `isdir` 하나도 root 밖에 대해서는 하지 않는다 — 계획이
        # 외부 경로를 들여다본 사실 자체가 J8 이 막는 것이고, 그 뒤에 오는 지문·비교는 전부
        # 그 위반 위에 세워진다.
        if candidate_block(root, path, following=False):
            actions.append(Action(PRESERVE, SCOPE_GLOBAL, path,
                                  "uninstall.path_escape"))
            continue
        if not os.path.isdir(path):
            continue
        project_copy = os.path.join(os.path.abspath(dest), ".codex", "skills", aid, "SKILL.md")
        global_copy = os.path.join(path, "SKILL.md")
        if not _same_bytes(project_copy, global_copy):
            # 손댄 사본이다. 지우면 사용자 편집을 삼키는 것이고, 되돌릴 수 없다.
            actions.append(Action(PRESERVE, SCOPE_GLOBAL, path,
                                  "uninstall.global_copy_drifted"))
            continue
        actions.append(Action(DELETE, SCOPE_GLOBAL, path,
                              "uninstall.generated_skill", group="global-skill"))
    return actions


def build(dest, scope, environ=None):
    """읽기만 해서 불변 계획 하나를 만든다. 어떤 경로에서도 파일을 바꾸지 않는다."""
    # root 를 먼저 실경로로 확정한다. 이후 모든 판정이 이 root 기준이므로, 어떤 경로로 찾아
    # 왔는지와 무관하게 같은 결론이 나온다.
    dest = os.path.realpath(dest)
    notices = []

    if scope in (SCOPE_PROJECT, SCOPE_ALL):
        reason = boundary_block(dest)
        if reason:
            return UninstallPlan(scope, dest, (), BLOCKED, reason)

    manifest, damaged = (None, None)
    if scope in (SCOPE_PROJECT, SCOPE_ALL):
        manifest, damaged, detail = read_manifest(dest)
        if damaged:
            # 좌표를 BLOCK action 에 실어 보낸다. 사유 code 하나만 내면 사용자는 manifest 의
            # 어디가 왜 문제인지 모른 채 같은 화면을 반복해서 받는다.
            blocked_actions = (Action(BLOCK, SCOPE_PROJECT, manifest_path(dest), damaged,
                                      detail),)
            return UninstallPlan(scope, dest, blocked_actions, BLOCKED, damaged)
        if manifest is None:
            traces = sage_traces(dest)
            damaged = damaged_registrations(dest)
            if not traces and damaged:
                # 지울 수 있는 것은 없고, 손댈 수 없는 것만 남았다. 차단은 사용자가 할 수 있는
                # 일이 있을 때 쓰는 판정이다 — 여기서는 없으므로, 남은 것을 보고하고 끝낸다.
                actions = [Action(PRESERVE, SCOPE_PROJECT, path,
                                  "uninstall.host_json_damaged", outcome.as_json(),
                                  state=outcome.state)
                           for path, outcome in damaged]
                return UninstallPlan(scope, dest, actions, PARTIAL, None,
                                     ("uninstall.notice.residual_hook_error",
                                      "uninstall.notice.preserved_user_assets"))
            if traces:
                # 흔적은 있는데 무엇을 배치했는지 증명할 것이 없다. 추측해서 지우는 것이 이
                # 명령이 절대 하지 않기로 한 일이다.
                actions = [Action(BLOCK, SCOPE_PROJECT, path, "uninstall.trace_without_manifest")
                           for path in traces]
                return UninstallPlan(scope, dest, actions, BLOCKED,
                                     "uninstall.manifest_missing_with_traces")
            return UninstallPlan(scope, dest, (), COMPLETE, None,
                                 ("uninstall.notice.nothing_installed",))

    actions = []
    residual = ()
    global_root = None
    if scope in (SCOPE_PROJECT, SCOPE_ALL):
        project_actions, residual = _project_actions(dest, manifest or {})
        actions.extend(project_actions)
    if scope in (SCOPE_GLOBAL, SCOPE_ALL):
        # 전역 root 를 **여기서만** 만든다. project 분기에서는 이 줄에 닿지 않으므로
        # `$CODEX_HOME` 을 읽는 일도 없다.
        global_root = os.path.realpath(_managed.codex_global_skills_root(environ))
        if _is_broad_path(global_root):
            # `$CODEX_HOME` 이 `/` 면 전역 root 는 `/skills` 다. project dest 에 걸던 경계를
            # 전역에만 걸지 않으면, 같은 실수가 다른 문으로 그대로 들어온다.
            return UninstallPlan(scope, dest, (), BLOCKED, "uninstall.global_root_too_broad")
        actions.extend(_global_actions(dest, manifest or {}, scope, global_root))

    if scope == SCOPE_PROJECT:
        # 전역을 **읽지 않았으므로** 무엇이 남았는지 말하지 않는다. 보지 않은 것을 봤다고
        # 하지 않는 것이 이 고지의 전부다.
        notices.append("uninstall.notice.global_not_checked")
    if scope in (SCOPE_GLOBAL, SCOPE_ALL):
        notices.append("uninstall.notice.global_shared_warning")
    if residual:
        # 남은 등록은 아직 hook 을 부른다. 그 상태에서 CLI 패키지를 먼저 지우면 host 는
        # 없는 실행 파일을 부르고, 사용자는 uninstall 과 무관해 보이는 오류를 매 세션 받는다.
        notices.append("uninstall.notice.residual_hook_error")
    notices.append("uninstall.notice.preserved_user_assets")
    notices.append("uninstall.notice.pipx_removal")

    clash = conflicting_actions(actions)
    if clash:
        # 두 근거가 같은 경로에 다른 결론을 냈다. 어느 쪽도 고르지 않는다.
        blocked_actions = tuple(
            Action(BLOCK, first.scope, first.path, "uninstall.action_conflict",
                   [{"kind": "conflict", "first": first.reason, "second": second.reason}])
            for first, second in clash)
        return UninstallPlan(scope, dest, blocked_actions, BLOCKED,
                             "uninstall.action_conflict", global_root=global_root)

    preserved = [a for a in actions if a.kind == PRESERVE]
    status = PARTIAL if preserved else COMPLETE
    if not actions:
        status = COMPLETE
    return UninstallPlan(scope, dest, _ordered(actions), status, None, notices,
                         global_root=global_root)


def _ordered(actions):
    """결정론 정렬. 같은 저장소 상태가 실행마다 다른 계획을 내면 기계가 대조할 수 없다.

    `prune` 만 **깊은 것부터** 정렬한다. 경로 오름차순으로 두면 `docs` 가 `docs/agent` 보다
    먼저 와서, 부모를 볼 때 자식이 아직 남아 있다 — 실행 층의 "비었을 때만 지운다" 가 언제나
    거짓이 되어 빈 부모가 조용히 남는다. 정렬이 계약을 무효로 만드는 자리라 여기서 지킨다.
    """
    order = {name: index for index, name in enumerate(GROUP_ORDER)}
    kind_rank = {STRIP: 0, DELETE: 1, PRESERVE: 2, BLOCK: 3}

    def key(action):
        depth = -action.path.count(os.sep) if action.group == "prune" else 0
        return (order.get(action.group, len(GROUP_ORDER)), kind_rank.get(action.kind, 9),
                action.scope, depth, action.path)

    return sorted(actions, key=key)
