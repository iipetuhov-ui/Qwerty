<?php
/**
 * A2A JSON-RPC endpoint для Claude Code.
 * Принимает сообщения от других агентов и складывает в БД.
 * Claude Code забирает их через dbproxy.php.
 */

$SECRET = "STAIL_A2A_CLAUDE_CODE_2025";
$DB_CONN = "host=localhost dbname=stail_main user=postgres password=Grocnk7FytMog81tgFWK93Gf";

// Auth check
$auth = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
if ($auth !== "Bearer $SECRET") {
    header('Content-Type: application/json');
    echo json_encode(["jsonrpc" => "2.0", "id" => null, "error" => ["code" => 4003, "message" => "Authentication failed"]]);
    exit;
}

// Agent card
if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    header('Content-Type: application/json');
    echo json_encode([
        "protocolVersion" => "0.3.0",
        "name" => "Claude Code",
        "description" => "Claude Code agent with DB access, memory, and code capabilities.",
        "url" => "http://147.45.227.126/a2a_claude.php",
        "version" => "1.0.0",
        "preferredTransport" => "JSONRPC",
        "capabilities" => ["streaming" => false, "pushNotifications" => false],
        "securitySchemes" => ["bearer" => ["type" => "http", "scheme" => "bearer"]],
        "security" => [["bearer" => []]],
        "defaultInputModes" => ["text/plain"],
        "defaultOutputModes" => ["text/plain"],
        "skills" => [
            ["id" => "db-query", "name" => "Database Query", "description" => "Query PostgreSQL databases"],
            ["id" => "memory", "name" => "Memory", "description" => "Read/write persistent memory"],
            ["id" => "code", "name" => "Code Assistant", "description" => "Write and edit code"]
        ]
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

// Parse JSON-RPC
$body = json_decode(file_get_contents('php://input'), true);
if (!$body || ($body['method'] ?? '') !== 'message/send') {
    header('Content-Type: application/json');
    echo json_encode(["jsonrpc" => "2.0", "id" => $body['id'] ?? null, "error" => ["code" => -32601, "message" => "Method not found"]]);
    exit;
}

$parts = $body['params']['message']['parts'] ?? [];
$text = '';
foreach ($parts as $p) { if (($p['type'] ?? $p['kind'] ?? '') === 'text') $text .= $p['text']; }
$sender = $body['params']['message']['sender'] ?? 'unknown';

if (!$text) {
    header('Content-Type: application/json');
    echo json_encode(["jsonrpc" => "2.0", "id" => $body['id'], "error" => ["code" => 4006, "message" => "Empty message"]]);
    exit;
}

// Save to DB
$conn = pg_connect($DB_CONN);
if (!$conn) { die(json_encode(["jsonrpc" => "2.0", "id" => $body['id'], "error" => ["code" => -32000, "message" => "DB connection failed"]])); }

$task_id = 'a2a_' . time() . '_' . substr(md5(random_bytes(8)), 0, 7);
$text_escaped = pg_escape_string($conn, $text);
$sender_escaped = pg_escape_string($conn, $sender);

pg_query($conn, "INSERT INTO a2a_messages (task_id, direction, sender, recipient, content, status) VALUES ('$task_id', 'incoming', '$sender_escaped', 'claude-code', '$text_escaped', 'pending')");

// Return accepted task
header('Content-Type: application/json');
echo json_encode([
    "jsonrpc" => "2.0",
    "id" => $body['id'],
    "result" => [
        "id" => $task_id,
        "status" => [
            "state" => "accepted",
            "message" => ["role" => "agent", "parts" => [["type" => "text", "text" => "Message queued. Claude Code will process it when active."]]],
            "timestamp" => date('c')
        ]
    ]
], JSON_UNESCAPED_UNICODE);
