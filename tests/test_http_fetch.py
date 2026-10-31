"""Tests for bounded downloads: total deadline, size cap and content type."""
import httpx
import pytest

from src.http_fetch import FetchError, fetch

URL = "https://example.com/page"


def _client(body, status: int = 200, content_type: str | None = "text/html; charset=utf-8") -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": content_type} if content_type else {}
        return httpx.Response(status, headers=headers, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _ticking_clock(step: float):
    now = [0.0]

    def clock():
        now[0] += step
        return now[0]

    return clock


def test_returns_status_and_decoded_text():
    result = fetch(_client("Grüße".encode()), URL, max_bytes=1000, deadline_seconds=60)

    assert result.status == 200
    assert result.text == "Grüße"


def test_non_200_status_is_returned_without_reading_further():
    result = fetch(_client(b"gone", status=404), URL, max_bytes=1000, deadline_seconds=60)

    assert result.status == 404


def test_body_over_size_cap_is_permanent():
    with pytest.raises(FetchError) as exc:
        fetch(_client(b"x" * 5000), URL, max_bytes=1000, deadline_seconds=60)

    assert exc.value.permanent
    assert "larger than" in str(exc.value)


def test_slow_trickle_hits_total_deadline():
    def trickle():
        while True:
            yield b"x"

    with pytest.raises(FetchError) as exc:
        fetch(_client(trickle()), URL, max_bytes=10**9, deadline_seconds=60, clock=_ticking_clock(10))

    assert not exc.value.permanent
    assert "60s" in str(exc.value)


def test_disallowed_content_type_is_permanent():
    with pytest.raises(FetchError) as exc:
        fetch(_client(b"%PDF", content_type="application/pdf"), URL, max_bytes=1000, deadline_seconds=60,
              allowed_types=("text/", "application/xhtml+xml"))

    assert exc.value.permanent
    assert "application/pdf" in str(exc.value)


def test_missing_content_type_is_allowed():
    result = fetch(_client(b"<p>hi</p>", content_type=None), URL, max_bytes=1000, deadline_seconds=60,
                   allowed_types=("text/",))

    assert result.text == "<p>hi</p>"


def test_network_error_is_transient():
    def handler(request):
        raise httpx.ConnectError("refused")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(FetchError) as exc:
        fetch(client, URL, max_bytes=1000, deadline_seconds=60)

    assert not exc.value.permanent
    assert "ConnectError" in str(exc.value)
