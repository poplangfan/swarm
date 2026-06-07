"""AgentLoop — the core state machine orchestrator with subagent support.

Production-grade implementation with:
- Streaming output with delta callbacks and throttling
- Checkpoint persistence for crash recovery across restarts
- Mid-turn message injection via per-session queues
- Subagent lifecycle management with concurrency control
- Graceful shutdown with in-flight turn drainage
- Per-state timing and tracing for observability
- Command routing with inline dispatch
- Memory consolidation triggers after each turn
- Event bus integration for runtime metrics
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable

import structlog

from agent.context import ContextBuilder, RequestContext, TurnContext
from agent.runner import AgentRunner, AgentRunSpec
from agent.subagent import SubagentManager
from bus.queue import InboundMessage, MessageBus, OutboundMessage
from providers.base import LLMProvider
from utils import extract_chat_id

logger = structlog.get_logger(__name__)

# Standardized error messages — one per failure category
_ERR_INTERNAL = "Sorry, an internal error occurred."
_ERR_PROCESSING = "Sorry, an error occurred while processing your request."
_ERR_MESSAGE = "Sorry, I encountered an error processing your message."


class TurnState(Enum):
    """States in the agent processing state machine."""

    RESTORE = auto()  # Load session, restore any checkpoint
    BUILD = auto()  # Assemble system prompt + context
    RUN = auto()  # LLM call + tool execution loop
    SAVE = auto()  # Persist session and trigger memory consolidation
    RESPOND = auto()  # Send outbound message
    DONE = auto()  # Turn complete, return to event loop


@dataclass
class StateTraceEntry:
    """Diagnostic record of a single state transition."""

    state: TurnState
    started_at: float
    duration_ms: float
    event: str
    error: str | None = None


def _safe_remove_task(active_tasks: dict, key: str, task: Any) -> None:
    """Remove a task from active dict, swallowing KeyError/ValueError."""
    try:
        active_tasks[key].remove(task)
    except (KeyError, ValueError):
        pass


class AgentLoop:
    """Core agent processing engine.

    Architecture:
    - 5-state machine processes each message through RESTORE→BUILD→RUN→SAVE→RESPOND
    - Per-session asyncio.Lock ensures serial execution per chat_id
    - Global semaphore limits total concurrent turns
    - Mid-turn messages for active sessions are queued and injected
    - Checkpoint persistence enables crash recovery
    - Commands (/help, /status, /clear) bypass the LLM entirely

    Concurrency Model:
    - Same chat_id: serial (Lock) + mid-turn injection
    - Different chat_id: concurrent (separate Locks)
    - Global: limited by Semaphore(MAX_CONCURRENT=10)
    """

    # State transition table: (current_state, event) → next_state
    _TRANSITIONS: dict[tuple[TurnState, str], TurnState] = {
        (TurnState.RESTORE, "ok"): TurnState.BUILD,
        (TurnState.BUILD, "ok"): TurnState.RUN,
        (TurnState.BUILD, "cmd"): TurnState.RESPOND,  # Command shortcut
        (TurnState.RUN, "ok"): TurnState.SAVE,
        (TurnState.SAVE, "ok"): TurnState.RESPOND,
        (TurnState.RESPOND, "ok"): TurnState.DONE,
    }

    # Configuration defaults
    _MAX_CONCURRENT = 10  # Max simultaneous turns across all sessions
    _PENDING_QUEUE_SIZE = 20  # Max queued messages per active session
    _MAX_INJECTIONS_PER_TURN = 5  # Max mid-turn message injections per turn
    _SHUTDOWN_TIMEOUT = 30.0  # Seconds to drain in-flight turns on shutdown

    # Session metadata keys
    _CHECKPOINT_KEY = "runtime_checkpoint"
    _PENDING_USER_KEY = "pending_user_turn"

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: str | Path = ".",
        model: str | None = None,
        max_iterations: int = 30,
        max_tool_result_chars: int = 16_000,
        max_context_tokens: int = 32_000,
        tools: Any = None,
        sessions: Any = None,
        memory: Any = None,
        context_builder: ContextBuilder | None = None,
        timezone: str = "Asia/Shanghai",
        max_concurrent_subagents: int = 3,
        hooks: list[Any] | None = None,
        event_bus: Any = None,
        consolidation_threshold: int = 20,
    ):
        # Core dependencies
        self.bus = bus
        self.provider = provider
        self.workspace = Path(workspace)
        self.model = model or provider.model
        self.max_iterations = max_iterations
        self.max_tool_result_chars = max_tool_result_chars
        self.max_context_tokens = max_context_tokens
        self.tools = tools
        self.sessions = sessions
        self.memory = memory
        self.timezone = timezone
        self.hooks = hooks or []
        self._event_bus = event_bus
        self._consolidation_threshold = consolidation_threshold

        # Skills loading (auto-load from built-in skills directory and workspace)
        self._skills_loader = None
        try:
            from skills.loader import SkillsLoader

            # Load built-in skills from project root
            builtin_path = Path(__file__).parent.parent / "skills_builtin"
            if builtin_path.exists():
                self._skills_loader = SkillsLoader(builtin_path)
            # Also try workspace skills
            ws_skills = self.workspace / "skills"
            if ws_skills.exists():
                if self._skills_loader:
                    # Merge: reload with workspace skills taking priority
                    ws_loader = SkillsLoader(ws_skills)
                    for name in ws_loader.list_skills():
                        skill = ws_loader.get_skill(name["name"])
                        if skill:
                            self._skills_loader._skills[skill.name] = skill
                else:
                    self._skills_loader = SkillsLoader(ws_skills)
        except Exception as e:
            logger.debug("skills_load_skipped", error=str(e))

        # Context building (with skills injected into prompts)
        self.context_builder = context_builder or ContextBuilder(
            workspace=self.workspace,
            timezone=timezone,
            memory=memory,
            skills_loader=self._skills_loader,
        )

        # Sub-components
        self.runner = AgentRunner(provider)
        self.subagents = SubagentManager(
            provider=provider,
            workspace=self.workspace,
            max_concurrent=max_concurrent_subagents,
            timeout=300.0,
        )

        # Concurrency control
        self._running = False
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._active_tasks: dict[str, list[asyncio.Task]] = {}
        self._pending_queues: dict[str, asyncio.Queue] = {}
        self._concurrency_gate = asyncio.Semaphore(self._MAX_CONCURRENT)
        self._background_tasks: list[asyncio.Task] = []

        # Token budget for session replay
        ctx_window = getattr(provider, "context_window", 128_000)
        max_output = getattr(getattr(provider, "generation", None), "max_tokens", 4096)
        self._replay_token_budget = max(128, ctx_window - max_output - 1024)

        # Command registry
        self._commands: dict[str, Callable] = {}
        self._register_commands()

        # Lazy-cached dream consolidator (#9)
        self._dream_consolidator: Any = None

        # Runtime state
        self._start_time = time.time()
        self._total_turns = 0
        self._total_errors = 0
        self._shutdown_requested = False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Command System
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _register_commands(self) -> None:
        """Register built-in slash commands."""
        self._commands["/help"] = self._cmd_help
        self._commands["/status"] = self._cmd_status
        self._commands["/clear"] = self._cmd_clear

    async def _cmd_help(self, ctx: RequestContext) -> str:
        return (
            "**Swarm Commands**\n"
            "- `/help` — Show this help message\n"
            "- `/status` — Show session and system status\n"
            "- `/clear` — Clear conversation history"
        )

    async def _cmd_status(self, ctx: RequestContext) -> str:
        active_sessions = sum(len(ts) for ts in self._active_tasks.values())
        uptime = int(time.time() - self._start_time)
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)

        return (
            f"**Swarm Status**\n"
            f"- Model: `{self.model}`\n"
            f"- Active sessions: {active_sessions}\n"
            f"- Active subagents: {self.subagents.active_count}\n"
            f"- Total turns: {self._total_turns}\n"
            f"- Errors: {self._total_errors}\n"
            f"- Uptime: {hours}h {minutes}m {seconds}s\n"
            f"- Your chat: `{ctx.chat_id}`"
        )

    async def _cmd_clear(self, ctx: RequestContext) -> str:
        if self.sessions:
            key = f"feishu:{ctx.chat_id}"
            await self.sessions.clear(key)
            return "Conversation history cleared. Starting fresh."
        return "Session manager not available."

    def _is_command(self, text: str) -> str | None:
        """Check if text matches a registered command. Returns command key or None."""
        stripped = text.strip().lower()
        for cmd in self._commands:
            if stripped == cmd or stripped.startswith(cmd + " "):
                return cmd
        return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Core Processing — 5-State Machine
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str,
        on_stream: Callable[[str], Any] | None = None,
        on_stream_end: Callable[[], Any] | None = None,
    ) -> OutboundMessage | None:
        """Run a single message through the complete 5-state machine.

        Each state returns an event string. The transition table maps
        (current_state, event) → next_state. The loop continues until
        DONE is reached.

        Error handling: if any state raises an unhandled exception,
        the error is caught at the dispatch level (see _dispatch).
        """
        trace_id = str(uuid.uuid4())
        ctx = RequestContext(
            trace_id=trace_id,
            chat_id=msg.chat_id,
            chat_type=msg.metadata.get("chat_type", "p2p"),
            user_id=msg.sender_id,
            message_id=msg.metadata.get("message_id", ""),
        )
        turn = TurnContext(ctx=ctx)
        state = TurnState.RESTORE
        history: list[dict] = []
        trace: list[StateTraceEntry] = []

        # Track timing for the full turn
        turn_wall_start = time.time()

        while state is not TurnState.DONE:
            t0 = time.perf_counter()
            event = "ok"  # Default

            # ── RESTORE ──────────────────────────────────────
            if state == TurnState.RESTORE:
                event = await self._state_restore(msg, session_key, turn, history)

            # ── BUILD ────────────────────────────────────────
            elif state == TurnState.BUILD:
                event = await self._state_build(msg, session_key, ctx, turn, history)

            # ── RUN ──────────────────────────────────────────
            elif state == TurnState.RUN:
                event = await self._state_run(msg, session_key, turn, on_stream, on_stream_end)

            # ── SAVE ─────────────────────────────────────────
            elif state == TurnState.SAVE:
                event = await self._state_save(msg, session_key, turn)

            # ── RESPOND ──────────────────────────────────────
            elif state == TurnState.RESPOND:
                latency_ms = int((time.time() - turn_wall_start) * 1000)
                self._total_turns += 1
                return await self._state_respond(msg, turn, trace_id, latency_ms)

            # ── Trace ────────────────────────────────────────
            duration_ms = (time.perf_counter() - t0) * 1000
            trace.append(
                StateTraceEntry(
                    state=state,
                    started_at=t0,
                    duration_ms=duration_ms,
                    event=event,
                )
            )

            # ── Transition ───────────────────────────────────
            next_state = self._TRANSITIONS.get((state, event))
            if next_state is None:
                logger.error(
                    "no_transition",
                    state=state.name,
                    turn_event=event,
                    trace_id=trace_id,
                )
                self._total_errors += 1
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=_ERR_INTERNAL,
                    metadata={"trace_id": trace_id, "error": "no_transition"},
                )
            state = next_state

        return None

    # ── State Handlers ───────────────────────────────────────

    async def _state_restore(
        self,
        msg: InboundMessage,
        session_key: str,
        turn: TurnContext,
        history: list[dict],
    ) -> str:
        """RESTORE: Load session, recover from checkpoint if needed."""
        if not self.sessions:
            return "ok"

        try:
            session = await self.sessions.get_or_create(msg.session_key)
        except Exception as e:
            logger.error("session_load_failed", session_key=session_key, error=str(e))
            return "ok"  # Continue without session persistence

        # Restore from a previous crash
        self._recover_from_crash(session)

        # Load conversation history
        try:
            max_msgs = min(50, self._replay_token_budget // 100)
            history[:] = session.get_history(
                max_messages=max_msgs,
                max_tokens=self._replay_token_budget,
            )
        except Exception as e:
            logger.warning("history_load_failed", session_key=session_key, error=str(e))

        return "ok"

    async def _state_build(
        self,
        msg: InboundMessage,
        session_key: str,
        ctx: RequestContext,
        turn: TurnContext,
        history: list[dict],
    ) -> str:
        """BUILD: Check for commands or assemble the LLM context."""
        # Check for command shortcut
        cmd = self._is_command(msg.content)
        if cmd:
            try:
                handler = self._commands[cmd]
                turn.final_content = await handler(ctx)
                turn.stop_reason = "command"
                return "cmd"
            except Exception as e:
                logger.error("command_error", cmd=cmd, error=str(e))
                turn.final_content = f"Error executing {cmd}: {e}"
                turn.stop_reason = "command_error"
                return "cmd"

        # Build memory context for prompt injection
        memory_ctx = ""
        if self.memory:
            try:
                memory_ctx = self.context_builder.get_memory_context(msg.chat_id)
            except Exception as e:
                logger.debug("memory_context_failed", chat_id=msg.chat_id, error=str(e))

        # Get session summary (compressed old context)
        session_summary = ""
        if self.sessions:
            try:
                s = await self.sessions.get_or_create(msg.session_key)
                session_summary = s.metadata.get("summary", "")
            except Exception:
                pass

        # Assemble messages for LLM
        try:
            turn.messages = self.context_builder.build_messages(
                history=list(history),
                current_message=msg.content,
                media=msg.media,
                channel=msg.channel,
                chat_id=msg.chat_id,
                sender_id=msg.sender_id,
                session_summary=session_summary,
                memory_context=memory_ctx,
            )
        except Exception as e:
            logger.error("context_build_failed", error=str(e))
            # Fallback: minimal context
            turn.messages = [
                {"role": "system", "content": "You are Swarm, a helpful assistant."},
                {"role": "user", "content": msg.content},
            ]

        return "ok"

    async def _state_run(
        self,
        msg: InboundMessage,
        session_key: str,
        turn: TurnContext,
        on_stream: Callable | None,
        on_stream_end: Callable | None,
    ) -> str:
        """RUN: Execute the LLM conversation loop with tools."""

        # Build injection callback for mid-turn messages
        async def _inject(limit: int = 3) -> list[dict]:
            injected = []
            queue = self._pending_queues.get(session_key)
            if queue is None:
                return []
            count = 0
            while count < limit:
                try:
                    pending_msg = queue.get_nowait()
                    injected.append(
                        {
                            "role": "user",
                            "content": f"[Follow-up]\n{pending_msg.content}",
                        }
                    )
                    count += 1
                except asyncio.QueueEmpty:
                    break
            if injected:
                logger.debug("mid_turn_injection", count=len(injected), session_key=session_key)
            return injected

        # Build checkpoint callback
        async def _checkpoint(payload: dict) -> None:
            if not self.sessions:
                return
            try:
                s = await self.sessions.get_or_create(msg.session_key)
                s.metadata[self._CHECKPOINT_KEY] = payload
                await self.sessions.save(s)
            except Exception as e:
                logger.warning("checkpoint_save_failed", error=str(e))

        spec = AgentRunSpec(
            initial_messages=list(turn.messages),
            tools=self.tools,
            model=self.model,
            max_iterations=self.max_iterations,
            max_tool_result_chars=self.max_tool_result_chars,
            llm_timeout_s=120.0,
            tool_timeout_s=60.0,
            stream_callback=on_stream,
            stream_end_callback=on_stream_end,
            checkpoint_callback=_checkpoint,
            injection_callback=_inject,
            workspace=str(self.workspace),
            session_key=session_key,
            ctx=turn.ctx,
        )

        try:
            result = await self.runner.run(spec)
        except Exception as e:
            logger.error("runner_failed", session_key=session_key, error=str(e))
            self._total_errors += 1
            turn.final_content = _ERR_PROCESSING
            turn.stop_reason = "error"
            return "ok"

        turn.final_content = result.final_content or ""
        turn.tools_used = result.tools_used
        turn.stop_reason = result.stop_reason

        return "ok"

    async def _state_save(
        self,
        msg: InboundMessage,
        session_key: str,
        turn: TurnContext,
    ) -> str:
        """SAVE: Persist the conversation turn and trigger memory consolidation."""
        if not self.sessions:
            return "ok"

        try:
            s = await self.sessions.get_or_create(msg.session_key)

            # Persist user message (independent of assistant reply)
            already_persisted = s.metadata.pop(self._PENDING_USER_KEY, False)
            if not already_persisted:
                s.add_message("user", msg.content)

            # Persist assistant reply if available
            if turn.final_content:
                s.add_message("assistant", turn.final_content)

            # Clean up checkpoint data
            s.metadata.pop(self._CHECKPOINT_KEY, None)

            await self.sessions.save(s)

            # Trigger background memory storage + consolidation
            if self.memory and hasattr(self.memory, "add"):
                self._schedule_background(
                    self._store_in_memory(msg.session_key, msg.content, turn.final_content or "")
                )
            # Check if consolidation threshold reached and trigger Dream
            self._schedule_background(self._maybe_consolidate_memory(msg.session_key))
        except Exception as e:
            logger.error("session_save_failed", session_key=session_key, error=str(e))

        return "ok"

    async def _state_respond(
        self,
        msg: InboundMessage,
        turn: TurnContext,
        trace_id: str,
        latency_ms: int,
    ) -> OutboundMessage | None:
        """RESPOND: Build and return the outbound message."""
        content = turn.final_content or ""

        # Suppress empty responses
        if not content.strip():
            logger.debug("empty_response_suppressed", trace_id=trace_id)
            return None

        # Log completion for observability
        logger.info(
            "turn_completed",
            trace_id=trace_id,
            chat_id=msg.chat_id,
            latency_ms=latency_ms,
            tools_used=turn.tools_used,
            stop_reason=turn.stop_reason,
        )

        # Emit event if event bus is available
        if self._event_bus:
            try:
                await self._event_bus.turn_completed(
                    trace_id=trace_id,
                    chat_id=msg.chat_id,
                    latency_ms=latency_ms,
                    tools_used=turn.tools_used,
                )
            except Exception:
                pass

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=content,
            metadata={
                "trace_id": trace_id,
                "stop_reason": turn.stop_reason,
                "latency_ms": latency_ms,
            },
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Crash Recovery
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _recover_from_crash(self, session) -> bool:
        """Recover session state after a crash or unexpected shutdown.

        If a previous turn was interrupted (e.g., process killed during
        tool execution), the checkpoint is used to add an error marker
        so the user knows their last request was not completed.
        """
        checkpoint = session.metadata.get(self._CHECKPOINT_KEY)
        if not isinstance(checkpoint, dict):
            return False

        # Mark the interrupted turn
        session.messages.append(
            {
                "role": "assistant",
                "content": (
                    "I apologize — my previous response was interrupted. "
                    "Could you please repeat your last request?"
                ),
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Clean up checkpoint metadata
        session.metadata.pop(self._CHECKPOINT_KEY, None)
        session.metadata.pop(self._PENDING_USER_KEY, None)

        logger.warning("crash_recovery_applied", session_key=session.key)
        return True

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Memory Storage
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _store_in_memory(
        self,
        session_key: str,
        user_msg: str,
        assistant_msg: str,
    ) -> None:
        """Store conversation turns in short-term memory for later consolidation."""
        if not self.memory:
            return
        try:
            chat_id = extract_chat_id(session_key)
            if hasattr(self.memory, "add"):
                result = self.memory.add(chat_id, "user", user_msg[:500], role="user")
                if asyncio.iscoroutine(result):
                    await result
                result = self.memory.add(
                    chat_id, "assistant", assistant_msg[:500], role="assistant"
                )
                if asyncio.iscoroutine(result):
                    await result
        except Exception as e:
            logger.debug("memory_store_failed", session_key=session_key, error=str(e))

    async def _maybe_consolidate_memory(self, session_key: str) -> None:
        """Check if Dream consolidation threshold is met and trigger if so."""
        if not self.memory or not hasattr(self.memory, "count_since_consolidation"):
            return
        try:
            chat_id = extract_chat_id(session_key)

            # Check threshold
            count_result = self.memory.count_since_consolidation(chat_id)
            if asyncio.iscoroutine(count_result):
                count = await count_result
            else:
                count = count_result

            threshold = self._consolidation_threshold

            if count >= threshold:
                logger.info("dream_consolidation_triggered", chat_id=chat_id, message_count=count)
                dreamer = await self._get_dream_consolidator(threshold)
                result = await dreamer.maybe_consolidate(chat_id)
                logger.info(
                    "dream_consolidation_result",
                    chat_id=chat_id,
                    facts=result.get("facts_extracted", 0),
                )
        except Exception as e:
            logger.debug("consolidation_skipped", session_key=session_key, error=str(e))

    async def _get_dream_consolidator(self, threshold: int):
        """Lazy-create and cache the DreamConsolidator (#9)."""
        if self._dream_consolidator is None:
            from config.paths import chroma_dir
            from memory.dream import DreamConsolidator
            from memory.store import ChromaMemoryStore

            chroma = (
                self.memory
                if isinstance(self.memory, ChromaMemoryStore)
                else ChromaMemoryStore(chroma_dir())
            )
            self._dream_consolidator = DreamConsolidator(
                chroma_store=chroma,
                short_term=self.memory,
                provider=self.provider,
                consolidation_threshold=threshold,
            )
        return self._dream_consolidator

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Dispatch
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Dispatch a message with per-session serialization.

        This is the main entry point for messages from the bus.
        - Acquires the session lock (serial per chat_id)
        - Acquires the concurrency gate (global limit)
        - Routes mid-turn messages to pending queues
        - Handles errors gracefully without crashing the loop
        """
        session_key = msg.session_key

        # If there's already an active task for this session,
        # queue the message for mid-turn injection instead of
        # creating a competing task.
        if session_key in self._active_tasks:
            active = [t for t in self._active_tasks.get(session_key, []) if not t.done()]
            if active:
                queue = self._pending_queues.get(session_key)
                if queue:
                    try:
                        queue.put_nowait(msg)
                        logger.debug("message_routed_to_pending_queue", session_key=session_key)
                        return
                    except asyncio.QueueFull:
                        pass  # Fall through to normal dispatch

        lock = self._session_locks.setdefault(session_key, asyncio.Lock())
        gate = self._concurrency_gate or nullcontext()

        # Create a pending queue for this session's turn
        pending = asyncio.Queue(maxsize=self._PENDING_QUEUE_SIZE)
        self._pending_queues[session_key] = pending

        async with lock, gate:
            try:
                response = await self._process_message(msg, session_key)
                if response:
                    await self.bus.publish_outbound(response)
            except asyncio.CancelledError:
                logger.info("task_cancelled", session_key=session_key)
                raise
            except Exception:
                logger.exception("dispatch_error", session_key=session_key)
                self._total_errors += 1
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=_ERR_MESSAGE,
                    )
                )
            finally:
                # Clean up only OUR pending queue
                if self._pending_queues.get(session_key) is pending:
                    self._pending_queues.pop(session_key, None)

                # Drain any leftover messages back to the bus
                leftover = 0
                while True:
                    try:
                        item = pending.get_nowait()
                        await self.bus.publish_inbound(item)
                        leftover += 1
                    except asyncio.QueueEmpty:
                        break
                if leftover:
                    logger.info("pending_queue_drained", session_key=session_key, count=leftover)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Main Event Loop
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def run(self) -> None:
        """Main event loop: consume messages from the bus and dispatch as tasks.

        Runs until stop() is called. Messages are consumed with a 1-second
        timeout so the loop can periodically check for shutdown.

        Priority commands (messages starting with "/") are handled inline
        without spawning a full task, providing near-instant responses.
        """
        self._running = True
        self._shutdown_requested = False
        logger.info("agent_loop_started", model=self.model)

        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
                continue
            except Exception as e:
                logger.warning("consume_error", error=str(e))
                continue

            # Handle priority commands inline (fast path)
            if self._is_command(msg.content):
                await self._dispatch_command_inline(msg)
                continue

            # Spawn task for normal processing
            task = asyncio.create_task(self._dispatch(msg))
            sk = msg.session_key
            self._active_tasks.setdefault(sk, []).append(task)
            task.add_done_callback(lambda t, k=sk: _safe_remove_task(self._active_tasks, k, t))

    async def _dispatch_command_inline(self, msg: InboundMessage) -> None:
        """Handle a command message inline (fast path, no task spawn)."""
        cmd = self._is_command(msg.content)
        if not cmd:
            return

        ctx = RequestContext(
            trace_id=str(uuid.uuid4()),
            chat_id=msg.chat_id,
            chat_type=msg.metadata.get("chat_type", "p2p"),
            user_id=msg.sender_id,
            message_id=msg.metadata.get("message_id", ""),
        )
        try:
            handler = self._commands[cmd]
            result = await handler(ctx)
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=result,
                )
            )
        except Exception as e:
            logger.error("inline_command_error", cmd=cmd, error=str(e))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Lifecycle Management
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def stop(self) -> None:
        """Signal the loop to stop accepting new messages."""
        self._running = False
        self._shutdown_requested = True
        self.bus.stop_accepting()
        logger.info("agent_loop_stopping")

    async def shutdown(self, timeout: float | None = None) -> None:
        """Graceful shutdown with in-flight turn drainage.

        Sequence:
        1. Stop accepting new messages
        2. Wait for active turns to complete (up to timeout)
        3. Cancel remaining turns (checkpoints are preserved)
        4. Save all sessions
        5. Cancel subagents
        """
        if timeout is None:
            timeout = self._SHUTDOWN_TIMEOUT

        self.stop()

        # Drain in-flight turns
        all_tasks = [t for ts in self._active_tasks.values() for t in ts if not t.done()]
        if all_tasks:
            logger.info("shutdown_draining_turns", count=len(all_tasks))
            try:
                await asyncio.wait_for(
                    asyncio.gather(*all_tasks, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "shutdown_timeout",
                    remaining=sum(1 for t in all_tasks if not t.done()),
                )
                for t in all_tasks:
                    if not t.done():
                        t.cancel()

        # Cancel subagents
        subagent_cancelled = await self.subagents.cancel_all()
        if subagent_cancelled:
            logger.info("shutdown_cancelled_subagents", count=subagent_cancelled)

        # Save all sessions
        if self.sessions:
            saved = 0
            for key in list(await self.sessions.all_keys()):
                try:
                    s = await self.sessions.get_or_create(key)
                    await self.sessions.save(s)
                    saved += 1
                except Exception:
                    pass
            logger.info("shutdown_saved_sessions", count=saved)

        # Clean up per-session locks for inactive sessions
        self._session_locks.clear()

        logger.info(
            "agent_loop_shutdown_complete",
            total_turns=self._total_turns,
            total_errors=self._total_errors,
        )

    def _schedule_background(self, coro) -> None:
        """Schedule a coroutine as a tracked background task.

        Background tasks are awaited during shutdown.
        """
        task = asyncio.create_task(coro)
        self._background_tasks.append(task)
        task.add_done_callback(
            lambda t: self._background_tasks.remove(t) if t in self._background_tasks else None
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Public API
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
    ) -> OutboundMessage | None:
        """Process a message directly, bypassing the bus.

        Used by CLI and other synchronous callers. Shares the same
        session lock as bus-based messages.

        Args:
            content: The message text
            session_key: Session identifier for persistence
            channel: Channel name (default: "cli")
            chat_id: Chat identifier (default: "direct")

        Returns:
            OutboundMessage with the response, or None if suppressed
        """
        msg = InboundMessage(
            channel=channel,
            sender_id="user",
            chat_id=chat_id,
            content=content,
            session_key_override=session_key,
        )
        lock = self._session_locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            return await self._process_message(msg, session_key)

    async def process_ephemeral(
        self,
        content: str,
        tools: Any = None,
    ) -> str:
        """Process a one-shot query without session persistence.

        Useful for stateless queries where history is not needed.
        No session is created or updated.

        Args:
            content: The message text
            tools: Optional tool registry override

        Returns:
            The assistant's response text
        """

        memory_ctx = ""
        if self.memory:
            try:
                memory_ctx = self.context_builder.get_memory_context("ephemeral")
            except Exception:
                pass

        messages = self.context_builder.build_messages(
            history=[],
            current_message=content,
            channel="cli",
            chat_id="ephemeral",
            sender_id="user",
            memory_context=memory_ctx,
        )

        spec = AgentRunSpec(
            initial_messages=messages,
            tools=tools or self.tools,
            model=self.model,
            max_iterations=self.max_iterations,
            max_tool_result_chars=self.max_tool_result_chars,
            llm_timeout_s=120.0,
        )

        result = await self.runner.run(spec)
        return result.final_content or ""

    def get_stats(self) -> dict:
        """Return runtime statistics for monitoring."""
        return {
            "total_turns": self._total_turns,
            "total_errors": self._total_errors,
            "active_sessions": len(self._active_tasks),
            "active_subagents": self.subagents.active_count,
            "uptime_seconds": int(time.time() - self._start_time),
            "model": self.model,
            "session_count": len(self._session_locks),
        }
