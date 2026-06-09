"""Credential pool for LLM providers — API key rotation + exhaustion tracking.

Hermes pattern: multiple API keys per provider, rotated round-robin to
distribute rate limits across accounts. Exhausted keys are quarantined
and automatically revived after a cooldown period.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Default cooldown for exhausted keys (seconds)
DEFAULT_COOLDOWN = 300  # 5 minutes
# Max keys per provider
MAX_KEYS = 20


@dataclass
class PooledCredential:
    """A single API key in the pool with status tracking."""

    key: str
    provider: str
    label: str = ""  # human-readable label (e.g. "account-1")
    exhausted_until: float = 0.0  # timestamp when quarantined until
    last_used: float = 0.0
    use_count: int = 0
    error_count: int = 0

    @property
    def is_available(self) -> bool:
        """Check if this credential is currently usable."""
        return time.time() >= self.exhausted_until

    @property
    def is_exhausted(self) -> bool:
        return not self.is_available

    def mark_used(self) -> None:
        self.last_used = time.time()
        self.use_count += 1

    def mark_error(self, cooldown: float = DEFAULT_COOLDOWN) -> None:
        self.error_count += 1
        self.exhausted_until = time.time() + cooldown


@dataclass
class CredentialPool:
    """Round-robin credential pool for a single provider.

    Usage:
        pool = CredentialPool("anthropic")
        pool.add("sk-key1", label="account-1")
        pool.add("sk-key2", label="account-2")

        cred = pool.acquire()  # returns next available key
        try:
            response = await llm_call(cred.key)
            pool.release(cred)
        except RateLimitError:
            pool.exhaust(cred)  # quarantine for cooldown period
    """

    provider: str
    _credentials: list[PooledCredential] = field(default_factory=list)
    _index: int = 0  # round-robin cursor
    _lock: Any = field(default_factory=asyncio.Lock)
    _cooldown: float = DEFAULT_COOLDOWN

    def add(self, key: str, label: str = "") -> PooledCredential:
        """Add a credential to the pool. Returns the added credential."""
        if len(self._credentials) >= MAX_KEYS:
            raise ValueError(f"Max {MAX_KEYS} keys per provider")
        cred = PooledCredential(key=key, provider=self.provider, label=label)
        self._credentials.append(cred)
        logger.info("credential_added", provider=self.provider, label=label)
        return cred

    def remove(self, key: str) -> bool:
        """Remove a credential by key value. Returns True if found."""
        for i, cred in enumerate(self._credentials):
            if cred.key == key:
                self._credentials.pop(i)
                logger.info("credential_removed", provider=self.provider)
                return True
        return False

    async def acquire(self) -> PooledCredential:
        """Get the next available credential (round-robin)."""
        async with self._lock:
            if not self._credentials:
                raise RuntimeError(f"No credentials for provider '{self.provider}'")

            # Try up to one full rotation to find an available key
            for _ in range(len(self._credentials)):
                self._index = (self._index + 1) % len(self._credentials)
                cred = self._credentials[self._index]
                if cred.is_available:
                    cred.mark_used()
                    return cred

            # All keys exhausted — return the one with the shortest remaining cooldown
            best = min(self._credentials, key=lambda c: c.exhausted_until)
            remaining = max(0, best.exhausted_until - time.time())
            if remaining > 0:
                logger.warning(
                    "all_credentials_exhausted",
                    provider=self.provider,
                    best_available_in=f"{remaining:.0f}s",
                )
            best.mark_used()
            return best

    def release(self, cred: PooledCredential) -> None:
        """Release a credential back to the pool (no-op for now)."""
        pass

    def exhaust(self, cred: PooledCredential, cooldown: float | None = None) -> None:
        """Quarantine a credential for the cooldown period."""
        cred.mark_error(cooldown or self._cooldown)
        logger.warning(
            "credential_exhausted",
            provider=self.provider,
            label=cred.label,
            cooldown=f"{cooldown or self._cooldown}s",
        )

    def reset(self) -> None:
        """Reset all credentials (clear exhaustion flags)."""
        for cred in self._credentials:
            cred.exhausted_until = 0.0
        logger.info("credential_pool_reset", provider=self.provider)

    @property
    def available_count(self) -> int:
        return sum(1 for c in self._credentials if c.is_available)

    @property
    def total_count(self) -> int:
        return len(self._credentials)

    def stats(self) -> dict[str, Any]:
        """Return pool statistics."""
        return {
            "provider": self.provider,
            "total": self.total_count,
            "available": self.available_count,
            "exhausted": self.total_count - self.available_count,
            "credentials": [
                {
                    "label": c.label,
                    "available": c.is_available,
                    "use_count": c.use_count,
                    "error_count": c.error_count,
                    "last_used": c.last_used,
                    "exhausted_until": c.exhausted_until if c.is_exhausted else None,
                }
                for c in self._credentials
            ],
        }


class CredentialPoolManager:
    """Manages credential pools for multiple providers.

    Singleton-like manager that tracks pools per provider.
    Used by provider factories to inject credentials.
    """

    def __init__(self) -> None:
        self._pools: dict[str, CredentialPool] = {}

    def get_or_create(self, provider: str) -> CredentialPool:
        """Get or create a credential pool for a provider."""
        if provider not in self._pools:
            self._pools[provider] = CredentialPool(provider=provider)
            logger.debug("pool_created", provider=provider)
        return self._pools[provider]

    def add_key(self, provider: str, key: str, label: str = "") -> None:
        """Add an API key to a provider's pool."""
        pool = self.get_or_create(provider)
        pool.add(key, label)

    async def acquire_key(self, provider: str) -> str:
        """Acquire the next available API key for a provider."""
        pool = self.get_or_create(provider)
        cred = await pool.acquire()
        return cred.key

    def exhaust_key(self, provider: str, key: str, cooldown: float | None = None) -> None:
        """Quarantine a key that hit rate limits."""
        pool = self._pools.get(provider)
        if pool:
            for cred in pool._credentials:
                if cred.key == key:
                    pool.exhaust(cred, cooldown)
                    return

    def stats(self, provider: str | None = None) -> dict:
        """Return stats for one or all pools."""
        if provider:
            pool = self._pools.get(provider)
            return pool.stats() if pool else {}
        return {p: pool.stats() for p, pool in self._pools.items()}

    def reset(self, provider: str | None = None) -> None:
        """Reset exhaustion flags for one or all pools."""
        if provider:
            pool = self._pools.get(provider)
            if pool:
                pool.reset()
        else:
            for pool in self._pools.values():
                pool.reset()


# Global singleton
_global_pool_manager: CredentialPoolManager | None = None


def get_pool_manager() -> CredentialPoolManager:
    """Get or create the global credential pool manager."""
    global _global_pool_manager
    if _global_pool_manager is None:
        _global_pool_manager = CredentialPoolManager()
    return _global_pool_manager
