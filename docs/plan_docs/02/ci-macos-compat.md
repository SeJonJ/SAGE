# CI 구성 설계

Cycle-Stem: ci-macos-compat
Document-Language: ko
Done-Criteria-Revision: 1

일반 ci.yml의 uninstall_matrix에서 macOS3.10/3.11만 matrix.exclude로 제외한다. 기존 smoke/race/core steps는 유지한다. 새로운 macos-compat.yml은 workflow_dispatch로 candidate_sha를 받아 형식을 검사한 뒤 해당 SHA를 checkout하고 HEAD를 다시 대조한다. macos-latest에서 Python3.10/3.11을 순차 실행(max-parallel1)한다. 읽기 권한만 부여하고 기존 세 제거 검사와 같은 명령/엄격 설정을 사용한다.

기존 publish.yml은 그대로 둔다. 이 수동 검사는 배포 전 운영 단계이며 자동 publish gate를 새로 만들지 않는다. default branch에 workflow가 있어야 실행 버튼을 사용할 수 있다. 지원 환경 검증을 폐지하거나 runner 미배정을 성공으로 바꾸지 않는다.
