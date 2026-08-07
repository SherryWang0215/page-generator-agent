from __future__ import annotations

import logging

from ..agent.runner import run_page_generation_agent, run_page_revision_agent
from ..schemas.page_dsl import GenerationRequestDraft
from ..services.conversation_store import ConversationStore
from ..services.memory_service import MemoryService
from ..services.page_store import PageStore
from .celery_app import celery_app


logger = logging.getLogger(__name__)


@celery_app.task(name="page.generate")
def generate_page_task(request_id: str) -> dict[str, str | None]:
    store = PageStore()
    try:
        request_record = store.load_generation_request(request_id)
        store.mark_running(request_id)
        payload = GenerationRequestDraft(
            prompt=request_record.prompt,
            page_type=request_record.page_type,
            brand_style=request_record.brand_style,
        )
        agent_result = run_page_generation_agent(payload, request_id=request_id)
        page_id = store.complete_request(
            request_id=request_id,
            page_dsl=agent_result.page_dsl,
            generation_source=agent_result.generation_source,
            agent_trace=agent_result.agent_trace,
        )
        _sync_conversation_result(request_record.session_id, request_id, page_id, "页面生成完成")
        logger.info("Celery generation task completed | request_id=%s | page_id=%s", request_id, page_id)
        return {"request_id": request_id, "page_id": page_id, "status": "SUCCESS"}
    except Exception as exc:
        logger.exception("Celery generation task failed | request_id=%s", request_id)
        store.fail_request(request_id, str(exc))
        raise


@celery_app.task(name="page.revise")
def revise_page_task(request_id: str) -> dict[str, str | None]:
    store = PageStore()
    try:
        request_record = store.load_generation_request(request_id)
        if not request_record.base_page_id:
            raise ValueError("base_page_id is required for revision task")

        store.mark_running(request_id)
        stored_page = store.load_page(request_record.base_page_id)
        instruction = request_record.revision_instruction or request_record.prompt
        agent_result = run_page_revision_agent(stored_page.page_dsl, instruction, request_id=request_id)
        page_id = store.complete_request(
            request_id=request_id,
            page_dsl=agent_result.page_dsl,
            generation_source=agent_result.generation_source,
            agent_trace=agent_result.agent_trace,
            base_page_id=request_record.base_page_id,
            revision_instruction=instruction,
        )
        _sync_conversation_result(request_record.session_id, request_id, page_id, "页面修改完成")
        logger.info("Celery revision task completed | request_id=%s | page_id=%s", request_id, page_id)
        return {"request_id": request_id, "page_id": page_id, "status": "SUCCESS"}
    except Exception as exc:
        logger.exception("Celery revision task failed | request_id=%s", request_id)
        store.fail_request(request_id, str(exc))
        raise


def _sync_conversation_result(
    conversation_id: str | None,
    request_id: str,
    page_id: str,
    message_prefix: str,
) -> None:
    """Best-effort sync from async page tasks back to conversation memory."""
    if not conversation_id:
        return

    try:
        conversation_store = ConversationStore()
        conversation_store.update_conversation(conversation_id, page_id=page_id)
        MemoryService(store=conversation_store).save_assistant_message(
            conversation_id,
            content=f"{message_prefix}，页面ID: {page_id}",
            metadata={"page_id": page_id, "request_id": request_id, "status": "SUCCESS"},
        )
    except Exception:
        logger.warning(
            "Failed to sync async page result to conversation | conversation_id=%s | request_id=%s",
            conversation_id,
            request_id,
            exc_info=True,
        )
