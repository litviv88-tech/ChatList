"""Главное окно ChatList."""

from __future__ import annotations

import sys
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import db
import models


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

        self.refresh_button = QPushButton("Обновить")
        self.add_button = QPushButton("Добавить")
        self.toggle_button = QPushButton("Вкл/Выкл")
        self.delete_button = QPushButton("Удалить")

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.refresh_button)
        buttons_layout.addWidget(self.add_button)
        buttons_layout.addWidget(self.toggle_button)
        buttons_layout.addWidget(self.delete_button)
        buttons_layout.addStretch()

        layout = QVBoxLayout()
        layout.addWidget(self.table)
        layout.addLayout(buttons_layout)
        self.setLayout(layout)

        self.refresh_button.clicked.connect(self.load_models)
        self.add_button.clicked.connect(self.add_model)
        self.toggle_button.clicked.connect(self.toggle_active)
        self.delete_button.clicked.connect(self.delete_model)

        self.load_models()

    def load_models(self) -> None:
        rows = models.get_all_models()
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
        data = dialog.get_data()
        try:
            models.add_model(**data)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить модель:\n{exc}")
            return
        self.load_models()

    def toggle_active(self) -> None:
        model_id = self._selected_model_id()
        if model_id is None:
            QMessageBox.information(self, "Модели", "Выберите модель в таблице")
            return

        all_models = models.get_all_models()
        current = next((item for item in all_models if item["id"] == model_id), None)
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
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Новая модель")

        self.name_edit = QLineEdit()
        self.url_edit = QLineEdit("https://api.openai.com/v1/chat/completions")
        self.api_id_edit = QLineEdit("gpt-4o-mini")
        self.env_edit = QLineEdit("OPENAI_API_KEY")
        self.type_edit = QLineEdit("openai")
        self.active_checkbox = QCheckBox("Активна")
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
        self.resize(1000, 500)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск по промту, модели или ответу")
        self.search_button = QPushButton("Найти")
        self.refresh_button = QPushButton("Обновить")

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_edit)
        search_layout.addWidget(self.search_button)
        search_layout.addWidget(self.refresh_button)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Дата", "Промт", "Модель", "Ответ", "ID"]
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout = QVBoxLayout()
        layout.addLayout(search_layout)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.search_button.clicked.connect(self.load_results)
        self.refresh_button.clicked.connect(self.load_results)
        self.load_results()

    def load_results(self) -> None:
        search = self.search_edit.text().strip() or None
        rows = models.get_saved_results(search)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(row["created_at"]))
            self.table.setItem(row_index, 1, QTableWidgetItem(row["prompt_text"]))
            self.table.setItem(row_index, 2, QTableWidgetItem(row["model_name"]))
            self.table.setItem(row_index, 3, QTableWidgetItem(row["response"]))
            self.table.setItem(row_index, 4, QTableWidgetItem(str(row["id"])))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ChatList")
        self.resize(1100, 700)
        self.worker: SendPromptWorker | None = None

        self.prompt_combo = QComboBox()
        self.prompt_combo.setPlaceholderText("Выберите сохранённый промт")
        self.refresh_prompts_button = QPushButton("Обновить список")

        prompt_select_layout = QHBoxLayout()
        prompt_select_layout.addWidget(QLabel("Сохранённые промты:"))
        prompt_select_layout.addWidget(self.prompt_combo, stretch=1)
        prompt_select_layout.addWidget(self.refresh_prompts_button)

        self.prompt_edit = QTextEdit()
        self.prompt_edit.setPlaceholderText("Введите текст промта...")
        self.prompt_edit.setMinimumHeight(120)

        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("Теги (необязательно, через запятую)")

        self.send_button = QPushButton("Отправить")
        self.status_label = QLabel("Готово")

        top_buttons = QHBoxLayout()
        top_buttons.addWidget(self.send_button)
        top_buttons.addWidget(self.status_label, stretch=1)

        self.results_table = QTableWidget(0, 3)
        self.results_table.setHorizontalHeaderLabels(["Модель", "Ответ", "Выбрать"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.save_button = QPushButton("Сохранить выбранные")
        self.new_request_button = QPushButton("Новый запрос")
        self.models_button = QPushButton("Модели")
        self.history_button = QPushButton("История")

        bottom_buttons = QHBoxLayout()
        bottom_buttons.addWidget(self.save_button)
        bottom_buttons.addWidget(self.new_request_button)
        bottom_buttons.addStretch()
        bottom_buttons.addWidget(self.models_button)
        bottom_buttons.addWidget(self.history_button)

        central = QWidget()
        layout = QVBoxLayout()
        layout.addLayout(prompt_select_layout)
        layout.addWidget(self.prompt_edit)
        layout.addWidget(self.tags_edit)
        layout.addLayout(top_buttons)
        layout.addWidget(self.results_table, stretch=1)
        layout.addLayout(bottom_buttons)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.prompt_combo.currentIndexChanged.connect(self.on_prompt_selected)
        self.refresh_prompts_button.clicked.connect(self.load_prompts)
        self.send_button.clicked.connect(self.on_send_clicked)
        self.save_button.clicked.connect(self.on_save_clicked)
        self.new_request_button.clicked.connect(self.on_new_request)
        self.models_button.clicked.connect(self.open_models_dialog)
        self.history_button.clicked.connect(self.open_history_dialog)

        self.load_prompts()
        self.clear_results_table()

    def set_busy(self, busy: bool, message: str = "") -> None:
        self.send_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.new_request_button.setEnabled(not busy)
        if message:
            self.status_label.setText(message)

    def load_prompts(self) -> None:
        current_data = self.prompt_combo.currentData()
        self.prompt_combo.blockSignals(True)
        self.prompt_combo.clear()
        self.prompt_combo.addItem("— новый промт —", None)

        for prompt in models.get_prompts():
            label = prompt["text"].replace("\n", " ")
            if len(label) > 80:
                label = label[:77] + "..."
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
            self.prompt_edit.setPlainText(prompt["text"])
            self.tags_edit.setText(prompt.get("tags") or "")

    def clear_results_table(self) -> None:
        self.results_table.setRowCount(0)

    def populate_results_table(self, rows: list[dict[str, Any]]) -> None:
        self.results_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.results_table.setItem(row_index, 0, QTableWidgetItem(row["model_name"]))
            self.results_table.setItem(row_index, 1, QTableWidgetItem(row["response"]))

            checkbox = QCheckBox()
            checkbox.setChecked(bool(row.get("selected", False)))
            checkbox.stateChanged.connect(
                lambda state, idx=row_index: self.on_checkbox_changed(idx, state)
            )
            self.results_table.setCellWidget(row_index, 2, checkbox)

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
        self.set_busy(False, f"Получено ответов: {len(results)}")
        if self.prompt_combo.currentData() is None:
            self.load_prompts()

    def on_send_failed(self, error: str) -> None:
        self.set_busy(False, "Ошибка")
        QMessageBox.warning(self, "Отправка", error)

    def on_save_clicked(self) -> None:
        for row_index in range(self.results_table.rowCount()):
            checkbox = self.results_table.cellWidget(row_index, 2)
            if isinstance(checkbox, QCheckBox):
                models.update_temp_selection(row_index, checkbox.isChecked())

        saved_count, error = models.save_selected_results()
        if error:
            QMessageBox.warning(self, "Сохранение", error)
            return

        self.clear_results_table()
        self.status_label.setText(f"Сохранено результатов: {saved_count}")
        QMessageBox.information(self, "Сохранение", f"Сохранено результатов: {saved_count}")

    def on_new_request(self) -> None:
        models.clear_temp_results()
        self.prompt_edit.clear()
        self.tags_edit.clear()
        self.prompt_combo.setCurrentIndex(0)
        self.clear_results_table()
        self.status_label.setText("Готово")

    def open_models_dialog(self) -> None:
        dialog = ModelsDialog(self)
        dialog.exec()

    def open_history_dialog(self) -> None:
        dialog = ResultsDialog(self)
        dialog.exec()


def main() -> None:
    db.load_env()
    models.initialize()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
