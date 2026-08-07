from __future__ import annotations

import json
import time
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agent.state import AgentTraceStep, GenerationSource
from ..schemas.page_dsl import GenerationRequestDraft, PageDSL
from ..services.page_store import PageStore, PageStoreError, TERMINAL_STATUSES
from ..worker.tasks import generate_page_task, revise_page_task


router = APIRouter(prefix="/api", tags=["pages"])
page_store = PageStore()


class PageTaskResponse(BaseModel):
    request_id: str
    status: str
    celery_task_id: str | None = None


class RevisePageRequest(BaseModel):
    page_id: str = Field(..., min_length=1)
    instruction: str = Field(..., min_length=8, max_length=500)


class StoredPageResponse(BaseModel):
    page_id: str
    request_id: str | None = None
    generation_source: GenerationSource | None = None
    agent_trace: list[AgentTraceStep] = Field(default_factory=list)
    page_dsl: PageDSL


class PageResultResponse(BaseModel):
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


class ErrorResponse(BaseModel):
    detail: str = Field(..., min_length=1)


_page_keywords = (
    # Generation
    "生成", "创建", "制作", "设计", "落地页", "页面", "推广页", "做一个", "建一个",
    "写一个", "帮我做", "帮我生成", "给我做",
    # Revision
    "改", "修改", "换", "换成", "调整", "变成", "移除", "删除", "添加", "增加",
    "替换", "变更", "变小", "变大", "颜色", "字体", "布局", "标题", "内容",
    "样式", "风格", "色调", "按钮", "文案", "图片", "背景", "模块", "组件",
    "商务", "科技", "简洁", "大气", "高端", "年轻", "活泼", "正式", "温馨",
)


def _looks_like_page_instruction(text: str) -> bool:
    """Check if the text appears to be a page-related instruction."""
    return any(kw in text for kw in _page_keywords)


@router.post(
    "/agent/page/generate",
    response_model=PageTaskResponse,
    responses={500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def generate_page(payload: GenerationRequestDraft) -> PageTaskResponse:
    """Create a generation request and dispatch it to Celery."""
    request_id: str | None = None
    try:
        request_id = page_store.create_generation_request(payload)
        async_result = generate_page_task.delay(request_id)
        page_store.set_celery_task_id(request_id, async_result.id)
    except PageStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        if request_id:
            try:
                page_store.fail_request(request_id, str(exc), error_code="CELERY_DISPATCH_FAILED")
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"failed to dispatch generation task: {exc}",
        ) from exc

    return PageTaskResponse(
        request_id=request_id,
        status="PENDING",
        celery_task_id=async_result.id,
    )


@router.post(
    "/agent/page/revise",
    response_model=PageTaskResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def revise_page(payload: RevisePageRequest) -> PageTaskResponse:
    """Create a revision request and dispatch it to Celery."""
    if not _looks_like_page_instruction(payload.instruction):
        raise HTTPException(
            status_code=400,
            detail="输入的修改指令似乎与页面修改无关，请输入与页面设计相关的指令，如：改标题、换配色、调整布局等。",
        )

    request_id: str | None = None
    try:
        stored_page = page_store.load_page(payload.page_id)
        request_id = page_store.create_revision_request(
            base_page_id=payload.page_id,
            instruction=payload.instruction,
            base_page=stored_page.page_dsl,
        )
        async_result = revise_page_task.delay(request_id)
        page_store.set_celery_task_id(request_id, async_result.id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"page '{payload.page_id}' not found") from exc
    except PageStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        if request_id:
            try:
                page_store.fail_request(request_id, str(exc), error_code="CELERY_DISPATCH_FAILED")
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"failed to dispatch revision task: {exc}",
        ) from exc

    return PageTaskResponse(
        request_id=request_id,
        status="PENDING",
        celery_task_id=async_result.id,
    )


@router.get(
    "/pages/{page_id}",
    response_model=StoredPageResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def get_page(page_id: str) -> StoredPageResponse:
    try:
        stored_page = page_store.load_page(page_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"page '{page_id}' not found") from exc
    except PageStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return StoredPageResponse(
        page_id=page_id,
        request_id=stored_page.request_id,
        generation_source=stored_page.generation_source,
        agent_trace=stored_page.agent_trace,
        page_dsl=stored_page.page_dsl,
    )


@router.get(
    "/agent/page/result",
    response_model=PageResultResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def get_generation_result(request_id: str = Query(..., min_length=1)) -> PageResultResponse:
    """Return the current persisted result for a generation request."""
    try:
        result = page_store.load_generation_result(request_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"request '{request_id}' not found") from exc
    except PageStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return PageResultResponse(**result.model_dump())


@router.get(
    "/agent/page/stream",
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def stream_generation_progress(request_id: str = Query(..., min_length=1)) -> StreamingResponse:
    """Stream generation progress events using DB polling SSE."""
    try:
        page_store.load_generation_result(request_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"request '{request_id}' not found") from exc
    except PageStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return StreamingResponse(
        _build_sse_events(request_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


def _build_sse_events(request_id: str) -> Iterator[str]:
    last_event_id = 0
    yield _sse("request_observed", {"request_id": request_id})

    while True:
        for event in page_store.list_task_events(request_id, after_id=last_event_id):
            last_event_id = event.id
            yield _sse(
                event.action,
                {
                    "event_id": event.id,
                    "request_id": request_id,
                    "task_id": event.task_id,
                    "status": event.status,
                    "duration_ms": event.cost_ms,
                    "message": event.result_summary,
                    "error_code": event.error_code,
                    "created_at": event.created_at,
                },
            )

        result = page_store.load_generation_result(request_id)
        if result.status in TERMINAL_STATUSES:
            final_event = "preview_ready" if result.status == "SUCCESS" else "failed"
            yield _sse(
                final_event,
                {
                    "request_id": request_id,
                    "status": result.status,
                    "page_id": result.page_id,
                    "preview_url": result.preview_url,
                    "error_code": result.error_code,
                    "error_message": result.error_message,
                },
            )
            break

        yield _sse("heartbeat", {"request_id": request_id, "status": result.status})
        time.sleep(1)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
