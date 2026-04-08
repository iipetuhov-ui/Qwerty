"""MCP-сервер для работы с PostgreSQL через HTTP-прокси."""

import json
import os
import urllib.parse

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

PROXY_URL = os.getenv("PROXY_URL", "http://147.45.227.126/dbproxy.php")
PROXY_KEY = os.getenv("PROXY_KEY", "STAIL_SECRET_2025")
DEFAULT_DB = os.getenv("DEFAULT_DB", "stail_main")
ALLOW_WRITE = os.getenv("ALLOW_WRITE", "false").lower() == "true"

READONLY_PREFIXES = ("SELECT", "WITH", "EXPLAIN", "SHOW")

DATABASES = ["dental", "invest", "smc_bot", "stail_main"]


async def _query_db(sql: str, db: str | None = None) -> list[dict] | str:
    """Execute SQL via HTTP proxy and return rows or error string."""
    db = db or DEFAULT_DB
    params = {"key": PROXY_KEY, "db": db, "sql": sql}
    url = f"{PROXY_URL}?{urllib.parse.urlencode(params)}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        text = resp.text
    if resp.status_code != 200:
        return f"Ошибка HTTP {resp.status_code}: {text}"
    if text.startswith(("connection failed", "error:", "no query", "forbidden")):
        return f"Ошибка: {text}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return f"Неожиданный ответ: {text[:500]}"


def _format_rows(rows: list[dict]) -> str:
    """Format query results as a readable table."""
    if not rows:
        return "Запрос не вернул результатов."

    columns = list(rows[0].keys())

    col_widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            val = str(row.get(col, ""))
            col_widths[col] = max(col_widths[col], min(len(val), 60))

    header = " | ".join(col.ljust(col_widths[col]) for col in columns)
    separator = "-+-".join("-" * col_widths[col] for col in columns)
    lines = [header, separator]
    for row in rows:
        line = " | ".join(
            str(row.get(col, "")).ljust(col_widths[col])[:60] for col in columns
        )
        lines.append(line)

    lines.append(f"\n({len(rows)} rows)")
    return "\n".join(lines)


mcp = FastMCP(
    "PostgreSQL Connector",
    instructions=(
        "MCP-сервер для работы с PostgreSQL на сервере 147.45.227.126. "
        f"Доступные базы данных: {', '.join(DATABASES)}. "
        "По умолчанию используется stail_main."
    ),
)


@mcp.tool(
    name="list_databases",
    description="Список доступных баз данных на сервере.",
)
async def list_databases() -> str:
    """List available databases."""
    result = await _query_db(
        "SELECT datname, pg_size_pretty(pg_database_size(datname)) as size "
        "FROM pg_database WHERE datname NOT IN ('postgres','template0','template1') "
        "ORDER BY datname",
        db="postgres",
    )
    if isinstance(result, str):
        return result
    return _format_rows(result)


@mcp.tool(
    name="list_tables",
    description="Список всех таблиц в базе данных с количеством строк.",
)
async def list_tables(db: str = "stail_main", schema: str = "public") -> str:
    """List all tables in a database."""
    sql = (
        "SELECT t.table_name, t.table_type, "
        "COALESCE(s.n_live_tup, 0) AS approx_row_count "
        "FROM information_schema.tables t "
        "LEFT JOIN pg_stat_user_tables s "
        "ON s.schemaname = t.table_schema AND s.relname = t.table_name "
        f"WHERE t.table_schema = '{schema}' ORDER BY t.table_name"
    )
    result = await _query_db(sql, db)
    if isinstance(result, str):
        return result
    if not result:
        return f"В схеме '{schema}' базы '{db}' таблиц не найдено."
    return _format_rows(result)


