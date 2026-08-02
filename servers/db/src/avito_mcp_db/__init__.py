"""avito-mcp-db — сервер: хранилище avito-mcp (PostgreSQL).

Фаза 1: скелет (FastMCP-инстанс + `status`). Storage-слой переезжает сюда
из gateway в фазе 3.
"""

from .server import mcp

__all__ = ["mcp"]
__version__ = "0.1.0"
