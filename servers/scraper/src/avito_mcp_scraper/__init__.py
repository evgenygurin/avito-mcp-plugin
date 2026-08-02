"""avito-mcp-scraper — сервер: парсинг публичного каталога Avito.

Фаза 1: скелет (FastMCP-инстанс + `status`). Движок парсинга переезжает сюда
из gateway в фазе 2.
"""

from .server import mcp

__all__ = ["mcp"]
__version__ = "0.1.0"
