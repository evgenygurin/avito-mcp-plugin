"""avito-mcp-notify — сервер: уведомления avito-mcp (Telegram/VK).

Фаза 1: скелет (FastMCP-инстанс + `status`). Уведомления переезжают сюда
из gateway в фазе 4.
"""

from .server import mcp

__all__ = ["mcp"]
__version__ = "0.1.0"
