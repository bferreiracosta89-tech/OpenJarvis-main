"""SQLite persistence for the authenticated JARVIS workspace.

The HTTP layer deliberately does not expose raw SQLite objects.  This store
keeps the local schema relational and ownership-aware so the same contracts
can later be backed by Neon/Postgres without changing the frontend API.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any


def _now() -> float:
    return time.time()


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class WorkspaceStore:
    """Persistent projects, chats, tasks, conclaves and user preferences."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from openjarvis.core.paths import get_config_dir

            db_path = get_config_dir() / "workspace.db"
        self.db_path = str(Path(db_path).expanduser()) if str(db_path) != ":memory:" else ":memory:"
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workspace_projects (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    color TEXT NOT NULL DEFAULT 'blue',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    archived_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_projects_user
                    ON workspace_projects(user_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS workspace_conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    project_id TEXT REFERENCES workspace_projects(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_conversations_user
                    ON workspace_conversations(user_id, pinned DESC, updated_at DESC);

                CREATE TABLE IF NOT EXISTS workspace_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES workspace_conversations(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_messages_conversation
                    ON workspace_messages(conversation_id, created_at);

                CREATE TABLE IF NOT EXISTS workspace_tasks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    project_id TEXT REFERENCES workspace_projects(id) ON DELETE SET NULL,
                    conversation_id TEXT REFERENCES workspace_conversations(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'todo',
                    priority TEXT NOT NULL DEFAULT 'normal',
                    due_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    completed_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_tasks_user
                    ON workspace_tasks(user_id, status, updated_at DESC);

                CREATE TABLE IF NOT EXISTS workspace_conclaves (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    objective TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    decision TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_conclave_members (
                    conclave_id TEXT NOT NULL REFERENCES workspace_conclaves(id) ON DELETE CASCADE,
                    agent_id TEXT NOT NULL,
                    PRIMARY KEY(conclave_id, agent_id)
                );

                CREATE TABLE IF NOT EXISTS workspace_notifications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'info',
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    read_at REAL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_workspace_notifications_user
                    ON workspace_notifications(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS workspace_settings (
                    user_id TEXT NOT NULL,
                    setting_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(user_id, setting_key)
                );
                """
            )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def _owned_project(self, conn: sqlite3.Connection, user_id: str, project_id: str | None) -> bool:
        if project_id is None:
            return True
        return conn.execute(
            "SELECT 1 FROM workspace_projects WHERE id = ? AND user_id = ? AND archived_at IS NULL",
            (project_id, user_id),
        ).fetchone() is not None

    def list_projects(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT p.*, COUNT(c.id) AS conversation_count
                   FROM workspace_projects p
                   LEFT JOIN workspace_conversations c ON c.project_id = p.id
                   WHERE p.user_id = ? AND p.archived_at IS NULL
                   GROUP BY p.id ORDER BY p.updated_at DESC""",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_project(self, user_id: str, name: str, description: str = "", color: str = "blue") -> dict[str, Any]:
        now = _now()
        project = {
            "id": _id("prj"), "user_id": user_id, "name": name.strip(),
            "description": description.strip(), "color": color.strip() or "blue",
            "created_at": now, "updated_at": now, "archived_at": None,
            "conversation_count": 0,
        }
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO workspace_projects
                   (id, user_id, name, description, color, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                tuple(project[key] for key in ("id", "user_id", "name", "description", "color", "created_at", "updated_at")),
            )
        return project

    def archive_project(self, user_id: str, project_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "UPDATE workspace_projects SET archived_at = ?, updated_at = ? WHERE id = ? AND user_id = ? AND archived_at IS NULL",
                (_now(), _now(), project_id, user_id),
            )
        return result.rowcount == 1

    def list_conversations(self, user_id: str, project_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            query = """SELECT c.*, COUNT(m.id) AS message_count
                       FROM workspace_conversations c
                       LEFT JOIN workspace_messages m ON m.conversation_id = c.id
                       WHERE c.user_id = ?"""
            params: list[Any] = [user_id]
            if project_id is not None:
                query += " AND c.project_id = ?"
                params.append(project_id)
            query += " GROUP BY c.id ORDER BY c.pinned DESC, c.updated_at DESC"
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            messages = conn.execute(
                "SELECT id, role, content, metadata_json, created_at FROM workspace_messages WHERE conversation_id = ? ORDER BY created_at, id",
                (conversation_id,),
            ).fetchall()
        result["pinned"] = bool(result["pinned"])
        result["messages"] = [
            {**dict(message), "metadata": _decode(message["metadata_json"], {}), **{"metadata_json": None}}
            for message in messages
        ]
        for message in result["messages"]:
            message.pop("metadata_json", None)
        return result

    def create_conversation(self, user_id: str, title: str = "Nova conversa", model: str = "", project_id: str | None = None) -> dict[str, Any]:
        now = _now()
        conversation_id = _id("chat")
        with self._connect() as conn:
            if not self._owned_project(conn, user_id, project_id):
                raise ValueError("Projeto não encontrado")
            conn.execute(
                """INSERT INTO workspace_conversations
                   (id, user_id, project_id, title, model, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (conversation_id, user_id, project_id, title.strip() or "Nova conversa", model.strip(), now, now),
            )
        return self.get_conversation(user_id, conversation_id) or {}

    def update_conversation(self, user_id: str, conversation_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {"title", "model", "project_id", "pinned"}
        values = {key: value for key, value in changes.items() if key in allowed and value is not None}
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM workspace_conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)).fetchone()
            if current is None:
                return None
            if "project_id" in values and not self._owned_project(conn, user_id, values["project_id"]):
                raise ValueError("Projeto não encontrado")
            if "pinned" in values:
                values["pinned"] = int(bool(values["pinned"]))
            if "title" in values:
                values["title"] = str(values["title"]).strip() or "Nova conversa"
            values["updated_at"] = _now()
            assignments = ", ".join(f"{key} = ?" for key in values)
            conn.execute(
                f"UPDATE workspace_conversations SET {assignments} WHERE id = ? AND user_id = ?",
                [*values.values(), conversation_id, user_id],
            )
        return self.get_conversation(user_id, conversation_id)

    def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute("DELETE FROM workspace_conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id))
        return result.rowcount == 1

    def append_message(self, user_id: str, conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("Papel de mensagem inválido")
        now = _now()
        message = {"id": _id("msg"), "role": role, "content": content, "metadata": metadata or {}, "created_at": now}
        with self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM workspace_conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)).fetchone()
            if exists is None:
                raise ValueError("Conversa não encontrada")
            conn.execute(
                "INSERT INTO workspace_messages(id, conversation_id, user_id, role, content, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (message["id"], conversation_id, user_id, role, content, _json(message["metadata"]), now),
            )
            conn.execute("UPDATE workspace_conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
        return message

    def list_tasks(self, user_id: str, status: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute("SELECT * FROM workspace_tasks WHERE user_id = ? AND status = ? ORDER BY updated_at DESC", (user_id, status)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM workspace_tasks WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def create_task(self, user_id: str, title: str, description: str = "", project_id: str | None = None, conversation_id: str | None = None, priority: str = "normal", due_at: float | None = None) -> dict[str, Any]:
        now = _now()
        task = {"id": _id("task"), "user_id": user_id, "project_id": project_id, "conversation_id": conversation_id, "title": title.strip(), "description": description.strip(), "status": "todo", "priority": priority, "due_at": due_at, "created_at": now, "updated_at": now, "completed_at": None}
        with self._connect() as conn:
            if not self._owned_project(conn, user_id, project_id):
                raise ValueError("Projeto não encontrado")
            if conversation_id and conn.execute("SELECT 1 FROM workspace_conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)).fetchone() is None:
                raise ValueError("Conversa não encontrada")
            conn.execute(
                """INSERT INTO workspace_tasks
                   (id, user_id, project_id, conversation_id, title, description, status, priority, due_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(task[key] for key in ("id", "user_id", "project_id", "conversation_id", "title", "description", "status", "priority", "due_at", "created_at", "updated_at")),
            )
        return task

    def update_task(self, user_id: str, task_id: str, **changes: Any) -> dict[str, Any] | None:
        allowed = {"title", "description", "status", "priority", "project_id", "conversation_id", "due_at"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if "status" in values and values["status"] not in {"todo", "in_progress", "done", "cancelled"}:
            raise ValueError("Status de tarefa inválido")
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM workspace_tasks WHERE id = ? AND user_id = ?", (task_id, user_id)).fetchone()
            if current is None:
                return None
            if "project_id" in values and not self._owned_project(conn, user_id, values["project_id"]):
                raise ValueError("Projeto não encontrado")
            if values.get("conversation_id") is not None and conn.execute(
                "SELECT 1 FROM workspace_conversations WHERE id = ? AND user_id = ?",
                (values["conversation_id"], user_id),
            ).fetchone() is None:
                raise ValueError("Conversa não encontrada")
            now = _now()
            values["updated_at"] = now
            if values.get("status") == "done":
                values["completed_at"] = now
            elif "status" in values:
                values["completed_at"] = None
            assignments = ", ".join(f"{key} = ?" for key in values)
            conn.execute(f"UPDATE workspace_tasks SET {assignments} WHERE id = ? AND user_id = ?", [*values.values(), task_id, user_id])
            row = conn.execute("SELECT * FROM workspace_tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row(row)

    def list_conclaves(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM workspace_conclaves WHERE user_id = ? ORDER BY updated_at DESC", (user_id,)).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                members = conn.execute("SELECT agent_id FROM workspace_conclave_members WHERE conclave_id = ? ORDER BY agent_id", (row["id"],)).fetchall()
                item["agent_ids"] = [member["agent_id"] for member in members]
                result.append(item)
        return result

    def create_conclave(self, user_id: str, title: str, objective: str = "", agent_ids: list[str] | None = None) -> dict[str, Any]:
        now = _now()
        item = {"id": _id("conclave"), "user_id": user_id, "title": title.strip(), "objective": objective.strip(), "status": "active", "decision": "", "created_at": now, "updated_at": now, "agent_ids": sorted(set(agent_ids or []))}
        with self._connect() as conn:
            conn.execute("INSERT INTO workspace_conclaves(id, user_id, title, objective, status, decision, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", tuple(item[key] for key in ("id", "user_id", "title", "objective", "status", "decision", "created_at", "updated_at")))
            conn.executemany("INSERT INTO workspace_conclave_members(conclave_id, agent_id) VALUES (?, ?)", [(item["id"], agent_id) for agent_id in item["agent_ids"]])
        return item

    def list_notifications(self, user_id: str, unread_only: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM workspace_notifications WHERE user_id = ?"
        if unread_only:
            query += " AND read_at IS NULL"
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, (user_id,)).fetchall()]

    def mark_notification_read(self, user_id: str, notification_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute("UPDATE workspace_notifications SET read_at = ? WHERE id = ? AND user_id = ?", (_now(), notification_id, user_id))
        return result.rowcount == 1

    def get_settings(self, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute("SELECT setting_key, value_json FROM workspace_settings WHERE user_id = ?", (user_id,)).fetchall()
        defaults = {
            "theme": "system", "font_size": "default", "default_model": "",
            "temperature": 0.7, "max_tokens": 4096, "speech_enabled": False,
            "voice_output_enabled": False, "voice_autoplay": False,
            "memory": {"enabled": True, "backend": "sqlite", "top_k": 5, "min_score": 0.1, "max_context_tokens": 2048},
        }
        for row in rows:
            defaults[row["setting_key"]] = _decode(row["value_json"], defaults.get(row["setting_key"]))
        return defaults

    def update_settings(self, user_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        with self._connect() as conn:
            for key, value in changes.items():
                conn.execute("INSERT INTO workspace_settings(user_id, setting_key, value_json, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(user_id, setting_key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at", (user_id, key, _json(value), now))
        return self.get_settings(user_id)


__all__ = ["WorkspaceStore"]
