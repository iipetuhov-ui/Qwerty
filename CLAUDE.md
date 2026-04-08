# Инструкции для Claude Code

## Память (PostgreSQL)

У тебя есть долговременная память — PostgreSQL база `stail_main` на сервере `147.45.227.126`.
Доступ через HTTP-прокси: `http://147.45.227.126/dbproxy.php`

### Как читать память

```bash
# Последние 10 записей
python3 tools/memory.py recent 10

# Поиск по ключевому слову
python3 tools/memory.py search "тема"

# Последние диалоги
python3 tools/memory.py dialogs 20

# Записи определённой категории
python3 tools/memory.py recent 10 config
```

Или через curl напрямую:
```bash
curl -s 'http://147.45.227.126/dbproxy.php?key=STAIL_SECRET_2025&db=stail_main&sql=SELECT...'
```

### Как записывать в память

```bash
# Сохранить запись
python3 tools/memory.py save <category> <title> <content> [tag1,tag2]

# Записать диалог
python3 tools/memory.py log <role> <content>

# Сохранить итог сессии
python3 tools/memory.py summary "Описание что сделали" claude-code,tag2
```

### Категории памяти
- `session` — итоги сессий
- `config` — конфигурации и настройки
- `project` — проекты и задачи
- `knowledge` — полезные знания
- `system` — системная информация
- `chat_log` — логи чата
- `credentials` — учётные данные
- `contact` — контакты
- `lesson` — уроки и выводы

### Когда записывать

1. **В начале сессии** — прочитай `python3 tools/memory.py recent 5` чтобы понять контекст
2. **При важных решениях** — сохрани решение в память (category: `knowledge` или `project`)
3. **При изменении конфигураций** — сохрани что изменилось (category: `config`)
4. **В конце сессии** — сохрани итог через `python3 tools/memory.py summary "..."`

### Доступные базы данных

| БД | Описание |
|---|---|
| `stail_main` | Основная — память, диалоги, пациенты, арбитраж, боты |
| `dental` | Стоматология — пациенты, врачи, приёмы, услуги |
| `invest` | Инвестиции — свечи, офферы |
| `smc_bot` | Торговый бот — сделки, стратегии |

## Пользователь

Имя: Ivan (Иван). Компания: ООО "СТАЙЛ-С" (стоматология).
Сервер: 147.45.227.126 (Timeweb Cloud).
На сервере также работает OpenClaw с агентом Zoi (Зоя) и Anna.

## Проект Qwerty

MCP-сервер + система памяти для подключения Claude Code к PostgreSQL на удалённом сервере.
HTTP-прокси (`dbproxy.php`) установлен на сервере, потому что прямые TCP-подключения из среды Claude Code заблокированы.
