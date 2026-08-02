"""avito-mcp-db — сервер: хранилище avito-mcp (PostgreSQL).

Единственный stateful-сервер (Фаза 3): владеет Supabase (``AVITO_SUPABASE_DSN``),
историей цены и экспортом. Тулзы: ``record_scan_result``, ``get_price_history``,
``export_listings`` + системный ``status``.
"""

from .server import mcp

__all__ = ["mcp"]
__version__ = "0.4.0"