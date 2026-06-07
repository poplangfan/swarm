"""Feishu message content parser — handles all msg_types."""

from __future__ import annotations

import json
from typing import Any

MSG_TYPE_MAP = {
    "image": "[image]", "audio": "[audio]",
    "file": "[file]", "sticker": "[sticker]",
}


def parse_message_content(msg_type: str, content_json: str) -> tuple[str, list[str]]:
    """Parse Feishu message content into (text, image_keys)."""
    try:
        content = json.loads(content_json) if isinstance(content_json, str) else content_json
    except (json.JSONDecodeError, TypeError):
        return content_json if isinstance(content_json, str) else "", []

    if msg_type == "text":
        return content.get("text", ""), []
    elif msg_type == "post":
        text, images = _extract_post_content(content)
        return text or "[post message]", images
    elif msg_type == "image":
        # Support both single image_key and multi-image image_keys
        images = content.get("image_keys", [])
        if not images:
            key = content.get("image_key", "")
            images = [key] if key else []
        count = len(images)
        label = f"[image]" if count <= 1 else f"[{count} images]"
        return label, [str(k) for k in images]
    elif msg_type == "audio":
        return "[audio]", []
    elif msg_type == "file":
        return f"[file: {content.get('file_name', 'unknown')}]", []
    elif msg_type == "sticker":
        return "[sticker]", []
    elif msg_type in ("share_chat", "share_user", "share_calendar_event"):
        return f"[{msg_type}]", []
    elif msg_type == "interactive":
        return _extract_card_text(content), []
    elif msg_type == "system":
        return "", []
    elif msg_type == "merge_forward":
        return "[merged forward messages]", []
    else:
        return f"[{msg_type}]", []


def _extract_post_content(content: dict) -> tuple[str, list[str]]:
    texts, images = [], []
    root = content
    if isinstance(root, dict) and isinstance(root.get("post"), dict):
        root = root["post"]
    if isinstance(root.get("title"), str) and root["title"]:
        texts.append(root["title"])
    body = root.get("content", root)
    if isinstance(body, list):
        for paragraph in body:
            if not isinstance(paragraph, list):
                continue
            for el in paragraph:
                if not isinstance(el, dict):
                    continue
                tag = el.get("tag", "")
                if tag == "text":
                    texts.append(el.get("text", ""))
                elif tag == "a":
                    texts.append(el.get("text", ""))
                elif tag == "at":
                    texts.append(f"@{el.get('user_name', 'user')}")
                elif tag == "img":
                    if key := el.get("image_key"):
                        images.append(key)
    return " ".join(texts).strip(), images


def _extract_card_text(content: dict) -> str:
    parts = []
    if isinstance(content.get("title"), str):
        parts.append(content["title"])
    _walk_elements(content, parts)
    return "\n".join(parts) if parts else "[interactive card]"


def _walk_elements(node, parts):
    if isinstance(node, str):
        if node.strip():
            parts.append(node)
    elif isinstance(node, dict):
        for key in ("content", "text", "title"):
            if val := node.get(key):
                _walk_elements(val, parts)
        for key in ("elements", "fields", "columns"):
            if lst := node.get(key):
                if isinstance(lst, list):
                    for item in lst:
                        _walk_elements(item, parts)
    elif isinstance(node, list):
        for item in node:
            _walk_elements(item, parts)
