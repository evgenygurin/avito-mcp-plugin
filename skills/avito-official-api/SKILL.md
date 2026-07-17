---
name: avito-official-api
description: Use when working with a user's OWN Avito listings, ads, statistics, or messenger via the official api.avito.ru. Covers OAuth2 client_credentials, scopes, and X-RateLimit headers. NOT for mass-scraping other sellers' listings.
---

# Avito official API (свои объявления)

## Overview

Официальный API `api.avito.ru` легален и стабилен, но работает **только со своими
данными** (объявления, реклама, статистика, мессенджер, Автотека). Массовый сбор
чужих объявлений им невозможен — для этого см. [scraping-avito](../scraping-avito/SKILL.md).

В плагине доступ идёт через MCP-тулзу **`official_api_call`** (сервер `avito`).
Не пиши HTTP-запросы к `api.avito.ru` руками — вызывай тулзу.

## When to Use

- Пользователь управляет **своими** объявлениями/рекламой/кабинетом.
- Нужна статистика, автозагрузка, мессенджер, Автотека по своему аккаунту.

**Не используй** для сбора чужих объявлений — API это не даёт.

## Quick Reference

| Аспект | Значение |
|---|---|
| Авторизация | OAuth2, `grant_type=client_credentials`, `GET /token/` |
| База | `https://api.avito.ru/` |
| Scopes | `items:info`, `items:apply_vas`, `messenger:read/write`, `autoteka:*`, … |
| Лимиты | заголовки `X-RateLimit-Limit` / `X-RateLimit-Remaining` |
| Реклама | отдельная модель «баллов» (восстановление пн 00:00 UTC) |

Client ID и secret выдаются бесплатно в кабинете; есть песочница. Полный список
scopes и endpoints — `docs/avito-scraping.md` § Официальный API.

## Как вызвать

Через тулзу `official_api_call` (MCP-сервер `avito`):

- `method` — HTTP-метод (`GET`/`POST`);
- `path` — путь метода API (напр. `core/v1/items`, `core/v1/accounts/self`);
- `params` — query-параметры (опц.).

Секреты тулза читает из окружения сама:

```bash
export AVITO_CLIENT_ID=...
export AVITO_CLIENT_SECRET=...
```

Тулза выполняет OAuth2 `client_credentials`, кэширует токен и добавляет
`Authorization: Bearer`. Если переменные не заданы — вернёт понятную ошибку
(`ToolError`), не роняя сессию. Секреты не логируются.

Пример: получить свои объявления → `official_api_call(method="GET", path="core/v1/items")`.

## Common Mistakes

- Пытаться собрать чужие объявления официальным API (невозможно).
- Хардкодить client_secret в коде/репозитории.
- Игнорировать `X-RateLimit-Remaining` → блок метода.

## Related

- `docs/avito-scraping.md` § Официальный API — полный список scopes, endpoints,
  модель баллов рекламного API, песочница
- [scraping-avito](../scraping-avito/SKILL.md) — для чужих публичных данных
- [using-avito-mcp](../using-avito-mcp/SKILL.md) — вызов через тулзу `official_api_call`
