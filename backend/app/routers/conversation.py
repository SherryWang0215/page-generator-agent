from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Query

from ..schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    MessageListResponse,
    MessageResponse,
    ProfileResponse,
    SearchResponse,
    SearchResultItem,
    SendMessageResponse,
)
from ..schemas.page_dsl import GenerationRequestDraft
from ..services.conversation_store import ConversationStore
from ..services.memory_service import MemoryService
from ..services.page_store import PageStore, PageStoreError
from ..worker.tasks import generate_page_task, revise_page_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["conversations"])

conversation_store = ConversationStore()
memory_service = MemoryService(store=conversation_store)
page_store = PageStore()


def _get_user_id(x_user_id: str | None = Header(default=None)) -> str:
    """Extract user ID from header or raise 400."""
    if not x_user_id:
        raise HTTPException(status_code=400, detail="X-User-ID header is required")
    return x_user_id


def _conv_to_response(conv: dict) -> ConversationResponse:
    return ConversationResponse(
        conversation_id=conv["conversation_id"],
        user_id=conv["user_id"],
        page_id=conv.get("page_id"),
        title=conv.get("title"),
        created_at=conv["created_at"],
        updated_at=conv["updated_at"],
        status=conv.get("status", "active"),
    )


def _msg_to_response(msg: dict) -> MessageResponse:
    return MessageResponse(
        message_id=msg["message_id"],
        conversation_id=msg["conversation_id"],
        role=msg["role"],
        content=msg["content"],
        metadata=msg.get("metadata", {}),
        created_at=msg["created_at"],
    )


