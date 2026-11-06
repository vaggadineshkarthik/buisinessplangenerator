"""OpenRouter client (OpenAI-compatible chat completions).

Handles authentication, retries, rate limits, timeouts and streaming. The API key
is read from the backend environment and is never returned to the frontend.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from ..config import settings


class OpenRouterError(Exception):
    """Error raised for OpenRouter failures with an HTTP-ish status code."""

    def __init__(self, message: str, status_code: int = 502, code: str = "openrouter_error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class OpenRouterNotConfigured(OpenRouterError):
    def __init__(self) -> None:
        super().__init__(
            "OPENROUTER_API_KEY is not configured. Add it to your .env file and restart the backend.",
            status_code=503,
            code="not_configured",
        )


RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class OpenRouterClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openrouter_api_key
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self.model = model or settings.openrouter_model

    # -- configuration -----------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def _headers(self) -> Dict[str, str]:
        if not self.configured:
            raise OpenRouterNotConfigured()
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.openrouter_site_url,
            "X-Title": settings.openrouter_app_name,
        }

    def _payload(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        stream: bool,
    ) -> Dict[str, Any]:
        return {
            "model": model or self.model,
            "messages": messages,
            "temperature": settings.openrouter_temperature if temperature is None else temperature,
            "max_tokens": settings.openrouter_max_tokens if max_tokens is None else max_tokens,
            "stream": stream,
        }

    # -- non-streaming -----------------------------------------------------
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        headers = self._headers()
        payload = self._payload(messages, model, temperature, max_tokens, stream=False)

        last_error: Optional[Exception] = None
        async with httpx.AsyncClient(timeout=settings.openrouter_timeout) as client:
            for attempt in range(max_retries):
                try:
                    response = await client.post(
                        f"{self.base_url}/chat/completions", headers=headers, json=payload
                    )
                    if response.status_code in RETRYABLE_STATUS:
                        last_error = self._error_from_response(response)
                        await self._backoff(attempt, response)
                        continue
                    if response.status_code >= 400:
                        raise self._error_from_response(response)
                    data = response.json()
                    return {
                        "content": self._extract_content(data),
                        "model": data.get("model", payload["model"]),
                        "usage": data.get("usage", {}),
                        "raw_finish_reason": self._finish_reason(data),
                    }
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = OpenRouterError(
                        f"Network error contacting OpenRouter: {exc}", status_code=504
                    )
                    await self._sleep(attempt)

        raise last_error or OpenRouterError("OpenRouter request failed after retries.")

    # -- streaming ---------------------------------------------------------
    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        max_retries: int = 2,
    ) -> AsyncIterator[str]:
        headers = self._headers()
        payload = self._payload(messages, model, temperature, max_tokens, stream=True)
        payload["stream_options"] = {"include_usage": True}

        timeout = httpx.Timeout(settings.openrouter_timeout, connect=20.0)
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            emitted = False
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response:
                        if response.status_code >= 400:
                            body = await response.aread()
                            err = self._error_from_body(response.status_code, body)
                            if response.status_code in RETRYABLE_STATUS and attempt < max_retries - 1:
                                last_error = err
                                await self._sleep(attempt)
                                continue
                            raise err

                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            data = line[5:].strip()
                            if not data or data == "[DONE]":
                                if data == "[DONE]":
                                    break
                                continue
                            try:
                                event = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            if event.get("error"):
                                raise OpenRouterError(
                                    str(event["error"].get("message", event["error"])),
                                    status_code=502,
                                )
                            delta = self._extract_delta(event)
                            if delta:
                                emitted = True
                                yield delta
                return
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if emitted or attempt >= max_retries - 1:
                    raise OpenRouterError(
                        f"Streaming interrupted: {exc}", status_code=504
                    ) from exc
                last_error = exc
                await self._sleep(attempt)
            except OpenRouterError:
                raise
        if last_error:
            raise OpenRouterError(f"Streaming failed: {last_error}", status_code=504)

    # -- health ------------------------------------------------------------
    async def health_check(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "configured": self.configured,
            "model": self.model,
            "base_url": self.base_url,
            "reachable": False,
            "error": None,
        }
        if not self.configured:
            status["error"] = "API key not configured"
            return status
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
                if resp.status_code == 401:
                    status["error"] = "Invalid API key (401 Unauthorized)"
                    return status
                if resp.status_code >= 400:
                    status["error"] = f"OpenRouter returned HTTP {resp.status_code}"
                    return status
                status["reachable"] = True
                models = resp.json().get("data", [])
                available = {m.get("id") for m in models if isinstance(m, dict)}
                status["model_available"] = self.model in available if available else None
        except Exception as exc:  # noqa: BLE001
            status["error"] = f"Could not reach OpenRouter: {exc}"
        return status

    async def list_models(self) -> List[Dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
                if resp.status_code >= 400:
                    raise self._error_from_body(resp.status_code, resp.content)
                data = resp.json().get("data", [])
                return [
                    {
                        "id": m.get("id"),
                        "name": m.get("name", m.get("id")),
                        "context_length": m.get("context_length"),
                    }
                    for m in data
                    if isinstance(m, dict) and m.get("id")
                ]
        except OpenRouterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise OpenRouterError(f"Could not fetch models: {exc}", status_code=502) from exc

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _extract_content(data: Dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise OpenRouterError("OpenRouter returned no choices.", status_code=502)
        message = choices[0].get("message") or {}
        content = message.get("content")
        if content is None:
            return ""
        if isinstance(content, list):
            return "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return str(content)

    @staticmethod
    def _extract_delta(event: Dict[str, Any]) -> str:
        choices = event.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        content = delta.get("content")
        if content is None:
            return ""
        if isinstance(content, list):
            return "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return str(content)

    @staticmethod
    def _finish_reason(data: Dict[str, Any]) -> Optional[str]:
        choices = data.get("choices") or []
        return choices[0].get("finish_reason") if choices else None

    @staticmethod
    def _error_from_response(response: httpx.Response) -> OpenRouterError:
        return OpenRouterClient._error_from_body(response.status_code, response.content)

    @staticmethod
    def _error_from_body(status_code: int, body: bytes) -> OpenRouterError:
        message = ""
        try:
            payload = json.loads(body.decode("utf-8", errors="replace") or "{}")
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message", "")
            elif isinstance(error, str):
                message = error
            if not message:
                message = payload.get("message", "")
        except Exception:  # noqa: BLE001
            message = body.decode("utf-8", errors="replace")[:300]

        if status_code == 401:
            message = message or "Invalid OpenRouter API key."
        elif status_code == 402:
            message = message or "Insufficient OpenRouter credits."
        elif status_code == 404:
            message = message or "Requested model is unavailable on OpenRouter."
        elif status_code == 429:
            message = message or "OpenRouter rate limit reached."
        return OpenRouterError(message or f"OpenRouter error (HTTP {status_code}).", status_code=status_code)

    @staticmethod
    async def _sleep(attempt: int) -> None:
        await asyncio.sleep(min(2 ** attempt, 8))

    async def _backoff(self, attempt: int, response: httpx.Response) -> None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                await asyncio.sleep(min(float(retry_after), 20.0))
                return
            except ValueError:
                pass
        await self._sleep(attempt)


openrouter_client = OpenRouterClient()
