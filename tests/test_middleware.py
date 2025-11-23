import zlib

import pytest
from httpx import AsyncClient


# --- Helper to decompress ---
def decompress_gzip(data: bytes) -> bytes:
    # 16 + zlib.MAX_WBITS means automatic header detection (gzip/zlib)
    return zlib.decompress(data, 16 + zlib.MAX_WBITS)

def decompress_deflate(data: bytes) -> bytes:
    try:
        return zlib.decompress(data, -zlib.MAX_WBITS)
    except zlib.error:
        return zlib.decompress(data)

@pytest.mark.asyncio
async def test_skip_small_response(client: AsyncClient):
    """Should not compress responses smaller than minimum_size."""
    response = await client.get("/small", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.text == "tiny"
    # Starlette/Uvicorn may automatically add Content-Length


@pytest.mark.asyncio
async def test_compress_large_response_gzip(client: AsyncClient):
    """
    [Single Shot] Large response should be compressed with Gzip,
    and Content-Length must be set correctly by our middleware.
    """
    response = await client.get("/large", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"

    # [Verify] Content-Length must exist (Single shot logic)
    assert "content-length" in response.headers

    # [Verify] Actual body size must match Content-Length header
    content_length = int(response.headers["content-length"])
    assert len(response.content) == content_length

    # [Verify] Decompress and check original data
    decompressed = decompress_gzip(response.content)
    assert decompressed == b"A" * 1000


@pytest.mark.asyncio
async def test_compress_streaming_response(client: AsyncClient):
    """
    [Streaming] Response should be compressed,
    but Content-Length header must be absent (Transfer-Encoding: chunked).
    """
    response = await client.get("/stream", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"

    # [Verify] Content-Length must be removed for streaming
    assert "content-length" not in response.headers

    # [Verify] Check if data arrived compressed
    decompressed = decompress_gzip(response.content)
    expected_chunk = b"chunk1" * 100 + b"chunk2" * 100 + b"chunk3" * 100
    assert decompressed == expected_chunk


@pytest.mark.asyncio
async def test_negotiation_deflate(client: AsyncClient):
    """Should compress with Deflate when requested."""
    response = await client.get("/large", headers={"Accept-Encoding": "deflate"})

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "deflate"

    decompressed = decompress_deflate(response.content)
    assert decompressed == b"A" * 1000


@pytest.mark.asyncio
async def test_identity_encoding(client: AsyncClient):
    """Should not compress when identity is requested."""
    response = await client.get("/large", headers={"Accept-Encoding": "identity"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.text == "A" * 1000


@pytest.mark.asyncio
async def test_excluded_path(client: AsyncClient):
    """Should not compress excluded paths (regex match)."""
    response = await client.get("/skip/this", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.text == "B" * 1000


@pytest.mark.asyncio
async def test_status_code_preservation(client: AsyncClient):
    """Status code must be preserved even for small error responses without compression."""
    response = await client.get("/error", headers={"Accept-Encoding": "gzip"})

    assert response.status_code == 400
    assert response.text == "Error occurred"
