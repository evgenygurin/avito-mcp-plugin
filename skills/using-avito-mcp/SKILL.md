---
name: using-avito-mcp
description: Use when the user needs Avito data — listings, prices, seller info, item details, or official-API actions. Routes work to the avito MCP server tools instead of hand-written HTTP requests or ad-hoc scraping scripts.
---

# Using the Avito MCP tools

> **СТАТУС: черновик-заготовка (skeleton).** Финальный текст пишется по
> `superpowers:writing-skills` (RED→GREEN→REFACTOR с прогонами на субагентах)
> после реализации MCP-тулз. Сигнатуры тулз ниже — плановые, не финальные.

## Overview

Плагин `avito-mcp-plugin` несёт детерминированную логику в MCP-сервере `avito`.
Когда задача касается данных Avito — вызывай тулзы сервера, а не пиши HTTP-запросы
или парсинг руками. Код тулз не попадает в контекст; ты получаешь structured output.

## When to Use

- Пользователь просит найти/сравнить объявления, цены, характеристики на Avito.
- Нужны детали конкретного объявления по URL или id.
- Нужны действия над **своими** объявлениями (официальный API) — см.
  [[avito-official-api]].
- Идёт массовый сбор публичных данных → сперва прочитай [[scraping-avito]]
  (антибот) и [[avito-legal-guardrails]] (право).

**Не используй**, когда данные не с Avito или задача чисто локальная.

## Quick Reference (плановые тулзы)

| Тулза | Назначение | Статус |
|---|---|---|
| `search_listings(query, region, filters)` | Поиск объявлений | TODO |
| `get_listing(id_or_url)` | Детали объявления | TODO |
| `official_api_call(method, params)` | Официальный API (свои объявления) | TODO |
| `check_proxy_health()` | Диагностика прокси-пула | TODO |

Точный список и параметры — после реализации сервера; см. `docs/mcp-server.md`.

## Implementation

<!-- TODO: заполнить после реализации тулз в server/src/avito_mcp_server/tools/.
     Для каждой тулзы: когда вызывать, какие параметры, что возвращает,
     как обрабатывать блокировки/капчу (делегировать в scraping-avito). -->

## Common Mistakes

- Писать `curl_cffi`/Playwright руками вместо вызова тулзы.
- Собирать телефоны/имена продавцов — сначала [[avito-legal-guardrails]].
- Игнорировать `429`/`firewallCaptcha` в ответе тулзы вместо ретрая с ротацией.

## Related

- [[scraping-avito]] — процедура обхода антибота
- [[avito-legal-guardrails]] — правовые ограничения РФ
- [[avito-official-api]] — официальный API для своих объявлений
