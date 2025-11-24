import zlib
from abc import ABC, abstractmethod
from typing import Protocol


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
