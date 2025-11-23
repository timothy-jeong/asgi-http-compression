from asgi_http_compression.middleware import CompressionMiddleware


async def dummy_app(scope, receive, send):
    pass

def test_negotiate_encoding_basic():
    mw = CompressionMiddleware(app=dummy_app)

    # Default priority: gzip > deflate
    assert mw.negotiate_encoding("gzip, deflate") == "gzip"
    assert mw.negotiate_encoding("deflate, gzip") == "gzip"  # Follows server preference

def test_negotiate_encoding_q_values_ignored():
    mw = CompressionMiddleware(app=dummy_app)

    # Ignore q-values, select server preference among supported encodings
    assert mw.negotiate_encoding("gzip;q=0.5, deflate;q=1.0") == "gzip"

def test_negotiate_encoding_wildcard():
    mw = CompressionMiddleware(app=dummy_app)

    # Wildcard returns server's first preference
    assert mw.negotiate_encoding("*") == "gzip"

def test_negotiate_encoding_identity():
    mw = CompressionMiddleware(app=dummy_app)

    assert mw.negotiate_encoding("identity, gzip") == "gzip"
    # identity only means None (no compression)
    assert mw.negotiate_encoding("identity") is None

def test_negotiate_encoding_unsupported():
    mw = CompressionMiddleware(app=dummy_app)

    assert mw.negotiate_encoding("br") is None  # 'br' is currently unsupported
    assert mw.negotiate_encoding("") is None
