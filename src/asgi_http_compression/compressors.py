import zlib
from abc import ABC, abstractmethod
from typing import Protocol

try:
    import brotli
except ImportError:
    brotli = None

try:
    import zstandard
except ImportError:
    try:
        from compression.zstd import ZstdCompressor, CompressionParameter
    except ImportError:
        zstandard = None

BROTLI_AVAILABLE = brotli is not None
ZSTD_AVAILABLE = zstandard is not None


class Compressor(Protocol):
    def compress(self, data: bytes) -> bytes: ...

    def flush(self) -> bytes: ...


class BaseCompressor(ABC):
    @abstractmethod
    def compress(self, data: bytes) -> bytes: ...

    @abstractmethod
    def flush(self) -> bytes: ...


class GzipCompressor(BaseCompressor):
    def __init__(self, level: int = 9) -> None:
        self._compressobj = zlib.compressobj(level=level, wbits=15 + 16)

    def compress(self, data: bytes) -> bytes:
        return self._compressobj.compress(data)

    def flush(self) -> bytes:
        return self._compressobj.flush()


class DeflateCompressor(BaseCompressor):
    def __init__(self, level: int = 6) -> None:
        self._compressobj = zlib.compressobj(level=level)

    def compress(self, data: bytes) -> bytes:
        return self._compressobj.compress(data)

    def flush(self) -> bytes:
        return self._compressobj.flush()


class BrotliCompressor(BaseCompressor):
    def __init__(self, level: int = 4) -> None:
        if brotli is None:
            raise ImportError(
                "brotli extra is required. Install with: pip install 'asgi-http-compression[brotli]'"
            )
        self._compressor = brotli.Compressor(quality=level)

    def compress(self, data: bytes) -> bytes:
        return self._compressor.process(data)

    def flush(self) -> bytes:
        return self._compressor.finish()


class ZstdCompressor(BaseCompressor):
    # Class-level cache for ZstdCompressor configuration objects
    _compressors_cache: dict[int, "zstandard.ZstdCompressor"] = {}

    def __init__(self, level: int = 3) -> None:
        if zstandard is None:
            raise ImportError(
                "zstandard extra is required. Install with: pip install 'asgi-http-compression[zstd]'"
            )
        
        if level not in self._compressors_cache:
            self._compressors_cache[level] = zstandard.ZstdCompressor(
                level=level, write_content_size=False
            )

        self._compressor = self._compressors_cache[level].compressobj()

    def compress(self, data: bytes) -> bytes:
        return self._compressor.compress(data)

    def flush(self) -> bytes:
        return self._compressor.flush()
