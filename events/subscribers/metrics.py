"""Metrics subscriber — collects latency, throughput, error rate metrics."""

from __future__ import annotations

import time
from collections import defaultdict

from events.bus import Event, EventType


class MetricsCollector:
    """Collects runtime metrics from events for monitoring."""

    def __init__(self):
        self._start_time = time.time()
        self._counters: dict[str, int] = defaultdict(int)
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._active_sessions: set[str] = set()

    async def on_event(self, event: Event) -> None:
        """Process an event and update metrics."""
        self._counters[f"event_{event.type.value}"] += 1

        if event.type == EventType.TURN_COMPLETED:
            latency = event.data.get("latency_ms", 0)
            if latency:
                chat_id = event.chat_id or "unknown"
                self._latencies[chat_id].append(float(latency))

        elif event.type == EventType.SESSION_CREATED:
            if event.chat_id:
                self._active_sessions.add(event.chat_id)

        elif event.type == EventType.SESSION_EXPIRED:
            if event.chat_id:
                self._active_sessions.discard(event.chat_id)

    def get_summary(self) -> dict:
        """Get a summary of collected metrics."""
        avg_latency = 0.0
        all_latencies = []
        for lat_list in self._latencies.values():
            all_latencies.extend(lat_list)
        if all_latencies:
            avg_latency = sum(all_latencies) / len(all_latencies)

        return {
            "uptime_seconds": time.time() - self._start_time,
            "total_events": sum(self._counters.values()),
            "active_sessions": len(self._active_sessions),
            "avg_turn_latency_ms": round(avg_latency, 1),
            "event_counts": dict(self._counters),
        }

    def reset(self) -> None:
        self._start_time = time.time()
        self._counters.clear()
        self._latencies.clear()
        self._active_sessions.clear()
