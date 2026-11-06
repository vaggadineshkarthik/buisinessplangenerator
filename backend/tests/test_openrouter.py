"""OpenRouter client tests using a stubbed HTTP transport.

Mocks are used only inside the test-suite; the application itself always calls
the real OpenRouter API.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.services.openrouter import (
    OpenRouterClient,
    OpenRouterError,
    OpenRouterNotConfigured,
)


class FakeResponse:
    def __init__(self, status_code: int, payload=None, headers=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.content = json.dumps(payload).encode() if payload is not None else text.encode()

    def json(self):
        return self._payload


class FakeStreamResponse:
    def __init__(self, status_code: int, lines, payload=None):
        self.status_code = status_code
        self._lines = lines
        self.content = json.dumps(payload).encode() if payload is not None else b""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def aread(self):
        return self.content

    async def aiter_lines(self):
        for line in self._lines:
            yield line


def _token_line(content: str) -> str:
    return "data: " + json.dumps({"choices": [{"delta": {"content": content}}]})


def test_client_is_not_configured_without_key():
    client = OpenRouterClient(api_key="")
    assert client.configured is False
    with pytest.raises(OpenRouterNotConfigured):
        client._headers()


async def test_chat_completion_success(monkeypatch):
    captured = {}

    async def fake_post(self, url, headers=None, json=None, **kwargs):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse(
            200,
            {
                "model": "openai/gpt-oss-120b",
                "choices": [{"message": {"content": "Hello from OpenRouter"}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 12},
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenRouterClient(api_key="secret-key")
    result = await client.chat_completion([{"role": "user", "content": "hi"}])

    assert result["content"] == "Hello from OpenRouter"
    assert captured["url"].endswith("/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["json"]["stream"] is False


async def test_chat_completion_invalid_key_raises_401(monkeypatch):
    async def fake_post(self, url, headers=None, json=None, **kwargs):
        return FakeResponse(401, {"error": {"message": "No auth credentials found"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenRouterClient(api_key="bad-key")
    with pytest.raises(OpenRouterError) as exc:
        await client.chat_completion([{"role": "user", "content": "hi"}], max_retries=1)
    assert exc.value.status_code == 401


async def test_chat_completion_retries_on_429(monkeypatch):
    calls = {"n": 0}

    async def fake_post(self, url, headers=None, json=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(429, {"error": {"message": "rate limited"}}, headers={"Retry-After": "0"})
        return FakeResponse(
            200, {"choices": [{"message": {"content": "recovered"}}], "model": "m"}
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenRouterClient(api_key="key")
    result = await client.chat_completion([{"role": "user", "content": "hi"}])
    assert result["content"] == "recovered"
    assert calls["n"] == 2


async def test_chat_completion_model_unavailable_404(monkeypatch):
    async def fake_post(self, url, headers=None, json=None, **kwargs):
        return FakeResponse(404, {"error": {"message": "No endpoints found for model"}})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client = OpenRouterClient(api_key="key")
    with pytest.raises(OpenRouterError) as exc:
        await client.chat_completion([{"role": "user", "content": "hi"}], max_retries=1)
    assert exc.value.status_code == 404


async def test_stream_chat_yields_tokens(monkeypatch):
    lines = [
        _token_line("Hello "),
        _token_line("world"),
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]

    def fake_stream(self, method, url, headers=None, json=None, **kwargs):
        return FakeStreamResponse(200, lines)

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    client = OpenRouterClient(api_key="key")
    tokens = [t async for t in client.stream_chat([{"role": "user", "content": "hi"}])]
    assert "".join(tokens) == "Hello world"


async def test_stream_chat_error_event_raises(monkeypatch):
    lines = ['data: {"error": {"message": "quota exceeded"}}']

    def fake_stream(self, method, url, headers=None, json=None, **kwargs):
        return FakeStreamResponse(200, lines)

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    client = OpenRouterClient(api_key="key")
    with pytest.raises(OpenRouterError):
        [t async for t in client.stream_chat([{"role": "user", "content": "hi"}])]


async def test_stream_chat_http_error_raises(monkeypatch):
    def fake_stream(self, method, url, headers=None, json=None, **kwargs):
        return FakeStreamResponse(401, [], payload={"error": {"message": "unauthorized"}})

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    client = OpenRouterClient(api_key="key")
    with pytest.raises(OpenRouterError) as exc:
        [t async for t in client.stream_chat([{"role": "user", "content": "hi"}], max_retries=1)]
    assert exc.value.status_code == 401


async def test_health_check_reports_unconfigured():
    status = await OpenRouterClient(api_key="").health_check()
    assert status["configured"] is False
    assert status["reachable"] is False


async def test_health_check_detects_invalid_key(monkeypatch):
    async def fake_get(self, url, headers=None, **kwargs):
        return FakeResponse(401, {"error": {"message": "invalid"}})

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    status = await OpenRouterClient(api_key="key").health_check()
    assert status["reachable"] is False
    assert "Invalid API key" in status["error"]


async def test_stream_payload_requests_stream_true(monkeypatch):
    captured = {}

    def fake_stream(self, method, url, headers=None, json=None, **kwargs):
        captured["payload"] = json
        return FakeStreamResponse(200, [_token_line("x"), "data: [DONE]"])

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)
    client = OpenRouterClient(api_key="key")
    [t async for t in client.stream_chat([{"role": "user", "content": "hi"}])]
    assert captured["payload"]["stream"] is True
