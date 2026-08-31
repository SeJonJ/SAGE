"""manifest 가 **읽어도 되는 모양인가**에 대한 하나의 답.

## 왜 별도 모듈인가

install 은 이미 이 질문에 답하고 있었다. 재설치 전에 기존 manifest 를 검사해서, 정규화하거나
버릴 필드가 있으면 fail-closed 로 멈춘다. 그런데 uninstall 은 같은 파일을 읽으면서
**최상위가 dict 인가**만 봤다. 그래서 `{}` 도, `assets` 가 문자열인 것도, `host_runtime` 이
없는 것도 정상 manifest 로 통과했다.

그 차이가 실제로 무엇을 했는가: 빈 manifest 는 "설치는 증명됐고 배치 기록은 하나도 없다" 로
읽힌다. 배치 기록이 없으니 host agent 렌더도 skill 도 후보에 오르지 않고, 그런데 SAGE 전용
tree 는 이름만으로 지워진다. 그래서 **첫 실행이 manifest 를 지우고**, 손상된 host JSON 이
그대로 남은 두 번째 실행이 `COMPLETE(0)` 를 냈다. 증거를 먼저 지우고 나서 "증거가 없으니
할 일도 없다" 고 말한 것이다.

읽는 쪽마다 다른 기준을 두면 언제나 **가장 느슨한 쪽**이 실제 기준이 된다. 그래서 기준을
여기 하나로 둔다.

## 무엇을 보고 무엇을 보지 않는가

여기서 보는 것은 **끝까지**다 — 필수 필드·타입·host 이름에 더해, 자산 key 의 문법, 자산 항목의
해시 형식, `core_renders` receipt 의 SHA-256 과 semantic source 쌍, skill receipt 의 scope 규칙까지
전부 이 모듈이 소유한다.

처음에는 깊은 검사를 install 에 남겨 뒀다. "재설치가 무엇을 덮어쓸지 정하는 판단이라 소비자가
다르다" 고 봤는데 틀렸다 — **uninstall 이 소유권 증명에 쓰는 것이 바로 그 깊은 값**이다.
receipt 가 있다는 사실만으로 공유 디렉터리의 파일을 지우므로, receipt 가 비어 있으면 우리는
무엇을 배치했는지 모르는 상태이고 모르는 상태의 삭제는 남의 파일을 지우는 일이다. 통합은
남긴 것이 없을 때만 끝난 것이다.

판정은 언어를 타지 않는다. code 와 필드 이름만 돌려주고 문장은 호출자가 만든다 — 한국어
실행과 영어 실행이 다른 결론을 내면 그건 판정이 아니라 표시다.

## 필수 필드는 왜 셋뿐인가

`manifest.schema.json` 이 요구하는 셋(`sage_version`·`host_runtime`·`assets`)만 필수다.
`installed_hosts`·`core_renders` 는 나중에 생긴 key 라, 없다고 손상으로 부르면 구버전으로
설치한 프로젝트가 제거 자체를 못 하게 된다. **없는 것과 틀린 것은 다르고**, 여기서 막아야
하는 것은 뒤엣것이다. 그래서 있을 때만 타입을 본다.
"""

import re

# 자산 id 의 모양은 저장소에 이미 정본이 있다. 여기서 정규식을 새로 쓰면 같은 질문에 답하는
# 판정이 또 하나 늘고, 둘이 갈라지는 날 느슨한 쪽이 실제 기준이 된다.
from sage.hook_launcher import valid_hook_id as _valid_asset_id

# manifest 가 쓰는 자산 종류. `asset_paths` 의 kind 를 복수형으로 쓴 것이 key prefix 다.
ASSET_KINDS = ("hooks", "agents", "skills", "mcps")

KNOWN_HOSTS = ("claude", "codex")

REQUIRED_FIELDS = ("sage_version", "host_runtime", "assets")


# 좌표에 그대로 실어도 되는 이름의 모양. 식별자꼴 조각을 최대 셋까지 `/` 로 이은 것만 통과한다 —
# manifest 가 정상일 때 쓰는 이름(`assets`·`hooks/post-tool-logger`·`claude/agents/leader`)은 전부
# 이 모양이고, 사용자가 넣은 임의 문자열은 대개 아니다.
_SAFE_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
REDACTED = "<redacted>"


