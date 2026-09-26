import json
import pickle
import gzip
from typing import Any, Tuple, Optional


class BaseSerializer:
    """Base interface for cache value serialization."""
    def serialize(self, value: Any) -> bytes:
        raise NotImplementedError

    def deserialize(self, data: bytes) -> Any:
        raise NotImplementedError


class JsonSerializer(BaseSerializer):
    """JSON Serializer with optional Gzip compression for large payloads."""

    def __init__(self, compress: bool = False, min_compress_size: int = 1024):
        self.compress = compress
        self.min_compress_size = min_compress_size

    def serialize(self, value: Any) -> bytes:
        raw_bytes = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
        if self.compress and len(raw_bytes) >= self.min_compress_size:
            return b"GZIP:" + gzip.compress(raw_bytes)
        return b"RAW:" + raw_bytes

    def deserialize(self, data: bytes) -> Any:
        if data.startswith(b"GZIP:"):
            decompressed = gzip.decompress(data[5:])
            return json.loads(decompressed.decode("utf-8"))
        elif data.startswith(b"RAW:"):
            return json.loads(data[4:].decode("utf-8"))
        else:
            # Fallback for plain bytes
            return json.loads(data.decode("utf-8"))


class PickleSerializer(BaseSerializer):
    """Python Pickle Serializer for arbitrary Python objects."""

    def __init__(self, compress: bool = False, min_compress_size: int = 1024):
        self.compress = compress
        self.min_compress_size = min_compress_size

    def serialize(self, value: Any) -> bytes:
        raw_bytes = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        if self.compress and len(raw_bytes) >= self.min_compress_size:
            return b"GZIP:" + gzip.compress(raw_bytes)
        return b"RAW:" + raw_bytes

    def deserialize(self, data: bytes) -> Any:
        if data.startswith(b"GZIP:"):
            decompressed = gzip.decompress(data[5:])
            return pickle.loads(decompressed)
        elif data.startswith(b"RAW:"):
            return pickle.loads(data[4:])
        else:
            return pickle.loads(data)


class RawSerializer(BaseSerializer):
    """Raw string/HTML/bytes serializer without structured conversion."""

    def serialize(self, value: Any) -> bytes:
        if isinstance(value, str):
            return value.encode("utf-8")
        elif isinstance(value, bytes):
            return value
        else:
            return str(value).encode("utf-8")

    def deserialize(self, data: bytes) -> str:
        return data.decode("utf-8")
