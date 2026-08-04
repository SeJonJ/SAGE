# [Base Plan] SAGE 거버넌스 자산의 content 자기 위험도 상승 완화

Cycle-Stem: `sage-governance-asset-self-risk`
Risk Level: L3
Status: **HELD (2026-08-04)** — 매칭 규칙 교정으로는 풀 수 없음이 두 라운드로 확인됨. 코드 미반영.

## 1. Context

ChatForYou 실측(`0.9.77`): project hook core 에 rollout legacy 사이클 stem 26건을 상수로 넣었더니
`bug_136_recording_partial_cleanup` 이 recording 도메인(`risk_level: L3`)의 content keyword
`RECORDING_PARTIAL` 과 매칭돼 **core 소스 파일 자신이 L3 로 분류**됐다. 그 사이클 00 은 L2 라 상향
차단에 걸려 파일을 쓸 수 없었고, ChatForYou 는 정책 데이터를 `.txt` 로 분리해 우회했다.

메커니즘:

- `profile_compile.py` 가 `domains[].content_keywords` 를 레벨별 `l{2,3}_content_keywords` 로
  병합하고, 게이트의 `_has_kw`(`pre_implementation_gate_core.py`)가 **대소문자 무시 부분
  문자열**로 매칭한다: `kw.lower() in content.lower()`.
- `hook_runtime._matched_domains` 도 도메인 리뷰 매칭에 같은 부분 문자열을 쓴다.

## 2. 결론 — 보류

**부분 문자열 매칭을 어떤 방식으로 좁혀도, 실측 오탐을 닫는 규칙은 실제 위험 코드도 같이 닫는다.**
두 번의 구현·독립 리뷰로 확인했고, 두 번 다 미탐 폭을 과소 서술한 채 통과할 뻔했다. 매칭 규칙은
그대로 두고 사이클을 보류한다.

### 시도 1 — 완전 토큰 매칭 (양끝 경계를 각각 요구)

`(?<![A-Za-z0-9_])kw(?![A-Za-z0-9_])`. 비용을 "파생어 하나(`encrypt`→`encryption`)"로 적었으나
실측 폭은 훨씬 넓었다:

| 키워드 | content | 판정 |
| --- | --- | --- |
| `PrivateKey` | `getPrivateKey()`, `privateKeyBytes` | 미매칭 |
| `auth` | `authenticate(` | 미매칭 |
| `transaction` | `transactions`, `beginTransaction()` | 미매칭 |
| `password` | `db_password`, `passwordHash` | 미매칭 |

실코드에서 도메인 어휘가 등장하는 지배적 형태가 통째로 빠진다. 게다가 `cycle_domain_review` 에서
**새 hard BLOCK** 까지 만들었다(파일명으로 L3 가 된 `AuthController.java` 가 등록 도메인 미매칭).

### 시도 2 — 파묻힌 조각만 배제 (양쪽이 동시에 이어붙었을 때만)

`(?:(?<![A-Za-z0-9_])kw|kw(?![A-Za-z0-9_]))`. 시도 1 의 표는 전부 복구되고 `cycle_domain_review`
과차단도 해소됐다. 그러나 미매칭 조건이 실질적으로 **"키워드가 더 긴 식별자의 중간에 있음"** 이고,
그 부류가 여전히 넓다(실측):

| 키워드 | content | 판정 |
| --- | --- | --- |
| `Repository` | `UserRepositoryImpl`, `OrderRepositoryTest` | 미매칭 |
| `encrypt` | `_encrypt_data`, `doEncryptNow()` | 미매칭 |
| `SECRET` | `AWS_SECRET_ACCESS_KEY` | 미매칭 |
| `PrivateKey` | `getPrivateKeyBytes()`, `mPrivateKeyRef` | 미매칭 |
| `KeyStore` | `loadKeyStoreFile()` | 미매칭 |

