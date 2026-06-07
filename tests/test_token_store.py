"""Comprehensive tests for token store encryption and management."""

import time
from unittest.mock import MagicMock

from agent.context import RequestContext
from auth.middleware import inject_user_token
from auth.token_store import TokenData, TokenStore


class TestTokenStoreEncryption:
    """Verify AES-256-GCM encryption correctly protects token data."""

    def test_encryption_is_not_plaintext(self, temp_dir):
        store = TokenStore(temp_dir, encrypt_key="32-byte-secret-key-for-testing!")
        store.save(
            "user_1",
            TokenData(
                access_token="super-secret-token",
                refresh_token="super-secret-refresh",
                expires_at=9999999999,
            ),
        )
        # Read the raw DB file — should NOT contain plaintext tokens
        db_content = (temp_dir / "tokens.db").read_bytes()
        assert b"super-secret-token" not in db_content
        assert b"super-secret-refresh" not in db_content

    def test_different_keys_produce_different_ciphertext(self, temp_dir):
        store1 = TokenStore(temp_dir / "a", encrypt_key="key-aaa-bbb-ccc-ddd-eee-fff-ggg!")
        store2 = TokenStore(temp_dir / "b", encrypt_key="key-zzz-yyy-xxx-www-vvv-uuu-ttt!")
        token = TokenData(access_token="tok", refresh_token="ref", expires_at=0)

        store1.save("u1", token)
        store2.save("u1", token)

        raw1 = (temp_dir / "a" / "tokens.db").read_bytes()
        raw2 = (temp_dir / "b" / "tokens.db").read_bytes()

        # Same data, different keys → different ciphertexts
        assert raw1 != raw2

    def test_key_derivation_short_key(self, temp_dir):
        """Short keys are padded to 32 bytes."""
        store = TokenStore(temp_dir, encrypt_key="short")
        store.save("u1", TokenData(access_token="x", refresh_token="y", expires_at=0))
        assert store.lookup("u1") is not None

    def test_mass_operations(self, temp_dir):
        """Many users, no data leaks between them."""
        store = TokenStore(temp_dir, encrypt_key="32-byte-key-for-mass-testing!!")
        for i in range(100):
            store.save(
                f"user_{i}",
                TokenData(
                    access_token=f"tok_{i}",
                    refresh_token=f"ref_{i}",
                    expires_at=time.time() + 7200,
                ),
            )
        for i in range(100):
            token = store.lookup(f"user_{i}")
            assert token is not None
            assert token.access_token == f"tok_{i}"


class TestTokenExpiry:
    def test_not_expired(self):
        future = time.time() + 7200
        td = TokenData(access_token="x", refresh_token="y", expires_at=future)
        assert not td.is_expired()

    def test_expired(self):
        td = TokenData(access_token="x", refresh_token="y", expires_at=100)
        assert td.is_expired()

    def test_near_expiry_with_buffer(self):
        """Token expiring in 4 minutes with 5-min buffer → expired for safety."""
        near_future = time.time() + 240  # 4 minutes
        td = TokenData(access_token="x", refresh_token="y", expires_at=near_future)
        assert td.is_expired(buffer_seconds=300)


class TestMiddleware:
    def test_inject_token_into_context(self):
        store = MagicMock()
        store.lookup.return_value = TokenData(
            access_token="user_token_xxx",
            refresh_token="ref_xxx",
            expires_at=time.time() + 7200,
        )
        store.is_authorized.return_value = True

        ctx = RequestContext(
            trace_id="t1",
            chat_id="c1",
            chat_type="p2p",
            user_id="u1",
            message_id="m1",
        )

        import asyncio

        updated = asyncio.run(inject_user_token(ctx, store))
        assert updated.user_token == "user_token_xxx"

    def test_no_token_when_not_authorized(self):
        store = MagicMock()
        store.lookup.return_value = None
        store.is_authorized.return_value = False

        ctx = RequestContext(
            trace_id="t1",
            chat_id="c1",
            chat_type="p2p",
            user_id="u1",
            message_id="m1",
        )

        import asyncio

        updated = asyncio.run(inject_user_token(ctx, store))
        assert updated.user_token is None

    def test_already_has_token_skipped(self):
        store = MagicMock()
        ctx = RequestContext(
            trace_id="t1",
            chat_id="c1",
            chat_type="p2p",
            user_id="u1",
            message_id="m1",
            user_token="existing",
        )

        import asyncio

        updated = asyncio.run(inject_user_token(ctx, store))
        assert updated.user_token == "existing"
        store.lookup.assert_not_called()
