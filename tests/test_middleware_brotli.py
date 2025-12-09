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
    """미들웨어와 실제 ASGI 앱을 함께 테스트"""

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
    """미들웨어와 StreamingResponse 테스트"""

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
    """우선순위 테스트: br이 gzip보다 우선 선택되는지 확인"""

    async def hello_handler(request):
        return JSONResponse({"message": "Hello, World! " * 100})

    app = Starlette(
        routes=[Route("/hello", hello_handler, methods=["GET"])],
        middleware=[Middleware(CompressionMiddleware, minimum_size=10, brotli_level=4)],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # br과 gzip을 모두 지원하는 클라이언트
        resp = await client.get("/hello", headers={"Accept-Encoding": "br, gzip"})
        assert resp.headers["content-encoding"] == "br"

        # gzip과 br을 모두 지원하지만 순서가 다른 경우
        resp2 = await client.get("/hello", headers={"Accept-Encoding": "gzip, br"})
        assert resp2.headers["content-encoding"] == "br"


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_middleware_brotli_not_supported_client():
    """Brotli를 지원하지 않는 클라이언트는 gzip 사용"""

    async def hello_handler(request):
        return JSONResponse({"message": "Hello, World! " * 100})

    app = Starlette(
        routes=[Route("/hello", hello_handler, methods=["GET"])],
        middleware=[Middleware(CompressionMiddleware, minimum_size=10, brotli_level=4)],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # gzip만 지원하는 클라이언트
        resp = await client.get("/hello", headers={"Accept-Encoding": "gzip"})
        assert resp.headers["content-encoding"] == "gzip"
        assert resp.headers["content-encoding"] != "br"


@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_middleware_brotli_minimum_size():
    """minimum_size 조건 테스트"""

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
        # 작은 응답은 압축되지 않음
        assert "content-encoding" not in resp.headers
