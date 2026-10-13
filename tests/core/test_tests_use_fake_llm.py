"""안전장치: 테스트에서 만든 기본 LLM·그림 클라이언트는 항상 꺼진(가짜) 상태다 (로컬 모델 연결·API 키 무시)."""

import server.api.app  # noqa: F401  (.env를 읽는 모듈을 먼저 불러도 키가 살아나지 않아야 한다)
from server.llm.client import LLMClient
from server.llm.images import ImageClient


def test_default_client_is_fake_in_tests():
    client = LLMClient()
    assert client.fake_mode is True
    assert client.provider != "cli"


def test_default_image_client_is_off_in_tests():
    assert ImageClient().enabled is False
