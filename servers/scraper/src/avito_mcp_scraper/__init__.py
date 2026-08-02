"""avito-mcp-scraper — сервер: парсинг публичного каталога Avito (stateless).

Фаза 2: движок парсинга (http/cookies/proxies/parser/filters + 3 тулзы
search/system/get/check) перенесён сюда из gateway. Scraper не знает про
storage/notifications/export — gateway композирует и проксирует его.
"""

from .server import mcp

__all__ = ["mcp"]
__version__ = "0.3.0"
