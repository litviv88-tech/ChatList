"""Настройка логирования ChatList."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

import db

LOG_DIR = db.get_app_dir() / "logs"
LOG_FILE = LOG_DIR / "chatlist.log"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("chatlist")
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


def get_logger(name: str = "chatlist") -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
