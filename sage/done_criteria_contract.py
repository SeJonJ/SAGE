"""엔진측 loader — Done-Criteria 파싱·개정·해시 계약.

정본은 `scripts/sage_harness/hooks/done_criteria_contract.py` 다. 이 파일은 그 모듈의 공개 이름을
그대로 올려, 기존 `from sage.done_criteria_contract import ...` 호출부가 바뀌지 않게 한다.
왜 hook 트리가 정본인지는 `sage/_hook_contract.py` 에 있다.
"""
from sage._hook_contract import reexport as _reexport

_reexport(globals(), "done_criteria_contract")
