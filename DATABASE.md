# DATABASE.md — схема базы данных ChatList

База данных: **SQLite**, файл `chatlist.db` в каталоге приложения.

Доступ к БД инкапсулирован в модуле `db.py`. API-ключи **не хранятся** в базе — только имя переменной окружения из файла `.env`.

---

## ER-диаграмма (логическая)

```
┌─────────────┐       ┌─────────────┐
│   prompts   │       │   models    │
├─────────────┤       ├─────────────┤
│ id (PK)     │       │ id (PK)     │
│ created_at  │       │ name        │
│ text        │       │ api_url     │
│ tags        │       │ api_id      │
└──────┬──────┘       │ api_key_env │
       │              │ model_type  │
       │              │ is_active   │
       │              └──────┬──────┘
       │                     │
       └──────────┬──────────┘
                  │
                  ▼
           ┌─────────────┐
           │   results   │
           ├─────────────┤
           │ id (PK)     │
           │ prompt_id   │── FK → prompts.id
           │ model_id    │── FK → models.id
           │ response    │
           │ created_at  │
           └─────────────┘

           ┌─────────────┐
           │  settings   │
           ├─────────────┤
           │ key (PK)    │
           │ value       │
           └─────────────┘
```

---

## Таблица `prompts`

Хранит сохранённые пользователем промты (запросы).

| Поле        | Тип          | Ограничения              | Описание                              |
|-------------|--------------|--------------------------|---------------------------------------|
| `id`        | INTEGER      | PRIMARY KEY AUTOINCREMENT| Уникальный идентификатор              |
| `created_at`| TEXT         | NOT NULL DEFAULT (datetime('now','localtime')) | Дата и время создания |
| `text`      | TEXT         | NOT NULL                 | Текст промта                          |
| `tags`      | TEXT         | NULL                     | Теги через запятую, напр. `python,sql`|

### SQL создания

```sql
CREATE TABLE IF NOT EXISTS prompts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    text       TEXT    NOT NULL,
    tags       TEXT
);
```

### Индексы

```sql
CREATE INDEX IF NOT EXISTS idx_prompts_created_at ON prompts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_prompts_text ON prompts (text);
```

---

## Таблица `models`

Справочник нейросетей, доступных для отправки промтов.

| Поле          | Тип     | Ограничения              | Описание                                           |
|---------------|---------|--------------------------|----------------------------------------------------|
| `id`          | INTEGER | PRIMARY KEY AUTOINCREMENT| Уникальный идентификатор                           |
| `name`        | TEXT    | NOT NULL UNIQUE          | Отображаемое имя модели                            |
| `api_url`     | TEXT    | NOT NULL                 | URL endpoint API                                   |
| `api_id`      | TEXT    | NOT NULL                 | Идентификатор модели в API (напр. `gpt-4o-mini`)  |
| `api_key_env` | TEXT    | NOT NULL                 | Имя переменной в `.env` (напр. `OPENAI_API_KEY`)   |
| `model_type`  | TEXT    | NOT NULL DEFAULT 'openai'| Тип адаптера: `openai`, `deepseek`, `groq` и т.д.  |
| `is_active`   | INTEGER | NOT NULL DEFAULT 1       | 1 — активна, 0 — отключена                         |

> **Важно:** значение `api_key_env` — это имя переменной окружения, а не сам ключ.  
> Пример `.env`: `OPENAI_API_KEY=sk-...`

### SQL создания

```sql
CREATE TABLE IF NOT EXISTS models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    api_url     TEXT    NOT NULL,
    api_id      TEXT    NOT NULL,
    api_key_env TEXT    NOT NULL,
    model_type  TEXT    NOT NULL DEFAULT 'openai',
    is_active   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);
```

### Пример начальных записей

| name           | api_url                                      | api_id          | api_key_env        | model_type | is_active |
|----------------|----------------------------------------------|-----------------|--------------------|------------|-----------|
| GPT-4o Mini    | https://api.openai.com/v1/chat/completions   | gpt-4o-mini     | OPENAI_API_KEY     | openai     | 0         |
| DeepSeek Chat  | https://api.deepseek.com/v1/chat/completions | deepseek-chat   | DEEPSEEK_API_KEY   | openai     | 0         |
| Llama 3 Groq   | https://api.groq.com/openai/v1/chat/completions | llama-3.1-8b-instant | GROQ_API_KEY | openai  | 0         |

