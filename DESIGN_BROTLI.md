# Brotli 압축 기능 추가 설계 스케치

## 개요
현재 `gzip`과 `deflate`만 지원하는 미들웨어에 `brotli` 압축 기능을 추가합니다.
기존 아키텍처를 최대한 활용하여 일관성 있게 확장합니다.

---

## 1. 파일별 수정 계획

### 1.1 `src/asgi_http_compression/compressors.py`
**목적**: Brotli 압축기를 추가

**수정 내용**:
- `BrotliCompressor` 클래스 추가
- `brotli` 패키지 import (optional dependency 처리)
- 기존 `BaseCompressor` 인터페이스 준수 (incremental compression 지원)

**구체적 구현**:
```python
# 파일 상단에 추가 (기존 import 아래에 추가)
# 기존: import zlib
# 기존: from abc import ABC, abstractmethod
# 기존: from typing import Protocol

try:
    import brotli
except ImportError:
    brotli = None

# 가용 여부 플래그 추가 (다른 모듈에서 사용 가능)
BROTLI_AVAILABLE = brotli is not None

# ... 기존 Compressor Protocol, BaseCompressor, GzipCompressor, DeflateCompressor ...

# 파일 끝에 클래스 추가
class BrotliCompressor(BaseCompressor):
    def __init__(self, level: int = 4) -> None:
        if brotli is None:
            raise ImportError(
                "brotli extra is required. Install with: pip install 'asgi-http-compression[brotli]'"
            )
        self._compressor = brotli.Compressor(quality=level)
    
    def compress(self, data: bytes) -> bytes:
        """스트리밍 압축을 위한 incremental compress"""
        return self._compressor.process(data)
    
    def flush(self) -> bytes:
        """압축 완료 및 남은 데이터 반환"""
        return self._compressor.finish()
```

**참고**: `brotli.Compressor` API 확인 필요
- `brotli` 라이브러리의 `Compressor` 클래스는 `process(data: bytes) -> bytes`와 `finish() -> bytes` 메서드를 제공합니다.
- `quality` 파라미터는 0-11 범위의 정수입니다 (기본값 4 권장).
- `process()`로 데이터를 압축하고, 마지막에 `finish()`로 스트림을 완결해야 `brotli.decompress()`로 정상 복원 가능합니다.

**주의사항**:
- `brotli.Compressor`는 상태를 가지는 객체이므로 `compress()`와 `flush()`를 분리해서 사용 가능
- `level`은 `quality` 파라미터로 전달 (0-11 범위, 기본값 4 권장)
- `BROTLI_AVAILABLE` 플래그를 export하여 middleware와 테스트에서 사용 가능하도록 함

---

### 1.2 `src/asgi_http_compression/middleware.py`
**목적**: Brotli를 압축 옵션으로 등록하고 협상에 포함

**수정 내용**:
1. `BrotliCompressor` import 추가 (optional, try-except로 처리)
2. `__init__`에 `brotli_level` 파라미터 추가
3. `compressor_factories`에 `"br"` 등록 (우선순위: br > gzip > deflate)
4. `_select_encoding` 메서드는 수정 불필요 (이미 `compressor_factories`의 키를 순회하므로 자동 인식)

**구체적 구현**:
```python
# import 섹션 수정 (기존 import 아래에 추가)
from asgi_http_compression.compressors import (
    DeflateCompressor,
    GzipCompressor,
    BrotliCompressor,
    BROTLI_AVAILABLE,
)

# __init__ 메서드 수정
def __init__(
    self,
    app: ASGIApp,
    minimum_size: int = 500,
    gzip_level: int = 9,
    deflate_level: int = 6,
    brotli_level: int = 4,  # 추가
) -> None:
    self.app = app
    self.minimum_size = minimum_size

    # NOTE: Register the supported compression methods and their factories
    # NOTE: The order is important: list the ones the server prefers first
    self.compressor_factories: dict[str, Callable[[], Any]] = {}

    # Brotli를 가장 먼저 등록 (우선순위 높음)
    # BROTLI_AVAILABLE 플래그로 실제 brotli 패키지 설치 여부 확인
    if BROTLI_AVAILABLE:
        self.compressor_factories["br"] = lambda: BrotliCompressor(level=brotli_level)
    
    self.compressor_factories["gzip"] = lambda: GzipCompressor(level=gzip_level)
    self.compressor_factories["deflate"] = lambda: DeflateCompressor(level=deflate_level)
```

