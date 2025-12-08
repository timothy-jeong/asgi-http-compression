import zlib
from abc import ABC, abstractmethod
from typing import Protocol

try:
    import brotli
except ImportError:
    brotli = None

BROTLI_AVAILABLE = brotli is not None


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
        """스트리밍 압축을 위한 incremental compress"""
        return self._compressor.process(data)

    def flush(self) -> bytes:
        """압축 완료 및 남은 데이터 반환"""
        return self._compressor.finish()
