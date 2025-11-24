from __future__ import annotations

from collections.abc import Callable
from typing import Any

from asgi_http_compression.compressors import DeflateCompressor, GzipCompressor
from asgi_http_compression.responder import CompressionResponder
from asgi_http_compression.types import ASGIApp, Receive, Scope, Send


class CompressionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        gzip_level: int = 9,
        deflate_level: int = 6,
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size

        # NOTE: Register the supported compression methods and their factories
        # (creation functions)
        # NOTE: The order is important: list the ones the server prefers first
        self.compressor_factories: dict[str, Callable[[], Any]] = {}

        self.compressor_factories["gzip"] = lambda: GzipCompressor(level=gzip_level)

        self.compressor_factories["deflate"] = lambda: DeflateCompressor(
            level=deflate_level
        )

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

        selected_encoding = self._select_encoding(accept_encoding)

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

    def _select_encoding(self, accept_header: str) -> str | None:
        if not accept_header:
            return None

        # TODO: In the future, parse q-values and select encoding according to priority
        client_encodings = {
            part.split(";")[0].strip().lower() for part in accept_header.split(",")
        }

        for encoding in self.compressor_factories:
            if encoding in client_encodings:
                return encoding

        return None
