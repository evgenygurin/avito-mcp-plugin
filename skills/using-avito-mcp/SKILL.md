---
name: using-avito-mcp
description: Use when the user needs Avito data — listings, prices, item characteristics, or actions on their OWN listings — or when you are about to hand-write HTTP requests or ad-hoc scraping scripts for Avito. Points to the right avito MCP tool or sub-skill.
---

# Using the Avito MCP tools

## Overview

Плагин `avito-mcp-plugin` несёт детерминированную логику в MCP-сервере `avito`.
Когда задача касается данных Avito — вызывай тулзы сервера, а не пиши HTTP-запросы
или парсинг руками. Код тулз не попадает в контекст; ты получаешь structured output.

## When to Use

- Нужны действия над **своими** объявлениями (официальный API) → [avito-official-api](../avito-official-api/SKILL.md).
- Пользователь просит найти/сравнить объявления, цены, характеристики (парсинг —
  в разработке; сперва [scraping-avito](../scraping-avito/SKILL.md) и [avito-legal-guardrails](../avito-legal-guardrails/SKILL.md)).

**Не используй**, когда данные не с Avito или задача чисто локальная.

## Tools

| Тулза | Назначение | Статус |
|---|---|---|
| `ping(message)` | Диагностика связи с сервером | ✅ готово |
| `official_api_call(method, path, params)` | Официальный API (свои объявления) | ✅ готово |
| `search_listings(query, region, filters)` | Поиск объявлений | 🔜 план |
| `get_listing(id_or_url)` | Детали объявления | 🔜 план |
| `check_proxy_health()` | Диагностика прокси-пула | 🔜 план |

Актуальный список и параметры — `docs/mcp-server.md`.

## Implementation

- **Свои объявления / реклама / статистика** → `official_api_call`
  (детали и env-секреты — [avito-official-api](../avito-official-api/SKILL.md)).
- **Чужие публичные объявления** (поиск, детали) → парсинг-тулзы в разработке.
  Пока их нет — не подменяй их ручным `curl_cffi`/Playwright; объясни, что тулза
  ещё не реализована. Процедура и ограничения — [scraping-avito](../scraping-avito/SKILL.md).
- **Блокировки в ответе** (`429`, `firewallCaptcha`) → не решай капчу, делегируй
  логику ретрая с ротацией слою парсинга; см. [scraping-avito](../scraping-avito/SKILL.md).

## Common Mistakes

- Писать `curl_cffi`/Playwright руками вместо вызова тулзы.
- Собирать телефоны/имена продавцов — сначала [avito-legal-guardrails](../avito-legal-guardrails/SKILL.md).
- Игнорировать `429`/`firewallCaptcha` в ответе тулзы вместо ретрая с ротацией.

## Related

- [scraping-avito](../scraping-avito/SKILL.md) — процедура обхода антибота
- [avito-legal-guardrails](../avito-legal-guardrails/SKILL.md) — правовые ограничения РФ
- [avito-official-api](../avito-official-api/SKILL.md) — официальный API для своих объявлений
