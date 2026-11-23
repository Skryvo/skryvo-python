import asyncio
import json
import re
import time
from pathlib import Path

import httpx
import pytest

import skryvo
from skryvo import AsyncSkryvo, Skryvo, sign, verify_webhook

SPEC = json.loads((Path(__file__).parent.parent / "spec" / "openapi.json").read_text())
PREFIX = "/api/v1/agent"
KEY = "sk_skryvo_test"


def example(method: str, path: str):
    for template, item in SPEC["paths"].items():
        pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", template) + "$"
        op = item.get(method.lower())
        if op and re.match(pattern, path):
            code = next(c for c in op["responses"] if c.startswith("2"))
            return int(code), op["responses"][code].get("content", {}).get("application/json", {}).get("example")
    return 404, {"detail": "Not Found"}


def from_spec(request: httpx.Request) -> httpx.Response:
    status, body = example(request.method, request.url.path)
    return httpx.Response(status, json=body) if body is not None and status != 204 else httpx.Response(status)


def make(handler=from_spec, **options):
    seen = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = Skryvo(KEY, http_client=httpx.Client(transport=httpx.MockTransport(record)), **options)
    return client, seen


def calls(client):
    i = "x1"
    client.account.me()
    client.account.balance()
    client.account.save_defaults(kind="post", settings={"tone": "friendly"})
    client.brands.list()
    client.brands.add(name="Northside", website="https://example.com")
    client.brands.design(brand_id="bv_1")
    client.brands.change_look(change="closer")
    client.channels.list()
    client.channels.platforms()
    client.posts.write(topic="Our studio opens Saturday", platforms=["linkedin"])
    client.posts.schedule(text="Hello", channel_ids=["c1"])
    client.posts.list(days=7)
    client.posts.change(i, text="New words")
    client.posts.review(i, approve=True)
    client.posts.cancel(i)
    client.pictures.design(text="Hello", platforms=["linkedin"])
    client.articles.plan(topic="Grinders")
    client.articles.write(plan_id="pl_1")
    client.articles.status(i)
    client.articles.publish(i, channel_id="c1")
    client.articles.seo(i)
    client.articles.improve(i)
    client.articles.results(i)
    client.articles.import_(is_mine=True, url="https://example.com/post")
    client.articles.repurpose(i, platforms=["linkedin"])
    client.emails.write(about="Spring menu")
    client.listings.write(product="Board", features=["Oak"])
    client.ads.write(product="Board", platforms=["google_ads"])
    client.calendar.plan(start_date="2026-12-01")
    client.calendar.accept(
        items=[{"date": "2026-12-01", "time": "09:00", "content_type": "social_media", "topic": "t"}]
    )
    client.content.find(kind="article")
    client.videos.list()
    client.videos.add(name="a.mp4", size=10)
    client.videos.finish(i)
    client.results.get(days=30)
    client.webhooks.list()
    client.webhooks.create(url="https://example.com/hook", events=["post.published"])
    client.webhooks.delete(i)
    client.webhooks.test(i)
    client.webhooks.deliveries(i)


def test_every_operation_in_the_spec_has_a_method():
    client, seen = make()
    calls(client)
    called = {f"{r.method} {re.sub(r'x1|pl_1', '{}', r.url.path[len(PREFIX) :])}" for r in seen}
    wanted = {
        f"{method.upper()} {re.sub(r'{[^}]+}', '{}', path[len(PREFIX) :])}"
        for path, item in SPEC["paths"].items()
        for method in item
    }
    assert called == wanted


