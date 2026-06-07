"""Shared test fixtures for Swarm."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from swarm.bus.queue import MessageBus
from swarm.agent.context import RequestContext
from swarm.providers.base import LLMResponse


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def mock_provider():
    p = MagicMock()
    p.chat = AsyncMock(return_value=LLMResponse(
        content="Mock response", stop_reason="end_turn"))
    p.model = "gpt-4o"
    p.context_window = 128_000
    p._max_tokens = 4096
    p.generation = MagicMock()
    p.generation.max_tokens = 4096
    return p


@pytest.fixture
def sample_ctx():
    return RequestContext(
        trace_id="test-trace", chat_id="test_chat",
        chat_type="p2p", user_id="test_user", message_id="test_msg",
    )
