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
    def handle_block(self) -> bool:
        """Отреагировать на блокировку кук: разблокировать или обновить.

        Returns:
            Изменилось ли состояние. ``False`` означает «лечить нечем» — тогда
            вызывающему нет смысла повторять запрос с теми же куками, и он
            сразу переходит к смене выходного адреса (см. ``HttpClient``).
        """
