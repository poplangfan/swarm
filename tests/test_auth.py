"""Tests for auth system — token storage and encryption."""

import pytest
from auth.token_store import TokenStore, TokenData


class TestTokenStore:
    def test_save_and_lookup(self, temp_dir):
        store = TokenStore(temp_dir, encrypt_key="test-key-must-be-32-bytes-long!")
        store.save("user_1", TokenData(
            access_token="acc_xxx", refresh_token="ref_yyy", expires_at=9999999999))
        token = store.lookup("user_1")
        assert token is not None
        assert token.access_token == "acc_xxx"
        assert token.refresh_token == "ref_yyy"

    def test_lookup_missing(self, temp_dir):
        store = TokenStore(temp_dir, encrypt_key="test-key-must-be-32-bytes-long!")
        assert store.lookup("user_nonexistent") is None

    def test_delete(self, temp_dir):
        store = TokenStore(temp_dir, encrypt_key="test-key-must-be-32-bytes-long!")
        store.save("user_1", TokenData(access_token="x", refresh_token="y", expires_at=0))
        store.delete("user_1")
        assert store.lookup("user_1") is None

    def test_is_authorized(self, temp_dir):
        store = TokenStore(temp_dir, encrypt_key="test-key-must-be-32-bytes-long!")
        assert not store.is_authorized("user_1")
        store.save("user_1", TokenData(access_token="x", refresh_token="y",
                                       expires_at=9999999999))
        assert store.is_authorized("user_1")

    def test_encryption_roundtrip(self, temp_dir):
        store = TokenStore(temp_dir, encrypt_key="super-secret-key--32bytes!!")
        original = TokenData(access_token="very-secret", refresh_token="very-refresh",
                            expires_at=9999999999)
        store.save("u1", original)
        restored = store.lookup("u1")
        assert restored.access_token == original.access_token
        assert restored.refresh_token == original.refresh_token


class TestTokenData:
    def test_not_expired(self):
        td = TokenData(access_token="x", refresh_token="y", expires_at=9999999999)
        assert not td.is_expired()

    def test_expired(self):
        td = TokenData(access_token="x", refresh_token="y", expires_at=100)
        assert td.is_expired()
