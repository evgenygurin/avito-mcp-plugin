"""Провайдер кук через Playwright (браузерная добыча сессии Avito).

Опциональная тяжёлая зависимость (``playwright`` + браузерный движок).
Не устанавливается по умолчанию — ``pip install avito-mcp-server[playwright]``.

Браузер открывает целевую страницу каталога, даёт антиботу выставить куки и
отдаёт их ЦЕЛИКОМ: ``ft`` — признак пройденного challenge, но одной её мало,
запросу нужна вся сессия. Если браузер ходит не через тот же прокси, что и
HTTP-клиент, куки окажутся привязаны к чужому IP и не сработают.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from .base import CookiesProvider

log = logging.getLogger(__name__)

# Ходим на каталог, а не на главную: challenge выдаётся на целевой странице.
_DEFAULT_URL = "https://www.avito.ru/nizhniy_novgorod/kvartiry"

try:  # pragma: no cover — зависит от установки
    from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment]


def _proxy_settings(proxy: str | None) -> dict[str, str] | None:
    """Разложить ``user:pass@host:port`` в формат, который ждёт Playwright."""
    if not proxy:
        return None
    url = proxy if "://" in proxy else f"http://{proxy}"
    parts = urlsplit(url)
    settings = {"server": f"{parts.scheme}://{parts.hostname}"}
    if parts.port:
        settings["server"] += f":{parts.port}"
    if parts.username:
        settings["username"] = parts.username
    if parts.password:
        settings["password"] = parts.password
    return settings


class PlaywrightCookiesProvider(CookiesProvider):
    def __init__(
        self,
        headless: bool = True,
        timeout: float = 30.0,
        wait_until: str = "domcontentloaded",
        url: str = _DEFAULT_URL,
        proxy: str | None = None,
        user_agent: str | None = None,
        locale: str = "ru-RU",
        timezone_id: str = "Europe/Moscow",
    ) -> None:
        if sync_playwright is None:
            raise ImportError(
                "playwright не установлен. Установите: "
                "pip install avito-mcp-server[playwright] && playwright install chromium"
            )
        self._headless = headless
        self._timeout = timeout
        self._wait_until = wait_until
        self._url = url
        self._proxy = proxy
        self._user_agent = user_agent
        self._locale = locale
        self._timezone_id = timezone_id
        self._cookies: dict | None = None

    def get(self) -> dict:
        if self._cookies:
            return self._cookies
        return self._harvest()

    def handle_block(self) -> None:
        self._cookies = None
        self._harvest()

    def _harvest(self) -> dict:
        launch_kwargs: dict[str, Any] = {"headless": self._headless}
        proxy = _proxy_settings(self._proxy)
        if proxy:
            launch_kwargs["proxy"] = proxy

        context_kwargs: dict[str, Any] = {
            "locale": self._locale,
            "timezone_id": self._timezone_id,
            "viewport": {"width": 1920, "height": 1080},
        }
        if self._user_agent:
            context_kwargs["user_agent"] = self._user_agent

        with sync_playwright() as pw:
            browser = pw.chromium.launch(**launch_kwargs)
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            try:
                page.goto(
                    self._url,
                    wait_until=self._wait_until,
                    timeout=self._timeout * 1000,
                )
                # Challenge ставит куки асинхронно уже после загрузки DOM.
                page.wait_for_timeout(3000)
                raw = context.cookies(self._url)
                cookies = {
                    c["name"]: c["value"]
                    for c in raw
                    if c.get("name") and c.get("value")
                }
            finally:
                context.close()
                browser.close()

        if not cookies:
            raise RuntimeError("playwright не получил ни одной куки Avito")
        if "ft" not in cookies:
            # Не ошибка: сессия может работать и без ft, но это признак того,
            # что challenge не отдавался — полезно видеть в логе.
            log.info("куки получены (%s шт.), но ft отсутствует", len(cookies))
        self._cookies = cookies
        return cookies
