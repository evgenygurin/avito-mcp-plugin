---
name: scraping-avito
description: Use when Avito scraping BREAKS or when building/debugging the parsing engine itself — 403 «проблема с IP», 429 rate limits, firewallCaptcha, a blank JS page with no `catalog`, cookies expiring, IP rotation not helping, or when changing the cookie provider (spfa/own/playwright), rotate-until-clean, SSR redirect following, or loaderData extraction. For routine listing searches use the avito MCP tools instead.
---

# Scraping Avito (движок парсинга)

> How-to движка. Полная техдока (инструменты, прокси, БД) — в `docs/avito-scraping.md` (в репозитории плагина).
> Движок валидирован живьём 2026-07-18 (полный фичесет парсинга Avito + улучшение rotate-until-clean).

## Overview

Avito защищён Qrator (в РФ — CURATOR) Antibot: JS-fingerprinting, JA3/JA4 TLS,
поведенческий анализ, фаервол-капча. «Голый» HTTP получает `403`. Рабочая схема —
**гибрид**: провайдер кук отдаёт валидные Avito-куки → быстрый HTTP-клиент
(`curl_cffi` с `impersonate`) с этими куками и чистым RU-прокси тянет каталог,
следует за SSR-редиректом на канонический URL категории и достаёт встроенный JSON.

## When to Use

- Ответ `403` «Доступ ограничен: проблема с IP», `429` rate limit, пустая
  JS-страница без данных.
- Пишешь/чинишь движок парсинга: провайдер кук, ротацию прокси, извлечение JSON.
- Нужен rotate-until-clean (пул IP смешанный, одной ротации мало).
- Каталог отвечает SSR-редиректом на канонический URL — надо его пройти.
- Надо вытащить `loaderData.data.catalog.items` из HTML.

## Движок (pipeline)

```text
CookiesProvider (spfa дефолт | own | playwright)
      → валидные Avito-куки
proxy (Mobile change-url | Server статик | None)  +  rotate-until-clean
      → ротация IP до чистого (до AVITO_MAX_ROTATE_ATTEMPTS, дефолт 18)
curl_cffi (impersonate ∈ {chrome, edge, safari}, случайный UA)
      → GET каталога → follow SSR-редиректа на канонический URL категории
find_json_on_page (script[type=mime/invalid][data-mfe-state=true])
      → loaderData.data.catalog.items → факты (Listing)
```

Пагинация — параметром `pages` поверх этого прохода; фильтры
(`include_keywords`/`exclude_keywords`/`seller_blacklist`/`price_*`/`geo`/`max_age`)
— тоже параметры, не отдельные шаги.

## Провайдеры кук (`AVITO_COOKIE_PROVIDER`, дефолт `spfa`)

Единый интерфейс `CookiesProvider.get() / update() / handle_block()`.

| Провайдер | Как работает | Env |
|---|---|---|
| `spfa` (дефолт) | `POST spfa.ru/api/cookies` за куками, `/unblock` при блоке (валидировано) | `SPFA_API_KEY` |
| `own` | подставляет куки пользователя как есть | `AVITO_OWN_COOKIES` |
| `playwright` | браузерная добыча (кука `ft`); тяжёлая опциональная extra | — |

Дефолт `spfa` — без браузера и без ручных кук: ключ есть → куки приходят по HTTP.
`playwright` включай только когда spfa/own недоступны и нужен реальный браузер.

## Прокси (`AVITO_PROXY` + опц. `AVITO_PROXY_CHANGE_URL`)

Формат `user:pass@host:port`. Только RU-IP; мобильные > резидентные > датацентр.

| Тип | Условие | Ротация |
|---|---|---|
| `MobileProxy` | задан `AVITO_PROXY_CHANGE_URL` | дёргает change-url → новый IP |
| `ServerProxy` | статический `AVITO_PROXY` без change-url | нет |
| `NoProxy` | `AVITO_PROXY` не задан | нет |

## rotate-until-clean (наше улучшение retry-логики)

HTTP-клиент сохраняет проверенный метод парсинга (`curl_cffi` + `impersonate`),
но **меняет retry-логику**. Типичный дефект наивной retry-логики: связка
`block_threshold` + `max_count_of_retry` даёт **одну** ротацию и сдачу — на
смешанном IP-пуле парсер не пробивался.

