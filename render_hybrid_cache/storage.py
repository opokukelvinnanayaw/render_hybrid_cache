import os
import time
import threading
from typing import Any, Optional, Dict, Tuple, List
from .serializers import BaseSerializer, PickleSerializer


class BaseStorageCache:
    """Interface for Tier 2 (L2) Persistent / Remote Caches."""
    def get(self, key: str) -> Optional[Tuple[Any, float, float]]:
        """Returns (value, expire_timestamp, created_timestamp) or None."""
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl: float = 3600.0, tags: Optional[List[str]] = None) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> bool:
        raise NotImplementedError

    def delete_by_tag(self, tag: str) -> int:
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError

    def purge_expired(self) -> int:
        raise NotImplementedError


class MemoryStorageCache(BaseStorageCache):
    """
    In-memory Tier 2 Storage Cache used as a zero-external-dependency fallback.
    """
    def __init__(self, serializer: Optional[BaseSerializer] = None):
        self.serializer = serializer or PickleSerializer(compress=True)
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Tuple[Any, float, float]]:
        with self._lock:
            data = self._store.get(key)
            if not data:
                return None
            now = time.time()
            if data["expire_at"] > 0 and now > data["expire_at"]:
                del self._store[key]
                return None
            val = self.serializer.deserialize(data["val"])
            return val, data["expire_at"], data["created_at"]

    def set(self, key: str, value: Any, ttl: float = 3600.0, tags: Optional[List[str]] = None) -> None:
        with self._lock:
            now = time.time()
            expire_at = (now + ttl) if ttl > 0 else 0.0
            val_bytes = self.serializer.serialize(value)
            self._store[key] = {
                "val": val_bytes,
                "expire_at": expire_at,
                "created_at": now,
                "tags": tags or []
            }

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def delete_by_tag(self, tag: str) -> int:
        with self._lock:
            to_delete = [k for k, v in self._store.items() if tag in v.get("tags", [])]
            for k in to_delete:
                del self._store[k]
            return len(to_delete)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def purge_expired(self) -> int:
        with self._lock:
            now = time.time()
            to_delete = [k for k, v in self._store.items() if v["expire_at"] > 0 and now > v["expire_at"]]
            for k in to_delete:
                del self._store[k]
            return len(to_delete)


class FirebaseStorageCache(BaseStorageCache):
    """
    Tier 2 (L2) Cloud Storage Cache backed by Google Cloud Firebase Firestore.
    Integrates directly with Firebase to persist cached data across cloud instances.
    """

    def __init__(
        self,
        collection_name: str = "_render_hybrid_cache",
        serializer: Optional[BaseSerializer] = None,
        db=None
    ):
        self.collection_name = collection_name
        self.serializer = serializer or PickleSerializer(compress=True)
        self._db = db

    def _get_db(self):
        if self._db is not None:
            return self._db
        try:
            import firebase_admin  # type: ignore
            from firebase_admin import firestore  # type: ignore
            if firebase_admin._apps:
                self._db = firestore.client()
                return self._db
        except Exception:
            pass
        return None

    def get(self, key: str) -> Optional[Tuple[Any, float, float]]:
        db = self._get_db()
        if db is None:
            return None
        try:
            doc_ref = db.collection(self.collection_name).document(key)
            doc = doc_ref.get()
            if not doc.exists:
                return None
            data = doc.to_dict()
            expire_at = data.get("expire_at", 0.0)
            created_at = data.get("created_at", time.time())
            now = time.time()
            if expire_at > 0 and now > expire_at:
                self.delete(key)
                return None
            val_bytes = data.get("val")
            if isinstance(val_bytes, str):
                import base64
                val_bytes = base64.b64decode(val_bytes)
            val = self.serializer.deserialize(val_bytes)
            return val, expire_at, created_at
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: float = 3600.0, tags: Optional[List[str]] = None) -> None:
        db = self._get_db()
        if db is None:
            return
        try:
            now = time.time()
            expire_at = (now + ttl) if ttl > 0 else 0.0
            val_bytes = self.serializer.serialize(value)
            import base64
            val_b64 = base64.b64encode(val_bytes).decode("utf-8")
            doc_data = {
                "key": key,
                "val": val_b64,
                "expire_at": expire_at,
                "created_at": now,
                "tags": tags or []
            }
            db.collection(self.collection_name).document(key).set(doc_data)
        except Exception:
            pass

    def delete(self, key: str) -> bool:
        db = self._get_db()
        if db is None:
            return False
        try:
            db.collection(self.collection_name).document(key).delete()
            return True
        except Exception:
            return False

    def delete_by_tag(self, tag: str) -> int:
        db = self._get_db()
        if db is None:
            return 0
        try:
            query = db.collection(self.collection_name).where("tags", "array_contains", tag)
            docs = query.get()
            count = 0
            for d in docs:
                d.reference.delete()
                count += 1
            return count
        except Exception:
            return 0

    def clear(self) -> None:
        db = self._get_db()
        if db is None:
            return
        try:
            docs = db.collection(self.collection_name).stream()
            for d in docs:
                d.reference.delete()
        except Exception:
            pass

    def purge_expired(self) -> int:
        db = self._get_db()
        if db is None:
            return 0
        try:
            now = time.time()
            query = db.collection(self.collection_name).where("expire_at", ">", 0).where("expire_at", "<", now)
            docs = query.get()
            count = 0
            for d in docs:
                d.reference.delete()
                count += 1
            return count
        except Exception:
            return 0


