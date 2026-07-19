"""Бизнес-логика ChatList."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import db
import network
from logger import get_logger
from prompt_assistant import (
    PromptAssistantError,
    PromptImprovement,
    build_system_prompt,
    parse_assistant_response,
)

logger = get_logger("chatlist.models")


@dataclass
class TempResultRow:
    model_id: int
    model_name: str
    response: str
    selected: bool = False


@dataclass
class AppState:
    current_prompt_id: int | None = None
    current_prompt_text: str = ""
    temp_results: list[TempResultRow] = field(default_factory=list)


_state = AppState()


def initialize() -> None:
    db.init_db()
    logger.info("Приложение инициализировано")


def check_env_setup() -> list[str]:
    """Проверка .env и возвращает список предупреждений."""
    db.load_env()
    warnings: list[str] = []

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    if openrouter_key.startswith("sk-or-v1-"):
        warnings.append("OPENROUTER_API_KEY: формат ключа OpenRouter корректный.")
    elif openai_key.startswith("sk-or-v1-"):
        warnings.append(
            "Ключ OpenRouter найден в OPENAI_API_KEY. "
            "Рекомендуется переименовать переменную в OPENROUTER_API_KEY."
        )
    elif not openrouter_key:
        warnings.append("OPENROUTER_API_KEY не задан.")

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key and not groq_key.startswith("gsk_"):
        warnings.append(
            "GROQ_API_KEY не похож на API-ключ Groq (обычно начинается с gsk_)."
        )

    active = get_active_models()
    if not active:
        warnings.append("Нет активных моделей в базе данных.")
    else:
        warnings.append(f"Активных моделей: {len(active)}.")

    return warnings


def get_active_models() -> list[dict[str, Any]]:
    return db.get_models(active_only=True)


def save_prompt(text: str, tags: str | None = None) -> int:
    return db.add_prompt(text, tags)


def get_prompts(search: str | None = None) -> list[dict[str, Any]]:
    return db.get_prompts(search)


def get_prompt(prompt_id: int) -> dict[str, Any] | None:
    return db.get_prompt(prompt_id)


def delete_prompt(prompt_id: int) -> None:
    db.delete_prompt(prompt_id)


def update_prompt(prompt_id: int, text: str, tags: str | None = None) -> None:
    db.update_prompt(prompt_id, text, tags)


def get_all_models() -> list[dict[str, Any]]:
    return db.get_models(active_only=False)


def add_model(**fields: Any) -> int:
    return db.add_model(**fields)


def update_model(model_id: int, **fields: Any) -> None:
    db.update_model(model_id, **fields)


def set_model_active(model_id: int, is_active: bool) -> None:
    db.set_model_active(model_id, is_active)


def delete_model(model_id: int) -> None:
    db.delete_model(model_id)


def get_settings() -> dict[str, str | None]:
    return db.get_all_settings()


def set_setting(key: str, value: str) -> None:
    db.set_setting(key, value)


def get_assistant_model() -> dict[str, Any] | None:
    model_id = db.get_setting("assistant_model_id")
    if model_id:
        model = db.get_model(int(model_id))
        if model is not None:
            return model

    for model in db.get_models(active_only=False):
        if model.get("model_type") == "openrouter":
            set_assistant_model(model["id"])
            return model
    return None


def set_assistant_model(model_id: int) -> None:
    db.set_setting("assistant_model_id", str(model_id))


def get_assistant_task_type() -> str:
    value = db.get_setting("assistant_task_type", "general")
    return value or "general"


def set_assistant_task_type(task_type: str) -> None:
    db.set_setting("assistant_task_type", task_type)


def improve_user_prompt(
    text: str,
    task_type: str | None = None,
) -> tuple[PromptImprovement | None, str | None]:
    prompt_text = text.strip()
    if not prompt_text:
        return None, "Введите текст промта"

    if db.get_setting("assistant_enabled", "1") != "1":
        return None, "AI-ассистент отключён в настройках"

    model = get_assistant_model()
    if model is None:
        return None, "Не найдена модель для AI-ассистента. Добавьте модель OpenRouter."

    selected_task_type = task_type or get_assistant_task_type()
    system_prompt = build_system_prompt(selected_task_type)

    try:
        raw_response = network.improve_prompt_request(model, prompt_text, system_prompt)
    except network.NetworkError as exc:
        return None, str(exc)

    try:
        result = parse_assistant_response(prompt_text, raw_response)
    except PromptAssistantError as exc:
        return None, str(exc)

    set_assistant_task_type(selected_task_type)
    logger.info("Промт улучшен ассистентом через модель %s", model.get("name"))
    return result, None


def get_saved_results(search: str | None = None) -> list[dict[str, Any]]:
    return db.get_results(search)


def clear_temp_results() -> None:
    _state.temp_results.clear()
    _state.current_prompt_id = None
    _state.current_prompt_text = ""


def get_temp_results() -> list[dict[str, Any]]:
    return [asdict(row) for row in _state.temp_results]


def get_current_prompt_id() -> int | None:
    return _state.current_prompt_id


def send_prompt(
    prompt_text: str,
    prompt_id: int | None = None,
    tags: str | None = None,
    save_prompt_to_db: bool = True,
) -> tuple[list[dict[str, Any]], str | None]:
    text = prompt_text.strip()
    if not text:
        return [], "Введите текст промта"

    active_models = get_active_models()
    if not active_models:
        return [], "Нет активных моделей. Включите хотя бы одну модель в настройках."

    if prompt_id is None and save_prompt_to_db:
        prompt_id = save_prompt(text, tags)
    elif prompt_id is None:
        return [], "Не указан промт для отправки"

    _state.current_prompt_id = prompt_id
    _state.current_prompt_text = text
    _state.temp_results.clear()

    logger.info("Отправка промта id=%s в %s моделей", prompt_id, len(active_models))
    raw_results = network.send_prompts_parallel(active_models, text)
    _state.temp_results = [
        TempResultRow(
            model_id=row["model_id"],
            model_name=row["model_name"],
            response=row["response"],
            selected=False,
        )
        for row in raw_results
    ]

    db.set_setting("last_prompt_id", str(prompt_id))
    return [row.__dict__ for row in _state.temp_results], None


def update_temp_selection(index: int, selected: bool) -> None:
    if 0 <= index < len(_state.temp_results):
        _state.temp_results[index].selected = selected


def save_selected_results() -> tuple[int, str | None]:
    if _state.current_prompt_id is None:
        return 0, "Сначала отправьте промт"

    selected_rows = [row for row in _state.temp_results if row.selected]
    if not selected_rows:
        return 0, "Отметьте хотя бы один результат для сохранения"

    for row in selected_rows:
        db.add_result(_state.current_prompt_id, row.model_id, row.response)

    saved_count = len(selected_rows)
    logger.info("Сохранено результатов: %s", saved_count)
    _state.temp_results.clear()
    return saved_count, None


def export_temp_results_json(path: Path, selected_only: bool = False) -> int:
    rows = get_temp_results()
    if selected_only:
        rows = [row for row in rows if row["selected"]]
    if not rows:
        return 0

    payload = {
        "prompt_id": _state.current_prompt_id,
        "prompt_text": _state.current_prompt_text,
        "results": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def export_temp_results_markdown(path: Path, selected_only: bool = False) -> int:
    rows = get_temp_results()
    if selected_only:
        rows = [row for row in rows if row["selected"]]
    if not rows:
        return 0

    lines = [
        "# ChatList — результаты",
        "",
        f"**Промт:** {_state.current_prompt_text}",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"## {row['model_name']}",
                "",
                row["response"],
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    return len(rows)


def verify_full_flow() -> list[str]:
    """Проверка полного сценария без GUI."""
    messages: list[str] = []
    initialize()
    messages.append("init_db: OK")

    for warning in check_env_setup():
        messages.append(warning)

    prompt_id = save_prompt("Тестовый промт для проверки", "test")
    messages.append(f"save_prompt: OK (id={prompt_id})")

    results, error = send_prompt("Скажи одно слово: привет", prompt_id=prompt_id, save_prompt_to_db=False)
    if error:
        messages.append(f"send_prompt: ОШИБКА — {error}")
        return messages

    messages.append(f"send_prompt: OK ({len(results)} ответов)")

    if results:
        update_temp_selection(0, True)
        saved, save_error = save_selected_results()
        if save_error:
            messages.append(f"save_selected_results: ОШИБКА — {save_error}")
        else:
            messages.append(f"save_selected_results: OK ({saved} записей)")

    history = get_saved_results("Тестовый")
    messages.append(f"get_saved_results: OK ({len(history)} записей)")
    return messages
