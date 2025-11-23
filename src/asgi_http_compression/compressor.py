import zlib
from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CompressorProtocol(Protocol):
    """
    Interface definition for a compressor.
    Any class implementing these methods can be used by the middleware.
    """
    def compress(self, data: bytes) -> bytes: ...
    def flush(self) -> bytes: ...


class BaseCompressor(ABC):
    """
    Helper base class to enforce implementation of abstract methods.
    """
    ENCODING: str = ""

    def __init__(self, level: int = 6, **kwargs: Any) -> None:
        """
        Common initializer.

        :param level: Compression level (1-9 for zlib).
        :param kwargs: Extra arguments (e.g., 'threads') for future compatibility.
                       Currently ignored by Gzip/Deflate.
        """
        self.level = level
        self.kwargs = kwargs

    @abstractmethod
    def compress(self, data: bytes) -> bytes:
        """Compresses a chunk of data."""
        raise NotImplementedError

    @abstractmethod
    def flush(self) -> bytes:
        """Flushes any remaining data from the internal buffer."""
        raise NotImplementedError


class GzipCompressor(BaseCompressor):
    """
    Standard Gzip compressor using zlib.
    """
    ENCODING = "gzip"

    def __init__(self, level: int = 6, **kwargs: Any) -> None:
        super().__init__(level, **kwargs)
        # wbits=31 (16+15): zlib generates gzip header & trailer
        self.compressor = zlib.compressobj(level, zlib.DEFLATED, 31)

    def compress(self, data: bytes) -> bytes:
        return self.compressor.compress(data)

    def flush(self) -> bytes:
        return self.compressor.flush()


class DeflateCompressor(BaseCompressor):
    """
    Standard Deflate compressor using zlib.
    """
    ENCODING = "deflate"

    def __init__(self, level: int = 6, **kwargs: Any) -> None:
        super().__init__(level, **kwargs)
        # wbits=-15: raw deflate (no headers)
        self.compressor = zlib.compressobj(level, zlib.DEFLATED, -15)

    def compress(self, data: bytes) -> bytes:
        return self.compressor.compress(data)

    def flush(self) -> bytes:
        return self.compressor.flush()
