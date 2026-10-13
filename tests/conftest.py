"""모든 테스트는 가짜 LLM으로만 돈다.

개발 PC의 config/models.local.yaml(실제 모델 연결)이나 OPENROUTER_API_KEY가 있어도 테스트가 진짜 모델을 부르면
느려지고 사용량·비용이 든다. 그래서 테스트 프로세스에서는 둘 다 끈다.
"""

import os

os.environ.pop("OPENROUTER_API_KEY", None)
os.environ["THE_SUSPECTS_NO_LOCAL_MODELS"] = "1"
