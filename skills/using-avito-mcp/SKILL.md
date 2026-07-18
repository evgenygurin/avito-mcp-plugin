---
name: using-avito-mcp
description: Use when the user needs Avito data — search listings, prices, item characteristics, monitoring new/cheaper items, price history, export or notifications — or when you are about to hand-write HTTP requests or ad-hoc scraping scripts for Avito. Points to the right avito MCP tool or sub-skill.
---

# Using the Avito MCP tools

## Overview

Плагин `avito-mcp-plugin` несёт детерминированную логику в MCP-сервере `avito`.
Когда задача касается данных Avito — вызывай тулзы сервера, а не пиши HTTP-запросы
или парсинг руками. Код тулз не попадает в контекст; ты получаешь structured output.

Сервер несёт собственный движок парсинга (провайдер кук → rotate-until-clean →
curl_cffi + follow SSR-редиректа → извлечение `loaderData.data.catalog`). Механика
движка — [scraping-avito](../scraping-avito/SKILL.md).

## When to Use

- Пользователь просит найти/сравнить объявления, цены, характеристики, следить за
  новыми/подешевевшими лотами, выгрузить или разослать результат.
- Ты собрался писать `curl_cffi`/Playwright или ad-hoc парсинг Avito руками.

**Не используй**, когда данные не с Avito или задача чисто локальная.

## Tools

Все семь тулз — целевой фичесет полнофункционального парсера каталога Avito.
Статус — «план»: код движка ещё не написан.

| Тулза | Назначение | Статус |
|---|---|---|
| `search_listings(url_or_query, region, pages, include_keywords, exclude_keywords, seller_blacklist, price_min/max, geo, max_age, parse_views)` | Разовый поиск каталога с фильтрами | 🔜 план |
| `get_listing(id_or_url, with_views)` | Детали объявления | 🔜 план |
| `scan_new_listings(...)` | Dedup + отслеживание цены (мониторинг-примитив, sqlite); возвращает только новое/подешевевшее | 🔜 план |
| `check_proxy_health()` | Диагностика прокси-пула и ротации | 🔜 план |
| `send_notification(channel, message, targets?)` | Уведомление в Telegram/VK | 🔜 план |
| `export_listings(items, format, path?)` | Выгрузка в xlsx/json/csv | 🔜 план |
| `get_price_history(listing_id)` | История цены из sqlite | 🔜 план |

Актуальный список и параметры — `docs/mcp-server.md`.

## Implementation

- **Поиск и детали** (чужие публичные объявления) → `search_listings` / `get_listing`.
  Фильтры (`include_keywords`, `seller_blacklist`, `price_min/max`, `geo`, `max_age`)
  и `parse_views` — параметры тулзы, не отдельные вызовы.
- **Мониторинг** (новые/подешевевшие лоты) → `scan_new_listings` в связке с внешним
  планировщиком (агент/cron/`/schedule`); история цены — `get_price_history`. Оба
  опираются на sqlite (`AVITO_DB_PATH`).
- **Сайд-эффекты** → `export_listings` (xlsx/json/csv), `send_notification`
  (Telegram/VK).
- Пока движок не написан — не подменяй тулзы ручным `curl_cffi`/Playwright; объясни,
  что тулза ещё не реализована. Процедура и механика — [scraping-avito](../scraping-avito/SKILL.md).
- **Блокировки** (`429`, `firewallCaptcha`, «проблема с IP») → не решай капчу,
  делегируй ретрай с rotate-until-clean слою движка; см. [scraping-avito](../scraping-avito/SKILL.md).

## Common Mistakes

- Писать `curl_cffi`/Playwright руками вместо вызова тулзы.
- Ждать сбора телефонов продавцов — `parse_phone` намеренно не реализован; телефонов
  нет ни в тулзах, ни в моделях.
- Игнорировать `429`/`firewallCaptcha` в ответе тулзы вместо ретрая с ротацией.
- Гонять `scan_new_listings` фоновым циклом внутри сервера — мониторинг идёт через
  внешний планировщик.

## Related

- [scraping-avito](../scraping-avito/SKILL.md) — механика движка парсинга (spfa-куки,
  rotate-until-clean, SSR-редирект, извлечение JSON)