def test_the_async_client_covers_the_same_operations():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return from_spec(request)

    async def main():
        async with AsyncSkryvo(KEY, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as client:
            brands = await client.brands.list()
            drafted = await client.posts.write(topic="Our studio opens Saturday", platforms=["linkedin"])
            await client.posts.cancel("p1")
            return brands, drafted

    brands, drafted = asyncio.run(main())
    assert brands[0]["id"] == "bv_3c9d0e"
    assert drafted["status"] == "written"
    assert [r.method for r in seen] == ["GET", "POST", "DELETE"]


def test_sends_the_key_json_and_query_and_unwraps_lists():
    client, seen = make()
    channels = client.channels.list()
    client.posts.list(days=7)
    client.brands.design()
    client.posts.schedule(text="Hi", channel_ids=["c1"], at="2026-12-01T09:00:00+01:00")
    assert channels[0]["platform"] == "linkedin"
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"
    assert seen[0].headers["user-agent"].startswith("skryvo-python/")
    assert seen[1].url.query == b"days=7"
    assert seen[2].url.query == b""
    assert json.loads(seen[3].content) == {"text": "Hi", "channel_ids": ["c1"], "at": "2026-12-01T09:00:00+01:00"}
    assert str(seen[3].url) == "https://api.skryvo.ai/api/v1/agent/posts"


def test_reads_the_key_from_the_environment_and_refuses_to_start_without_one(monkeypatch):
    monkeypatch.delenv("SKRYVO_API_KEY", raising=False)
    with pytest.raises(skryvo.SkryvoError, match="No Skryvo API key"):
        Skryvo()
    monkeypatch.setenv("SKRYVO_API_KEY", KEY)
    Skryvo().close()


def test_a_refusal_carries_skryvos_own_words():
    client, _ = make(lambda r: httpx.Response(422, json={"detail": "That time has passed. Pick a time in the future."}))
    with pytest.raises(skryvo.RefusedError) as caught:
        client.posts.schedule(text="Hi", channel_ids=["c1"])
    assert caught.value.status == 422
    assert str(caught.value) == "That time has passed. Pick a time in the future."


def test_a_validation_failure_names_each_field():
    body = {
        "error": "validation_error",
        "message": "Request validation failed",
        "details": [
            {"field": "topic", "message": "String should have at least 3 characters", "type": "string_too_short"}
        ],
    }
    client, _ = make(lambda r: httpx.Response(422, json=body))
    with pytest.raises(skryvo.RefusedError, match="topic: String should have at least 3 characters") as caught:
        client.posts.write(topic="x")
    assert caught.value.fields[0]["field"] == "topic"


def test_401_is_an_authentication_error():
    client, _ = make(lambda r: httpx.Response(401, json={"detail": "Send a live Skryvo API key."}))
    with pytest.raises(skryvo.AuthenticationError):
        client.account.me()


def test_a_rate_limit_is_retried_after_retry_after_even_on_a_write():
    answers = iter(
        [
            httpx.Response(429, json={"message": "slow"}, headers={"retry-after": "0.01"}),
            httpx.Response(200, json={"status": "written", "posts": []}),
        ]
    )
    client, seen = make(lambda r: next(answers))
    assert client.posts.write(topic="Hello there", platforms=["x"])["status"] == "written"
    assert len(seen) == 2


def test_a_503_is_retried_on_a_read_but_never_on_a_write_that_spends():
    answers = iter([httpx.Response(503, json={"message": "busy"}, headers={"retry-after": "0.01"})])
    client, _ = make(lambda r: next(answers, None) or from_spec(r))
    assert client.account.me()["plan"] == "pro"
    client, seen = make(lambda r: httpx.Response(503, json={"message": "Our AI service is unavailable right now."}))
    with pytest.raises(skryvo.ServerError):
        client.posts.write(topic="Hello there", platforms=["x"])
    assert len(seen) == 1


def test_a_dropped_connection_and_a_timeout_are_connection_errors():
    def drop(request):
        raise httpx.ConnectError("down", request=request)

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    client, _ = make(drop, max_retries=0)
    with pytest.raises(skryvo.ConnectionError, match="Couldn't reach Skryvo"):
        client.account.me()
    client, _ = make(slow)
    with pytest.raises(skryvo.ConnectionError, match="didn't answer within 180 seconds"):
        client.account.me()


def test_wait_until_done_checks_until_the_article_is_done():
    done = example("GET", f"{PREFIX}/articles/pl_1")[1]
    answers = iter([{"article_id": "pl_1", "status": "writing", "stage": "Researching"}, done])
    client, _ = make(lambda r: httpx.Response(200, json=next(answers)))
    progress = []
    out = client.articles.wait_until_done("pl_1", interval=0.001, on_progress=lambda s: progress.append(s["status"]))
    assert out["status"] == "done"
    assert progress == ["writing", "done"]


def test_videos_upload_sends_each_chunk_with_its_range_then_finishes():
    def handler(request):
        if request.url.path.endswith("/videos"):
            return httpx.Response(
                201, json={"id": "clip_1", "upload_url": "https://upload.example/s", "chunk_bytes": 4}
            )
        if request.url.host == "upload.example":
            return httpx.Response(200 if request.headers["content-range"].endswith("9/10") else 308)
        return httpx.Response(
            200, json={"video_id": "clip_1", "status": "ready", "seconds": 12, "width": 1080, "height": 1920}
        )

    client, seen = make(handler)
    ready = client.videos.upload(b"0123456789", name="launch.mp4", mime="video/mp4")
    assert ready["status"] == "ready"
    puts = [r for r in seen if r.method == "PUT"]
    assert [r.headers["content-range"] for r in puts] == ["bytes 0-3/10", "bytes 4-7/10", "bytes 8-9/10"]
    assert all("authorization" not in r.headers for r in puts)
    assert seen[-1].url.path == f"{PREFIX}/videos/clip_1/finish"


SECRET = "whsec_test"
BODY = json.dumps(
    {"id": "evt_1", "type": "post.published", "created": "2026-11-23T10:00:00Z", "test": False, "data": {"id": "p1"}}
)


def test_verify_webhook_accepts_a_delivery_signed_with_the_secret():
    t = 1_800_000_000
    header = f"t={t},v1={sign(BODY, SECRET, t)}"
    assert verify_webhook(BODY, header, SECRET, now=t + 10)["type"] == "post.published"
    assert (
        verify_webhook(BODY.encode(), f"t={t},v1={'0' * 64},v1={sign(BODY, SECRET, t)}", SECRET, now=t)["id"] == "evt_1"
    )


def test_verify_webhook_refuses_a_changed_body_a_wrong_secret_an_old_signature_and_a_bad_header():
    t = 1_800_000_000
    header = f"t={t},v1={sign(BODY, SECRET, t)}"
    with pytest.raises(skryvo.WebhookVerificationError, match="doesn't match"):
        verify_webhook(BODY.replace("p1", "p2"), header, SECRET, now=t)
    with pytest.raises(skryvo.WebhookVerificationError):
        verify_webhook(BODY, header, "whsec_other", now=t)
    with pytest.raises(skryvo.WebhookVerificationError, match="older than 300 seconds"):
        verify_webhook(BODY, header, SECRET, now=t + 301)
    with pytest.raises(skryvo.WebhookVerificationError, match="form t="):
        verify_webhook(BODY, "v1=abc", SECRET)
    with pytest.raises(skryvo.WebhookVerificationError, match="no Skryvo-Signature"):
        verify_webhook(BODY, None, SECRET, now=int(time.time()))


def test_generated_code_matches_the_spec():
    import subprocess
    import sys

    root = Path(__file__).parent.parent
    before = {p: p.read_text() for p in [root / "src/skryvo/types.py", root / "src/skryvo/_resources.py"]}
    subprocess.run([sys.executable, str(root / "scripts/generate.py")], check=True, capture_output=True)
    assert {p: p.read_text() for p in before} == before
