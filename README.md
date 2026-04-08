# PostgreSQL MCP-сервер для Claude Code

MCP-сервер, позволяющий Claude Code напрямую работать с вашей PostgreSQL базой данных.

## Возможности

- **list_tables** — список всех таблиц в схеме с количеством строк
- **describe_table** — структура таблицы (колонки, типы, PK, FK)
- **query** — выполнение SELECT-запросов (только чтение)
- **execute** — выполнение INSERT/UPDATE/DELETE (требует `ALLOW_WRITE=true`)

## Установка

```bash
pip install -r requirements.txt
```

## Настройка

Скопируйте `.env.example` в `.env` и укажите параметры подключения:

```bash
cp .env.example .env
```

Отредактируйте `.env`:

```
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your_password
DB_NAME=your_database
ALLOW_WRITE=false
```

## Подключение к Claude Code

Добавьте MCP-сервер в настройки проекта (`.claude/settings.json`):

```json
{
  "mcpServers": {
    "postgres": {
      "command": "python3",
      "args": ["server.py"],
      "cwd": "/path/to/this/project"
    }
  }
}
```

Или через CLI:

```bash
claude mcp add postgres python3 server.py
```

## Безопасность

- По умолчанию разрешены только запросы на чтение (SELECT, WITH, EXPLAIN, SHOW)
- Для разрешения записи установите `ALLOW_WRITE=true` в `.env`
- Все запросы выполняются с таймаутом 30 секунд
- Пул соединений ограничен 5 подключениями
