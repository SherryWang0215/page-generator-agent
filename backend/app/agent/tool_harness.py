from __future__ import annotations

import logging
from collections.abc import Callable
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field

from ..config import settings
from ..services.audit_service import audit_event
from .tools.page_tools import (
    generate_cta_tool,
    generate_features_tool,
    generate_hero_tool,
    generate_testimonials_tool,
    rewrite_cta_tool,
    rewrite_features_tool,
    rewrite_hero_tool,
    select_layout_tool,
)


logger = logging.getLogger(__name__)

ToolCallable = Callable[..., Any]


class ToolSpec(BaseModel):
    name: str
    description: str
    required_params: list[str] = Field(default_factory=list)
    timeout_ms: int = 3000
    retry_count: int = 0
    permission: str = "read_write_page_dsl"


class ToolInvocationResult(BaseModel):
    tool_name: str
    success: bool
    duration_ms: float
    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegisteredTool(BaseModel):
    spec: ToolSpec
    handler: ToolCallable

    model_config = {"arbitrary_types_allowed": True}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, spec: ToolSpec, handler: ToolCallable) -> None:
        self._tools[spec.name] = RegisteredTool(spec=spec, handler=handler)

    def get(self, name: str) -> RegisteredTool:
        if name not in self._tools:
            raise KeyError(f"tool '{name}' is not registered")
        return self._tools[name]

    def describe(self) -> list[dict[str, Any]]:
        return [tool.spec.model_dump() for tool in self._tools.values()]


tool_registry = ToolRegistry()


def invoke_tool(tool_name: str, params: dict[str, Any], **kwargs: Any) -> ToolInvocationResult:
    """Invoke a registered tool with validation and observability metadata."""
    tool = tool_registry.get(tool_name)
    started_at = perf_counter()
    try:
        _enforce_permission(tool.spec)
        _validate_params(tool.spec, params)
        result = tool.handler(params, **kwargs)
        duration_ms = _elapsed_ms(started_at)
        logger.info(
            "Tool invocation succeeded | tool=%s | duration_ms=%.2f",
            tool_name,
            duration_ms,
        )
        invocation_result = ToolInvocationResult(
            tool_name=tool_name,
            success=True,
            duration_ms=duration_ms,
            result=result,
            metadata={
                "timeout_ms": tool.spec.timeout_ms,
                "permission": tool.spec.permission,
                "retry_count": tool.spec.retry_count,
            },
        )
        audit_tool_invocation(invocation_result, params)
        return invocation_result
    except Exception as exc:
        duration_ms = _elapsed_ms(started_at)
        logger.warning(
            "Tool invocation failed | tool=%s | duration_ms=%.2f | reason=%s",
            tool_name,
            duration_ms,
            exc,
        )
        invocation_result = ToolInvocationResult(
            tool_name=tool_name,
            success=False,
            duration_ms=duration_ms,
            error=str(exc),
            metadata={
                "timeout_ms": tool.spec.timeout_ms,
                "permission": tool.spec.permission,
                "retry_count": tool.spec.retry_count,
            },
        )
        audit_tool_invocation(invocation_result, params)
        return invocation_result


def tool_result_payload(invocation: ToolInvocationResult, result_type: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "success": invocation.success,
        "tool_name": invocation.tool_name,
        "result_type": result_type,
        "duration_ms": invocation.duration_ms,
        "metadata": invocation.metadata,
    }
    if invocation.success:
        payload["result"] = _serialize_result(invocation.result)
    else:
        payload["reason"] = invocation.error
    return payload


def _validate_params(spec: ToolSpec, params: dict[str, Any]) -> None:
    missing = [name for name in spec.required_params if not params.get(name)]
    if missing:
        raise ValueError(f"missing required tool params: {', '.join(missing)}")


def _enforce_permission(spec: ToolSpec) -> None:
    if not settings.tool_permissions_enabled:
        return
    if spec.permission not in settings.allowed_tool_permission_set:
        raise PermissionError(f"tool permission denied: {spec.permission}")


def audit_tool_invocation(invocation: ToolInvocationResult, params: dict[str, Any]) -> None:
    audit_event(
        "tool_invocation",
        {
            "tool_name": invocation.tool_name,
            "success": invocation.success,
            "duration_ms": invocation.duration_ms,
            "permission": invocation.metadata.get("permission"),
            "error": invocation.error,
            "params_keys": sorted(params.keys()),
        },
    )


def _serialize_result(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump()
    return result


def _elapsed_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 2)


def _register_default_tools() -> None:
    tool_registry.register(
        ToolSpec(
            name="select_layout",
            description="Select a PageDSL layout template for the requested page type.",
            required_params=["page_type"],
        ),
        select_layout_tool,
    )
    tool_registry.register(
        ToolSpec(
            name="generate_hero",
            description="Generate a hero_banner section.",
            required_params=["subject"],
        ),
        generate_hero_tool,
    )
    tool_registry.register(
        ToolSpec(
            name="generate_features",
            description="Generate a feature_cards section.",
            required_params=["subject"],
        ),
        generate_features_tool,
    )
    tool_registry.register(
        ToolSpec(
            name="generate_cta",
            description="Generate a cta_button section.",
            required_params=["subject"],
        ),
        generate_cta_tool,
    )
    tool_registry.register(
        ToolSpec(
            name="rewrite_hero",
            description="Rewrite or create a hero_banner section based on revision instruction.",
            required_params=["subject", "instruction"],
        ),
        rewrite_hero_tool,
    )
    tool_registry.register(
        ToolSpec(
            name="rewrite_features",
            description="Rewrite or create a feature_cards section based on revision instruction.",
            required_params=["subject", "instruction"],
        ),
        rewrite_features_tool,
    )
    tool_registry.register(
        ToolSpec(
            name="rewrite_cta",
            description="Rewrite or create a cta_button section based on revision instruction.",
            required_params=["subject", "instruction"],
        ),
        rewrite_cta_tool,
    )
    tool_registry.register(
        ToolSpec(
            name="generate_testimonials",
            description="Generate a testimonials section.",
            required_params=["subject"],
        ),
        generate_testimonials_tool,
    )


_register_default_tools()
