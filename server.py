"""MCP-сервер для работы с PostgreSQL из Claude Code."""

import asyncio
import os
from contextlib import asynccontextmanager

import asyncpg
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Context

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "postgres")
ALLOW_WRITE = os.getenv("ALLOW_WRITE", "false").lower() == "true"

QUERY_TIMEOUT = 30.0

READONLY_PREFIXES = ("SELECT", "WITH", "EXPLAIN", "SHOW")


@asynccontextmanager
async def db_lifespan(server: FastMCP):
    """Create and manage the database connection pool."""
    pool = await asyncpg.create_pool(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        min_size=1,
        max_size=5,
    )
    try:
        yield pool
    finally:
        await pool.close()


mcp = FastMCP(
    "PostgreSQL Connector",
    instructions="MCP-сервер для работы с PostgreSQL. Позволяет просматривать таблицы, схему и выполнять SQL-запросы.",
    lifespan=db_lifespan,
)


def _get_pool(ctx: Context) -> asyncpg.Pool:
    """Extract the connection pool from the context."""
    return ctx.request_context.lifespan_context


def _format_rows(rows: list[asyncpg.Record]) -> str:
    """Format query results as a readable table."""
    if not rows:
        return "Запрос не вернул результатов."

    columns = list(rows[0].keys())
    data = [dict(r) for r in rows]
    for row in data:
        for k, v in row.items():
            if not isinstance(v, (str, int, float, bool, type(None))):
                row[k] = str(v)

    col_widths = {col: len(col) for col in columns}
    for row in data:
        for col in columns:
            val = str(row.get(col, ""))
            col_widths[col] = max(col_widths[col], len(val))

    header = " | ".join(col.ljust(col_widths[col]) for col in columns)
    separator = "-+-".join("-" * col_widths[col] for col in columns)
    lines = [header, separator]
    for row in data:
        line = " | ".join(
            str(row.get(col, "")).ljust(col_widths[col]) for col in columns
        )
        lines.append(line)

    lines.append(f"\n({len(data)} rows)")
    return "\n".join(lines)


@mcp.tool(
    name="list_tables",
    description="Список всех таблиц в базе данных. Возвращает имена таблиц, их тип и примерное количество строк.",
)
async def list_tables(ctx: Context, schema: str = "public") -> str:
    """List all tables in the database."""
    pool = _get_pool(ctx)
    query = """
        SELECT
            t.table_name,
            t.table_type,
            COALESCE(s.n_live_tup, 0) AS approx_row_count
        FROM information_schema.tables t
        LEFT JOIN pg_stat_user_tables s
            ON s.schemaname = t.table_schema AND s.relname = t.table_name
        WHERE t.table_schema = $1
        ORDER BY t.table_name
    """
    rows = await pool.fetch(query, schema, timeout=QUERY_TIMEOUT)
    if not rows:
        return f"В схеме '{schema}' таблиц не найдено."
    return _format_rows(rows)


@mcp.tool(
    name="describe_table",
    description="Структура таблицы: колонки, типы данных, nullable, значения по умолчанию, первичные и внешние ключи.",
)
async def describe_table(
    ctx: Context, table_name: str, schema: str = "public"
) -> str:
    """Describe a table's structure."""
    pool = _get_pool(ctx)

    columns_query = """
        SELECT
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            c.character_maximum_length
        FROM information_schema.columns c
        WHERE c.table_schema = $1 AND c.table_name = $2
        ORDER BY c.ordinal_position
    """

    pk_query = """
        SELECT a.attname AS column_name
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        JOIN pg_class cls ON cls.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = cls.relnamespace
        WHERE i.indisprimary
            AND n.nspname = $1
            AND cls.relname = $2
    """

    fk_query = """
        SELECT
            kcu.column_name,
            ccu.table_schema AS foreign_schema,
            ccu.table_name AS foreign_table,
            ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = $1
            AND tc.table_name = $2
    """

    columns, pks, fks = await asyncio.gather(
        pool.fetch(columns_query, schema, table_name, timeout=QUERY_TIMEOUT),
        pool.fetch(pk_query, schema, table_name, timeout=QUERY_TIMEOUT),
        pool.fetch(fk_query, schema, table_name, timeout=QUERY_TIMEOUT),
    )

    if not columns:
        return f"Таблица '{schema}.{table_name}' не найдена."

    pk_columns = {r["column_name"] for r in pks}
    fk_map = {r["column_name"]: r for r in fks}

    lines = [f"Таблица: {schema}.{table_name}\n"]
    lines.append("Колонки:")
    for col in columns:
        parts = [f"  {col['column_name']}"]
        dtype = col["data_type"]
        if col["character_maximum_length"]:
            dtype += f"({col['character_maximum_length']})"
        parts.append(dtype)
        if col["column_name"] in pk_columns:
            parts.append("PRIMARY KEY")
        if col["is_nullable"] == "NO":
            parts.append("NOT NULL")
        if col["column_default"]:
            parts.append(f"DEFAULT {col['column_default']}")
        lines.append(" | ".join(parts))

    if fk_map:
        lines.append("\nВнешние ключи:")
        for col_name, fk in fk_map.items():
            lines.append(
                f"  {col_name} -> {fk['foreign_schema']}.{fk['foreign_table']}.{fk['foreign_column']}"
            )

    return "\n".join(lines)


@mcp.tool(
    name="query",
    description="Выполнить SQL-запрос только для чтения (SELECT, WITH, EXPLAIN, SHOW). Возвращает результат в табличном виде.",
)
async def run_query(ctx: Context, sql: str) -> str:
    """Execute a read-only SQL query."""
    normalized = sql.strip().upper()
    if not normalized.startswith(READONLY_PREFIXES):
        return (
            "Ошибка: разрешены только запросы на чтение (SELECT, WITH, EXPLAIN, SHOW). "
            "Для записи используйте инструмент 'execute'."
        )

    pool = _get_pool(ctx)
    try:
        rows = await pool.fetch(sql, timeout=QUERY_TIMEOUT)
        return _format_rows(rows)
    except Exception as e:
        return f"Ошибка выполнения запроса: {e}"


@mcp.tool(
    name="execute",
    description="Выполнить SQL-запрос на запись (INSERT, UPDATE, DELETE, CREATE, ALTER, DROP). Работает только если ALLOW_WRITE=true.",
)
async def run_execute(ctx: Context, sql: str) -> str:
    """Execute a write SQL query."""
    if not ALLOW_WRITE:
        return (
            "Ошибка: запись в БД отключена. "
            "Установите ALLOW_WRITE=true в .env для разрешения записи."
        )

    normalized = sql.strip().upper()
    if normalized.startswith(READONLY_PREFIXES):
        return "Для запросов на чтение используйте инструмент 'query'."

    pool = _get_pool(ctx)
    try:
        result = await pool.execute(sql, timeout=QUERY_TIMEOUT)
        return f"Выполнено успешно: {result}"
    except Exception as e:
        return f"Ошибка выполнения: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
