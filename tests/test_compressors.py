import zlib

import pytest

from asgi_http_compression.compressors import DeflateCompressor, GzipCompressor


@pytest.fixture(params=[GzipCompressor, DeflateCompressor])
def compressor(request):
    return request.param()


def test_compressor_simple_compression(compressor):
    original_data = b"Hello, World!" * 10
    compressed = compressor.compress(original_data)
    flushed = compressor.flush()

    full_compressed_data = compressed + flushed

    if isinstance(compressor, GzipCompressor):
        # 15 + 16 tells zlib to use the gzip header and trailer format.
        decompressed = zlib.decompress(full_compressed_data, 15 + 16)
    else:
        decompressed = zlib.decompress(full_compressed_data)

    assert decompressed == original_data
    assert original_data != full_compressed_data


def test_compressor_incremental_compression(compressor):
    data_part1 = b"This is the first part."
    data_part2 = b"This is the second part."
    original_data = data_part1 + data_part2

    compressed1 = compressor.compress(data_part1)
    compressed2 = compressor.compress(data_part2)
    flushed = compressor.flush()

    full_compressed_data = compressed1 + compressed2 + flushed

    if isinstance(compressor, GzipCompressor):
        decompressed = zlib.decompress(full_compressed_data, 15 + 16)
    else:
        decompressed = zlib.decompress(full_compressed_data)

    assert decompressed == original_data


def test_compressor_empty_data(compressor):
    original_data = b""
    compressed = compressor.compress(original_data)
    flushed = compressor.flush()

    full_compressed_data = compressed + flushed

    if isinstance(compressor, GzipCompressor):
        decompressed = zlib.decompress(full_compressed_data, 15 + 16)
    else:
        decompressed = zlib.decompress(full_compressed_data)

    assert decompressed == original_data
    assert full_compressed_data != original_data
