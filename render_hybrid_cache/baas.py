import functools
import logging
from typing import Any, Callable, Optional, List, Dict
from .core import RenderHybridCache
from .decorators import get_default_cache

logger = logging.getLogger("render_hybrid_cache.baas")


class BaaSCacheAdapter:
    """
    Adapter designed to wrap BaaS (Backend-as-a-Service) SDK query calls
    (e.g., Supabase, Firebase Firestore/RTDB, PocketBase, Appwrite, REST clients).
    """

    def __init__(self, cache_instance: Optional[RenderHybridCache] = None, default_ttl: float = 300.0):
        self.cache = cache_instance or get_default_cache()
        self.default_ttl = default_ttl

    def wrap_query(
        self,
        query_name: str,
        query_fn: Callable[[], Any],
        ttl: Optional[float] = None,
        tags: Optional[List[str]] = None
    ) -> Any:
        """
        Executes and caches a synchronous BaaS query execution.

        Example:
            data = adapter.wrap_query(
                "supabase:products:all",
                lambda: supabase.table("products").select("*").execute().data,
                ttl=600,
                tags=["products"]
            )
        """
        effective_ttl = self.default_ttl if ttl is None else ttl
        return self.cache.get_or_render(
            key=f"baas:{query_name}",
            render_fn=query_fn,
            ttl=effective_ttl,
            tags=tags
        )

    async def wrap_query_async(
        self,
        query_name: str,
        query_coro: Callable[[], Any],
        ttl: Optional[float] = None,
        tags: Optional[List[str]] = None
    ) -> Any:
        """
        Executes and caches an asynchronous BaaS query execution.
        """
        effective_ttl = self.default_ttl if ttl is None else ttl
        return await self.cache.get_or_render_async(
            key=f"baas:{query_name}",
            coro_fn=query_coro,
            ttl=effective_ttl,
            tags=tags
        )

    def invalidate(self, tag: str) -> int:
        """Invalidate all cached BaaS query results for a specific tag (e.g. after a mutation)."""
        logger.info(f"Invalidating BaaS cache tag: '{tag}'")
        return self.cache.invalidate_tag(tag)

    def on_mutation(self, mutated_tags: List[str]) -> Dict[str, int]:
        """
        Hook to call after a BaaS database write/update/delete mutation.
        Automatically purges affected cache tags.
        """
        results = {}
        for tag in mutated_tags:
            count = self.invalidate(tag)
            results[tag] = count
        return results
