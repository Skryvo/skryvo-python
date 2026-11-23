from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from ._errors import ConnectionError, SkryvoError, error_from_response
from ._version import VERSION

READS = {"GET", "DELETE"}
RETRY_STATUSES = {502, 503, 504}


def _query(query: dict[str, Any] | None) -> dict[str, Any] | None:
    if not query:
        return None
    return {k: v for k, v in query.items() if v is not None}


def _answer(response: httpx.Response) -> Any:
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def _error(response: httpx.Response) -> SkryvoError:
    try:
        body = response.json()
    except ValueError:
        body = None
    return error_from_response(response.status_code, body, response.headers)


def _retryable(method: str, error: SkryvoError) -> bool:
    return error.status == 429 or (method in READS and error.status in RETRY_STATUSES)


def _wait(error: SkryvoError | None, attempt: int) -> float:
    return min(error.retry_after if error and error.retry_after else 2**attempt, 60.0)


class _Settings:
    def __init__(self, api_key: str, base_url: str, timeout: float, max_retries: int, user_agent: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.headers = {
            "authorization": f"Bearer {api_key}",
            "accept": "application/json",
            "user-agent": user_agent or f"skryvo-python/{VERSION}",
        }


class SyncTransport:
    def __init__(self, settings: _Settings, client: httpx.Client | None) -> None:
        self._s = settings
        self._client = client or httpx.Client(timeout=settings.timeout)

    def request(self, method: str, path: str, *, query: dict[str, Any] | None = None, body: Any = None) -> Any:
        for attempt in range(self._s.max_retries + 1):
            try:
                response = self._client.request(
                    method, self._s.base_url + path, params=_query(query), json=body, headers=self._s.headers
                )
            except httpx.TimeoutException as cause:
                raise ConnectionError(f"Skryvo didn't answer within {self._s.timeout:g} seconds.") from cause
            except httpx.TransportError as cause:
                if method in READS and attempt < self._s.max_retries:
                    time.sleep(_wait(None, attempt) / 2)
                    continue
                raise ConnectionError(f"Couldn't reach Skryvo at {self._s.base_url}.") from cause
            if response.is_success:
                return _answer(response)
            error = _error(response)
            if not _retryable(method, error) or attempt >= self._s.max_retries:
                raise error
            time.sleep(_wait(error, attempt))
        raise AssertionError("unreachable")

    def put(self, url: str, data: bytes, headers: dict[str, str]) -> httpx.Response:
        try:
            return self._client.put(url, content=data, headers=headers)
        except httpx.HTTPError as cause:
            raise ConnectionError("The video upload lost its connection. Start it again.") from cause

    def close(self) -> None:
        self._client.close()


class AsyncTransport:
    def __init__(self, settings: _Settings, client: httpx.AsyncClient | None) -> None:
        self._s = settings
        self._client = client or httpx.AsyncClient(timeout=settings.timeout)

    async def request(self, method: str, path: str, *, query: dict[str, Any] | None = None, body: Any = None) -> Any:
        for attempt in range(self._s.max_retries + 1):
            try:
                response = await self._client.request(
                    method, self._s.base_url + path, params=_query(query), json=body, headers=self._s.headers
                )
            except httpx.TimeoutException as cause:
                raise ConnectionError(f"Skryvo didn't answer within {self._s.timeout:g} seconds.") from cause
            except httpx.TransportError as cause:
                if method in READS and attempt < self._s.max_retries:
                    await asyncio.sleep(_wait(None, attempt) / 2)
                    continue
                raise ConnectionError(f"Couldn't reach Skryvo at {self._s.base_url}.") from cause
            if response.is_success:
                return _answer(response)
            error = _error(response)
            if not _retryable(method, error) or attempt >= self._s.max_retries:
                raise error
            await asyncio.sleep(_wait(error, attempt))
        raise AssertionError("unreachable")

    async def put(self, url: str, data: bytes, headers: dict[str, str]) -> httpx.Response:
        try:
            return await self._client.put(url, content=data, headers=headers)
        except httpx.HTTPError as cause:
            raise ConnectionError("The video upload lost its connection. Start it again.") from cause

    async def aclose(self) -> None:
        await self._client.aclose()
