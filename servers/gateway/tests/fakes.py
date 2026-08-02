"""Тестовые двойники внешних зависимостей gateway.

Фаза 3: gateway не знает про хранилище (оно ушло в db), поэтому хранение в
наших тестах не фейкается — db-функции мокнутся точечно (``persist_scan``).
Здесь остаётся только двойник HTTP-клиента для обхода каталога (движок
scraper-шага оркестрации).
"""

from __future__ import annotations

from avito_mcp_scraper.proxies.proxy import NoProxy


class FakeHttpClient:
    """Двойник ``HttpClient`` для тулз: контекстный менеджер без сети.

    Настоящий клиент держит открытое TLS-соединение и освобождает его в
    ``close()``, поэтому тулзы используют его через ``with``. Тестовым двойникам
    достаточно унаследоваться отсюда и добавить свой ``get``.
    """

    proxy = NoProxy()

    def __init__(self, budget_scale: int = 1, cooldown_store: object = None) -> None:
        # Тулзы просят бюджет пропорционально числу страниц — двойник обязан
        # принимать те же аргументы.
        self.budget_scale = budget_scale
        self.cooldown_store = cooldown_store

    def __enter__(self) -> "FakeHttpClient":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def close(self) -> None:
        pass
