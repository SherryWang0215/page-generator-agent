from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from ..config import settings

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """Loads documents from data/knowledge/, chunks them, generates embeddings,
    and indexes everything into Elasticsearch for hybrid retrieval."""

    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 100

    def __init__(self) -> None:
        self._es: Elasticsearch | None = None

    def build_index(self) -> dict[str, Any]:
        """Full index rebuild: create index, load docs, chunk, embed, index."""
        logger.info("Starting knowledge index build | index=%s", settings.es_index_name)
        es = self._get_es()
        self._create_index(es)
        chunks = self._load_and_chunk_all()
        if not chunks:
            logger.warning("No knowledge documents found in data/knowledge/")
            return {"status": "empty", "chunks_indexed": 0}
        self._index_chunks(es, chunks)
        logger.info("Knowledge index build completed | chunks=%d", len(chunks))
        return {"status": "success", "chunks_indexed": len(chunks)}

    def _get_es(self) -> Elasticsearch:
        if self._es is None:
            self._es = Elasticsearch(hosts=[settings.es_host])
            try:
                info = self._es.info()
                logger.info(
                    "Connected to ES | cluster=%s | version=%s",
                    info.get("cluster_name", "unknown"),
                    info.get("version", {}).get("number", "unknown"),
                )
            except Exception as exc:
                raise ConnectionError(
                    f"unable to connect to Elasticsearch at {settings.es_host}: {exc}"
                ) from exc
        return self._es

    def _create_index(self, es: Elasticsearch) -> None:
        if es.indices.exists(index=settings.es_index_name):
            es.indices.delete(index=settings.es_index_name)
            logger.info("Deleted existing index | index=%s", settings.es_index_name)

        mapping = {
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "chunk_index": {"type": "integer"},
                    "source_path": {"type": "keyword"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": settings.embedding_dim,
                        "index": True,
                        "similarity": "cosine",
                    },
                }
            },
        }
        es.indices.create(index=settings.es_index_name, body=mapping)
        logger.info("Created ES index | index=%s | dims=%d", settings.es_index_name, settings.embedding_dim)

    def _load_and_chunk_all(self) -> list[dict[str, Any]]:
        knowledge_dir = self._knowledge_dir()
        if not knowledge_dir.exists():
            return []

        all_chunks: list[dict[str, Any]] = []
        for md_file in sorted(knowledge_dir.rglob("*.md")):
            chunks = self._process_document(md_file)
            all_chunks.extend(chunks)
            logger.info("Processed document | file=%s | chunks=%d", md_file.name, len(chunks))
        return all_chunks

    def _knowledge_dir(self) -> Path:
        # Walk up from this file's directory until we find data/knowledge
        current = Path(__file__).resolve().parent
        for _ in range(5):
            candidate = current / "data" / "knowledge"
            if candidate.exists():
                return candidate
            current = current.parent
        # fallback for local dev
        return Path(__file__).resolve().parents[3] / "data" / "knowledge"

    def _process_document(self, file_path: Path) -> list[dict[str, Any]]:
        try:
            text = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Failed to read knowledge document | file=%s | reason=%s", file_path, exc)
            return []

        title = self._extract_title(text)
        doc_id = file_path.stem
        chunks = self._chunk_text(text)

        return [
            {
                "doc_id": doc_id,
                "title": title,
                "content": chunk,
                "chunk_index": idx,
                "source_path": str(file_path.relative_to(self._knowledge_dir())),
            }
            for idx, chunk in enumerate(chunks)
        ]

    @staticmethod
    def _extract_title(text: str) -> str:
        first_line = text.strip().split("\n")[0].strip()
        return re.sub(r"^#+\s*", "", first_line) or "untitled"

    def _chunk_text(self, text: str) -> list[str]:
        cleaned = self._clean_markdown(text)
        paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
        chunks: list[str] = []
        for para in paragraphs:
            if len(para) <= self.CHUNK_SIZE:
                if chunks and len(chunks[-1]) + len(para) < self.CHUNK_SIZE:
                    chunks[-1] = chunks[-1] + "\n\n" + para
                else:
                    chunks.append(para)
            else:
                chunks.extend(self._split_long_text(para))
        return chunks

    @staticmethod
    def _clean_markdown(text: str) -> str:
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        text = re.sub(r"!\[.*?\]\(.+?\)", "", text)
        text = re.sub(r"[-*+]\s+", "", text)
        text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _split_long_text(self, text: str) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + self.CHUNK_SIZE
            if end >= len(text):
                chunks.append(text[start:].strip())
                break
            break_point = text.rfind("。", start, end)
            if break_point == -1:
                break_point = text.rfind(".", start, end)
            if break_point == -1 or break_point <= start:
                break_point = end
            else:
                break_point += 1
            chunks.append(text[start:break_point].strip())
            start = max(start + 1, break_point - self.CHUNK_OVERLAP)
        return chunks

    def _index_chunks(self, es: Elasticsearch, chunks: list[dict[str, Any]]) -> None:
        embeddings = self._encode_chunks(chunks)
        actions = [
            {
                "_index": settings.es_index_name,
                "_id": f"{chunk['doc_id']}#{chunk['chunk_index']}",
                "_source": {
                    **chunk,
                    "embedding": embedding,
                },
            }
            for chunk, embedding in zip(chunks, embeddings)
        ]
        success, errors = bulk(es, actions, refresh=True)
        if errors:
            logger.error("Bulk indexing completed with errors | errors=%s", len(errors))
            for err in errors[:5]:
                logger.error("ES bulk error | %s", json.dumps(err, default=str))

    def _encode_chunks(self, chunks: list[dict[str, Any]]) -> list[list[float]]:
        from .embedding_client import encode

        texts = [chunk["content"] for chunk in chunks]
        return encode(texts, text_type="document")
