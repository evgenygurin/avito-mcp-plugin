# avito-mcp-plugin — инструкции для AI-агентов

Прочитай это перед работой в репозитории.

## Что это

Переносимый плагин для AI-агентов: **skills + встроенный MCP-сервер** (FastMCP v3)
для работы с Avito. Архитектура — «толстое ядро + тонкие адаптеры». Полный
контекст: [`docs/architecture.md`](docs/architecture.md). Стадия — ранняя (v0.1.0),
код тулз и финальные skills ещё не написаны.

## Guardrails (обязательно)

Проект работает с парсингом Avito — это зона правового риска в РФ. При любой
реализации сбора данных:

- **Не реализуй «лобовой» обход капчи** (решение hCaptcha/GeeTest) — это смещает
  правовую квалификацию к ст. 272 УК. Стратегия проекта — **избегать** капчи
  чистыми RU-прокси, а не решать её.
- **Не собирай персональные данные** (телефоны, имена продавцов) для перепродажи —
  152-ФЗ. По умолчанию — только фактические поля (цена, характеристики).
- **Не копируй существенную долю БД** — ст. 1334 ГК. Парсинг инкрементальный.
- Детали — [`docs/avito-legal.md`](docs/avito-legal.md) и скил
  [`avito-legal-guardrails`](skills/avito-legal-guardrails/SKILL.md).

Секреты (client_secret официального API, прокси-креды) — только через переменные
окружения. Не хардкодить, не логировать, не коммитить.

## Структура

- **Только `plugin.json`** лежит в `.claude-plugin/`. Все компоненты (`skills/`,
  `.mcp.json`, …) — в корне. Положишь `skills/` внутрь `.claude-plugin/` —
  тихий провал (компоненты не загрузятся).
- `.mcp.json` — **плоский формат** (ключ = имя сервера на верхнем уровне, без
  обёртки `mcpServers`).

## Изменение skills

Skills — это не проза, а код, формирующий поведение агента. Меняй их по
методологии `superpowers:writing-skills`:

- `description` описывает **КОГДА** применять (триггеры, симптомы, ключевые слова),
  а не пересказывает workflow;
- тело < 500 строк, детали — в `references/`, детерминированные операции — в тулзы;
- перед релизом — RED→GREEN→REFACTOR на субагентах.

Текущие 4 скила — **черновики-заготовки**, помечены статусом в теле.

## Изменение MCP-сервера

Пакет в [`server/`](server/README.md), src-layout, `uv`:

```bash
cd server
uv sync --dev
uv run pytest -q      # in-memory Client(mcp) — основной слой тестов
uv run ruff check .
uv run mypy src
```

- Тулзы: `async def`, Pydantic-модель возврата (structured output), `Context` для
  логов/прогресса, docstring = «что делает + когда вызывать».
- < 20 тулз на сервер (иначе падает точность выбора моделью).

## Документация зависимостей — Context7 (обязательно)

Перед тем как писать или менять код, использующий **FastMCP** или любую другую
Python-зависимость, **сначала сверься с актуальной документацией через Context7**
под ту версию, что реально стоит в проекте. Не полагайся на память, обучающие
данные или `docs/researches/` — API меняется между версиями.

Проверить установленную версию:

```bash
cd server && uv run python -c "import fastmcp; print(fastmcp.__version__)"
grep -E 'fastmcp|python' server/pyproject.toml server/uv.lock | head
```

Затем (workflow Context7 из глобального `~/.claude/CLAUDE.md`):

1. `resolve-library-id(libraryName: "fastmcp")` → получить Context7 ID.
2. `query-docs(id, topic: "<tools|context|structured-output|auth|testing|...>", mode: "code")`
   — `topic` **обязателен**; `mode=code` для примеров, `mode=info` для архитектуры.

**Почему это критично:** FastMCP v3 имел breaking changes относительно v2, а
детали отличаются даже между 3.x. Пример: в `fastmcp 3.4.4` `res.data` —
десериализованный объект (`res.data.length`), а не dict (`res.data["length"]`),
как показывал research. Сверка с доками под конкретную версию экономит время и
предотвращает ошибки.

Так же — для `pydantic`, `uv`, `httpx`/`curl_cffi` и прочих зависимостей: сверяй
API с версией из `uv.lock`, а не по памяти.

## Версии

SemVer синхронно: `.claude-plugin/plugin.json` ↔ `server/pyproject.toml`.

## Git

Следуй глобальным правилам (`~/.claude/rules/git.md`): Conventional Commits,
явный `git add <файлы>` (не `git add .`), атомарные коммиты, без force-push в main.
