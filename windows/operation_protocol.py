import html
import json
from datetime import datetime

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
)


class OperationProtocolWindow(QDialog):
    def __init__(self, parent, db, patient_id, records_table, load_records_list_callback, history_id=None, edit_record_id=None):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.history_id = history_id
        self.edit_record_id = edit_record_id
        self.records_table = records_table
        self.load_records_list = load_records_list_callback
        self.setWindowTitle("Протокол операции")
        self.resize(900, 650)
        self.create_widgets()

    def create_widgets(self):
        main_layout = QVBoxLayout(self)

        header_grid = QGridLayout()
        header_grid.setHorizontalSpacing(8)
        header_grid.addWidget(QLabel("Дата"), 0, 0)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        header_grid.addWidget(self.date_edit, 0, 1)

        header_grid.addWidget(QLabel("Время"), 0, 2)
        self.time_edit = QTimeEdit(QTime.currentTime())
        self.time_edit.setDisplayFormat("HH:mm")
        header_grid.addWidget(self.time_edit, 0, 3)

        title = QLabel("Протокол операции")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_grid.addWidget(title, 0, 4)
        header_grid.setColumnStretch(5, 1)
        main_layout.addLayout(header_grid)

        main_layout.addWidget(QLabel("Название операции"))
        self.operation_name_edit = QLineEdit()
        main_layout.addWidget(self.operation_name_edit)

        main_layout.addWidget(QLabel("Описание операции"))
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("На печати будет только введенный текст, без названия поля.")
        main_layout.addWidget(self.description_edit, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save_protocol)
        buttons.addWidget(save_button)
        main_layout.addLayout(buttons)

    def _selected_datetime(self):
        date = self.date_edit.date().toPython()
        time = self.time_edit.time().toPython()
        return datetime.combine(date, time)

    def _build_protocol_html(self, data):
        operation_name = html.escape(data.get("operation_name", ""))
        description = html.escape(data.get("description", "")).replace("\n", "<br>")

        parts = []
        if operation_name:
            parts.append(f"<p><b>Название операции:</b> {operation_name}</p>")
        if description:
            parts.append(f"<p>{description}</p>")

        parts.append(
            """
            <div style="margin-top: 10mm; text-align: right;">
                <div>Хирург Воловая А.А __________________</div>
                <div style="margin-top: 3mm;">Хирургическая медсестра __________________</div>
            </div>
            """
        )
        return "\n".join(parts)

    def save_protocol(self):
        operation_name = self.operation_name_edit.text().strip()
        description = self.description_edit.toPlainText().strip()

        if not operation_name and not description:
            QMessageBox.warning(self, "Ошибка", "Заполните название или описание операции.")
            return

        operation_dt = self._selected_datetime()
        data = {
            "date": operation_dt.strftime("%d.%m.%Y"),
            "time": operation_dt.strftime("%H:%M"),
            "operation_name": operation_name,
            "description": description,
        }
        html_record = self._build_protocol_html(data)

        if self.edit_record_id is not None:
            self.db.update_history(
                self.edit_record_id,
                "operation_protocol",
                html_record,
                "",
                "",
                json.dumps(data, ensure_ascii=False),
                visit_date=operation_dt.isoformat(),
                logical_history_id=self.history_id,
            )
            QMessageBox.information(self, "Успех", "Протокол операции обновлен.")
        else:
            self.db.add_history(
                self.patient_id,
                "operation_protocol",
                html_record,
                "",
                "",
                json.dumps(data, ensure_ascii=False),
                history_id=self.history_id,
                visit_date=operation_dt.isoformat(),
            )
            QMessageBox.information(self, "Успех", "Протокол операции сохранен.")
        self.load_records_list(self.records_table, self.patient_id)

        parent = self.parent()
        while parent is not None and not hasattr(parent, "_nav_back"):
            parent = parent.parent()
        if parent is not None and hasattr(parent, "_nav_back"):
            try:
                parent._nav_back()
                return
            except Exception:
                pass
        self.accept()

    def load_existing(self, history):
        if not history:
            return
        data = None
        try:
            data = json.loads(history[7] or "")
        except Exception:
            data = None
        if not isinstance(data, dict):
            data = {}
        self.operation_name_edit.setText(data.get("operation_name", ""))
        self.description_edit.setPlainText(data.get("description", ""))
        date_text = (data.get("date") or "").strip()
        if date_text:
            qdate = QDate.fromString(date_text, "dd.MM.yyyy")
            if qdate.isValid():
                self.date_edit.setDate(qdate)
        else:
            try:
                self.date_edit.setDate(QDate.fromString(history[2][:10], "yyyy-MM-dd"))
            except Exception:
                pass
        time_text = (data.get("time") or "").strip()
        if time_text:
            qtime = QTime.fromString(time_text, "HH:mm")
            if qtime.isValid():
                self.time_edit.setTime(qtime)
