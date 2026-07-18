"""Доменные тулзы MCP-сервера (заготовка).

Каждый модуль здесь регистрирует свои тулзы на общем инстансе FastMCP через
функцию ``register(mcp)``. Пока пусто — модули парсинг-тулз (search_listings,
get_listing, check_proxy_health, …) добавляются по мере реализации; см.
skills/scraping-avito и docs/avito-scraping.md.

Правовые ограничения на сбор — см. skills/avito-legal-guardrails и
docs/avito-legal.md.
"""
