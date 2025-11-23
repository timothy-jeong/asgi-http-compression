import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from asgi_http_compression.middleware import CompressionMiddleware


async def small_response(request):
    """Response smaller than minimum_size."""
    return Response("tiny", media_type="text/plain")

async def large_response(request):
    """Large response target for compression."""
    data = "A" * 1000  # 1000 bytes
    return Response(data, media_type="text/plain")

async def streaming_response(request):
    """Streaming response generator."""
    async def generator():
        yield b"chunk1" * 100
        yield b"chunk2" * 100
        yield b"chunk3" * 100

    return StreamingResponse(generator(), media_type="text/plain")

async def error_response(request):
    """400 Bad Request response (for status code preservation test)."""
    return Response("Error occurred", status_code=400)

async def excluded_response(request):
    """Response for excluded path test."""
    data = "B" * 1000
    return Response(data, media_type="text/plain")

# --- App Fixture ---

@pytest.fixture
def app():
    routes = [
        Route("/small", small_response),
        Route("/large", large_response),
        Route("/stream", streaming_response),
        Route("/error", error_response),
        Route("/skip/this", excluded_response),
    ]

    application = Starlette(routes=routes)

    # Add Middleware
    application.add_middleware(
        CompressionMiddleware,
        minimum_size=500,        # Do not compress if smaller than 500 bytes
        excluded_handlers=["^/skip"], # Exclude paths starting with /skip
        compression_level=6
    )
    return application

@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver"
    ) as c:
        yield c
