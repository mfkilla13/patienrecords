import html
import json
import uuid
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QTabWidget, QWidget as QtWidget, QListWidget, QListWidgetItem, QMessageBox, QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDialog, QComboBox
from PySide6.QtCore import Qt, QMarginsF, QDate, QSizeF
from PySide6.QtGui import QTextDocument, QPageLayout, QPageSize, QTextCursor, QTextCharFormat, QFont, QTextTableFormat, QTextBlockFormat
from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
from datetime import datetime
from .add_record import AddRecordWindow
from .edit_record import EditRecordWindow
from .primary_exam import PrimaryExamWindow
from widgets.date_input import DateInput
from widgets.time_input import TimeInput
from .diary import render_diary_html

def _parse_ru_date(value):
    value = (value or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:10], fmt)
        except Exception:
            pass
    return None

def _html_plain(value):
    try:
        doc = QTextDocument()
        doc.setHtml(value or "")
        return doc.toPlainText().strip()
    except Exception:
        return value or ""

def _extract_after_label(text, label):
    for line in (text or "").splitlines():
        if line.strip().startswith(label):
            return line.split(":", 1)[1].strip() if ":" in line else ""
    return ""

def _format_ru_full_date(value):
    dt = _parse_ru_date(value)
    if not dt:
        dt = datetime.now()
    months = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    return f"«{dt.day:02d}» {months[dt.month - 1]} {dt.year} г."


def _print_document_without_page_numbers(printer, document):
    try:
        cloned = document.clone()

        src_block = document.firstBlock()
        dst_block = cloned.firstBlock()
        while src_block.isValid() and dst_block.isValid():
            if src_block.layout() is not None and dst_block.layout() is not None:
                dst_block.layout().setFormats(src_block.layout().formats())
            src_block = src_block.next()
            dst_block = dst_block.next()

        layout = cloned.documentLayout()
        try:
            layout.setPaintDevice(printer)
        except Exception:
            pass

        source_dpi_x = 96.0
        source_dpi_y = 96.0
        try:
            screen = QApplication.primaryScreen()
            if screen is not None:
                source_dpi_x = screen.logicalDotsPerInchX()
                source_dpi_y = screen.logicalDotsPerInchY()
        except Exception:
            pass

        horizontal_margin = int((2 / 2.54) * source_dpi_x)
        vertical_margin = int((2 / 2.54) * source_dpi_y)
        fmt = cloned.rootFrame().frameFormat()
        fmt.setLeftMargin(horizontal_margin)
        fmt.setRightMargin(horizontal_margin)
        fmt.setTopMargin(vertical_margin)
        fmt.setBottomMargin(vertical_margin)
        cloned.rootFrame().setFrameFormat(fmt)

        cloned.setPageSize(QSizeF(printer.width(), printer.height()))
        cloned.print_(printer)
    except Exception:
        document.print_(printer)


def _format_diary_date(value):
    try:
        return datetime.fromisoformat(value or "").strftime("%d.%m.%Y")
    except Exception:
        return (value or "")[:10]


def _diary_content_from_record(record):
    try:
        diary_data = json.loads(record[7] or "")
        if isinstance(diary_data, dict):
            return render_diary_html(diary_data), diary_data
    except Exception:
        pass
    return record[4] or "", None


def _make_invisible_print_html(value):
    html_value = value or ""
    replacements = (
        ("black", "#ffffff"),
        ("#000000", "#ffffff"),
        ("#000", "#ffffff"),
        ("#111", "#ffffff"),
        ("rgb(0,0,0)", "#ffffff"),
        ("rgb(0, 0, 0)", "#ffffff"),
    )
    for old, new in replacements:
        html_value = html_value.replace(old, new)
    return html_value

