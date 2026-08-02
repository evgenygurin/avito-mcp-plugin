"""FastMCP-сервер avito-mcp-server (gateway-композиция).

Компонует MCP-тулзы: 3 тулзы поиска/чтения/диагностики из scraper-движка
(stateless) + scan_new_listings (обход scraper → персистент в db) + делегированные
из db тулзы (get_price_history, export_listings) + делегированная из notify тулза
уведомления и раздачу ``skills/`` по MCP. См. docs/mcp-server.md.
"""

from __future__ import annotations

from fastmcp import FastMCP

from avito_mcp_scraper.logging_setup import setup_logging as setup_scraper_logging
from avito_mcp_scraper.tools import diagnostics, listings, search
from avito_mcp_db.tools import exporting as db_exporting
from avito_mcp_db.tools.monitoring import register_history

# Тудза уведомлений приходит из notify (прокси импортом): gateway
# не знает про каналы/конфиг уведомлений — только композирует.
from avito_mcp_notify import tools as notify_tools

from .skills_provider import register_skills
from .tools import monitoring

# До регистрации тулз: иначе диагностика самой сборки (список прокси из
# кабинета, подъём кук из кэша) осталась бы невидимой. Каждый вызов тулзы —
# новый процесс, поэтому настройка на импорте модуля, а не только в main().
# Настраиваем и логгер движка (avito_mcp_scraper), и gateway-логгер: иначе
# логи парсинга пропадали бы под чужим root.
setup_scraper_logging(loggers=["avito_mcp_server", "avito_mcp_scraper"])

mcp = FastMCP("avito-mcp-server")


def register_all(gw: FastMCP) -> None:
    """Зарегистрировать все тулзы gateway на переданном инстансе FastMCP."""
    # Парсинг-тулзы (stateless) из scraper-движка.
    search.register(gw)
    listings.register(gw)
    diagnostics.register(gw)

    # Мониторинг: обход scraper + персистент в db (dedup/история цены).
    monitoring.register(gw)
    # Внешний контракт истории цены и экспорт делегируются в db.
    register_history(gw)
    db_exporting.register(gw)

    # Уведомления делегируются в notify (Фаза 4): gateway чистый композитор.
    notify_tools.register(gw)

    # Раздача skills/ по MCP (skill://<name>/…) — любому MCP-клиенту.
    # graceful: если каталог skills/ не найден, сервер работает без раздачи.
    register_skills(gw)


# Регистрируем на инстансе при импорте (как в монолите): тесты и ``python -m``
# подхватывают готовый сервер без отдельного шага сборки.
register_all(mcp)


def main() -> None:
    """Точка входа: запуск по stdio (дефолтный транспорт)."""
    mcp.run()


if __name__ == "__main__":
    main()
