"""Провайдер кук через сторонний сервис spfa.ru.

Сервис отдаёт валидные Qrator-куки (проходит JS-challenge) под переданный ключ.
Проверено живьём: `POST /api/cookies/` → `results.{id,cookies}`; при блокировке —
`POST /api/unblock/`, иначе покупка новых.
"""

from __future__ import annotations

import httpx

from .base import CookiesProvider

API_URL = "https://spfa.ru/api"


class SpfaCookiesProvider(CookiesProvider):
    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.last_id: str | None = None
        self.last_cookies: dict | None = None
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def get(self) -> dict:
        if self.last_cookies:
            return self.last_cookies
        return self._buy()

    def handle_block(self) -> None:
        if self.last_id:
            try:
                resp = httpx.post(
                    f"{API_URL}/unblock/",
                    json={"id": self.last_id, "api_key": self.api_key},
                    headers=self._headers,
                    timeout=self.timeout,
                )
                if resp.status_code in (200, 202):
                    return
            except httpx.HTTPError:
                pass
        # Разблокировать не удалось — покупаем свежие куки.
        self.last_id = None
        self.last_cookies = None
        self._buy()

    def _buy(self) -> dict:
        resp = httpx.post(
            f"{API_URL}/cookies/",
            json={"api_key": self.api_key},
            headers=self._headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        results = resp.json().get("results", {})
        item_id = results.get("id")
        cookies = results.get("cookies")
        if not item_id or not cookies:
            raise RuntimeError("spfa вернул неполные данные cookies")
        self.last_id = item_id
        self.last_cookies = cookies
        return cookies
