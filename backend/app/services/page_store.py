from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from ..agent.state import AgentTraceStep, GenerationSource
from ..schemas.page_dsl import GenerationRequestDraft, PageDSL


TERMINAL_STATUSES = {"SUCCESS", "FAILED", "CANCELLED"}


def _find_data_dir() -> Path:
    current = Path(__file__).resolve().parent
    existing_candidates: list[Path] = []
    for _ in range(5):
        candidate = current / "data"
        if candidate.exists():
            existing_candidates.append(candidate)
        current = current.parent

    for candidate in existing_candidates:
        if (candidate / "knowledge").exists():
            return candidate
    if existing_candidates:
        return existing_candidates[0]

    return Path(__file__).resolve().parents[3] / "data"


class PageStoreError(RuntimeError):
    """Raised when SQL-backed page storage fails."""


class StoredPage(BaseModel):
    page_dsl: PageDSL
    generation_source: GenerationSource | None = None
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)
    request_id: str | None = None
    session_id: str | None = None
    status: str = "SUCCESS"
    preview_url: str | None = None
    draft_id: str | None = None


class StoredGenerationResult(BaseModel):
    request_id: str
    status: str
    celery_task_id: str | None = None
    page_id: str | None = None
    draft_id: str | None = None
    preview_url: str | None = None
    publish_url: str | None = None
    generation_source: GenerationSource | None = None
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)
    page_dsl: PageDSL | None = None
    error_code: str | None = None
    error_message: str | None = None


class StoredGenerationRequest(BaseModel):
    request_id: str
    status: str
    prompt: str
    page_type: str
    brand_style: str
    session_id: str | None = None
    user_id: str | None = None
    tenant_id: str | None = None
    page_id: str | None = None
    base_page_id: str | None = None
    revision_instruction: str | None = None


class TaskEvent(BaseModel):
    id: int
    request_id: str
    task_id: str
    action: str
    status: str
    cost_ms: float | None = None
    result_summary: str | None = None
    error_code: str | None = None
    created_at: str


