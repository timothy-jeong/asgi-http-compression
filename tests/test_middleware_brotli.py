import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

try:
    import brotli  # type: ignore[import-untyped]
    from asgi_http_compression import CompressionMiddleware

    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_middleware_brotli_integration():

    async def hello_handler(request):
        return JSONResponse({"message": "Hello, World! " * 100})

    app = Starlette(
        routes=[Route("/hello", hello_handler, methods=["GET"])],
        middleware=[Middleware(CompressionMiddleware, minimum_size=10, brotli_level=4)],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/hello", headers={"Accept-Encoding": "br"})
        assert resp.headers["content-encoding"] == "br"

        data = resp.json()
        assert data["message"] == "Hello, World! " * 100


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_middleware_brotli_streaming():

    async def stream_handler(request):
        async def gen():
            for i in range(5):
                yield f"chunk-{i},".encode()

        return StreamingResponse(gen(), media_type="text/plain")

    app = Starlette(
        routes=[Route("/stream", stream_handler, methods=["GET"])],
        middleware=[Middleware(CompressionMiddleware, minimum_size=1, brotli_level=4)],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/stream", headers={"Accept-Encoding": "br"})
        assert resp.headers["content-encoding"] == "br"

        text = resp.text
        assert "chunk-0," in text
        assert "chunk-4," in text


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_middleware_brotli_priority():

    async def hello_handler(request):
        return JSONResponse({"message": "Hello, World! " * 100})

    app = Starlette(
        routes=[Route("/hello", hello_handler, methods=["GET"])],
        middleware=[Middleware(CompressionMiddleware, minimum_size=10, brotli_level=4)],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/hello", headers={"Accept-Encoding": "br, gzip"})
        assert resp.headers["content-encoding"] == "br"

        resp2 = await client.get("/hello", headers={"Accept-Encoding": "gzip, br"})
        assert resp2.headers["content-encoding"] == "br"


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_middleware_brotli_not_supported_client():
    async def hello_handler(request):
        return JSONResponse({"message": "Hello, World! " * 100})

    app = Starlette(
        routes=[Route("/hello", hello_handler, methods=["GET"])],
        middleware=[Middleware(CompressionMiddleware, minimum_size=10, brotli_level=4)],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/hello", headers={"Accept-Encoding": "gzip"})
        assert resp.headers["content-encoding"] == "gzip"
        assert resp.headers["content-encoding"] != "br"


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_middleware_brotli_minimum_size():

    async def small_handler(request):
        return JSONResponse({"message": "small"})

    app = Starlette(
        routes=[Route("/small", small_handler, methods=["GET"])],
        middleware=[
            Middleware(CompressionMiddleware, minimum_size=1000, brotli_level=4)
        ],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/small", headers={"Accept-Encoding": "br"})
        assert "content-encoding" not in resp.headers
