# 릴리스 준비 상태

이 문서는 SAGE 를 릴리스할 수 있는 상태인지 **무엇으로 판단하는가**를 적는다. 판단 결과는 여기 적지
않는다 — 결과는 사이클마다 바뀌고, 바뀌는 값을 문서에 박아 두면 문서가 곧 거짓이 된다. 현재 상태는
POSIX에서는 `python3 scripts/ci/publish_preflight.py`, Windows에서는
`py -3 scripts/ci/publish_preflight.py`로 현재 상태를 확인한다.

이 문서가 한국어 authoring source 이고, [release-readiness.en.md](release-readiness.en.md) 는 그것을
옮긴 영어 mirror 다. 먼저 이 문서를 고치고 mirror 를 맞춘다 — mirror 첫 줄의 `sage-doc-source` hash
가 그 방향을 강제한다.

## 준비 상태는 두 값뿐이다

| 상태 | 뜻 |
|---|---|
| `NOT READY` | 미해결 P0/P1 이 있거나 증거가 서로 어긋난다 |
| `READY_FOR_USER_RELEASE_DECISION` | 증거가 일치하고 독립 검토가 끝났다. **릴리스 여부는 사용자가 정한다** |

`RELEASED`는 이 목록에 없다. 도구는 릴리스 가능 여부까지만 말하고, 실제 릴리스는 사람의 결정이다.
검사 도구가 그 경계를 넘으면 승인이라는 절차 자체가 사라진다.

## 무엇이 릴리스를 막는가

`publish_preflight.py`의 각 검사는 독립이고 전부 실행된다. 첫 실패에서 멈추면 두 번째 문제를 다음
실행에서야 발견하게 되고, 준비가 한 번에 한 개씩만 진행된다.

| 검사 | 막는 이유 |
|---|---|
| `tag-version` | tag 와 `__version__`이 다르면 사용자가 설치한 것과 tag 가 가리키는 것이 다르다 |
| `version` | `0.0.0` 류 자리표시자로 올리면 되돌릴 수 없다 |
| `catalog` | 한쪽에만 있는 key 는 런타임 fallback 으로 조용히 넘어가고, 사용자가 빈틈을 대신 발견한다 |
| `localization-debt` | 인벤토리가 0 이어도 남은 누출은 따로 센다. 부채를 목록에 적어 뒀다는 사실은 출하 근거가 아니다 |
| `docs-pair` | 한쪽 언어만 갱신된 채 릴리스되면 두 문서가 갈린다 |
| `inventory` | 인벤토리가 코드와 일치하고 catalog 미이관 사용자 표시 literal이 0건이어야 한다. 최신 목록은 완료를 뜻하지 않는다 |
| `upgrade` | 실제 v0.9.84 소비자에 신규 managed CORE 파일과 receipt를 함께 배포해야 한다. 명령·테스트 등록만으로는 충분하지 않다 |
| `mutation` | 저장소가 릴리스 준비 중에 바뀌었다면 승인 없이 version 이 올라간 것이다 |
| Windows 데스크톱 증거 | `publish_preflight`가 대신 세지 않는다. 그 SKU 에서 실제로 돈 기록이 없으면 자동 제거는 미검증이고, 문서가 말하는 지원 범위와 검증한 범위가 갈린다 |

`publish`는 되돌릴 수 없다. PyPI 는 같은 버전을 다시 올릴 수 없고, tag 는 남의 clone 으로 이미
퍼진다. 그래서 이 검사는 "빌드가 되는가"가 아니라 **"아티팩트가 주장하는 것과 저장소가 주장하는 것이
같은가"** 를 본다.

## 플랫폼 계약

`scripts/ci/platform_smoke.py`가 Linux·macOS·Windows 11 데스크톱에서 같은 항목을 확인한다. POSIX
둘은 매 PR 의 hosted matrix 에서 돌고, Windows 는 아래 **self-hosted 전용 job** 에서 돈다.

- 설치
- 한국어·영어 도움말이 서로 다른 화면을 낸다
- local profile 의 언어 설정이 실제로 화면을 바꾼다
- 사이클 문서 언어가 선언되고 Phase 00 에 마커가 기록된다
- `validate`가 문서화된 exit code 로 판정에 도달한다
- hook 진입점이 보고된다
- `PYTHONIOENCODING=ascii`에서 `UnicodeEncodeError`가 나지 않는다

이 스크립트는 **bash 를 쓰지 않는다.** bash 없는 환경에서 도는지가 검사 대상인데 검사 도구가 bash 를
요구하면, 그 환경은 영원히 미검증으로 남는다.