class PageStore:
    """SQL-backed page generation repository.

    Local demo uses SQLite, mirroring the production design where generation
    records, task records, and revision records live in a relational database.
    """

    def __init__(self) -> None:
        self.data_dir = _find_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "page_agent.sqlite3"
        self._ensure_schema()

    # -- Async generation request lifecycle --

    def create_generation_request(
        self,
        payload: GenerationRequestDraft,
        session_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> str:
        request_id = f"req_{uuid4().hex[:12]}"
        now = _now()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_generation_record (
                        request_id, session_id, user_id, tenant_id, prompt, page_type,
                        brand_style, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        session_id,
                        user_id,
                        tenant_id,
                        payload.prompt,
                        payload.page_type,
                        payload.brand_style,
                        "PENDING",
                        now,
                        now,
                    ),
                )
                conn.commit()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to create generation request") from exc
        return request_id

    def create_revision_request(
        self,
        base_page_id: str,
        instruction: str,
        base_page: PageDSL,
        session_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> str:
        request_id = f"req_{uuid4().hex[:12]}"
        now = _now()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_generation_record (
                        request_id, session_id, user_id, tenant_id, prompt, page_type,
                        brand_style, status, base_page_id, revision_instruction,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        session_id,
                        user_id,
                        tenant_id,
                        instruction,
                        base_page.page_meta.page_type,
                        base_page.page_meta.theme,
                        "PENDING",
                        base_page_id,
                        instruction,
                        now,
                        now,
                    ),
                )
                conn.commit()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to create revision request") from exc
        return request_id

    def set_celery_task_id(self, request_id: str, celery_task_id: str) -> None:
        self._update_generation_record(
            request_id,
            celery_task_id=celery_task_id,
            updated_at=_now(),
        )

    def load_generation_request(self, request_id: str) -> StoredGenerationRequest:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT request_id, status, prompt, page_type, brand_style,
                           session_id, user_id, tenant_id, page_id, base_page_id,
                           revision_instruction
                    FROM agent_generation_record
                    WHERE request_id = ?
                    """,
                    (request_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to read generation request") from exc

        if row is None:
            raise FileNotFoundError(request_id)

        return StoredGenerationRequest(
            request_id=row["request_id"],
            status=row["status"],
            prompt=row["prompt"],
            page_type=row["page_type"],
            brand_style=row["brand_style"],
            session_id=row["session_id"],
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
            page_id=row["page_id"],
            base_page_id=row["base_page_id"],
            revision_instruction=row["revision_instruction"],
        )

    def mark_running(self, request_id: str) -> None:
        now = _now()
        self._update_generation_record(
            request_id,
            status="RUNNING",
            started_at=now,
            updated_at=now,
        )
        self.add_task_event(
            request_id=request_id,
            task_id="request_running",
            action="request_status",
            status="RUNNING",
            result_summary="Celery worker started processing request",
        )

    def complete_request(
        self,
        request_id: str,
        page_dsl: PageDSL,
        generation_source: GenerationSource,
        agent_trace: list[AgentTraceStep],
        base_page_id: str | None = None,
        revision_instruction: str | None = None,
    ) -> str:
        page_id = f"page_{uuid4().hex[:8]}"
        draft_id = f"draft_{page_id.removeprefix('page_')}"
        preview_url = f"/preview/{page_id}"
        now = _now()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE agent_generation_record
                    SET status = ?, page_id = ?, draft_id = ?, preview_url = ?,
                        generation_source = ?, dsl_snapshot = ?, agent_trace = ?,
                        error_code = NULL, error_message = NULL,
                        finished_at = ?, updated_at = ?
                    WHERE request_id = ?
                    """,
                    (
                        "SUCCESS",
                        page_id,
                        draft_id,
                        preview_url,
                        generation_source,
                        page_dsl.model_dump_json(),
                        _trace_to_json(agent_trace),
                        now,
                        now,
                        request_id,
                    ),
                )
                self._insert_task_records(conn, request_id, agent_trace, now)
                if revision_instruction or base_page_id:
                    self._insert_revision_record(
                        conn=conn,
                        request_id=request_id,
                        session_id=self._get_session_id(conn, request_id),
                        base_page_id=base_page_id,
                        new_page_id=page_id,
                        instruction=revision_instruction or "",
                        created_at=now,
                    )
                conn.commit()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to complete generation request") from exc
        return page_id

    def fail_request(self, request_id: str, error_message: str, error_code: str = "AGENT_EXECUTION_FAILED") -> None:
        now = _now()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE agent_generation_record
                    SET status = ?, error_code = ?, error_message = ?,
                        finished_at = ?, updated_at = ?
                    WHERE request_id = ?
                    """,
                    ("FAILED", error_code, error_message, now, now, request_id),
                )
                conn.execute(
                    """
                    INSERT INTO agent_task_record (
                        request_id, task_id, action, task_params, status, cost_ms,
                        result_summary, error_code, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        "request_failed",
                        "request_status",
                        "{}",
                        "failed",
                        None,
                        error_message,
                        error_code,
                        now,
                    ),
                )
                conn.commit()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to mark generation request as failed") from exc

    def add_task_event(
        self,
        request_id: str,
        task_id: str,
        action: str,
        status: str,
        result_summary: str | None = None,
        task_params: dict | None = None,
        cost_ms: float | None = None,
        error_code: str | None = None,
    ) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_task_record (
                        request_id, task_id, action, task_params, status, cost_ms,
                        result_summary, error_code, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        task_id,
                        action,
                        json.dumps(task_params or {}, ensure_ascii=False),
                        status,
                        cost_ms,
                        result_summary,
                        error_code,
                        _now(),
                    ),
                )
                conn.commit()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to add task event") from exc

    def list_task_events(self, request_id: str, after_id: int = 0) -> list[TaskEvent]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, request_id, task_id, action, status, cost_ms,
                           result_summary, error_code, created_at
                    FROM agent_task_record
                    WHERE request_id = ? AND id > ?
                    ORDER BY id ASC
                    """,
                    (request_id, after_id),
                ).fetchall()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to list task events") from exc

        return [
            TaskEvent(
                id=row["id"],
                request_id=row["request_id"],
                task_id=row["task_id"],
                action=row["action"],
                status=row["status"],
                cost_ms=row["cost_ms"],
                result_summary=row["result_summary"],
                error_code=row["error_code"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    # -- Backward-compatible completed page storage --

    def save_page(
        self,
        page_dsl: PageDSL,
        generation_source: GenerationSource | None = None,
        agent_trace: list[AgentTraceStep] | None = None,
        request_payload: GenerationRequestDraft | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        tenant_id: str | None = None,
        base_page_id: str | None = None,
        revision_instruction: str | None = None,
    ) -> str:
        page_id = f"page_{uuid4().hex[:8]}"
        request_id = f"req_{uuid4().hex[:12]}"
        draft_id = f"draft_{page_id.removeprefix('page_')}"
        preview_url = f"/preview/{page_id}"
        now = _now()
        trace = agent_trace or []

        prompt = request_payload.prompt if request_payload else None
        page_type = request_payload.page_type if request_payload else page_dsl.page_meta.page_type
        brand_style = request_payload.brand_style if request_payload else page_dsl.page_meta.theme

        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO agent_generation_record (
                        request_id, session_id, user_id, tenant_id, prompt, page_type,
                        brand_style, status, page_id, draft_id, preview_url,
                        generation_source, dsl_snapshot, agent_trace,
                        started_at, finished_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        session_id,
                        user_id,
                        tenant_id,
                        prompt,
                        page_type,
                        brand_style,
                        "SUCCESS",
                        page_id,
                        draft_id,
                        preview_url,
                        generation_source,
                        page_dsl.model_dump_json(),
                        _trace_to_json(trace),
                        now,
                        now,
                        now,
                        now,
                    ),
                )
                self._insert_task_records(conn, request_id, trace, now)
                if revision_instruction or base_page_id:
                    self._insert_revision_record(
                        conn=conn,
                        request_id=request_id,
                        session_id=session_id,
                        base_page_id=base_page_id,
                        new_page_id=page_id,
                        instruction=revision_instruction or "",
                        created_at=now,
                    )
                conn.commit()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to save page generation record to sql storage") from exc

        return page_id

    def load_page(self, page_id: str) -> StoredPage:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT request_id, session_id, status, page_id, draft_id, preview_url,
                           generation_source, dsl_snapshot, agent_trace
                    FROM agent_generation_record
                    WHERE page_id = ?
                    """,
                    (page_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to read page generation record from sql storage") from exc

        if row:
            return self._row_to_stored_page(row)

        return self._load_legacy_json_page(page_id)

    def load_generation_result(self, request_id: str) -> StoredGenerationResult:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT request_id, status, celery_task_id, page_id, draft_id,
                           preview_url, publish_url, generation_source,
                           dsl_snapshot, agent_trace, error_code, error_message
                    FROM agent_generation_record
                    WHERE request_id = ?
                    """,
                    (request_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to read generation result from sql storage") from exc

        if row is None:
            raise FileNotFoundError(request_id)

        page_dsl = PageDSL.model_validate(json.loads(row["dsl_snapshot"])) if row["dsl_snapshot"] else None
        return StoredGenerationResult(
            request_id=row["request_id"],
            status=row["status"],
            celery_task_id=row["celery_task_id"],
            page_id=row["page_id"],
            draft_id=row["draft_id"],
            preview_url=row["preview_url"],
            publish_url=row["publish_url"],
            generation_source=row["generation_source"],
            agent_trace=_parse_trace(row["agent_trace"]),
            page_dsl=page_dsl,
            error_code=row["error_code"],
            error_message=row["error_message"],
        )

    def get_latest_request_id_for_page(self, page_id: str) -> str | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT request_id
                    FROM agent_generation_record
                    WHERE page_id = ?
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (page_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to query page request id from sql storage") from exc
        return row["request_id"] if row else None

    # -- Schema / helpers --

    def _ensure_schema(self) -> None:
        try:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS agent_generation_record (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_id TEXT NOT NULL UNIQUE,
                        celery_task_id TEXT,
                        session_id TEXT,
                        user_id TEXT,
                        tenant_id TEXT,
                        prompt TEXT,
                        page_type TEXT,
                        brand_style TEXT,
                        status TEXT NOT NULL,
                        page_id TEXT UNIQUE,
                        base_page_id TEXT,
                        revision_instruction TEXT,
                        draft_id TEXT,
                        preview_url TEXT,
                        publish_url TEXT,
                        generation_source TEXT,
                        dsl_snapshot TEXT,
                        agent_trace TEXT,
                        error_code TEXT,
                        error_message TEXT,
                        started_at TEXT,
                        finished_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_generation_page_id
                    ON agent_generation_record(page_id);

                    CREATE INDEX IF NOT EXISTS idx_generation_session_id
                    ON agent_generation_record(session_id);

                    CREATE INDEX IF NOT EXISTS idx_generation_status
                    ON agent_generation_record(status);

                    CREATE TABLE IF NOT EXISTS agent_task_record (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        task_params TEXT,
                        status TEXT NOT NULL,
                        cost_ms REAL,
                        result_summary TEXT,
                        error_code TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(request_id) REFERENCES agent_generation_record(request_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_task_request_id
                    ON agent_task_record(request_id);

                    CREATE TABLE IF NOT EXISTS agent_revision_record (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        request_id TEXT NOT NULL,
                        session_id TEXT,
                        page_id TEXT,
                        instruction TEXT,
                        base_version TEXT,
                        new_version TEXT,
                        diff_summary TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY(request_id) REFERENCES agent_generation_record(request_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_revision_session_id
                    ON agent_revision_record(session_id);
                    """
                )
                self._migrate_generation_record(conn)
                conn.commit()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to initialize sql page storage") from exc

    def _migrate_generation_record(self, conn: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(agent_generation_record)").fetchall()
        }
        migrations = {
            "celery_task_id": "ALTER TABLE agent_generation_record ADD COLUMN celery_task_id TEXT",
            "brand_style": "ALTER TABLE agent_generation_record ADD COLUMN brand_style TEXT",
            "base_page_id": "ALTER TABLE agent_generation_record ADD COLUMN base_page_id TEXT",
            "revision_instruction": "ALTER TABLE agent_generation_record ADD COLUMN revision_instruction TEXT",
            "error_code": "ALTER TABLE agent_generation_record ADD COLUMN error_code TEXT",
            "started_at": "ALTER TABLE agent_generation_record ADD COLUMN started_at TEXT",
            "finished_at": "ALTER TABLE agent_generation_record ADD COLUMN finished_at TEXT",
        }
        for column, sql in migrations.items():
            if column not in existing:
                conn.execute(sql)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _update_generation_record(self, request_id: str, **fields: object) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        values = list(fields.values()) + [request_id]
        try:
            with self._connect() as conn:
                conn.execute(
                    f"UPDATE agent_generation_record SET {assignments} WHERE request_id = ?",
                    values,
                )
                conn.commit()
        except sqlite3.Error as exc:
            raise PageStoreError("failed to update generation record") from exc

    def _insert_task_records(
        self,
        conn: sqlite3.Connection,
        request_id: str,
        trace: list[AgentTraceStep],
        created_at: str,
    ) -> None:
        for step in trace:
            conn.execute(
                """
                INSERT INTO agent_task_record (
                    request_id, task_id, action, task_params, status, cost_ms,
                    result_summary, error_code, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    f"node_{step.node}",
                    step.node,
                    json.dumps(step.metadata, ensure_ascii=False),
                    step.status,
                    step.duration_ms,
                    step.message,
                    None if step.status == "success" else step.message,
                    created_at,
                ),
            )

    def _insert_revision_record(
        self,
        conn: sqlite3.Connection,
        request_id: str,
        session_id: str | None,
        base_page_id: str | None,
        new_page_id: str,
        instruction: str,
        created_at: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO agent_revision_record (
                request_id, session_id, page_id, instruction, base_version,
                new_version, diff_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                session_id,
                new_page_id,
                instruction,
                base_page_id,
                new_page_id,
                _build_diff_summary(instruction),
                created_at,
            ),
        )

    def _get_session_id(self, conn: sqlite3.Connection, request_id: str) -> str | None:
        row = conn.execute(
            "SELECT session_id FROM agent_generation_record WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return row["session_id"] if row else None

    def _row_to_stored_page(self, row: sqlite3.Row) -> StoredPage:
        return StoredPage(
            request_id=row["request_id"],
            session_id=row["session_id"],
            status=row["status"],
            preview_url=row["preview_url"],
            draft_id=row["draft_id"],
            generation_source=row["generation_source"],
            agent_trace=_parse_trace(row["agent_trace"]),
            page_dsl=PageDSL.model_validate(json.loads(row["dsl_snapshot"])),
        )

    def _load_legacy_json_page(self, page_id: str) -> StoredPage:
        file_path = self.data_dir / "pages" / f"{page_id}.json"
        if not file_path.exists():
            raise FileNotFoundError(page_id)

        try:
            raw_text = file_path.read_text(encoding="utf-8")
            payload = json.loads(raw_text)
        except OSError as exc:
            raise PageStoreError("failed to read legacy page dsl from local json storage") from exc
        except json.JSONDecodeError as exc:
            raise PageStoreError("stored legacy page dsl is not valid json") from exc

        if "page_dsl" in payload:
            return StoredPage.model_validate(payload)

        return StoredPage(page_dsl=PageDSL.model_validate(payload))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace_to_json(trace: list[AgentTraceStep]) -> str:
    return json.dumps([step.model_dump() for step in trace], ensure_ascii=False)


def _parse_trace(raw_trace: str | None) -> list[AgentTraceStep]:
    if not raw_trace:
        return []
    return [AgentTraceStep.model_validate(item) for item in json.loads(raw_trace)]


def _build_diff_summary(instruction: str) -> str:
    if not instruction:
        return "recorded page revision"
    return f"revision requested: {instruction[:120]}"
