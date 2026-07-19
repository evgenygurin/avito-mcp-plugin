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

Все семь тулз реализованы. Сетевую часть не проверить без чистого RU-прокси:
с домашнего IP Avito отдаёт 403/429 после 2–3 запросов.

| Тулза | Назначение | Статус |
|---|---|---|
| `search_listings(url, pages, include_keywords, exclude_keywords, seller_blacklist, price_min/max, geo, max_age)` | Поиск каталога с фильтрами; `pages` обходит страницы по `pager.next` | ✅ готово |
| `get_listing(id_or_url, with_views)` | Детали объявления | ✅ готово |
| `scan_new_listings(..., pages)` | Dedup + отслеживание цены (Postgres); возвращает только новое/подешевевшее | ✅ готово |
| `check_proxy_health()` | Диагностика: проверяет каждый адрес пула, возвращает `probes` | ✅ готово |
| `send_notification(channel, message, targets?)` | Уведомление в Telegram/VK | ✅ готово |
| `export_listings(items, fmt, path?)` | Выгрузка в xlsx/json/csv | ✅ готово |
| `get_price_history(listing_id)` | История цены из Postgres | ✅ готово |

Актуальный список и параметры — `docs/mcp-server.md` в репозитории плагина;
в рантайме сверяйся со схемой тулзы, которую отдаёт сам MCP-сервер.

## Implementation

- **Поиск и детали** (чужие публичные объявления) → `search_listings` / `get_listing`.
  Фильтры (`include_keywords`, `seller_blacklist`, `price_min/max`, `geo`, `max_age`)
  — параметры тулзы, не отдельные вызовы. Просмотры доступны только
  у `get_listing` через `with_views`.
- **Мониторинг** (новые/подешевевшие лоты) → `scan_new_listings` в связке с внешним
  планировщиком (агент/cron/`/schedule`); история цены — `get_price_history`. Оба
  опираются на Postgres проекта Supabase (`AVITO_SUPABASE_DSN`).
- **Сайд-эффекты** → `export_listings` (xlsx/json/csv), `send_notification`
  (Telegram/VK).
- Не подменяй тулзы ручным `curl_cffi`/Playwright: движок реализован, ручной скрипт
  обойдёт кэш кук, cooldown прокси и дедуп. Механика — [scraping-avito](../scraping-avito/SKILL.md).
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
