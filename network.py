"""HTTP-запросы к API нейросетей."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

import db
from logger import get_logger

db.load_env()
logger = get_logger("chatlist.network")


class NetworkError(Exception):
    pass


def get_api_key(env_var_name: str) -> str:
    key = os.getenv(env_var_name, "").strip()
    if not key and env_var_name == "OPENROUTER_API_KEY":
        fallback = os.getenv("OPENAI_API_KEY", "").strip()
        if fallback.startswith("sk-or-v1-"):
            logger.info("Используется OPENAI_API_KEY как OPENROUTER_API_KEY")
            return fallback
    if not key:
        raise NetworkError(
            f"API-ключ не найден. Укажите переменную {env_var_name} в файле .env"
        )
    return key


def _get_timeout() -> float:
    value = db.get_setting("request_timeout", "60")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 60.0


def _send_openai_compatible(
    api_url: str,
    api_id: str,
    api_key: str,
    prompt_text: str,
    timeout: float,
    extra_headers: dict[str, str] | None = None,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    payload = {
        "model": api_id,
        "messages": [{"role": "user", "content": prompt_text}],
    }

    logger.info("Запрос к %s, модель %s", api_url, api_id)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(api_url, headers=headers, json=payload)
    except httpx.TimeoutException:
        logger.error("Таймаут запроса к %s", api_url)
        raise NetworkError("Превышено время ожидания ответа от API") from None
    except httpx.RequestError as exc:
        logger.error("Ошибка сети: %s", exc)
        raise NetworkError(f"Ошибка сети: {exc}") from exc

    if response.status_code == 401:
        raise NetworkError("Ошибка авторизации (401): проверьте API-ключ")
    if response.status_code == 429:
        raise NetworkError("Превышен лимит запросов (429): повторите позже")
    if response.status_code >= 400:
        raise NetworkError(f"Ошибка API ({response.status_code}): {response.text[:500]}")

    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"].strip()
        logger.info("Успешный ответ от %s", api_id)
        return content
    except (KeyError, IndexError, TypeError) as exc:
        raise NetworkError("Не удалось разобрать ответ API") from exc


def _send_openrouter(
    api_url: str,
    api_id: str,
    api_key: str,
    prompt_text: str,
    timeout: float,
) -> str:
    return _send_openai_compatible(
        api_url=api_url,
        api_id=api_id,
        api_key=api_key,
        prompt_text=prompt_text,
        timeout=timeout,
        extra_headers={
            "HTTP-Referer": "https://github.com/litviv88-tech/ChatList",
            "X-Title": "ChatList",
        },
    )


def send_prompt(model_row: dict[str, Any], prompt_text: str) -> str:
    model_type = model_row.get("model_type", "openai")
    timeout = _get_timeout()

    try:
        api_key = get_api_key(model_row["api_key_env"])
    except NetworkError as exc:
        logger.warning("Нет API-ключа для %s: %s", model_row.get("name"), exc)
        return str(exc)

    try:
        if model_type in {"openai", "deepseek", "groq"}:
            return _send_openai_compatible(
                api_url=model_row["api_url"],
                api_id=model_row["api_id"],
                api_key=api_key,
                prompt_text=prompt_text,
                timeout=timeout,
            )
        if model_type == "openrouter":
            return _send_openrouter(
                api_url=model_row["api_url"],
                api_id=model_row["api_id"],
                api_key=api_key,
                prompt_text=prompt_text,
                timeout=timeout,
            )
        return f"Неподдерживаемый тип модели: {model_type}"
    except NetworkError as exc:
        logger.error("Ошибка модели %s: %s", model_row.get("name"), exc)
        return str(exc)


def send_prompts_parallel(
    model_rows: list[dict[str, Any]],
    prompt_text: str,
) -> list[dict[str, Any]]:
    if not model_rows:
        return []

    logger.info("Параллельная отправка промта в %s моделей", len(model_rows))
    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=min(len(model_rows), 8)) as executor:
        future_map = {
            executor.submit(send_prompt, model_row, prompt_text): model_row
            for model_row in model_rows
        }

        for future in as_completed(future_map):
            model_row = future_map[future]
            try:
                response = future.result()
            except Exception as exc:
                response = f"Неожиданная ошибка: {exc}"
                logger.exception("Неожиданная ошибка для %s", model_row.get("name"))

            results.append(
                {
                    "model_id": model_row["id"],
                    "model_name": model_row["name"],
                    "response": response,
                    "selected": False,
                }
            )

    results.sort(key=lambda item: item["model_name"].lower())
    return results
