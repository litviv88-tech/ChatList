"""Стили и вспомогательные функции UI."""

from __future__ import annotations

APP_STYLESHEET = """
QMainWindow {
    background-color: #f4f6f9;
}

QMenuBar {
    background-color: #ffffff;
    border-bottom: 1px solid #d8dee9;
    padding: 4px;
}

QMenuBar::item:selected {
    background-color: #e8eef7;
    border-radius: 4px;
}

QStatusBar {
    background-color: #ffffff;
    border-top: 1px solid #d8dee9;
    color: #4a5568;
}

QGroupBox {
    font-weight: bold;
    border: 1px solid #d8dee9;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
    background-color: #ffffff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #2b6cb0;
}

QTextEdit, QLineEdit, QComboBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e0;
    border-radius: 6px;
    padding: 6px;
}

QTextEdit:focus, QLineEdit:focus, QComboBox:focus {
    border: 1px solid #4299e1;
}

QPushButton {
    background-color: #edf2f7;
    border: 1px solid #cbd5e0;
    border-radius: 6px;
    padding: 8px 14px;
    min-height: 18px;
}

QPushButton:hover {
    background-color: #e2e8f0;
}

QPushButton:pressed {
    background-color: #cbd5e0;
}

QPushButton#primaryButton {
    background-color: #3182ce;
    color: #ffffff;
    border: 1px solid #2b6cb0;
    font-weight: bold;
}

QPushButton#primaryButton:hover {
    background-color: #2b6cb0;
}

QPushButton#openButton {
    background-color: #ffffff;
}

QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    border: 1px solid #d8dee9;
    border-radius: 8px;
    gridline-color: #e2e8f0;
    selection-background-color: #ebf4ff;
    selection-color: #1a202c;
}

QHeaderView::section {
    background-color: #eef2f7;
    color: #2d3748;
    padding: 8px;
    border: none;
    border-right: 1px solid #d8dee9;
    border-bottom: 1px solid #d8dee9;
    font-weight: bold;
}

QLabel#sectionTitle {
    color: #2b6cb0;
    font-size: 14px;
    font-weight: bold;
}

QLabel#statusReady {
    color: #4a5568;
}

QLabel#statusSuccess {
    color: #2f855a;
    font-weight: bold;
}
"""


def normalize_response_text(text: str) -> str:
    return (
        text.replace("<br/>", "\n")
        .replace("<br />", "\n")
        .replace("<br>", "\n")
        .replace("\\n", "\n")
        .strip()
    )


def make_response_preview(text: str, max_lines: int = 6, max_chars: int = 500) -> str:
    normalized = normalize_response_text(text)
    lines = normalized.splitlines()
    if len(lines) > max_lines:
        normalized = "\n".join(lines[:max_lines]) + "\n..."
    if len(normalized) > max_chars:
        normalized = normalized[: max_chars - 3] + "..."
    return normalized


def is_error_response(text: str) -> bool:
    lowered = text.lower()
    markers = (
        "ошибка",
        "api-ключ",
        "не найден",
        "превышен",
        "неподдерживаемый",
        "не удалось",
    )
    return any(marker in lowered for marker in markers)
