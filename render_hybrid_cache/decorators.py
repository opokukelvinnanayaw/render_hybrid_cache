import functools
import inspect
import asyncio
from typing import Callable, Optional, List, Union, Any
from .core import RenderHybridCache

# Global default instance
_default_hybrid_cache: Optional[RenderHybridCache] = None


def get_default_cache() -> RenderHybridCache:
    global _default_hybrid_cache
    if _default_hybrid_cache is None:
        _default_hybrid_cache = RenderHybridCache()
    return _default_hybrid_cache


def _build_cache_key(func: Callable, args: tuple, kwargs: dict, key_builder: Optional[Callable] = None) -> str:
    if key_builder is not None:
        return key_builder(*args, **kwargs)
    arg_strs = [repr(a) for a in args]
    kwarg_strs = [f"{k}={repr(v)}" for k, v in sorted(kwargs.items())]
    joined = ",".join(arg_strs + kwarg_strs)
    return f"{func.__module__}.{func.__qualname__}({joined})"


def hybrid_cache(
    ttl: float = 300.0,
    swr_ttl: float = 0.0,
    tags: Optional[Union[List[str], Callable[..., List[str]]]] = None,
    key_builder: Optional[Callable] = None,
    cache_instance: Optional[RenderHybridCache] = None
):
    """
    Decorator to wrap sync or async functions with Render Hybrid Caching.

    Usage:
        @hybrid_cache(ttl=60, tags=["user_profile"])
        def get_user_profile(user_id: int):
            return db.fetch(user_id)

        @hybrid_cache(ttl=120)
        async def render_dashboard(user_id: int):
            return await generate_html(user_id)
    """

    def decorator(func: Callable):
        is_coroutine = inspect.iscoroutinefunction(func)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            cache = cache_instance or get_default_cache()
            cache_key = _build_cache_key(func, args, kwargs, key_builder)

            # Resolve dynamic tags
            resolved_tags = tags(*args, **kwargs) if callable(tags) else tags

            return cache.get_or_render(
                key=cache_key,
                render_fn=lambda: func(*args, **kwargs),
                ttl=ttl,
                swr_ttl=swr_ttl,
                tags=resolved_tags
            )

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache = cache_instance or get_default_cache()
            cache_key = _build_cache_key(func, args, kwargs, key_builder)

            resolved_tags = tags(*args, **kwargs) if callable(tags) else tags

            return await cache.get_or_render_async(
                key=cache_key,
                coro_fn=lambda: func(*args, **kwargs),
                ttl=ttl,
                swr_ttl=swr_ttl,
                tags=resolved_tags
            )

        return async_wrapper if is_coroutine else sync_wrapper

    return decorator


def render_cache(
    ttl: float = 600.0,
    tags: Optional[Union[List[str], Callable[..., List[str]]]] = None,
    key_builder: Optional[Callable] = None,
    cache_instance: Optional[RenderHybridCache] = None
):
    """
    Specialized alias decorator specifically for HTML/JSON View/Template Render functions.
    """
    return hybrid_cache(
        ttl=ttl,
        tags=tags,
        key_builder=key_builder,
        cache_instance=cache_instance
    )
