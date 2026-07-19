"""Главное окно ChatList."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import db
import models
from logger import setup_logging
from ui_helpers import (
    APP_STYLESHEET,
    is_error_response,
    make_response_preview,
    normalize_response_text,
)


class SendPromptWorker(QThread):
    finished = pyqtSignal(list, object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        prompt_text: str,
        prompt_id: int | None = None,
        tags: str | None = None,
        save_prompt_to_db: bool = True,
    ) -> None:
        super().__init__()
        self.prompt_text = prompt_text
        self.prompt_id = prompt_id
        self.tags = tags
        self.save_prompt_to_db = save_prompt_to_db

    def run(self) -> None:
        results, error = models.send_prompt(
            self.prompt_text,
            prompt_id=self.prompt_id,
            tags=self.tags,
            save_prompt_to_db=self.save_prompt_to_db,
        )
        if error:
            self.failed.emit(error)
        else:
            self.finished.emit(results, None)


class ResponseViewDialog(QDialog):
    def __init__(
        self,
        model_name: str,
        prompt_text: str,
        response_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Просмотр: {model_name}")
        self.resize(760, 560)

        prompt_title = QLabel("Промт")
        prompt_title.setObjectName("sectionTitle")
        prompt_view = QTextEdit()
        prompt_view.setReadOnly(True)
        prompt_view.setPlainText(prompt_text)
        prompt_view.setMinimumHeight(90)

        response_title = QLabel("Ответ")
        response_title.setObjectName("sectionTitle")
        response_view = QTextEdit()
        response_view.setReadOnly(True)
        response_view.setPlainText(normalize_response_text(response_text))
        if not is_error_response(response_text):
            response_view.setStyleSheet("color: #2f855a;")

        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(close_button)

        layout = QVBoxLayout()
        layout.addWidget(prompt_title)
        layout.addWidget(prompt_view)
        layout.addWidget(response_title)
        layout.addWidget(response_view, stretch=1)
        layout.addLayout(buttons)
        self.setLayout(layout)


class PromptEditDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        prompt_data: dict[str, Any] | None = None,
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        if read_only:
            self.setWindowTitle("Просмотр промта")
        elif prompt_data:
            self.setWindowTitle("Изменить промт")
        else:
            self.setWindowTitle("Создать промт")

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Текст промта...")
        self.text_edit.setMinimumHeight(120)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Теги (необязательно, через запятую)")

        if prompt_data:
            self.text_edit.setPlainText(prompt_data["text"])
            self.tags_edit.setText(prompt_data.get("tags") or "")

        if read_only:
            self.text_edit.setReadOnly(True)
            self.tags_edit.setReadOnly(True)

        form = QFormLayout()
        form.addRow("Текст", self.text_edit)
        form.addRow("Теги", self.tags_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        if read_only:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Закрыть")
            buttons.button(QDialogButtonBox.StandardButton.Cancel).hide()
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def get_data(self) -> dict[str, str | None]:
        return {
            "text": self.text_edit.toPlainText().strip(),
            "tags": self.tags_edit.text().strip() or None,
        }


class PromptsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Промты")
        self.resize(920, 520)
        self._parent_window = parent

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по тексту или тегам")
        self.search_edit.textChanged.connect(self.load_prompts)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Дата", "Текст", "Теги"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(True)
        self.table.doubleClicked.connect(self.read_prompt)

        self.create_button = QPushButton("Создать")
        self.read_button = QPushButton("Просмотр")
        self.update_button = QPushButton("Изменить")
        self.delete_button = QPushButton("Удалить")
        self.use_button = QPushButton("Выбрать")
        self.refresh_button = QPushButton("Обновить")

        self.create_button.setObjectName("primaryButton")
        self.delete_button.setStyleSheet("QPushButton { color: #c53030; }")

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.search_edit, stretch=1)
        top_layout.addWidget(self.refresh_button)

        crud_layout = QHBoxLayout()
        crud_layout.addWidget(self.create_button)
        crud_layout.addWidget(self.read_button)
        crud_layout.addWidget(self.update_button)
        crud_layout.addWidget(self.delete_button)
        crud_layout.addWidget(self.use_button)
        crud_layout.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(top_layout)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(crud_layout)
        self.setLayout(layout)

        self.create_button.clicked.connect(self.create_prompt)
        self.read_button.clicked.connect(self.read_prompt)
        self.update_button.clicked.connect(self.update_prompt)
        self.delete_button.clicked.connect(self.delete_prompt)
        self.use_button.clicked.connect(self.use_prompt)
        self.refresh_button.clicked.connect(self.load_prompts)

        self.load_prompts()

    def _selected_prompt(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        prompt_id = int(item.text())
        return models.get_prompt(prompt_id)

    def load_prompts(self) -> None:
        search = self.search_edit.text().strip() or None
        rows = models.get_prompts(search)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(str(row["id"])))
            self.table.setItem(row_index, 1, QTableWidgetItem(row["created_at"]))

            text_item = QTableWidgetItem(row["text"].replace("\n", " "))
            text_item.setToolTip(row["text"])
            text_item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            )
            self.table.setItem(row_index, 2, text_item)
            self.table.setItem(row_index, 3, QTableWidgetItem(row.get("tags") or ""))

        self.table.resizeRowsToContents()
        self.table.setSortingEnabled(True)

    def _refresh_parent(self) -> None:
        if isinstance(self._parent_window, MainWindow):
            self._parent_window.load_prompts()

    def create_prompt(self) -> None:
        dialog = PromptEditDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()
        if not data["text"]:
            QMessageBox.warning(self, "Промт", "Введите текст промта")
            return

        try:
            models.save_prompt(data["text"], data["tags"])
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать промт:\n{exc}")
            return

        self.load_prompts()
        self._refresh_parent()

    def read_prompt(self) -> None:
        prompt = self._selected_prompt()
        if prompt is None:
            QMessageBox.information(self, "Промты", "Выберите промт в таблице")
            return

        dialog = PromptEditDialog(parent=self, prompt_data=prompt, read_only=True)
        dialog.exec()

    def update_prompt(self) -> None:
        prompt = self._selected_prompt()
        if prompt is None:
            QMessageBox.information(self, "Промты", "Выберите промт в таблице")
            return

        dialog = PromptEditDialog(parent=self, prompt_data=prompt)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.get_data()
        if not data["text"]:
            QMessageBox.warning(self, "Промт", "Введите текст промта")
            return

        try:
            models.update_prompt(prompt["id"], data["text"], data["tags"])
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось изменить промт:\n{exc}")
            return

        self.load_prompts()
        self._refresh_parent()

    def delete_prompt(self) -> None:
        prompt = self._selected_prompt()
        if prompt is None:
            QMessageBox.information(self, "Промты", "Выберите промт в таблице")
            return

        answer = QMessageBox.question(
            self,
            "Удаление",
            "Удалить выбранный промт и связанные результаты?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            models.delete_prompt(prompt["id"])
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить промт:\n{exc}")
            return

        self.load_prompts()
        self._refresh_parent()

    def use_prompt(self) -> None:
        prompt = self._selected_prompt()
        if prompt is None:
            QMessageBox.information(self, "Промты", "Выберите промт в таблице")
            return

        if isinstance(self._parent_window, MainWindow):
            self._parent_window.apply_prompt(prompt)
        self.accept()


class ModelsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Управление моделями")
        self.resize(900, 420)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Имя", "API URL", "API ID", "Переменная .env", "Активна"]
        )
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по имени или API ID")
        self.search_edit.textChanged.connect(self.load_models)

        self.refresh_button = QPushButton("Обновить")
        self.add_button = QPushButton("Добавить")
        self.edit_button = QPushButton("Изменить")
        self.toggle_button = QPushButton("Вкл/Выкл")
        self.delete_button = QPushButton("Удалить")

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.search_edit, stretch=1)
        buttons_layout.addWidget(self.refresh_button)
        buttons_layout.addWidget(self.add_button)
        buttons_layout.addWidget(self.edit_button)
        buttons_layout.addWidget(self.toggle_button)
        buttons_layout.addWidget(self.delete_button)

        layout = QVBoxLayout()
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(buttons_layout)
        self.setLayout(layout)

        self.refresh_button.clicked.connect(self.load_models)
        self.add_button.clicked.connect(self.add_model)
        self.edit_button.clicked.connect(self.edit_model)
        self.toggle_button.clicked.connect(self.toggle_active)
        self.delete_button.clicked.connect(self.delete_model)

        self.load_models()

    def load_models(self) -> None:
        search = self.search_edit.text().strip().lower()
        rows = models.get_all_models()
        if search:
            rows = [
                row
                for row in rows
                if search in row["name"].lower()
                or search in row["api_id"].lower()
                or search in row["api_key_env"].lower()
            ]

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(str(row["id"])))
            self.table.setItem(row_index, 1, QTableWidgetItem(row["name"]))
            self.table.setItem(row_index, 2, QTableWidgetItem(row["api_url"]))
            self.table.setItem(row_index, 3, QTableWidgetItem(row["api_id"]))
            self.table.setItem(row_index, 4, QTableWidgetItem(row["api_key_env"]))
            checkbox = QCheckBox()
            checkbox.setChecked(bool(row["is_active"]))
            checkbox.setEnabled(False)
            self.table.setCellWidget(row_index, 5, checkbox)
        self.table.setSortingEnabled(True)

    def _selected_model_id(self) -> int | None:
        current_row = self.table.currentRow()
        if current_row < 0:
            return None
        item = self.table.item(current_row, 0)
        return int(item.text()) if item else None

    def add_model(self) -> None:
        dialog = ModelEditDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            models.add_model(**dialog.get_data())
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить модель:\n{exc}")
            return
        self.load_models()

    def edit_model(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            QMessageBox.information(self, "Модели", "Выберите модель в таблице")
            return

        current = next((item for item in models.get_all_models() if item["id"] == model_id), None)
        if current is None:
            return

        dialog = ModelEditDialog(parent=self, model_data=current)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            models.update_model(model_id, **dialog.get_data())
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось изменить модель:\n{exc}")
            return
        self.load_models()

    def toggle_active(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            QMessageBox.information(self, "Модели", "Выберите модель в таблице")
            return

        current = next((item for item in models.get_all_models() if item["id"] == model_id), None)
        if current is None:
            return

        models.set_model_active(model_id, not bool(current["is_active"]))
        self.load_models()

    def delete_model(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            QMessageBox.information(self, "Модели", "Выберите модель в таблице")
            return

        answer = QMessageBox.question(
            self,
            "Удаление",
            "Удалить выбранную модель?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            models.delete_model(model_id)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить модель:\n{exc}")
            return
        self.load_models()


class ModelEditDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        model_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Редактирование модели" if model_data else "Новая модель")

        self.name_edit = QLineEdit()
        self.url_edit = QLineEdit("https://openrouter.ai/api/v1/chat/completions")
        self.api_id_edit = QLineEdit("openai/gpt-4o-mini")
        self.env_edit = QLineEdit("OPENROUTER_API_KEY")
        self.type_edit = QLineEdit("openrouter")
        self.active_checkbox = QCheckBox("Активна")

        if model_data:
            self.name_edit.setText(model_data["name"])
            self.url_edit.setText(model_data["api_url"])
            self.api_id_edit.setText(model_data["api_id"])
            self.env_edit.setText(model_data["api_key_env"])
            self.type_edit.setText(model_data["model_type"])
            self.active_checkbox.setChecked(bool(model_data["is_active"]))
        else:
            self.active_checkbox.setChecked(False)

        form = QFormLayout()
        form.addRow("Имя", self.name_edit)
        form.addRow("API URL", self.url_edit)
        form.addRow("API ID", self.api_id_edit)
        form.addRow("Переменная .env", self.env_edit)
        form.addRow("Тип", self.type_edit)
        form.addRow("", self.active_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def get_data(self) -> dict[str, Any]:
        return {
            "name": self.name_edit.text().strip(),
            "api_url": self.url_edit.text().strip(),
            "api_id": self.api_id_edit.text().strip(),
            "api_key_env": self.env_edit.text().strip(),
            "model_type": self.type_edit.text().strip() or "openai",
            "is_active": 1 if self.active_checkbox.isChecked() else 0,
        }


class ResultsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("История результатов")
        self.resize(1000, 520)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по промту, модели или ответу")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Дата", "Промт", "Модель", "Ответ", "ID"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)

        self.open_button = QPushButton("Открыть")
        self.export_json_button = QPushButton("Экспорт JSON")
        self.export_md_button = QPushButton("Экспорт Markdown")
        self.refresh_button = QPushButton("Обновить")

        buttons = QHBoxLayout()
        buttons.addWidget(self.search_edit, stretch=1)
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.export_json_button)
        buttons.addWidget(self.export_md_button)

        layout = QVBoxLayout()
        layout.addLayout(buttons)
        layout.addWidget(self.table, stretch=1)
        self.setLayout(layout)

        self.search_edit.textChanged.connect(self.load_results)
        self.refresh_button.clicked.connect(self.load_results)
        self.open_button.clicked.connect(self.open_selected)
        self.export_json_button.clicked.connect(self.export_json)
        self.export_md_button.clicked.connect(self.export_markdown)
        self.table.doubleClicked.connect(self.open_selected)
        self.load_results()

    def open_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "История", "Выберите строку в таблице")
            return

        prompt_item = self.table.item(row, 1)
        model_item = self.table.item(row, 2)
        response_item = self.table.item(row, 3)
        if not all([prompt_item, model_item, response_item]):
            return

        dialog = ResponseViewDialog(
            model_name=model_item.text(),
            prompt_text=prompt_item.text(),
            response_text=response_item.data(Qt.ItemDataRole.UserRole) or response_item.text(),
            parent=self,
        )
        dialog.exec()

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт JSON",
            str(db.get_app_dir() / "results.json"),
            "JSON (*.json)",
        )
        if not path:
            return
        rows = models.get_saved_results(self.search_edit.text().strip() or None)
        Path(path).write_text(
            __import__("json").dumps(rows, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        QMessageBox.information(self, "Экспорт", f"Сохранено записей: {len(rows)}")

    def export_markdown(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт Markdown",
            str(db.get_app_dir() / "results.md"),
            "Markdown (*.md)",
        )
        if not path:
            return
        rows = models.get_saved_results(self.search_edit.text().strip() or None)
        lines = ["# ChatList — история результатов", ""]
        for row in rows:
            lines.extend(
                [
                    f"## {row['model_name']} — {row['created_at']}",
                    "",
                    f"**Промт:** {row['prompt_text']}",
                    "",
                    normalize_response_text(row["response"]),
                    "",
                ]
            )
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        QMessageBox.information(self, "Экспорт", f"Сохранено записей: {len(rows)}")

    def load_results(self) -> None:
        search = self.search_edit.text().strip() or None
        rows = models.get_saved_results(search)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(row["created_at"]))
            self.table.setItem(row_index, 1, QTableWidgetItem(row["prompt_text"]))
            self.table.setItem(row_index, 2, QTableWidgetItem(row["model_name"]))

            response_item = QTableWidgetItem(make_response_preview(row["response"]))
            response_item.setData(Qt.ItemDataRole.UserRole, row["response"])
            response_item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            )
            if not is_error_response(row["response"]):
                response_item.setForeground(QColor("#2f855a"))
            self.table.setItem(row_index, 3, response_item)
            self.table.setItem(row_index, 4, QTableWidgetItem(str(row["id"])))

        self.table.resizeRowsToContents()
        self.table.setSortingEnabled(True)


class MainWindow(QMainWindow):
    COL_SELECT = 0
    COL_MODEL = 1
    COL_RESPONSE = 2

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ChatList — Сравнение ответов нейросетей")
        self.resize(1180, 760)
        self.worker: SendPromptWorker | None = None
        self._result_rows: list[dict[str, Any]] = []

        self._build_menu()
        self._build_ui()
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.set_status("Готово к работе")

        self.load_prompts()
        self.clear_results_table()

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        prompts_menu = menu_bar.addMenu("Промты")
        prompts_menu.addAction("Управление промтами", self.open_prompts_dialog)
        prompts_menu.addAction("Обновить список", self.load_prompts)
        prompts_menu.addAction("Новый запрос", self.on_new_request)

        models_menu = menu_bar.addMenu("Модели")
        models_menu.addAction("Управление моделями", self.open_models_dialog)

        results_menu = menu_bar.addMenu("Результаты")
        results_menu.addAction("История", self.open_history_dialog)
        results_menu.addAction("Сохранить выбранные", self.on_save_clicked)
        results_menu.addAction("Экспорт JSON", self.on_export_json)
        results_menu.addAction("Экспорт Markdown", self.on_export_markdown)

        settings_menu = menu_bar.addMenu("Настройки")
        settings_menu.addAction("Проверить .env", self.show_env_status)

    def _build_ui(self) -> None:
        prompt_group = QGroupBox("Промт")
        prompt_layout = QVBoxLayout()

        prompt_select_layout = QHBoxLayout()
        prompt_select_layout.addWidget(QLabel("Сохранённые:"))
        self.prompt_combo = QComboBox()
        self.prompts_button = QPushButton("Промты")
        self.refresh_prompts_button = QPushButton("Обновить")
        prompt_select_layout.addWidget(self.prompt_combo, stretch=1)
        prompt_select_layout.addWidget(self.prompts_button)
        prompt_select_layout.addWidget(self.refresh_prompts_button)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("Введите текст промта...")
        self.prompt_edit.setMinimumHeight(100)
        self.prompt_edit.setMaximumHeight(130)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Теги (необязательно, через запятую)")

        send_layout = QHBoxLayout()
        self.send_button = QPushButton("Отправить")
        self.send_button.setObjectName("primaryButton")
        send_layout.addWidget(self.send_button)
        send_layout.addStretch()

        prompt_layout.addLayout(prompt_select_layout)
        prompt_layout.addWidget(self.prompt_edit)
        prompt_layout.addWidget(self.tags_edit)
        prompt_layout.addLayout(send_layout)
        prompt_group.setLayout(prompt_layout)

        results_group = QGroupBox("Результаты")
        results_layout = QVBoxLayout()

        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(["Выбрать", "Модель", "Ответ"])
        self.results_table.verticalHeader().setVisible(True)
        self.results_table.horizontalHeader().setSectionResizeMode(
            self.COL_SELECT, QHeaderView.ResizeMode.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            self.COL_MODEL, QHeaderView.ResizeMode.ResizeToContents
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            self.COL_RESPONSE, QHeaderView.ResizeMode.Stretch
        )
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setWordWrap(True)
        self.results_table.setSortingEnabled(True)
        self.results_table.doubleClicked.connect(self.open_selected_response)

        actions_layout = QHBoxLayout()
        self.save_button = QPushButton("Сохранить выбранные")
        self.open_button = QPushButton("Открыть")
        self.open_button.setObjectName("openButton")
        self.clear_button = QPushButton("Очистить")
        self.models_button = QPushButton("Модели")
        self.history_button = QPushButton("История")

        actions_layout.addWidget(self.save_button)
        actions_layout.addWidget(self.open_button)
        actions_layout.addWidget(self.clear_button)
        actions_layout.addStretch()
        actions_layout.addWidget(self.models_button)
        actions_layout.addWidget(self.history_button)

        results_layout.addWidget(self.results_table, stretch=1)
        results_layout.addLayout(actions_layout)
        results_group.setLayout(results_layout)

        central = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(prompt_group)
        layout.addWidget(results_group, stretch=1)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.prompt_combo.currentIndexChanged.connect(self.on_prompt_selected)
        self.prompts_button.clicked.connect(self.open_prompts_dialog)
        self.refresh_prompts_button.clicked.connect(self.load_prompts)
        self.send_button.clicked.connect(self.on_send_clicked)
        self.save_button.clicked.connect(self.on_save_clicked)
        self.open_button.clicked.connect(self.open_selected_response)
        self.clear_button.clicked.connect(self.on_new_request)
        self.models_button.clicked.connect(self.open_models_dialog)
        self.history_button.clicked.connect(self.open_history_dialog)

    def set_status(self, message: str, success: bool = False) -> None:
        self.status_bar.showMessage(message)
        if success:
            self.status_bar.setStyleSheet("QStatusBar { color: #2f855a; font-weight: bold; }")
        else:
            self.status_bar.setStyleSheet("QStatusBar { color: #4a5568; }")

    def set_busy(self, busy: bool, message: str = "") -> None:
        self.send_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.open_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy)
        if message:
            self.set_status(message)

    def show_env_status(self) -> None:
        warnings = models.check_env_setup()
        QMessageBox.information(self, "Настройки .env", "\n".join(warnings))

    def load_prompts(self) -> None:
        current_data = self.prompt_combo.currentData()
        self.prompt_combo.blockSignals(True)
        self.prompt_combo.clear()
        self.prompt_combo.addItem("— новый промт —", None)

        for prompt in models.get_prompts():
            label = prompt["text"].replace("\n", " ")
            created = prompt.get("created_at", "")
            if created:
                label = f"{label[:60]}... ({created[:10]})" if len(label) > 60 else f"{label} ({created[:10]})"
            self.prompt_combo.addItem(label, prompt["id"])

        if current_data is not None:
            index = self.prompt_combo.findData(current_data)
            if index >= 0:
                self.prompt_combo.setCurrentIndex(index)

        self.prompt_combo.blockSignals(False)

    def on_prompt_selected(self, index: int) -> None:
        if index <= 0:
            return
        prompt_id = self.prompt_combo.itemData(index)
        if prompt_id is None:
            return
        prompt = models.get_prompt(int(prompt_id))
        if prompt:
            self.apply_prompt(prompt)

    def apply_prompt(self, prompt: dict[str, Any]) -> None:
        self.prompt_edit.setPlainText(prompt["text"])
        self.tags_edit.setText(prompt.get("tags") or "")
        index = self.prompt_combo.findData(prompt["id"])
        if index >= 0:
            self.prompt_combo.blockSignals(True)
            self.prompt_combo.setCurrentIndex(index)
            self.prompt_combo.blockSignals(False)

    def clear_results_table(self) -> None:
        self.results_table.setRowCount(0)
        self._result_rows.clear()

    def populate_results_table(self, rows: list[dict[str, Any]]) -> None:
        self._result_rows = rows
        self.results_table.setSortingEnabled(False)
        self.results_table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            checkbox = QCheckBox()
            checkbox.setChecked(bool(row.get("selected", False)))
            checkbox.stateChanged.connect(
                lambda state, idx=row_index: self.on_checkbox_changed(idx, state)
            )
            self.results_table.setCellWidget(row_index, self.COL_SELECT, checkbox)

            model_item = QTableWidgetItem(row["model_name"])
            model_font = QFont()
            model_font.setBold(True)
            model_item.setFont(model_font)
            self.results_table.setItem(row_index, self.COL_MODEL, model_item)

            full_response = row["response"]
            preview = make_response_preview(full_response)
            response_item = QTableWidgetItem(preview)
            response_item.setData(Qt.ItemDataRole.UserRole, full_response)
            response_item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            )
            if not is_error_response(full_response):
                response_item.setForeground(QColor("#2f855a"))
            self.results_table.setItem(row_index, self.COL_RESPONSE, response_item)

        self.results_table.resizeRowsToContents()
        for row_index in range(len(rows)):
            if self.results_table.rowHeight(row_index) < 88:
                self.results_table.setRowHeight(row_index, 88)
        self.results_table.setSortingEnabled(True)

    def _get_row_data(self, row_index: int) -> dict[str, Any] | None:
        if 0 <= row_index < len(self._result_rows):
            return self._result_rows[row_index]
        return None

    def open_selected_response(self) -> None:
        row_index = self.results_table.currentRow()
        if row_index < 0:
            QMessageBox.information(self, "Просмотр", "Выберите строку с ответом")
            return

        row_data = self._get_row_data(row_index)
        if row_data is None:
            return

        dialog = ResponseViewDialog(
            model_name=row_data["model_name"],
            prompt_text=self.prompt_edit.toPlainText().strip(),
            response_text=row_data["response"],
            parent=self,
        )
        dialog.exec()

    def on_checkbox_changed(self, index: int, state: int) -> None:
        models.update_temp_selection(index, state == int(Qt.CheckState.Checked))

    def on_send_clicked(self) -> None:
        prompt_text = self.prompt_edit.toPlainText().strip()
        if not prompt_text:
            QMessageBox.warning(self, "Промт", "Введите текст промта")
            return

        selected_prompt_id = self.prompt_combo.currentData()
        use_existing_prompt = selected_prompt_id is not None
        tags = self.tags_edit.text().strip() or None

        self.set_busy(True, "Отправка запросов...")
        self.worker = SendPromptWorker(
            prompt_text=prompt_text,
            prompt_id=int(selected_prompt_id) if use_existing_prompt else None,
            tags=tags,
            save_prompt_to_db=not use_existing_prompt,
        )
        self.worker.finished.connect(self.on_send_finished)
        self.worker.failed.connect(self.on_send_failed)
        self.worker.start()

    def on_send_finished(self, results: list, _error: object) -> None:
        self.populate_results_table(results)
        self.set_busy(False)
        self.set_status(f"Запросы завершены. Получено ответов: {len(results)}", success=True)
        if self.prompt_combo.currentData() is None:
            self.load_prompts()

    def on_send_failed(self, error: str) -> None:
        self.set_busy(False)
        self.set_status("Ошибка отправки")
        QMessageBox.warning(self, "Отправка", error)

    def on_save_clicked(self) -> None:
        for row_index in range(self.results_table.rowCount()):
            checkbox = self.results_table.cellWidget(row_index, self.COL_SELECT)
            if isinstance(checkbox, QCheckBox):
                models.update_temp_selection(row_index, checkbox.isChecked())

        saved_count, error = models.save_selected_results()
        if error:
            QMessageBox.warning(self, "Сохранение", error)
            return

        self.clear_results_table()
        self.set_status(f"Сохранено результатов: {saved_count}", success=True)
        QMessageBox.information(self, "Сохранение", f"Сохранено результатов: {saved_count}")

    def on_export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт JSON",
            str(db.get_app_dir() / "temp_results.json"),
            "JSON (*.json)",
        )
        if not path:
            return
        count = models.export_temp_results_json(Path(path), selected_only=False)
        if count == 0:
            QMessageBox.warning(self, "Экспорт", "Нет результатов для экспорта")
            return
        QMessageBox.information(self, "Экспорт", f"Экспортировано строк: {count}")

    def on_export_markdown(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт Markdown",
            str(db.get_app_dir() / "temp_results.md"),
            "Markdown (*.md)",
        )
        if not path:
            return
        count = models.export_temp_results_markdown(Path(path), selected_only=False)
        if count == 0:
            QMessageBox.warning(self, "Экспорт", "Нет результатов для экспорта")
            return
        QMessageBox.information(self, "Экспорт", f"Экспортировано строк: {count}")

    def on_new_request(self) -> None:
        models.clear_temp_results()
        self.prompt_edit.clear()
        self.tags_edit.clear()
        self.prompt_combo.setCurrentIndex(0)
        self.clear_results_table()
        self.set_status("Готово к работе")

    def open_prompts_dialog(self) -> None:
        dialog = PromptsDialog(self)
        dialog.exec()

    def open_models_dialog(self) -> None:
        dialog = ModelsDialog(self)
        dialog.exec()

    def open_history_dialog(self) -> None:
        dialog = ResultsDialog(self)
        dialog.exec()


def main() -> None:
    setup_logging()
    db.load_env()
    models.initialize()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()

    warnings = models.check_env_setup()
    if warnings:
        window.set_status(warnings[-1])

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
