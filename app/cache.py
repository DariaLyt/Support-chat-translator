"""Cache a translation so the same sentence is not sent to the model twice."""

import hashlib
import json
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError


def cache_key(model: str, source: str, target: str, text: str) -> str:
    """Hash of the model, source language, target language, and original text."""
    material = json.dumps(
        [model, source, target, text], ensure_ascii=False, separators=(",", ":")
    )
    return "translate:" + hashlib.sha256(material.encode()).hexdigest()


class TranslationCache(Protocol):
    def get(self, key: str) -> str | None:
        """Return the cached translation, or None on a miss."""

    def set(self, key: str, translation: str, ttl_seconds: int) -> None:
        """Store a translation until the TTL expires."""


class MemoryTranslationCache:
    """Test double. Production uses RedisTranslationCache."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, translation: str, ttl_seconds: int) -> None:
        self.values[key] = translation
        self.ttls[key] = ttl_seconds


class RedisCommands(Protocol):
    def get(self, key: str) -> str | None:
        """Return a cached value."""

    def set(self, key: str, value: str, ex: int) -> object:
        """Store a value with a TTL in seconds."""


class RedisTranslationCache:
    def __init__(self, url: str, client: RedisCommands | None = None) -> None:
        self._redis = client or Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> str | None:
        try:
            value = self._redis.get(key)
        except RedisError:
            return None
        if value is None:
            return None
        return str(value)

    def set(self, key: str, translation: str, ttl_seconds: int) -> None:
        try:
            self._redis.set(key, translation, ex=ttl_seconds)
        except RedisError:
            return None

    def ttl(self, key: str) -> int:
        return int(self._redis.ttl(key))

    def delete(self, key: str) -> None:
        self._redis.delete(key)
