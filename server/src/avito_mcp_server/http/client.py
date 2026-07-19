"""HTTP-клиент скрапинга: curl_cffi + rotate-until-clean + follow-редирект.

Пул выходных IP смешанный (часть прожжена Qrator). Клиент ротирует IP на каждый
block-код (401/403/429), пока не попадёт на чистый и не получит 200. Затем
``fetch_catalog`` следует SSR-редиректу на канонический URL категории. Схема
воспроизведена и валидирована живьём.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, cast

from curl_cffi import requests as cffi

from ..cookies.base import CookiesProvider
from ..parser import classify
from ..proxies.proxy import Proxy

# Только алиасы, следующие за свежими версиями браузеров. "edge" исключён:
# curl_cffi резолвит его в edge101 — отпечаток 2022 года, заметный антиботу.
_IMPERSONATE = ("chrome", "safari")
_BLOCK_CODES = (401, 403, 429)

log = logging.getLogger(__name__)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _build_session(proxy_url: str | None) -> Any:
    session: Any = cffi.Session(impersonate=cast(Any, random.choice(_IMPERSONATE)))
    # User-Agent НЕ переопределяем: impersonate уже выставил UA, Sec-Ch-Ua и
    # платформу, согласованные с TLS-отпечатком профиля. Ручной Windows-Chrome
    # UA поверх случайного профиля (включая safari) даёт противоречие, по
    # которому антибот отличает автоматизацию от браузера.
    session.headers.update({"accept-language": "ru-RU,ru;q=0.9"})
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
        backoff_cap: float = 60.0,
    ) -> None:
        self.proxy = proxy
        self.cookies = cookies
        self.max_attempts = max_attempts
        self.wait_after_rotate = wait_after_rotate
        self.timeout = timeout
        self.block_codes = block_codes
        self.backoff_cap = backoff_cap

    def get(self, url: str) -> Any:
        """GET с ротацией IP до чистого. Возвращает 200-ответ или бросает RuntimeError."""
        cookies = self.cookies.get() if self.cookies else None
        blocks = 0
        for attempt in range(1, self.max_attempts + 1):
            log.info("GET %s (попытка %s/%s)", url, attempt, self.max_attempts)
            with _build_session(self.proxy.httpx_proxy()) as session:
                resp = session.get(
                    url, cookies=cookies, timeout=self.timeout, allow_redirects=True
                )
            log.info("ответ %s на попытке %s", resp.status_code, attempt)
            if self.cookies:
                self.cookies.update(resp)
            if resp.status_code in self.block_codes:
                log.warning("блокировка %s — ротирую IP", resp.status_code)
                self.proxy.rotate()
                # Экспоненциальный backoff с потолком: первая блокировка часто
                # случайна, а на десятой частые повторы только злят антибот.
                # После последней попытки не спим — всё равно сдаёмся.
                if attempt < self.max_attempts:
                    delay = min(self.wait_after_rotate * (2**blocks), self.backoff_cap)
                    _sleep(delay)
                blocks += 1
                # Каждые 5 блокировок — принудительно обновить куки (могли протухнуть).
                if blocks % 5 == 0 and self.cookies:
                    self.cookies.handle_block()
                cookies = self.cookies.get() if self.cookies else None
                continue
            return resp
        # Без прокси менять нечего: NoProxy.rotate() — заглушка, все попытки идут
        # с одного IP, поэтому подсказка про AVITO_PROXY здесь ключевая.
        via = "прокси не задан" if self.proxy.httpx_proxy() is None else "через прокси"
        raise RuntimeError(
            f"не удалось получить {url} за {self.max_attempts} попыток "
            f"(блокировки IP, {via}). Нужен чистый RU-прокси: "
            "задайте AVITO_PROXY и AVITO_PROXY_CHANGE_URL"
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
