"""Text embeddings for dedup and "similar parts" (384-d everywhere, spec v1.1 §0 row 1).

Two interchangeable backends:
  * SentenceTransformerEmbedder — all-MiniLM-L6-v2 (384-d). Production default when the
    `ml` extra is installed (EMBEDDING_BACKEND=sentence-transformers).
  * HashingEmbedder — signed feature hashing of word and character-trigram features into
    384 dims. Deterministic, dependency-free, CPU-cheap; used in CI and offline dev.
Both return L2-normalised vectors, so cosine similarity == dot product.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache
from typing import Any, Protocol

from common.settings import get_settings

DIM = 384
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*")


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class HashingEmbedder:
    dim = DIM

    def _features(self, text: str) -> list[tuple[str, float]]:
        t = text.lower()
        feats: list[tuple[str, float]] = []
        for tok in _TOKEN.findall(t):
            feats.append(("w:" + tok, 2.0))
            compact = re.sub(r"[^a-z0-9]", "", tok)
            padded = f"^{compact}$"
            for i in range(len(padded) - 2):
                feats.append(("c:" + padded[i : i + 3], 1.0))
        return feats

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for feat, weight in self._features(text):
            h = hashlib.blake2b(feat.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[idx] += sign * weight
        return _normalize(vec)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


class SentenceTransformerEmbedder:
    dim = DIM

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model: Any = SentenceTransformer(model_name, device="cpu")
        actual = int(self._model.get_sentence_embedding_dimension())
        if actual != DIM:
            raise ValueError(f"{model_name} produces {actual}-d vectors; schema expects {DIM}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return [list(map(float, row)) for row in out]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_backend == "sentence-transformers":
        return SentenceTransformerEmbedder(s.embedding_model)
    return HashingEmbedder()


def embedding_text(
    manufacturer: str | None, mpn: str | None, title: str | None, specs: dict[str, str] | None
) -> str:
    """§6.2: manufacturer + mpn + title + top-5 specs."""
    top_specs = list((specs or {}).items())[:5]
    parts = [manufacturer or "", mpn or "", title or ""] + [f"{k} {v}" for k, v in top_specs]
    return " | ".join(p for p in parts if p)


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
