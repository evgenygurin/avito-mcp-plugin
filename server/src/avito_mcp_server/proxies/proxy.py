"""Типы прокси и ротация выходного IP."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from ..storage.base import ProxyCooldownStore

log = logging.getLogger(__name__)


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
            # Параметр клеим через URL, а не строкой: change_url может уже
            # иметь или не иметь query. trust_env=False — служебный запрос к
            # кабинету не должен уходить через HTTPS_PROXY из шелла (то есть
            # через сам ротируемый прокси). Построение URL — внутри try:
            # httpx.InvalidURL (опечатка/битый порт в change_url) не наследует
            # HTTPError (проверено в httpx 0.28.1) и иначе пробросился бы сырым
            # исключением вместо контрактного False.
            url = httpx.URL(self.change_url).copy_merge_params({"format": "json"})
            resp = httpx.get(
                url,
                timeout=self.timeout,
                trust_env=False,
                follow_redirects=True,
            )
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            log.warning("ротация IP не удалась: %s", exc)
            return False
        if resp.status_code != 200:
            log.warning("ротация IP вернула статус %s", resp.status_code)
            return False
        return True


class ProxyPool(Proxy):
    """Несколько прокси-адресов с перебором при блокировках.

    Пул выходных IP смешанный: часть адресов прожжена Qrator, часть чиста. При
    блокировке ``rotate()`` переключается на следующий адрес; когда круг замкнулся,
    возвращает ``False`` — перебирать больше нечего, нужен свежий пул.
    """

    def __init__(
        self,
        urls: list[str],
        cooldown_store: ProxyCooldownStore | None = None,
        cooldown: float = 1800.0,
    ) -> None:
        if not urls:
            raise ValueError("пул прокси пуст")
        self.urls = urls
        self.cooldown_store = cooldown_store
        self.cooldown = cooldown
        self._index = 0
        self._rotations = 0
        self._skip_cooled_down()

    def _blocked(self) -> set[str]:
        if self.cooldown_store is None:
            return set()
        try:
            blocked = self.cooldown_store.blocked_proxies(self.cooldown)
        except Exception as exc:  # noqa: BLE001 — память об IP не критична
            log.warning("не удалось прочитать cooldown прокси: %s", exc)
            return set()
        return set(blocked)

    def _skip_cooled_down(self) -> None:
        """Встать на адрес вне cooldown; если остывают все — работаем как есть."""
        blocked = self._blocked()
        if not blocked:
            return
        for offset in range(len(self.urls)):
            candidate = (self._index + offset) % len(self.urls)
            if self.urls[candidate] not in blocked:
                self._index = candidate
                return

    def httpx_proxy(self) -> str | None:
        return f"http://{self.urls[self._index]}"

    def rotate(self) -> bool:
        # rotate() вызывается именно после блокировки — помечаем текущий адрес,
        # чтобы следующий запуск не тратил на него попытки.
        if self.cooldown_store is not None:
            try:
                self.cooldown_store.mark_proxy_blocked(self.urls[self._index])
            except Exception as exc:  # noqa: BLE001
                log.warning("не удалось запомнить блокировку прокси: %s", exc)
        self._index = (self._index + 1) % len(self.urls)
        self._rotations += 1
        self._skip_cooled_down()
        return self._rotations % len(self.urls) != 0
