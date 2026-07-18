"""Типы прокси и ротация выходного IP."""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx


class Proxy(ABC):
    """Прокси для запросов к Avito. `rotate()` меняет выходной IP, если умеет."""

    @abstractmethod
    def httpx_proxy(self) -> str | None:
        """Строка прокси для HTTP-клиента (`http://user:pass@host:port`) или None."""

    @abstractmethod
    def rotate(self) -> bool:
        """Сменить выходной IP. True — успех; False — не поддерживается/не удалось."""


class NoProxy(Proxy):
    def httpx_proxy(self) -> str | None:
        return None

    def rotate(self) -> bool:
        return False


class ServerProxy(Proxy):
    """Статический серверный прокси — без ротации IP."""

    def __init__(self, url: str) -> None:
        self.url = url

    def httpx_proxy(self) -> str | None:
        return f"http://{self.url}"

    def rotate(self) -> bool:
        return False


class MobileProxy(Proxy):
    """Мобильный прокси с ротацией IP через change-IP URL."""

    def __init__(self, url: str, change_url: str, timeout: float = 20.0) -> None:
        self.url = url
        self.change_url = change_url
        self.timeout = timeout

    def httpx_proxy(self) -> str | None:
        return f"http://{self.url}"

    def rotate(self) -> bool:
        try:
            resp = httpx.get(f"{self.change_url}&format=json", timeout=self.timeout)
        except httpx.HTTPError:
            return False
        return resp.status_code == 200
