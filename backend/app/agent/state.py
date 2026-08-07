from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..schemas.page_dsl import GenerationRequestDraft, PageDSL


GenerationSource = Literal["llm", "llm_normalized", "fallback", "revision"]
TaskStatus = Literal["pending", "success", "failed", "skipped"]
TraceStatus = Literal["success", "failed"]


class AgentTask(BaseModel):
    task_id: str
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = "pending"


class ReflectionResult(BaseModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)


class AgentTraceStep(BaseModel):
    node: str
    status: TraceStatus
    duration_ms: float
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextSource(BaseModel):
    source_type: str
    source_id: str
    title: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextPackage(BaseModel):
    request_context: dict[str, Any] = Field(default_factory=dict)
    session_context: dict[str, Any] = Field(default_factory=dict)
    object_context: dict[str, Any] = Field(default_factory=dict)
    knowledge_context: dict[str, Any] = Field(default_factory=dict)
    tool_context: dict[str, Any] = Field(default_factory=dict)
    runtime_context: dict[str, Any] = Field(default_factory=dict)
    context_sources: list[ContextSource] = Field(default_factory=list)
    token_budget: dict[str, int] = Field(default_factory=dict)


class PageGenerationState(BaseModel):
    conversation_id: str | None = None
    request_id: str | None = None
    request: GenerationRequestDraft
    base_page_dsl: PageDSL | None = None
    revision_instruction: str | None = None
    context_package: ContextPackage | None = None
    safety_issues: list[dict[str, Any]] = Field(default_factory=list)
    parsed_intent: dict[str, Any] = Field(default_factory=dict)
    task_plan: list[AgentTask] = Field(default_factory=list)
    tool_results: dict[str, Any] = Field(default_factory=dict)
    reflection_result: ReflectionResult | None = None
    page_dsl: PageDSL | None = None
    generation_source: GenerationSource | None = None
    error_info: list[str] = Field(default_factory=list)
    trace: list[AgentTraceStep] = Field(default_factory=list)


class PageGenerationAgentResult(BaseModel):
    page_dsl: PageDSL
    generation_source: GenerationSource
    agent_trace: list[AgentTraceStep]
