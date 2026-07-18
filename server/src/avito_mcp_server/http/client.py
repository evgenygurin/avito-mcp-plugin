"""HTTP-клиент скрапинга: curl_cffi + rotate-until-clean + follow-редирект.

Пул выходных IP смешанный (часть прожжена Qrator). Клиент ротирует IP на каждый
block-код (401/403/429), пока не попадёт на чистый и не получит 200. Затем
``fetch_catalog`` следует SSR-редиректу на канонический URL категории. Схема
воспроизведена и валидирована живьём.
"""

from __future__ import annotations

import random
import time
from typing import Any, cast

from curl_cffi import requests as cffi

from ..cookies.base import CookiesProvider
from ..parser import classify
from ..proxies.proxy import Proxy

_IMPERSONATE = ("chrome", "edge", "safari")
_BLOCK_CODES = (401, 403, 429)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _build_session(proxy_url: str | None) -> Any:
    session: Any = cffi.Session(impersonate=cast(Any, random.choice(_IMPERSONATE)))
    version = random.randint(142, 147)
    session.headers.update(
        {
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{version}.0.0.0 Safari/537.36"
            ),
            "accept-language": "ru-RU,ru;q=0.9",
        }
    )
    if proxy_url:
        session.proxies = {"http": proxy_url, "https": proxy_url}
    return session


class HttpClient:
    def __init__(
        self,
        proxy: Proxy,
        cookies: CookiesProvider | None,
        max_attempts: int = 18,
        wait_after_rotate: float = 9.0,
        timeout: float = 20.0,
        block_codes: tuple[int, ...] = _BLOCK_CODES,
    ) -> None:
        self.proxy = proxy
        self.cookies = cookies
        self.max_attempts = max_attempts
        self.wait_after_rotate = wait_after_rotate
        self.timeout = timeout
        self.block_codes = block_codes

    def get(self, url: str) -> Any:
        """GET с ротацией IP до чистого. Возвращает 200-ответ или бросает RuntimeError."""
        cookies = self.cookies.get() if self.cookies else None
        for _ in range(self.max_attempts):
            with _build_session(self.proxy.httpx_proxy()) as session:
                resp = session.get(
                    url, cookies=cookies, timeout=self.timeout, allow_redirects=True
                )
            if self.cookies:
                self.cookies.update(resp)
            if resp.status_code in self.block_codes:
                self.proxy.rotate()
                _sleep(self.wait_after_rotate)
                cookies = self.cookies.get() if self.cookies else None
                continue
            return resp
        raise RuntimeError(
            f"не удалось получить {url} за {self.max_attempts} попыток (блокировки IP)"
        )


def fetch_catalog(
    client: HttpClient, url: str, max_redirects: int = 3
) -> tuple[str, Any]:
    """Забрать страницу и следовать SSR-редиректу на канонический URL.

    Возвращает результат ``classify``: ``("ok", catalog)`` при успехе, либо
    ``("softblock"|"nojson", None)``; ``("redirect_loop", None)`` при зацикливании.
    """
    for _ in range(max_redirects + 1):
        resp = client.get(url)
        kind, payload = classify(resp.text)
        if kind == "redirect":
            url = (
                payload
                if payload.startswith("http")
                else f"https://www.avito.ru{payload}"
            )
            continue
        return kind, payload
    return "redirect_loop", None
