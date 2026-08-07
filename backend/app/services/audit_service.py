from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import settings


logger = logging.getLogger(__name__)


def audit_event(event_type: str, payload: dict[str, Any]) -> None:
    """Append an audit event to a local JSONL file.

    This keeps governance observable in local/demo environments without adding
    another storage dependency. Production can replace this with Kafka/DB/SIEM.
    """
    record = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    try:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("Failed to write audit event | event_type=%s", event_type, exc_info=True)


def _audit_path() -> Path:
    path = Path(settings.audit_log_path)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[3] / path
