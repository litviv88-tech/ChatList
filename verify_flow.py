"""Проверка связки компонентов ChatList (этап 5 PLAN.md)."""

from __future__ import annotations

import db
import models
from logger import get_logger, setup_logging


def main() -> None:
    setup_logging()
    logger = get_logger("chatlist.verify")
    db.load_env()
    models.initialize()

    print("=== Проверка ChatList ===")
    for message in models.verify_full_flow():
        print(message)
        logger.info(message)

    print("\nЛог: logs/chatlist.log")


if __name__ == "__main__":
    main()