Наш движок ротирует IP **до чистого ответа** (rotate-until-clean), до
`AVITO_MAX_ROTATE_ATTEMPTS` попыток (дефолт 18). На каждой попытке: сменить IP
(если `MobileProxy`), при блоке кук — `provider.handle_block()`, повторить.
Чистый ответ = каталог отдал JSON; блок (`403`/капча) = следующая попытка.

## Капча — это стоп-сигнал, а не задача

Техническая тактика: **капча = индикатор, что твой трафик уже помечен как
ботовый, а не стена, которую надо пробить.** Решатель (CapSolver/2captcha)
инженерно бесполезен — детектор продолжит триггериться, ты платишь десятками
секунд на челлендж (рушит throughput), антибот эскалирует и банит IP.

Правильная реакция: **этот IP → ротация до чистого, снизить общий rate,
устранить причину детекта** (TLS-отпечаток + чистый RU-прокси), а не проходить
челлендж. Движок делает это сам через rotate-until-clean.

| Соблазн | Что делать вместо |
|---|---|
| «Дедлайн, подключу CapSolver» | Почини `impersonate`-отпечаток + чистые RU-прокси; капча уйдёт сама |
| «Капча раз в 3 запроса — надо решать» | Трафик помечен ботом — снизь rate, rotate-until-clean, cooldown IP |
| «Решить дешевле, чем возиться» | Решение не убирает причину; растут баны и эскалация |

## find_json_on_page (извлечение фактов)

Данные каталога лежат не в DOM, а во встроенном стейте MFE:

- Найди `script[type=mime/invalid][data-mfe-state=true]` в HTML.
- Распарсь его содержимое как JSON.
- Возьми `loaderData.data.catalog.items` — это список объявлений.
- Смапь в модель `Listing` (факты: `id`, `title`, `price`, `url`, `address`,
  `params`, `seller_id`, `is_promotion`, `published_at` (epoch-секунды);
  `views` — только у `get_listing` при `with_views=true`).

Если селектор не нашёлся или `catalog` пуст — это признак блока/редиректа, а не
«пустого каталога»: проверь, прошёл ли follow-редирект и чист ли IP.

## Quick Reference

| Симптом | Причина | Действие |
|---|---|---|
| `403` «проблема с IP» | датацентр/иностранный IP | только RU-прокси (мобильные > резидентные), rotate-until-clean |
| Пустая страница / нет `catalog` | блок или непройденный редирект | follow SSR-редиректа, сменить IP, обновить куки |
| `firewallCaptcha` | hCaptcha/GeeTest | НЕ решать в лоб — ротация чистых IP |
| Капча на 30–50 запросе | поведенческий анализ | паузы 2–6с, длинная пауза каждые ~20 |
| `429` | rate limit | снизить темп, cooldown прокси |
| Одна ротация не помогла | смешанный IP-пул | rotate-until-clean (до `AVITO_MAX_ROTATE_ATTEMPTS`) |

## Env

| Переменная | Назначение |
|---|---|
| `SPFA_API_KEY` | ключ провайдера кук `spfa` |
| `AVITO_COOKIE_PROVIDER` | `spfa`\|`own`\|`playwright` (дефолт `spfa`) |
| `AVITO_OWN_COOKIES` | куки для провайдера `own` |
| `AVITO_PROXY` | `user:pass@host:port` |
| `AVITO_PROXY_CHANGE_URL` | URL ротации IP (→ `MobileProxy`) |
| `AVITO_MAX_ROTATE_ATTEMPTS` | лимит ротаций rotate-until-clean (дефолт 18) |

## Common Mistakes

- Датацентр-прокси или иностранный IP → мгновенный `403`.
- Ротация IP на каждый запрос без нужды → антифрод; ротируй на блоке (rotate-until-clean).
- Игнорировать SSR-редирект → пустой `catalog`, ложный «нет данных».
- Пиновать версию в `impersonate` → отпечаток протухает; держи набор {chrome, edge, safari}.
- Считать пустой `catalog` концом каталога, а не блоком → недобор данных.

## Тулзы (реализованы)

Движок обёрнут в MCP-тулзы; их список и параметры — в скиле
[using-avito-mcp](../using-avito-mcp/SKILL.md). Код движка —
в `server/src/avito_mcp_server/` репозитория плагина (`cookies/`, `proxies/`,
`http/`, `parser.py`, `filters/`, `tools/`).

## Related

- `docs/avito-scraping.md` (в репозитории плагина) — полная техдока движка (инструменты, прокси, БД)
- [using-avito-mcp](../using-avito-mcp/SKILL.md) — вызов движка через MCP-тулзы
