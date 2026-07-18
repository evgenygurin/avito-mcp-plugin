"""Сборка движка парсинга из переменных окружения.

Сервер не читает `.env` — переменные передаёт шелл/агент. См. `.env.example`.
"""

from __future__ import annotations

import json
import os

from .cookies.factory import build_cookies_provider
from .http.client import HttpClient
from .proxies.factory import build_proxy


def _parse_own_cookies(raw: str | None) -> dict[str, str]:
    """Разобрать `AVITO_OWN_COOKIES`: JSON-объект либо строку `k=v; k=v`."""
    if not raw:
        return {}
    raw = raw.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}

    result: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def build_http_client() -> HttpClient:
    """Собрать `HttpClient` (провайдер кук + прокси) из окружения."""
    provider = build_cookies_provider(
        os.getenv("AVITO_COOKIE_PROVIDER", "spfa"),
        api_key=os.getenv("SPFA_API_KEY"),
        own_cookies=_parse_own_cookies(os.getenv("AVITO_OWN_COOKIES")),
    )
    proxy = build_proxy(
        os.getenv("AVITO_PROXY", ""),
        os.getenv("AVITO_PROXY_CHANGE_URL", ""),
    )
    max_attempts = int(os.getenv("AVITO_MAX_ROTATE_ATTEMPTS", "18"))
    return HttpClient(proxy=proxy, cookies=provider, max_attempts=max_attempts)
