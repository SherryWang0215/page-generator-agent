from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import httpx

from ..config import settings


logger = logging.getLogger(__name__)


def trace_agent_run(
    *,
    name: str,
    inputs: dict[str, Any],
    outputs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Best-effort LangSmith run creation.

    The project remains fully functional when LangSmith is not configured.
    """
    if not settings.langsmith_enabled or not settings.langsmith_api_key:
        return

    payload = {
        "id": str(uuid4()),
        "name": name,
        "run_type": "chain",
        "session_name": settings.langsmith_project,
        "inputs": inputs,
        "outputs": outputs or {},
        "extra": {"metadata": metadata or {}},
        "error": error,
    }
    try:
        with httpx.Client(timeout=5) as client:
            response = client.post(
                f"{settings.langsmith_endpoint.rstrip('/')}/runs",
                headers={"x-api-key": settings.langsmith_api_key},
                json=payload,
            )
        logger.info(
            "LangSmith trace sent | name=%s | project=%s | status=%s",
            name,
            settings.langsmith_project,
            response.status_code,
        )
    except Exception:
        logger.warning("Failed to send LangSmith trace | name=%s", name, exc_info=True)
