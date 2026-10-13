"""안전장치: 테스트에서 만든 기본 LLM 클라이언트는 항상 가짜 모드다 (로컬 모델 연결·API 키 무시)."""

from server.llm.client import LLMClient


def test_default_client_is_fake_in_tests():
    client = LLMClient()
    assert client.fake_mode is True
    assert client.provider != "cli"
