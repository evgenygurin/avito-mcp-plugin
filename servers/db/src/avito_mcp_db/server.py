"""FastMCP-инстанс db-сервера (Фаза 3): единственный stateful-сервер.

db владеет хранилищем (Supabase/Postgres): ``record_scan_result`` (персистент
результата сканирования: dedup/seen/история цены), ``get_price_history`` и
``export_listings``. Плюс системный ``status`` (роль и готовность).
"""

from __future__ import annotations

from fastmcp import FastMCP

from avito_mcp_shared.roles import ServerRole

from .tools import exporting, monitoring

mcp = FastMCP("avito-mcp-db")


@mcp.tool
async def status() -> dict[str, str]:
    """Возвращает роль и готовность db-сервера."""
    return {"role": ServerRole.DB.value, "status": "ok"}


def register_all(db: FastMCP) -> None:
    """Зарегистрировать все доменные тулзы db на переданном инстансе."""
    monitoring.register(db)
    exporting.register(db)


# Регистрируем на инстансе при импорте: тесты и ``python -m`` подхватывают
# готовый сервер без отдельного шага сборки (как в gateway/scraper).
register_all(mcp)


def main() -> None:
    """Точка входа: запуск по stdio (дефолтный транспорт)."""
    mcp.run()


if __name__ == "__main__":
    main()
