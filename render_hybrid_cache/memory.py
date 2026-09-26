import time
import threading
from collections import OrderedDict
from typing import Any, Optional, Dict, Tuple, List


class MemoryCache:
    """
    Tier 1 (L1) In-Memory Cache with LRU Eviction and Per-Key TTL.
    Thread-safe implementation using RLock.
    """

    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, Tuple[Any, float, float]] = OrderedDict()
        # Storage format: key -> (value, expire_timestamp, created_timestamp)
        self._lock = threading.RLock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def get(self, key: str) -> Optional[Any]:
        """Fetch item from memory cache. Returns None if missing or expired."""
        with self._lock:
            if key not in self._cache:
                self.misses += 1
                return None

            val, exp_time, created_at = self._cache[key]

            # Check expiration
            if exp_time > 0 and time.time() > exp_time:
                del self._cache[key]
                self.misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self.hits += 1
            return val

    def get_meta(self, key: str) -> Optional[Tuple[Any, float, float]]:
        """
        Returns (value, expire_timestamp, created_timestamp) or None.
        Does not count as a miss if expired, but removes if expired.
        """
        with self._lock:
            if key not in self._cache:
                return None

            val, exp_time, created_at = self._cache[key]
            if exp_time > 0 and time.time() > exp_time:
                del self._cache[key]
                return None

            self._cache.move_to_end(key)
            return val, exp_time, created_at

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Insert or update a key in memory cache with optional TTL in seconds."""
        with self._lock:
            effective_ttl = self.default_ttl if ttl is None else ttl
            now = time.time()
            exp_time = (now + effective_ttl) if effective_ttl > 0 else 0.0

            if key in self._cache:
                del self._cache[key]

            # Check capacity and evict LRU if needed
            while len(self._cache) >= self.max_size:
                oldest_key, _ = self._cache.popitem(last=False)
                self.evictions += 1

            self._cache[key] = (value, exp_time, now)

    def delete(self, key: str) -> bool:
        """Remove a key from memory cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all stored entries in memory cache."""
        with self._lock:
            self._cache.clear()

    def purge_expired(self) -> int:
        """Clean up expired entries. Returns count of purged keys."""
        with self._lock:
            now = time.time()
            expired_keys = [
                k for k, (_, exp, _) in self._cache.items()
                if exp > 0 and now > exp
            ]
            for k in expired_keys:
                del self._cache[k]
            return len(expired_keys)

    def keys(self) -> List[str]:
        """Return list of active non-expired keys."""
        with self._lock:
            self.purge_expired()
            return list(self._cache.keys())

    def get_stats(self) -> Dict[str, Any]:
        """Return cache usage statistics."""
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "evictions": self.evictions,
                "hit_rate": (
                    round(self.hits / (self.hits + self.misses), 4)
                    if (self.hits + self.misses) > 0 else 0.0
                )
            }
