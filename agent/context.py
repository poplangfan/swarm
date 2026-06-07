"""RequestContext — immutable per-request isolation core + ContextBuilder."""

from __future__ import annotations

import base64
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from utils.text import current_time_str


@dataclass(frozen=True)
class RequestContext:
    """Immutable per-request context.

    Passed explicitly to ALL stateful functions.
    Framework code MUST NOT use os.environ or contextvars for per-request state.
    """

    trace_id: str
    chat_id: str
    chat_type: str  # "p2p" | "group"
    user_id: str
    message_id: str
    user_token: str | None = None
    permissions: frozenset[str] = field(default_factory=frozenset)
    locale: str = "zh-CN"


@dataclass
class TurnContext:
    """Mutable turn-level state — only used within a single turn, not persisted."""
    ctx: RequestContext
    messages: list[dict] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    final_content: str | None = None
    stop_reason: str = ""


class ContextBuilder:
    """Assembles system prompt and message lists for LLM calls.

    Layers (in order):
    1. Identity — who the agent is, runtime info
    2. Bootstrap files — AGENTS.md, SOUL.md, USER.md from workspace
    3. Tool contract — rules for tool usage
    4. Memory context — ChromaDB recall results
    5. Active Skills — always-on skill definitions
    6. Available Skills — on-demand skill catalog
    7. Recent history summary — from short-term memory
    8. Session summary — compressed archive of older context
    """

    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md"]
    _RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"
    _RUNTIME_CONTEXT_END = "[/Runtime Context]"

    def __init__(self, workspace: Path, timezone: str | None = None,
                 memory: Any = None, skills_loader: Any = None):
        self.workspace = Path(workspace)
        self.timezone = timezone or "Asia/Shanghai"
        self.memory = memory
        self.skills = skills_loader

    # ── System Prompt ────────────────────────────────────────

    def build_system_prompt(
        self,
        channel: str | None = None,
        chat_id: str | None = None,
        sender_id: str | None = None,
        session_summary: str | None = None,
        memory_context: str | None = None,
        skill_names: list[str] | None = None,
    ) -> str:
        """Assemble the complete system prompt."""
        root = self.workspace
        parts = []

        # 1. Identity
        parts.append(self._build_identity(channel=channel))

        # 2. Bootstrap files
        bootstrap = self._load_bootstrap_files(root)
        if bootstrap:
            parts.append(bootstrap)

        # 3. Always-active skills (before tool contract —
        #    active skills may contain tool usage constraints)
        if self.skills:
            try:
                always_names = self.skills.get_always_skills()
                if always_names:
                    skills_content = self.skills.load_skills_for_context(always_names)
                    if skills_content:
                        parts.append(skills_content)
            except Exception:
                pass

        # 4. Tool contract
        parts.append(self._build_tool_contract())

        # 5. Available Skills summary
        if self.skills:
            try:
                always_set = set(self.skills.get_always_skills())
                summary = self.skills.build_skills_summary(exclude=always_set)
                if summary:
                    parts.append(summary)
            except Exception:
                pass

        # 6. Session summary (compressed old context)
        if session_summary:
            parts.append(f"[Archived Context]\n{session_summary}")

        # 7. Memory context
        if memory_context:
            parts.append(f"# Relevant Context\n{memory_context}")

        # 8. Recent history from short-term memory
        if self.memory and chat_id:
            try:
                entries = self.memory.get_recent(chat_id, limit=10)
                if entries:
                    history_text = "\n".join(
                        f"- {e.get('timestamp', '')}: [{e.get('role', '')}] {e.get('content', '')[:200]}"
                        for e in entries
                    )
                    if history_text:
                        parts.append(f"# Recent Conversation\n{history_text}")
            except Exception:
                pass

        return "\n\n---\n\n".join(parts)

    def _build_identity(self, channel: str | None = None) -> str:
        """Build the agent identity section."""
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"
        workspace_path = str(self.workspace.expanduser().resolve())

        lines = [
            "You are Swarm, an intelligent AI assistant for Feishu.",
            "",
            f"**Runtime**: {runtime}",
            f"**Workspace**: {workspace_path}",
            f"**Current Time**: {current_time_str(self.timezone)}",
        ]
        if channel:
            lines.append(f"**Channel**: {channel}")
        lines.extend([
            "",
            "## Core Principles",
            "- Be helpful, accurate, and concise.",
            "- Use tools when they help answer the user's question.",
            "- Respond in the same language as the user.",
            "- For Feishu users: respect group context, don't spam, be professional.",
        ])
        return "\n".join(lines)

    def _build_tool_contract(self) -> str:
        """Build tool usage rules section."""
        return """## Tool Usage Rules
- Call tools with exactly the arguments they require.
- If a tool returns an error, explain the issue to the user and try an alternative.
- Don't call the same tool with the same arguments repeatedly.
- When you have enough information, stop calling tools and give the final answer.
- Format tool results clearly when presenting to the user."""

    def _load_bootstrap_files(self, workspace: Path) -> str:
        """Load AGENTS.md, SOUL.md, USER.md from workspace."""
        parts = []
        for filename in self.BOOTSTRAP_FILES:
            file_path = workspace / filename
            if file_path.exists():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    parts.append(f"## {filename}\n\n{content}")
                except Exception:
                    pass
        return "\n\n".join(parts)

    def get_memory_context(self, chat_id: str) -> str:
        """Get memory context for a specific chat_id."""
        if not self.memory:
            return ""
        try:
            entries = self.memory.get_recent(chat_id, limit=20)
            if not entries:
                return ""
            lines = []
            for e in entries:
                role = e.get("role", "unknown")
                content = str(e.get("content", ""))[:300]
                lines.append(f"[{role}] {content}")
            return "\n".join(lines)
        except Exception:
            return ""

    # ── Message Building ──────────────────────────────────────

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        sender_id: str | None = None,
        session_summary: str | None = None,
        memory_context: str | None = None,
        skip_runtime_lines: bool = False,
    ) -> list[dict[str, Any]]:
        """Build the complete message list for an LLM call."""
        # System prompt
        system_content = self.build_system_prompt(
            channel=channel, chat_id=chat_id,
            sender_id=sender_id, session_summary=session_summary,
            memory_context=memory_context,
        )

        # User content with runtime context appended
        user_content = self._build_user_content(current_message, media)
        if not skip_runtime_lines:
            runtime_ctx = self._build_runtime_context(
                channel=channel, chat_id=chat_id, sender_id=sender_id,
                timezone=self.timezone,
            )
            if isinstance(user_content, str):
                user_content = f"{user_content}\n\n{runtime_ctx}"
            else:
                user_content = user_content + [{"type": "text", "text": runtime_ctx}]

        messages = [{"role": "system", "content": system_content}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content, optionally with base64-encoded images."""
        if not media:
            return text

        images = []
        for path in media:
            p = Path(path)
            if not p.is_file():
                continue
            raw = p.read_bytes()
            mime = self._detect_image_mime(raw)
            if not mime:
                continue
            b64 = base64.b64encode(raw).decode()
            images.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
                "_meta": {"path": str(p)},
            })

        if not images:
            return text
        return images + [{"type": "text", "text": text}]

    @staticmethod
    def _detect_image_mime(data: bytes) -> str | None:
        from utils.media import detect_image_mime
        return detect_image_mime(data)

    @staticmethod
    def _build_runtime_context(
        channel: str | None = None,
        chat_id: str | None = None,
        timezone: str | None = None,
        sender_id: str | None = None,
        supplemental_lines: Sequence[str] | None = None,
    ) -> str:
        """Build the untrusted runtime metadata block appended after user content."""
        lines = [f"Current Time: {current_time_str(timezone)}"]
        if channel and chat_id:
            lines.append(f"Channel: {channel}")
            lines.append(f"Chat ID: {chat_id}")
        if sender_id:
            lines.append(f"Sender ID: {sender_id}")
        if supplemental_lines:
            lines.extend(supplemental_lines)
        tag = ContextBuilder._RUNTIME_CONTEXT_TAG
        end = ContextBuilder._RUNTIME_CONTEXT_END
        return tag + "\n" + "\n".join(lines) + "\n" + end
