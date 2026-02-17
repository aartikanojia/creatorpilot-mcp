"""
Redis-based short-term memory store.

Handles:
- Conversation state
- Session-based context
- Temporary caching
- Real-time state management
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from config import config

logger = logging.getLogger(__name__)


class RedisMemoryStore:
    """
    Short-term memory store using Redis.

    Manages ephemeral data with automatic expiration:
    - Active conversation context
    - Session state
    - User preferences cache
    - Recent tool outputs
    """

    # Key prefixes for organization
    PREFIX_CONVERSATION = "conv"
    PREFIX_SESSION = "session"
    PREFIX_CACHE = "cache"

    # Default TTLs (in seconds)
    TTL_CONVERSATION = 3600 * 24  # 24 hours
    TTL_SESSION = 3600 * 2  # 2 hours
    TTL_CACHE = 300  # 5 minutes

    def __init__(self) -> None:
        """Initialize the Redis store."""
        self._client: Optional[Any] = None
        self._connected = False

    async def _ensure_connection(self) -> Any:
        """
        Ensure Redis connection is established.

        Returns:
            Redis client instance
        """
        if self._client is None or not self._connected:
            try:
                import redis.asyncio as redis

                self._client = redis.from_url(
                    config.redis.url,
                    encoding="utf-8",
                    decode_responses=True
                )
                # Test connection
                await self._client.ping()
                self._connected = True
                logger.info("Redis connection established")
            except ImportError:
                logger.warning(
                    "redis package not installed - using in-memory fallback")
                self._client = InMemoryRedisStub()
                self._connected = True
            except Exception as e:
                logger.error(f"Redis connection failed: {e}")
                # Fall back to in-memory store
                self._client = InMemoryRedisStub()
                self._connected = True

        return self._client

    def _make_key(self, prefix: str, *parts: str) -> str:
        """Build a Redis key from parts."""
        return f"mcp:{prefix}:{':'.join(parts)}"

    async def get_conversation_context(
        self,
        user_id: str,
        channel_id: str
    ) -> dict[str, Any]:
        """
        Get the conversation context for a user/channel pair.

        Args:
            user_id: User identifier
            channel_id: Channel identifier

        Returns:
            Dictionary with conversation state and messages
        """
        client = await self._ensure_connection()
        key = self._make_key(self.PREFIX_CONVERSATION, user_id, channel_id)

        try:
            data = await client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Failed to get conversation context: {e}")

        # Return empty context if not found
        return {
            "messages": [],
            "state": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

    async def store_message(
        self,
        user_id: str,
        channel_id: str,
        message: str,
        response: str,
        tools_used: list[str]
    ) -> None:
        """
        Store a conversation turn (message + response).

        Args:
            user_id: User identifier
            channel_id: Channel identifier
            message: User's message
            response: System's response
            tools_used: Tools that were executed
        """
        client = await self._ensure_connection()
        key = self._make_key(self.PREFIX_CONVERSATION, user_id, channel_id)

        # Get existing context
        context = await self.get_conversation_context(user_id, channel_id)

        # Add new messages
        timestamp = datetime.now(timezone.utc).isoformat()
        context["messages"].append({
            "role": "user",
            "content": message,
            "timestamp": timestamp
        })
        context["messages"].append({
            "role": "assistant",
            "content": response,
            "timestamp": timestamp,
            "tools_used": tools_used
        })

        # Trim to last 50 messages to prevent unbounded growth
        if len(context["messages"]) > 50:
            context["messages"] = context["messages"][-50:]

        context["updated_at"] = timestamp

        try:
            await client.setex(
                key,
                self.TTL_CONVERSATION,
                json.dumps(context)
            )
        except Exception as e:
            logger.error(f"Failed to store message: {e}")

    async def get_session_state(
        self,
        user_id: str,
        session_id: str
    ) -> dict[str, Any]:
        """
        Get session state for a user.

        Args:
            user_id: User identifier
            session_id: Session identifier

        Returns:
            Session state dictionary
        """
        client = await self._ensure_connection()
        key = self._make_key(self.PREFIX_SESSION, user_id, session_id)

        try:
            data = await client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Failed to get session state: {e}")

        return {}

    async def set_session_state(
        self,
        user_id: str,
        session_id: str,
        state: dict[str, Any]
    ) -> None:
        """
        Set session state for a user.

        Args:
            user_id: User identifier
            session_id: Session identifier
            state: State dictionary to store
        """
        client = await self._ensure_connection()
        key = self._make_key(self.PREFIX_SESSION, user_id, session_id)

        try:
            await client.setex(
                key,
                self.TTL_SESSION,
                json.dumps(state)
            )
        except Exception as e:
            logger.error(f"Failed to set session state: {e}")

    async def cache_get(self, cache_key: str) -> Optional[Any]:
        """
        Get a cached value.

        Args:
            cache_key: Cache key

        Returns:
            Cached value or None
        """
        client = await self._ensure_connection()
        key = self._make_key(self.PREFIX_CACHE, cache_key)

        try:
            data = await client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Cache get failed: {e}")

        return None

    async def cache_set(
        self,
        cache_key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> None:
        """
        Set a cached value.

        Args:
            cache_key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Optional TTL in seconds (default: TTL_CACHE)
        """
        client = await self._ensure_connection()
        key = self._make_key(self.PREFIX_CACHE, cache_key)
        ttl = ttl or self.TTL_CACHE

        try:
            await client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            logger.error(f"Cache set failed: {e}")

    async def clear_conversation(
        self,
        user_id: str,
        channel_id: str
    ) -> None:
        """
        Clear conversation context for a user/channel.

        Args:
            user_id: User identifier
            channel_id: Channel identifier
        """
        client = await self._ensure_connection()
        key = self._make_key(self.PREFIX_CONVERSATION, user_id, channel_id)

        try:
            await client.delete(key)
        except Exception as e:
            logger.error(f"Failed to clear conversation: {e}")


class InMemoryRedisStub:
    """
    In-memory fallback when Redis is not available.

    Used for development/testing or when Redis connection fails.
    Data is not persisted and will be lost on restart.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, Optional[float]]] = {}

    async def get(self, key: str) -> Optional[str]:
        """Get a value by key."""
        if key in self._store:
            value, expiry = self._store[key]
            if expiry is None or expiry > datetime.now(timezone.utc).timestamp():
                return value
            else:
                del self._store[key]
        return None

    async def setex(self, key: str, ttl: int, value: str) -> None:
        """Set a value with expiry."""
        expiry = datetime.now(timezone.utc).timestamp() + ttl
        self._store[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        self._store.pop(key, None)

    async def incr(self, key: str) -> int:
        """Increment a key's value by 1, creating it if it doesn't exist."""
        if key in self._store:
            value, expiry = self._store[key]
            # Check if expired
            if expiry is not None and expiry <= datetime.now(timezone.utc).timestamp():
                del self._store[key]
                self._store[key] = ("1", None)
                return 1
            # Increment existing value
            new_value = int(value) + 1
            self._store[key] = (str(new_value), expiry)
            return new_value
        else:
            self._store[key] = ("1", None)
            return 1

    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiry on a key."""
        if key in self._store:
            value, _ = self._store[key]
            expiry = datetime.now(timezone.utc).timestamp() + ttl
            self._store[key] = (value, expiry)
            return True
        return False

    async def ping(self) -> bool:
        """Health check."""
        return True
