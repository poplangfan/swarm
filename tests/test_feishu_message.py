"""Tests for feishu message parser."""

import json
from swarm.gateway.feishu_message import parse_message_content


class TestMessageParser:
    def test_text_message(self):
        content = json.dumps({"text": "Hello, Swarm!"})
        text, images = parse_message_content("text", content)
        assert text == "Hello, Swarm!"
        assert images == []

    def test_image_message(self):
        content = json.dumps({"image_key": "img_abc123"})
        text, images = parse_message_content("image", content)
        assert "image" in text.lower()
        assert "img_abc123" in images

    def test_audio_message(self):
        text, images = parse_message_content("audio", "{}")
        assert "audio" in text.lower()

    def test_sticker_message(self):
        text, images = parse_message_content("sticker", "{}")
        assert "sticker" in text.lower()

    def test_post_message(self):
        content = json.dumps({
            "title": "Test Post",
            "content": [[{"tag": "text", "text": "Hello from post"}]],
        })
        text, images = parse_message_content("post", content)
        assert "Hello from post" in text

    def test_system_ignored(self):
        text, images = parse_message_content("system", "{}")
        assert text == ""
        assert images == []

    def test_file_message(self):
        content = json.dumps({"file_name": "report.pdf"})
        text, images = parse_message_content("file", content)
        assert "report.pdf" in text