class StationaryCardPage(QWidget):
    def __init__(self, parent, db, patient_id, patient, card_number, case_id=None, read_only=False):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.patient = patient
        self.case = self.db.get_case_by_id(case_id) if case_id is not None else None
        if self.case is None:
            try:
                self.case = self.db.get_case_by_id(int(card_number))
            except Exception:
                self.case = None
        self.history_id = self.case[0] if self.case else None
        if self.history_id is None:
            try:
                self.history_id = int(card_number)
            except Exception:
                self.history_id = None
        if self.case:
            card_number = self.case[2]
        self.read_only = read_only or bool(self.case and self.case[8] == "archived")
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
        status_text = " Архив" if self.read_only else ""
        header_label = QLabel(f"Стационарная карта №{self.card_number}{status_text} {self.patient[2] or ''} {self.patient[9] if len(self.patient) > 9 else ''} {self.patient[1]} {dob_formatted}".strip())
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(header_label)
        top_actions = QHBoxLayout()
        top_actions.addStretch(1)
        self.discharge_button = QPushButton("Выписать пациента")
        self.discharge_button.clicked.connect(self.discharge_patient)
        self.discharge_button.setVisible(not self.read_only)
        top_actions.addWidget(self.discharge_button)
        layout.addLayout(top_actions)

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
                if h[3] == "passport" and (self.history_id is None or h[11] == self.history_id):
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

        self.admission_time = admission_time
        for h in histories:
            if h[3] == "primary_exam" and (self.history_id is None or h[11] == self.history_id):
                if h[9]: clinical_diag = h[9]
                break

        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Header Update (now we have the real card number)
        status_text = " Архив" if self.read_only else ""
        header_label.setText(f"Стационарная карта №{self.card_number}{status_text} {self.patient[2] or ''} {self.patient[9] if len(self.patient) > 9 else ''} {self.patient[1]} {dob_formatted}".strip())
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

        diary_print_button = QPushButton("Печать дневников")
        diary_print_button.clicked.connect(self.print_diaries)
        button_layout.addWidget(diary_print_button)

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
        if self.read_only:
            self._apply_archive_mode()

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
        if self.history_id is not None:
            self.db.update_case_admission(
                self.history_id,
                str(card_number),
                self.admission_date_input.text().strip(),
                self.admission_time_entry.text().strip(),
                diag_clinical or diag_admission,
            )
        
        existing = self.db.get_history_record(self.patient_id, "passport", self.history_id)
        if existing:
            self.db.update_history(
                existing[0], "passport", passport_info, diag_admission, "", "",
                diag_admission=diag_admission,
                diag_clinical=diag_clinical,
                logical_history_id=self.history_id,
            )
        else:
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

    def discharge_patient(self):
        if self.history_id is None:
            QMessageBox.warning(self, "Ошибка", "Не удалось определить историю болезни.")
            return
        dialog = DischargeDialog(
            self,
            self.clinical_diag_entry.text().strip(),
            self.outcome_text.toPlainText().strip(),
            self.admission_date_input.text().strip(),
        )
        if dialog.exec() != QDialog.Accepted:
            return
        data = dialog.get_data()
        try:
            if data["stay_days"] and int(data["stay_days"]) <= 0:
                QMessageBox.warning(self, "Ошибка", "Дата выписки не может быть раньше даты поступления.")
                return
        except ValueError:
            pass
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"История болезни №{self.card_number} будет закрыта и перенесена в архив. Продолжить?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        summary_html = (
            f"<b>Куда направляется выписка:</b> {html.escape(data['destination'])}<br>"
            f"<b>Дата выписки:</b> {html.escape(data['discharge_date'])} {html.escape(data['discharge_time'])}<br>"
            f"<b>Место работы и род занятий:</b> {html.escape(data['workplace'])}<br>"
            f"<b>Исход:</b> {html.escape(data['outcome'])}<br>"
            f"<b>Заключительный диагноз:</b> {html.escape(data['final_diagnosis'])}<br><br>"
            f"<b>Краткий анализ, диагностические исследования, течение болезни, проведенное лечение, состояние при выписке:</b><br>{html.escape(data['summary']).replace(chr(10), '<br>')}<br><br>"
            f"<b>Лечебные и трудовые рекомендации:</b><br>{html.escape(data['recommendations']).replace(chr(10), '<br>')}"
        )
        self.db.discharge_case(
            self.history_id,
            data['discharge_date'],
            data['discharge_time'],
            data['outcome'],
            data['final_diagnosis'],
            data['summary'],
            data['recommendations'],
        )
        existing = self.db.get_history_record(self.patient_id, "discharge_summary", self.history_id)
        if existing:
            self.db.update_history(
                existing[0], "discharge_summary", summary_html, data['final_diagnosis'], "", data['recommendations'],
                diag_clinical=data['final_diagnosis'],
                logical_history_id=self.history_id,
            )
        else:
            self.db.add_history(
                self.patient_id, "discharge_summary", summary_html,
                diagnosis=data['final_diagnosis'],
                notes=data['recommendations'],
                diag_clinical=data['final_diagnosis'],
                history_id=self.history_id,
            )
        QMessageBox.information(self, "Готово", "Пациент выписан. История перенесена в архив.")
        parent = self.parent()
        while parent is not None and not hasattr(parent, '_nav_back'):
            parent = parent.parent()
        if parent is not None:
            try:
                if hasattr(parent, 'load_patients'):
                    parent.load_patients()
                parent._nav_back()
            except Exception:
                pass

    def _apply_archive_mode(self):
        for edit in self.findChildren(QLineEdit):
            edit.setReadOnly(True)
        for edit in self.findChildren(QTextEdit):
            edit.setReadOnly(True)
        for button in self.findChildren(QPushButton):
            if button.text() not in ("🖨️", "Печать"):
                button.setEnabled(False)

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
            page = PlanPage(dlg, self.db, self.patient_id, self.records_table, self.load_histories_list, allowed_categories=['exam','drugs'], history_id=self.history_id)
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
                    anc.nav_push(PlanPage(anc, self.db, self.patient_id, self.records_table, self.load_histories_list, allowed_categories=['exam','drugs'], history_id=self.history_id))
                    return
            except Exception:
                pass

    def load_appointments(self, patient_id):
        # load appointments for the most recent history of patient
        try:
            if self.history_id is None:
                appts = self.db.get_appointments_for_patient(patient_id)
            else:
                appts = self.db.get_appointments_for_logical_history(patient_id, self.history_id)
            self.appointments_table.setRowCount(0)
            for a in appts:
                # a: id, history_id, name, method, freq, date_assign, date_cancel, created_at
                row = self.appointments_table.rowCount()
                self.appointments_table.insertRow(row)
                name_item = QTableWidgetItem(a[2] or "")
                name_item.setData(Qt.UserRole, a[0])
                self.appointments_table.setItem(row, 0, name_item)
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
                appointment_id = self.appointments_table.item(row, 0).data(Qt.UserRole) if self.appointments_table.item(row, 0) else None
                if appointment_id:
                    self.db.update_appointment(
                        appointment_id,
                        res.get("name", ""),
                        res.get("method", ""),
                        res.get("freq", ""),
                        res.get("date_assign", ""),
                        res.get("date_cancel", ""),
                    )
                name_item = QTableWidgetItem(res.get("name", ""))
                name_item.setData(Qt.UserRole, appointment_id)
                self.appointments_table.setItem(row, 0, name_item)
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
            appointment_id = self.appointments_table.item(row, 0).data(Qt.UserRole) if self.appointments_table.item(row, 0) else None
            if appointment_id:
                self.db.delete_appointment(appointment_id)
            self.appointments_table.removeRow(row)

    def add_record(self):
        # Открываем окно выбора типа записи как всплывающее (popup)
        dialog = AddRecordWindow(self, self.db, self.patient_id, self.records_table, 
                                 self.open_primary_exam, self.load_histories_list, 
                                 history_id=self.history_id)
        dialog.exec()

    def open_primary_exam(self, patient_id, records_table):
        # Проверка: первичный осмотр может быть только один
        if self.db.has_primary_exam(patient_id, self.history_id):
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
        if record_type == "discharge_summary":
            self._print_discharge_form(history)
            return
        if record_type == "diary":
            try:
                diary_data = json.loads(history[7] or "")
                if isinstance(diary_data, dict):
                    html_content = render_diary_html(diary_data)
            except Exception:
                pass
        title = ""
        if record_type == "primary_exam":
            title = "Первичный осмотр"
        elif record_type == "plan":
            title = "Лист назначений"
        elif record_type == "passport":
            title = "Паспортная часть"
        elif record_type == "diary":
            title = ""
        elif record_type == "operation_protocol":
            title = "Протокол операции"
        elif record_type == "discharge_summary":
            title = "Выписной эпикриз"
        elif record_type == "history":
            title = "История болезни"
        else:
            title = "Другое"
        
        try:
            dt = datetime.fromisoformat(history[2])
            formatted_date = dt.strftime("%d.%m.%Y %H:%M")
            if record_type == "diary":
                formatted_date_only = dt.strftime("%d.%m.%Y")
            elif record_type == "operation_protocol":
                formatted_date_only = dt.strftime("%d.%m.%Y %H:%M")
            else:
                formatted_date_only = dt.strftime("%d.%m.%Y") + (" " + self.admission_time if self.admission_time else "")
        except:
            formatted_date = history[2] or ""
            formatted_date_only = formatted_date
        
        # Получаем информацию о пациенте
        patient_name = f"{self.patient[1]} {self.patient[2]} {self.patient[9] if len(self.patient) > 9 else ''}".strip() if self.patient and len(self.patient) > 2 else "Неизвестно"
        
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
            
            # Создаем таблицу для шапки: дата слева, заголовок по центру
            table = cursor.insertTable(1, 2)
            table_format = QTextTableFormat()
            table_format.setBorder(0)
            table.setFormat(table_format)
            
            # Левая ячейка: дата
            cursor = table.cellAt(0, 0).firstCursorPosition()
            cursor.insertText("Дата: " + formatted_date_only, header_format)
            
            # Правая ячейка: заголовок по центру
            cursor = table.cellAt(0, 1).firstCursorPosition()
            block_format = QTextBlockFormat()
            block_format.setAlignment(Qt.AlignCenter)
            cursor.setBlockFormat(block_format)
            cursor.insertText(title, title_format)
            
            cursor.movePosition(QTextCursor.End)
            cursor.insertText("\n\n")
            
            # Основное содержимое
            cursor.insertHtml(html_content)
            _print_document_without_page_numbers(printer, document)
        
        preview.paintRequested.connect(handle_paint)
        preview.exec()

    def print_diaries(self):
        if self.history_id is None:
            QMessageBox.warning(self, "Ошибка", "Не удалось определить текущую историю болезни.")
            return
        dialog = DiaryPrintDialog(self, self.db, self.patient_id, self.history_id)
        dialog.exec()
        self.load_histories_list(self.records_table, self.patient_id)

    def _patient_address(self):
        if not self.patient:
            return ""
        parts = []
        for idx in (5, 6, 7, 8):
            if len(self.patient) > idx and self.patient[idx]:
                parts.append(str(self.patient[idx]))
        return ", ".join(parts)

    def _patient_dob(self):
        if not self.patient or len(self.patient) <= 3 or not self.patient[3]:
            return ""
        try:
            return datetime.fromisoformat(self.patient[3]).strftime("%d.%m.%Y")
        except Exception:
            return str(self.patient[3])

    def _build_discharge_form_html(self, history):
        case = self.db.get_case_by_id(self.history_id) if self.history_id is not None else self.case
        patient_name = f"{self.patient[1]} {self.patient[2]} {self.patient[9] if len(self.patient) > 9 else ''}".strip()
        address = self._patient_address()
        dob = self._patient_dob()

        admission_date = case[3] if case and case[3] else self.admission_date_input.text().strip()
        discharge_date = case[5] if case and case[5] else _extract_after_label(_html_plain(history[4]), "Дата выписки")
        final_diagnosis = case[9] if case and case[9] else history[5]
        summary = case[10] if case and case[10] else _extract_after_label(_html_plain(history[4]), "Выписной эпикриз")
        recommendations = case[11] if case and case[11] else history[7]
        plain = _html_plain(history[4])
        destination = _extract_after_label(plain, "Куда направляется выписка")
        workplace = _extract_after_label(plain, "Место работы и род занятий")

        stay_days = ""
        start = _parse_ru_date(admission_date)
        end = _parse_ru_date(discharge_date)
        if start and end:
            stay_days = str((end - start).days + 1)

        signature_date = _format_ru_full_date(discharge_date)

        def esc(value):
            return html.escape(value or "")

        def block(label, value):
            text = esc(value).replace("\n", "<br>") or "&nbsp;"
            return f"<div class='block'><span class='label'>{label}</span> {text}</div>"

        return f"""
        <html>
        <head>
        <style>
            body {{
                font-family: "Times New Roman", serif;
                font-size: 10pt;
                color: #111;
            }}
            .top {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 8px;
            }}
            .top td {{
                width: 50%;
                vertical-align: top;
                font-size: 9pt;
                line-height: 1.1;
            }}
            .center {{ text-align: center; }}
            .right {{ text-align: right; padding-left: 0; }}
            .right-wrap {{
                display: inline-block;
                text-align: right;
            }}
            .title {{
                text-align: center;
                font-size: 15pt;
                font-weight: bold;
                letter-spacing: 1px;
                margin-top: 8px;
            }}
            .subtitle {{
                text-align: center;
                font-weight: bold;
                margin-bottom: 10px;
            }}
            .block {{
                margin-top: 6px;
                line-height: 1.18;
            }}
            .label {{
                font-weight: bold;
                margin-bottom: 1px;
            }}
            .date-line {{
                margin-top: 18px;
            }}
            .doctor {{
                text-align: right;
                width: 100%;
                font-size: 10pt;
                white-space: nowrap;
            }}
        </style>
        </head>
        <body>
            <table class="top">
                <tr>
                    <td class="center">
                        Министерство здравоохранения<br>
                        Приднестровской Молдавской Республики<br>
                        ГУ БГЦБ
                    </td>
                    <td></td>
                </tr>
            </table>

            <div class="title">ВЫПИСКА</div>
            <div class="subtitle">из медицинской карты стационарного больного</div>

            {block("В", destination)}
            {block("1. Фамилия, имя, отчество больного", patient_name)}
            {block("2. Дата рождения", dob)}
            {block("3. Домашний адрес", address)}
            {block("4. Место работы и род занятий", workplace)}
            <div class="block">
                <span class="label">5. Даты: поступления - {esc(admission_date)}, выписка - {esc(discharge_date)}</span>
            </div>
            {block("6. Полный диагноз (основное заболевание, сопутствующее осложнение)", final_diagnosis)}
            {block("7. Краткий анализ, диагностические исследование, течение болезни, проведение лечения, состояние при направлении, при выписке", summary)}
            {block("8. Рекомендации", recommendations)}

            <div class="date-line">{esc(signature_date)}</div>
            <div class="doctor">Лечащий врач Воловая А.А. ______________________</div>
        </body>
        </html>
        """

    def _print_discharge_form(self, history):
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageMargins(QMarginsF(10, 8, 10, 8), QPageLayout.Millimeter)

        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Предварительный просмотр выписки")

        def handle_paint(printer):
            document = QTextDocument()
            document.setDefaultFont(QFont("Times New Roman", 12))
            document.setHtml(self._build_discharge_form_html(history))
            _print_document_without_page_numbers(printer, document)

        preview.paintRequested.connect(handle_paint)
        preview.exec()

    def add_diagnostic(self):
        def _on_done(res):
            try:
                diagnostic_id = self.db.add_diagnostic(
                    self.patient_id,
                    self.history_id,
                    res.get("date", ""),
                    res.get("name", ""),
                    res.get("results", ""),
                )
                row = self.diagnostics_table.rowCount()
                self.diagnostics_table.insertRow(row)
                date_item = QTableWidgetItem(res.get("date", ""))
                date_item.setData(Qt.UserRole, diagnostic_id)
                self.diagnostics_table.setItem(row, 0, date_item)
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
                diagnostic_id = self.diagnostics_table.item(row, 0).data(Qt.UserRole) if self.diagnostics_table.item(row, 0) else None
                if diagnostic_id:
                    self.db.update_diagnostic(diagnostic_id, res.get("date", ""), res.get("name", ""), res.get("results", ""))
                date_item = QTableWidgetItem(res.get("date", ""))
                date_item.setData(Qt.UserRole, diagnostic_id)
                self.diagnostics_table.setItem(row, 0, date_item)
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
            diagnostic_id = self.diagnostics_table.item(row, 0).data(Qt.UserRole) if self.diagnostics_table.item(row, 0) else None
            if diagnostic_id:
                self.db.delete_diagnostic(diagnostic_id)
            self.diagnostics_table.removeRow(row)

    def load_diagnostics(self, patient_id):
        diagnostics = self.db.get_diagnostics(patient_id, self.history_id)
        self.diagnostics_table.setRowCount(0)
        for d in diagnostics:
            row = self.diagnostics_table.rowCount()
            self.diagnostics_table.insertRow(row)
            date_item = QTableWidgetItem(d[3] or "")
            date_item.setData(Qt.UserRole, d[0])
            self.diagnostics_table.setItem(row, 0, date_item)
            self.diagnostics_table.setItem(row, 1, QTableWidgetItem(d[4] or ""))
            self.diagnostics_table.setItem(row, 2, QTableWidgetItem(d[5] or ""))

    def delete_history(self):
        reply1 = QMessageBox.question(self, "Подтверждение", "Вы уверены, что хотите удалить всю историю болезни этого пациента?",
                                      QMessageBox.Yes | QMessageBox.No)
        if reply1 == QMessageBox.Yes:
            reply2 = QMessageBox.question(self, "Второе подтверждение", "Это действие необратимо. Подтвердить удаление всей истории?",
                                          QMessageBox.Yes | QMessageBox.No)
            if reply2 == QMessageBox.Yes:
                if self.history_id is not None:
                    self.db.delete_entire_history_group(self.history_id)
                else:
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
            elif record_type == "operation_protocol":
                title = "Протокол операции"
            elif record_type == "discharge_summary":
                title = "Выписной эпикриз"
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


