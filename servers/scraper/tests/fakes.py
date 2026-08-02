"""Тестовый двойник ``HttpClient`` для scraper-тулз (без сети и ПДн).

Scraper stateless — хранилища здесь нет, нужен только двойник HTTP-клиента для
тулз поиска/чтения/диагностики. Gateway-тесты (мониторинг/экспорт/уведомления)
используют свой ``fakes.FakeStorage`` в ``servers/gateway/tests``.
"""

from __future__ import annotations

from avito_mcp_scraper.proxies.proxy import NoProxy


class FakeHttpClient:
    """Двойник ``HttpClient`` для тулз: контекстный менеджер без сети.

    Настоящий клиент держит открытое TLS-соединение и освобождает его в
    ``close()``, поэтому тулзу используют его через ``with``. Тестовым двойникам
    достаточно унаследоваться отсюда и добавить свой ``get``.
    """

    proxy = NoProxy()

    def __init__(self, budget_scale: int = 1, cooldown_store: object = None) -> None:
        # Тулзы просят бюджет пропорционально числу страниц — двойник обязан
        # принимать тот же аргумент, иначе подмена ловит TypeError. Фаза 2:
        # scraper-stateless — cooldown не используется, но параметр принимается.
        self.budget_scale = budget_scale
        self.cooldown_store = cooldown_store

    def __enter__(self) -> "FakeHttpClient":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def close(self) -> None:
        pass
