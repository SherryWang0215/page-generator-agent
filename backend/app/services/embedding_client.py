from __future__ import annotations

import logging
from typing import Literal

import httpx

from ..config import settings

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when embedding generation fails."""


def encode(texts: list[str], text_type: Literal["document", "query"] = "document") -> list[list[float]]:
    """Encode texts using DashScope text-embedding-v3 API.

    Args:
        texts: List of texts to encode (max 16 per batch for document, 8 for query).
        text_type: "document" for indexing, "query" for retrieval.

    Returns:
        List of embedding vectors.
    """
    if not settings.dashscope_api_key:
        raise EmbeddingError("DASHSCOPE_API_KEY is not configured")

    max_batch = 10
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), max_batch):
        batch = texts[i : i + max_batch]
        all_embeddings.extend(_encode_batch(batch, text_type))

    return all_embeddings


def _encode_batch(texts: list[str], text_type: str) -> list[list[float]]:
    payload = {
        "model": settings.embedding_model_name,
        "input": {"texts": texts},
        "parameters": {"text_type": text_type},
    }
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            logger.info(
                "DashScope embedding request | model=%s | count=%d | text_type=%s | first_text_len=%d",
                settings.embedding_model_name,
                len(texts),
                text_type,
                len(texts[0]) if texts else 0,
            )
            response = client.post(
                "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        body = exc.response.text if hasattr(exc, "response") else "N/A"
        logger.error(
            "DashScope embedding request failed | status=%s | body=%s",
            exc.response.status_code if hasattr(exc, "response") else "?",
            body,
        )
        raise EmbeddingError(f"dashscope embedding request failed: {body}") from exc

    try:
        body = response.json()
        items = sorted(body["output"]["embeddings"], key=lambda item: item["text_index"])
        embeddings = [item["embedding"] for item in items]
        logger.info(
            "DashScope embedding batch done | model=%s | count=%d | tokens=%d",
            settings.embedding_model_name,
            len(embeddings),
            body.get("usage", {}).get("total_tokens", 0),
        )
        return embeddings
    except (KeyError, IndexError, TypeError) as exc:
        logger.exception("DashScope embedding response invalid | raw=%s", response.text)
        raise EmbeddingError("dashscope embedding response invalid") from exc
