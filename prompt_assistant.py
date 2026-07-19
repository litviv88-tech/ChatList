"""AI-ассистент для улучшения промтов."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

TASK_TYPES = {
    "general": "Общая задача",
    "code": "Код",
    "analysis": "Анализ",
    "creative": "Креатив",
}

TASK_INSTRUCTIONS = {
    "general": "Сделай промт более конкретным, структурированным и однозначным.",
    "code": (
        "Адаптируй промт под задачу программирования: укажи язык, формат ответа, "
        "ограничения и ожидаемый результат."
    ),
    "analysis": (
        "Адаптируй промт под аналитическую задачу: добавь критерии, шаги рассуждения "
        "и формат вывода."
    ),
    "creative": (
        "Адаптируй промт под креативную задачу: уточни стиль, тон, аудиторию "
        "и ограничения."
    ),
}


@dataclass
class PromptImprovement:
    original: str
    improved: str
    alternatives: list[str]
    notes: str = ""


class PromptAssistantError(Exception):
    pass


def build_system_prompt(task_type: str = "general") -> str:
    instruction = TASK_INSTRUCTIONS.get(task_type, TASK_INSTRUCTIONS["general"])
    return f"""Ты помощник по улучшению промтов для нейросетей.
{instruction}
Сохраняй исходный смысл запроса пользователя.
Верни только JSON без markdown и пояснений вне JSON:
{{
  "improved": "улучшенный промт",
  "alternatives": ["вариант 1", "вариант 2", "вариант 3"],
  "notes": "краткий комментарий, что изменено"
}}
alternatives должно содержать от 2 до 3 строк."""


def extract_json_text(raw_text: str) -> str:
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def parse_assistant_response(original: str, raw_text: str) -> PromptImprovement:
    try:
        data = json.loads(extract_json_text(raw_text))
    except json.JSONDecodeError as exc:
        raise PromptAssistantError(
            f"Не удалось разобрать ответ ассистента.\n\nОтвет модели:\n{raw_text[:1000]}"
        ) from exc

    improved = str(data.get("improved", "")).strip()
    alternatives = data.get("alternatives", [])
    notes = str(data.get("notes", "")).strip()

    if not improved:
        raise PromptAssistantError("Ответ ассистента не содержит поле improved.")

    if not isinstance(alternatives, list):
        alternatives = []

    cleaned_alternatives = [str(item).strip() for item in alternatives if str(item).strip()]
    if len(cleaned_alternatives) < 2:
        raise PromptAssistantError("Ответ ассистента должен содержать 2–3 альтернативы.")

    return PromptImprovement(
        original=original,
        improved=improved,
        alternatives=cleaned_alternatives[:3],
        notes=notes,
    )


if __name__ == "__main__":
    sample = """
```json
{
  "improved": "Объясни Python простыми словами для новичка.",
  "alternatives": [
    "Что такое Python и где он используется?",
    "Опиши Python как язык программирования."
  ],
  "notes": "Добавлена аудитория и ясность."
}
```
"""
    result = parse_assistant_response("что такое Python?", sample)
    print(result.improved)
    print(result.alternatives)
