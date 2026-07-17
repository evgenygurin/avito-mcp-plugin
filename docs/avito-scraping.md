# Парсинг Avito: техническая документация

Основано на исследовании
[`researches/…avito…`](researches/compass_artifact_wf-b2af6ce8-bf3c-54d9-be56-db9ddc0bc5c7_text_markdown.md).
Правовую часть см. в [`avito-legal.md`](avito-legal.md) — читать **до** сбора.

## TL;DR

- Avito защищён **Qrator/CURATOR Antibot** + фаервол-капча (hCaptcha Enterprise /
  GeeTest). «Голый» HTTP-клиент получает `403` «Доступ ограничен: проблема с IP».
- `curl_cffi` снимает TLS/JA3-слой, но **не исполняет JS** → Qrator-challenge не
  проходит. Нужен реальный браузер для кук либо чистые RU-прокси.
- Рабочая схема — **гибрид**: браузер генерирует куки (`qrator_jsid`) →
  куки+прокси → async HTTP-клиент к внутреннему JSON-API `m.avito.ru/api/*`.
- Живой open-source-ориентир — `Duff89/parser_avito`.

## Уровни защиты

| Уровень | Механизм | Признак |
|---|---|---|
| Сетевой | Блок IP, rate limiting | `403`/`429`, «проблема с IP» |
| Транспортный | TLS/JA3/JA4 fingerprint | блок до HTTP-ответа |
| Прикладной | Qrator JS-challenge, hCaptcha/GeeTest | пустая страница / капча |
| Поведенческий | Мышь, скролл, паттерны | внезапная капча на 30–50+ запросе |

Провайдер — **Qrator Labs** (российский бизнес с дек. 2024 — **Curator**).
Маркер прошедшего проверку — кука `qrator_jsid`. Фаервол-капча детектится через
эндпоинт `/web/5/firewallCaptcha/get` (параметр `rqdata`).

## Инструменты

### HTTP-клиенты

- **`curl_cffi`** — де-факто стандарт обхода TLS-fingerprint (`impersonate="chrome"`,
  async, ротация прокси, HTTP/2). Ограничение: **не исполняет JS**. Совет практики —
  не пиновать `chrome124`, паузы 1–3с, полный набор заголовков, одна сессия на IP.
- **`httpx`/`aiohttp`** — не спуфят TLS; httpx удобен как обёртка (в parser_avito
  curl_cffi подключён транспортом к httpx).
- Альтернативы: `tls-client`, `primp` (новее/быстрее).

```python
from curl_cffi import AsyncSession

async def fetch(url, proxy, cookies):
    async with AsyncSession(impersonate="chrome", proxies={"https": proxy}) as s:
        return await s.get(url, cookies=cookies, headers={
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Referer": "https://www.avito.ru/",
        })
```

### Браузеры (для добычи кук)

| Инструмент | База | Стелс | Против Avito |
|---|---|---|---|
| **Camoufox** | Firefox (C-level spoofing) | топ | работает; Firefox TLS иногда флагается |
| **nodriver/zendriver** | CDP напрямую | очень высокий | хорош, наследник undetected-chromedriver |
| **patchright** | Playwright fork | высокий | самый простой drop-in |
| **SeleniumBase UC** | undetected-chromedriver | высокий | проверенный RU-выбор |

**Headless детектится** — нужен headful или Xvfb.

## Гибридная схема (рекомендуемая)

```text
browser (patchright/Camoufox, headful/Xvfb, RU-прокси)
   → проходит Qrator JS-challenge → куки (qrator_jsid, …) → Redis (TTL ~10–12ч)
async workers (curl_cffi impersonate="chrome", http2=False) + sticky-прокси
   → m.avito.ru/api/*  или  JSON в HTML
```

**Внутренний мобильный API:** `m.avito.ru/api/9/items`, `/api/15/items/{id}`,
телефон — `/api/1/items/{id}/phone`. Требует параметр `key` (зашит во фронт,
меняется при обновлениях). Быстро, но нестабильно.

**Данные в HTML:** начальное состояние часто в JSON внутри страницы
(`__initialData__`) и JSON-LD. Атрибуты `data-marker` стабильнее CSS-классов.

## Официальный API

`api.avito.ru` — **только для своих объявлений/рекламы**, не для массового сбора
чужих. Детально — в скиле [`avito-official-api`](../skills/avito-official-api/SKILL.md).

- Авторизация: OAuth2 `client_credentials`, `GET /token/`.
- Scopes: `items:info`, `messenger:read/write`, `autoteka:*` и др.
- Лимиты: `X-RateLimit-Limit` / `X-RateLimit-Remaining`; у рекламного API — «баллы».

## Прокси

- **Только RU-IP.** Иностранные и датацентр → фаервол-заглушка сразу.
- **Иерархия:** мобильные > резидентные > датацентр.
- Порядок цен: мобильные ~2500–5000 ₽/мес, резидентные ~290 ₽/ГБ.
- **Ротация:** sticky-сессия на поток; смена IP+фингерпринта только на ретрае/бане.
  Смена контекста браузера каждые 15–20 запросов.
- **Паузы:** 2–6с между действиями, 30–60с каждые ~20 объявлений; «Показать
  телефон» — ≤5–10/мин.

## Production-архитектура

Под стек FastAPI / async SQLAlchemy / PostgreSQL / Redis / Celery+Kafka / Docker:

- **Browser pool** — отдельный Deployment (Playwright под Xvfb, 1 браузер = 1
  RU-прокси), складывает куки в Redis с TTL.
- **HTTP workers** — async `curl_cffi`, берут куки+sticky-прокси из Redis.
- **Очереди** — Celery (периодика/ретраи), Kafka (`listings.raw` → `listings.parsed`).
- **Мониторинг банов** — счётчик `403`/`429`/капч по прокси → карантин + алерт
  (Prometheus/Grafana).
- **Инкрементальный парсинг** — UPSERT + `content_hash`, история цен, по `last_seen`.

```python
async def fetch_with_retry(url, get_proxy, get_cookies, tries=3):
    for attempt in range(tries):
        proxy, cookies = get_proxy(), get_cookies()
        r = await fetch(url, proxy, cookies)
        if r.status_code == 200 and "firewallCaptcha" not in r.text:
            return r
        mark_bad(proxy)                         # карантин + новые куки
        await asyncio.sleep(2 ** attempt + random.random())
    raise BlockedError(url)
```

## Пороги смены стратегии

- >20% ответов — капча/`403` → сменить подход (браузер/прокси).
- Рост доли банов >10% → добавить прокси / снизить темп.
- Стоимость поддержки антибот-обхода > $300–500/мес → рассмотреть сервис
  (Apify-актор под Avito) или официальный API.

## Caveats

- Точные лимиты/пороги бана Avito публично не раскрыты — цифры оценочные.
- Внутренний `key` и эндпоинты мобильного API меняются без предупреждения.
- `curl_cffi` в одиночку против Qrator, скорее всего, недостаточен.
- Antidetect-браузеры — движущаяся мишень, требуют патчинга.

Полные источники и оговорки — в
[исследовании](researches/compass_artifact_wf-b2af6ce8-bf3c-54d9-be56-db9ddc0bc5c7_text_markdown.md).