`UserRepositoryImpl`(Spring 정본 명명), `_encrypt_data`(Python), `AWS_SECRET_ACCESS_KEY`(env 상수)는
드문 형태가 아니다.

### 왜 더 좁혀도 안 되는가

실측 오탐 `bug_136_recording_partial_cleanup` 과 진짜 위험 `AWS_SECRET_ACCESS_KEY` 는 **구문상
같은 형태**다 — 구분자 사이에 낀 어휘. 전자를 닫는 규칙은 후자도 닫는다. camel hump 를 경계로
인정하면 `UserRepositoryImpl` 류는 복구되지만 snake 중간형(`AWS_SECRET_ACCESS_KEY`)은 여전히
못 살린다. 어휘 매칭은 "그 도메인을 **언급**한 코드"와 "**구현**한 코드"를 구별할 수 없고,
그 구별이 J-7 의 본질이다.

### 놓쳤을 때 바닥이 없다 (두 번 틀린 가정)

초안이 이 트레이드를 수용한 근거는 "content 는 경로 분류 위의 보조 신호라 미매칭이어도 경로 기반
바닥이 남는다 — fail-open 이 아니다" 였다. **거짓이다**(실측):

- `l1_path_globs` 로 L1 인 파일은 content 로만 L3 에 닿는다. 미매칭이면
  `{"status": "ok", "exit_code": 0, "message_key": None}` — **경고 없는 통과**.
- `l0_pass_globs` 파일은 content escalation 경로를 아예 안 탄다. 유일한 신호인 `l0_l3_file`
  비차단 WARN 도 같은 매칭을 쓰므로 함께 좁아진다.

J-11 기각 논거에서 틀린 것과 **같은 자리**다. 이 코드베이스에서 "부재·미매칭은 안전 방향"은
성립하지 않는다 — 이후 판단에서 이 가정을 쓰지 않는다.

과분류는 눈에 보이고 우회 가능하지만(ChatForYou 는 실제로 우회했다), 과소분류는 보이지 않는다.
fail-closed 프레임워크에서 이 교환은 순손실이다.

## 3. 검토하고 기각한 대안

- **거버넌스 자산 경로에 대한 content 분류 면제**: "위험 코드를 거버넌스 경로에 두면 escalation 을
  피한다"는 우회를 만든다.
- **profile 플래그 opt-in**: 기본값이 어느 쪽이든 한쪽은 침묵 속에 남는다. 설정 분기만 늘린다.
- **camel hump 경계 인정**: 위 사유로 부분해에 그친다. `re.IGNORECASE` 하에서 대소문자 단언이
  무력화돼 구현도 까다롭다.

## 4. 다음에 다룬다면

매칭이 아니라 **판정 경로**에서 풀어야 한다. 검토할 방향:

- content 단독 trigger(경로 바닥보다 높은 escalation)를 차단이 아니라 선언 요구로 돌리는 안 —
  `content_l3_enforce` 가 이미 warn/block 축을 갖고 있다.
- 저작자가 "이 내용은 데이터이지 구현이 아니다"를 사이클 단위로 선언하고 감사에 남기는 안.

어느 쪽이든 **경로 분류 바닥이 없다는 사실**(§2)을 전제로 설계해야 한다.

## 5. Tracking

- 정본: 위키 `SAGE - 장수 브랜치 다중 사이클 결속·선언 risk 설계` J-7
- 독립 리뷰 2라운드 결과가 이 판단의 근거다. 두 라운드 모두 리뷰어 세션에서 `python3` 실행이
  거부돼 소스 정독으로 지적했고, 작성자가 실측으로 재확인했다.
- 리뷰가 제기했으나 이번에 다루지 않은 것: `_matched_domains` 가 좁아지면 도메인이 1개 이상 남는
  경우 사라진 도메인의 리뷰 요구가 조용히 줄어든다. 매칭을 바꾸는 어떤 안이든 이 축을 함께 봐야 한다.