**주의사항**:
- `BROTLI_AVAILABLE` 플래그를 사용하여 실제 `brotli` 패키지 설치 여부를 확인
- `brotli` 패키지가 없으면 `"br"`을 등록하지 않음 (graceful degradation)
- `"br"`은 HTTP 표준에서 사용하는 Brotli 인코딩 이름
- 우선순위는 `compressor_factories`의 순서에 따라 결정됨 (현재 `_select_encoding`은 순서대로 체크)
- `_select_encoding` 메서드는 수정 불필요 (이미 `compressor_factories`의 키를 순회하므로 `"br"`이 등록되면 자동으로 인식됨)
- `BrotliCompressor` 클래스는 항상 import 가능하지만, `brotli` 패키지가 없으면 생성 시 `ImportError` 발생

---

### 1.3 `src/asgi_http_compression/responder.py`
**목적**: 변경 없음 (이미 streaming/non-streaming 모두 지원)

**확인 사항**:
- `CompressionResponder`는 이미 `Compressor` 프로토콜을 사용하므로 추가 수정 불필요
- `compress()`와 `flush()` 메서드만 있으면 동작함
- streaming 응답 처리 로직도 이미 구현되어 있음

---

### 1.4 `tests/test_compressors.py`
**목적**: Brotli 압축기 단위 테스트 추가

**수정 내용**:
- `BrotliCompressor`를 테스트에 포함
- 기존 fixture에 `BrotliCompressor` 추가 (optional)
- Brotli 전용 테스트 케이스 추가

**구체적 구현**:
```python
# import 추가
try:
    import brotli  # type: ignore[import-untyped]
    from asgi_http_compression.compressors import BrotliCompressor
    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False

# fixture 수정 (optional로 추가)
@pytest.fixture(params=[GzipCompressor, DeflateCompressor] + ([BrotliCompressor] if BROTLI_AVAILABLE else []))
def compressor(request):
    return request.param()

# Brotli 전용 테스트 추가
@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
def test_brotli_compressor():
    import brotli
    compressor = BrotliCompressor(level=4)
    original_data = b"Hello, World!" * 10
    compressed = compressor.compress(original_data)
    flushed = compressor.flush()
    full_compressed_data = compressed + flushed
    decompressed = brotli.decompress(full_compressed_data)
    assert decompressed == original_data
```

**주의사항**:
- `import brotli`를 직접 시도하여 실제 패키지 설치 여부를 확인
- `from asgi_http_compression.compressors import BrotliCompressor`는 항상 성공할 수 있으므로, 실제 `brotli` 모듈 존재 여부를 기준으로 판단
- `BROTLI_AVAILABLE`이 `False`면 fixture에서 `BrotliCompressor`를 제외하고, 전용 테스트는 skip됨

---

### 1.5 `tests/test_responder.py` (또는 새 파일 `tests/test_brotli.py`)
**목적**: Brotli를 사용한 end-to-end 테스트 작성

**새 파일 생성**: `tests/test_brotli.py`

**테스트 시나리오**:

1. **기본 Brotli 압축 테스트**
   - `Accept-Encoding: br` 헤더로 요청
   - `Content-Encoding: br` 확인
   - 압축 해제 후 원본 데이터 확인

2. **Brotli 비지원 클라이언트 테스트**
   - `Accept-Encoding: gzip`만 보냈을 때 `br`이 나오지 않는지 확인

3. **우선순위 테스트**
   - `Accept-Encoding: br, gzip` → `br` 선택 확인
   - `Accept-Encoding: gzip, br` → `br` 선택 확인 (서버 우선순위)

4. **minimum_size 조건 테스트**
   - 작은 응답 → 압축 안 됨
   - 큰 응답 → 압축 됨

5. **StreamingResponse 테스트**
   - 여러 chunk로 나뉜 응답도 Brotli로 압축되는지 확인
   - `Content-Length` 제거 확인

