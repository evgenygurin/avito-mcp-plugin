"""Доменные тулзы MCP-сервера scraper.

Каждый модуль регистрирует свои тулзы на общем инстансе FastMCP через
``register(mcp)`` — те же функции можно регистрировать на gateway-композиции.
"""

from __future__ import annotations
