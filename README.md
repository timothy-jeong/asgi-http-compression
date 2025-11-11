# asgi-http-compression

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
[![Python Support](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://pypi.org/project/asgi-http-compression)

An ASGI middleware for HTTP response compression.

This middleware provides high-performance compression for ASGI applications (Starlette, FastAPI, etc.), supporting multiple modern encoding formats.

## Features

* **Multiple Encodings:** Supports `gzip`, `deflate`, `brotli`, and `zstd`.
* **Smart Content-Negotiation:** Automatically selects the best encoding format that both the server and client support, based on the client's `Accept-Encoding` header.
* **Fully Configurable:**
    * **`minimum_size`**: Set the minimum response size (in bytes) required to trigger compression.
    * **`level`**: Fine-tune the compression level for each algorithm (e.g., `gzip_level`, `brotli_level`, `zstd_level`).
* **Advanced Dictionary Compression:**
    * Supports pre-trained **static dictionaries** for `brotli` and `zstd`. This is perfect for dramatically improving compression ratios on known data structures (like common JSON responses).
    * Includes planned support for the emerging [**experimental HTTP Compression Dictionaries**](https://developer.mozilla.org/en-US/docs/Web/HTTP/Compression_dictionaries) standard, allowing browsers to opt-in to using a dictionary.

## Installation

```bash
# Core installation (gzip, deflate support)
pip install asgi-http-compression

# To add Brotli support
pip install "asgi-http-compression[brotli]"

# To add Zstd support
pip install "asgi-http-compression[zstd]"

# To install all features
pip install "asgi-http-compression[brotli,zstd]"

```

## Basic Usage
Simply add `CompressionMiddleware` as the outermost middleware to your ASGI application.
```python
# main.py
from fastapi import FastAPI
from asgi_http_compression import CompressionMiddleware

app = FastAPI()

# Add the middleware
# This will enable gzip, brotli, and zstd
# if the dependencies are installed.
app.add_middleware(CompressionMiddleware)


@app.get("/")
async def root():
    # This response will be automatically compressed
    # if it's large enough and the client supports it.
    return {"message": "Hello World! " * 1000}
```

## Configuration
You can customize the middleware's behavior by passing arguments.
```python
app.add_middleware(
    CompressionMiddleware,
    
    # Minimum size (in bytes) to trigger compression
    # Default: 500
    minimum_size=500,

    # Set a specific compression level for gzip (1-9)
    gzip_level=9,

    # Set a specific compression level for Brotli (0-11)
    brotli_level=5,

    # Set a specific compression level for Zstd (1-22)
    zstd_level=3,

    # (Future API for static dictionaries)
    # brotli_dictionary=b"your_static_brotli_dict_data",
    # zstd_dictionary=b"your_static_zstd_dict_data"
)
```

## Tanks to
This project is inspired by and builds upon the ideas from:
- [asgi-zstd](https://github.com/tuffnatty/zstd-asgi)
- [django-http-compression](https://github.com/adamchainz/django-http-compression)


## License
This project is licensed under the MIT License.