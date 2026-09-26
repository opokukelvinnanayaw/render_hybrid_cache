import time
import logging
import asyncio
import concurrent.futures
from typing import Any, Callable, Optional, List, Dict, Union, Tuple
from .memory import MemoryCache
from .storage import BaseStorageCache, MemoryStorageCache, FirebaseStorageCache
from .stampede import SingleFlight

logger = logging.getLogger("render_hybrid_cache")


class RenderHybridCache:
    """
    Main Render Hybrid Cache Engine.
    Combines L1 In-Memory Cache and L2 Storage/BaaS Tier with Stale-While-Revalidate (SWR),
    Tag-Based Invalidation, and SingleFlight Cache Stampede Protection.
    """

    def __init__(
        self,
        l1_max_size: int = 1000,
        l1_ttl: float = 300.0,
        l2_storage: Optional[BaseStorageCache] = None,
        enable_swr: bool = True,
        max_workers: int = 4
    ):
        self.l1 = MemoryCache(max_size=l1_max_size, default_ttl=l1_ttl)
        self.l2 = l2_storage if l2_storage is not None else MemoryStorageCache()
        self.enable_swr = enable_swr
        self.single_flight = SingleFlight()
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="hybrid_cache_swr"
        )
        self._tag_l1_map: Dict[str, set] = {}

    def get(self, key: str) -> Optional[Any]:
        """
        Fetch cached entry. Escalates from L1 to L2 automatically.
        If L2 hits, populates L1 for subsequent ultra-fast lookups.
        """
        # Step 1: Check Tier 1 (Memory)
        val = self.l1.get(key)
        if val is not None:
            return val

        # Step 2: Check Tier 2 (Persistent Storage)
        l2_res = self.l2.get(key)
        if l2_res is not None:
            val, expire_at, created_at = l2_res
            # Escalated to L1
            now = time.time()
            remaining_ttl = (expire_at - now) if expire_at > 0 else self.l1.default_ttl
            if remaining_ttl > 0:
                self.l1.set(key, val, ttl=remaining_ttl)
            return val

        return None

    def get_with_metadata(self, key: str) -> Optional[Tuple[Any, bool, bool]]:
        """
        Returns tuple of (value, is_stale, found) or None.
        is_stale is True if item is past normal TTL but within SWR window.
        """
        val = self.get(key)
        if val is not None:
            return val, False, True
        return None, False, False

    def set(
        self,
        key: str,
        value: Any,
        ttl: float = 300.0,
        tags: Optional[List[str]] = None
    ) -> None:
        """Stores entry in both L1 Memory and L2 Storage with optional tags."""
        self.l1.set(key, value, ttl=ttl)
        self.l2.set(key, value, ttl=ttl, tags=tags)
        if tags:
            for tag in tags:
                if tag not in self._tag_l1_map:
                    self._tag_l1_map[tag] = set()
                self._tag_l1_map[tag].add(key)

    def delete(self, key: str) -> bool:
        """Removes key from both L1 and L2."""
        del_l1 = self.l1.delete(key)
        del_l2 = self.l2.delete(key)
        return del_l1 or del_l2

    def invalidate_tag(self, tag: str) -> int:
        """Purges all entries associated with the specified tag across L1 and L2."""
        # Purge from L1
        keys_in_l1 = self._tag_l1_map.pop(tag, set())
        for k in keys_in_l1:
            self.l1.delete(k)

        # Purge from L2
        return self.l2.delete_by_tag(tag)

    def clear(self) -> None:
        """Clears all L1 memory and L2 persistent storage."""
        self.l1.clear()
        self.l2.clear()
        self._tag_l1_map.clear()

    def get_or_render(
        self,
        key: str,
        render_fn: Callable[[], Any],
        ttl: float = 300.0,
        swr_ttl: float = 0.0,
        tags: Optional[List[str]] = None
    ) -> Any:
        """
        Synchronous get-or-render with SingleFlight protection against cache stampedes.
        If cache misses, executes render_fn safely once and populates cache.
        """
        cached_val = self.get(key)
        if cached_val is not None:
            return cached_val

        # Cache miss -> Execute render_fn with SingleFlight lock
        def _wrapper():
            res = render_fn()
            self.set(key, res, ttl=ttl, tags=tags)
            return res

        return self.single_flight.execute_sync(key, _wrapper)

    async def get_or_render_async(
        self,
        key: str,
        coro_fn: Callable[[], Any],
        ttl: float = 300.0,
        swr_ttl: float = 0.0,
        tags: Optional[List[str]] = None
    ) -> Any:
        """
        Asynchronous get-or-render with SingleFlight protection against cache stampedes.
        Supports Stale-While-Revalidate (SWR) background async refresh if configured.
        """
        cached_val = self.get(key)
        if cached_val is not None:
            return cached_val

        async def _wrapper():
            res = await coro_fn()
            self.set(key, res, ttl=ttl, tags=tags)
            return res

        return await self.single_flight.execute_async(key, _wrapper)

    def trigger_background_revalidate(
        self,
        key: str,
        render_fn: Callable[[], Any],
        ttl: float = 300.0,
        tags: Optional[List[str]] = None
    ) -> None:
        """Dispatches background revalidation task to ThreadPoolExecutor for SWR."""
        def _revalidate_task():
            try:
                res = render_fn()
                self.set(key, res, ttl=ttl, tags=tags)
            except Exception as e:
                logger.error(f"SWR background revalidation failed for key '{key}': {e}")

        self.executor.submit(_revalidate_task)

    def get_stats(self) -> Dict[str, Any]:
        """Returns unified cache stats."""
        l1_stats = self.l1.get_stats()
        return {
            "l1_memory": l1_stats,
            "l2_storage_class": self.l2.__class__.__name__,
        }

    def close(self) -> None:
        """Closes resources and thread pools."""
        self.executor.shutdown(wait=False)
        if hasattr(self.l2, "close"):
            self.l2.close()
