"""avito-mcp-shared — общие утилиты для серверов avito-mcp.

Фаза 1: единая точка для ролей серверов (``ServerRole``) и неймспейсов
композиции. Растёт по мере выноса общих черт (фазы 2–4).
"""

from .roles import ROLE_NAMESPACES, ServerRole

__all__ = ["ROLE_NAMESPACES", "ServerRole"]
__version__ = "0.1.0"