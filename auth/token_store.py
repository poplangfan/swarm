"""Encrypted SQLite token storage — AES-256-GCM for Feishu OAuth tokens."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TokenData:
    access_token: str
    refresh_token: str
    expires_at: float  # Unix timestamp

    def is_expired(self, buffer_seconds: float = 300) -> bool:
        return time.time() + buffer_seconds >= self.expires_at


class TokenStore:
    """AES-encrypted SQLite storage for Feishu user OAuth tokens."""

    def __init__(self, data_dir: Path, encrypt_key: str):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "tokens.db"
        key_bytes = encrypt_key.encode("utf-8")
        # Use SHA-256 as a KDF to derive a fixed 32-byte key from any-length input.
        # This avoids the security weakness of null-byte padding for short keys.
        self._key = hashlib.sha256(key_bytes).digest()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tokens (
                    user_id TEXT PRIMARY KEY, encrypted_data TEXT NOT NULL, updated_at REAL NOT NULL
                )
            """)
            conn.commit()

    def _encrypt(self, plaintext: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        nonce = os.urandom(12)
        aesgcm = AESGCM(self._key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    def _decrypt(self, encoded: str) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        combined = base64.b64decode(encoded)
        nonce, ciphertext = combined[:12], combined[12:]
        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")

    def save(self, user_id: str, token: TokenData) -> None:
        data = json.dumps(
            {
                "access_token": token.access_token,
                "refresh_token": token.refresh_token,
                "expires_at": token.expires_at,
            }
        )
        encrypted = self._encrypt(data)
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO tokens (user_id, encrypted_data, updated_at) VALUES (?,?,?)",
                (user_id, encrypted, time.time()),
            )
            conn.commit()
        logger.info("token_saved", user_id=user_id)

    def lookup(self, user_id: str) -> TokenData | None:
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT encrypted_data FROM tokens WHERE user_id=?", (user_id,)
            ).fetchone()
        if not row:
            return None
        try:
            plain = self._decrypt(row[0])
            data = json.loads(plain)
            return TokenData(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=data["expires_at"],
            )
        except Exception:
            logger.exception("token_decrypt_failed", user_id=user_id)
            return None

    def delete(self, user_id: str) -> None:
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))
            conn.commit()

    def is_authorized(self, user_id: str) -> bool:
        return self.lookup(user_id) is not None