class DiaryPrintDialog(QDialog):
    def __init__(self, parent, db, patient_id, case_id):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.case_id = case_id
        self.setWindowTitle("Печать дневников")
        self.resize(560, 520)
        self.create_widgets()
        self.refresh_records()

    def create_widgets(self):
        layout = QVBoxLayout(self)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Режим:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Печать новых", "new")
        self.mode_combo.addItem("Перепечатать выбранные", "reprint")
        self.mode_combo.addItem("Печать всех", "all")
        self.mode_combo.currentIndexChanged.connect(self.refresh_records)
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)

        self.state_label = QLabel("")
        self.state_label.setWordWrap(True)
        layout.addWidget(self.state_label)

        self.hint_label = QLabel("Галочками можно выбрать, какие дневники попадут в печать.")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        layout.addWidget(QLabel("Дневники к печати:"))
        self.records_list = QListWidget()
        layout.addWidget(self.records_list, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        preview_button = QPushButton("Предпросмотр")
        preview_button.clicked.connect(self.preview_print)
        buttons.addWidget(preview_button)
        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.reject)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def refresh_records(self, *args):
        state = self.db.get_case_print_state(self.case_id)
        mode = self.mode_combo.currentData()
        records = self.db.get_diary_records_for_case(self.patient_id, self.case_id, only_unprinted=False)

        self.records_list.clear()
        for record in records:
            printed_text = "новый"
            if record[12]:
                printed_text = f"уже печатался {record[12][:10]}"
            item = QListWidgetItem(f"{_format_diary_date(record[2])} - {printed_text}")
            item.setData(Qt.UserRole, record)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if mode == "new":
                checked = not bool(record[12])
            elif mode == "all":
                checked = True
            else:
                checked = False
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self.records_list.addItem(item)

        last_print = state[2]
        if last_print:
            last_print = last_print[:16].replace("T", " ")
            if mode == "reprint":
                text = (
                    f"Последняя печать дневников: {last_print}. "
                    "Перепечатка не меняет отметки печати."
                )
            else:
                text = (
                    f"Последняя печать дневников: {last_print}. "
                    "Невидимые дневники сохранят свое место на листе белым текстом."
                )
            self.state_label.setText(text)
        else:
            self.state_label.setText("Ранее дневники по этой истории не отмечались как напечатанные.")

        if mode == "reprint":
            self.hint_label.setText(
                "Выберите нужные дневники галочками. Невыбранные останутся в разметке белым текстом."
            )
        elif mode == "new":
            self.hint_label.setText(
                "Новые дневники отмечены галочками. Уже напечатанные пойдут белым текстом и сохранят место на листе."
            )
        else:
            self.hint_label.setText("Все дневники будут напечатаны черным текстом.")

    def selected_records(self):
        records = []
        for row in range(self.records_list.count()):
            item = self.records_list.item(row)
            if item.checkState() == Qt.Checked:
                records.append(item.data(Qt.UserRole))
        return records

    def all_records(self):
        records = []
        for row in range(self.records_list.count()):
            records.append(self.records_list.item(row).data(Qt.UserRole))
        return records

    def preview_print(self):
        all_records = self.all_records()
        visible_records = self.selected_records()
        if not visible_records:
            QMessageBox.warning(self, "Ошибка", "Выберите хотя бы один дневник.")
            return

        visible_ids = {record[0] for record in visible_records}
        html_content = self.build_print_html(all_records, visible_ids)

        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageMargins(QMarginsF(5, 5, 5, 7), QPageLayout.Millimeter)

        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Предварительный просмотр дневников")

        def handle_paint(printer):
            document = QTextDocument()
            document.setDefaultFont(QFont("Segoe UI", 9))
            document.setHtml(html_content)
            _print_document_without_page_numbers(printer, document)

        preview.paintRequested.connect(handle_paint)
        preview.exec()

        if self.mode_combo.currentData() == "reprint":
            return

        reply = QMessageBox.question(
            self,
            "Отметить печать",
            "Отметить видимые дневники как напечатанные?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        batch_id = uuid.uuid4().hex[:10]
        printed_at = datetime.now().isoformat()
        record_ids = [record[0] for record in visible_records]
        self.db.mark_histories_printed(record_ids, batch_id, 0, printed_at=printed_at)
        self.db.update_case_diary_print_state(self.case_id, 0, batch_id, printed_at=printed_at)
        QMessageBox.information(self, "Готово", "Видимые дневники отмечены как напечатанные.")
        self.refresh_records()

    def build_print_html(self, records, visible_ids):
        blocks = []
        for record in records:
            content, _ = _diary_content_from_record(record)
            is_visible = record[0] in visible_ids
            visibility_class = "visible" if is_visible else "invisible"
            if not is_visible:
                content = _make_invisible_print_html(content)
            blocks.append(f"""
                <div class="diary-entry {visibility_class}">
                    <div class="diary-date">Дата: {html.escape(_format_diary_date(record[2]))}</div>
                    {content}
                </div>
                <br>
            """)

        return f"""
        <html>
        <head>
        <style>
            body {{
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9pt;
                line-height: 1.22;
                margin: 0;
            }}
            .diary-entry {{
                page-break-inside: avoid;
                margin-bottom: 4mm;
            }}
            .vision-block,
            .vision-block tr,
            .vision-block td,
            .vision-block table {{
                page-break-inside: avoid;
                break-inside: avoid;
            }}
            .diary-entry.invisible,
            .diary-entry.invisible * {{
                visibility: hidden;
                color: #ffffff !important;
                border-color: #ffffff !important;
                background: transparent !important;
            }}
            .diary-date {{
                margin-bottom: 2mm;
            }}
            table {{
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9pt;
            }}
        </style>
        </head>
        <body>
            {''.join(blocks)}
        </body>
        </html>
        """


class DischargeDialog(QDialog):
    def __init__(self, parent, final_diagnosis='', outcome='', admission_date=''):
        super().__init__(parent)
        self.setWindowTitle("Выписка пациента")
        self.setModal(True)
        self.admission_date = admission_date
        self.resize(600, 500)
        layout = QVBoxLayout(self)

        date_row = QHBoxLayout()
        date_row.addWidget(QLabel(f"Дата поступления: {admission_date or 'не указана'}"))
        date_row.addWidget(QLabel("Дата выписки:"))
        self.discharge_date = DateInput()
        self.discharge_date.setText(datetime.now().strftime("%d.%m.%Y"))
        self.discharge_date.edit.textChanged.connect(self._update_stay_days)
        date_row.addWidget(self.discharge_date)
        date_row.addWidget(QLabel("Время:"))
        self.discharge_time = TimeInput()
        self.discharge_time.setText(datetime.now().strftime("%H:%M"))
        date_row.addWidget(self.discharge_time)
        layout.addLayout(date_row)

        self.stay_days_label = QLabel("")
        layout.addWidget(self.stay_days_label)
        self._update_stay_days()

        layout.addWidget(QLabel("Куда направляется выписка:"))
        self.destination = QLineEdit()
        layout.addWidget(self.destination)

        layout.addWidget(QLabel("Место работы и род занятий:"))
        self.workplace = QLineEdit()
        layout.addWidget(self.workplace)

        layout.addWidget(QLabel("Исход:"))
        self.outcome_combo = QComboBox()
        self.outcome_combo.setEditable(True)
        self.outcome_combo.addItems(["улучшение", "без перемен", "ухудшение", "перевод", "смерть", "другое"])
        if outcome:
            self.outcome_combo.setCurrentText(outcome)
        layout.addWidget(self.outcome_combo)

        layout.addWidget(QLabel("Заключительный диагноз:"))
        self.final_diagnosis = QTextEdit()
        self.final_diagnosis.setPlainText(final_diagnosis)
        layout.addWidget(self.final_diagnosis)

        layout.addWidget(QLabel("Краткий анализ, диагностические исследования, течение болезни, проведенное лечение, состояние при выписке:"))
        self.summary = QTextEdit()
        layout.addWidget(self.summary)

        layout.addWidget(QLabel("Лечебные и трудовые рекомендации:"))
        self.recommendations = QTextEdit()
        layout.addWidget(self.recommendations)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        ok = QPushButton("Выписать и перенести в архив")
        ok.clicked.connect(self.accept)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    def _stay_days(self):
        start = _parse_ru_date(self.admission_date)
        end = _parse_ru_date(self.discharge_date.text())
        if not start or not end:
            return ""
        return str((end - start).days + 1)

    def _update_stay_days(self):
        days = self._stay_days()
        if days:
            self.stay_days_label.setText(f"Койко-дней: {days}")
        else:
            self.stay_days_label.setText("Койко-дней: не удалось рассчитать")

    def get_data(self):
        return {
            "destination": self.destination.text().strip(),
            "discharge_date": self.discharge_date.text().strip(),
            "discharge_time": self.discharge_time.text().strip(),
            "stay_days": self._stay_days(),
            "workplace": self.workplace.text().strip(),
            "outcome": self.outcome_combo.currentText().strip(),
            "final_diagnosis": self.final_diagnosis.toPlainText().strip(),
            "summary": self.summary.toPlainText().strip(),
            "recommendations": self.recommendations.toPlainText().strip(),
        }


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
