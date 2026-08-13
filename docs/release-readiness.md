# 릴리스 준비 상태

이 문서는 SAGE 를 릴리스할 수 있는 상태인지 **무엇으로 판단하는가**를 적는다. 판단 결과는 여기 적지 않는다 — 결과는 사이클마다 바뀌고, 바뀌는 값을 문서에 박아 두면 문서가 곧 거짓이 된다. 현재 상태는 `python scripts/ci/publish_preflight.py` 가 말한다.

영어 정본은 [release-readiness.en.md](release-readiness.en.md) 다.

## 준비 상태는 두 값뿐이다

| 상태 | 뜻 |
|---|---|
| `NOT READY` | 미해결 P0/P1 이 있거나 증거가 서로 어긋난다 |
| `READY_FOR_USER_RELEASE_DECISION` | 증거가 일치하고 독립 검토가 끝났다. **릴리스 여부는 사용자가 정한다** |

`RELEASED` 는 이 목록에 없다. 도구는 릴리스 가능 여부까지만 말하고, 실제 릴리스는 사람의 결정이다. 검사 도구가 그 경계를 넘으면 승인이라는 절차 자체가 사라진다.

## 무엇이 릴리스를 막는가

`publish_preflight.py` 의 각 검사는 독립이고 전부 실행된다. 첫 실패에서 멈추면 두 번째 문제를 다음 실행에서야 발견하게 되고, 준비가 한 번에 한 개씩만 진행된다.

| 검사 | 막는 이유 |
|---|---|
| `tag-version` | tag 와 `__version__` 이 다르면 사용자가 설치한 것과 tag 가 가리키는 것이 다르다 |
| `version` | `0.0.0` 류 자리표시자로 올리면 되돌릴 수 없다 |
| `catalog` | 한쪽에만 있는 key 는 런타임 fallback 으로 조용히 넘어가고, 사용자가 빈틈을 대신 발견한다 |
| `docs-pair` | 한쪽 언어만 갱신된 채 릴리스되면 두 문서가 갈린다 |
| `inventory` | 인벤토리가 코드와 어긋나면 남은 규모가 사실이 아니고, 릴리스 판단의 근거가 무너진다 |
| `upgrade` | upgrade 계약이 실행망에 없으면 회귀가 아무 때나 들어온다 |
| `mutation` | 저장소가 릴리스 준비 중에 바뀌었다면 승인 없이 version 이 올라간 것이다 |

`publish` 는 되돌릴 수 없다. PyPI 는 같은 버전을 다시 올릴 수 없고, tag 는 남의 clone 으로 이미 퍼진다. 그래서 이 검사는 "빌드가 되는가"가 아니라 **"아티팩트가 주장하는 것과 저장소가 주장하는 것이 같은가"** 를 본다.

## 플랫폼 계약

`scripts/ci/platform_smoke.py` 가 Linux · macOS · Windows 에서 같은 항목을 확인한다.

- 설치
- 한국어·영어 도움말이 서로 다른 화면을 낸다
- local profile 의 언어 설정이 실제로 화면을 바꾼다
- 사이클 문서 언어가 선언되고 Phase 00 에 마커가 기록된다
- `validate` 가 문서화된 exit code 로 판정에 도달한다
- hook 진입점이 보고된다
- `PYTHONIOENCODING=ascii` 에서 `UnicodeEncodeError` 가 나지 않는다

이 스크립트는 **bash 를 쓰지 않는다.** bash 없는 환경에서 도는지가 검사 대상인데 검사 도구가 bash 를 요구하면, 그 환경은 영원히 미검증으로 남는다.

실패한 플랫폼은 skip 이 아니라 실패로 남는다. 조용한 skip 은 통과로 세어져 플랫폼 하나가 미검증인 채 릴리스에 실린다.

## 릴리스 후보를 만드는 방법

version 은 **임시 source copy 에서만** 바꾼다. 저장소 자체를 stamp 하면 승인 없이 version 을 올린 것이고, 되돌리기 전까지 모든 후속 판정이 그 값을 사실로 읽는다.

```bash
# 저장소를 건드리지 않는 후보 빌드
git archive HEAD | (mkdir -p /tmp/sage-candidate && tar -x -C /tmp/sage-candidate)
# /tmp/sage-candidate 안에서만 version 을 바꾸고 빌드한다
```

`publish_preflight.py` 의 `mutation` 검사가 이 규칙을 강제한다.

## downgrade

자동 downgrade 는 없다. `sage upgrade --apply` 가 남긴 backup 으로 복구한다. 보고서는 `.sage/upgrades/<run-id>.json` 에 있고 Git 이 추적하지 않는다.

되돌리는 절차를 도구에 넣지 않은 이유는 upgrade 가 소유하지 않는 파일까지 함께 되돌려야 안전한 경우가 있기 때문이다. 무엇을 되돌릴지는 그 프로젝트의 상태를 아는 사람이 정한다.
