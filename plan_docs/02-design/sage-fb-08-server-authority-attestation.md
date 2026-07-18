# [Design] SAGE-FB-08 서버측 PR-diff 권위 게이트와 attestation

Cycle-Stem: `sage-fb-08-server-authority-attestation`

## 1. Pure Core API

`sage.ci_authority.evaluate(request)`는 filesystem, subprocess, environment를 읽지 않는다.

```text
request = {
  base_profile, head_profile,
  changes: [{path, old_path?, op, base_content, head_content, base_oid, head_oid}],
  phase_docs: {"00": [...], ..., "05": [...]},
  cycle_stem, repository, base_sha, head_sha,
  attestation_token, attestation_key, expected_issuer, now
}
```

결과는 `PASS|BLOCK`, exit code, max risk, base/head risk, deterministic diff digest, reason list, verified claims를
반환한다. local override와 acceptance waiver audit은 request에도 포함하지 않는다.

## 2. Diff and Policy

- CLI adapter가 `git diff --name-status -z -M base head`와 `git show <sha>:<path>`로 full blobs를 읽는다.
- add/modify/delete/rename을 구조화하고 rename은 source와 destination을 모두 classifier input으로 만든다.
- 삭제 파일은 base content를, 추가 파일은 head content를, 수정은 양쪽 content를 검사한다.
- base/head profile을 독립 분류하고 risk rank의 max를 authoritative risk로 사용한다.
- invalid/missing profile은 완화로 간주하지 않고 BLOCK한다.

## 3. Phase Evidence

L3는 head tree에서 exact `Cycle-Stem`으로 Phase 00~05 문서를 각각 하나 선택한다. 누락·중복·declaration drift는
BLOCK하고 Phase 05의 `Final Status: APPROVED`가 정확히 하나여야 한다. PR-local loop audit은 권위 증거가 아니다.

## 4. Attestation

Compact token: `base64url(canonical-json-claims).base64url(HMAC-SHA256)`.

Required claims: version, issuer, repository, base_sha, head_sha, diff_sha256, cycle_stem, risk, reviewer, verdict,
nonce, issued_at, expires_at. Key는 32 bytes 이상이며 TTL은 최대 1시간이다. verify는 constant-time signature 비교,
exact expected claim binding, expiry/clock-skew 검사를 수행한다. Fork secret 부재는 fail-closed다.

## 5. Protected Workflow

설치 template은 `pull_request_target`에서 최소 `contents: read`만 사용한다. base repository와 PR head를 git
objects로 fetch하지만 head의 workflow/script/package를 실행하지 않는다. 보호된 SAGE engine checkout은 40-hex
SHA를 요구한다. 실제 SHA 치환과 branch protection expected-source 설정은 FB-09 실증에서 수행한다.
