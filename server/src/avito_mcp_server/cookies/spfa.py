"""Провайдер кук через сторонний сервис spfa.ru.

Сервис отдаёт валидные Qrator-куки (проходит JS-challenge) под переданный ключ.
Проверено живьём: `POST /api/cookies/` → `results.{id,cookies}`; при блокировке —
`POST /api/unblock/`, иначе покупка новых.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from ..timing import timed
from .base import CookiesProvider

API_URL = "https://spfa.ru/api"
# Сервис держит куки рабочими ~12 часов; после этого кэш заведомо мёртв.
CACHE_TTL = 12 * 3600

log = logging.getLogger(__name__)


class SpfaCookiesProvider(CookiesProvider):
    def __init__(
        self,
        api_key: str,
        timeout: float = 15.0,
        cache_path: Path | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.cache_path = cache_path
        self.last_id: str | None = None
        self.last_cookies: dict | None = None
        self._load_cache()
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
                    trust_env=False,
                )
                if resp.status_code in (200, 202):
                    return
            except httpx.HTTPError:
                pass
        # Разблокировать не удалось — покупаем свежие куки.
        self.last_id = None
        self.last_cookies = None
        self._drop_cache()
        self._buy()

    def _buy(self) -> dict:
        # Покупка кук — платный внешний вызов на несколько секунд: в сводке
        # он должен быть отделим от собственно запросов к Avito.
        with timed("cookies.buy", logger=log):
            resp = httpx.post(
                f"{API_URL}/cookies/",
                json={"api_key": self.api_key},
                headers=self._headers,
                timeout=self.timeout,
                trust_env=False,
            )
        resp.raise_for_status()
        results = resp.json().get("results", {})
        item_id = results.get("id")
        cookies = results.get("cookies")
        if not item_id or not cookies:
            raise RuntimeError("spfa вернул неполные данные cookies")
        self.last_id = item_id
        self.last_cookies = cookies
        self._save_cache()
        return cookies

    def _load_cache(self) -> None:
        """Поднять куки, купленные прошлым процессом (каждый вызов тулзы — новый)."""
        if self.cache_path is None or not self.cache_path.exists():
            return
        try:
            data = json.loads(self.cache_path.read_text())
        except (OSError, ValueError):
            return
        if time.time() - float(data.get("ts", 0)) > CACHE_TTL:
            log.info("кэш кук протух — покупаем свежие")
            return
        if data.get("id") and data.get("cookies"):
            self.last_id = str(data["id"])
            self.last_cookies = data["cookies"]
            log.info("куки подняты из кэша (id=%s)", self.last_id)

    def _save_cache(self) -> None:
        if self.cache_path is None:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(
                    {
                        "id": self.last_id,
                        "cookies": self.last_cookies,
                        "ts": time.time(),
                    }
                )
            )
            # Куки — учётные данные: стоят денег и аутентифицируют запросы к
            # Avito. Права по умолчанию (0644) отдали бы их любому пользователю
            # машины. chmod после записи, а не umask — umask глобален для процесса.
            self.cache_path.chmod(0o600)
        except OSError as exc:
            log.warning("не удалось сохранить кэш кук: %s", exc)

    def _drop_cache(self) -> None:
        if self.cache_path is None:
            return
        try:
            self.cache_path.unlink(missing_ok=True)
        except OSError:
            pass
