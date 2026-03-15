from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QTabWidget, QWidget as QtWidget, QListWidget, QMessageBox, QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDialog
from PySide6.QtCore import Qt, QMarginsF, QDate
from PySide6.QtGui import QTextDocument, QPageLayout, QTextCursor, QTextCharFormat, QFont, QTextTableFormat
from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
from datetime import datetime
from .add_record import AddRecordWindow
from .edit_record import EditRecordWindow
from .primary_exam import PrimaryExamWindow
from widgets.date_input import DateInput
from widgets.time_input import TimeInput

class StationaryCardPage(QWidget):
    def __init__(self, parent, db, patient_id, patient, card_number):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.patient = patient
        # card_number is the logical history_id
        try:
            self.history_id = int(card_number)
        except Exception:
            self.history_id = None
        self.card_number = card_number
        # templates for appointments (shared within this window)
        self.appointment_templates = ["стол 15", "стол 9", "стол 14", "режим общий", "режим постельный"]
        # page title available via accessibleName
        self.setAccessibleName(f"Стационарная карта №{card_number}")
        self.resize(800, 600)
        self.create_widgets()

    def create_widgets(self):
        layout = QVBoxLayout(self)

        # Header
        dob_formatted = ""
        if self.patient[3]:
            d = QDate.fromString(self.patient[3], "yyyy-MM-dd")
            if d.isValid():
                dob_formatted = d.toString("dd.MM.yyyy")
            else:
                dob_formatted = self.patient[3]
        header_label = QLabel(f"Стационарная карта №{self.card_number} {self.patient[2] or ''} {self.patient[1]} {dob_formatted}")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)

        # Извлечь данные из последней истории
        histories = self.db.get_histories(self.patient_id)
        admission_date = ""
        admission_time = ""
        admission_diag = ""
        clinical_diag = ""
        outcome = ""
        
        # Ищем самую свежую запись с паспортными данными
        passport_record_text = None
        passport_data_obj = None # To store column values
        if histories:
            for h in histories:
                # h: (id, patient_id, visit_date, record_type, examination, diagnosis, treatment, notes, diag_adm, diag_clin, diag_com)
                if h[3] == "passport":
                    passport_record_text = h[4]
                    passport_data_obj = h
                    break
        
        # Use columns first, fallback to text parsing
        if passport_data_obj:
            admission_diag = passport_data_obj[8] or "" # diag_admission
            clinical_diag = passport_data_obj[9] or ""  # diag_clinical
            # comorbid? Usually from primary exam
            
            # Still parse outcome and dates from text as they aren't dedicated columns yet
            if passport_record_text:
                lines = passport_record_text.split('\n')
                for line in lines:
                    if line.startswith("Номер карты:"):
                        cnum = line.split(":", 1)[1].strip()
                        if cnum: self.card_number = cnum
                    elif line.startswith("Дата поступления:"):
                        parts = line.split(":", 1)[1].strip().split()
                        if len(parts) >= 1: admission_date = parts[0]
                        if len(parts) >= 2: admission_time = parts[1]
                    elif line.startswith("Исход:"):
                        outcome = line.split(":", 1)[1].strip()
        elif histories:
            # Fallback for old records without record_type "passport"
            curr = histories[0]
            lines = (curr[4] or "").split('\n')
            for line in lines:
                if line.startswith("Номер карты:"):
                    cnum = line.split(":", 1)[1].strip()
                    if cnum: self.card_number = cnum
                elif line.startswith("Дата поступления:"):
                    parts = line.split(":", 1)[1].strip().split()
                    if len(parts) >= 1: admission_date = parts[0]
                    if len(parts) >= 2: admission_time = parts[1]
                elif line.startswith("Диагноз при поступлении:"):
                    admission_diag = line.split(":", 1)[1].strip()
                elif line.startswith("Клинический диагноз:"):
                    clinical_diag = line.split(":", 1)[1].strip()
                elif line.startswith("Исход:"):
                    outcome = line.split(":", 1)[1].strip()

        # Update diagnoses from primary_exam if primary_exam exists (it has higher priority for clinical)
        for h in histories:
            if h[3] == "primary_exam":
                if h[9]: clinical_diag = h[9]
                break

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Header Update (now we have the real card number)
        header_label.setText(f"Стационарная карта №{self.card_number} {self.patient[2] or ''} {self.patient[1]} {dob_formatted}")
        self.setAccessibleName(f"Стационарная карта №{self.card_number}")

        # Tab 1: Паспортная часть
        passport_widget = QWidget()
        passport_layout = QVBoxLayout(passport_widget)

        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("Дата поступления:"))
        self.admission_date_input = DateInput()
        if admission_date:
            try:
                d = QDate.fromString(admission_date, "dd.MM.yyyy")
                if d.isValid():
                    self.admission_date_input.setDate(d)
                else:
                    self.admission_date_input.setText(admission_date)
            except Exception:
                self.admission_date_input.setText(admission_date)
        date_layout.addWidget(self.admission_date_input)
        passport_layout.addLayout(date_layout)

        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Время поступления:"))
        self.admission_time_entry = TimeInput()
        if admission_time:
            self.admission_time_entry.setText(admission_time)
        time_layout.addWidget(self.admission_time_entry)
        passport_layout.addLayout(time_layout)

        passport_layout.addWidget(QLabel("Диагноз при поступлении:"))
        self.admission_diag_entry = QLineEdit(admission_diag)
        passport_layout.addWidget(self.admission_diag_entry)

        passport_layout.addWidget(QLabel("Клинический диагноз:"))
        self.clinical_diag_entry = QLineEdit(clinical_diag)
        passport_layout.addWidget(self.clinical_diag_entry)

        passport_layout.addWidget(QLabel("Исход:"))
        self.outcome_text = QTextEdit()
        self.outcome_text.setPlainText(outcome)
        passport_layout.addWidget(self.outcome_text)

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save_passport_info)
        passport_layout.addWidget(save_button)

        self.tab_widget.addTab(passport_widget, "Паспортная часть")

        # Tab 2: Записи в историю болезни
        records_widget = QWidget()
        records_layout = QVBoxLayout(records_widget)

        records_layout.addWidget(QLabel("Записи в историю болезни:"))
        self.records_table = QTableWidget()
        self.records_table.setColumnCount(3)
        self.records_table.setHorizontalHeaderLabels(["Дата", "Название записи", "Текст"])
        self.records_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.records_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.records_table.verticalHeader().setDefaultSectionSize(20)
        self.records_table.setStyleSheet("QTableWidget::item { padding: 0px; margin: 0px; }")
        records_layout.addWidget(self.records_table)

        button_layout = QHBoxLayout()
        add_button = QPushButton("+")
        add_button.clicked.connect(self.add_record)
        button_layout.addWidget(add_button)

        edit_button = QPushButton("✏")
        edit_button.clicked.connect(self.edit_record)
        button_layout.addWidget(edit_button)

        delete_button = QPushButton("✕")
        delete_button.clicked.connect(self.delete_record)
        button_layout.addWidget(delete_button)

        print_button = QPushButton("🖨️")
        print_button.clicked.connect(self.print_record)
        button_layout.addWidget(print_button)

        records_layout.addLayout(button_layout)

        self.load_histories_list(self.records_table, self.patient_id)

        self.tab_widget.addTab(records_widget, "Записи в историю болезни")
        appointments_widget = QWidget()
        appointments_layout = QVBoxLayout(appointments_widget)

        appointments_layout.addWidget(QLabel("Назначения:"))
        self.appointments_table = QTableWidget()
        self.appointments_table.setColumnCount(5)
        self.appointments_table.setHorizontalHeaderLabels(["Назначение", "Способ", "Кратность", "Дата назначения", "Дата отмены"])
        self.appointments_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.appointments_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        appointments_layout.addWidget(self.appointments_table)

        button_layout = QHBoxLayout()
        add_button = QPushButton("+")
        add_button.clicked.connect(self.add_appointment)
        button_layout.addWidget(add_button)

        edit_button = QPushButton("✏")
        edit_button.clicked.connect(self.edit_appointment)
        button_layout.addWidget(edit_button)

        delete_button = QPushButton("✕")
        delete_button.clicked.connect(self.delete_appointment)
        button_layout.addWidget(delete_button)

        appointments_layout.addLayout(button_layout)

        self.tab_widget.addTab(appointments_widget, "Лист назначений")

        # Load appointments for the current (most recent) history
        try:
            self.load_appointments(self.patient_id)
        except Exception:
            pass

        # Tab 4: Диагностические исследования
        diagnostics_widget = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics_widget)

        diagnostics_layout.addWidget(QLabel("Исследования:"))
        self.diagnostics_table = QTableWidget()
        self.diagnostics_table.setColumnCount(3)
        self.diagnostics_table.setHorizontalHeaderLabels(["Дата исследования", "Название", "Результаты"])
        self.diagnostics_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.diagnostics_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        diagnostics_layout.addWidget(self.diagnostics_table)

        button_layout = QHBoxLayout()
        add_button = QPushButton("+")
        add_button.clicked.connect(self.add_diagnostic)
        button_layout.addWidget(add_button)

        edit_button = QPushButton("✏")
        edit_button.clicked.connect(self.edit_diagnostic)
        button_layout.addWidget(edit_button)

        delete_button = QPushButton("✕")
        delete_button.clicked.connect(self.delete_diagnostic)
        button_layout.addWidget(delete_button)

        diagnostics_layout.addLayout(button_layout)

        self.tab_widget.addTab(diagnostics_widget, "Диагностические исследования")

        # Load diagnostics
        try:
            self.load_diagnostics(self.patient_id)
        except Exception:
            pass

    def save_passport_info(self):
        # Build a passport section text and save as a history record
        card_number = getattr(self, 'card_number', '')
        passport_info = (
            f"Номер карты: {card_number}\n"
            f"Дата поступления: {self.admission_date_input.text().strip()} {self.admission_time_entry.text().strip()}\n"
            f"Диагноз при поступлении: {self.admission_diag_entry.text().strip()}\n"
            f"Клинический диагноз: {self.clinical_diag_entry.text().strip()}\n"
            f"Исход: {self.outcome_text.toPlainText().strip()}"
        )
        diag_admission = self.admission_diag_entry.text().strip()
        diag_clinical = self.clinical_diag_entry.text().strip()
        
        self.db.add_history(self.patient_id, "passport", passport_info, 
                            diagnosis=diag_admission, 
                            diag_admission=diag_admission,
                            diag_clinical=diag_clinical,
                            history_id=self.history_id)
        QMessageBox.information(self, "Успех", "Паспортная информация сохранена.")
        try:
            # refresh records list if present
            self.load_histories_list(self.records_table, self.patient_id)
        except Exception:
            pass
        # close page if parent provides navigation back
        parent = self.parent()
        if parent is not None and hasattr(parent, '_nav_back'):
            try:
                parent._nav_back()
            except Exception:
                pass

    def select_date(self, entry):
        from datetime import datetime
        entry.setText(datetime.now().strftime("%d.%m.%Y"))

    def add_appointment(self):
        # Open the Plan editor as a modal dialog (similar to PrimaryExamWindow)
        from .plan_window import PlanPage
        try:
            from PySide6.QtWidgets import QDialog, QVBoxLayout
            dlg = QDialog(self)
            dlg.setWindowTitle("План обследования и лечения")
            dlg.setModal(True)
            # ensure dialog is at least as large as the main/top-level window and centered
            try:
                main_win = self.window()
                if main_win is not None:
                    try:
                        mw_size = main_win.size()
                        dlg.setMinimumSize(mw_size.width(), mw_size.height())
                        dlg.resize(mw_size.width(), mw_size.height())
                    except Exception:
                        pass
            except Exception:
                pass
            layout = QVBoxLayout(dlg)
            # create the page after sizing the dialog so the page picks up correct parent size
            page = PlanPage(dlg, self.db, self.patient_id, self.records_table, self.load_histories_list, allowed_categories=['exam','drugs'])
            layout.addWidget(page)
            # center dialog over main window if possible
            try:
                main_win = self.window()
                if main_win is not None:
                    mg = main_win.geometry()
                    dx = mg.x() + max(0, (mg.width() - dlg.width()) // 2)
                    dy = mg.y() + max(0, (mg.height() - dlg.height()) // 2)
                    dlg.move(dx, dy)
            except Exception:
                pass
            # execute modally
            dlg.exec()
        except Exception:
            # fallback to previous behavior: push into navigation if available
            try:
                anc = self.parent()
                while anc is not None and not hasattr(anc, 'nav_push'):
                    try:
                        anc = anc.parent()
                    except Exception:
                        anc = None
                if anc is not None and hasattr(anc, 'nav_push'):
                    anc.nav_push(PlanPage(anc, self.db, self.patient_id, self.records_table, self.load_histories_list, allowed_categories=['exam','drugs']))
                    return
            except Exception:
                pass

    def load_appointments(self, patient_id):
        # load appointments for the most recent history of patient
        try:
            # Retrieve all appointments for the patient (across histories)
            appts = self.db.get_appointments_for_patient(patient_id)
            self.appointments_table.setRowCount(0)
            for a in appts:
                # a: id, history_id, name, method, freq, date_assign, date_cancel, created_at
                row = self.appointments_table.rowCount()
                self.appointments_table.insertRow(row)
                self.appointments_table.setItem(row, 0, QTableWidgetItem(a[2] or ""))
                self.appointments_table.setItem(row, 1, QTableWidgetItem(a[3] or ""))
                self.appointments_table.setItem(row, 2, QTableWidgetItem(a[4] or ""))
                self.appointments_table.setItem(row, 3, QTableWidgetItem(a[5] or ""))
                # date_cancel stored at index 6 in query (a[6])
                self.appointments_table.setItem(row, 4, QTableWidgetItem(a[6] or ""))
        except Exception:
            pass

    def edit_appointment(self):
        selected = self.appointments_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите назначение для редактирования.")
            return
        row = selected[0].row()
        from .appointment_editor import AppointmentEditorDialog
        current = {
            "name": self.appointments_table.item(row, 0).text() if self.appointments_table.item(row, 0) else "",
            "method": self.appointments_table.item(row, 1).text() if self.appointments_table.item(row, 1) else "",
            "freq": self.appointments_table.item(row, 2).text() if self.appointments_table.item(row, 2) else "",
            "date_assign": self.appointments_table.item(row, 3).text() if self.appointments_table.item(row, 3) else "",
            "date_cancel": self.appointments_table.item(row, 4).text() if self.appointments_table.item(row, 4) else "",
            "templates": self.appointment_templates,
        }
        def _on_edit(res):
            try:
                self.appointment_templates = res.get("templates", self.appointment_templates)
                self.appointments_table.setItem(row, 0, QTableWidgetItem(res.get("name", "")))
                self.appointments_table.setItem(row, 1, QTableWidgetItem(res.get("method", "")))
                self.appointments_table.setItem(row, 2, QTableWidgetItem(res.get("freq", "")))
                self.appointments_table.setItem(row, 3, QTableWidgetItem(res.get("date_assign", "")))
                self.appointments_table.setItem(row, 4, QTableWidgetItem(res.get("date_cancel", "")))
            except Exception:
                pass

        dlg_parent = self.parent() if self.parent() is not None else self
        dlg = AppointmentEditorDialog(dlg_parent, templates=self.appointment_templates, initial=current, done_callback=_on_edit)
        try:
            app_main = self.parent()
            app_main.nav_push(dlg)
        except Exception:
            try:
                dlg.show()
            except Exception:
                pass

    def delete_appointment(self):
        selected = self.appointments_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите назначение для удаления.")
            return
        reply = QMessageBox.question(self, "Подтверждение", "Удалить это назначение?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            row = selected[0].row()
            self.appointments_table.removeRow(row)

    def add_record(self):
        # Открываем окно выбора типа записи как всплывающее (popup)
        dialog = AddRecordWindow(self, self.db, self.patient_id, self.records_table, 
                                 self.open_primary_exam, self.load_histories_list, 
                                 history_id=self.history_id)
        dialog.exec()

    def open_primary_exam(self, patient_id, records_table):
        # Проверка: первичный осмотр может быть только один
        if self.db.has_primary_exam(patient_id):
            QMessageBox.warning(self, "Предупреждение", "Первичный осмотр для этого пациента уже существует. Его можно отредактировать в истории.")
            return

        try:
            app_main = self.parent()
            while app_main is not None and not hasattr(app_main, 'nav_push'):
                app_main = app_main.parent()
            if app_main is not None:
                app_main.nav_push(PrimaryExamWindow(app_main, self.db, patient_id, records_table, self.load_histories_list, history_id=self.history_id))
            else:
                raise Exception("No nav_push found")
        except Exception:
            dialog = PrimaryExamWindow(self, self.db, patient_id, records_table, self.load_histories_list, history_id=self.history_id)
            try:
                dialog.show()
            except Exception:
                pass

    def edit_record(self):
        # determine parent navigation stack
        app_main = self.parent()
        while app_main is not None and not hasattr(app_main, 'nav_push'):
            app_main = app_main.parent()

        if app_main is not None:
            app_main.nav_push(EditRecordWindow(app_main, self.db, self.patient_id, self.records_table, self.load_histories_list))
        else:
            dialog = EditRecordWindow(self, self.db, self.patient_id, self.records_table, self.load_histories_list)
            dialog.show()

    def delete_record(self):
        selected = self.records_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите запись для удаления.")
            return
        row = selected[0].row()
        record_id = self.records_table.item(row, 0).data(Qt.UserRole)
        
        reply = QMessageBox.question(self, "Подтверждение", "Удалить эту запись?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_history(record_id)
            QMessageBox.information(self, "Успех", "Запись удалена.")
            self.load_histories_list(self.records_table, self.patient_id)

    def print_record(self):
        selected = self.records_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите запись для печати.")
            return
        
        row = selected[0].row()
        record_id = self.records_table.item(row, 0).data(Qt.UserRole)
        history = self.db.get_history_by_id(record_id)
        
        if not history:
            QMessageBox.warning(self, "Ошибка", "Не удалось найти запись.")
            return
        
        html_content = history[4]  # examination содержит HTML
        record_type = history[3]
        title = ""
        if record_type == "primary_exam":
            title = "Первичный осмотр врача ГУ БЦГБ"
        elif record_type == "plan":
            title = "Лист назначений"
        elif record_type == "passport":
            title = "Паспортная часть"
        elif record_type == "diary":
            title = "Дневник"
        elif record_type == "history":
            title = "История болезни"
        else:
            title = "Другое"
        
        try:
            dt = datetime.fromisoformat(history[2])
            formatted_date = dt.strftime("%d.%m.%Y %H:%M")
            formatted_date_only = dt.strftime("%d.%m.%Y")
        except:
            formatted_date = history[2] or ""
        
        # Получаем информацию о пациенте
        patient_name = self.patient[2] if self.patient and len(self.patient) > 2 else "Неизвестно"
        
        # Создаем принтер и диалог предварительного просмотра
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageMargins(QMarginsF(5, 5, 5, 7), QPageLayout.Millimeter)
        
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Предварительный просмотр")
        
        def handle_paint(printer):
            document = QTextDocument()
            
            # Явно задаем шрифт и стили для документа
            document.setDefaultFont(QFont("Segoe UI", 9))
            document.setDefaultStyleSheet("""
                body { 
                    font-family: 'Segoe UI', Arial, sans-serif; 
                    font-size: 9pt; 
                    line-height: 1.2;
                }
                table { 
                    font-family: 'Segoe UI', Arial, sans-serif; 
                    font-size: 9pt; 
                }
            """)
            
            cursor = QTextCursor(document)
            
            # Формат для шапки
            header_format = QTextCharFormat()
            header_format.setFont(QFont("Segoe UI", 9))
            
            title_format = QTextCharFormat()
            title_format.setFont(QFont("Segoe UI", 10, QFont.Bold))
            
            # Добавляем дату слева
            cursor.insertText("Дата: " + formatted_date_only, header_format)
            
            # Добавляем несколько абзацев для сдвига вправо
            cursor.insertText("\n\n")
            
            # Добавляем название документа
            cursor.insertText(title, title_format)
            cursor.insertText("\n\n")
            
            # Горизонтальная линия
            line_format = QTextCharFormat()
            line_format.setFont(QFont("Segoe UI", 8))
            cursor.insertText("_" * 90 + "\n\n", line_format)
            
            # Основное содержимое
            cursor.insertHtml(html_content)
            
            document.print_(printer)
        
        preview.paintRequested.connect(handle_paint)
        preview.exec()

    def add_diagnostic(self):
        def _on_done(res):
            try:
                row = self.diagnostics_table.rowCount()
                self.diagnostics_table.insertRow(row)
                self.diagnostics_table.setItem(row, 0, QTableWidgetItem(res.get("date", "")))
                self.diagnostics_table.setItem(row, 1, QTableWidgetItem(res.get("name", "")))
                self.diagnostics_table.setItem(row, 2, QTableWidgetItem(res.get("results", "")))
            except Exception:
                pass

        dlg_parent = self.parent() if self.parent() is not None else self
        dialog = DiagnosticDialog(dlg_parent, done_callback=_on_done)
        try:
            app_main = self.parent()
            app_main.nav_push(dialog)
        except Exception:
            try:
                dialog.show()
            except Exception:
                pass

    def edit_diagnostic(self):
        selected = self.diagnostics_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите исследование для редактирования.")
            return
        row = selected[0].row()
        def _on_edit(res):
            try:
                self.diagnostics_table.setItem(row, 0, QTableWidgetItem(res.get("date", "")))
                self.diagnostics_table.setItem(row, 1, QTableWidgetItem(res.get("name", "")))
                self.diagnostics_table.setItem(row, 2, QTableWidgetItem(res.get("results", "")))
            except Exception:
                pass

        dlg_parent = self.parent() if self.parent() is not None else self
        dialog = DiagnosticDialog(dlg_parent, done_callback=_on_edit)
        dialog.date_edit.setText(self.diagnostics_table.item(row, 0).text())
        dialog.name_edit.setText(self.diagnostics_table.item(row, 1).text())
        dialog.results_edit.setText(self.diagnostics_table.item(row, 2).text())
        try:
            app_main = self.parent()
            app_main.nav_push(dialog)
        except Exception:
            try:
                dialog.show()
            except Exception:
                pass

    def delete_diagnostic(self):
        selected = self.diagnostics_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите исследование для удаления.")
            return
        reply = QMessageBox.question(self, "Подтверждение", "Удалить это исследование?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            row = selected[0].row()
            self.diagnostics_table.removeRow(row)

    def delete_history(self):
        reply1 = QMessageBox.question(self, "Подтверждение", "Вы уверены, что хотите удалить всю историю болезни этого пациента?",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply1 == QMessageBox.Yes:
            reply2 = QMessageBox.question(self, "Второе подтверждение", "Это действие необратимо. Подтвердить удаление всей истории?",
                                          QMessageBox.Yes | QMessageBox.No)
            if reply2 == QMessageBox.Yes:
                # Удалить все истории пациента
                histories = self.db.get_histories(self.patient_id)
                for h in histories:
                    self.db.delete_history(h[0])
                QMessageBox.information(self, "Успех", "История болезни удалена.")
                # navigate back if possible
                parent = self.parent()
                if parent is not None and hasattr(parent, '_nav_back'):
                    try:
                        parent._nav_back()
                    except Exception:
                        pass

    def load_histories_list(self, table, patient_id):
        table.setRowCount(0)
        all_histories = self.db.get_histories(patient_id)
        # Отфильтруем только записи, относящиеся к данной истории болезни (history_id)
        histories = [h for h in all_histories if h[11] == self.history_id]
        
        # Если история пустая (например, старые записи), но мы открыли карту, 
        # возможно стоит показать всё? Нет, лучше придерживаться новой логики.
        
        for h in histories:
            row = table.rowCount()
            table.insertRow(row)
            # Дата в формате ДД.ММ.ГГГГ
            try:
                dt = datetime.fromisoformat(h[2])
                date_str = dt.strftime("%d.%m.%Y")
                time_str = dt.strftime("%H:%M")
            except:
                date_str = h[2] or ""
                time_str = ""
            table.setItem(row, 0, QTableWidgetItem(date_str))
            # Название записи
            record_type = h[3]
            examination = h[4]
            # Store physical record ID in the first column's item
            table.item(row, 0).setData(Qt.UserRole, h[0])
            # If stored as HTML, convert to plain text to preserve newlines for preview
            try:
                doc = QTextDocument()
                doc.setHtml(examination)
                plain = doc.toPlainText()
            except Exception:
                plain = examination or ""

            if not record_type:
                # Fallback for old records without record_type
                if plain.startswith("Первичный осмотр"):
                    title = "Первичный осмотр"
                elif plain.startswith("План обследования") or plain.startswith("Лист назначений"):
                    title = "Лист назначений"
                elif plain.startswith("Паспортная часть"):
                    title = "Паспортная часть"
                elif plain.startswith("Дневник"):
                    title = "Дневник"
                else:
                    title = plain.split(':')[0] if ':' in plain else "Другое"
            elif record_type == "primary_exam":
                title = "Первичный осмотр"
            elif record_type == "plan":
                title = "Лист назначений"
            elif record_type == "passport":
                title = "Паспортная часть"
            elif record_type == "diary":
                title = "Дневник"
            elif record_type == "history":
                title = "История болезни"
            elif record_type == "other":
                title = plain.split(':')[0] if ':' in plain else "Другое"
            else:
                title = "Другое"
            table.setItem(row, 1, QTableWidgetItem(title))
            # For passport entries, only show text after the 'Номер карты:' line
            if title == "Паспортная часть":
                lines = plain.split('\n')
                # find the line with 'Номер карты:' and take everything after it
                preview_lines = []
                found = False
                for i, ln in enumerate(lines):
                    if ln.strip().startswith("Номер карты:"):
                        # take following lines (after this one)
                        preview_lines = lines[i+1:]
                        found = True
                        break
                if not found:
                    # fallback: don't show passport text in preview
                    preview_text = ""
                else:
                    preview_text = "\n".join(preview_lines).strip()
            else:
                preview_text = plain
            preview = preview_text[:200]
            table.setItem(row, 2, QTableWidgetItem(preview))

# Removed on_record_item_changed method as time editing is disabled


# Old simple AppointmentDialog replaced by `AppointmentEditorDialog` in windows/appointment_editor.py


class DiagnosticDialog(QDialog):
    def __init__(self, parent, done_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Исследование")
        self.setModal(True)
        self.done_callback = done_callback
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Дата исследования:"))
        self.date_edit = QLineEdit()
        layout.addWidget(self.date_edit)

        layout.addWidget(QLabel("Название:"))
        self.name_edit = QLineEdit()
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("Результаты:"))
        self.results_edit = QTextEdit()
        layout.addWidget(self.results_edit)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        ok = QPushButton("Сохранить")
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._on_ok)

    def _on_ok(self):
        res = {
            "date": self.date,
            "name": self.name,
            "results": self.results,
        }
        try:
            if self.done_callback and callable(self.done_callback):
                self.done_callback(res)
        except Exception:
            pass
        parent = self.parent()
        if parent is not None and hasattr(parent, '_nav_back'):
            try:
                parent._nav_back()
                return
            except Exception:
                pass
        self.accept()

    @property
    def date(self):
        return self.date_edit.text().strip()

    @property
    def name(self):
        return self.name_edit.text().strip()

    @property
    def results(self):
        return self.results_edit.toPlainText().strip()