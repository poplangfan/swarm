"""Subagent system — for delegating complex tasks to independent sub-agents."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from providers.base import LLMProvider

logger = structlog.get_logger(__name__)


@dataclass
class SubagentSpec:
    """Specification for spawning a subagent task."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    parent_trace_id: str = ""
    user_token: str | None = None
    max_iterations: int = 15
    timeout: float = 300.0
    tools: Any = None


@dataclass
class SubagentResult:
    """Result from a completed subagent task."""

    task_id: str
    content: str
    success: bool = True
    error: str | None = None
    tools_used: list[str] = field(default_factory=list)


class SubagentManager:
    """Manages the lifecycle of subagent tasks spawned by the main AgentLoop.

    Constraints:
    - Max concurrent subagents per manager (default: 3)
    - Subagents cannot recursively spawn sub-subagents
    - Subagent sessions are ephemeral (not persisted)
    - Each subagent has a timeout (default: 300s)
    """

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path = Path("."),
        max_concurrent: int = 3,
        timeout: float = 300.0,
    ):
        self.provider = provider
        self.workspace = workspace
        self._max_concurrent = max_concurrent
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active: dict[str, asyncio.Task] = {}

    @property
    def active_count(self) -> int:
        return len([t for t in self._active.values() if not t.done()])

    async def spawn(self, spec: SubagentSpec) -> SubagentResult:
        """Spawn a subagent and wait for its result.

        The subagent runs independently with its own LLM conversation.
        The result is returned when the subagent completes or times out.
        """
        async with self._semaphore:
            task_id = spec.task_id
            task = asyncio.create_task(self._run_subagent(spec))
            self._active[task_id] = task
            try:
                result = await asyncio.wait_for(task, timeout=spec.timeout)
                return result
            except asyncio.TimeoutError:
                logger.warning("subagent_timeout", task_id=task_id)
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                return SubagentResult(
                    task_id=task_id,
                    content="Subagent task timed out.",
                    success=False,
                    error="timeout",
                )
            except Exception as e:
                logger.error("subagent_error", task_id=task_id, error=str(e))
                return SubagentResult(
                    task_id=task_id,
                    content=f"Subagent failed: {e}",
                    success=False,
                    error=str(e),
                )
            finally:
                self._active.pop(task_id, None)

    async def spawn_parallel(self, specs: list[SubagentSpec]) -> list[SubagentResult]:
        """Spawn multiple subagents in parallel and collect results."""
        tasks = [self.spawn(spec) for spec in specs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                out.append(
                    SubagentResult(
                        task_id=specs[i].task_id if i < len(specs) else "unknown",
                        content=f"Subagent crashed: {r}",
                        success=False,
                        error=str(r),
                    )
                )
            else:
                out.append(r)
        return out

    async def cancel_by_session(self, session_key: str) -> int:
        """Cancel all subagents associated with a session. Returns count cancelled."""
        cancelled = 0
        for task_id, task in list(self._active.items()):
            if session_key in task_id and not task.done():
                task.cancel()
                cancelled += 1
        return cancelled

    async def cancel_all(self) -> int:
        """Cancel all active subagents. Returns count cancelled."""
        cancelled = 0
        for task in list(self._active.values()):
            if not task.done():
                task.cancel()
                cancelled += 1
        for task in list(self._active.values()):
            with suppress(asyncio.CancelledError, Exception):
                await task
        self._active.clear()
        return cancelled

    async def _run_subagent(self, spec: SubagentSpec) -> SubagentResult:
        """Internal: execute a single subagent task."""
        from agent.runner import AgentRunner, AgentRunSpec

        runner = AgentRunner(self.provider)

        system_prompt = f"""You are a specialized sub-agent. Your task is:
{spec.description}

Rules:
- Focus ONLY on the assigned task.
- Use tools when helpful.
- Return a clear, concise result.
- Do NOT spawn additional sub-agents.
- If you cannot complete the task, explain why."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Please complete this task: {spec.description}"},
        ]

        run_spec = AgentRunSpec(
            initial_messages=messages,
            tools=spec.tools,
            model=self.provider.model,
            max_iterations=spec.max_iterations,
            max_tool_result_chars=8_000,
            llm_timeout_s=min(spec.timeout / 2, 120.0),
        )

        result = await runner.run(run_spec)
        tools_used = list(result.tools_used)

        return SubagentResult(
            task_id=spec.task_id,
            content=result.final_content or "No result produced.",
            success=result.stop_reason not in ("error", "max_iterations"),
            error=None if result.stop_reason not in ("error",) else "LLM error",
            tools_used=tools_used,
        )

    def set_provider(self, provider: LLMProvider, model: str | None = None) -> None:
        """Update the provider used by subagents."""
        self.provider = provider
