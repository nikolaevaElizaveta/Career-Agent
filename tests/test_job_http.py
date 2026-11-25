from __future__ import annotations

import httpx
import pytest

from career_agent.integrations.job_sources.errors import JobSourceError
from career_agent.integrations.job_sources.http import JobHttpClient


def _client(handler: object) -> JobHttpClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return JobHttpClient(httpx.Client(transport=transport))


def test_http_429() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    with pytest.raises(JobSourceError) as exc:
        _client(handler).get_json("remotive", "https://example.test/jobs")
    assert exc.value.status_code == 429
    assert "rate limited" in str(exc.value)


def test_http_500() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="broken")

    with pytest.raises(JobSourceError) as exc:
        _client(handler).get_json("remotive", "https://example.test/jobs")
    assert exc.value.status_code == 500


def test_http_timeout() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    with pytest.raises(JobSourceError) as exc:
        _client(handler).get_json("adzuna", "https://example.test/jobs")
    assert "timed out" in str(exc.value)
    assert exc.value.status_code is None


def test_http_invalid_json() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    with pytest.raises(JobSourceError) as exc:
        _client(handler).get_json("remotive", "https://example.test/jobs")
    assert "JSON" in str(exc.value)



def test_url_check_uses_head_without_loading_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "HEAD"
        return httpx.Response(200)

    raw_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    client = JobHttpClient(raw_client)

    try:
        result = client.check_url("https://himalayas.app/jobs/qa")
        assert result.status_code == 200
        assert result.error is None
    finally:
        raw_client.close()


def test_url_check_falls_back_to_range_get() -> None:
    methods = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "HEAD":
            return httpx.Response(405)
        assert request.headers.get("Range") == "bytes=0-0"
        return httpx.Response(206)

    raw_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    client = JobHttpClient(raw_client)

    try:
        result = client.check_url("https://himalayas.app/jobs/qa")
        assert methods == ["HEAD", "GET"]
        assert result.status_code == 206
    finally:
        raw_client.close()
