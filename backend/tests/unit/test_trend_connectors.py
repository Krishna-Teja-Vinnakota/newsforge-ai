from datetime import UTC, datetime

import httpx
import pytest

from app.core.settings import settings
from app.services.trends import connectors
from app.services.trends.connectors import ConnectorFetchError, GoogleNewsConnector, _get, fetch_connector

NOW = datetime(2026, 9, 21, 12, tzinfo=UTC)


def rss(count: int) -> bytes:
    items = "".join(
        f"<item><title>Story number {index} headline - Outlet</title>"
        f"<link>https://example.test/{index}</link><pubDate>Mon, 21 Sep 2026 11:00:00 GMT</pubDate></item>"
        for index in range(1, count + 1)
    )
    return f"<rss><channel>{items}</channel></rss>".encode()


def client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def instant(_: float) -> None:
        return None

    monkeypatch.setattr(connectors.asyncio, "sleep", instant)


@pytest.mark.asyncio
async def test_transient_status_is_retried_then_succeeds():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, content=b"ok")

    async with client_for(handler) as client:
        response = await _get(client, "https://example.test/feed")
    assert response.content == b"ok"
    assert len(calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "code"), [(429, "rate_limited"), (502, "upstream_unavailable"), (503, "upstream_unavailable")])
async def test_retries_are_bounded_and_report_safe_codes(status, code):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status)

    async with client_for(handler) as client:
        with pytest.raises(ConnectorFetchError) as error:
            await _get(client, "https://example.test/feed")
    assert error.value.code == code
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_non_transient_errors_are_not_retried():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404)

    async with client_for(handler) as client:
        with pytest.raises(ConnectorFetchError) as error:
            await _get(client, "https://example.test/feed")
    assert error.value.code == "upstream_error"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_timeouts_and_transport_errors_become_safe_codes():
    def timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    def broken(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    async with client_for(timeout) as client:
        with pytest.raises(ConnectorFetchError) as error:
            await _get(client, "https://example.test/feed")
    assert error.value.code == "timeout"
    async with client_for(broken) as client:
        with pytest.raises(ConnectorFetchError) as error:
            await _get(client, "https://example.test/feed")
    assert error.value.code == "transport_error"


@pytest.mark.asyncio
async def test_oversized_responses_are_rejected():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (connectors.MAX_RESPONSE_BYTES + 1))

    async with client_for(handler) as client:
        with pytest.raises(ConnectorFetchError) as error:
            await _get(client, "https://example.test/feed")
    assert error.value.code == "response_too_large"


@pytest.mark.asyncio
async def test_google_news_parses_signals_and_respects_the_per_source_cap(monkeypatch):
    monkeypatch.setattr(settings, "trends_max_signals_per_source", 2)
    async with client_for(lambda _: httpx.Response(200, content=rss(5))) as client:
        result = await GoogleNewsConnector().fetch("US", client, NOW)
    assert result.status == "success"
    assert [signal.label for signal in result.signals] == ["Story number 1 headline", "Story number 2 headline"]
    first = result.signals[0]
    assert (first.geo, first.country_code, first.source, first.rank) == ("US", "US", "google_news", 1)
    assert first.expires_at > first.observed_at


@pytest.mark.asyncio
async def test_empty_feed_is_success_empty_not_failure():
    async with client_for(lambda _: httpx.Response(200, content=rss(0))) as client:
        result = await GoogleNewsConnector().fetch("US", client, NOW)
    assert result.status == "success_empty"
    assert result.signals == []


@pytest.mark.asyncio
async def test_malformed_feed_fails_with_parse_error_and_never_looks_empty():
    async with client_for(lambda _: httpx.Response(200, content=b"<rss><channel>")) as client:
        result = await fetch_connector(GoogleNewsConnector(), "US", client, NOW)
    assert result.status == "failed"
    assert result.error_code == "parse_error"


@pytest.mark.asyncio
async def test_unexpected_connector_errors_are_reported_without_leaking_details():
    class Exploding(GoogleNewsConnector):
        async def fetch(self, geo, client, now):
            raise ValueError("secret internal detail")

    async with client_for(lambda _: httpx.Response(200)) as client:
        result = await fetch_connector(Exploding(), "US", client, NOW)
    assert result.status == "failed"
    assert result.error_code == "unexpected_error"
