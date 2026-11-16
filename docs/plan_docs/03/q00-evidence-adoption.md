Cycle-Stem: q00-evidence-adoption
Document-Language: ko
Issue: https://github.com/SeJonJ/SAGE/issues/40

# 구현

runner, 인터뷰/PDCA template, QA 원문·중립 spec, verification/review protocol, Standard/Fast/review bootstrap 지침을 보완했다. 설치된 양 host QA는 공유 framework 소스를 사용한다.

Windows 추가 검증에서 공개1.3.6과 후보 모두 `/` 선언의 사용자 runner를 force 설치가 덮어쓰는 기존 결함을 재현했다. `install.py`에서 지원하는 두 경로의 정확한 portable 표기도 보존하도록 수정하고 기존 force 회귀를 양 host·양경로·양표기로 확대했다.

새 runner 테스트는 실제 실행 흔적과 exit를 함께 검사한다. 기존 역사적 layout 회귀는 최신 파일의 경로만 바꿔 구판을 합성하던 대신 실제 v1.0.0 fixture와 SHA를 사용한다. 사용자 수정본 보존도 확인했다.

추가 문서 감사에서 완료 기준·output contract·중립 skill spec의 같은 의미를 정렬했다. 이는 새 gate나 상태를 만들지 않는다.
