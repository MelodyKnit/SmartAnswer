"""Shared synchronous HTTP helpers for model and web-search providers.

The project uses ``httpx`` here instead of hand-rolled ``urllib`` opener code so
timeouts, proxy handling, status errors, and JSON decoding share one small,
testable boundary.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx


class HttpClientError(RuntimeError):
    """HTTP request failure with a redaction-friendly summary."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str = "",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def request_text(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
    params: dict[str, str] | None = None,
    timeout: float,
    proxy_env: str,
) -> str:
    """Send an HTTP request and return response text, using an optional proxy env var."""
    try:
        response = httpx.request(
            method,
            normalize_container_loopback_url(url),
            headers=headers,
            json=json_body,
            params=params,
            timeout=timeout,
            proxy=_proxy_from_env(proxy_env),
        )
        response.raise_for_status()
        return response.text
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        raise HttpClientError(
            f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}; body={body[:1000]}",
            status_code=exc.response.status_code,
            response_body=body,
        ) from exc
    except httpx.HTTPError as exc:
        raise HttpClientError(str(exc)) from exc


def request_bytes(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: Any | None = None,
    params: dict[str, str] | None = None,
    timeout: float,
    proxy_env: str,
    max_bytes: int | None = None,
    redirect_validator: Callable[[str], bool] | None = None,
    max_redirects: int = 3,
) -> tuple[bytes, str]:
    """发送请求并返回受限长度的二进制响应与 Content-Type。

    ``redirect_validator`` 用于下载不可信服务返回的临时资源地址。
    指定后会逐跳校验重定向目标，避免首个公网地址跳转到内网资源。
    """

    try:
        request_url = normalize_container_loopback_url(url)
        redirect_count = 0
        while True:
            with httpx.stream(
                method,
                request_url,
                headers=headers,
                json=json_body,
                params=params,
                timeout=timeout,
                proxy=_proxy_from_env(proxy_env),
                follow_redirects=redirect_validator is None,
            ) as response:
                if response.is_redirect and redirect_validator is not None:
                    location = str(response.headers.get("location") or "").strip()
                    if not location:
                        raise HttpClientError("Redirect response is missing its Location header")
                    if redirect_count >= max_redirects:
                        raise HttpClientError("Response exceeded the configured redirect limit")
                    redirect_url = str(response.url.join(location))
                    if not redirect_validator(redirect_url):
                        raise HttpClientError("Redirect target is not allowed")
                    request_url = normalize_container_loopback_url(redirect_url)
                    redirect_count += 1
                    continue
                if response.is_error:
                    error_chunks: list[bytes] = []
                    error_size = 0
                    for chunk in response.iter_bytes():
                        remaining = 1_000 - error_size
                        if remaining <= 0:
                            break
                        error_chunks.append(chunk[:remaining])
                        error_size += min(len(chunk), remaining)
                    body = b"".join(error_chunks).decode("utf-8", errors="replace")
                    raise HttpClientError(
                        f"HTTP {response.status_code}: {response.reason_phrase}; body={body}",
                        status_code=response.status_code,
                        response_body=body,
                    )
                declared_size = response.headers.get("content-length", "")
                if max_bytes is not None and declared_size.isdigit() and int(declared_size) > max_bytes:
                    raise HttpClientError("Response body exceeds the configured size limit")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if max_bytes is not None and total > max_bytes:
                        raise HttpClientError("Response body exceeds the configured size limit")
                    chunks.append(chunk)
                return b"".join(chunks), str(response.headers.get("content-type") or "")
    except httpx.HTTPError as exc:
        raise HttpClientError(str(exc)) from exc


def request_multipart_text(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    timeout: float,
    proxy_env: str,
) -> str:
    """发送 multipart 请求并返回文本，供标准 Images 编辑接口使用。"""

    try:
        response = httpx.request(
            method,
            normalize_container_loopback_url(url),
            headers=headers,
            data=data,
            files=files,
            timeout=timeout,
            proxy=_proxy_from_env(proxy_env),
        )
        response.raise_for_status()
        return response.text
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        raise HttpClientError(
            f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}; body={body[:1000]}",
            status_code=exc.response.status_code,
            response_body=body,
        ) from exc
    except httpx.HTTPError as exc:
        raise HttpClientError(str(exc)) from exc


def get_json(
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float,
    proxy_env: str,
) -> dict:
    """Send a GET request and decode a JSON object response."""
    text = request_text(
        "GET",
        url,
        headers=headers,
        params=params,
        timeout=timeout,
        proxy_env=proxy_env,
    )
    return httpx.Response(200, text=text).json()


def post_json(
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
    timeout: float,
    proxy_env: str,
) -> dict:
    """Send a JSON POST request and decode a JSON object response."""
    text = request_text(
        "POST",
        url,
        headers=headers,
        json_body=payload,
        timeout=timeout,
        proxy_env=proxy_env,
    )
    return httpx.Response(200, text=text).json()


def _proxy_from_env(proxy_env: str) -> str | None:
    proxy_url = os.getenv(proxy_env, "").strip()
    if not proxy_url:
        return None
    return normalize_container_loopback_url(proxy_url)


def is_running_in_container() -> bool:
    """Return whether the current process appears to run inside a container."""

    return Path("/.dockerenv").exists()


def normalize_container_loopback_url(
    url: str,
    *,
    host_alias: str = "host.docker.internal",
) -> str:
    """Rewrite loopback URLs to a host alias when running inside a container.

    Containerized services cannot reach host-side dependencies through ``127.0.0.1`` or
    ``localhost``. When we detect those hostnames inside a container, rewrite them to the
    explicit host gateway alias so existing host-bound integrations keep working.
    """

    raw = (url or "").strip()
    if not raw or not is_running_in_container():
        return raw
    parsed = urlsplit(raw)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return raw
    if not host_alias.strip():
        return raw
    netloc = host_alias.strip()
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    if parsed.username:
        credentials = parsed.username
        if parsed.password:
            credentials += f":{parsed.password}"
        netloc = f"{credentials}@{netloc}"
    rewritten = SplitResult(
        scheme=parsed.scheme,
        netloc=netloc,
        path=parsed.path,
        query=parsed.query,
        fragment=parsed.fragment,
    )
    return urlunsplit(rewritten)
