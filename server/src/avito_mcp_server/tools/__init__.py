"""Доменные тулзы MCP-сервера (заготовка).

Каждый модуль здесь регистрирует свои тулзы на общем инстансе FastMCP через
функцию ``register(mcp)``. Модули:

- ``official_api`` — официальный API api.avito.ru для своих объявлений
                     (реализован; см. skills/avito-official-api);
- ``listings``     — поиск и детали публичных объявлений (план; гибридная схема,
                     см. skills/scraping-avito и docs/avito-scraping.md);
- ``proxy``        — диагностика и ротация прокси-пула (план).

Правовые ограничения на сбор — см. skills/avito-legal-guardrails и
docs/avito-legal.md.
"""
