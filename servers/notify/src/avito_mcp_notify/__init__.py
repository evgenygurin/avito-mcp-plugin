"""avito-mcp-notify — сервер уведомлений avito-mcp (Telegram/VK).

Фаза 4: уведомления переехали сюда из gateway (sender + тулза
``send_notification``); gateway проксирует тулзу импортом.
"""

from .server import mcp

__all__ = ["mcp"]
__version__ = "0.5.0"
