from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QMessageBox,
    QDateEdit,
    QTimeEdit,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QInputDialog,
)
from PySide6.QtCore import QDate, QTime, QLocale


class PlanPage(QWidget):
    def __init__(self, parent, db, patient_id, records_table, load_records_list_callback, allowed_categories=None, history_id=None):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.history_id = history_id
        self.records_table = records_table
        self.load_records_list = load_records_list_callback
        # allowed_categories: list of category keys to show (e.g. ['exam','drugs'])
        # if None, show all
        self.allowed_categories = set(allowed_categories) if allowed_categories is not None else None

        # This is a page that will be shown inside main window's navigation stack
        # setAccessibleName used for debugging/title purposes
        self.setAccessibleName("План обследования и лечения")
        # Make dialog at least as large as parent (main window)
        if parent is not None:
            try:
                psize = parent.size()
                # set minimum size and resize to match parent
                self.setMinimumSize(psize.width(), psize.height())
                self.resize(psize.width(), psize.height())
            except Exception:
                pass
        # templates preserved per category
        self.template_categories = {
            "stol": ["стол 15", "стол 9", "стол 14", "режим общий", "режим постельный"],
            "exam": [
                "Общий анализ мочи",
                "Биохимический анализ крови",
                "Флюорография",
                "Маммография",
                "ЭКГ",
                "УЗИ органов брюшной полости",
                "Рентген грудной клетки",
                "Анализ кала",
            ],
            "drugs": ["анальгетики", "антибиотикотерапия", "физиолечение", "спазмолитики", "витамины"],
            "lfk": ["ЛФК", "массаж", "лечебная физкультура"],
        }

        main_layout = QVBoxLayout(self)

        # header: date/time
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Дата:"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setLocale(QLocale(QLocale.Russian))
        header_layout.addWidget(self.date_edit)
        header_layout.addWidget(QLabel("Время:"))
        self.time_edit = QTimeEdit(QTime.currentTime())
        header_layout.addWidget(self.time_edit)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Appointments table + right-side buttons
        appoint_group = QGroupBox("Лист назначений")
        appoint_layout = QHBoxLayout(appoint_group)

        self.appointments_table = QTableWidget(0, 7)
        self.appointments_table.setHorizontalHeaderLabels([
            "Назначение", "Способ", "Кратность", "Дата назн.", "Врач", "Дата отм.", "Врач"
        ])
        self.appointments_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        appoint_layout.addWidget(self.appointments_table)

        buttons_panel = QVBoxLayout()

        # Add category buttons according to allowed_categories
        def add_cat_button(key, label):
            btn = QPushButton(label)
            btn.clicked.connect(lambda: self.open_templates(key))
            buttons_panel.addWidget(btn)

        if self.allowed_categories is None or 'stol' in self.allowed_categories:
            add_cat_button('stol', 'Стол, режим')
        if self.allowed_categories is None or 'exam' in self.allowed_categories:
            add_cat_button('exam', 'Обследования')
        if self.allowed_categories is None or 'drugs' in self.allowed_categories:
            add_cat_button('drugs', 'Препараты')
        if self.allowed_categories is None or 'lfk' in self.allowed_categories:
            add_cat_button('lfk', 'ЛФК, массаж')

        edit_btn = QPushButton("Изм.")
        edit_btn.clicked.connect(self.edit_selected)
        buttons_panel.addWidget(edit_btn)

        del_btn = QPushButton("Удалить")
        del_btn.clicked.connect(self.delete_selected)
        buttons_panel.addWidget(del_btn)

        buttons_panel.addStretch()

        print_btn = QPushButton("Печать")
        print_btn.clicked.connect(self.print_table)
        buttons_panel.addWidget(print_btn)
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self.save_plan)
        buttons_panel.addWidget(save_btn)

        appoint_layout.addLayout(buttons_panel)
        main_layout.addWidget(appoint_group)

        # bottom buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        cancel_button = QPushButton("Назад")
        cancel_button.clicked.connect(self.close_page)
        bottom_layout.addWidget(cancel_button)
        save_button = QPushButton("Готово")
        save_button.clicked.connect(self.save_plan)
        bottom_layout.addWidget(save_button)
        main_layout.addLayout(bottom_layout)

    
    def add_empty_row(self):
        row = self.appointments_table.rowCount()
        self.appointments_table.insertRow(row)
        # default date = selected date
        self.appointments_table.setItem(row, 3, QTableWidgetItem(self.date_edit.date().toString("dd.MM.yyyy")))

    def insert_template(self, name: str):
        # kept for compatibility: insert simple named row
        self._insert_row_with_name(name)

    def open_templates(self, category: str):
        from .appointment_editor import AppointmentEditorDialog
        templates = self.template_categories.get(category, [])

        def _on_done(res):
            try:
                self.template_categories[category] = res.get("templates", templates)
                # res may contain multiple items ("items"). Insert each as its own row.
                items = res.get("items") or ([res.get("name")] if res.get("name") else [])
                for nm in items:
                    data = {
                        "name": nm,
                        "method": res.get("method", ""),
                        "freq": res.get("freq", ""),
                        "date_assign": res.get("date_assign", ""),
                        "date_cancel": res.get("date_cancel", ""),
                    }
                    self._insert_row_with_data(data)
            except Exception:
                pass

        dlg_parent = self.parent() if self.parent() is not None else self
        dlg = AppointmentEditorDialog(dlg_parent, templates=templates, done_callback=_on_done, category=category)
        try:
            app_main = self.parent()
            app_main.nav_push(dlg)
        except Exception:
            try:
                dlg.show()
            except Exception:
                pass

    def _insert_row_with_name(self, name: str):
        row = self.appointments_table.rowCount()
        self.appointments_table.insertRow(row)
        self.appointments_table.setItem(row, 0, QTableWidgetItem(name))
        # default date = selected date
        self.appointments_table.setItem(row, 3, QTableWidgetItem(self.date_edit.date().toString("dd.MM.yyyy")))
        # default doctor left empty for now

    def edit_selected(self):
        row = self.appointments_table.currentRow()
        if row < 0:
            return
        from .appointment_editor import AppointmentEditorDialog
        # collect current data
        current = {}
        def _get(col):
            it = self.appointments_table.item(row, col)
            return it.text() if it else ""
        current["name"] = _get(0)
        current["method"] = _get(1)
        current["freq"] = _get(2)
        current["date_assign"] = _get(3)
        current["date_cancel"] = _get(5)
        # provide combined templates across categories for editing
        combined_templates = []
        for v in self.template_categories.values():
            combined_templates.extend(v)
        def _on_edit(res):
            try:
                self._update_row_with_data(row, res)
            except Exception:
                pass

        dlg_parent = self.parent() if self.parent() is not None else self
        dlg = AppointmentEditorDialog(dlg_parent, templates=combined_templates, initial=current, done_callback=_on_edit)
        try:
            app_main = self.parent()
            app_main.nav_push(dlg)
        except Exception:
            try:
                dlg.show()
            except Exception:
                pass

    def _insert_row_with_data(self, data: dict):
        row = self.appointments_table.rowCount()
        self.appointments_table.insertRow(row)
        self._update_row_with_data(row, data)

    def _update_row_with_data(self, row: int, data: dict):
        self.appointments_table.setItem(row, 0, QTableWidgetItem(data.get("name", "")))
        self.appointments_table.setItem(row, 1, QTableWidgetItem(data.get("method", "")))
        self.appointments_table.setItem(row, 2, QTableWidgetItem(data.get("freq", "")))
        self.appointments_table.setItem(row, 3, QTableWidgetItem(data.get("date_assign", "")))
        # primary doctor
        self.appointments_table.setItem(row, 4, QTableWidgetItem("") )
        self.appointments_table.setItem(row, 5, QTableWidgetItem(data.get("date_cancel", "")))
        # secondary doctor
        self.appointments_table.setItem(row, 6, QTableWidgetItem("") )

    def delete_selected(self):
        row = self.appointments_table.currentRow()
        if row >= 0:
            self.appointments_table.removeRow(row)

    def print_table(self):
        QMessageBox.information(self, "Печать", "Печать назначений (заглушка).")

    def save_plan(self):
        date = self.date_edit.date().toString("dd.MM.yyyy")
        time = self.time_edit.time().toString("HH:mm")

        lines = []
        # lines.append(f"Лист назначений {date} {time}")  # Remove, title from record_type
        lines.append("")

        # Use table rows to build the plan
        rows = self.appointments_table.rowCount()
        if rows > 0:
            lines.append("План назначений:")
            for i in range(rows):
                name_item = self.appointments_table.item(i, 0)
                date_item = self.appointments_table.item(i, 3)
                doctor_item = self.appointments_table.item(i, 4)
                name = name_item.text() if name_item else ""
                date_item_text = date_item.text() if date_item else ""
                doctor = doctor_item.text() if doctor_item else ""
                parts = [f"{i+1}. {name}"]
                if date_item_text:
                    parts.append(f"({date_item_text})")
                if doctor:
                    parts.append(f"{doctor}")
                lines.append(" ".join(parts))
            lines.append("")

        record = "\n".join(lines)

        # Create or update a history entry for the plan and persist individual appointments
        history_id = None
        try:
            # look for an existing 'plan' history for this patient
            histories = self.db.get_histories(self.patient_id)
            for h in histories:
                if h[3] == "plan":  # record_type
                    history_id = h[0]
                    break
        except Exception:
            histories = []

        try:
            if history_id is None:
                history_id = self.db.add_history(self.patient_id, "plan", record, "", "", "", history_id=self.history_id)
            else:
                # update existing plan history instead of creating a new one
                try:
                    self.db.update_history(history_id, "plan", record, "", "", "", logical_history_id=self.history_id)
                except Exception:
                    pass
        except Exception:
            history_id = None

        # Persist each appointment row into appointments table tied to history_id
        try:
            if history_id is not None:
                try:
                    self.db.delete_appointments_for_history(history_id)
                except Exception:
                    pass
            rows = self.appointments_table.rowCount()
            for i in range(rows):
                name_item = self.appointments_table.item(i, 0)
                method_item = self.appointments_table.item(i, 1)
                freq_item = self.appointments_table.item(i, 2)
                date_item = self.appointments_table.item(i, 3)
                cancel_item = self.appointments_table.item(i, 5)
                name = name_item.text() if name_item else ""
                method = method_item.text() if method_item else ""
                freq = freq_item.text() if freq_item else ""
                date_assign = date_item.text() if date_item else ""
                date_cancel = cancel_item.text() if cancel_item else ""
                if history_id is not None and name:
                    try:
                        self.db.add_appointment(history_id, name, method, freq, date_assign, date_cancel)
                    except Exception:
                        pass
        except Exception:
            pass

        QMessageBox.information(self, "Успех", "План обследования и лечения сохранен.")
        try:
            self.load_records_list(self.records_table, self.patient_id)
        except Exception:
            pass
        # notify nearest ancestor (e.g., StationaryCardPage) to reload appointments table
        try:
            anc = self.parent()
            while anc is not None and not hasattr(anc, 'load_appointments'):
                try:
                    anc = anc.parent()
                except Exception:
                    anc = None
            if anc is not None and hasattr(anc, 'load_appointments'):
                try:
                    anc.load_appointments(self.patient_id)
                except Exception:
                    pass
        except Exception:
            pass
        self.close_page()

    def close_page(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, '_nav_back'):
            try:
                parent._nav_back()
                return
            except Exception:
                pass
        # If this page is hosted inside a QDialog, close that dialog
        try:
            from PySide6.QtWidgets import QDialog
            if isinstance(parent, QDialog):
                try:
                    parent.close()
                    return
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.hide()
        except Exception:
            pass