6. **이미 Content-Encoding이 있는 응답 처리**
   - 기존 인코딩이 있으면 Brotli 적용 안 됨

**구체적 구현 예시**:
```python
import pytest

try:
    import brotli  # type: ignore[import-untyped]
    from asgi_http_compression.compressors import BrotliCompressor
    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False

from asgi_http_compression.responder import CompressionResponder

# test_responder.py의 MockSend, mock_app, streaming_app 등을 재사용
from tests.test_responder import MockSend, mock_app, streaming_app, app_with_encoding

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
    
    # 압축 해제 확인
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
    
    # 전체 압축 데이터 수집 및 압축 해제
    full_compressed = body1["body"] + body2["body"]
    decompressed = brotli.decompress(full_compressed)
    assert decompressed == b"Streaming part 2"

# test_responder.py의 app_with_encoding도 재사용 가능
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
    assert headers[b"content-encoding"] == b"identity"  # 기존 인코딩 유지
    assert b"vary" not in headers
```

---

### 1.6 통합 테스트 (선택사항, `tests/test_middleware_brotli.py`)
**목적**: 실제 ASGI 앱과 미들웨어를 함께 테스트

**구체적 구현**:
```python
import pytest
from httpx import AsyncClient
from fastapi import FastAPI

try:
    import brotli  # type: ignore[import-untyped]
    from asgi_http_compression import CompressionMiddleware
    BROTLI_AVAILABLE = True
except ImportError:
    BROTLI_AVAILABLE = False

@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_middleware_brotli_integration():
    app = FastAPI()
    app.add_middleware(CompressionMiddleware, minimum_size=10, brotli_level=4)
    
    @app.get("/hello")
    async def hello():
        return {"message": "Hello, World! " * 100}
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/hello", headers={"Accept-Encoding": "br"})
        assert resp.headers["content-encoding"] == "br"
        
        decompressed = brotli.decompress(resp.content)
        import json
        data = json.loads(decompressed.decode())
        assert data["message"] == "Hello, World! " * 100

@pytest.mark.skipif(not BROTLI_AVAILABLE, reason="brotli package not installed")
@pytest.mark.asyncio
async def test_middleware_brotli_streaming():
    app = FastAPI()
    app.add_middleware(CompressionMiddleware, minimum_size=1, brotli_level=4)
    
    @app.get("/stream")
    async def stream():
        from fastapi.responses import StreamingResponse
        async def gen():
            for i in range(5):
                yield f"chunk-{i},".encode()
        return StreamingResponse(gen(), media_type="text/plain")
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.get("/stream", headers={"Accept-Encoding": "br"})
        assert resp.headers["content-encoding"] == "br"
        
        decompressed = brotli.decompress(resp.content)
        text = decompressed.decode()
        assert "chunk-0," in text
        assert "chunk-4," in text
```

---

## 2. 구현 순서 및 체크리스트

### Phase 1: HTTP Compression (기본 기능)
- [ ] `compressors.py`에 `BrotliCompressor` 클래스 추가
- [ ] `middleware.py`에 `brotli_level` 파라미터 및 `"br"` 등록
- [ ] `test_compressors.py`에 Brotli 단위 테스트 추가
- [ ] 기본 압축 동작 확인 (non-streaming)

### Phase 2: Streaming Compression (스트리밍 지원)
- [ ] `BrotliCompressor`가 incremental API 사용하는지 확인
- [ ] `test_responder.py` 또는 `test_brotli.py`에 streaming 테스트 추가
- [ ] 여러 chunk로 나뉜 응답도 정상 압축되는지 확인

### Phase 3: Test Code (테스트 완성)
- [ ] `test_brotli.py` 파일 생성 및 모든 시나리오 테스트 작성
- [ ] 통합 테스트 (선택사항) 작성
- [ ] Edge case 테스트 (minimum_size, Content-Encoding 이미 있는 경우 등)
- [ ] 모든 테스트 통과 확인

---

## 3. 주의사항 및 고려사항

