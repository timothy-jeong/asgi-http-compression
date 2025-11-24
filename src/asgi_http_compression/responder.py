from __future__ import annotations


from asgi_http_compression.compressors import Compressor
from asgi_http_compression.types import ASGIApp, Message, Receive, Send, Scope



class CompressionResponder:

    def __init__(
        self,
        app: ASGIApp,
        compressor: Compressor,
        minimum_size: int,
        encoding_name: str,
    ) -> None:
        self.app = app
        self.compressor = compressor
        self.minimum_size = minimum_size
        self.encoding_name = encoding_name

        self.send: Send = self.unattached_send
        self.initial_message: Message = {}
        self.started = False
        self.content_encoding_set = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.send = send
        await self.app(scope, receive, self.send_with_compression)

    async def send_with_compression(self, message: Message) -> None:
        message_type = message["type"]

        if message_type == "http.response.start":
            self.initial_message = message
            headers = message.get("headers", [])

            for key, value in headers:
                if key.lower() == b"content-encoding":
                    self.content_encoding_set = True
                    break

        elif message_type == "http.response.body":
            body = message.get("body", b"")
            more_body = message.get("more_body", False)

            if self.content_encoding_set:
                if not self.started:
                    self.started = True
                    await self.send(self.initial_message)
                await self.send(message)
                return

            if not self.started:
                self.started = True

                if len(body) < self.minimum_size and not more_body:
                    await self.send(self.initial_message)
                    await self.send(message)
                    return

                headers = list(self.initial_message.get("headers", []))
                headers.append((b"content-encoding", self.encoding_name.encode()))
                headers.append((b"vary", b"Accept-Encoding"))

                compressed_body = self.compressor.compress(body)

                if not more_body:
                    compressed_body += self.compressor.flush()
                    self._update_content_length(headers, len(compressed_body))
                else:
                    self._remove_content_length(headers)

                self.initial_message["headers"] = headers

                await self.send(self.initial_message)
                await self.send(
                    {
                        "type": "http.response.body",
                        "body": compressed_body,
                        "more_body": more_body,
                    }
                )

            else:
                compressed_body = self.compressor.compress(body)
                if not more_body:
                    compressed_body += self.compressor.flush()

                await self.send(
                    {
                        "type": "http.response.body",
                        "body": compressed_body,
                        "more_body": more_body,
                    }
                )

    def _update_content_length(self, headers: list, length: int) -> None:
        found = False
        for i, (key, _) in enumerate(headers):
            if key.lower() == b"content-length":
                headers[i] = (key, str(length).encode())
                found = True
                break
        if not found:
            headers.append((b"content-length", str(length).encode()))

    def _remove_content_length(self, headers: list) -> None:
        headers[:] = [h for h in headers if h[0].lower() != b"content-length"]

    async def unattached_send(self, message: Message) -> None:
        raise RuntimeError("send awaitable not set")
