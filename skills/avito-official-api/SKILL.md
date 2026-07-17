---
name: avito-official-api
description: Use when working with a user's OWN Avito listings, ads, statistics, or messenger via the official api.avito.ru. Covers OAuth2 client_credentials, scopes, and X-RateLimit headers. NOT for mass-scraping other sellers' listings.
---

# Avito official API (свои объявления)

> **СТАТУС: черновик-заготовка (skeleton).** Финализировать по
> `superpowers:writing-skills`. Детали — в `docs/avito-scraping.md` (§ Официальный API).

## Overview

Официальный API `api.avito.ru` легален и стабилен, но работает **только со своими
данными** (объявления, реклама, статистика, мессенджер, Автотека). Массовый сбор
чужих объявлений им невозможен — для этого см. [[scraping-avito]].

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

Client ID и secret выдаются бесплатно в кабинете; есть песочница.

## Implementation

<!-- TODO: тулза official_api_call в server/. Хранение client_id/secret через env
     (${CLAUDE_PLUGIN_DATA} / переменные окружения), обновление токена,
     обработка X-RateLimit-*. Секреты НЕ логировать, НЕ хардкодить. -->

## Common Mistakes

- Пытаться собрать чужие объявления официальным API (невозможно).
- Хардкодить client_secret в коде/репозитории.
- Игнорировать `X-RateLimit-Remaining` → блок метода.

## Related

- [[scraping-avito]] — для чужих публичных данных
- [[using-avito-mcp]] — вызов через тулзу `official_api_call`
