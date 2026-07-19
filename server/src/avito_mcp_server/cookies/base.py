"""Интерфейс провайдера кук."""

from __future__ import annotations

from abc import ABC, abstractmethod


class CookiesProvider(ABC):
    """Отдаёт куки для запросов к Avito и умеет реагировать на блокировку."""

    @abstractmethod
    def get(self) -> dict:
        """Вернуть текущие куки (при необходимости — получить/купить)."""

    def update(self, response: object) -> None:
        """Обновить состояние по ответу запроса. По умолчанию — ничего."""

    @abstractmethod
    def handle_block(self) -> None:
        """Что делать, если куки заблокированы (разблокировка/обновление)."""
