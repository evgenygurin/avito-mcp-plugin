"""Доменные тулзы MCP-сервера (заготовка).

Каждый модуль здесь регистрирует свои тулзы на общем инстансе FastMCP через
функцию ``register(mcp)``. Планируемые модули:

- ``listings``     — поиск и детали публичных объявлений (гибридная схема,
                     см. skills/scraping-avito и docs/avito-scraping.md);
- ``official_api`` — официальный API api.avito.ru для своих объявлений
                     (см. skills/avito-official-api);
- ``proxy``        — диагностика и ротация прокси-пула.

Правовые ограничения на сбор — см. skills/avito-legal-guardrails и
docs/avito-legal.md.
"""
