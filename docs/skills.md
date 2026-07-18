# Skills

Skills — процедурное знание плагина по открытому стандарту
[Agent Skills](https://agentskills.io) (`SKILL.md`). Они переносимы между
Claude Code, Codex, Cursor, Gemini CLI, VS Code и другими агентами.

## Скилы плагина

| Скил | Когда триггерится | Тип |
|---|---|---|
| [`using-avito-mcp`](../skills/using-avito-mcp/SKILL.md) | нужны данные Avito → маршрутизация в тулзы | reference |
| [`scraping-avito`](../skills/scraping-avito/SKILL.md) | антибот, `403`/`429`, капча при парсинге | technique |

> Оба — **черновики-заготовки**. Финализация — по методологии
> `superpowers:writing-skills` (см. ниже).
>
> Скилы `avito-legal-guardrails` и `avito-official-api` удалены вместе с
> официальным API — проект переходит на целевой фичесет парсинга Avito
> ([дизайн](superpowers/specs/2026-07-18-avito-parser-design.md)), где
> legal-обвязка и работа со своим кабинетом через официальный API не входят
> в фичесет.

## Формат SKILL.md

```markdown
---
name: skill-name                 # опц.; по умолчанию = имя директории; lowercase+hyphens, ≤64
description: >                   # ОБЯЗАТЕЛЬНО: КОГДА применять (не что делает), с trigger-словами
  Use when [условие] — [симптомы, ключевые слова].
allowed-tools: Read, Grep        # опц. (через дефис!), пред-одобренные тулзы
---
# Заголовок
Тело: держать < 500 строк / ~5k токенов; детали — в references/, код — в scripts/.
```

Часть открытого стандарта — только `name`, `description`, `license`,
`compatibility`, `metadata`, `allowed-tools`. Остальные поля (`model`, `context`,
`disable-model-invocation`, `argument-hint` …) — расширения Claude Code.

### Description решает всё

`description` — главный фактор срабатывания. Правила:

- пиши от третьего лица, начинай с «Use when …»;
- описывай **только условия/симптомы триггера**, а не workflow скила;
- включай ключевые слова, по которым агент будет искать (тексты ошибок:
  `403`, `firewallCaptcha`; симптомы: «капча», «пустая страница»);
- **не пересказывай процесс** — иначе агент выполнит description вместо чтения тела.

## Progressive disclosure (3 уровня)

1. **Startup:** агент грузит только `name` + `description` каждого скила
   (~80–100 токенов) в системный промпт.
2. **Activation:** при совпадении задачи грузится полное тело `SKILL.md`.
3. **Execution:** `scripts/` (выполняются, код не входит в контекст),
   `references/` (грузятся по требованию), `assets/` (шаблоны/статика).

Поэтому: тонкий `SKILL.md`, тяжёлая логика — в MCP-тулзах, детали — в `references/`.

## Как финализировать скил (writing-skills)

Создание скила = TDD для документации: **RED → GREEN → REFACTOR**.

1. **RED** — прогони сценарий на субагенте БЕЗ скила, зафиксируй, как он ошибается
   и какие «отговорки» использует.
2. **GREEN** — напиши минимальный скил, закрывающий именно эти ошибки; прогони
   те же сценарии СО скилом — агент должен соблюдать правила.
3. **REFACTOR** — находи новые лазейки, добавляй явные контр-аргументы, повторяй
   до устойчивости.

Полная методология — в скиле `superpowers:writing-skills`. Каждый скил перед
релизом тестируется на свежем агенте.

## Дальше

- Переносимость skills между агентами → [`portability.md`](portability.md)
- Раздача skills по MCP (`SkillsProvider`) → [`mcp-server.md`](mcp-server.md)
