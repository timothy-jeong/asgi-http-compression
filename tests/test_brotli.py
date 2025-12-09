import pytest

try:
    import brotli  # type: ignore[import-untyped]
    from asgi_http_compression.compressors import BrotliCompressor

    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False

from asgi_http_compression.responder import CompressionResponder

from test_responder import (
    MockSend,
    app_with_encoding,
    mock_app,
    streaming_app,
)


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_brotli_basic_compression():
    compressor = BrotliCompressor(level=4)
    send = MockSend()
    responder = CompressionResponder(
        app=mock_app,
        compressor=compressor,
        minimum_size=5,
        encoding_name="br",
    )

    await responder(scope={}, receive=None, send=send)

    assert len(send.messages) == 2
    start_message, body_message = send.messages

    headers = dict(start_message["headers"])
    assert headers[b"content-encoding"] == b"br"
    assert headers[b"vary"] == b"Accept-Encoding"
    assert b"content-length" in headers

    compressed_body = body_message["body"]
    decompressed = brotli.decompress(compressed_body)
    assert decompressed == b"Hello, World!"


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_brotli_streaming_response():
    compressor = BrotliCompressor(level=4)
    send = MockSend()
    responder = CompressionResponder(
        app=streaming_app,
        compressor=compressor,
        minimum_size=1,
        encoding_name="br",
    )

    await responder(scope={}, receive=None, send=send)

    assert len(send.messages) == 3
    start_message, body1, body2 = send.messages

    headers = dict(start_message["headers"])
    assert headers[b"content-encoding"] == b"br"
    assert b"content-length" not in headers

    assert body1["more_body"]
    assert body2["more_body"] is False

    full_compressed = body1["body"] + body2["body"]
    decompressed = brotli.decompress(full_compressed)
    assert decompressed == b"Streaming part 2"


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_brotli_respects_existing_content_encoding():
    compressor = BrotliCompressor(level=4)
    send = MockSend()
    responder = CompressionResponder(
        app=app_with_encoding,
        compressor=compressor,
        minimum_size=1,
        encoding_name="br",
    )

    await responder(scope={}, receive=None, send=send)

    assert len(send.messages) == 2
    start_message, _ = send.messages

    headers = dict(start_message["headers"])
    assert headers[b"content-encoding"] == b"identity"
    assert b"vary" not in headers


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_brotli_skips_small_response():
    compressor = BrotliCompressor(level=4)
    send = MockSend()
    responder = CompressionResponder(
        app=mock_app,
        compressor=compressor,
        minimum_size=100,
        encoding_name="br",
    )

    await responder(scope={}, receive=None, send=send)

    assert len(send.messages) == 2
    start_message, body_message = send.messages

    headers = dict(start_message["headers"])
    assert b"content-encoding" not in headers
    assert b"vary" not in headers

    assert body_message["body"] == b"Hello, World!"


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_brotli_incremental_compression():
    compressor = BrotliCompressor(level=4)

    chunk1 = b"First chunk of data. "
    chunk2 = b"Second chunk of data. "
    chunk3 = b"Third chunk of data."

    compressed1 = compressor.compress(chunk1)
    compressed2 = compressor.compress(chunk2)
    compressed3 = compressor.compress(chunk3)
    flushed = compressor.flush()

    full_compressed = compressed1 + compressed2 + compressed3 + flushed
    decompressed = brotli.decompress(full_compressed)

    assert decompressed == chunk1 + chunk2 + chunk3
