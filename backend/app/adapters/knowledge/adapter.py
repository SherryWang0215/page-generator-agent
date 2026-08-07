from __future__ import annotations

import logging
from collections.abc import Sequence

from elasticsearch import Elasticsearch

from ...config import settings

logger = logging.getLogger(__name__)


class KnowledgeChunk(dict):
    """A single knowledge chunk returned from retrieval."""

    @property
    def doc_id(self) -> str:
        return self.get("doc_id", "")

    @property
    def title(self) -> str:
        return self.get("title", "")

    @property
    def content(self) -> str:
        return self.get("content", "")

    @property
    def score(self) -> float:
        return float(self.get("score", 0.0))


class KnowledgeAdapter:
    """Retrieve knowledge chunks from Elasticsearch using hybrid search.

    Combines dense vector similarity (cosine) with BM25 full-text matching
    via a weighted score merge: final = 0.7 * vector_score + 0.3 * bm25_score.
    """

    VECTOR_WEIGHT = 0.7
    BM25_WEIGHT = 0.3

    def __init__(self, es_client: Elasticsearch | None = None) -> None:
        self._es = es_client
        self._enabled = settings.rag_enabled

    @property
    def enabled(self) -> bool:
        return self._enabled and self._es is not None

    def _get_es(self) -> Elasticsearch:
        if self._es is None:
            self._es = Elasticsearch(hosts=[settings.es_host])
            try:
                self._es.info()
            except Exception as exc:
                raise ConnectionError(
                    f"unable to connect to Elasticsearch at {settings.es_host}: {exc}"
                ) from exc
        return self._es

    def query_rag(self, question: str, top_k: int | None = None) -> list[KnowledgeChunk]:
        """Return top-k knowledge chunks relevant to the question.

        Returns an empty list when ES is unavailable (graceful degradation).
        """
        if not self.enabled:
            logger.info("RAG is disabled, skipping knowledge retrieval")
            return []

        k = top_k or settings.rag_top_k

        try:
            es = self._get_es()
            embedding = _encode_query(question)

            knn_results = self._knn_search(es, embedding, k * 2)
            bm25_results = self._bm25_search(es, question, k * 2)

            merged = self._merge_results(knn_results, bm25_results, k)
            logger.info(
                "RAG hybrid search completed | question_len=%d | candidates=%d | returned=%d",
                len(question),
                len(knn_results) + len(bm25_results),
                len(merged),
            )
            return merged
        except Exception as exc:
            logger.warning("RAG retrieval failed, returning empty results | reason=%s", exc)
            return []

    def _knn_search(self, es: Elasticsearch, embedding: list[float], k: int) -> list[dict]:
        try:
            response = es.search(
                index=settings.es_index_name,
                body={
                    "knn": {
                        "field": "embedding",
                        "query_vector": embedding,
                        "k": k,
                        "num_candidates": k * 2,
                    },
                    "_source": ["doc_id", "title", "content", "chunk_index"],
                },
            )
            return [
                {**hit["_source"], "score": float(hit["_score"])}
                for hit in response.get("hits", {}).get("hits", [])
            ]
        except Exception:
            logger.exception("ES KNN search failed")
            return []

    def _bm25_search(self, es: Elasticsearch, question: str, k: int) -> list[dict]:
        try:
            response = es.search(
                index=settings.es_index_name,
                body={
                    "query": {
                        "match": {
                            "content": {
                                "query": question,
                                "operator": "or",
                            }
                        }
                    },
                    "size": k,
                    "_source": ["doc_id", "title", "content", "chunk_index"],
                },
            )
            return [
                {**hit["_source"], "score": float(hit["_score"])}
                for hit in response.get("hits", {}).get("hits", [])
            ]
        except Exception:
            logger.exception("ES BM25 search failed")
            return []

    def _merge_results(
        self,
        knn_results: list[dict],
        bm25_results: list[dict],
        top_k: int,
    ) -> list[KnowledgeChunk]:
        knn_max = max((r["score"] for r in knn_results), default=1.0)
        bm25_max = max((r["score"] for r in bm25_results), default=1.0)

        scored: dict[str, float] = {}
        docs: dict[str, dict] = {}

        for r in knn_results:
            key = f"{r.get('doc_id')}#{r.get('chunk_index')}"
            norm_score = r["score"] / knn_max if knn_max > 0 else 0.0
            scored[key] = self.VECTOR_WEIGHT * norm_score
            docs[key] = r

        for r in bm25_results:
            key = f"{r.get('doc_id')}#{r.get('chunk_index')}"
            norm_score = r["score"] / bm25_max if bm25_max > 0 else 0.0
            scored[key] = scored.get(key, 0.0) + self.BM25_WEIGHT * norm_score
            if key not in docs:
                docs[key] = r

        ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)[:top_k]
        return [
            KnowledgeChunk(
                {
                    "doc_id": docs[key].get("doc_id", ""),
                    "title": docs[key].get("title", ""),
                    "content": docs[key].get("content", ""),
                    "score": round(score, 4),
                }
            )
            for key, score in ranked
        ]


def _encode_query(text: str) -> list[float]:
    from ...services.embedding_client import encode

    return encode([text], text_type="query")[0]
