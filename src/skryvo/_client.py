from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable
from typing import Any

import httpx
from typing_extensions import Self

from . import _resources as r
from . import types as t
from ._errors import SkryvoError
from ._http import AsyncTransport, SyncTransport, _Settings

DEFAULT_BASE_URL = "https://api.skryvo.ai/api/v1/agent"
ArticleOutcome = t.ArticleStarted | t.ArticleWriting | t.ArticleFailed | t.ArticleDone


def _settings(
    api_key: str | None, base_url: str, timeout: float, max_retries: int, user_agent: str | None
) -> _Settings:
    key = (api_key or os.environ.get("SKRYVO_API_KEY") or "").strip()
    if not key:
        raise SkryvoError(
            "No Skryvo API key. Create one at https://app.skryvo.ai/settings/agents and pass api_key "
            "or set SKRYVO_API_KEY."
        )
    return _Settings(key, base_url, timeout, max_retries, user_agent)


def _upload_failed(start: int, status: int) -> SkryvoError:
    return SkryvoError(f"The video upload stopped at byte {start} ({status}). Start it again.", status=status)


class Articles(r.Articles):
    def wait_until_done(
        self,
        article_id: str,
        *,
        interval: float = 30.0,
        timeout: float = 25 * 60.0,
        on_progress: Callable[[ArticleOutcome], None] | None = None,
    ) -> ArticleOutcome:
        """Checks the article until it is done or failed."""
        deadline = time.monotonic() + timeout
        while True:
            status = self.status(article_id)
            if on_progress:
                on_progress(status)
            if status["status"] != "writing":
                return status
            if time.monotonic() + interval > deadline:
                raise SkryvoError(f"The article {article_id} is still being written. Check its status later.")
            time.sleep(interval)


class AsyncArticles(r.AsyncArticles):
    async def wait_until_done(
        self,
        article_id: str,
        *,
        interval: float = 30.0,
        timeout: float = 25 * 60.0,
        on_progress: Callable[[ArticleOutcome], None] | None = None,
    ) -> ArticleOutcome:
        """Checks the article until it is done or failed."""
        deadline = time.monotonic() + timeout
        while True:
            status = await self.status(article_id)
            if on_progress:
                on_progress(status)
            if status["status"] != "writing":
                return status
            if time.monotonic() + interval > deadline:
                raise SkryvoError(f"The article {article_id} is still being written. Check its status later.")
            await asyncio.sleep(interval)


class Videos(r.Videos):
    def upload(self, data: bytes, *, name: str, mime: str = "") -> t.VideoReady:
        """Opens an upload, sends every chunk, and finishes it; the video is then ready to schedule."""
        opened = self.add(name=name, size=len(data), mime=mime)
        chunk = opened["chunk_bytes"]
        for start in range(0, len(data), chunk):
            end = min(start + chunk, len(data))
            sent = self._t.put(
                opened["upload_url"], data[start:end], {"content-range": f"bytes {start}-{end - 1}/{len(data)}"}
            )
            if (sent.status_code >= 300) if end == len(data) else (sent.status_code != 308):
                raise _upload_failed(start, sent.status_code)
        return self.finish(opened["id"])


class AsyncVideos(r.AsyncVideos):
    async def upload(self, data: bytes, *, name: str, mime: str = "") -> t.VideoReady:
        """Opens an upload, sends every chunk, and finishes it; the video is then ready to schedule."""
        opened = await self.add(name=name, size=len(data), mime=mime)
        chunk = opened["chunk_bytes"]
        for start in range(0, len(data), chunk):
            end = min(start + chunk, len(data))
            sent = await self._t.put(
                opened["upload_url"], data[start:end], {"content-range": f"bytes {start}-{end - 1}/{len(data)}"}
            )
            if (sent.status_code >= 300) if end == len(data) else (sent.status_code != 308):
                raise _upload_failed(start, sent.status_code)
        return await self.finish(opened["id"])


class Skryvo:
    """The Skryvo agent API. Drafting schedules nothing; ``posts.schedule`` publishes the words it is given."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 180.0,
        max_retries: int = 2,
        http_client: httpx.Client | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._transport = SyncTransport(_settings(api_key, base_url, timeout, max_retries, user_agent), http_client)
        self.account = r.Account(self._transport)
        self.brands = r.Brands(self._transport)
        self.channels = r.Channels(self._transport)
        self.posts = r.Posts(self._transport)
        self.pictures = r.Pictures(self._transport)
        self.articles = Articles(self._transport)
        self.emails = r.Emails(self._transport)
        self.listings = r.Listings(self._transport)
        self.ads = r.Ads(self._transport)
        self.calendar = r.Calendar(self._transport)
        self.content = r.Content(self._transport)
        self.videos = Videos(self._transport)
        self.results = r.Results(self._transport)
        self.webhooks = r.Webhooks(self._transport)

    def request(self, method: str, path: str, *, query: dict[str, Any] | None = None, body: Any = None) -> Any:
        """Any agent route, for one this version doesn't name yet: ``request("GET", "/me")``."""
        return self._transport.request(method, path, query=query, body=body)

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class AsyncSkryvo:
    """The Skryvo agent API for asyncio; every method is awaited."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 180.0,
        max_retries: int = 2,
        http_client: httpx.AsyncClient | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._transport = AsyncTransport(_settings(api_key, base_url, timeout, max_retries, user_agent), http_client)
        self.account = r.AsyncAccount(self._transport)
        self.brands = r.AsyncBrands(self._transport)
        self.channels = r.AsyncChannels(self._transport)
        self.posts = r.AsyncPosts(self._transport)
        self.pictures = r.AsyncPictures(self._transport)
        self.articles = AsyncArticles(self._transport)
        self.emails = r.AsyncEmails(self._transport)
        self.listings = r.AsyncListings(self._transport)
        self.ads = r.AsyncAds(self._transport)
        self.calendar = r.AsyncCalendar(self._transport)
        self.content = r.AsyncContent(self._transport)
        self.videos = AsyncVideos(self._transport)
        self.results = r.AsyncResults(self._transport)
        self.webhooks = r.AsyncWebhooks(self._transport)

    async def request(self, method: str, path: str, *, query: dict[str, Any] | None = None, body: Any = None) -> Any:
        """Any agent route, for one this version doesn't name yet."""
        return await self._transport.request(method, path, query=query, body=body)

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
