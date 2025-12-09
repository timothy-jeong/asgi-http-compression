from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from asgi_http_compression.compressors import (
    DeflateCompressor,
    GzipCompressor,
    BrotliCompressor,
    ZstdCompressor,
    BROTLI_AVAILABLE,
    ZSTD_AVAILABLE,
)
from asgi_http_compression.responder import CompressionResponder
from asgi_http_compression.types import ASGIApp, Receive, Scope, Send


@functools.lru_cache(maxsize=1024)
def parse_and_select_encoding(
    accept_header: str, available_encodings: tuple[str, ...]
) -> str | None:
    """
    Parses Accept-Encoding header and returns the best match.
    Cached to minimize parsing overhead on repetitive headers.

    available_encodings: sorted by server priority
    """
    if not accept_header:
        return None

    # Fast Path: no q-value
    if ";" not in accept_header:
        candidates = set(part.strip().lower() for part in accept_header.split(","))
        for encoding in available_encodings:
            if encoding in candidates:
                return encoding
        return None

    # Slow Path: parse q-value
    client_preferences: dict[str, float] = {}

    for part in accept_header.split(","):
        if not part:
            continue

        pieces = part.split(";", 1)
        encoding = pieces[0].strip().lower()

        q_value = 1.0
        if len(pieces) > 1:
            param = pieces[1].strip()
            if param.startswith("q="):
                try:
                    q_value = float(param[2:])
                except ValueError:
                    pass

        client_preferences[encoding] = q_value

    # match
    best_encoding = None
    best_q = -1.0

    for encoding in available_encodings:
        q = client_preferences.get(encoding)

        # wildcard
        if q is None and "*" in client_preferences:
            q = client_preferences["*"]

        if q is not None and q > best_q:
            best_q = q
            best_encoding = encoding
            # Early Exit
            if best_q >= 1.0:
                return best_encoding

    if best_q > 0:
        return best_encoding

    return None


class CompressionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        gzip_level: int = 9,
        deflate_level: int = 6,
        brotli_level: int = 4,
        zstd_level: int = 3,
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size

        # NOTE: Register the supported compression methods and their factories
        # (creation functions)
        # NOTE: The order is important: list the ones the server prefers first
        self.compressor_factories: dict[str, Callable[[], Any]] = {}

        if ZSTD_AVAILABLE:
            self.compressor_factories["zstd"] = lambda: ZstdCompressor(level=zstd_level)

        if BROTLI_AVAILABLE:
            self.compressor_factories["br"] = lambda: BrotliCompressor(
                level=brotli_level
            )

        self.compressor_factories["gzip"] = lambda: GzipCompressor(level=gzip_level)
        self.compressor_factories["deflate"] = lambda: DeflateCompressor(
            level=deflate_level
        )

        # tuple for cache
        self.available_encodings = tuple(self.compressor_factories.keys())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        accept_encoding = ""
        for key, value in scope.get("headers", []):
            if key == b"accept-encoding":
                try:
                    accept_encoding = value.decode("latin-1")
                except UnicodeDecodeError:
                    await self.app(scope, receive, send)
                    return
                break

        selected_encoding = parse_and_select_encoding(
            accept_encoding,
            self.available_encodings,
        )

        if not selected_encoding:
            await self.app(scope, receive, send)
            return

        compressor_factory = self.compressor_factories[selected_encoding]
        compressor = compressor_factory()

        responder = CompressionResponder(
            self.app,
            compressor,
            minimum_size=self.minimum_size,
            encoding_name=selected_encoding,
        )

        await responder(scope, receive, send)
