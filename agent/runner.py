"""AgentRunner — LLM call + tool execution loop with streaming support."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import structlog

from providers.base import LLMProvider, LLMResponse

logger = structlog.get_logger(__name__)

# Max mid-turn injections per iteration to prevent infinite loops
_MAX_INJECTIONS_PER_TURN = 5


@dataclass
class AgentRunSpec:
    """Specification for a single agent run."""

    initial_messages: list[dict[str, Any]]
    tools: Any | None = None
    model: str = "gpt-4o"
    max_iterations: int = 30
    max_tool_result_chars: int = 16_000
    hook: Any | None = None
    error_message: str = "Sorry, an error occurred."
    workspace: str = "."
    session_key: str | None = None
    context_window_tokens: int = 128_000
    progress_callback: Callable | None = None
    stream_callback: Callable[[str], Any] | None = None
    stream_end_callback: Callable[[], Any] | None = None
    retry_wait_callback: Callable[[str], Any] | None = None
    checkpoint_callback: Callable[[dict], Any] | None = None
    injection_callback: Callable[[int], Any] | None = None
    llm_timeout_s: float = 120.0
    tool_timeout_s: float = 60.0
    goal_active_predicate: Callable | None = None
    goal_continue_message: str = ""
    ctx: Any | None = None  # RequestContext for permission-aware tool definitions


@dataclass
class AgentRunResult:
    """Result from a completed agent run."""

    final_content: str | None
    tools_used: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str = ""
    had_injections: bool = False
    usage: dict[str, int] = field(default_factory=dict)
    reasoning_content: str | None = None
    latency_ms: float = 0.0


class AgentRunner:
    """Executes the LLM conversation loop with tool execution and streaming.

    The run loop:
    1. Send messages to LLM
    2. If response has tool_calls: execute tools, inject results, go to 1
    3. If response has content (no tool_calls): final answer, return
    4. If max_iterations reached: return with warning

    Streaming:
    - LLM streaming deltas forwarded to stream_callback
    - stream_end_callback called when streaming segment ends
    - Tool calls accumulate during streaming, then execute

    Error handling:
    - LLM timeout → return partial content if any
    - Tool timeout → inject error result, continue
    - Tool exception → inject error result, continue
    - Network errors → retry with backoff (handled by provider layer)
    """

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def run(self, spec: AgentRunSpec) -> AgentRunResult:
        """Execute one complete agent turn."""
        t_start = time.time()
        messages = list(spec.initial_messages)
        tools_used: list[str] = []
        total_usage: dict[str, int] = {}
        stop_reason = "end_turn"
        had_injections = False
        reasoning_accumulated: list[str] = []

        for iteration in range(spec.max_iterations):
            # ── Mid-turn injection ──────────────────────────
            if spec.injection_callback and iteration < _MAX_INJECTIONS_PER_TURN:
                try:
                    injected = await spec.injection_callback(limit=3)
                    if injected:
                        messages.extend(injected)
                        had_injections = True
                except Exception:
                    pass

            # ── Build tool definitions ──────────────────────
            tool_defs = None
            tool_names = []
            if spec.tools:
                tool_defs = spec.tools.get_definitions(spec.ctx)
                tool_names = spec.tools.tool_names

            # ── Call LLM ────────────────────────────────────
            # NOTE: asyncio.wait_for applies to the ENTIRE call (chat or stream),
            # which includes all retry attempts from the @async_retry decorator.
            # If spec.llm_timeout_s=120 and the retry layer needs 3×60s backoff,
            # the Runner's TimeoutError will fire before retries complete.
            # This is intentional — the user gets a timeout response rather than
            # waiting 180s for all retries to exhaust.
            response = None
            try:
                if spec.stream_callback and hasattr(self.provider, "stream"):
                    response = await asyncio.wait_for(
                        self._streaming_call(
                            messages,
                            tool_defs if tool_names else None,
                            spec,
                        ),
                        timeout=spec.llm_timeout_s,
                    )
                else:
                    response = await asyncio.wait_for(
                        self.provider.chat(messages, tools=tool_defs if tool_names else None),
                        timeout=spec.llm_timeout_s,
                    )
            except asyncio.TimeoutError:
                logger.error("llm_timeout", iteration=iteration)
                stop_reason = "error"
                return AgentRunResult(
                    final_content="Sorry, the request timed out. Please try again.",
                    stop_reason=stop_reason,
                    usage=total_usage,
                    tools_used=tools_used,
                    had_injections=had_injections,
                    latency_ms=(time.time() - t_start) * 1000,
                )
            except Exception as e:
                logger.error("llm_error", iteration=iteration, error=str(e))
                stop_reason = "error"
                return AgentRunResult(
                    final_content=spec.error_message,
                    stop_reason=stop_reason,
                    usage=total_usage,
                    tools_used=tools_used,
                    had_injections=had_injections,
                    latency_ms=(time.time() - t_start) * 1000,
                )

            # ── Accumulate usage ────────────────────────────
            if response and response.usage:
                for k, v in response.usage.items():
                    try:
                        total_usage[k] = total_usage.get(k, 0) + int(v or 0)
                    except (ValueError, TypeError):
                        total_usage[k] = total_usage.get(k, v)

            # ── Accumulate reasoning ────────────────────────
            if response and response.reasoning_content:
                reasoning_accumulated.append(response.reasoning_content)

            # ── Process tool calls ──────────────────────────
            if response and response.has_tool_calls() and spec.tools:
                # Persist checkpoint before tool execution
                if spec.checkpoint_callback:
                    try:
                        await spec.checkpoint_callback(
                            {
                                "assistant_message": {
                                    "role": "assistant",
                                    "content": response.content,
                                    "tool_calls": response.tool_calls,
                                },
                                "completed_tool_results": [],
                                "pending_tool_calls": response.tool_calls,
                            }
                        )
                    except Exception:
                        pass

                # Add assistant message with tool calls
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": response.content,
                }
                if response.tool_calls:
                    assistant_msg["tool_calls"] = response.tool_calls
                messages.append(assistant_msg)

                # Execute tools
                completed_results = []
                for tc in response.tool_calls:
                    tool_name = tc.get("function", {}).get("name", "unknown")
                    try:
                        args_str = tc.get("function", {}).get("arguments", "{}")
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except (json.JSONDecodeError, TypeError):
                        args = {}

                    tools_used.append(tool_name)

                    tool_result_text = await self._execute_tool(
                        spec,
                        tool_name,
                        args,
                    )

                    # Truncate long results
                    if len(tool_result_text) > spec.max_tool_result_chars:
                        tool_result_text = (
                            tool_result_text[: spec.max_tool_result_chars] + "\n... [truncated]"
                        )

                    tool_msg: dict[str, Any] = {
                        "role": "tool",
                        "tool_call_id": tc.get("id", f"call_{iteration}"),
                        "name": tool_name,
                        "content": tool_result_text,
                    }
                    messages.append(tool_msg)
                    completed_results.append(tool_msg)

                # Update checkpoint
                if spec.checkpoint_callback:
                    try:
                        await spec.checkpoint_callback(
                            {
                                "assistant_message": assistant_msg,
                                "completed_tool_results": completed_results,
                                "pending_tool_calls": [],
                            }
                        )
                    except Exception:
                        pass

                if spec.stream_end_callback:
                    try:
                        await spec.stream_end_callback()
                    except Exception:
                        pass

                continue  # Next LLM iteration

            # ── Final response ──────────────────────────────
            if response and response.content:
                messages.append({"role": "assistant", "content": response.content})

            if spec.stream_end_callback:
                try:
                    await spec.stream_end_callback()
                except Exception:
                    pass

            stop_reason = response.stop_reason if response else "end_turn"
            return AgentRunResult(
                final_content=response.content if response else None,
                tools_used=tools_used,
                messages=messages,
                stop_reason=stop_reason,
                had_injections=had_injections,
                usage=total_usage,
                reasoning_content="\n".join(reasoning_accumulated)
                if reasoning_accumulated
                else None,
                latency_ms=(time.time() - t_start) * 1000,
            )

        # ── Max iterations reached ──────────────────────────
        logger.warning("max_iterations_reached", max_iterations=spec.max_iterations)
        return AgentRunResult(
            final_content=None,
            tools_used=tools_used,
            messages=messages,
            stop_reason="max_iterations",
            had_injections=had_injections,
            usage=total_usage,
            latency_ms=(time.time() - t_start) * 1000,
        )

    async def _execute_tool(self, spec: AgentRunSpec, name: str, args: dict) -> str:
        """Execute a single tool with timeout and error handling."""
        try:
            result = await asyncio.wait_for(
                spec.tools.execute(name, args),
                timeout=spec.tool_timeout_s,
            )
            return result if isinstance(result, str) else str(result)
        except asyncio.TimeoutError:
            logger.warning("tool_timeout", tool=name)
            return f"Error: tool '{name}' timed out after {spec.tool_timeout_s}s"
        except Exception as e:
            logger.error("tool_execution_error", tool=name, error=str(e))
            return f"Error executing '{name}': {e}"

    async def _streaming_call(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        spec: AgentRunSpec,
    ) -> LLMResponse:
        """Execute a streaming LLM call, forwarding deltas to callback.

        Accumulates the full response from stream chunks, including:
        - Text content (forwarded as deltas)
        - Tool call deltas (accumulated for final tool call list)
        - Reasoning content (accumulated separately)
        """
        content_parts: list[str] = []
        tool_call_accumulator: dict[int, dict] = {}
        reasoning_parts: list[str] = []
        usage_info: dict = {}
        finish_reason = "end_turn"

        try:
            async for chunk in self.provider.stream(messages, tools=tools):
                # Content delta
                if chunk.content:
                    content_parts.append(chunk.content)
                    if spec.stream_callback:
                        try:
                            result = spec.stream_callback(chunk.content)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:
                            pass

                # Reasoning delta
                if chunk.reasoning_content:
                    reasoning_parts.append(chunk.reasoning_content)

                # Tool call delta
                if chunk.tool_call_delta:
                    idx = chunk.tool_call_delta.get("index", 0)
                    if idx not in tool_call_accumulator:
                        tool_call_accumulator[idx] = {
                            "id": chunk.tool_call_delta.get("id", ""),
                            "function": {"name": "", "arguments": ""},
                        }
                    acc = tool_call_accumulator[idx]
                    if "id" in chunk.tool_call_delta:
                        acc["id"] = chunk.tool_call_delta["id"] or acc["id"]
                    func = chunk.tool_call_delta.get("function", {})
                    if func.get("name"):
                        acc["function"]["name"] += func["name"]
                    if func.get("arguments"):
                        acc["function"]["arguments"] += func["arguments"]

                # Usage info
                if chunk.usage:
                    usage_info.update(chunk.usage)

                # Finish reason — pass through actual reason for observability
                if chunk.finish_reason:
                    if "tool" in chunk.finish_reason:
                        finish_reason = "tool_calls"
                    elif chunk.finish_reason in ("stop", "end_turn", "length", "content_filter"):
                        finish_reason = chunk.finish_reason
                    else:
                        finish_reason = "end_turn"

        except asyncio.TimeoutError:
            logger.warning("stream_timeout")
            finish_reason = "error"
        except Exception as e:
            logger.error("stream_error", error=str(e))
            finish_reason = "error"

        # Build tool calls from accumulator
        tool_calls = [
            {"id": acc["id"], "function": acc["function"]}
            for acc in tool_call_accumulator.values()
            if acc["function"]["name"]
        ]

        content = "".join(content_parts) if content_parts else None
        reasoning = "".join(reasoning_parts) if reasoning_parts else None

        return LLMResponse(
            content=content,
            stop_reason=finish_reason,
            tool_calls=tool_calls,
            usage=usage_info,
            reasoning_content=reasoning,
        )
