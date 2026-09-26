"""
Render Hybrid Cache
===================
A high-performance, multi-tier hybrid caching system designed specifically for 
Firebase Backend-as-a-Service (BaaS) integrations, HTML/JSON render caching, and microservices.

Features:
- L1 Fast In-Memory Cache (LRU + TTL)
- L2 Firebase Cloud Firestore / Redis / Storage Cache
- Stale-While-Revalidate (SWR) background async updating
- Tag-based cache invalidation for Firebase mutation hooks
- Single-Flight mutex lock for Cache Stampede protection
- Gzip/JSON/Pickle serialization options
- Sync and Async Decorator support (@hybrid_cache, @render_cache)
- Native Firebase BaaS query adapter (BaaSCacheAdapter)
"""

from .core import RenderHybridCache
from .memory import MemoryCache
from .storage import FirebaseStorageCache, MemoryStorageCache, RedisCache
from .decorators import hybrid_cache, render_cache
from .serializers import JsonSerializer, PickleSerializer, RawSerializer
from .baas import BaaSCacheAdapter

__version__ = "1.0.0"
__all__ = [
    "RenderHybridCache",
    "MemoryCache",
    "FirebaseStorageCache",
    "MemoryStorageCache",
    "RedisCache",
    "hybrid_cache",
    "render_cache",
    "JsonSerializer",
    "PickleSerializer",
    "RawSerializer",
    "BaaSCacheAdapter",
]
