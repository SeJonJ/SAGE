# [Base Plan] SAGE-FB-08 서버측 PR-diff 권위 게이트와 attestation

Cycle-Stem: `sage-fb-08-server-authority-attestation`
Risk Level: L3

## 1. Problem

로컬 hook, profile, workflow, audit은 PR 작성자가 바꿀 수 있으므로 branch protection의 권위가 될 수 없다.
서버 검증기는 보호된 revision의 SAGE 코드를 실행하고 PR head를 실행 코드가 아닌 git object data로만 읽어야 한다.

## 2. Trust Boundary

- verifier code/workflow: default branch 또는 외부 SAGE commit SHA에 고정된 보호 자산
- untrusted input: PR base/head tree, head profile, phase 문서, 제출된 attestation
- protected secret: 최소 32-byte HMAC key; fork PR에는 전달되지 않으므로 attestation-required gate는 BLOCK
- local override/waiver/audit: 서버 권위 입력으로 사용하지 않음
- actual ChatForYou ref publish, required check, branch protection wiring: SAGE-FB-09

## 3. Non-goals

- PR head의 스크립트/테스트 실행
- 자동 host 전환 또는 cross-model reviewer 실행
- GitHub App/Sigstore 운영 인프라 구축
- branch protection API 변경
