from __future__ import annotations

from typing import Any


class SkryvoError(Exception):
    """Every failure; ``message`` is a sentence to show the person."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        fields: list[dict[str, Any]] | None = None,
        retry_after: float | None = None,
        request_id: str | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.fields = fields or []
        self.retry_after = retry_after
        self.request_id = request_id
        self.body = body


class AuthenticationError(SkryvoError):
    """401: the key is missing, revoked or mistyped."""


class PermissionDeniedError(SkryvoError):
    """403: the key's team role can't do this."""


class NotFoundError(SkryvoError):
    pass


class RefusedError(SkryvoError):
    """422: Skryvo refused, and ``message`` says why."""


class RateLimitError(SkryvoError):
    pass


class ServerError(SkryvoError):
    pass


class ConnectionError(SkryvoError):
    """No answer: the network failed or the timeout passed."""


class WebhookVerificationError(SkryvoError):
    pass


_BY_STATUS = {
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    422: RefusedError,
    429: RateLimitError,
}


def error_from_response(status: int, body: Any, headers: Any) -> SkryvoError:
    said = body if isinstance(body, dict) else {}
    fields = said.get("details") if isinstance(said.get("details"), list) else []
    if isinstance(said.get("detail"), str):
        message = said["detail"]
    elif fields:
        message = "Check the request: " + "; ".join(f"{f.get('field')}: {f.get('message')}" for f in fields) + "."
    else:
        message = said.get("message") or f"Skryvo answered {status}."
    try:
        retry_after: float | None = float(headers.get("retry-after"))
    except (TypeError, ValueError):
        retry_after = None
    kind = _BY_STATUS.get(status) or (ServerError if status >= 500 else SkryvoError)
    return kind(
        message,
        status=status,
        code=said.get("error"),
        fields=fields,
        retry_after=retry_after if retry_after and retry_after > 0 else None,
        request_id=headers.get("x-request-id"),
        body=body,
    )