### 3.1 Optional Dependency 처리
- `brotli` 패키지가 없어도 미들웨어는 정상 동작해야 함
- `compressors.py`에서 `BROTLI_AVAILABLE` 플래그를 export하여 실제 패키지 설치 여부를 명확히 표시
- `middleware.py`에서는 `BROTLI_AVAILABLE` 플래그를 사용하여 `"br"` 등록 여부 결정
- 테스트에서는 `import brotli`를 직접 시도하여 실제 패키지 설치 여부 확인
- `BrotliCompressor` 클래스는 항상 import 가능하지만, `brotli` 패키지가 없으면 생성 시 `ImportError` 발생

### 3.2 우선순위 정책

**현재 구현**: 서버가 지원하는 순서대로 체크 (`compressor_factories` 순서)

**우선순위: br > gzip > deflate**

**근거**:
1. **압축 효율성**: Brotli는 gzip보다 일반적으로 15-20% 더 나은 압축률을 제공합니다.
2. **최신 표준**: Brotli는 2015년 Google에서 개발된 최신 압축 알고리즘으로, HTTP/2와 함께 널리 사용됩니다.
3. **브라우저 지원**: 현재 대부분의 모던 브라우저가 Brotli를 지원합니다 (Chrome, Firefox, Edge, Safari 등).
4. **호환성**: gzip은 여전히 널리 지원되므로 fallback으로 유지합니다.
5. **deflate의 문제점**: deflate는 gzip과 유사하지만 헤더 형식이 표준화되지 않아 호환성 문제가 있을 수 있습니다.

**참고**: 현재 구현은 q-value 파싱을 하지 않으므로, 서버가 선호하는 순서대로 선택됩니다. 향후 q-value 파싱이 추가되면 더 정교한 협상이 가능합니다.

### 3.3 압축 레벨 기본값

**현재 설정**:
- `gzip_level: int = 9` (최대 압축률, zlib의 기본값)
- `deflate_level: int = 6` (중간 압축률, zlib의 기본값)
- `brotli_level: int = 4` (속도/압축률 균형)

**Brotli level 4 선택 근거**:
1. **압축률 vs 속도 균형**: 
   - Level 0-4: 빠른 압축, 적당한 압축률
   - Level 5-9: 중간 속도, 좋은 압축률
   - Level 10-11: 느린 압축, 최고 압축률
   - Level 4는 속도와 압축률의 좋은 균형점입니다.

2. **실제 사용 사례**:
   - 많은 웹 서버(예: Nginx, Cloudflare)에서 기본값으로 4-6을 사용합니다.
   - Level 4는 gzip level 9와 비슷한 압축률을 더 빠른 속도로 제공할 수 있습니다.

3. **기존 프로젝트와의 일관성**:
   - `gzip_level=9`는 최대 압축률을 추구하는 설정입니다.
   - `brotli_level=4`는 비슷한 압축률을 더 빠르게 달성할 수 있는 설정입니다.

4. **사용자 조정 가능**: 
   - 사용자가 `brotli_level` 파라미터로 필요에 따라 조정할 수 있습니다.
   - 대역폭이 중요한 경우: level 6-8 권장
   - CPU가 제한적인 경우: level 2-4 권장
   - 최대 압축률이 필요한 경우: level 10-11 권장

**참고**: Brotli의 quality 파라미터는 0-11 범위이며, 기본값 4는 일반적으로 권장되는 값입니다.

### 3.4 기존 코드와의 호환성
- 기존 `GzipCompressor`, `DeflateCompressor` 동작 변경 없음
- `CompressionResponder`는 수정 불필요 (이미 범용적으로 구현됨)

---

## 4. 예상 파일 변경 요약

```
src/asgi_http_compression/
  ├── compressors.py          [수정] BrotliCompressor 추가
  ├── middleware.py           [수정] br 등록 및 brotli_level 파라미터
  └── responder.py            [변경 없음]

tests/
  ├── test_compressors.py      [수정] BrotliCompressor 테스트 추가
  ├── test_responder.py        [변경 없음 또는 선택적 수정]
  └── test_brotli.py          [신규] Brotli end-to-end 테스트
```

---

## 5. 실제 코드와의 검증 결과

### ✅ 확인된 사항

