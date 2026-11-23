"""Checks a webhook delivery's ``Skryvo-Signature`` header."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import cast

from ._errors import WebhookVerificationError
from .types import WebhookEvent

Payload = str | bytes


def _bytes(payload: Payload) -> bytes:
    return payload.encode() if isinstance(payload, str) else payload


def sign(payload: Payload, secret: str, timestamp: int) -> str:
    """The hex HMAC-SHA256 Skryvo puts in ``v1=``: of ``<t>.<raw body>`` with the endpoint's secret."""
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + _bytes(payload), hashlib.sha256).hexdigest()


def verify_webhook(
    payload: Payload,
    signature_header: str | None,
    secret: str,
    *,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> WebhookEvent:
    """Returns the event when the header signs the raw body (pass it before any JSON parsing); raises otherwise."""
    if not signature_header:
        raise WebhookVerificationError("The delivery has no Skryvo-Signature header.")
    if not secret:
        raise WebhookVerificationError("Pass the endpoint's secret (whsec_…).")
    t: int | None = None
    given: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t" and value.isdigit():
            t = int(value)
        elif key == "v1" and value:
            given.append(value)
    if t is None or not given:
        raise WebhookVerificationError("The Skryvo-Signature header is not in the form t=…,v1=….")
    if abs((now if now is not None else int(time.time())) - t) > tolerance_seconds:
        raise WebhookVerificationError(f"The signature is older than {tolerance_seconds} seconds.")
    expected = sign(payload, secret, t)
    if not any(hmac.compare_digest(expected, candidate) for candidate in given):
        raise WebhookVerificationError("The signature doesn't match this endpoint's secret.")
    try:
        return cast(WebhookEvent, json.loads(_bytes(payload)))
    except ValueError as cause:
        raise WebhookVerificationError("The delivery's body is not JSON.") from cause