class RedisCache(BaseStorageCache):
    """
    Optional Tier 2 (L2) Distributed Cache using Redis (via redis-py).
    Falls back gracefully if redis is not installed.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0", serializer: Optional[BaseSerializer] = None):
        self.serializer = serializer or PickleSerializer(compress=True)
        try:
            import importlib
            redis = importlib.import_module("redis")
            self.client = redis.from_url(redis_url)
        except ImportError:
            raise ImportError("redis package is required to use RedisCache. Install via `pip install redis` or `pip install render-hybrid-cache[redis]`.")

    def get(self, key: str) -> Optional[Tuple[Any, float, float]]:
        data = self.client.get(f"render_cache:{key}")
        if not data:
            return None
        meta = self.client.hgetall(f"render_cache_meta:{key}")
        expire_at = float(meta.get(b"expire_at", 0.0))
        created_at = float(meta.get(b"created_at", time.time()))
        val = self.serializer.deserialize(data)
        return val, expire_at, created_at

    def set(self, key: str, value: Any, ttl: float = 3600.0, tags: Optional[List[str]] = None) -> None:
        now = time.time()
        expire_at = (now + ttl) if ttl > 0 else 0.0
        val_bytes = self.serializer.serialize(value)
        rkey = f"render_cache:{key}"
        rmeta = f"render_cache_meta:{key}"

        if ttl > 0:
            self.client.setex(rkey, int(ttl), val_bytes)
            self.client.hset(rmeta, mapping={"expire_at": expire_at, "created_at": now})
            self.client.expire(rmeta, int(ttl))
        else:
            self.client.set(rkey, val_bytes)
            self.client.hset(rmeta, mapping={"expire_at": expire_at, "created_at": now})

        if tags:
            for tag in tags:
                self.client.sadd(f"render_tag:{tag}", key)

    def delete(self, key: str) -> bool:
        res = self.client.delete(f"render_cache:{key}", f"render_cache_meta:{key}")
        return res > 0

    def delete_by_tag(self, tag: str) -> int:
        tag_key = f"render_tag:{tag}"
        keys = self.client.smembers(tag_key)
        if not keys:
            return 0
        pipe = self.client.pipeline()
        for k in keys:
            decoded_key = k.decode("utf-8") if isinstance(k, bytes) else k
            pipe.delete(f"render_cache:{decoded_key}", f"render_cache_meta:{decoded_key}")
        pipe.delete(tag_key)
        results = pipe.execute()
        return len(keys)

    def clear(self) -> None:
        keys = self.client.keys("render_cache:*") + self.client.keys("render_cache_meta:*") + self.client.keys("render_tag:*")
        if keys:
            self.client.delete(*keys)

    def purge_expired(self) -> int:
        return 0

