"""Tests for Feishu reply builder — card types, reactions, helpers."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from gateway.feishu_reply import FeishuReply


class TestFeishuReply:
    def test_build_mention(self):
        mention = FeishuReply.build_mention("ou_123", "Alice")
        assert "ou_123" in mention
        assert "Alice" in mention
        assert "<at" in mention

    def test_build_mention_all(self):
        mention = FeishuReply.build_mention_all()
        assert "all" in mention

    def test_build_link(self):
        link = FeishuReply.build_link("https://example.com", "Click here")
        assert "example.com" in link
        assert "Click here" in link

    def test_build_code_block(self):
        code = FeishuReply.build_code_block("print('hello')", "python")
        assert "python" in code
        assert "print" in code
        assert "```" in code

    def test_build_progress_bar(self):
        bar = FeishuReply.build_progress_bar(75, width=10)
        assert "75%" in bar
        assert "█" in bar

    def test_build_progress_bar_full(self):
        bar = FeishuReply.build_progress_bar(100, width=5)
        assert "100%" in bar

    def test_build_progress_bar_empty(self):
        bar = FeishuReply.build_progress_bar(0, width=5)
        assert "0%" in bar

    @pytest.mark.asyncio
    async def test_send_text(self):
        reply = FeishuReply(
            app_id="test_app", app_secret="test_secret",
        )
        with patch.object(reply._token, 'get_token', return_value="mock_token"):
            with patch.object(reply, '_post') as mock_post:
                mock_post.return_value = {
                    "code": 0,
                    "data": {"message_id": "msg_001"},
                }
                msg_id = await reply.send_text("oc_test", "Hello")
                assert msg_id == "msg_001"

    @pytest.mark.asyncio
    async def test_send_markdown_card(self):
        reply = FeishuReply(
            app_id="test_app", app_secret="test_secret",
        )
        with patch.object(reply._token, 'get_token', return_value="mock_token"):
            with patch.object(reply, '_post') as mock_post:
                mock_post.return_value = {
                    "code": 0,
                    "data": {"message_id": "msg_card_001"},
                }
                msg_id = await reply.send_markdown_card(
                    "oc_test", "**Bold** text", title="Test"
                )
                assert msg_id == "msg_card_001"

    @pytest.mark.asyncio
    async def test_send_card_with_actions(self):
        reply = FeishuReply(
            app_id="test_app", app_secret="test_secret",
        )
        actions = [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "Approve"},
                "type": "primary",
                "value": {"action": "approve"},
            },
        ]
        with patch.object(reply._token, 'get_token', return_value="mock_token"):
            with patch.object(reply, '_post') as mock_post:
                mock_post.return_value = {
                    "code": 0,
                    "data": {"message_id": "msg_action_001"},
                }
                msg_id = await reply.send_card_with_actions(
                    "oc_test", "Please review", actions=actions,
                )
                assert msg_id == "msg_action_001"

    @pytest.mark.asyncio
    async def test_send_error_card(self):
        reply = FeishuReply(
            app_id="test_app", app_secret="test_secret",
        )
        with patch.object(reply._token, 'get_token', return_value="mock_token"):
            with patch.object(reply, '_post') as mock_post:
                mock_post.return_value = {
                    "code": 0,
                    "data": {"message_id": "msg_err"},
                }
                msg_id = await reply.send_error_card("oc_test", "Something wrong")
                assert msg_id is not None

    @pytest.mark.asyncio
    async def test_add_reaction(self):
        reply = FeishuReply(
            app_id="test_app", app_secret="test_secret",
        )
        with patch.object(reply._token, 'get_token', return_value="mock_token"):
            with patch.object(reply, '_post') as mock_post:
                mock_post.return_value = {"code": 0}
                ok = await reply.add_reaction("msg_001", "THUMBSUP")
                assert ok is True

    @pytest.mark.asyncio
    async def test_add_reaction_failure(self):
        reply = FeishuReply(
            app_id="test_app", app_secret="test_secret",
        )
        with patch.object(reply._token, 'get_token', return_value="mock_token"):
            with patch.object(reply, '_post') as mock_post:
                mock_post.return_value = {"code": 999, "msg": "error"}
                ok = await reply.add_reaction("msg_001", "THUMBSUP")
                assert ok is False

    @pytest.mark.asyncio
    async def test_send_failure_returns_none(self):
        reply = FeishuReply(
            app_id="test_app", app_secret="test_secret",
        )
        with patch.object(reply._token, 'get_token', return_value="mock_token"):
            with patch.object(reply, '_post') as mock_post:
                mock_post.return_value = {"code": 999, "msg": "API error"}
                msg_id = await reply.send_text("oc_test", "hello")
                assert msg_id is None

    @pytest.mark.asyncio
    async def test_update_card(self):
        reply = FeishuReply(
            app_id="test_app", app_secret="test_secret",
        )
        with patch.object(reply._token, 'get_token', return_value="mock_token"):
            with patch.object(reply, '_patch') as mock_patch:
                mock_patch.return_value = {"code": 0}
                ok = await reply.update_card("msg_001", "Updated content")
                assert ok is True
