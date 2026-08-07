from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from elasticsearch import Elasticsearch

from ..config import settings

logger = logging.getLogger(__name__)


class ConversationStoreError(RuntimeError):
    """Raised when conversation store operations fail."""


class ConversationStore:
    """CRUD operations for conversations and messages in Elasticsearch."""

    def __init__(self, es_client: Elasticsearch | None = None) -> None:
        self._es = es_client
        self._indices_ensured = False

    def _get_es(self) -> Elasticsearch:
        if self._es is None:
            self._es = Elasticsearch(hosts=[settings.es_host])
        return self._es

    def ensure_indices(self) -> None:
        """Create conversation, message, and profile indices if they don't exist."""
        if self._indices_ensured:
            return
        es = self._get_es()
        try:
            self._create_conversation_index(es)
            self._create_message_index(es)
            self._create_profile_index(es)
            self._indices_ensured = True
        except Exception as exc:
            logger.warning("Failed to ensure conversation indices | reason=%s", exc)

    def _create_conversation_index(self, es: Elasticsearch) -> None:
        if es.indices.exists(index=settings.es_conversation_index):
            return
        mapping = {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "properties": {
                    "conversation_id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "page_id": {"type": "keyword"},
                    "title": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "status": {"type": "keyword"},
                    "summary": {"type": "text"},
                    "summary_updated_at": {"type": "date"},
                    "compressed_round_count": {"type": "integer"},
                }
            },
        }
        es.indices.create(index=settings.es_conversation_index, body=mapping)
        logger.info("Created ES index | index=%s", settings.es_conversation_index)

    def _create_message_index(self, es: Elasticsearch) -> None:
        if es.indices.exists(index=settings.es_message_index):
            return
        mapping = {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "properties": {
                    "message_id": {"type": "keyword"},
                    "conversation_id": {"type": "keyword"},
                    "role": {"type": "keyword"},
                    "content": {"type": "text"},
                    "metadata": {"type": "object", "enabled": True},
                    "created_at": {"type": "date"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": settings.embedding_dim,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "embedding_status": {"type": "keyword"},
                }
            },
        }
        es.indices.create(index=settings.es_message_index, body=mapping)
        logger.info("Created ES index | index=%s", settings.es_message_index)

    def create_conversation(
        self, user_id: str, page_id: str | None = None
    ) -> dict:
        """Create a new conversation and return its document."""
        now = datetime.now(timezone.utc)
        doc = {
            "conversation_id": uuid4().hex,
            "user_id": user_id,
            "page_id": page_id,
            "title": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "status": "active",
        }
        es = self._get_es()
        es.index(
            index=settings.es_conversation_index,
            id=doc["conversation_id"],
            body=doc,
            refresh=True,
        )
        return doc

    def get_conversation(self, conversation_id: str) -> dict | None:
        """Get a conversation by ID. Returns None if not found."""
        try:
            es = self._get_es()
            result = es.get(
                index=settings.es_conversation_index, id=conversation_id
            )
            return result["_source"]
        except Exception:
            return None

    def list_conversations(
        self, user_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict], int]:
        """List conversations for a user. Returns (conversations, total)."""
        es = self._get_es()
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {"term": {"status": "active"}},
                    ]
                }
            },
            "sort": [{"updated_at": {"order": "desc"}}],
            "from": offset,
            "size": limit,
        }
        result = es.search(index=settings.es_conversation_index, body=body)
        hits = result.get("hits", {}).get("hits", [])
        total = result.get("hits", {}).get("total", {}).get("value", 0)
        return [hit["_source"] for hit in hits], total

    def archive_conversation(self, conversation_id: str) -> bool:
        """Archive a conversation. Returns True if successful."""
        try:
            es = self._get_es()
            es.update(
                index=settings.es_conversation_index,
                id=conversation_id,
                body={
                    "doc": {
                        "status": "archived",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                refresh=True,
            )
            return True
        except Exception:
            return False

    def update_conversation(self, conversation_id: str, **fields) -> None:
        """Update conversation fields."""
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        es = self._get_es()
        es.update(
            index=settings.es_conversation_index,
            id=conversation_id,
            body={"doc": fields},
            refresh=True,
        )

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
        embedding: list[float] | None = None,
    ) -> dict:
        """Add a message to a conversation. Returns the message document."""
        now = datetime.now(timezone.utc)
        doc = {
            "message_id": uuid4().hex,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "created_at": now.isoformat(),
            "embedding_status": "ready" if embedding else "pending",
        }
        if embedding:
            doc["embedding"] = embedding

        es = self._get_es()
        es.index(
            index=settings.es_message_index,
            id=doc["message_id"],
            body=doc,
            refresh=True,
        )
        # Update conversation's updated_at
        self.update_conversation(conversation_id)
        return doc

    def list_messages(
        self,
        conversation_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List messages for a conversation. Returns (messages, total)."""
        es = self._get_es()
        body = {
            "query": {"term": {"conversation_id": conversation_id}},
            "sort": [{"created_at": {"order": "asc"}}],
            "from": offset,
            "size": limit,
        }
        result = es.search(index=settings.es_message_index, body=body)
        hits = result.get("hits", {}).get("hits", [])
        total = result.get("hits", {}).get("total", {}).get("value", 0)
        return [hit["_source"] for hit in hits], total

    def get_recent_messages(
        self, conversation_id: str, max_rounds: int | None = None
    ) -> list[dict]:
        """Get the most recent N rounds of messages (2*N messages).

        Returns messages in chronological order (oldest first).
        """
        rounds = max_rounds or settings.memory_max_rounds
        es = self._get_es()
        body = {
            "query": {"term": {"conversation_id": conversation_id}},
            "sort": [{"created_at": {"order": "desc"}}],
            "size": rounds * 2,
            "_source": ["message_id", "role", "content", "metadata", "created_at"],
        }
        result = es.search(index=settings.es_message_index, body=body)
        hits = result.get("hits", {}).get("hits", [])
        # Reverse to chronological order
        return list(reversed([hit["_source"] for hit in hits]))

    def count_messages(self, conversation_id: str) -> int:
        """Count total messages for a conversation."""
        es = self._get_es()
        body = {
            "query": {"term": {"conversation_id": conversation_id}},
            "size": 0,
        }
        result = es.search(index=settings.es_message_index, body=body)
        return result.get("hits", {}).get("total", {}).get("value", 0)

    def get_messages_range(
        self, conversation_id: str, offset: int, limit: int
    ) -> list[dict]:
        """Get a range of messages for a conversation (oldest first).

        Used for fetching messages that need to be summarized.
        """
        es = self._get_es()
        body = {
            "query": {"term": {"conversation_id": conversation_id}},
            "sort": [{"created_at": {"order": "asc"}}],
            "from": offset,
            "size": limit,
            "_source": ["role", "content"],
        }
        result = es.search(index=settings.es_message_index, body=body)
        hits = result.get("hits", {}).get("hits", [])
        return [hit["_source"] for hit in hits]

    # -- Profile --

    def _create_profile_index(self, es: Elasticsearch) -> None:
        if es.indices.exists(index=settings.es_profile_index):
            return
        mapping = {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "properties": {
                    "user_id": {"type": "keyword"},
                    "preferences": {"type": "object", "enabled": True},
                    "extracted_at": {"type": "date"},
                    "source_conversation_ids": {"type": "keyword"},
                    "confidence_scores": {"type": "object", "enabled": True},
                }
            },
        }
        es.indices.create(index=settings.es_profile_index, body=mapping)
        logger.info("Created ES index | index=%s", settings.es_profile_index)

    def get_profile(self, user_id: str) -> dict | None:
        """Get user profile. Returns None if not found."""
        try:
            es = self._get_es()
            result = es.get(index=settings.es_profile_index, id=user_id)
            return result["_source"]
        except Exception:
            return None

    def save_profile(self, user_id: str, preferences: dict, source_conversation_ids: list[str] | None = None) -> dict:
        """Save or update user profile."""
        now = datetime.now(timezone.utc)
        doc = {
            "user_id": user_id,
            "preferences": preferences,
            "extracted_at": now.isoformat(),
            "source_conversation_ids": source_conversation_ids or [],
        }
        es = self._get_es()
        es.index(
            index=settings.es_profile_index,
            id=user_id,
            body=doc,
            refresh=True,
        )
        return doc

    def delete_profile(self, user_id: str) -> bool:
        """Delete user profile. Returns True if successful."""
        try:
            es = self._get_es()
            es.delete(index=settings.es_profile_index, id=user_id, refresh=True)
            return True
        except Exception:
            return False

    def count_user_messages(self, user_id: str) -> int:
        """Count total user messages across all conversations for a user."""
        es = self._get_es()
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"role": "user"}},
                    ]
                }
            },
            "size": 0,
        }
        # We need to find messages from conversations belonging to this user.
        # First get conversation IDs for this user.
        conv_body = {
            "query": {"term": {"user_id": user_id}},
            "size": 1000,
            "_source": ["conversation_id"],
        }
        conv_result = es.search(index=settings.es_conversation_index, body=conv_body)
        conv_ids = [hit["_source"]["conversation_id"] for hit in conv_result.get("hits", {}).get("hits", [])]
        if not conv_ids:
            return 0

        body = {
            "query": {
                "bool": {
                    "must": [
                        {"terms": {"conversation_id": conv_ids}},
                        {"term": {"role": "user"}},
                    ]
                }
            },
            "size": 0,
        }
        result = es.search(index=settings.es_message_index, body=body)
        return result.get("hits", {}).get("total", {}).get("value", 0)

    def get_user_conversation_messages(self, user_id: str, limit: int = 50) -> list[dict]:
        """Get recent user messages across all conversations for profile extraction."""
        es = self._get_es()
        # Get conversation IDs for this user
        conv_body = {
            "query": {"term": {"user_id": user_id}},
            "size": 1000,
            "_source": ["conversation_id"],
        }
        conv_result = es.search(index=settings.es_conversation_index, body=conv_body)
        conv_ids = [hit["_source"]["conversation_id"] for hit in conv_result.get("hits", {}).get("hits", [])]
        if not conv_ids:
            return []

        body = {
            "query": {
                "bool": {
                    "must": [
                        {"terms": {"conversation_id": conv_ids}},
                        {"term": {"role": "user"}},
                    ]
                }
            },
            "sort": [{"created_at": {"order": "desc"}}],
            "size": limit,
            "_source": ["content", "conversation_id", "created_at"],
        }
        result = es.search(index=settings.es_message_index, body=body)
        return [hit["_source"] for hit in result.get("hits", {}).get("hits", [])]

    # -- Search --

    def search_conversations(
        self,
        user_id: str,
        query_text: str,
        query_embedding: list[float] | None = None,
        limit: int = 10,
    ) -> tuple[list[dict], int]:
        """Search conversations using hybrid vector + BM25 retrieval.

        Returns (results, total) where each result has conversation metadata + highlights.
        """
        es = self._get_es()
        top_k = limit

        # BM25 search on messages
        bm25_results = self._search_messages_bm25(user_id, query_text, top_k * 2)

        # Vector search on messages (if embedding available)
        vector_results = []
        if query_embedding:
            vector_results = self._search_messages_vector(user_id, query_embedding, top_k * 2)

        # Merge and rank by conversation
        return self._merge_search_results(user_id, bm25_results, vector_results, top_k)

    def _search_messages_bm25(self, user_id: str, query_text: str, k: int) -> list[dict]:
        """BM25 search on message content, scoped to user's conversations."""
        es = self._get_es()
        # First get user's conversation IDs
        conv_ids = self._get_user_conv_ids(user_id)
        if not conv_ids:
            return []

        body = {
            "query": {
                "bool": {
                    "must": [
                        {"terms": {"conversation_id": conv_ids}},
                        {"match": {"content": {"query": query_text, "operator": "or"}}},
                    ]
                }
            },
            "sort": [{"created_at": {"order": "desc"}}],
            "size": k,
            "_source": ["conversation_id", "content"],
            "highlight": {
                "fields": {"content": {"fragment_size": 80, "number_of_fragments": 2}},
            },
        }
        result = es.search(index=settings.es_message_index, body=body)
        hits = result.get("hits", {}).get("hits", [])
        return [
            {
                "conversation_id": hit["_source"]["conversation_id"],
                "score": float(hit["_score"]),
                "highlights": hit.get("highlight", {}).get("content", []),
                "source": "bm25",
            }
            for hit in hits
        ]

    def _search_messages_vector(self, user_id: str, query_embedding: list[float], k: int) -> list[dict]:
        """Vector similarity search on message embeddings, scoped to user's conversations."""
        es = self._get_es()
        conv_ids = self._get_user_conv_ids(user_id)
        if not conv_ids:
            return []

        body = {
            "query": {
                "bool": {
                    "must": [
                        {"terms": {"conversation_id": conv_ids}},
                    ],
                    "filter": {"term": {"embedding_status": "ready"}},
                }
            },
            "knn": {
                "field": "embedding",
                "query_vector": query_embedding,
                "k": k,
                "num_candidates": k * 2,
            },
            "size": k,
            "_source": ["conversation_id"],
        }
        try:
            result = es.search(index=settings.es_message_index, body=body)
            hits = result.get("hits", {}).get("hits", [])
            return [
                {
                    "conversation_id": hit["_source"]["conversation_id"],
                    "score": float(hit["_score"]),
                    "source": "vector",
                }
                for hit in hits
            ]
        except Exception as exc:
            logger.warning("Vector search failed | reason=%s", exc)
            return []

    def _merge_search_results(
        self,
        user_id: str,
        bm25_results: list[dict],
        vector_results: list[dict],
        top_k: int,
    ) -> tuple[list[dict], int]:
        """Merge BM25 and vector results, group by conversation, return ranked."""
        # Score normalization
        bm25_max = max((r["score"] for r in bm25_results), default=1.0) or 1.0
        vector_max = max((r["score"] for r in vector_results), default=1.0) or 1.0

        VECTOR_WEIGHT = 0.7
        BM25_WEIGHT = 0.3

        conv_scores: dict[str, float] = {}
        conv_highlights: dict[str, list[str]] = {}

        for r in bm25_results:
            cid = r["conversation_id"]
            norm_score = r["score"] / bm25_max
            conv_scores[cid] = conv_scores.get(cid, 0.0) + BM25_WEIGHT * norm_score
            if r.get("highlights"):
                conv_highlights.setdefault(cid, []).extend(r["highlights"])

        for r in vector_results:
            cid = r["conversation_id"]
            norm_score = r["score"] / vector_max
            conv_scores[cid] = conv_scores.get(cid, 0.0) + VECTOR_WEIGHT * norm_score

        # Rank by merged score
        ranked = sorted(conv_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]

        # Fetch conversation metadata for ranked results
        results: list[dict] = []
        for cid, score in ranked:
            conv = self.get_conversation(cid)
            if not conv:
                continue
            # Count messages
            msg_count = self.count_messages(cid)
            # Get last message timestamp
            recent = self.get_recent_messages(cid, max_rounds=1)
            last_msg_at = recent[-1].get("created_at") if recent else conv.get("updated_at")

            results.append({
                "conversation_id": cid,
                "title": conv.get("title"),
                "score": round(score, 4),
                "highlights": conv_highlights.get(cid, [])[:3],
                "page_id": conv.get("page_id"),
                "message_count": msg_count,
                "last_message_at": last_msg_at,
            })

        return results, len(conv_scores)

    def _get_user_conv_ids(self, user_id: str) -> list[str]:
        """Get all conversation IDs for a user."""
        es = self._get_es()
        body = {
            "query": {"term": {"user_id": user_id}},
            "size": 1000,
            "_source": ["conversation_id"],
        }
        result = es.search(index=settings.es_conversation_index, body=body)
        return [hit["_source"]["conversation_id"] for hit in result.get("hits", {}).get("hits", [])]