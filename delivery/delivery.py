"""Outbound message delivery — per-chat queues, global rate limiting, retry."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

import structlog

from bus.queue import OutboundMessage

logger = structlog.get_logger(__name__)


@dataclass
class DeliveryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    rate_limit_per_second: float = 10.0  # Feishu: 10 req/s per app
    queue_max_size: int = 100


class Delivery:
    """Outbound message delivery layer with per-chat ordering and global rate limiting.

    Design (inspired by hermes-agent):
    - Channel adapters handle format conversion (markdown → feishu card)
    - Delivery handles reliability: queuing, rate limiting, retry, confirmation
    - Each chat_id gets its own FIFO queue (preserves message order within a chat)
    - Global rate limiter prevents API throttling
    """

    def __init__(
        self,
        send_fn: Callable[[OutboundMessage], Any],
        config: DeliveryConfig | None = None,
    ):
        self._send_fn = send_fn
        self._config = config or DeliveryConfig()
        self._queues: dict[str, asyncio.Queue[OutboundMessage]] = defaultdict(
            lambda: asyncio.Queue(maxsize=self._config.queue_max_size)
        )
        self._workers: dict[str, asyncio.Task] = {}
        self._running = False
        self._rate_limiter = _RateLimiter(self._config.rate_limit_per_second)

    async def send(self, msg: OutboundMessage) -> bool:
        """Enqueue an outbound message for delivery. Returns True if queued."""
        chat_id = msg.chat_id
        queue = self._queues[chat_id]
        try:
            queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("delivery_queue_full", chat_id=chat_id)
            return False

        # Ensure a worker is running for this chat
        if chat_id not in self._workers or self._workers[chat_id].done():
            self._workers[chat_id] = asyncio.create_task(self._worker(chat_id))
        return True

    async def _worker(self, chat_id: str) -> None:
        """Worker coroutine that drains the queue for a specific chat_id."""
        import structlog
        queue = self._queues[chat_id]
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # No messages for 30s — stop worker
                break

            # Rate limit
            await self._rate_limiter.acquire()

            # Send with retry
            delivered = await self._send_with_retry(msg)
            if not delivered:
                logger.error("delivery_failed_permanently",
                             chat_id=chat_id,
                             content_preview=str(msg.content)[:100])

    async def _send_with_retry(self, msg: OutboundMessage) -> bool:
        """Attempt to send a message with exponential backoff retry.

        send_fn should raise an exception on failure. A non-exception return
        (including None) is treated as success — some APIs return empty bodies
        (e.g. 204 No Content).
        """
        for attempt in range(self._config.max_retries + 1):
            try:
                await self._send_fn(msg)
                return True
            except Exception as e:
                logger.warning("delivery_attempt_failed",
                               attempt=attempt,
                               chat_id=msg.chat_id,
                               error=str(e))

            if attempt < self._config.max_retries:
                delay = min(
                    self._config.base_delay * (2 ** attempt),
                    self._config.max_delay,
                )
                await asyncio.sleep(delay)

        return False

    async def flush(self) -> None:
        """Wait for all pending messages to be delivered."""
        tasks = [t for t in self._workers.values() if not t.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def shutdown(self) -> None:
        """Graceful shutdown: flush queues, cancel workers."""
        self._running = False
        await self.flush()
        for task in list(self._workers.values()):
            if not task.done():
                task.cancel()


class _RateLimiter:
    """Token bucket rate limiter for API call throttling."""

    def __init__(self, rate: float):
        self._rate = rate
        self._tokens = rate
        self._last_refill = time.monotonic()

    async def acquire(self) -> None:
        """Wait until a token is available."""
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            # Wait for next token
            wait_time = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(wait_time)
