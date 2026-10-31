"""Downloads with a total deadline, a size cap and an optional content-type check.

httpx timeouts apply per network operation, so a server that keeps sending a byte
now and then never trips them. Streaming with our own clock bounds the whole download.
"""
import time
from dataclasses import dataclass

import httpx


@dataclass
class FetchResult:
    status: int
    text: str
    content: bytes


class FetchError(Exception):
    """Download failed; permanent failures are not worth retrying."""

    def __init__(self, reason: str, permanent: bool):
        super().__init__(reason)
        self.reason = reason
        self.permanent = permanent


def fetch(client: httpx.Client, url: str, *, max_bytes: int, deadline_seconds: float,
          allowed_types: tuple[str, ...] | None = None, clock=time.monotonic) -> FetchResult:
    """GET a URL; a non-200 status is returned with an empty body."""
    start = clock()
    try:
        with client.stream("GET", url) as response:
            if response.status_code != 200:
                return FetchResult(response.status_code, "", b"")

            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if allowed_types and content_type and not content_type.startswith(allowed_types):
                raise FetchError(f"not an HTML page ({content_type})", permanent=True)

            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > max_bytes:
                    raise FetchError(f"larger than {max_bytes:,} bytes", permanent=True)
                if clock() - start > deadline_seconds:
                    raise FetchError(f"download not finished after {deadline_seconds:g}s", permanent=False)
                chunks.append(chunk)

            content = b"".join(chunks)
            text = content.decode(response.encoding or "utf-8", errors="replace")
            return FetchResult(response.status_code, text, content)
    except httpx.HTTPError as e:
        raise FetchError(f"{type(e).__name__}: {e}", permanent=False) from None
