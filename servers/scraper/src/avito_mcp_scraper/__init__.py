"""avito-mcp-scraper — сервер: парсинг публичного каталога Avito (stateless).

Фаза 2: движок парсинга (http/cookies/proxies/parser/filters + 3 тулзы
search/get_listing/get_health) перенесён сюда из gateway. Scraper не знает
ни про БД, ни про уведомления и экспорт — их композирует gateway.
"""

from .server import mcp

__all__ = ["mcp"]
__version__ = "0.3.0"
