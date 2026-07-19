"""Модуль доступа к SQLite для ChatList."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def load_env() -> None:
    from dotenv import load_dotenv

    load_dotenv(get_app_dir() / ".env")


DB_PATH = get_app_dir() / "chatlist.db"

DEFAULT_MODELS: list[dict[str, Any]] = [
    {
        "name": "GPT-4o Mini",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "api_id": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "model_type": "openai",
        "is_active": 0,
    },
    {
        "name": "DeepSeek Chat",
        "api_url": "https://api.deepseek.com/v1/chat/completions",
        "api_id": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_type": "openai",
        "is_active": 0,
    },
    {
        "name": "Llama 3 Groq",
        "api_url": "https://api.groq.com/openai/v1/chat/completions",
        "api_id": "llama-3.1-8b-instant",
        "api_key_env": "GROQ_API_KEY",
        "model_type": "openai",
        "is_active": 0,
    },
    {
        "name": "OpenRouter GPT-4o Mini",
        "api_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_id": "openai/gpt-4o-mini",
        "api_key_env": "OPENROUTER_API_KEY",
        "model_type": "openrouter",
        "is_active": 1,
    },
    {
        "name": "OpenRouter DeepSeek Chat",
        "api_url": "https://openrouter.ai/api/v1/chat/completions",
        "api_id": "deepseek/deepseek-chat",
        "api_key_env": "OPENROUTER_API_KEY",
        "model_type": "openrouter",
        "is_active": 1,
    },
]

DEFAULT_SETTINGS: dict[str, str] = {
    "request_timeout": "60",
    "max_response_chars": "8000",
    "theme": "light",
}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS prompts (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
                text       TEXT    NOT NULL,
                tags       TEXT
            );

            CREATE TABLE IF NOT EXISTS models (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                api_url     TEXT    NOT NULL,
                api_id      TEXT    NOT NULL,
                api_key_env TEXT    NOT NULL,
                model_type  TEXT    NOT NULL DEFAULT 'openai',
                is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
            );

            CREATE TABLE IF NOT EXISTS results (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id  INTEGER NOT NULL,
                model_id   INTEGER NOT NULL,
                response   TEXT    NOT NULL,
                created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (prompt_id) REFERENCES prompts (id) ON DELETE CASCADE,
                FOREIGN KEY (model_id)  REFERENCES models  (id) ON DELETE RESTRICT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_prompts_created_at ON prompts (created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_prompts_text ON prompts (text);
            CREATE INDEX IF NOT EXISTS idx_results_prompt_id ON results (prompt_id);
            CREATE INDEX IF NOT EXISTS idx_results_model_id ON results (model_id);
            CREATE INDEX IF NOT EXISTS idx_results_created_at ON results (created_at DESC);
            """
        )

        model_count = conn.execute("SELECT COUNT(*) FROM models").fetchone()[0]
        if model_count == 0:
            conn.executemany(
                """
                INSERT INTO models (name, api_url, api_id, api_key_env, model_type, is_active)
                VALUES (:name, :api_url, :api_id, :api_key_env, :model_type, :is_active)
                """,
                DEFAULT_MODELS,
            )
        else:
            _ensure_seed_models(conn)

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO settings (key, value)
                VALUES (?, ?)
                """,
                (key, value),
            )

        conn.commit()


def _ensure_seed_models(conn: sqlite3.Connection) -> None:
    for model in DEFAULT_MODELS:
        exists = conn.execute(
            "SELECT id FROM models WHERE name = ?",
            (model["name"],),
        ).fetchone()
        if exists is None:
            conn.execute(
                """
                INSERT INTO models (name, api_url, api_id, api_key_env, model_type, is_active)
                VALUES (:name, :api_url, :api_id, :api_key_env, :model_type, :is_active)
                """,
                model,
            )


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


# --- prompts ---


def add_prompt(text: str, tags: str | None = None) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO prompts (text, tags) VALUES (?, ?)",
            (text.strip(), tags),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_prompts(search: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT * FROM prompts"
    params: tuple[Any, ...] = ()
    if search:
        query += " WHERE text LIKE ? OR IFNULL(tags, '') LIKE ?"
        pattern = f"%{search.strip()}%"
        params = (pattern, pattern)
    query += " ORDER BY created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_prompt(prompt_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
    return _row_to_dict(row)


def delete_prompt(prompt_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        conn.commit()


# --- models ---


def add_model(
    name: str,
    api_url: str,
    api_id: str,
    api_key_env: str,
    model_type: str = "openai",
    is_active: int = 0,
) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO models (name, api_url, api_id, api_key_env, model_type, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name.strip(), api_url.strip(), api_id.strip(), api_key_env.strip(), model_type, is_active),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_models(active_only: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM models"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY name"

    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
    return [dict(row) for row in rows]


def get_model(model_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    return _row_to_dict(row)


def update_model(model_id: int, **fields: Any) -> None:
    allowed = {"name", "api_url", "api_id", "api_key_env", "model_type", "is_active"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return

    columns = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [model_id]

    with get_connection() as conn:
        conn.execute(f"UPDATE models SET {columns} WHERE id = ?", values)
        conn.commit()


def set_model_active(model_id: int, is_active: bool) -> None:
    update_model(model_id, is_active=1 if is_active else 0)


def delete_model(model_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
        conn.commit()


# --- results ---


def add_result(prompt_id: int, model_id: int, response: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO results (prompt_id, model_id, response)
            VALUES (?, ?, ?)
            """,
            (prompt_id, model_id, response),
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_results(search: str | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT
            r.id,
            r.prompt_id,
            r.model_id,
            r.response,
            r.created_at,
            p.text AS prompt_text,
            m.name AS model_name
        FROM results r
        JOIN prompts p ON p.id = r.prompt_id
        JOIN models m ON m.id = r.model_id
    """
    params: tuple[Any, ...] = ()
    if search:
        query += " WHERE r.response LIKE ? OR p.text LIKE ? OR m.name LIKE ?"
        pattern = f"%{search.strip()}%"
        params = (pattern, pattern, pattern)
    query += " ORDER BY r.created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


# --- settings ---


def get_setting(key: str, default: str | None = None) -> str | None:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return row["value"]


def get_all_settings() -> dict[str, str | None]:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    return {row["key"]: row["value"] for row in rows}


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()


if __name__ == "__main__":
    init_db()
    prompts = get_prompts()
    models = get_models()
    settings = get_all_settings()
    print(f"База данных инициализирована: {DB_PATH}")
    print(f"Промтов: {len(prompts)}, моделей: {len(models)}, настроек: {len(settings)}")
