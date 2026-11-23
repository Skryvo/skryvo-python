# skryvo

The Skryvo SDK for Python: write posts, articles, emails, ads and listings in a brand's voice, design their
pictures, and schedule them to the person's channels once they approve. Sync and async, typed, on httpx.

[Skryvo](https://skryvo.ai) is a hosted AI content platform. This package is a client for its agent API
(`https://api.skryvo.ai/api/v1/agent`) with a helper that verifies webhook signatures.

- Python 3.10 or later. Depends on `httpx` and `typing_extensions`.
- Docs: https://skryvo.ai/docs/
- MIT licensed. Skryvo itself is a paid service with a 7-day free trial on Hobby and Pro: https://skryvo.ai/pricing/

## Install

```bash
pip install skryvo
```

## Sign in

Create an API key (`sk_skryvo_…`) in Skryvo under
[Settings › API & agents](https://app.skryvo.ai/settings/agents); it is shown once. Pass it as `api_key`, or set
`SKRYVO_API_KEY`. A key acts in the workspace it was made in, with its holder's role there. An OAuth access token
(`sko_…`) works in place of a key.

## 60 seconds

```python
from skryvo import Skryvo

with Skryvo() as skryvo:  # reads SKRYVO_API_KEY
    brand = skryvo.brands.list()[0]
    # {'id': 'bv_3c9d0e', 'name': 'Northside Coffee', 'is_default': True}

    linkedin = next(c for c in skryvo.channels.list() if c["platform"] == "linkedin" and not c["needs_reconnect"])
    # {'id': 'conn_8f2e1a', 'platform': 'linkedin', 'kind': 'social', 'can': {'words': 3000, 'poll': True, ...}, ...}

    drafts = skryvo.posts.write(topic="Our new studio opens Saturday", brand_id=brand["id"], platforms=["linkedin"], pictures=False)
    # {'status': 'written', 'generation_id': 'gen_5d1c9a',
    #  'posts': [{'platform': 'linkedin', 'text': 'Our new studio opens this Saturday in Leeds. #coffee', 'hashtags': ['coffee']}], ...}

    # Show the draft to the person. Only after their go-ahead:
    [post] = skryvo.posts.schedule(text=drafts["posts"][0]["text"], channel_ids=[linkedin["id"]], at="2026-11-24T09:00:00+00:00")
    # {'id': 'c1a2b3c4d5', 'platform': 'linkedin', 'date': '2026-11-24', 'time': '09:00', 'status': 'scheduled', ...}
```

Async is the same with `await`:

```python
from skryvo import AsyncSkryvo

async with AsyncSkryvo() as skryvo:
    plan = await skryvo.articles.plan(topic="How to choose a coffee grinder for home")
    await skryvo.articles.write(plan_id=plan["plan_id"], answers=[{"question": plan["questions"][0], "answer": "We test every grinder for a month."}])
    article = await skryvo.articles.wait_until_done(plan["plan_id"])
    # {'status': 'done', 'title': 'How to choose a coffee grinder for home', 'words': 1512, 'score': 88,
    #  'claims': {'checked': 9, 'verified': 9, ...}, 'open_in_skryvo': 'https://app.skryvo.ai/generate/blog/gen_a7c2f0', ...}
```

**Drafting and scheduling are separate on purpose.** `posts.write` drafts and schedules nothing. When it leaves a
choice to the brand's defaults (platforms or pictures), Skryvo writes nothing and answers `status: "confirm"`
with each setting, where it came from, the cost and what is left this month: show it, then call again with the
person's final values and `confirmed=True`. `posts.schedule` publishes the words you send, so send only words the
person approved. Any scheduled post can be cancelled before it goes out.

## Every operation

Request fields are keyword arguments named as in the API; answers are typed dicts (`skryvo.types`).

| Method | Route |
|---|---|
| `account.me()`, `account.balance()`, `account.save_defaults(**)` | `GET /me`, `GET /balance`, `POST /defaults` |
| `brands.list()`, `brands.add(**)`, `brands.design(brand_id=)`, `brands.change_look(**)` | `/brands`, `/design`, `/design/look` |
| `channels.list()`, `channels.platforms()` | `GET /channels`, `GET /platforms` |
| `posts.write(**)` | `POST /drafts` |
| `posts.schedule(**)`, `posts.list(days=)` | `POST /posts`, `GET /posts` |
| `posts.change(id, **)`, `posts.review(id, **)`, `posts.cancel(id)` | `PATCH`, `POST …/review`, `DELETE /posts/{id}` |
| `pictures.design(**)` | `POST /pictures` |
| `articles.plan(**)`, `articles.write(**)`, `articles.status(id)`, `articles.wait_until_done(id)` | `/articles/plan`, `/articles`, `/articles/{id}` |
| `articles.publish(id, **)`, `articles.seo(id)`, `articles.improve(id, **)`, `articles.results(id)` | `/articles/{id}/publish`, `/seo`, `/improve`, `/results` |
| `articles.import_(**)`, `articles.repurpose(id, **)` | `/articles/import`, `/articles/{id}/posts` |
| `emails.write(**)`, `listings.write(**)`, `ads.write(**)` | `/emails`, `/listings`, `/ads` |
| `calendar.plan(**)`, `calendar.accept(**)` | `/calendar/plan`, `/calendar/accept` |
| `content.find(kind=, limit=)` | `GET /content` |
| `videos.list()`, `videos.add(**)`, `videos.finish(id)`, `videos.upload(data, name=)` | `/videos`, the upload, `/videos/{id}/finish` |
| `results.get(days=, brand_id=)` | `GET /results` |
| `webhooks.list()`, `webhooks.create(**)`, `webhooks.delete(id)`, `webhooks.test(id)`, `webhooks.deliveries(id)` | `/webhooks…` |
| `request(method, path, query=, body=)` | any agent route |

## Webhooks

Subscribe an HTTPS endpoint to `post.published`, `post.failed`, `article.ready`, `article.failed` or
`results.ready` with `webhooks.create(url=..., events=[...])`. The answer carries the endpoint's `secret`
(`whsec_…`) once; keep it. Verify each delivery against the raw body, before parsing it:

```python
from skryvo import WebhookVerificationError, verify_webhook

@app.post("/skryvo")
async def skryvo_event(request: Request):
    try:
        event = verify_webhook(await request.body(), request.headers.get("skryvo-signature"), SECRET)
    except WebhookVerificationError:
        return Response(status_code=400)
    if event["type"] == "post.published":
        print("live:", event["data"]["posted_url"])
    return Response(status_code=204)
```

`verify_webhook` refuses a signature older than five minutes, compares in constant time, and accepts any of
several `v1=` values. Dedupe on the event's `id`, which is the same on every retry.

## Errors

Every failure is a `SkryvoError` with `status`, `message`, `fields`, `retry_after` and `request_id`:
`RefusedError` (422, Skryvo's own sentence to show the person, and `fields` when a field check failed),
`AuthenticationError` (401), `PermissionDeniedError` (403), `NotFoundError` (404), `RateLimitError` (429, over 60
requests a minute or 1000 an hour for the key), `ServerError` (5xx) and `ConnectionError` (no answer within the
timeout, 180 seconds by default).

The client retries a rate limit after `Retry-After` (twice by default, `max_retries` changes it). It retries a
dropped connection or a 502, 503 or 504 only on reads, so a call that spends generations is never sent twice.

```python
Skryvo(api_key, base_url=..., timeout=180.0, max_retries=2, http_client=httpx.Client(...), user_agent=...)
```

## Contributing

```bash
python -m venv .venv && .venv/bin/pip install -e . pytest mypy ruff
.venv/bin/pytest        # offline, against the examples in spec/openapi.json
.venv/bin/mypy          # strict
.venv/bin/ruff check
```

`spec/openapi.json` is Skryvo's published description of the agent API (`https://api.skryvo.ai/openapi.json`).
`python scripts/generate.py` rewrites `src/skryvo/types.py` and `src/skryvo/_resources.py` from it, and stops
when the spec has an operation without a method name in its table. Replace the file, run the script and the tests.

Report bugs at https://github.com/Skryvo/skryvo-python/issues. Questions: support@skryvo.ai.

## License

MIT © Flutter Studio LLC
