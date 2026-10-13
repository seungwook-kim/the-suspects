"""모든 테스트는 가짜 LLM과 가짜 그림으로만 돈다.

개발 PC의 config/models.local.yaml(실제 모델 연결)이나 API 키가 있어도 테스트가 진짜 모델을 부르면
느려지고 사용량·비용이 든다. 그래서 테스트 프로세스에서는 모두 끈다.
키는 지우지 않고 빈 값으로 둔다: 서버 모듈이 .env를 읽을 때(load_dotenv) 이미 있는 값은 덮어쓰지 않기 때문.
"""

import os

for _key in ("OPENROUTER_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
    os.environ[_key] = ""
os.environ["THE_SUSPECTS_NO_LOCAL_MODELS"] = "1"
