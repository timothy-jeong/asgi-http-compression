import pprint
import pytest

from asgi_http_compression.compressors import GzipCompressor
from asgi_http_compression.responder import CompressionResponder


@pytest.fixture
def compressor():
    return GzipCompressor()


class MockSend:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)


async def mock_app(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, World!", "more_body": False})


@pytest.mark.asyncio
async def test_responder_compresses_response(compressor):
    send = MockSend()
    responder = CompressionResponder(
        app=mock_app,
        compressor=compressor,
        minimum_size=5,
        encoding_name="gzip",
    )

    await responder(scope={}, receive=None, send=send)

    assert len(send.messages) == 2
    start_message, body_message = send.messages

    assert start_message["type"] == "http.response.start"
    headers = dict(start_message["headers"])
    assert headers[b"content-encoding"] == b"gzip"
    assert headers[b"vary"] == b"Accept-Encoding"
    assert b"content-length" in headers

    assert body_message["type"] == "http.response.body"
    assert body_message["body"] != b"Hello, World!" 
    assert not body_message["more_body"]

    print("\n--- Captured messages for test_responder_compresses_response ---")
    pprint.pprint(send.messages)
    print("----------------------------------------------------------")


@pytest.mark.asyncio
async def test_responder_skips_small_response(compressor):
    """Test that the responder does not compress a response smaller than minimum_size."""
    send = MockSend()
    responder = CompressionResponder(
        app=mock_app,
        compressor=compressor,
        minimum_size=100,
        encoding_name="gzip",
    )

    await responder(scope={}, receive=None, send=send)

    assert len(send.messages) == 2
    start_message, body_message = send.messages

    headers = dict(start_message["headers"])
    assert b"content-encoding" not in headers
    assert b"vary" not in headers

    assert body_message["body"] == b"Hello, World!" 


async def streaming_app(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"Streaming ", "more_body": True})
    await send({"type": "http.response.body", "body": b"part 2", "more_body": False})


@pytest.mark.asyncio
async def test_responder_streaming_response(compressor):
    send = MockSend()
    responder = CompressionResponder(
        app=streaming_app,
        compressor=compressor,
        minimum_size=1,
        encoding_name="gzip",
    )

    await responder(scope={}, receive=None, send=send)

    assert len(send.messages) == 3
    start_message, body1, body2 = send.messages

    headers = dict(start_message["headers"])
    assert b"content-length" not in headers
    assert headers[b"content-encoding"] == b"gzip"

    assert body1["more_body"]
    assert body2["more_body"] is False


async def app_with_encoding(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"content-encoding", b"identity"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, World!"})


@pytest.mark.asyncio
async def test_responder_respects_existing_content_encoding(compressor):
    send = MockSend()
    responder = CompressionResponder(
        app=app_with_encoding,
        compressor=compressor,
        minimum_size=1,
        encoding_name="gzip",
    )

    await responder(scope={}, receive=None, send=send)

    assert len(send.messages) == 2
    start_message, _ = send.messages

    headers = dict(start_message["headers"])
    assert headers[b"content-encoding"] == b"identity" 
    assert b"vary" not in headers