1. **compressors.py 구조**
   - `Compressor` Protocol과 `BaseCompressor` ABC가 존재하며, `compress()`와 `flush()` 메서드만 구현하면 됨 ✓
   - `GzipCompressor`와 `DeflateCompressor`가 `zlib.compressobj`를 사용하는 패턴과 동일하게 구현 가능 ✓
   - `brotli.Compressor`의 `process()`와 `finish()` API가 스트리밍 압축에 적합함 ✓

2. **middleware.py 구조**
   - `compressor_factories` 딕셔너리에 lambda 함수로 등록하는 패턴 확인 ✓
   - `_select_encoding`이 `compressor_factories`의 키를 순회하므로 `"br"` 등록만으로 자동 인식 ✓
   - 기존 import 방식: `from asgi_http_compression.compressors import DeflateCompressor, GzipCompressor` ✓
   - `BROTLI_AVAILABLE` 플래그를 사용하여 optional dependency를 안전하게 처리 ✓

3. **responder.py 구조**
   - `Compressor` Protocol을 사용하므로 추가 수정 불필요 ✓
   - Streaming/non-streaming 모두 이미 지원됨 ✓
   - `compress()`와 `flush()` 호출 패턴이 기존과 동일 ✓

4. **테스트 구조**
   - `test_responder.py`에 `MockSend`, `mock_app`, `streaming_app` 등 재사용 가능한 fixture 존재 ✓
   - `test_compressors.py`의 fixture 패턴 확인 ✓
   - `import brotli`를 직접 체크하여 실제 패키지 설치 여부 확인하는 방식 ✓

### ⚠️ 수정된 사항

1. **optional dependency 처리 방식**
   - `compressors.py`에서 `BROTLI_AVAILABLE` 플래그를 export하여 실제 `brotli` 패키지 설치 여부를 명확히 표시
   - `middleware.py`에서는 `BROTLI_AVAILABLE` 플래그를 사용하여 `"br"` 등록 여부 결정
   - `from asgi_http_compression.compressors import BrotliCompressor`는 항상 성공할 수 있으므로, 실제 `brotli` 모듈 존재 여부를 기준으로 판단

2. **테스트에서 BROTLI_AVAILABLE 체크**
   - `import brotli`를 직접 시도하여 실제 패키지 설치 여부 확인
   - `from asgi_http_compression.compressors import BrotliCompressor` 성공 여부가 아니라 `import brotli` 성공 여부를 기준으로 `skipif` 적용

3. **테스트 코드 재사용**
   - `test_responder.py`의 fixture들을 `from tests.test_responder import ...`로 import하여 재사용

---

## 6. 핵심 변경사항 요약

### Optional Dependency 처리 방식 (중요!)

**문제점**: `compressors.py`에서 `try/except ImportError`로 `brotli`를 처리하면, `brotli` 패키지가 없어도 `BrotliCompressor` 클래스는 항상 import 가능합니다. 이 경우 `BrotliCompressor is None` 체크가 작동하지 않습니다.

**해결책**:
1. **`compressors.py`**: `BROTLI_AVAILABLE = brotli is not None` 플래그를 export
2. **`middleware.py`**: `BROTLI_AVAILABLE` 플래그를 사용하여 `"br"` 등록 여부 결정
3. **테스트**: `import brotli`를 직접 시도하여 실제 패키지 설치 여부 확인

이렇게 하면 `brotli` 패키지가 없을 때:
- `compressors.py` 모듈은 정상 import됨
- `BROTLI_AVAILABLE = False`로 설정됨
- `middleware.py`에서 `"br"` 등록을 건너뜀 (graceful degradation)
- 테스트는 자동으로 skip됨

---

## 7. 검증 체크리스트

구현 완료 후 다음을 확인:

- [ ] `Accept-Encoding: br` 요청 시 `Content-Encoding: br` 응답
- [ ] Brotli로 압축된 응답을 `brotli.decompress()`로 정상 복원 가능
- [ ] StreamingResponse도 Brotli 압축 정상 동작
- [ ] `brotli` 패키지 없을 때 graceful degradation (에러 없이 gzip/deflate만 사용)
- [ ] `minimum_size` 조건 정상 동작
- [ ] 이미 `Content-Encoding`이 있는 응답은 건드리지 않음
- [ ] 모든 기존 테스트 통과 (회귀 테스트)