@router.post("/conversations", response_model=ConversationResponse)
def create_conversation(
    payload: ConversationCreate,
    x_user_id: str = Header(alias="X-User-ID"),
):
    """Create a new conversation."""
    conversation_store.ensure_indices()
    conv = memory_service.get_or_create_conversation(
        user_id=x_user_id, page_id=payload.page_id
    )
    return _conv_to_response(conv)


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    x_user_id: str = Header(alias="X-User-ID"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List conversations for a user."""
    conversation_store.ensure_indices()
    conversations, total = conversation_store.list_conversations(
        user_id=x_user_id, limit=limit, offset=offset
    )
    return ConversationListResponse(
        conversations=[_conv_to_response(c) for c in conversations],
        total=total,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(conversation_id: str):
    """Get conversation detail with messages."""
    conv = conversation_store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    messages, total = conversation_store.list_messages(conversation_id)
    return ConversationDetailResponse(
        conversation=_conv_to_response(conv),
        messages=[_msg_to_response(m) for m in messages],
    )


@router.delete("/conversations/{conversation_id}")
def archive_conversation(conversation_id: str):
    """Archive a conversation."""
    success = conversation_store.archive_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {"status": "archived"}


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListResponse)
def list_messages(
    conversation_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Get message history for a conversation."""
    messages, total = conversation_store.list_messages(
        conversation_id, limit=limit, offset=offset
    )
    return MessageListResponse(
        messages=[_msg_to_response(m) for m in messages],
        total=total,
    )


@router.post("/conversations/{conversation_id}/messages", response_model=SendMessageResponse)
def send_message(conversation_id: str, payload: dict):
    """Send a message in a conversation and get a response.

    This is the core endpoint that handles generation, revision, and chat.
    """
    content = payload.get("content", "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    # Verify conversation exists
    conv = conversation_store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")

    # Save user message
    memory_service.save_user_message(conversation_id, content)

    # Detect intent
    intent = memory_service.detect_intent(conversation_id, content)
    logger.info("Detected intent | conv=%s | intent=%s | content=%s", conversation_id, intent, content[:50])

    # Validate minimum length for generate/revise intents
    if intent in ("generate", "revise") and len(content) < 8:
        raise HTTPException(
            status_code=400,
            detail=f"页面生成/修改需要至少8个字的描述，当前输入仅{len(content)}个字，请补充更多细节。",
        )

    request_id: str | None = None
    celery_task_id: str | None = None

    # Handle based on intent. Page generation/revision is always dispatched to
    # Celery so conversation mode shares the same execution boundary as HomePage.
    if intent == "generate":
        response_content, page_id, pages, request_id, celery_task_id = _handle_generate(
            conv, content, conversation_id
        )
    elif intent == "revise":
        response_content, page_id, pages, request_id, celery_task_id = _handle_revise(
            conv, content, conversation_id
        )
    else:
        response_content, page_id, pages = _handle_chat(conv, content, conversation_id)

    # Save assistant message
    metadata = {}
    if page_id:
        metadata["page_id"] = page_id
    if request_id:
        metadata["request_id"] = request_id
        metadata["status"] = "PENDING"
        metadata["intent"] = intent

    assistant_msg = memory_service.save_assistant_message(
        conversation_id,
        content=response_content,
        metadata=metadata,
    )

    # Always track the latest page_id in the conversation
    if page_id and page_id != conv.get("page_id"):
        conversation_store.update_conversation(conversation_id, page_id=page_id)

    # Trigger profile extraction if threshold reached (async-safe, non-blocking)
    try:
        user_id = conv.get("user_id")
        if user_id:
            memory_service.maybe_extract_profile(user_id)
    except Exception:
        logger.warning("Profile extraction trigger failed | conv=%s", conversation_id)

    # Trigger conversation compression if needed
    try:
        memory_service.maybe_compress_conversation(conversation_id)
    except Exception:
        logger.warning("Conversation compression trigger failed | conv=%s", conversation_id)

    return SendMessageResponse(
        message_id=assistant_msg["message_id"],
        content=response_content,
        page_id=page_id,
        pages=pages,
        request_id=request_id,
        status="PENDING" if request_id else None,
        celery_task_id=celery_task_id,
        intent=intent,
    )


def _build_history_context(conversation_id: str) -> str:
    """Build conversation history as text for injection into LLM prompts."""
    history = memory_service.load_history(conversation_id)
    if not history:
        return ""
    lines = ["[以下是之前的对话历史，请结合上下文理解用户当前请求]"]
    for msg in history:
        role_label = "用户" if msg.get("role") == "user" else "助手"
        lines.append(f"{role_label}: {msg.get('content', '')}")
    return "\n".join(lines) + "\n"


def _handle_generate(
    conv: dict, content: str, conversation_id: str
) -> tuple[str, str | None, list[dict], str | None, str | None]:
    """Handle a generate intent."""
    history_context = _build_history_context(conversation_id)
    enhanced_prompt = history_context + content if history_context else content
    request = GenerationRequestDraft(
        prompt=enhanced_prompt,
        page_type="landing_page",
        brand_style="tech_clean",
    )

    request_id: str | None = None
    try:
        request_id = page_store.create_generation_request(
            request,
            session_id=conversation_id,
            user_id=conv.get("user_id"),
        )
        async_result = generate_page_task.delay(request_id)
        page_store.set_celery_task_id(request_id, async_result.id)
        response_content = f"已提交页面生成任务，任务ID: {request_id}。生成完成后将自动关联到当前对话。"
        return response_content, None, [], request_id, async_result.id
    except PageStoreError as exc:
        logger.exception("Page generation request creation failed | conv=%s", conversation_id)
        return f"页面生成任务创建失败: {exc}", None, [], None, None
    except Exception as exc:
        if request_id:
            try:
                page_store.fail_request(request_id, str(exc), error_code="CELERY_DISPATCH_FAILED")
            except Exception:
                logger.warning("Failed to mark generation request as failed | request_id=%s", request_id)
        logger.exception("Page generation dispatch failed | conv=%s", conversation_id)
        return f"页面生成任务提交失败: {exc}", None, [], None, None


def _handle_revise(
    conv: dict, content: str, conversation_id: str
) -> tuple[str, str | None, list[dict], str | None, str | None]:
    """Handle a revise intent."""
    page_id = conv.get("page_id")
    if not page_id:
        return _handle_generate(conv, content, conversation_id)

    request_id: str | None = None
    try:
        history_context = _build_history_context(conversation_id)
        enhanced_instruction = history_context + content if history_context else content
        stored_page = page_store.load_page(page_id)
        request_id = page_store.create_revision_request(
            base_page_id=page_id,
            instruction=enhanced_instruction,
            base_page=stored_page.page_dsl,
            session_id=conversation_id,
            user_id=conv.get("user_id"),
        )
        async_result = revise_page_task.delay(request_id)
        page_store.set_celery_task_id(request_id, async_result.id)
        response_content = f"已提交页面修改任务，任务ID: {request_id}。修改完成后将自动生成新版页面。"
        return response_content, None, [], request_id, async_result.id
    except FileNotFoundError:
        return _handle_generate(conv, content, conversation_id)
    except PageStoreError as exc:
        logger.exception("Page revision request creation failed | conv=%s", conversation_id)
        return f"页面修改任务创建失败: {exc}", None, [], None, None
    except Exception as exc:
        if request_id:
            try:
                page_store.fail_request(request_id, str(exc), error_code="CELERY_DISPATCH_FAILED")
            except Exception:
                logger.warning("Failed to mark revision request as failed | request_id=%s", request_id)
        logger.exception("Page revision dispatch failed | conv=%s", conversation_id)
        return f"页面修改任务提交失败: {exc}", None, [], None, None


def _handle_chat(
    conv: dict, content: str, conversation_id: str
) -> tuple[str, str | None, list[dict]]:
    """Handle a chat intent — simple LLM response without page generation."""
    from ..services.llm_client import OpenAICompatibleClient

    try:
        user_id = conv.get("user_id")
        messages = memory_service.build_llm_messages(
            conversation_id=conversation_id,
            current_content=content,
            system_prompt="你是一个页面生成助手。请用 JSON 格式回复，包含一个 reply 字段。",
            user_id=user_id,
        )
        llm = OpenAICompatibleClient()
        result = llm.generate_json(messages=messages)
        reply = result.get("reply", result.get("content", "抱歉，我无法理解您的问题。"))
        return reply, None, []
    except Exception as exc:
        logger.exception("Chat response failed | conv=%s", conversation_id)
        return "抱歉，暂时无法回复您的问题。", None, []


# -- User Profile --


@router.get("/profile/{user_id}", response_model=ProfileResponse)
def get_profile(user_id: str):
    """Get user profile."""
    profile = conversation_store.get_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")
    return ProfileResponse(
        user_id=profile["user_id"],
        preferences=profile.get("preferences", {}),
        extracted_at=profile.get("extracted_at"),
        source_conversation_ids=profile.get("source_conversation_ids", []),
    )


@router.post("/profile/{user_id}/extract", response_model=ProfileResponse)
def extract_profile(user_id: str):
    """Manually trigger profile extraction."""
    conversation_store.ensure_indices()
    profile = memory_service.extract_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="no conversations found for user")
    return ProfileResponse(
        user_id=profile["user_id"],
        preferences=profile.get("preferences", {}),
        extracted_at=profile.get("extracted_at"),
        source_conversation_ids=profile.get("source_conversation_ids", []),
    )


@router.delete("/profile/{user_id}")
def delete_profile(user_id: str):
    """Delete user profile."""
    success = conversation_store.delete_profile(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="profile not found")
    return {"status": "deleted"}


# -- Conversation Search --


@router.get("/conversations/search", response_model=SearchResponse)
def search_conversations(
    q: str = Query(..., min_length=1, max_length=200, alias="q"),
    limit: int = Query(default=10, ge=1, le=50),
    x_user_id: str = Header(alias="X-User-ID"),
):
    """Search user's conversations using hybrid vector + BM25 retrieval."""
    results, total = memory_service.search_conversations(
        user_id=x_user_id, query=q, limit=limit
    )
    return SearchResponse(
        results=[
            SearchResultItem(
                conversation_id=r["conversation_id"],
                title=r.get("title"),
                score=r.get("score", 0),
                highlights=r.get("highlights", []),
                page_id=r.get("page_id"),
                message_count=r.get("message_count", 0),
                last_message_at=r.get("last_message_at"),
            )
            for r in results
        ],
        total=total,
    )
