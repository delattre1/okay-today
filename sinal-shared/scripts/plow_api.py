#!/usr/bin/env python3
"""The two Plow Chat calls this agent makes without a model turn.

Both carry the tenant's bearer, so both refuse a redirect: a 30x from a proxy
would otherwise walk the credential to whatever host the Location header names.
The token is read from the process environment and never appears in argv, in a
log line, or in an exception message.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 20


class ApiError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"Plow API {status}: {detail}")
        self.status = status
        self.detail = detail


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise ApiError(code, f"refused a redirect to {newurl.split('?')[0]}")


_OPENER = urllib.request.build_opener(_NoRedirect)


def config() -> tuple:
    """(base, token), or a loud exit. Both come from the container environment,
    which first boot fills from the credential the host dropped in."""
    base = (os.environ.get("PLOW_API_BASE") or "").strip().rstrip("/")
    token = (os.environ.get("PLOW_AGENT_TOKEN") or "").strip()
    if not base or not token:
        raise ApiError(0, "PLOW_API_BASE or PLOW_AGENT_TOKEN is missing from this process")
    return base, token


def _request(method: str, url: str, token: str, payload: dict = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise ApiError(exc.code, detail) from None
    except urllib.error.URLError as exc:
        raise ApiError(0, f"{type(exc.reason).__name__ if exc.reason else 'URLError'}") from None
    return json.loads(body) if body.strip() else {}


def send_message(chat_uid: str, body: str) -> dict:
    base, token = config()
    return _request("POST", f"{base}/v1/chats/{chat_uid}/messages", token, {"body": body})


def recent_messages(chat_uid: str, limit: int = 50) -> list:
    """Newest first, as the API returns them."""
    base, token = config()
    payload = _request("GET", f"{base}/v1/chats/{chat_uid}/messages?limit={int(limit)}", token)
    return payload.get("data") or []