def safe_field(value):
    """좌표에 실어도 되는 값인가. 아니면 가린다.

    ## 왜 가리는 쪽이 기본인가

    손상된 manifest 의 key 는 **사용자가 쓴 문자열**이다. 절대 경로일 수도, 개행이 든 값일 수도,
    비밀이 든 값일 수도 있다. 그것을 진단에 실으면 화면·`--json`·CI 로그·이슈로 그대로 흘러가고,
    개행이 든 값은 목록 한 줄을 두 줄로 만들어 우리가 쓰지 않은 문장을 화면에 끼워 넣는다.

    실제로 `skills//Users/alice/private\nFORGED` 같은 key 가 `detail` 에 원문 그대로 나왔다.
    **가려서 잃는 것은 편의고 실어서 잃는 것은 사용자 데이터**라, 둘 중에서는 언제나 앞을 버린다.
    잃은 좌표는 `index` 로 대신한다 — 몇 번째 항목인지는 우리가 만든 값이라 안전하다.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return REDACTED
    parts = value.split("/")
    if 1 <= len(parts) <= 3 and all(_SAFE_SEGMENT.match(part) for part in parts):
        return value
    return REDACTED


def _violation(code, **fields):
    """위반 하나. **모든 값이 이 관문을 지난다.**

    가리는 판정을 호출부마다 두면 한 곳을 빠뜨리는 순간 그 자리가 유출 경로가 된다. 그래서
    만드는 자리 하나에서 건다 — install 과 uninstall 이 같은 dict 를 소비하므로 양쪽이 함께 안전하다.
    """
    entry = {"kind": "manifest", "code": code}
    entry.update({name: safe_field(value) for name, value in fields.items()})
    return entry


def violation(manifest):
    """구조 위반 하나, 없으면 `None`.

    첫 위반에서 멈춘다. manifest 가 깨졌을 때 호출자가 할 일은 어느 경우에나 같고(읽지 않고
    멈춘다), 위반을 더 모아도 그 행동이 달라지지 않는다.
    """
    if not isinstance(manifest, dict):
        return _violation("manifest_not_object")

    for field in REQUIRED_FIELDS:
        if field not in manifest:
            return _violation("manifest_field_missing", field=field)

    if not isinstance(manifest.get("sage_version"), str):
        return _violation("manifest_sage_version_not_string")
    if manifest.get("host_runtime") not in KNOWN_HOSTS:
        return _violation("manifest_host_runtime_invalid")

    assets = manifest.get("assets")
    if not isinstance(assets, dict):
        return _violation("manifest_assets_not_mapping")
    for index, key in enumerate(sorted(assets, key=repr)):
        value = assets[key]
        broken_key = asset_key_violation(key)
        if broken_key is not None:
            broken_key["index"] = index
            return broken_key
        entry = asset_entry_violation(value)
        if entry is not None:
            entry["index"] = index
            # 어느 자산인지 붙여서 돌려준다. 항목 하나가 깨진 것과 `assets` 자체가 깨진 것은
            # 사용자가 볼 자리가 다르다. **이 값도 같은 관문을 지난다** — 관문 밖에서 붙이는
            # 자리가 하나라도 있으면 그 자리가 유출 경로다.
            entry["asset"] = safe_field(key)
            return entry

    if "installed_hosts" in manifest:
        hosts = manifest["installed_hosts"]
        if (not isinstance(hosts, list) or not hosts
                or any(host not in KNOWN_HOSTS for host in hosts)
                or len(hosts) != len(set(hosts))):
            return _violation("manifest_installed_hosts_invalid")
        # 주 host 가 자기 목록에 없으면 둘 중 하나는 거짓이다. 어느 쪽인지 알 수 없으므로
        # 둘 다 증거로 쓰지 않는다.
        if manifest["host_runtime"] not in hosts:
            return _violation("manifest_installed_hosts_missing_primary")

    if "core_renders" in manifest:
        renders = manifest["core_renders"]
        if not isinstance(renders, dict):
            return _violation("manifest_core_renders_not_mapping")
        for index, key in enumerate(sorted(renders, key=repr)):
            receipt = renders[key]
            if not isinstance(key, str):
                return _violation("manifest_core_renders_entry_invalid", field=key,
                                  index=index)
            broken = core_render_receipt_violation(key, receipt)
            if broken is not None:
                broken["index"] = index
                return broken

    if "core_skill_receipts" in manifest:
        receipts = manifest["core_skill_receipts"]
        if not isinstance(receipts, dict):
            return _violation("manifest_core_skill_receipts_not_mapping")
        for host in sorted(receipts, key=repr):
            if host not in KNOWN_HOSTS:
                return _violation("manifest_core_skill_receipts_unknown_host", host=host)
            broken = core_skill_receipt_violation(host, receipts[host])
            if broken is not None:
                return broken

    return None


# --- 자산 항목 --------------------------------------------------------------

ASSET_FORMS = ("native", "core_adapter", "interpretive", "declarative")
CONFORMANCE_VALUES = ("PASS", "FAIL", "STALE", "UNKNOWN")
ASSET_KEYS = {
    "spec_hash", "claims_hash", "canonical_hash", "adapter_hash",
    "adapter_contract_version", "render_hash", "conformance", "form",
    "runtime_targets", "test", "safety_degraded", "l3_review_strategy",
    "risk", "unresolved", "origin",
}
_PREFIXED_SHA = re.compile(r"sha256:[0-9a-f]{64}")
_BARE_SHA = re.compile(r"[0-9a-f]{64}")


def asset_key_violation(key):
    """자산 key 하나의 **문법**. `<kind>s/<id>` 정확히 두 조각이어야 한다.

    ## 왜 값만으로는 부족한가

    이 key 는 값이 아니라 **경로 조각**으로 쓰인다. `skills/<id>` 의 `<id>` 가 전역 skill 경로
    `$CODEX_HOME/skills/<prefix>-<id>` 에 그대로 붙는다. 그래서 `skills/../../../victim` 같은
    key 하나로 계획이 write root **밖**을 가리키게 된다 — 실행 층의 2차 방어가 막더라도, 그때는
    이미 사용자가 승인한 불변 계획 안에 root 밖 대상이 들어 있고 계획을 만드는 동안 외부 경로를
    조회하고 지문까지 뜬 뒤다. 경계는 **계획을 만들기 전에** 서야 한다.

    id 판정은 `hook_launcher.valid_hook_id` 를 그대로 쓴다. 이름은 hook 에서 왔지만 저장소가
    자산 id 에 요구하는 모양의 정본이 그것 하나다.
    """
    if not isinstance(key, str):
        return _violation("manifest_assets_entry_invalid", field=key)
    parts = key.split("/")
    if len(parts) != 2:
        # 조각이 하나면 kind 가 없고, 셋 이상이면 separator 를 더 넣었다는 뜻이다.
        return _violation("manifest_asset_key_invalid", field=key)
    kind, asset_id = parts
    if kind not in ASSET_KINDS:
        return _violation("manifest_asset_kind_unknown", field=key)
    if not _valid_asset_id(asset_id):
        # 빈 id · `.` · `..` · 절대경로 · 경로 문자가 전부 여기서 걸린다.
        return _violation("manifest_asset_id_invalid", field=key)
    return None


def asset_entry_violation(value):
    """자산 항목 하나. `manifest.schema.json` 을 jsonschema 없이 대조한다."""
    if not isinstance(value, dict):
        return _violation("asset_not_mapping")
    unknown = sorted(set(value) - ASSET_KEYS)
    if unknown:
        return _violation("asset_unknown_fields", fields=", ".join(unknown))
    if value.get("form") not in ASSET_FORMS:
        return _violation("asset_form_invalid")
    if value.get("conformance") not in CONFORMANCE_VALUES:
        return _violation("asset_conformance_invalid")

    for field in ("spec_hash", "claims_hash", "canonical_hash"):
        if field in value and (not isinstance(value[field], str)
                               or _PREFIXED_SHA.fullmatch(value[field]) is None):
            return _violation("asset_hash_format_invalid", field=field)

    for field, allowed in (("adapter_hash", {"claude", "codex"}),
                           ("render_hash", {"claude", "codex", "native"})):
        if field not in value:
            continue
        hashes = value[field]
        if not isinstance(hashes, dict) or not hashes:
            return _violation("asset_key_not_nonempty_mapping", field=field)
        unknown_targets = sorted(set(hashes) - allowed)
        if unknown_targets:
            return _violation("asset_key_unknown_targets", field=field,
                              targets=", ".join(unknown_targets))
        for target, digest in hashes.items():
            if not isinstance(digest, str) or _PREFIXED_SHA.fullmatch(digest) is None:
                return _violation("asset_key_target_hash_invalid", field=field, target=target)

    for field in ("adapter_contract_version", "test", "l3_review_strategy"):
        if field in value and not isinstance(value[field], str):
            return _violation("asset_key_not_string", field=field)
    if "safety_degraded" in value and not isinstance(value["safety_degraded"], bool):
        return _violation("asset_safety_degraded_not_bool")
    if "runtime_targets" in value:
        targets = value["runtime_targets"]
        if (not isinstance(targets, list)
                or any(target not in KNOWN_HOSTS for target in targets)):
            return _violation("asset_runtime_targets_invalid")
    if "origin" in value and value["origin"] != "project":
        return _violation("asset_origin_invalid")
    for field in ("risk", "unresolved"):
        if field in value:
            items = value[field]
            if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
                return _violation("asset_key_not_string_array", field=field)
    return None


# --- CORE 렌더 receipt ------------------------------------------------------

# managed framework doc 은 엔진 정본과 설치본이 다른 파일이라, 설치본 해시만으로는 "정본이
# 바뀌었다" 와 "설치본이 손댔다" 를 구분할 수 없다. 그 둘만 semantic_source 쌍을 함께 기록한다.
CORE_RECEIPT_KEYS = {"base_sha256", "sage_version"}
CORE_RECEIPT_OPTIONAL = {"semantic_source", "semantic_source_sha256"}


def core_render_receipt_violation(key, receipt):
    """CORE 렌더 receipt 하나. **이것이 소유권 증거다.**

    uninstall 은 이 receipt 가 있다는 사실만으로 `.claude/agents/<id>.md` 를 지운다. 그 자리는
    사용자도 자기 agent 를 두는 공유 디렉터리라, receipt 가 비었거나 해시가 아니면 우리는
    **무엇을 배치했는지 모르는 상태**다. 모르는 상태에서 지우면 남의 파일을 지운다.
    """
    if not isinstance(receipt, dict):
        return _violation("manifest_core_renders_entry_invalid", field=key)
    present_optional = CORE_RECEIPT_OPTIONAL & set(receipt)
    unknown = sorted(set(receipt) - CORE_RECEIPT_KEYS - CORE_RECEIPT_OPTIONAL)
    if unknown:
        return _violation("manifest_core_render_unknown_fields", field=key,
                          fields=", ".join(unknown))
    if present_optional and present_optional != CORE_RECEIPT_OPTIONAL:
        # 한쪽만 있으면 정본을 지목하지 못하거나 지목만 하고 대조할 값이 없다.
        return _violation("manifest_core_render_semantic_source_incomplete", field=key,
                          missing=", ".join(sorted(CORE_RECEIPT_OPTIONAL - present_optional)))
    base_sha = receipt.get("base_sha256")
    if not isinstance(base_sha, str) or _BARE_SHA.fullmatch(base_sha) is None:
        return _violation("manifest_core_render_base_sha_invalid", field=key)
    if not isinstance(receipt.get("sage_version"), str):
        return _violation("manifest_core_render_sage_version_invalid", field=key)
    if present_optional:
        source_sha = receipt.get("semantic_source_sha256")
        if not isinstance(receipt.get("semantic_source"), str):
            return _violation("manifest_core_render_semantic_source_incomplete", field=key,
                              missing="semantic_source")
        if not isinstance(source_sha, str) or _BARE_SHA.fullmatch(source_sha) is None:
            # `base_sha256` 과 다른 필드다. 같은 code 로 보고하면 사용자는 멀쩡한 값을 고치려
            # 들고, 고쳐도 같은 화면을 다시 받는다.
            return _violation("manifest_core_render_semantic_sha_invalid", field=key)
    return None


def core_skill_receipt_shape(receipt):
    """모양만. host 규칙과 나눠 두는 이유는 소비자가 다르기 때문이다 — `validate`·`doctor` 는
    receipt 를 **읽을 수 있는가**만 묻고, manifest 계약은 거기에 host 규칙까지 요구한다."""
    return (isinstance(receipt, dict)
            and set(receipt) == {"scope", "sage_version"}
            and receipt.get("scope") in ("global", "project-local", "disabled")
            and isinstance(receipt.get("sage_version"), str))


def core_skill_receipt_violation(host, receipt):
    if not core_skill_receipt_shape(receipt):
        return _violation("manifest_core_skill_receipt_invalid", host=host)
    if host == "claude" and receipt["scope"] != "project-local":
        return _violation("manifest_core_skill_receipt_claude_scope")
    return None
