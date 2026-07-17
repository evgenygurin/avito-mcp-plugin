"""Клиент официального API Avito (api.avito.ru).

OAuth2 ``client_credentials``. Работает только со своими объявлениями/рекламой
(см. skills/avito-official-api). Секреты берутся из окружения и НЕ логируются.
HTTP-клиент инъектируется — это делает класс тестируемым без реальной сети.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic import BaseModel

TOKEN_PATH = "/token/"


class AvitoOfficialConfig(BaseModel):
    """Конфигурация доступа к официальному API."""

    client_id: str
    client_secret: str
    base_url: str = "https://api.avito.ru"

    @classmethod
    def from_env(cls) -> AvitoOfficialConfig:
        """Собрать конфиг из переменных окружения.

        Raises:
            ValueError: если ``AVITO_CLIENT_ID`` / ``AVITO_CLIENT_SECRET`` не заданы.
        """
        client_id = os.environ.get("AVITO_CLIENT_ID")
        client_secret = os.environ.get("AVITO_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise ValueError(
                "не заданы AVITO_CLIENT_ID / AVITO_CLIENT_SECRET в окружении"
            )
        return cls(client_id=client_id, client_secret=client_secret)


class AvitoOfficialClient:
    """Асинхронный клиент официального API с кэшем токена."""

    def __init__(self, config: AvitoOfficialConfig, http: httpx.AsyncClient) -> None:
        self._config = config
        self._http = http
        self._token: str | None = None

    async def get_token(self) -> str:
        """Получить access-токen (client_credentials), закэшировать."""
        if self._token is not None:
            return self._token
        resp = await self._http.post(
            f"{self._config.base_url}{TOKEN_PATH}",
            data={
                "grant_type": "client_credentials",
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
            },
        )
        resp.raise_for_status()
        token: str = resp.json()["access_token"]
        self._token = token
        return token

    async def call(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Вызвать метод API с Bearer-токеном. Возвращает разобранный JSON."""
        token = await self.get_token()
        url = f"{self._config.base_url}/{path.lstrip('/')}"
        resp = await self._http.request(
            method,
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        """Закрыть нижележащий HTTP-клиент."""
        await self._http.aclose()
