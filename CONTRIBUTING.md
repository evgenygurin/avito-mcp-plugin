# Вклад в avito-mcp-plugin

Спасибо за интерес к проекту. Ниже — как контрибьютить, чтобы изменения приняли.

## Перед началом

- Прочитай [`CLAUDE.md`](CLAUDE.md) (инструкции для агентов и людей) и
  [`docs/architecture.md`](docs/architecture.md).
- Ознакомься с **guardrails** по праву РФ — [`docs/avito-legal.md`](docs/avito-legal.md).
  PR, реализующие «лобовой» обход капчи или сбор ПДн для перепродажи, не принимаются.

## Workflow

1. Форкни репозиторий.
2. Создай ветку от `main`: `feat/<кратко>`, `fix/<кратко>`, `docs/<кратко>`.
3. Внеси изменения (см. ниже по типам).
4. Прогони проверки.
5. Открой PR с описанием **проблемы**, которую решаешь (не только «что изменил»).

## Типы изменений

### Skills

Skills — код, формирующий поведение агента. Меняй их по методологии
`superpowers:writing-skills`:

- `description` = **КОГДА** применять (триггеры/симптомы/ключевые слова), не пересказ workflow;
- тело < 500 строк; детали — в `references/`, детерминированные операции — в MCP-тулзы;
- перед PR — RED→GREEN→REFACTOR на субагентах, приложи результаты к PR.

### MCP-сервер

```bash
cd server
uv sync --dev
uv run ruff check .
uv run mypy src
uv run pytest -q          # добавь тест на новую тулзу (in-memory Client(mcp))
```

- Тулза: `async def`, Pydantic-модель возврата, `Context`, содержательный docstring.
- Не превышай ~20 тулз на сервер.

### Документация

- Пиши на русском, лаконично, активным залогом.
- Технические утверждения сверяй с `docs/researches/` и первоисточниками.

## Коммиты

Conventional Commits (см. `~/.claude/rules/git.md`):

```text
<type>(<scope>): <кратко до 72 символов>

<зачем это изменение>
```

Типы: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `style`.
Один коммит = одна логическая единица. Явный `git add <файлы>`, не `git add .`.

## Версии

При изменении поведения синхронно бампай `.claude-plugin/plugin.json` и
`server/pyproject.toml` по SemVer.
