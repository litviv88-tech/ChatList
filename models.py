"""Бизнес-логика ChatList."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import db
import network


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


def get_saved_results(search: str | None = None) -> list[dict[str, Any]]:
    return db.get_results(search)


def clear_temp_results() -> None:
    _state.temp_results.clear()
    _state.current_prompt_id = None
    _state.current_prompt_text = ""


def get_temp_results() -> list[TempResultRow]:
    return list(_state.temp_results)


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
    _state.temp_results.clear()
    return saved_count, None
