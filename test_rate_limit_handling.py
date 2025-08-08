import asyncio
import types
import time
import pytest

from config import load_config
from data_fetcher import WeatherDataFetcher


class DummyResponse:
    def __init__(self, status: int, headers=None, json_data=None):
        self.status = status
        self.headers = headers or {}
        self._json_data = json_data or {}

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummySession:
    def __init__(self, response):
        self._response = response

    def get(self, url, params=None):
        return self._response


@pytest.mark.asyncio
async def test_fetcher_handles_429_and_applies_cooldown(monkeypatch):
    config = load_config()
    fetcher = WeatherDataFetcher(config)

    # First call returns 429 with Retry-After 120
    dummy_resp = DummyResponse(429, headers={"Retry-After": "120"})
    fetcher.session = DummySession(dummy_resp)

    data = await fetcher._fetch_data("https://example.com", {"q": 1}, "Tomorrow.io")
    assert data is None
    assert "Tomorrow.io" in fetcher._rate_limit_until
    cooldown_until = fetcher._rate_limit_until["Tomorrow.io"]
    assert cooldown_until > time.time()
    assert cooldown_until - time.time() >= 100  # ~120s minus test runtime

    # Subsequent call is skipped due to cooldown (no request performed)
    # Swap session to one that would raise if used, to ensure skip path is taken
    class ExplodingSession:
        def get(self, *args, **kwargs):
            raise AssertionError("Should not perform network call during cooldown")

    fetcher.session = ExplodingSession()
    data2 = await fetcher._fetch_data("https://example.com", {"q": 1}, "Tomorrow.io")
    assert data2 is None

