# Changelog

## 0.1.0

- First release: `Skryvo` and `AsyncSkryvo` clients on httpx for every route of the Skryvo agent API, with
  request and answer types generated from its OpenAPI description.
- `articles.wait_until_done` and `videos.upload` helpers.
- `verify_webhook` checks a delivery's `Skryvo-Signature` header.
- Retries a rate limit after `Retry-After`, and a dropped connection or a 502 to 504 on reads only.
