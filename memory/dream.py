"""Dream memory consolidation — two-phase LLM-assisted memory extraction.

Phase 1 (Extraction): LLM reviews recent messages and extracts key facts.
Phase 2 (Storage): Facts are embedded and stored in ChromaDB by chat_id.

Triggered when message count exceeds consolidation_threshold (default: 20).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from memory.short_term import ShortTermMemory
from memory.store import ChromaMemoryStore
from providers.base import LLMProvider

logger = structlog.get_logger(__name__)


class DreamConsolidator:
    """Two-phase memory consolidation using LLM extraction + ChromaDB storage."""

    SYSTEM_PROMPT = "You are a memory consolidation system. Output ONLY a JSON array of fact objects. No other text, no markdown, no explanation."

    EXTRACTION_PROMPT = """Review the following conversation and extract key facts.

For each important fact, output a JSON object with:
- "fact": the factual information
- "importance": 0.0-1.0 rating of how important this fact is
- "entities": list of people, projects, or topics mentioned

Recent conversation:
{conversation}

Output ONLY a JSON list. Example: [{{"fact": "...", "importance": 0.8, "entities": ["..."], "timestamp": "..."}}]"""

    def __init__(
        self,
        chroma_store: ChromaMemoryStore,
        short_term: ShortTermMemory,
        provider: LLMProvider | None = None,
        consolidation_threshold: int = 20,
        dream_model: str = "gpt-4o-mini",
    ):
        self._chroma = chroma_store
        self._short_term = short_term
        self._provider = provider
        self._threshold = consolidation_threshold
        self._dream_model = dream_model

    async def maybe_consolidate(self, chat_id: str) -> dict[str, Any]:
        """Check if consolidation is needed and run it if so.

        Returns: {"consolidated": bool, "facts_extracted": int, "error": str|None}
        """
        count = await self._short_term.count_since_consolidation(chat_id)
        if count < self._threshold:
            return {"consolidated": False, "facts_extracted": 0, "error": None}

        logger.info("dream_consolidation_started", chat_id=chat_id, message_count=count)

        try:
            facts = await self._extract_facts(chat_id)
            last_id = await self._short_term.get_last_message_id(chat_id)

            if not facts:
                # Still advance cursor to avoid re-processing same messages (#1)
                if last_id is not None:
                    await self._short_term.mark_consolidated(chat_id, last_id)
                return {"consolidated": True, "facts_extracted": 0, "error": None}

            stored_count = 0
            for fact in facts:
                content = fact.get("fact", "")
                importance = float(fact.get("importance", 0.5))
                entities = fact.get("entities", [])

                if content:
                    success = await self._chroma.add(
                        chat_id=chat_id,
                        user_id="dream",
                        content=content,
                        importance=importance,
                        metadata={"entities": ",".join(entities), "source": "dream"},
                    )
                    if success:
                        stored_count += 1

            # Advance consolidation cursor so we don't re-process (#1)
            if last_id is not None:
                await self._short_term.mark_consolidated(chat_id, last_id)

            logger.info(
                "dream_consolidation_complete", chat_id=chat_id, facts_extracted=stored_count
            )
            return {"consolidated": True, "facts_extracted": stored_count, "error": None}

        except Exception as e:
            logger.error("dream_consolidation_error", chat_id=chat_id, error=str(e))
            return {"consolidated": False, "facts_extracted": 0, "error": str(e)}

    async def _extract_facts(self, chat_id: str) -> list[dict[str, Any]]:
        """Phase 1: Extract key facts from recent messages."""
        recent = await self._short_term.get_recent(chat_id, limit=self._threshold)
        if not recent:
            return []

        # Build conversation text
        lines = []
        for m in recent:
            role = m.get("role", "unknown")
            content = str(m.get("content", ""))[:500]
            lines.append(f"[{role}] {content}")
        conversation = "\n".join(lines)

        if not self._provider:
            # No LLM provider — use simple extraction heuristics
            return self._heuristic_extraction(conversation)

        # Use LLM for extraction with system message (#5)
        prompt = self.EXTRACTION_PROMPT.format(conversation=conversation)

        try:
            messages = [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
            response = await asyncio.wait_for(
                self._provider.chat(messages=messages),
                timeout=60.0,
            )
            if response and response.content:
                text = response.content
                facts = self._parsejson_facts(text)
                if facts:
                    return facts
        except Exception as e:
            logger.warning("dream_extraction_llm_error", error=str(e))

        return self._heuristic_extraction(conversation)

    @staticmethod
    def _parsejson_facts(text: str) -> list[dict[str, Any]] | None:
        """Robust JSON extraction from LLM output (#5).

        Tries in order:
        1. Direct JSON parse (if model output is clean)
        2. Extract from ```json ... ``` fenced block
        3. Extract from first [ to last ]
        """
        text = text.strip()
        # 1. Direct parse
        try:
            result = json.loads(text)
            return result if isinstance(result, list) else None
        except (json.JSONDecodeError, ValueError):
            pass
        # 2. Fenced code block
        fence_start = text.find("```json")
        if fence_start >= 0:
            fence_end = text.find("```", fence_start + 7)
            if fence_end > fence_start:
                try:
                    inner = text[fence_start + 7 : fence_end].strip()
                    result = json.loads(inner)
                    return result if isinstance(result, list) else None
                except (json.JSONDecodeError, ValueError):
                    pass
        # 3. Bracket scan
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(text[start:end])
                return result if isinstance(result, list) else None
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _heuristic_extraction(self, conversation: str) -> list[dict[str, Any]]:
        """Simple heuristic-based fact extraction when LLM is unavailable."""
        facts = []
        sentences = [s.strip() for s in conversation.split("\n") if s.strip() and len(s) > 20]
        for i, sent in enumerate(sentences[:10]):
            # Extract sentences that look like factual statements
            if any(
                kw in sent.lower()
                for kw in ["is ", "are ", "works ", "project", "need", "want", "like ", "use"]
            ):
                facts.append(
                    {
                        "fact": sent[:300],
                        "importance": 0.5 + (0.1 * (len(sentences) - i) / max(1, len(sentences))),
                        "entities": [],
                    }
                )
        return facts
