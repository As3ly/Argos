from __future__ import annotations

import os
from typing import Optional

DEFAULT_HTTP_PROXY = "http://163.116.128.80:8080"
DEFAULT_HTTPS_PROXY = "http://163.116.128.80:8080"


def _framatome_proxy(name: str) -> Optional[str]:
    try:
        import framatome  # type: ignore
    except Exception:
        return None

    value = getattr(framatome, name, None)
    return str(value).strip() if value else None


def get_http_proxy(*, default: str | None = DEFAULT_HTTP_PROXY) -> Optional[str]:
    return (
        _framatome_proxy("HTTP_PROXY")
        or os.getenv("ARGOS_HTTP_PROXY")
        or os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
        or default
    )


def get_https_proxy(*, default: str | None = DEFAULT_HTTPS_PROXY) -> Optional[str]:
    return (
        _framatome_proxy("HTTPS_PROXY")
        or os.getenv("ARGOS_HTTPS_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or default
    )


def get_requests_proxies() -> dict[str, str]:
    proxies = {
        "http": get_http_proxy(),
        "https": get_https_proxy(),
    }
    return {key: value for key, value in proxies.items() if value}


def get_azure_proxy() -> Optional[str]:
    use_proxy = os.getenv("AZURE_USE_PROXY", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not use_proxy:
        return None
    return os.getenv("AZURE_PROXY_URL") or get_https_proxy()
