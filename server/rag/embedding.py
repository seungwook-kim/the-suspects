"""임베딩 제공자 인터페이스와 테스트용 결정적 가짜 임베딩."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

import numpy as np

from server.rag.tokenize import tokenize


class EmbeddingProvider(ABC):
    """모든 임베딩 제공자가 따르는 인터페이스. 같은 텍스트는 항상 같은 벡터여야 한다."""

    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        """(len(texts), dim) float32, 행마다 L2 정규화."""

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]


class HashEmbedding(EmbeddingProvider):
    """해시 기반 고정 차원 벡터 (feature hashing). 네트워크 없이 결정적으로 동작한다.

    의미 임베딩이 아니라 토큰 겹침을 반영하는 벡터라서 테스트·개발용이다.
    파이썬 내장 hash()는 실행마다 달라지므로 md5를 쓴다.
    """

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self._dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for tok in tokenize(text):
                digest = hashlib.md5(tok.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:4], "little") % self._dim
                sign = 1.0 if digest[4] & 1 else -1.0
                out[i, idx] += sign
            norm = float(np.linalg.norm(out[i]))
            if norm > 0:
                out[i] /= norm
        return out


class CachedEmbedding(EmbeddingProvider):
    """같은 텍스트를 다시 임베딩하지 않는 캐시 래퍼 (PRD §11.4.6)."""

    def __init__(self, inner: EmbeddingProvider) -> None:
        self._inner = inner
        self._cache: dict[str, np.ndarray] = {}
        self.calls = 0  # 내부 제공자에 실제로 보낸 텍스트 수

    @property
    def dim(self) -> int:
        return self._inner.dim

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        keys = [hashlib.sha1(t.encode("utf-8")).hexdigest() for t in texts]
        missing = list(dict((k, t) for k, t in zip(keys, texts) if k not in self._cache).items())
        if missing:
            vecs = self._inner.embed([t for _, t in missing])
            self.calls += len(missing)
            for (k, _), v in zip(missing, vecs):
                self._cache[k] = v
        return np.stack([self._cache[k] for k in keys])


class RemoteEmbedding(EmbeddingProvider):
    """실제 API 임베딩 자리표시. 구현은 메인 담당이 나중에 채운다(OpenRouter 등)."""

    def __init__(self, model: str, dim: int) -> None:
        self.model = model
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError("실제 임베딩 API 호출은 아직 구현되지 않았다. HashEmbedding을 쓰거나 이 클래스를 구현하라.")