---

## Таблица `results`

Постоянное хранилище ответов, которые пользователь отметил и сохранил.

| Поле        | Тип     | Ограничения              | Описание                              |
|-------------|---------|--------------------------|---------------------------------------|
| `id`        | INTEGER | PRIMARY KEY AUTOINCREMENT| Уникальный идентификатор              |
| `prompt_id` | INTEGER | NOT NULL, FK → prompts.id| Ссылка на промт                       |
| `model_id`  | INTEGER | NOT NULL, FK → models.id | Ссылка на модель                      |
| `response`  | TEXT    | NOT NULL                 | Текст ответа нейросети                |
| `created_at`| TEXT    | NOT NULL DEFAULT (datetime('now','localtime')) | Дата сохранения |

### SQL создания

```sql
CREATE TABLE IF NOT EXISTS results (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id  INTEGER NOT NULL,
    model_id   INTEGER NOT NULL,
    response   TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (prompt_id) REFERENCES prompts (id) ON DELETE CASCADE,
    FOREIGN KEY (model_id)  REFERENCES models  (id) ON DELETE RESTRICT
);
```

### Индексы

```sql
CREATE INDEX IF NOT EXISTS idx_results_prompt_id ON results (prompt_id);
CREATE INDEX IF NOT EXISTS idx_results_model_id  ON results (model_id);
CREATE INDEX IF NOT EXISTS idx_results_created_at ON results (created_at DESC);
```

---

## Таблица `settings`

Ключ–значение для настроек приложения.

| Поле   | Тип  | Ограничения | Описание                    |
|--------|------|-------------|-----------------------------|
| `key`  | TEXT | PRIMARY KEY | Имя настройки               |
| `value`| TEXT | NULL        | Значение настройки          |

### SQL создания

```sql
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
```

### Примеры настроек

| key                  | value (пример) | Описание                          |
|----------------------|----------------|-----------------------------------|
| `request_timeout`    | `60`           | Таймаут HTTP-запроса (секунды)    |
| `max_response_chars` | `8000`         | Макс. длина отображаемого ответа  |
| `theme`              | `light`        | Тема интерфейса                   |
| `last_prompt_id`     | `3`            | ID последнего использованного промта |

---

## Временная таблица результатов (не в SQLite)

При отправке промта программа формирует **in-memory** список (не сохраняется в БД до нажатия «Сохранить»):

| Поле          | Тип     | Описание                                      |
|---------------|---------|-----------------------------------------------|
| `model_name`  | str     | Имя модели (из `models.name`)                 |
| `model_id`    | int     | ID модели (для сохранения в `results`)        |
| `response`    | str     | Текст ответа или сообщение об ошибке          |
| `selected`    | bool    | Отметка пользователя (чекбокс в GUI)          |

Реализуется как список словарей или dataclass в памяти приложения. При новом запросе список полностью пересоздаётся.

---

## Связи и правила целостности

| Связь                    | Тип        | Поведение при удалении                          |
|--------------------------|------------|-------------------------------------------------|
| `results.prompt_id` → `prompts.id` | Many-to-One | CASCADE — удаление промта удаляет его результаты |
| `results.model_id` → `models.id`   | Many-to-One | RESTRICT — модель с результатами не удаляется   |

---

## Инициализация (`init_db`)

При первом запуске `db.py` выполняет:

1. Создание всех таблиц (`CREATE TABLE IF NOT EXISTS ...`).
2. Создание индексов.
3. Вставку начальных моделей (если таблица `models` пуста).
4. Установку настроек по умолчанию (если таблица `settings` пуста).

---

## Примечания по безопасности

- Файл `.env` с API-ключами **не коммитится** в git (уже в `.gitignore`).
- В БД хранится только имя переменной (`api_key_env`), не секрет.
- Рекомендуется включить `PRAGMA foreign_keys = ON` при каждом подключении к SQLite.
