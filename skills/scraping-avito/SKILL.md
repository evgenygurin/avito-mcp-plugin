---
name: scraping-avito
description: Use when scraping public Avito listings and hitting Qrator/CURATOR anti-bot — 403 "проблема с IP", 429 rate limits, firewall captcha (hCaptcha/GeeTest), or blank JS pages. Covers RU proxy hygiene and the browser→cookies→HTTP hybrid.
---

# Scraping Avito (обход антибота)

> Перед сбором данных ОБЯЗАТЕЛЬНО пройти [avito-legal-guardrails](../avito-legal-guardrails/SKILL.md).
> Технические детали и источники — в `docs/avito-scraping.md`.

## Overview

Avito защищён Qrator (в РФ — CURATOR) Antibot: JS-fingerprinting, JA3/JA4 TLS,
поведенческий анализ, фаервол-капча. «Голый» HTTP получает `403`. Рабочая
схема — **гибрид**: реальный браузер генерирует куки (`qrator_jsid`) →
куки+прокси передаются в быстрый async HTTP-клиент к внутреннему JSON-API.

## When to Use

- Ответ `403` «Доступ ограничен: проблема с IP», `429`, пустая JS-страница.
- Перехвачен `/web/5/firewallCaptcha/get` (hCaptcha Enterprise / GeeTest).
- Нужен массовый сбор публичных объявлений (сотни-тысячи/день).

**Не используй** для своих объявлений — там официальный API ([avito-official-api](../avito-official-api/SKILL.md)).

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

## Капча — это стоп-сигнал, а не задача

Ключевое правило: **капча = индикатор, что твой трафик уже помечен как ботовый,
а не стена, которую надо пробить.** Решать её решателем (CapSolver/2captcha) —
и правовая (ст. 272 УК — обход средства защиты), и инженерная ошибка: детектор
продолжит триггериться, ты платишь временем (десятки секунд на челлендж рушат
throughput), антибот эскалирует челленджи и банит IP.

Правильная реакция на капчу: **этот IP → в cooldown, снизить общий rate,
устранить причину детекта** (отпечаток + чистый прокси), а не проходить челлендж.

| Соблазн | Что делать вместо |
|---|---|
| «Дедлайн, просто подключу CapSolver» | Почини TLS-отпечаток + чистые RU-прокси; капча уйдёт сама |
| «Капча раз в 3 запроса — надо её решать» | Трафик помечен ботом — снизь rate, sticky-сессии, cooldown |
| «Решить дешевле ($2/1000), чем возиться» | Решение не убирает причину; растут баны и эскалация |

## Implementation (процедурные решения)

- **Когда включать браузер:** только для добычи кук (`qrator_jsid`), headful/Xvfb,
  1 браузер = 1 RU-прокси. Запросы данных — быстрым async-клиентом с этими куками.
- **Отпечаток:** `curl_cffi impersonate="chrome"` (не пиновать версию), полный набор
  заголовков в правильном порядке, `Referer`-chain (заход через каталог), `ru-RU`.
- **Прокси:** только RU, мобильные > резидентные > датацентр; sticky-сессия на поток;
  смена IP+фингерпринта только на ретрае/бане; смена контекста каждые 15–20 запросов.
- **Темп:** паузы 2–6с, длинная пауза 30–60с каждые ~20 объявлений.
- **Пороги карантина:** доля `403`/`429`/капч по прокси растёт → прокси в cooldown,
  снизить общий rate; >20% капч/`403` → сменить стратегию.
- **Приоритет официального API:** где поле доступно через `official_api_call`
  (свои данные) — брать оттуда, парсинг не нужен. См. [avito-official-api](../avito-official-api/SKILL.md).
- Будущие тулзы (`search_listings`, `get_listing`, `check_proxy_health`) и код
  добычи кук + async-запросов — в `server/src/avito_mcp_server/tools/` (в разработке).

## Common Mistakes

- Датацентр-прокси или иностранный IP → мгновенный бан.
- Ротация IP на каждый запрос → антифрод (нужны sticky-сессии).
- Headless-Chromium без Xvfb → капча/заглушка.
- Решать капчу «в лоб» → смещает правовую квалификацию к ст. 272 УК.
- Сплошная выгрузка существенной доли БД → ст. 1334 ГК; парсить инкрементально.

## Related

- `docs/avito-scraping.md` — полная техдока (инструменты, прокси, БД)
- [avito-legal-guardrails](../avito-legal-guardrails/SKILL.md) — что собирать нельзя
- [using-avito-mcp](../using-avito-mcp/SKILL.md) — вызов через тулзы
