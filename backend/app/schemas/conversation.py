from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    page_id: str | None = None


class ConversationResponse(BaseModel):
    conversation_id: str
    user_id: str
    page_id: str | None = None
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    status: str = "active"


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]
    total: int


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class MessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    role: str
    content: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    total: int


class ConversationDetailResponse(BaseModel):
    conversation: ConversationResponse
    messages: list[MessageResponse]


class SendMessageResponse(BaseModel):
    message_id: str
    content: str
    page_id: str | None = None
    pages: list[dict] = Field(default_factory=list)
    request_id: str | None = None
    status: str | None = None
    celery_task_id: str | None = None
    intent: str | None = None


# -- User Profile --

class ProfileResponse(BaseModel):
    user_id: str
    preferences: dict = Field(default_factory=dict)
    extracted_at: datetime | None = None
    source_conversation_ids: list[str] = Field(default_factory=list)


# -- Conversation Search --

class SearchResultItem(BaseModel):
    conversation_id: str
    title: str | None = None
    score: float
    highlights: list[str] = Field(default_factory=list)
    page_id: str | None = None
    message_count: int = 0
    last_message_at: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int
