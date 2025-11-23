import re

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from asgi_http_compression.compressor import (
    CompressorProtocol,
    DeflateCompressor,
    GzipCompressor,
)


class CompressionMiddleware:
    """
    Performs content negotiation and starts the appropriate Responder.
    """

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        threads: int = 0,
        write_checksum: bool = False,
        write_content_size: bool = True,
        excluded_handlers: list | None = None,
        compression_level: int = 6,
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.excluded_handlers = [re.compile(path) for path in excluded_handlers or []]
        self.compressor_map: dict[str, type[CompressorProtocol]] = {
            "gzip": GzipCompressor,
            "deflate": DeflateCompressor,
        }
        self.preferred_encodings = ["gzip", "deflate"]
        self.compressor_kwargs = {
            "level": compression_level,
            "threads": threads,
            "write_checksum": write_checksum,
            "write_content_size": write_content_size,
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. Check for excluded handlers
        if any(pattern.search(scope["path"]) for pattern in self.excluded_handlers):
            await self.app(scope, receive, send)
            return

        # 2. Content negotiation
        headers = Headers(scope=scope)
        accept_encoding = headers.get("accept-encoding", "")
        chosen_encoding = self.negotiate_encoding(accept_encoding)

        # If explicit identity or no supported encoding found
        if not chosen_encoding:
            await self.app(scope, receive, send)
            return

        # 3. Start Responder
        responder = CompressionResponder(
            self.app,
            send,
            self.compressor_map[chosen_encoding],
            self.compressor_kwargs,
            self.minimum_size,
            chosen_encoding,
        )
        await responder(scope, receive)

    def negotiate_encoding(self, accept_encoding: str) -> str | None:
        """
        Selects an encoding based on the Accept-Encoding header.
        Current Strategy: Server Preference (Ignores q-values).
        """
        # 1. Parse headers: "gzip;q=0.8, deflate" -> {"gzip", "deflate"}
        parsed_encodings = {
            enc.strip().split(";")[0]
            for enc in accept_encoding.split(",")
            if enc.strip()  # 빈 문자열(예: 'gzip, , deflate') 방어
        }

        # 2. Match with server preferences
        for encoding in self.preferred_encodings:
            if encoding in parsed_encodings:
                return encoding

        # 3. Explicit identity check
        if "identity" in parsed_encodings:
            return None

        # 4. Wildcard (*) handling
        if "*" in parsed_encodings and self.preferred_encodings:
            return self.preferred_encodings[0]

        return None


class CompressionResponder:
    """
    Handles buffering for single-shot responses to calculate Content-Length,
    or streams directly for chunked responses.
    """
    def __init__(
        self,
        app: ASGIApp,
        send: Send,
        compressor_cls: type[CompressorProtocol],
        compressor_kwargs: dict,
        minimum_size: int,
        encoding: str,
    ) -> None:
        self.app = app
        self.original_send = send
        self.compressor_cls = compressor_cls
        self.compressor_kwargs = compressor_kwargs
        self.minimum_size = minimum_size
        self.encoding = encoding

        self.compressor: CompressorProtocol | None = None
        self.started = False
        self.headers: MutableHeaders | None = None
        self.initial_status: int = 200

    async def __call__(self, scope: Scope, receive: Receive) -> None:
        await self.app(scope, receive, self.send)

    async def send(self, message: Message) -> None:
        message_type = message["type"]

        if message_type == "http.response.start":
            # Capture status and headers, but don't send yet
            self.initial_status = message.get("status", 200)
            self.headers = MutableHeaders(scope={"headers": message["headers"]})

            # Check if we should skip compression (already encoded or event-stream)
            if "content-encoding" in self.headers or self.headers.get("content-type") == "text/event-stream":
                self.compressor = None
                await self.original_send(message)
                self.started = True

        elif message_type == "http.response.body" and not self.started:
            # First body chunk arrived. Decide strategy.
            body = message.get("body", b"")
            more_body = message.get("more_body", False)

            if not more_body:
                # [Strategy 1] Single Shot: Calculate Content-Length
                if len(body) < self.minimum_size:
                    await self.send_uncompressed(body)
                else:
                    await self.send_compressed_single_shot(body)
            else:
                # [Strategy 2] Streaming: Chunked Transfer (No Content-Length)
                await self.start_streaming_compression(body)

        elif message_type == "http.response.body" and self.started:
            # Subsequent chunks for streaming responses
            if self.compressor:
                await self.compress_and_send(message)
            else:
                await self.original_send(message)

    async def send_compressed_single_shot(self, body: bytes) -> None:
        """
        Compresses the entire body at once, calculates new Content-Length,
        and sends headers + body.
        """
        if self.headers is None:
            raise RuntimeError("Headers not set")

        # 1. Compress full body
        compressor = self.compressor_cls(**self.compressor_kwargs)
        compressed_body = compressor.compress(body) + compressor.flush()

        # 2. Update Headers
        self.headers["Content-Encoding"] = self.encoding
        self.headers.add_vary("Accept-Encoding")
        self.headers["Content-Length"] = str(len(compressed_body))

        # 3. Send Start
        await self.original_send({
            "type": "http.response.start",
            "status": self.initial_status,
            "headers": self.headers.raw,
        })

        # 4. Send Body
        self.started = True
        await self.original_send({
            "type": "http.response.body",
            "body": compressed_body,
            "more_body": False,
        })

    async def start_streaming_compression(self, body: bytes) -> None:
        """
        Starts streaming compression. Removes Content-Length to trigger chunked encoding.
        """
        if self.headers is None:
            raise RuntimeError("Headers not set")

        self.compressor = self.compressor_cls(**self.compressor_kwargs)

        # Update Headers
        self.headers["Content-Encoding"] = self.encoding
        self.headers.add_vary("Accept-Encoding")

        # Remove Content-Length because we don't know the final size yet
        if "content-length" in self.headers:
            del self.headers["content-length"]

        # Send Start
        await self.original_send({
            "type": "http.response.start",
            "status": self.initial_status,
            "headers": self.headers.raw,
        })

        self.started = True

        # Compress and send the first chunk
        await self.compress_and_send({"type": "http.response.body", "body": body, "more_body": True})

    async def send_uncompressed(self, body: bytes) -> None:
        if self.headers is None:
            raise RuntimeError("Headers not set")

        await self.original_send({
            "type": "http.response.start",
            "status": self.initial_status,
            "headers": self.headers.raw,
        })
        self.started = True
        await self.original_send({"type": "http.response.body", "body": body, "more_body": False,})

    async def compress_and_send(self, message: Message) -> None:
        body = message.get("body", b"")
        more_body = message.get("more_body", False)

        compressed_data = self.compressor.compress(body)
        if compressed_data:
            await self.send_bytes(compressed_data, more_body=True)

        if not more_body:
            flush_data = self.compressor.flush()
            if flush_data:
                await self.send_bytes(flush_data, more_body=False)
            else:
                await self.send_bytes(b"", more_body=False)

    async def send_bytes(self, data: bytes, more_body: bool) -> None:
        await self.original_send({
            "type": "http.response.body",
            "body": data,
            "more_body": more_body,
        })