실패한 플랫폼은 skip 이 아니라 실패로 남는다. 조용한 skip 은 통과로 세어져 플랫폼 하나가 미검증인 채
릴리스에 실린다.

## Windows 증거는 hosted 러너가 만들 수 없다

GitHub-hosted `windows-latest`의 실체는 **Windows Server 2025** 다. 그 러너의 초록은 backend 회귀
증거로 유효하지만 **데스크톱 SKU 증거가 아니다.**

**로그는 이제 둘을 구별한다.** capability 진단·smoke·race smoke·core checks 네 로그가
edition·build·product type·filesystem·process bitness 를 각각 낸다. 그래도 hosted matrix 에서
Windows 를 뺀 이유는 따로다 — 그 값을 읽는 일이 **사람의 단계**로 남기 때문이다. 초록 자체는 두 SKU
에서 똑같이 생겼고, 요약 줄을 되짚지 않으면 구별이 서지 않는다. 실제로 이 사이클에서 Server 러너의
초록을 데스크톱 증거로 읽을 뻔했고, 그때 막은 것은 주석이었다.

그래서 사람이 매번 옳게 읽기를 요구하는 대신, **범위 밖 러너가 데스크톱 증거로 읽힐 자리 자체를
없앴다.** CI 안에서 이 증거를 만드는 자리는 `windows11_uninstall` self-hosted 전용 job 하나다.

| 항목 | 값 |
|---|---|
| 러너 | `[self-hosted, windows, x64, win11, sage-uninstall]` |
| 실행 조건 | 같은 저장소 PR 에 `run-win11-uninstall` 라벨을 **붙이는 사건** (`labeled`) |
| 실행하지 않는 경우 | fork PR·`synchronize`·`opened`·`reopened`·push |
| 실행 전 관문 | `windows_capability_report.py --require-product-support` (모든 native 실행보다 먼저) |
| 실행 항목 | rename probe·capability report·platform smoke(3.12)·uninstall smoke·race smoke·core checks (py 3.10·3.11·3.12) |

라벨은 **상태가 아니라 승인 사건**이다. 라벨이 붙어 있다는 이유로 새 커밋이 자동 실행되지 않으므로,
다음 커밋을 검증하려면 라벨을 떼었다 다시 붙인다. checkout 은 `head.sha`로 고정되고 증거 단계가 실제
트리와 그 값을 대조하므로, **증거와 커밋이 1:1 로 묶인다.**

제거 검사는 `SAGE_UNINSTALL_REQUIRE_PRODUCT_SUPPORT=1` 엄격 모드로 돈다. 정책 거부 1건, 실제 제거
0건, 세 scope 중 하나라도 미실행이면 non-zero 다 — 거부 계약 단언으로 **갈음하는 것 자체가 실패**다.
그 갈음이 열리면 이 job 은 실제 제거를 한 번도 하지 않은 채 증거를 만들었다고 말한다.

**증거는 그 SKU 에서 실제로 돈 기록이다.** 요구 항목은 edition·build·product type·filesystem·process
bitness·실제 removal 수·policy refusal 수·검증 대상 커밋이고, 이 job 은 그 기록을 **반복 가능하게**
만드는 자리다. 같은 항목과 같은 커밋을 남긴 Windows 11 데스크톱 직접 실행 기록도 같은 증거로 센다 —
대체할 수 없는 것은 SKU 이지 실행 방식이 아니다. 어느 쪽 기록도 없으면 그 플랫폼의 자동 제거는
미검증이다.

## 릴리스 후보를 만드는 방법

version 은 **임시 source copy 에서만** 바꾼다. 저장소 자체를 stamp 하면 승인 없이 version 을 올린
것이고, 되돌리기 전까지 모든 후속 판정이 그 값을 사실로 읽는다.

```bash
# 저장소를 건드리지 않는 후보 빌드
git archive HEAD | (mkdir -p /tmp/sage-candidate && tar -x -C /tmp/sage-candidate)
# /tmp/sage-candidate 안에서만 version 을 바꾸고 빌드한다
```

`publish_preflight.py`의 `mutation` 검사가 이 규칙을 강제한다.

## downgrade

자동 downgrade 는 없다. `sage upgrade --apply`가 남긴 backup 으로 복구한다. 보고서는
`.sage/upgrades/<run-id>.json`에 있고 Git 이 추적하지 않는다.

되돌리는 절차를 도구에 넣지 않은 이유는 upgrade 가 소유하지 않는 파일까지 함께 되돌려야 안전한
경우가 있기 때문이다. 무엇을 되돌릴지는 그 프로젝트의 상태를 아는 사람이 정한다.
