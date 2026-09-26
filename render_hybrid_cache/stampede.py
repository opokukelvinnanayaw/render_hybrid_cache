import threading
import asyncio
from typing import Any, Callable, Dict, Optional


class SingleFlight:
    """
    SingleFlight deduplicates in-flight calls for the same key.
    If 100 concurrent requests ask for key 'user:123' at the exact same moment when cache misses,
    only 1 request executes the computation/render, and the other 99 wait and receive the exact same result.
    Supports both sync and async functions.
    """

    def __init__(self):
        self._sync_locks: Dict[str, threading.Lock] = {}
        self._sync_results: Dict[str, Any] = {}
        self._sync_errors: Dict[str, Exception] = {}
        self._main_lock = threading.Lock()

        self._async_futures: Dict[str, asyncio.Future] = {}
        self._async_lock = asyncio.Lock()

    def execute_sync(self, key: str, fn: Callable[[], Any]) -> Any:
        """Executes fn synchronously with single-flight mutex protection."""
        with self._main_lock:
            if key in self._sync_locks:
                lock = self._sync_locks[key]
                is_leader = False
            else:
                lock = threading.Lock()
                self._sync_locks[key] = lock
                is_leader = True

        if not is_leader:
            # Wait for leader to compute
            with lock:
                with self._main_lock:
                    if key in self._sync_errors:
                        raise self._sync_errors[key]
                    return self._sync_results.get(key)

        # Leader executes computation
        with lock:
            try:
                result = fn()
                with self._main_lock:
                    self._sync_results[key] = result
                return result
            except Exception as exc:
                with self._main_lock:
                    self._sync_errors[key] = exc
                raise exc
            finally:
                with self._main_lock:
                    self._sync_locks.pop(key, None)
                    self._sync_results.pop(key, None)
                    self._sync_errors.pop(key, None)

    async def execute_async(self, key: str, coro_fn: Callable[[], Any]) -> Any:
        """Executes coro_fn asynchronously with single-flight deduplication."""
        async with self._async_lock:
            if key in self._async_futures:
                fut = self._async_futures[key]
                is_leader = False
            else:
                fut = asyncio.get_event_loop().create_future()
                self._async_futures[key] = fut
                is_leader = True

        if not is_leader:
            return await fut

        try:
            res = await coro_fn()
            fut.set_result(res)
            return res
        except Exception as exc:
            fut.set_exception(exc)
            raise exc
        finally:
            async with self._async_lock:
                self._async_futures.pop(key, None)
