"""Тестовая программа для просмотра и редактирования SQLite-базы."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui_helpers import APP_STYLESHEET

PAGE_SIZE = 20


class SQLiteRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self.conn.close()

    def list_tables(self) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
        return [row["name"] for row in rows]

    def get_columns(self, table_name: str) -> list[str]:
        rows = self.conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        return [row["name"] for row in rows]

    def count_rows(self, table_name: str) -> int:
        row = self.conn.execute(f'SELECT COUNT(*) AS cnt FROM "{table_name}"').fetchone()
        return int(row["cnt"])

    def fetch_page(self, table_name: str, page: int, page_size: int) -> list[dict[str, Any]]:
        offset = page * page_size
        rows = self.conn.execute(
            f'SELECT rowid AS __rowid__, * FROM "{table_name}" LIMIT ? OFFSET ?',
            (page_size, offset),
        ).fetchall()
        return [dict(row) for row in rows]

    def insert_row(self, table_name: str, values: dict[str, Any]) -> None:
        columns = [name for name in values if name != "__rowid__"]
        if not columns:
            raise ValueError("Нет данных для добавления")
        placeholders = ", ".join("?" for _ in columns)
        column_names = ", ".join(f'"{name}"' for name in columns)
        params = [values[name] for name in columns]
        self.conn.execute(
            f'INSERT INTO "{table_name}" ({column_names}) VALUES ({placeholders})',
            params,
        )
        self.conn.commit()

    def update_row(self, table_name: str, rowid: int, values: dict[str, Any]) -> None:
        columns = [name for name in values if name != "__rowid__"]
        if not columns:
            raise ValueError("Нет данных для обновления")
        assignments = ", ".join(f'"{name}" = ?' for name in columns)
        params = [values[name] for name in columns] + [rowid]
        self.conn.execute(
            f'UPDATE "{table_name}" SET {assignments} WHERE rowid = ?',
            params,
        )
        self.conn.commit()

    def delete_row(self, table_name: str, rowid: int) -> None:
        self.conn.execute(f'DELETE FROM "{table_name}" WHERE rowid = ?', (rowid,))
        self.conn.commit()


class RowEditDialog(QDialog):
    def __init__(
        self,
        columns: list[str],
        values: dict[str, Any] | None = None,
        title: str = "Запись",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.fields: dict[str, QLineEdit] = {}

        form = QFormLayout()
        for column in columns:
            if column == "__rowid__":
                continue
            edit = QLineEdit()
            if values and column in values and values[column] is not None:
                edit.setText(str(values[column]))
            self.fields[column] = edit
            form.addRow(column, edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def get_values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for column, edit in self.fields.items():
            text = edit.text()
            result[column] = text if text != "" else None
        return result


class TableCrudWindow(QMainWindow):
    def __init__(
        self,
        repo: SQLiteRepository,
        table_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repo = repo
        self.table_name = table_name
        self.current_page = 0
        self.page_size = PAGE_SIZE
        self.columns: list[str] = []

        self.setWindowTitle(f"Таблица: {table_name}")
        self.resize(980, 620)

        self.table = QTableWidget(0, 0)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(self.update_selected_row)

        self.page_label = QLabel()
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.valueChanged.connect(self.on_page_spin_changed)

        self.page_size_spin = QSpinBox()
        self.page_size_spin.setRange(5, 200)
        self.page_size_spin.setValue(PAGE_SIZE)
        self.page_size_spin.valueChanged.connect(self.on_page_size_changed)

        self.prev_button = QPushButton("← Назад")
        self.next_button = QPushButton("Вперёд →")
        self.refresh_button = QPushButton("Обновить")

        self.create_button = QPushButton("Создать")
        self.read_button = QPushButton("Просмотр")
        self.update_button = QPushButton("Изменить")
        self.delete_button = QPushButton("Удалить")

        self.create_button.setObjectName("primaryButton")
        self.delete_button.setStyleSheet("QPushButton { color: #c53030; }")

        pagination_layout = QHBoxLayout()
        pagination_layout.addWidget(self.prev_button)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addWidget(QLabel("Страница"))
        pagination_layout.addWidget(self.page_spin)
        pagination_layout.addWidget(QLabel("Размер"))
        pagination_layout.addWidget(self.page_size_spin)
        pagination_layout.addWidget(self.next_button)
        pagination_layout.addWidget(self.refresh_button)
        pagination_layout.addStretch()

        crud_layout = QHBoxLayout()
        crud_layout.addWidget(self.create_button)
        crud_layout.addWidget(self.read_button)
        crud_layout.addWidget(self.update_button)
        crud_layout.addWidget(self.delete_button)
        crud_layout.addStretch()

        central = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(pagination_layout)
        layout.addLayout(crud_layout)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.prev_button.clicked.connect(self.prev_page)
        self.next_button.clicked.connect(self.next_page)
        self.refresh_button.clicked.connect(self.load_page)
        self.create_button.clicked.connect(self.create_row)
        self.read_button.clicked.connect(self.read_selected_row)
        self.update_button.clicked.connect(self.update_selected_row)
        self.delete_button.clicked.connect(self.delete_selected_row)

        self.load_page()

    def total_pages(self) -> int:
        total_rows = self.repo.count_rows(self.table_name)
        if total_rows == 0:
            return 1
        return (total_rows + self.page_size - 1) // self.page_size

    def load_page(self) -> None:
        self.columns = self.repo.get_columns(self.table_name)
        display_columns = ["__rowid__", *self.columns]
        rows = self.repo.fetch_page(self.table_name, self.current_page, self.page_size)
        total_rows = self.repo.count_rows(self.table_name)
        pages = self.total_pages()

        if self.current_page >= pages:
            self.current_page = max(pages - 1, 0)

        self.table.setColumnCount(len(display_columns))
        self.table.setHorizontalHeaderLabels(display_columns)
        self.table.setRowCount(len(rows))

        for row_index, row in enumerate(rows):
            for col_index, column in enumerate(display_columns):
                value = row.get(column, "")
                self.table.setItem(
                    row_index,
                    col_index,
                    QTableWidgetItem("" if value is None else str(value)),
                )

        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(pages, 1))
        self.page_spin.setValue(self.current_page + 1)
        self.page_spin.blockSignals(False)

        self.page_label.setText(f"Страница {self.current_page + 1} из {pages}")
        self.prev_button.setEnabled(self.current_page > 0)
        self.next_button.setEnabled(self.current_page < pages - 1)
        self.status_bar.showMessage(
            f"Таблица {self.table_name}: {total_rows} записей, показано {len(rows)}"
        )

    def on_page_spin_changed(self, value: int) -> None:
        self.current_page = value - 1
        self.load_page()

    def on_page_size_changed(self, value: int) -> None:
        self.page_size = value
        self.current_page = 0
        self.load_page()

    def prev_page(self) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self.load_page()

    def next_page(self) -> None:
        if self.current_page < self.total_pages() - 1:
            self.current_page += 1
            self.load_page()

    def _selected_row_data(self) -> dict[str, Any] | None:
        row_index = self.table.currentRow()
        if row_index < 0:
            return None

        data: dict[str, Any] = {}
        for col_index in range(self.table.columnCount()):
            header = self.table.horizontalHeaderItem(col_index)
            item = self.table.item(row_index, col_index)
            if header is None:
                continue
            column = header.text()
            data[column] = item.text() if item else None
        return data

    def create_row(self) -> None:
        dialog = RowEditDialog(self.columns, title="Создать запись", parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.repo.insert_row(self.table_name, dialog.get_values())
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать запись:\n{exc}")
            return
        self.load_page()

    def read_selected_row(self) -> None:
        row_data = self._selected_row_data()
        if row_data is None:
            QMessageBox.information(self, "Просмотр", "Выберите строку в таблице")
            return

        dialog = RowEditDialog(
            self.columns,
            values=row_data,
            title="Просмотр записи",
            parent=self,
        )
        for edit in dialog.fields.values():
            edit.setReadOnly(True)
        dialog.exec()

    def update_selected_row(self) -> None:
        row_data = self._selected_row_data()
        if row_data is None:
            QMessageBox.information(self, "Изменение", "Выберите строку в таблице")
            return

        rowid = int(row_data["__rowid__"])
        dialog = RowEditDialog(
            self.columns,
            values=row_data,
            title="Изменить запись",
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.repo.update_row(self.table_name, rowid, dialog.get_values())
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось изменить запись:\n{exc}")
            return
        self.load_page()

    def delete_selected_row(self) -> None:
        row_data = self._selected_row_data()
        if row_data is None:
            QMessageBox.information(self, "Удаление", "Выберите строку в таблице")
            return

        answer = QMessageBox.question(
            self,
            "Удаление",
            f"Удалить запись rowid={row_data['__rowid__']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.repo.delete_row(self.table_name, int(row_data["__rowid__"]))
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить запись:\n{exc}")
            return
        self.load_page()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Test DB — просмотр SQLite")
        self.resize(640, 480)
        self.repo: SQLiteRepository | None = None
        self.table_windows: list[TableCrudWindow] = []

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Путь к файлу SQLite...")
        default_db = Path(__file__).resolve().parent / "chatlist.db"
        if default_db.exists():
            self.path_edit.setText(str(default_db))

        self.browse_button = QPushButton("Выбрать файл")
        self.load_button = QPushButton("Загрузить")
        self.open_button = QPushButton("Открыть")
        self.open_button.setObjectName("primaryButton")
        self.open_button.setEnabled(False)

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_edit, stretch=1)
        path_layout.addWidget(self.browse_button)
        path_layout.addWidget(self.load_button)

        self.tables_list = QListWidget()

        file_group = QGroupBox("Файл базы данных")
        file_layout = QVBoxLayout()
        file_layout.addLayout(path_layout)
        file_group.setLayout(file_layout)

        tables_group = QGroupBox("Таблицы")
        tables_layout = QVBoxLayout()
        tables_layout.addWidget(self.tables_list)
        tables_layout.addWidget(self.open_button)
        tables_group.setLayout(tables_layout)

        central = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(file_group)
        layout.addWidget(tables_group, stretch=1)
        central.setLayout(layout)
        self.setCentralWidget(central)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.set_status("Выберите файл SQLite")

        self.browse_button.clicked.connect(self.browse_file)
        self.load_button.clicked.connect(self.load_database)
        self.open_button.clicked.connect(self.open_selected_table)
        self.tables_list.itemDoubleClicked.connect(self.open_selected_table)

        if default_db.exists():
            self.load_database()

    def set_status(self, message: str) -> None:
        self.status_bar.showMessage(message)

    def browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите SQLite файл",
            str(Path(__file__).resolve().parent),
            "SQLite (*.db *.sqlite *.sqlite3);;All files (*.*)",
        )
        if path:
            self.path_edit.setText(path)
            self.load_database()

    def load_database(self) -> None:
        db_path = Path(self.path_edit.text().strip())
        if not db_path.exists():
            QMessageBox.warning(self, "Файл", "Файл базы данных не найден")
            return

        if self.repo is not None:
            self.repo.close()

        try:
            self.repo = SQLiteRepository(db_path)
            tables = self.repo.list_tables()
        except sqlite3.Error as exc:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть базу:\n{exc}")
            self.repo = None
            self.open_button.setEnabled(False)
            return

        self.tables_list.clear()
        self.tables_list.addItems(tables)
        self.open_button.setEnabled(bool(tables))
        self.set_status(f"Загружено таблиц: {len(tables)} — {db_path.name}")

    def open_selected_table(self) -> None:
        if self.repo is None:
            QMessageBox.warning(self, "База", "Сначала загрузите файл SQLite")
            return

        item = self.tables_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Таблицы", "Выберите таблицу из списка")
            return

        window = TableCrudWindow(self.repo, item.text(), parent=self)
        window.show()
        self.table_windows.append(window)


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
