---
name: scraping-avito
description: Use when scraping public Avito listings and hitting Qrator/CURATOR anti-bot — 403 "проблема с IP", 429 rate limits, firewall captcha (hCaptcha/GeeTest), or blank JS pages. Covers RU proxy hygiene and the browser→cookies→HTTP hybrid.
---

# Scraping Avito (обход антибота)

> **СТАТУС: черновик-заготовка (skeleton).** Финализировать по
> `superpowers:writing-skills`. Технические детали — в `docs/avito-scraping.md`.
> Перед сбором данных ОБЯЗАТЕЛЬНО пройти [[avito-legal-guardrails]].

## Overview

Avito защищён Qrator (в РФ — CURATOR) Antibot: JS-fingerprinting, JA3/JA4 TLS,
поведенческий анализ, фаервол-капча. «Голый» HTTP получает `403`. Рабочая
схема — **гибрид**: реальный браузер генерирует куки (`qrator_jsid`) →
куки+прокси передаются в быстрый async HTTP-клиент к внутреннему JSON-API.

## When to Use

- Ответ `403` «Доступ ограничен: проблема с IP», `429`, пустая JS-страница.
- Перехвачен `/web/5/firewallCaptcha/get` (hCaptcha Enterprise / GeeTest).
- Нужен массовый сбор публичных объявлений (сотни-тысячи/день).

**Не используй** для своих объявлений — там официальный API ([[avito-official-api]]).

## Core Pattern (гибридная схема)

```text
browser (Playwright/patchright, headful/Xvfb, RU-прокси)
      → проходит Qrator JS-challenge → куки (qrator_jsid, …)
      → Redis (TTL ~10–12ч)
async workers (curl_cffi impersonate="chrome") + sticky-прокси
      → m.avito.ru/api/* или JSON в HTML (data-marker)
```

## Quick Reference

| Симптом | Причина | Действие |
|---|---|---|
| `403` «проблема с IP» | датацентр/иностранный IP | только RU-прокси (мобильные > резидентные) |
| Пустая страница | Qrator JS-challenge | браузер для кук, не «голый» HTTP |
| `firewallCaptcha` | hCaptcha/GeeTest | НЕ решать в лоб — ротация чистых IP |
| Внезапная капча на 30–50 запросе | поведенческий анализ | паузы 2–6с, длинная пауза каждые ~20 |
| `429` | rate limit | token-bucket на прокси, снизить темп |

## Implementation

<!-- TODO: рабочий код добычи кук + async-запросов в
     server/src/avito_mcp_server/tools/. Здесь — только процедурные решения:
     когда включать браузер, как ротировать прокси, пороги карантина. -->

## Common Mistakes

- Датацентр-прокси или иностранный IP → мгновенный бан.
- Ротация IP на каждый запрос → антифрод (нужны sticky-сессии).
- Headless-Chromium без Xvfb → капча/заглушка.
- Решать капчу «в лоб» → смещает правовую квалификацию к ст. 272 УК.

## Related

- `docs/avito-scraping.md` — полная техдока (инструменты, прокси, БД)
- [[avito-legal-guardrails]] — что собирать нельзя
- [[using-avito-mcp]] — вызов через тулзы