@mcp.tool(
    name="describe_table",
    description="Структура таблицы: колонки, типы данных, nullable, PK, FK.",
)
async def describe_table(
    table_name: str, db: str = "stail_main", schema: str = "public"
) -> str:
    """Describe a table's structure."""
    columns_sql = (
        "SELECT column_name, data_type, is_nullable, column_default, "
        "character_maximum_length "
        "FROM information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = '{table_name}' "
        "ORDER BY ordinal_position"
    )
    pk_sql = (
        "SELECT a.attname AS column_name "
        "FROM pg_index i "
        "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
        "JOIN pg_class cls ON cls.oid = i.indrelid "
        "JOIN pg_namespace n ON n.oid = cls.relnamespace "
        f"WHERE i.indisprimary AND n.nspname = '{schema}' AND cls.relname = '{table_name}'"
    )
    fk_sql = (
        "SELECT kcu.column_name, ccu.table_name AS foreign_table, "
        "ccu.column_name AS foreign_column "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "ON tc.constraint_name = kcu.constraint_name "
        "JOIN information_schema.constraint_column_usage ccu "
        "ON ccu.constraint_name = tc.constraint_name "
        f"WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = '{schema}' "
        f"AND tc.table_name = '{table_name}'"
    )

    columns = await _query_db(columns_sql, db)
    if isinstance(columns, str):
        return columns
    if not columns:
        return f"Таблица '{schema}.{table_name}' не найдена в базе '{db}'."

    pks = await _query_db(pk_sql, db)
    fks = await _query_db(fk_sql, db)

    pk_columns = set()
    if isinstance(pks, list):
        pk_columns = {r["column_name"] for r in pks}

    fk_map = {}
    if isinstance(fks, list):
        fk_map = {r["column_name"]: r for r in fks}

    lines = [f"Таблица: {db}.{schema}.{table_name}\n", "Колонки:"]
    for col in columns:
        parts = [f"  {col['column_name']}"]
        dtype = col["data_type"]
        if col.get("character_maximum_length"):
            dtype += f"({col['character_maximum_length']})"
        parts.append(dtype)
        if col["column_name"] in pk_columns:
            parts.append("PRIMARY KEY")
        if col["is_nullable"] == "NO":
            parts.append("NOT NULL")
        if col.get("column_default"):
            parts.append(f"DEFAULT {col['column_default']}")
        lines.append(" | ".join(parts))

    if fk_map:
        lines.append("\nВнешние ключи:")
        for col_name, fk in fk_map.items():
            lines.append(f"  {col_name} -> {fk['foreign_table']}.{fk['foreign_column']}")

    return "\n".join(lines)


@mcp.tool(
    name="query",
    description="Выполнить SQL-запрос только для чтения (SELECT). Указывайте базу данных параметром db.",
)
async def run_query(sql: str, db: str = "stail_main") -> str:
    """Execute a read-only SQL query."""
    normalized = sql.strip().upper()
    if not normalized.startswith(READONLY_PREFIXES):
        return (
            "Ошибка: разрешены только запросы на чтение (SELECT, WITH, EXPLAIN, SHOW). "
            "Для записи используйте инструмент 'execute'."
        )
    result = await _query_db(sql, db)
    if isinstance(result, str):
        return result
    return _format_rows(result)


@mcp.tool(
    name="execute",
    description="Выполнить SQL-запрос на запись (INSERT, UPDATE, DELETE и др.). Работает только если ALLOW_WRITE=true.",
)
async def run_execute(sql: str, db: str = "stail_main") -> str:
    """Execute a write SQL query."""
    if not ALLOW_WRITE:
        return (
            "Ошибка: запись в БД отключена. "
            "Установите ALLOW_WRITE=true в .env для разрешения записи."
        )
    normalized = sql.strip().upper()
    if normalized.startswith(READONLY_PREFIXES):
        return "Для запросов на чтение используйте инструмент 'query'."
    result = await _query_db(sql, db)
    if isinstance(result, str):
        return result
    return f"Выполнено успешно. Затронуто строк: {len(result)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
