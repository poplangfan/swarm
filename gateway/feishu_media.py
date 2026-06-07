"""Feishu media — download images, files, audio from Feishu messages."""

from __future__ import annotations

from pathlib import Path

import httpx
import structlog

from gateway.feishu_token import FeishuTokenManager

logger = structlog.get_logger(__name__)


class FeishuMedia:
    """Download media files from Feishu using the Im API."""

    def __init__(self, app_id: str, app_secret: str, domain: str = "feishu",
                 download_dir: str = "./data/media"):
        self._domain = domain
        self._download_dir = Path(download_dir)
        self._download_dir.mkdir(parents=True, exist_ok=True)
        self._token = FeishuTokenManager(app_id, app_secret, domain)

    async def download_image(self, image_key: str) -> Path | None:
        """Download an image from Feishu by image_key. Returns local file path."""
        token = await self._token.get_token()
        base = "https://open.feishu.cn" if self._domain == "feishu" else "https://open.larksuite.com"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{base}/open-apis/im/v1/images/{image_key}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                    follow_redirects=True,
                )
                if resp.status_code != 200:
                    logger.warning("image_download_failed", image_key=image_key,
                                   status=resp.status_code)
                    return None
                ext = _guess_image_ext(resp.headers.get("content-type", ""))
                filepath = self._download_dir / f"{image_key}{ext}"
                filepath.write_bytes(resp.content)
                return filepath
        except Exception as e:
            logger.warning("image_download_error", image_key=image_key, error=str(e))
            return None

    async def download_file(self, file_key: str) -> Path | None:
        """Download a file from Feishu by file_key."""
        token = await self._token.get_token()
        base = "https://open.feishu.cn" if self._domain == "feishu" else "https://open.larksuite.com"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{base}/open-apis/im/v1/messages/{file_key}/resources/{file_key}",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=60.0,
                    params={"type": "file"},
                    follow_redirects=True,
                )
                if resp.status_code != 200:
                    logger.warning("file_download_failed", file_key=file_key)
                    return None
                filepath = self._download_dir / f"file_{file_key}"
                filepath.write_bytes(resp.content)
                return filepath
        except Exception as e:
            logger.warning("file_download_error", file_key=file_key, error=str(e))
            return None


def _guess_image_ext(content_type: str) -> str:
    if "png" in content_type:
        return ".png"
    if "jpeg" in content_type or "jpg" in content_type:
        return ".jpg"
    if "gif" in content_type:
        return ".gif"
    if "webp" in content_type:
        return ".webp"
    return ".img"
