"""HTTP helper for job sources. Timeouts, no infinite retries, no secret logging."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from career_agent.integrations.job_sources.errors import JobSourceError

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
USER_AGENT = "PersonalCareerAgent/0.1 (local job search; not a public aggregator)"


@dataclass(frozen=True)
class URLCheckResult:
    status_code: int | None
    error: str | None = None


class JobHttpClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=DEFAULT_TIMEOUT,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def get_json(
        self,
        source: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        try:
            response = self._client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise JobSourceError(source, "request timed out") from exc
        except httpx.HTTPError as exc:
            raise JobSourceError(source, f"network error: {exc.__class__.__name__}") from exc

        if response.status_code == 429:
            raise JobSourceError(source, "rate limited by the provider", status_code=429)
        if response.status_code >= 500:
            raise JobSourceError(
                source,
                "provider error",
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise JobSourceError(
                source,
                "request was rejected",
                status_code=response.status_code,
            )

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise JobSourceError(source, "response is not valid JSON") from exc
        except ValueError as exc:
            raise JobSourceError(source, "response is not valid JSON") from exc

    def check_url(self, url: str) -> URLCheckResult:
        """Check a page without downloading its full body."""
        try:
            response = self._client.head(url, follow_redirects=False)

            # Some providers do not support HEAD. Retry once with a tiny range.
            if response.status_code in {405, 501}:
                with self._client.stream(
                    "GET",
                    url,
                    headers={"Range": "bytes=0-0"},
                    follow_redirects=False,
                ) as fallback:
                    return URLCheckResult(status_code=fallback.status_code)

            return URLCheckResult(status_code=response.status_code)

        except httpx.TimeoutException:
            return URLCheckResult(status_code=None, error="timeout")
        except httpx.HTTPError as exc:
            return URLCheckResult(
                status_code=None,
                error=exc.__class__.__name__,
            )
