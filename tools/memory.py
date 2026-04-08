#!/usr/bin/env python3
"""Инструмент для работы с памятью (zoi_memory) и диалогами (zoi_dialogs) через HTTP-прокси."""

import json
import os
import sys
import urllib.parse
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

PROXY_URL = os.getenv("PROXY_URL", "http://147.45.227.126/dbproxy.php")
PROXY_KEY = os.getenv("PROXY_KEY", "STAIL_SECRET_2025")
DB = "stail_main"
TIMEOUT = 15.0


def _query(sql: str) -> list[dict] | str:
    """Execute SQL via HTTP proxy."""
    params = {"key": PROXY_KEY, "db": DB, "sql": sql}
    url = f"{PROXY_URL}?{urllib.parse.urlencode(params)}"
    resp = httpx.get(url, timeout=TIMEOUT)
    text = resp.text
    if text.startswith(("connection failed", "error:", "forbidden")):
        return f"ERROR: {text}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _escape(s: str) -> str:
    """Escape single quotes for SQL."""
    return s.replace("'", "''")


def save_memory(category: str, title: str, content: str, tags: list[str] | None = None, sender: str = "claude-code") -> str:
    """Save a memory entry to zoi_memory."""
    tags_sql = "NULL"
    if tags:
        tags_items = ", ".join(f"'{_escape(t)}'" for t in tags)
        tags_sql = f"ARRAY[{tags_items}]"

    sql = (
        f"INSERT INTO zoi_memory (category, title, content, tags, sender) "
        f"VALUES ('{_escape(category)}', '{_escape(title)}', '{_escape(content)}', "
        f"{tags_sql}, '{_escape(sender)}') RETURNING id"
    )
    result = _query(sql)
    if isinstance(result, list) and result:
        return f"OK: saved memory id={result[0]['id']}"
    return f"Result: {result}"


def log_dialog(role: str, content: str, session_key: str = "claude-code") -> str:
    """Log a dialog message to zoi_dialogs."""
    sql = (
        f"INSERT INTO zoi_dialogs (session_key, role, content, model, channel) "
        f"VALUES ('{_escape(session_key)}', '{_escape(role)}', '{_escape(content)}', "
        f"'claude-opus-4-6', 'claude-code') RETURNING id"
    )
    result = _query(sql)
    if isinstance(result, list) and result:
        return f"OK: logged dialog id={result[0]['id']}"
    return f"Result: {result}"


def search_memory(query: str, limit: int = 10) -> list[dict] | str:
    """Search memory by keyword."""
    sql = (
        f"SELECT id, category, title, LEFT(content, 300) as content, tags, created_at "
        f"FROM zoi_memory "
        f"WHERE content ILIKE '%{_escape(query)}%' OR title ILIKE '%{_escape(query)}%' "
        f"ORDER BY created_at DESC LIMIT {limit}"
    )
    return _query(sql)


def recent_memory(limit: int = 10, category: str | None = None) -> list[dict] | str:
    """Get recent memory entries."""
    where = ""
    if category:
        where = f"WHERE category = '{_escape(category)}'"
    sql = (
        f"SELECT id, category, title, LEFT(content, 300) as content, tags, created_at "
        f"FROM zoi_memory {where} "
        f"ORDER BY created_at DESC LIMIT {limit}"
    )
    return _query(sql)


def recent_dialogs(limit: int = 20, session_key: str | None = None) -> list[dict] | str:
    """Get recent dialog messages."""
    where = ""
    if session_key:
        where = f"WHERE session_key = '{_escape(session_key)}'"
    sql = (
        f"SELECT id, session_key, role, LEFT(content, 300) as content, model, channel, created_at "
        f"FROM zoi_dialogs {where} "
        f"ORDER BY created_at DESC LIMIT {limit}"
    )
    return _query(sql)


def save_session_summary(summary: str, tags: list[str] | None = None) -> str:
    """Save a session summary."""
    title = f"Claude Code Session {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    return save_memory("session", title, summary, tags or ["claude-code"])


def _print_results(data):
    """Pretty-print results."""
    if isinstance(data, str):
        print(data)
    elif isinstance(data, list):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(data)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  memory.py recent [limit] [category]  — последние записи памяти")
        print("  memory.py search <query> [limit]      — поиск в памяти")
        print("  memory.py dialogs [limit]              — последние диалоги")
        print('  memory.py save <category> <title> <content> [tag1,tag2]  — сохранить')
        print('  memory.py log <role> <content>         — записать диалог')
        print('  memory.py summary <text> [tag1,tag2]   — сохранить итог сессии')
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "recent":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        cat = sys.argv[3] if len(sys.argv) > 3 else None
        _print_results(recent_memory(limit, cat))

    elif cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        _print_results(search_memory(q, limit))

    elif cmd == "dialogs":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        _print_results(recent_dialogs(limit))

    elif cmd == "save":
        cat = sys.argv[2]
        title = sys.argv[3]
        content = sys.argv[4]
        tags = sys.argv[5].split(",") if len(sys.argv) > 5 else None
        print(save_memory(cat, title, content, tags))

    elif cmd == "log":
        role = sys.argv[2]
        content = sys.argv[3]
        print(log_dialog(role, content))

    elif cmd == "summary":
        text = sys.argv[2]
        tags = sys.argv[3].split(",") if len(sys.argv) > 3 else None
        print(save_session_summary(text, tags))

    else:
        print(f"Unknown command: {cmd}")
