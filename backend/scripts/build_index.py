"""
CLI script to build the Elasticsearch knowledge index.

Usage (in Docker):
    python -m scripts.build_index

Usage (local dev):
    python -m backend.scripts.build_index
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure the parent directory is on sys.path so "app" is importable
# Works both in Docker (/app) and local dev (backend/)
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from app.config import settings
from app.services.knowledge_store import KnowledgeStore


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("build_index")


def main() -> None:
    import elasticsearch as es_pkg

    logger.info("=" * 60)
    logger.info("Knowledge Index Builder")
    logger.info("ES Host: %s", settings.es_host)
    logger.info("Index Name: %s", settings.es_index_name)
    logger.info("Embedding Model: %s", settings.embedding_model_name)
    logger.info("Embedding Dim: %s", settings.embedding_dim)
    logger.info("ES Client Version: %s", es_pkg.__version__)
    logger.info("=" * 60)

    store = KnowledgeStore()
    try:
        result = store.build_index()
        logger.info("Build result: %s", result)
    except Exception as exc:
        logger.exception("Index build failed")
        sys.exit(1)

    logger.info("Index build completed successfully")


if __name__ == "__main__":
    main()
