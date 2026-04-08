#!/usr/bin/env python3
"""A2A-клиент для двусторонней связи Claude Code <-> Claudegram."""

import json
import os
import sys
import urllib.parse

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

PROXY_URL = os.getenv("PROXY_URL", "http://147.45.227.126/dbproxy.php")
PROXY_KEY = os.getenv("PROXY_KEY", "STAIL_SECRET_2025")
CLAUDEGRAM_URL = "http://147.45.227.126:3847/a2a/jsonrpc"
CLAUDEGRAM_TOKEN = "766295de1271343e0b084b253b50d36bf3e9f3e6a5baea9d"
DB = "stail_main"
TIMEOUT = 60.0


def _db_query(sql: str) -> list[dict] | str:
    params = {"key": PROXY_KEY, "db": DB, "sql": sql}
    url = f"{PROXY_URL}?{urllib.parse.urlencode(params)}"
    resp = httpx.get(url, timeout=15.0)
    text = resp.text
    if text.startswith(("connection failed", "error:", "forbidden")):
        return f"ERROR: {text}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _escape(s: str) -> str:
    return s.replace("'", "''")


def send_to_claudegram(message: str) -> dict | str:
    """Send a message to Claudegram via A2A."""
    payload = {
        "jsonrpc": "2.0",
        "id": "cc_" + str(int(__import__('time').time())),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}]
            }
        }
    }
    try:
        resp = httpx.post(
            CLAUDEGRAM_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CLAUDEGRAM_TOKEN}"
            },
            timeout=TIMEOUT
        )
        return resp.json()
    except Exception as e:
        return f"ERROR: {e}"


def check_inbox() -> list[dict] | str:
    """Check for new incoming A2A messages."""
    sql = (
        "SELECT id, task_id, sender, content, created_at "
        "FROM a2a_messages "
        "WHERE direction = 'incoming' AND recipient = 'claude-code' AND status = 'pending' "
        "ORDER BY created_at ASC"
    )
    return _db_query(sql)


def respond(task_id: str, response: str) -> str:
    """Respond to an incoming A2A message."""
    sql = (
        f"UPDATE a2a_messages SET status = 'completed', "
        f"response = '{_escape(response)}', updated_at = now() "
        f"WHERE task_id = '{_escape(task_id)}' RETURNING id"
    )
    result = _db_query(sql)
    if isinstance(result, list) and result:
        return f"OK: responded to {task_id}"
    return f"Result: {result}"


def history(limit: int = 10) -> list[dict] | str:
    """Show recent A2A messages."""
    sql = (
        f"SELECT id, task_id, direction, sender, LEFT(content, 200) as content, "
        f"status, LEFT(response, 200) as response, created_at "
        f"FROM a2a_messages ORDER BY created_at DESC LIMIT {limit}"
    )
    return _db_query(sql)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  a2a.py send <message>     — отправить сообщение Claudegram")
        print("  a2a.py inbox              — проверить входящие сообщения")
        print("  a2a.py respond <task_id> <text> — ответить на сообщение")
        print("  a2a.py history [limit]    — история сообщений")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "send":
        msg = sys.argv[2] if len(sys.argv) > 2 else ""
        result = send_to_claudegram(msg)
        print(json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, dict) else result)

    elif cmd == "inbox":
        result = check_inbox()
        print(json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, list) else result)

    elif cmd == "respond":
        task_id = sys.argv[2]
        text = sys.argv[3]
        print(respond(task_id, text))

    elif cmd == "history":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        result = history(limit)
        print(json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, list) else result)

    else:
        print(f"Unknown command: {cmd}")
