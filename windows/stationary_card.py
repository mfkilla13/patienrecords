import html
import json
import uuid
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QStackedWidget, QLabel, QLineEdit, QPushButton, QTextEdit, QTabWidget, QWidget as QtWidget, QListWidget, QListWidgetItem, QMessageBox, QInputDialog, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDialog, QComboBox, QCheckBox, QSpinBox
from PySide6.QtCore import Qt, QMarginsF, QDate, QSizeF
from PySide6.QtGui import QTextDocument, QPageLayout, QPageSize, QTextCursor, QTextCharFormat, QFont, QTextTableFormat, QTextBlockFormat
from PySide6.QtPrintSupport import QPrintPreviewDialog, QPrinter
from datetime import datetime
from .add_record import AddRecordWindow
from .edit_record import EditRecordWindow
from .primary_exam import PrimaryExamWindow, MultiSelectButton
from .config import LOCAL_ROWS_CONFIG
from widgets.date_input import DateInput
from widgets.time_input import TimeInput
from .diary import render_diary_html, _diary_vis_html

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

        # Do not derive document margins from screen DPI: that makes print
        # geometry drift between machines. Let the printer/page geometry define
        # the printable area, and keep the QTextDocument margin neutral.
        cloned.setDocumentMargin(0)

        cloned.setPageSize(QSizeF(printer.width(), printer.height()))
        cloned.print_(printer)
    except Exception:
        document.print_(printer)


def _format_diary_date(value):
    try:
        return datetime.fromisoformat(value or "").strftime("%d.%m.%Y")
    except Exception:
        return (value or "")[:10]


def _format_record_time(value):
    try:
        return datetime.fromisoformat(value or "").strftime("%H:%M")
    except Exception:
        return ""


def _record_print_content(record):
    record_type = record[3]
    if record_type == "diary":
        try:
            diary_data = json.loads(record[7] or "")
            if isinstance(diary_data, dict):
                return render_diary_html(diary_data, _format_diary_date(record[2])), diary_data
        except Exception:
            pass
        return record[4] or "", None
    if record_type == "operation_protocol":
        return f"""
            <div class="protocol-entry">
                {record[4] or ""}
            </div>
        """, None

    if record_type == "primary_exam":
        content = record[4] or ""
        if "Воловая А.А." not in content:
            content += '<div style="margin-top:6mm; text-align:right;">Воловая А.А. __________________</div>'
        return content, None
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


def _load_discharge_payload(value):
    try:
        data = json.loads(value or "")
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _strip_local_markers(text):
    """Убрать служебные маркеры блока местного статуса из текста эпикриза."""
    import re as _re_m
    text = _re_m.sub(r'--- Местный статус при выписке ---\n?', '', text or '')
    text = _re_m.sub(r'\n?--- Конец местного статуса ---\n?', '\n', text).strip()
    return text


DIAGNOSTIC_TYPES = [
    "Флюорография (ФГ)",
    "МРС",
    "ОАМ",
    "Сахар крови",
    "ОАК",
    "ЭКГ",
    "Свободная форма",
]


def _diagnostic_payload_from_results(value):
    try:
        payload = json.loads(value or "")
        if isinstance(payload, dict) and payload.get("schema") == "diagnostic_form_v1":
            return payload
    except Exception:
        pass
    return None


def _join_nonempty(parts, sep=", "):
    return sep.join(part for part in parts if part)


def _diagnostic_results_text(name, payload_or_text):
    payload = payload_or_text if isinstance(payload_or_text, dict) else _diagnostic_payload_from_results(payload_or_text)
    if not payload:
        return payload_or_text or ""

    fields = payload.get("fields") or {}
    diag_type = payload.get("type") or name or ""

    if diag_type == "Флюорография (ФГ)":
        lines = [
            f"№ флюорографии: {fields.get('number', '').strip()}" if fields.get("number") else "",
            f"Результат: {fields.get('result', '').strip()}" if fields.get("result") else "",
        ]
        return "\n".join(line for line in lines if line)

    if diag_type == "МРС":
        lines = [
            f"Результат: {fields.get('result', '').strip()}" if fields.get("result") else "",
            f"Титр: {fields.get('titer', '').strip()}" if fields.get("titer") else "",
            fields.get("comment", "").strip(),
        ]
        return "\n".join(line for line in lines if line)

    if diag_type == "ОАМ":
        line1 = _join_nonempty([
            f"Уд. вес: {fields.get('gravity', '').strip()}" if fields.get("gravity") else "",
            f"pH: {fields.get('ph', '').strip()}" if fields.get("ph") else "",
        ], "; ")
        line2 = _join_nonempty([
            f"Белок: {fields.get('protein', '').strip()}" if fields.get("protein") else "",
            f"Сахар: {fields.get('glucose', '').strip()}" if fields.get("glucose") else "",
            f"Лейкоциты: {fields.get('leukocytes', '').strip()}" if fields.get("leukocytes") else "",
            f"Эритроциты: {fields.get('erythrocytes', '').strip()}" if fields.get("erythrocytes") else "",
            f"Эпителий: {fields.get('epithelium', '').strip()}" if fields.get("epithelium") else "",
            f"Соли: {fields.get('salts', '').strip()}" if fields.get("salts") else "",
            f"Бактерии: {fields.get('bacteria', '').strip()}" if fields.get("bacteria") else "",
        ], "; ")
        return "\n".join(line for line in (line1, line2, fields.get("note", "").strip()) if line)

    if diag_type == "Сахар крови":
        lines = [
            f"Глюкоза: {fields.get('value', '').strip()} ммоль/л" if fields.get("value") else "",
            fields.get("note", "").strip(),
        ]
        return "\n".join(line for line in lines if line)

    if diag_type == "ЭКГ":
        return fields.get("results", "").strip()

    if diag_type == "ОАК":
        line1 = _join_nonempty([
            f"Hb {fields.get('hemoglobin', '').strip()}" if fields.get("hemoglobin") else "",
            f"Эр {fields.get('rbc', '').strip()}" if fields.get("rbc") else "",
            f"Л {fields.get('wbc', '').strip()}" if fields.get("wbc") else "",
            f"Тр {fields.get('platelets', '').strip()}" if fields.get("platelets") else "",
            f"СОЭ {fields.get('esr', '').strip()}" if fields.get("esr") else "",
        ], "; ")
        line2 = _join_nonempty([
            f"П/я {fields.get('stab', '').strip()}%" if fields.get("stab") else "",
            f"С/я {fields.get('segmented', '').strip()}%" if fields.get("segmented") else "",
            f"Э {fields.get('eosinophils', '').strip()}%" if fields.get("eosinophils") else "",
            f"Лимф {fields.get('lymphocytes', '').strip()}%" if fields.get("lymphocytes") else "",
            f"Мон {fields.get('monocytes', '').strip()}%" if fields.get("monocytes") else "",
            f"ЦП {fields.get('color_index', '').strip()}" if fields.get("color_index") else "",
        ], "; ")
        return "\n".join(line for line in (line1, line2, fields.get("note", "").strip()) if line)

    return payload.get("text") or payload_or_text or ""

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
        self.medical_record_number = (self.case[14] if self.case and len(self.case) > 14 else "") or ""
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
        self.discharge_button = QPushButton("Перенести в архив")
        self.discharge_button.clicked.connect(self.archive_case)
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

        med_card_layout = QHBoxLayout()
        med_card_layout.addWidget(QLabel("Номер мед.карты:"))
        self.medical_record_number_input = QLineEdit(self.medical_record_number)
        self.medical_record_number_input.setMaxLength(6)
        self.medical_record_number_input.setPlaceholderText("до 6 цифр")
        self.medical_record_number_input.setInputMask("999999;_")
        med_card_layout.addWidget(self.medical_record_number_input)
        passport_layout.addLayout(med_card_layout)

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

        diary_print_button = QPushButton("Печать записей")
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
        medical_record_number = self.medical_record_number_input.text().replace("_", "").strip()
        passport_info = (
            f"Номер карты: {card_number}\n"
            f"Номер мед.карты: {medical_record_number}\n"
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
            self.db.set_case_medical_record_number(self.history_id, medical_record_number)
            self.medical_record_number = medical_record_number
        
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
        _primary_exam = self.db.get_history_record(self.patient_id, "primary_exam", self.history_id)
        _complaints = _extract_after_label(_html_plain(_primary_exam[4]), "Жалобы") if _primary_exam else ""
        _main_diag = (_primary_exam[9] or "").strip() if _primary_exam else ""
        _comorbid_diag = (_primary_exam[10] or "").strip() if _primary_exam else ""
        _primary_vis = {}
        if _primary_exam:
            try:
                import json as _json
                _pnotes = _json.loads(_primary_exam[7] or "")
                if isinstance(_pnotes, dict):
                    for _k in ("vis_od", "vis_os", "vis_correction_od", "vis_correction_os",
                               "vis_od_corr", "vis_od_result", "vis_os_corr", "vis_os_result",
                               "vgd_od", "vgd_os"):
                        _primary_vis[_k] = _pnotes.get(_k, "")
            except Exception:
                pass
        dialog = DischargeDialog(
            self,
            self.clinical_diag_entry.text().strip(),
            self.outcome_text.toPlainText().strip(),
            self.admission_date_input.text().strip(),
            self.db.get_diagnostics(self.patient_id, self.history_id),
            complaints=_complaints,
            main_diagnosis=_main_diag,
            comorbid_diagnosis=_comorbid_diag,
            primary_vis=_primary_vis,
            db=self.db,
            patient_id=self.patient_id,
            history_id=self.history_id,
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
        summary_html = (
            f"<b>Куда направляется выписка:</b> {html.escape(data['destination'])}<br>"
            f"<b>Дата выписки:</b> {html.escape(data['discharge_date'])} {html.escape(data['discharge_time'])}<br>"
            f"<b>Место работы и род занятий:</b> {html.escape(data['workplace'])}<br>"
            f"<b>Исход:</b> {html.escape(data['outcome'])}<br>"
            f"<b>Заключительный диагноз:</b> {html.escape(data['final_diagnosis'])}<br><br>"
            f"<b>Эпикриз:</b><br>{html.escape(data['epicrisis']).replace(chr(10), '<br>')}<br><br>"
            f"<b>Лечебные и трудовые рекомендации:</b><br>{html.escape(data['recommendations']).replace(chr(10), '<br>')}"
        )
        discharge_payload = {
            "epicrisis": data["epicrisis"],
            "recommendations": data["recommendations"],
            "vis_od": data["vis_od"],
            "vis_os": data["vis_os"],
            "vis_correction_od": data["vis_correction_od"],
            "vis_correction_os": data["vis_correction_os"],
            "vis_od_corr": data["vis_od_corr"],
            "vis_os_corr": data["vis_os_corr"],
            "vis_od_result": data["vis_od_result"],
            "vis_os_result": data["vis_os_result"],
            "vgd_od": data["vgd_od"],
            "vgd_os": data["vgd_os"],
            "vgd_od_max": data["vgd_od_max"],
            "vgd_od_min": data["vgd_od_min"],
            "vgd_os_max": data["vgd_os_max"],
            "vgd_os_min": data["vgd_os_min"],
            "elasto_od": data["elasto_od"],
            "elasto_os": data["elasto_os"],
            "tono_od_ro": data["tono_od_ro"],
            "tono_od_c": data["tono_od_c"],
            "tono_od_kb": data["tono_od_kb"],
            "tono_od_f": data["tono_od_f"],
            "tono_os_ro": data["tono_os_ro"],
            "tono_os_c": data["tono_os_c"],
            "tono_os_kb": data["tono_os_kb"],
            "tono_os_f": data["tono_os_f"],
            "treatment_summary": data["treatment_summary"],
            "sig_dep_chief": data["sig_dep_chief"],
            "sig_chief": data["sig_chief"],
            "discharge_local": data["discharge_local"],
            "local_status_text": data["local_status_text"],
        }
        self.db.discharge_case(
            self.history_id,
            data['discharge_date'],
            data['discharge_time'],
            data['outcome'],
            data['final_diagnosis'],
            data['epicrisis'],
            data['recommendations'],
        )
        existing = self.db.get_history_record(self.patient_id, "discharge_summary", self.history_id)
        if existing:
            self.db.update_history(
                existing[0], "discharge_summary", summary_html, data['final_diagnosis'], data['recommendations'], json.dumps(discharge_payload, ensure_ascii=False),
                diag_clinical=data['final_diagnosis'],
                logical_history_id=self.history_id,
            )
        else:
            self.db.add_history(
                self.patient_id, "discharge_summary", summary_html,
                diagnosis=data['final_diagnosis'],
                treatment=data['recommendations'],
                notes=json.dumps(discharge_payload, ensure_ascii=False),
                diag_clinical=data['final_diagnosis'],
                history_id=self.history_id,
            )
        QMessageBox.information(self, "Готово", "Выписка сохранена. История пока остается в общем списке, чтобы можно было распечатать документы.")
        try:
            self.load_histories_list(self.records_table, self.patient_id)
        except Exception:
            pass
        parent = self.parent()
        while parent is not None and not hasattr(parent, 'load_patients'):
            parent = parent.parent()
        if parent is not None and hasattr(parent, 'load_patients'):
            try:
                parent.load_patients()
            except Exception:
                pass

    def archive_case(self):
        if self.history_id is None:
            QMessageBox.warning(self, "Ошибка", "Не удалось определить историю болезни.")
            return

        case = self.db.get_case_by_id(self.history_id)
        discharge_record = self.db.get_history_record(self.patient_id, "discharge_summary", self.history_id)
        has_discharge_data = bool(
            case and ((case[5] or "").strip() or (case[10] or "").strip() or discharge_record)
        )
        if not has_discharge_data:
            QMessageBox.warning(
                self,
                "Сначала оформите выписку",
                "Сначала сохраните выписку через 'Выписной эпикриз', а потом переносите историю в архив.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Перенести историю болезни №{self.card_number} в архив?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.db.archive_case(self.history_id)
        QMessageBox.information(self, "Готово", "История перенесена в архив.")
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
            if button.text() not in ("🖨️", "Печать", "Печать записей"):
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
        selected = self.records_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите запись для редактирования.")
            return
        row = selected[0].row()
        record_id = self.records_table.item(row, 0).data(Qt.UserRole)
        history = self.db.get_history_by_id(record_id)
        if not history:
            QMessageBox.warning(self, "Ошибка", "Запись не найдена.")
            return

        record_type = history[3]

        app_main = self.parent()
        while app_main is not None and not hasattr(app_main, 'nav_push'):
            app_main = app_main.parent()

        if record_type == "primary_exam":
            dialog = PrimaryExamWindow(
                app_main or self,
                self.db,
                self.patient_id,
                self.records_table,
                self.load_histories_list,
                history_id=self.history_id,
                edit_record_id=record_id,
            )
            dialog.load_existing(history)
            if app_main is not None:
                app_main.nav_push(dialog)
            else:
                dialog.show()
            return

        if record_type == "diary":
            from .diary import DiaryWindow
            dialog = DiaryWindow(
                app_main or self,
                self.db,
                self.patient_id,
                self.records_table,
                self.load_histories_list,
                history_id=self.history_id,
                edit_record_id=record_id,
            )
            dialog.load_existing(history)
            if app_main is not None:
                app_main.nav_push(dialog)
            else:
                dialog.show()
            return

        if record_type == "operation_protocol":
            from .operation_protocol import OperationProtocolWindow
            dialog = OperationProtocolWindow(
                app_main or self,
                self.db,
                self.patient_id,
                self.records_table,
                self.load_histories_list,
                history_id=self.history_id,
                edit_record_id=record_id,
            )
            dialog.load_existing(history)
            if app_main is not None:
                app_main.nav_push(dialog)
            else:
                dialog.show()
            return

        if record_type == "discharge_summary":
            case = self.db.get_case_by_id(self.history_id) if self.history_id is not None else None
            _primary_exam = self.db.get_history_record(self.patient_id, "primary_exam", self.history_id)
            _complaints = _extract_after_label(_html_plain(_primary_exam[4]), "Жалобы") if _primary_exam else ""
            _main_diag = (_primary_exam[9] or "").strip() if _primary_exam else ""
            _comorbid_diag = (_primary_exam[10] or "").strip() if _primary_exam else ""
            _primary_vis = {}
            if _primary_exam:
                try:
                    import json as _json
                    _pnotes = _json.loads(_primary_exam[7] or "")
                    if isinstance(_pnotes, dict):
                        for _k in ("vis_od", "vis_os", "vis_correction_od", "vis_correction_os",
                                   "vis_od_corr", "vis_od_result", "vis_os_corr", "vis_os_result",
                                   "vgd_od", "vgd_os"):
                            _primary_vis[_k] = _pnotes.get(_k, "")
                except Exception:
                    pass
            dialog = DischargeDialog(
                self,
                (case[9] if case else "") or history[5],
                (case[7] if case else ""),
                self.admission_date_input.text().strip(),
                self.db.get_diagnostics(self.patient_id, self.history_id),
                complaints=_complaints,
                main_diagnosis=_main_diag,
                comorbid_diagnosis=_comorbid_diag,
                primary_vis=_primary_vis,
                db=self.db,
                patient_id=self.patient_id,
                history_id=self.history_id,
            )
            dialog.load_existing(history, case=case)
            if dialog.exec() != QDialog.Accepted:
                return
            data = dialog.get_data()
            try:
                if data["stay_days"] and int(data["stay_days"]) <= 0:
                    QMessageBox.warning(self, "Ошибка", "Дата выписки не может быть раньше даты поступления.")
                    return
            except ValueError:
                pass
            summary_html = (
                f"<b>Куда направляется выписка:</b> {html.escape(data['destination'])}<br>"
                f"<b>Дата выписки:</b> {html.escape(data['discharge_date'])} {html.escape(data['discharge_time'])}<br>"
                f"<b>Место работы и род занятий:</b> {html.escape(data['workplace'])}<br>"
                f"<b>Исход:</b> {html.escape(data['outcome'])}<br>"
                f"<b>Заключительный диагноз:</b> {html.escape(data['final_diagnosis'])}<br><br>"
                f"<b>Эпикриз:</b><br>{html.escape(data['epicrisis']).replace(chr(10), '<br>')}<br><br>"
                f"<b>Лечебные и трудовые рекомендации:</b><br>{html.escape(data['recommendations']).replace(chr(10), '<br>')}"
            )
            discharge_payload = {
                "epicrisis": data["epicrisis"],
                "recommendations": data["recommendations"],
                "vis_od": data["vis_od"],
                "vis_os": data["vis_os"],
                "vis_correction_od": data["vis_correction_od"],
                "vis_correction_os": data["vis_correction_os"],
                "vis_od_corr": data["vis_od_corr"],
                "vis_os_corr": data["vis_os_corr"],
                "vis_od_result": data["vis_od_result"],
                "vis_os_result": data["vis_os_result"],
                "vgd_od": data["vgd_od"],
                "vgd_os": data["vgd_os"],
                "vgd_od_max": data["vgd_od_max"],
                "vgd_od_min": data["vgd_od_min"],
                "vgd_os_max": data["vgd_os_max"],
                "vgd_os_min": data["vgd_os_min"],
                "elasto_od": data["elasto_od"],
                "elasto_os": data["elasto_os"],
                "tono_od_ro": data["tono_od_ro"],
                "tono_od_c": data["tono_od_c"],
                "tono_od_kb": data["tono_od_kb"],
                "tono_od_f": data["tono_od_f"],
                "tono_os_ro": data["tono_os_ro"],
                "tono_os_c": data["tono_os_c"],
                "tono_os_kb": data["tono_os_kb"],
                "tono_os_f": data["tono_os_f"],
                "treatment_summary": data["treatment_summary"],
                "sig_dep_chief": data["sig_dep_chief"],
                "sig_chief": data["sig_chief"],
                "discharge_local": data["discharge_local"],
                "local_status_text": data["local_status_text"],
            }
            self.db.discharge_case(
                self.history_id,
                data['discharge_date'],
                data['discharge_time'],
                data['outcome'],
                data['final_diagnosis'],
                data['epicrisis'],
                data['recommendations'],
            )
            self.db.update_history(
                record_id,
                "discharge_summary",
                summary_html,
                data['final_diagnosis'],
                data['recommendations'],
                json.dumps(discharge_payload, ensure_ascii=False),
                logical_history_id=self.history_id,
            )
            QMessageBox.information(self, "Успех", "Выписка обновлена.")
            self.load_histories_list(self.records_table, self.patient_id)
            try:
                parent = self.parent()
                while parent is not None and not hasattr(parent, 'load_patients'):
                    parent = parent.parent()
                if parent is not None and hasattr(parent, 'load_patients'):
                    parent.load_patients()
            except Exception:
                pass
            return

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
                    html_content = render_diary_html(diary_data, formatted_date_only)
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
            elif record_type in ("operation_protocol", "primary_exam"):
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
        printer.setPageMargins(QMarginsF(15, 20, 15, 20), QPageLayout.Millimeter)
        
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Предварительный просмотр")
        
        def handle_paint(printer):
            document = QTextDocument()

            if record_type == "primary_exam":
                _font = QFont("Segoe UI")
                _font.setPointSizeF(9.5)
                document.setDefaultFont(_font)
            else:
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
            if record_type == "primary_exam":
                _header_font = QFont("Segoe UI")
                _header_font.setPointSizeF(9.5)
                header_format.setFont(_header_font)
            else:
                header_format.setFont(QFont("Segoe UI", 9))
            
            title_format = QTextCharFormat()
            if record_type == "primary_exam":
                _title_font = QFont("Segoe UI")
                _title_font.setBold(True)
                _title_font.setPointSizeF(9.5)
                title_format.setFont(_title_font)
            else:
                title_format.setFont(QFont("Segoe UI", 10, QFont.Bold))
            
            if record_type != "diary":
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
        medical_record_number = (case[14] if case and len(case) > 14 else "") or ""

        admission_date = case[3] if case and case[3] else self.admission_date_input.text().strip()
        discharge_date = case[5] if case and case[5] else _extract_after_label(_html_plain(history[4]), "Дата выписки")
        final_diagnosis = case[9] if case and case[9] else history[5]
        payload = _load_discharge_payload(history[7] if history else "")
        epicrisis = case[10] if case and case[10] else payload.get("epicrisis") or _extract_after_label(_html_plain(history[4]), "Эпикриз") or _extract_after_label(_html_plain(history[4]), "Выписной эпикриз")
        recommendations = case[11] if case and case[11] else payload.get("recommendations") or history[6] or ""
        plain = _html_plain(history[4])
        destination = _extract_after_label(plain, "Куда направляется выписка")
        workplace = _extract_after_label(plain, "Место работы и род занятий")
        # Vis/ВГД "При выписке" — из discharge payload
        discharge_vis_html = _diary_vis_html(payload)
        # Vis/ВГД "При поступлении" — из primary exam notes
        admission_vis_html = ""
        try:
            _pe = self.db.get_history_record(self.patient_id, "primary_exam", self.history_id)
            if _pe:
                import json as _json
                _pnotes = _json.loads(_pe[7] or "")
                if isinstance(_pnotes, dict):
                    admission_vis_html = _diary_vis_html(_pnotes)
        except Exception:
            pass

        # Дополнительные офтальмологические данные (только если заполнены)
        extra_oph_lines = []
        vgd_od_max = (payload.get("vgd_od_max") or "").strip()
        vgd_od_min = (payload.get("vgd_od_min") or "").strip()
        vgd_os_max = (payload.get("vgd_os_max") or "").strip()
        vgd_os_min = (payload.get("vgd_os_min") or "").strip()
        if any([vgd_od_max, vgd_od_min, vgd_os_max, vgd_os_min]):
            extra_oph_lines.append(
                f'''<table border="0" cellpadding="0" cellspacing="0" style="border-collapse:collapse; margin:0;"><tr>
                <td style="vertical-align:middle; padding-right:6px; white-space:nowrap;"><b>ВГД</b></td>
                <td style="vertical-align:top;">
                    <div>OD &nbsp; max {vgd_od_max or '—'} &nbsp; min {vgd_od_min or '—'} &nbsp; мм.рт.ст.</div>
                    <div>OS &nbsp; max {vgd_os_max or '—'} &nbsp; min {vgd_os_min or '—'} &nbsp; мм.рт.ст.</div>
                </td>
                </tr></table>'''
            )
        elasto_od = (payload.get("elasto_od") or "").strip()
        elasto_os = (payload.get("elasto_os") or "").strip()
        if elasto_od or elasto_os:
            extra_oph_lines.append(
                f'''<table border="0" cellpadding="0" cellspacing="0" style="border-collapse:collapse; margin:0;"><tr>
                <td style="vertical-align:middle; padding-right:6px; white-space:nowrap;"><b>Эластотонометрия</b></td>
                <td style="vertical-align:top;">
                    <div>OD &nbsp; {elasto_od or '—'}</div>
                    <div>OS &nbsp; {elasto_os or '—'}</div>
                </td>
                </tr></table>'''
            )
        tono_od = {k: (payload.get(f"tono_od_{k}") or "").strip() for k in ("ro", "c", "kb", "f")}
        tono_os = {k: (payload.get(f"tono_os_{k}") or "").strip() for k in ("ro", "c", "kb", "f")}
        if any(tono_od.values()) or any(tono_os.values()):
            od_row = f"OD &nbsp; Ро {tono_od['ro'] or '—'} &nbsp; С {tono_od['c'] or '—'} &nbsp; КБ {tono_od['kb'] or '—'} &nbsp; F {tono_od['f'] or '—'}"
            os_row = f"OS &nbsp; Ро {tono_os['ro'] or '—'} &nbsp; С {tono_os['c'] or '—'} &nbsp; КБ {tono_os['kb'] or '—'} &nbsp; F {tono_os['f'] or '—'}"
            extra_oph_lines.append(
                f'''<table border="0" cellpadding="0" cellspacing="0" style="border-collapse:collapse; margin:0;"><tr>
                <td style="vertical-align:middle; padding-right:6px; white-space:nowrap;"><b>Тонография по Нестерову</b></td>
                <td style="vertical-align:top;">
                    <div>{od_row}</div>
                    <div>{os_row}</div>
                </td>
                </tr></table>'''
            )
        extra_oph_html = "".join(f"<div style='margin-top:3px;'>{line}</div>" for line in extra_oph_lines)

        # Лечение из payload (отредактированное пользователем)
        _ts = (payload.get("treatment_summary") or "").strip()
        treatment_summary_html = (
            f"<div style='margin-top:3px;'><b>Лечение:</b> {html.escape(_ts)}</div>"
            if _ts else ""
        )

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

        def block_newline(label, value):
            text = esc(value).replace("\n", "<br>") or "&nbsp;"
            return f"<div class='block'><span class='label'>{label}</span><div>{text}</div></div>"

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
            .vision-wrap {{
                margin-top: 4px;
                margin-bottom: 4px;
            }}
            .vision-block,
            .vision-block table,
            .vision-block td,
            .vision-block tr {{
                font-family: "Times New Roman", serif;
                font-size: 10pt;
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

            <div class="title">ВЫПИСКА{f" №{esc(medical_record_number)}" if medical_record_number else ""}</div>
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
            <div class="block">
                <span class="label">7. Эпикриз</span>
                <div>Находился/лась на стационарном лечении в офтальмологическом отделении</div>
                {"<div><b>При поступлении:</b></div><div class='vision-wrap'>" + admission_vis_html + "</div>" if admission_vis_html else ""}
                <div>{esc(epicrisis).replace("\n", "<br>") or "&nbsp;"}</div>
                {extra_oph_html}
                {treatment_summary_html}
                {"<div style='margin-top:4px;'><b>При выписке:</b></div><div class='vision-wrap'>" + discharge_vis_html + "</div>" if discharge_vis_html else ""}
            </div>
            {block_newline("8. Рекомендации", recommendations)}

            <table width="100%" cellspacing="0" cellpadding="0" style="margin-top:18px; border-collapse:collapse;">
                <tr>
                    <td width="30%" style="text-align:left; vertical-align:top; font-size:10pt; white-space:nowrap;">{esc(signature_date)}</td>
                    <td width="30%">&nbsp;</td>
                    <td width="40%" style="text-align:right; vertical-align:top; font-size:10pt; line-height:1.7; white-space:nowrap;">
                        {"Зам. главного врача __________________<br>" if payload.get("sig_dep_chief") else ""}{"Гл. врач __________________________<br>" if payload.get("sig_chief") else ""}Зав. отделением ______________________
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    def _print_discharge_form(self, history):
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageMargins(QMarginsF(15, 20, 15, 20), QPageLayout.Millimeter)

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
                self.diagnostics_table.setItem(row, 2, QTableWidgetItem(_diagnostic_results_text(res.get("name", ""), res.get("results", ""))))
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
                self.diagnostics_table.setItem(row, 2, QTableWidgetItem(_diagnostic_results_text(res.get("name", ""), res.get("results", ""))))
            except Exception:
                pass

        dlg_parent = self.parent() if self.parent() is not None else self
        dialog = DiagnosticDialog(dlg_parent, done_callback=_on_edit)
        dialog.date_edit.setText(self.diagnostics_table.item(row, 0).text())
        diagnostic_id = self.diagnostics_table.item(row, 0).data(Qt.UserRole) if self.diagnostics_table.item(row, 0) else None
        existing = None
        if diagnostic_id:
            for d in self.db.get_diagnostics(self.patient_id, self.history_id):
                if d[0] == diagnostic_id:
                    existing = d
                    break
        dialog.load_existing(
            existing[4] if existing else self.diagnostics_table.item(row, 1).text(),
            existing[5] if existing else self.diagnostics_table.item(row, 2).text(),
        )
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
            self.diagnostics_table.setItem(row, 2, QTableWidgetItem(_diagnostic_results_text(d[4] or "", d[5] or "")))

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
        self.setWindowTitle("Печать записей")
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
        self.mode_combo.addItem("Печатать выбранные с нового листа", "selected_new_page")
        self.mode_combo.addItem("Печатать от указанной границы", "selected_from_offset")
        self.mode_combo.addItem("Печать всех", "all")
        self.mode_combo.currentIndexChanged.connect(self.refresh_records)
        mode_row.addWidget(self.mode_combo, 1)
        layout.addLayout(mode_row)

        offset_row = QHBoxLayout()
        self.offset_label = QLabel("Отступ сверху на первой странице:")
        offset_row.addWidget(self.offset_label)
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(0, 290)
        self.offset_spin.setSuffix(" мм")
        self.offset_spin.setValue(0)
        offset_row.addWidget(self.offset_spin)
        offset_row.addStretch(1)
        layout.addLayout(offset_row)

        self.state_label = QLabel("")
        self.state_label.setWordWrap(True)
        layout.addWidget(self.state_label)

        self.hint_label = QLabel("Галочками можно выбрать, какие дневники, протоколы и первичные осмотры попадут в печать.")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        layout.addWidget(QLabel("Записи к печати:"))
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
        custom_offset_mm = int(state[4] or 0)
        custom_last_print = state[5]

        self.records_list.clear()
        for record in records:
            printed_text = "новый"
            if record[12]:
                printed_text = f"уже печатался {record[12][:10]}"
            record_title = "Дневник" if record[3] == "diary" else "Протокол операции" if record[3] == "operation_protocol" else "Первичный осмотр"
            time_text = _format_record_time(record[2])
            time_suffix = f" {time_text}" if time_text and record[3] == "operation_protocol" else ""
            item = QListWidgetItem(f"{_format_diary_date(record[2])} {record_title}{time_suffix} - {printed_text}")
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
        self.offset_label.setVisible(mode == "selected_from_offset")
        self.offset_spin.setVisible(mode == "selected_from_offset")
        if mode == "selected_from_offset":
            self.offset_spin.setValue(custom_offset_mm)
        if last_print:
            last_print = last_print[:16].replace("T", " ")
            if mode == "reprint":
                text = (
                    f"Последняя печать записей: {last_print}. "
                    "Перепечатка не меняет отметки печати."
                )
            elif mode == "selected_new_page":
                text = (
                    f"Последняя печать записей: {last_print}. "
                    "Выбранные записи будут собраны с начала нового листа."
                )
            elif mode == "selected_from_offset":
                custom_part = ""
                if custom_last_print:
                    custom_part = (
                        f" Последняя печать от границы: {custom_last_print[:16].replace('T', ' ')} "
                        f"(отступ {custom_offset_mm} мм)."
                    )
                text = (
                    f"Последняя печать записей: {last_print}. "
                    f"Выбранные записи будут напечатаны от указанной границы на первой странице."
                    f"{custom_part}"
                )
            else:
                text = (
                    f"Последняя печать записей: {last_print}. "
                    "Невидимые записи сохранят свое место на листе белым текстом."
                )
            self.state_label.setText(text)
        else:
            if mode == "selected_from_offset" and custom_last_print:
                self.state_label.setText(
                    f"Последняя печать от границы: {custom_last_print[:16].replace('T', ' ')} "
                    f"(отступ {custom_offset_mm} мм)."
                )
            else:
                self.state_label.setText("Ранее записи по этой истории не отмечались как напечатанные.")

        if mode == "reprint":
            self.hint_label.setText(
                "Выберите нужные записи галочками. Невыбранные останутся в разметке белым текстом."
            )
        elif mode == "selected_new_page":
            self.hint_label.setText(
                "Выберите нужные записи галочками. Они будут напечатаны с начала нового листа без скрытых пустых мест."
            )
        elif mode == "selected_from_offset":
            self.hint_label.setText(
                "Выберите нужные записи галочками. Они будут напечатаны с указанной высоты на первой странице. "
                "Последнее значение отступа запоминается для этой истории."
            )
        elif mode == "new":
            self.hint_label.setText(
                "Новые записи отмечены галочками. Уже напечатанные пойдут белым текстом и сохранят место на листе."
            )
        else:
            self.hint_label.setText("Все записи будут напечатаны черным текстом.")

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
        mode = self.mode_combo.currentData()
        top_offset_mm = 0
        if mode == "selected_new_page":
            html_content = self.build_print_html(visible_records, visible_ids)
        elif mode == "selected_from_offset":
            top_offset_mm = self.offset_spin.value()
            html_content = self.build_print_html(visible_records, visible_ids)
        else:
            html_content = self.build_print_html(all_records, visible_ids)

        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A4))
        if mode == "selected_from_offset":
            printer.setPageMargins(QMarginsF(15, top_offset_mm, 15, 20), QPageLayout.Millimeter)
        else:
            printer.setPageMargins(QMarginsF(15, 20, 15, 20), QPageLayout.Millimeter)

        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("Предварительный просмотр записей")

        def handle_paint(printer):
            document = QTextDocument()
            document.setDefaultFont(QFont("Segoe UI", 9))
            document.setHtml(html_content)
            _print_document_without_page_numbers(printer, document)

        preview.paintRequested.connect(handle_paint)
        preview.exec()

        if self.mode_combo.currentData() == "selected_from_offset":
            self.db.update_case_custom_print_state(self.case_id, top_offset_mm, printed_at=datetime.now().isoformat())
            self.refresh_records()
            return

        if self.mode_combo.currentData() in ("reprint", "selected_new_page"):
            return

        reply = QMessageBox.question(
            self,
            "Отметить печать",
            "Отметить видимые записи как напечатанные?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        batch_id = uuid.uuid4().hex[:10]
        printed_at = datetime.now().isoformat()
        record_ids = [record[0] for record in visible_records]
        self.db.mark_histories_printed(record_ids, batch_id, 0, printed_at=printed_at)
        self.db.update_case_diary_print_state(self.case_id, 0, batch_id, printed_at=printed_at)
        QMessageBox.information(self, "Готово", "Видимые записи отмечены как напечатанные.")
        self.refresh_records()

    def build_print_html(self, records, visible_ids, first_page_top_offset_mm=0):
        grouped = {}
        ordered_dates = []
        for record in records:
            date_key = _format_diary_date(record[2])
            if date_key not in grouped:
                grouped[date_key] = []
                ordered_dates.append(date_key)
            grouped[date_key].append(record)

        blocks = []
        prev_date = None
        for date_key in ordered_dates:
            day_records = sorted(
                grouped[date_key],
                key=lambda record: (
                    0 if record[3] == "primary_exam" else 1 if record[3] == "diary" else 2,
                    record[2] or "",
                    record[0],
                ),
            )
            child_blocks = []
            any_visible = False
            for record in day_records:
                content, _ = _record_print_content(record)
                is_visible = record[0] in visible_ids
                if is_visible:
                    any_visible = True
                else:
                    content = _make_invisible_print_html(content)
                visibility_class = "visible" if is_visible else "invisible"
                record_type = record[3]
                if record_type == "primary_exam":
                    time_text = _format_record_time(record[2])
                    date_with_time = f"Дата: {html.escape(date_key)}{' ' + time_text if time_text else ''}"
                    date_label = f"<table border='0' cellpadding='0' cellspacing='0' width='100%'><tr><td width='25%' style='white-space:nowrap;'>{date_with_time}</td><td align='center'><b>Первичный осмотр</b></td><td width='25%'></td></tr></table>"
                elif record_type == "operation_protocol":
                    time_text = _format_record_time(record[2])
                    date_with_time = f"Дата: {html.escape(date_key)}{' ' + time_text if time_text else ''}"
                    date_label = f"<table border='0' cellpadding='0' cellspacing='0' width='100%'><tr><td width='25%' style='white-space:nowrap;'>{date_with_time}</td><td align='center'><b>Протокол операции</b></td><td width='25%'></td></tr></table>"
                else:
                    date_label = ""
                record_class = "primary-record" if record_type == "primary_exam" else "standard-record"
                child_blocks.append(f"""
                    <div style="page-break-inside:avoid; break-inside:avoid;">
                    <div class="diary-date {record_class} {visibility_class}">{date_label}</div>
                    <div class="entry-item {record_class} {visibility_class}">
                        {content}
                    </div>
                    </div>
                """)

            blocks.append(f"""
                <div class="diary-entry">
                    {''.join(child_blocks)}
                </div>
                <br>
            """)

        return f"""
        <html>
        <head>
        <style>
            body {{
                margin: 0;
            }}
            .diary-entry {{
                page-break-inside: avoid;
                margin-bottom: 4mm;
            }}
            .entry-item {{
                page-break-inside: avoid;
                break-inside: avoid;
                margin-bottom: 2mm;
            }}
            .vision-block,
            .vision-block tr,
            .vision-block td,
            .vision-block table {{
                page-break-inside: avoid;
                break-inside: avoid;
            }}
            .invisible,
            .invisible * {{
                visibility: hidden;
                color: #ffffff !important;
                border-color: #ffffff !important;
                background: transparent !important;
            }}
            .diary-date {{
                margin-bottom: 2mm;
            }}
            .protocol-entry {{
                margin-top: 1mm;
            }}
            .protocol-title {{
                font-weight: bold;
                margin-bottom: 1.5mm;
            }}
            .standard-record {{
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9pt;
                line-height: 1.22;
            }}
            .standard-record table,
            .standard-record th,
            .standard-record td {{
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9pt;
            }}
            .primary-record {{
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9.5pt;
                line-height: 1.05;
            }}
            .primary-record table,
            .primary-record th,
            .primary-record td {{
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9.5pt;
            }}
        </style>
        </head>
        <body>
            {''.join(blocks)}
        </body>
        </html>
        """


class DiagnosticSelectionDialog(QDialog):
    def __init__(self, parent, diagnostics):
        super().__init__(parent)
        self.setWindowTitle("Выбрать исследования")
        self.setModal(True)
        self.resize(560, 360)
        self.diagnostics = diagnostics or []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Отметьте исследования, которые нужно вставить в эпикриз:"))

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        for diagnostic in self.diagnostics:
            study_date = diagnostic[3] or ""
            name = diagnostic[4] or "Исследование"
            result_preview = _diagnostic_results_text(name, diagnostic[5] or "").replace("\n", "; ")
            text = f"{study_date} | {name}"
            if result_preview:
                text += f" | {result_preview}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, diagnostic)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.list_widget.addItem(item)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        ok = QPushButton("Вставить")
        ok.clicked.connect(self.accept)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

    def selected_diagnostics(self):
        selected = []
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.checkState() == Qt.Checked:
                selected.append(item.data(Qt.UserRole))
        return selected


class DischargeDialog(QDialog):
    def __init__(self, parent, final_diagnosis='', outcome='', admission_date='', diagnostics=None, complaints=None, main_diagnosis=None, comorbid_diagnosis=None, primary_vis=None, db=None, patient_id=None, history_id=None):
        super().__init__(parent)
        self.setWindowTitle("Выписка пациента")
        self.setModal(True)
        self.admission_date = admission_date
        self.diagnostics = diagnostics or []
        self.complaints = complaints or ""
        self.main_diagnosis = main_diagnosis or ""
        self.comorbid_diagnosis = comorbid_diagnosis or ""
        self.primary_vis = primary_vis or {}
        self.db = db
        self.patient_id = patient_id
        self.history_id = history_id
        self.resize(820, 800)
        from PySide6.QtWidgets import QTabWidget, QScrollArea
        main_layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        # ── Вкладка 1: Общие данные ───────────────────────────────────────
        tab1 = QWidget()
        t1 = QVBoxLayout(tab1)
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
        date_row.addStretch(1)
        t1.addLayout(date_row)
        self.stay_days_label = QLabel("")
        t1.addWidget(self.stay_days_label)
        self._update_stay_days()
        t1.addWidget(QLabel("Куда направляется выписка:"))
        self.destination = QLineEdit()
        t1.addWidget(self.destination)
        t1.addWidget(QLabel("Место работы и род занятий:"))
        self.workplace = QLineEdit()
        t1.addWidget(self.workplace)
        t1.addWidget(QLabel("Исход:"))
        self.outcome_combo = QComboBox()
        self.outcome_combo.setEditable(True)
        self.outcome_combo.addItems(["улучшение", "без перемен", "ухудшение", "перевод", "смерть", "другое"])
        if outcome:
            self.outcome_combo.setCurrentText(outcome)
        t1.addWidget(self.outcome_combo)
        t1.addStretch(1)
        self.tabs.addTab(tab1, "Общие данные")

        # ── Вкладка 2: Диагноз ───────────────────────────────────────────
        tab2 = QWidget()
        t2 = QVBoxLayout(tab2)
        t2.addWidget(QLabel("Заключительный диагноз:"))
        self.final_diagnosis = QTextEdit()
        self.final_diagnosis.setPlainText(final_diagnosis)
        t2.addWidget(self.final_diagnosis)
        diag_buttons_row = QHBoxLayout()
        _btn_main = QPushButton("Взять основной диагноз")
        _btn_main.clicked.connect(self._insert_main_diagnosis)
        diag_buttons_row.addWidget(_btn_main)
        _btn_comorbid = QPushButton("Взять сопутствующий диагноз")
        _btn_comorbid.clicked.connect(self._insert_comorbid_diagnosis)
        diag_buttons_row.addWidget(_btn_comorbid)
        diag_buttons_row.addStretch(1)
        t2.addLayout(diag_buttons_row)
        self.tabs.addTab(tab2, "Диагноз")

        # ── Вкладка 3: Офт. статус ────────────────────────────────────────
        tab3_scroll = QScrollArea()
        tab3_scroll.setWidgetResizable(True)
        tab3 = QWidget()
        t3 = QVBoxLayout(tab3)
        t3.addWidget(QLabel("<b>При выписке:</b>"))
        vis_row = QHBoxLayout()
        vis_row.addWidget(QLabel("<b>Vis</b>"))
        vis_grid = QGridLayout()
        vis_grid.setHorizontalSpacing(6)
        vis_grid.setVerticalSpacing(6)
        self._build_vis_row(vis_grid, 0, "OD")
        self._build_vis_row(vis_grid, 1, "OS")
        vis_row.addLayout(vis_grid)
        vis_row.addSpacing(18)
        vis_row.addWidget(QLabel("<b>ВГД</b>"))
        vgd_grid = QGridLayout()
        vgd_grid.addWidget(QLabel("OD"), 0, 0)
        self.vgd_od = QLineEdit(); self.vgd_od.setFixedWidth(90)
        vgd_grid.addWidget(self.vgd_od, 0, 1)
        vgd_grid.addWidget(QLabel("OS"), 1, 0)
        self.vgd_os = QLineEdit(); self.vgd_os.setFixedWidth(90)
        vgd_grid.addWidget(self.vgd_os, 1, 1)
        vis_row.addLayout(vgd_grid)
        vis_row.addStretch(1)
        t3.addLayout(vis_row)
        t3.addSpacing(10)
        # ВГД max/min
        vgd_mm_row = QHBoxLayout()
        vgd_mm_row.addWidget(QLabel("<b>ВГД</b>"))
        vgd_mm_grid = QGridLayout()
        vgd_mm_grid.setHorizontalSpacing(6); vgd_mm_grid.setVerticalSpacing(4)
        vgd_mm_grid.addWidget(QLabel("OD"), 0, 0); vgd_mm_grid.addWidget(QLabel("max"), 0, 1)
        self.vgd_od_max = QLineEdit(); self.vgd_od_max.setFixedWidth(70)
        vgd_mm_grid.addWidget(self.vgd_od_max, 0, 2); vgd_mm_grid.addWidget(QLabel("min"), 0, 3)
        self.vgd_od_min = QLineEdit(); self.vgd_od_min.setFixedWidth(70)
        vgd_mm_grid.addWidget(self.vgd_od_min, 0, 4); vgd_mm_grid.addWidget(QLabel("мм. рт. ст."), 0, 5)
        vgd_mm_grid.addWidget(QLabel("OS"), 1, 0); vgd_mm_grid.addWidget(QLabel("max"), 1, 1)
        self.vgd_os_max = QLineEdit(); self.vgd_os_max.setFixedWidth(70)
        vgd_mm_grid.addWidget(self.vgd_os_max, 1, 2); vgd_mm_grid.addWidget(QLabel("min"), 1, 3)
        self.vgd_os_min = QLineEdit(); self.vgd_os_min.setFixedWidth(70)
        vgd_mm_grid.addWidget(self.vgd_os_min, 1, 4); vgd_mm_grid.addWidget(QLabel("мм. рт. ст."), 1, 5)
        vgd_mm_row.addLayout(vgd_mm_grid); vgd_mm_row.addStretch(1)
        t3.addLayout(vgd_mm_row)
        t3.addSpacing(10)
        # Эластотонометрия
        elasto_row = QHBoxLayout()
        elasto_row.addWidget(QLabel("<b>Эластотонометрия</b>"))
        elasto_grid = QGridLayout(); elasto_grid.setHorizontalSpacing(6); elasto_grid.setVerticalSpacing(4)
        elasto_grid.addWidget(QLabel("OD"), 0, 0)
        self.elasto_od = QLineEdit(); self.elasto_od.setFixedWidth(120)
        elasto_grid.addWidget(self.elasto_od, 0, 1)
        elasto_grid.addWidget(QLabel("OS"), 1, 0)
        self.elasto_os = QLineEdit(); self.elasto_os.setFixedWidth(120)
        elasto_grid.addWidget(self.elasto_os, 1, 1)
        elasto_row.addLayout(elasto_grid); elasto_row.addStretch(1)
        t3.addLayout(elasto_row)
        t3.addSpacing(10)
        # Тонография по Нестерову
        tono_grid = QGridLayout(); tono_grid.setHorizontalSpacing(6); tono_grid.setVerticalSpacing(4)
        tono_grid.addWidget(QLabel("<b>Тонография по Нестерову</b>"), 0, 0, 1, 9)
        for col, lbl in enumerate(["Ро", "С", "КБ", "F"]):
            tono_grid.addWidget(QLabel(lbl), 1, col * 2 + 1)
        tono_grid.addWidget(QLabel("OD"), 2, 0)
        self.tono_od_ro = QLineEdit(); self.tono_od_ro.setFixedWidth(55)
        self.tono_od_c  = QLineEdit(); self.tono_od_c.setFixedWidth(55)
        self.tono_od_kb = QLineEdit(); self.tono_od_kb.setFixedWidth(55)
        self.tono_od_f  = QLineEdit(); self.tono_od_f.setFixedWidth(55)
        for i, w in enumerate([self.tono_od_ro, self.tono_od_c, self.tono_od_kb, self.tono_od_f]):
            tono_grid.addWidget(w, 2, i * 2 + 1)
        tono_grid.addWidget(QLabel("OS"), 3, 0)
        self.tono_os_ro = QLineEdit(); self.tono_os_ro.setFixedWidth(55)
        self.tono_os_c  = QLineEdit(); self.tono_os_c.setFixedWidth(55)
        self.tono_os_kb = QLineEdit(); self.tono_os_kb.setFixedWidth(55)
        self.tono_os_f  = QLineEdit(); self.tono_os_f.setFixedWidth(55)
        for i, w in enumerate([self.tono_os_ro, self.tono_os_c, self.tono_os_kb, self.tono_os_f]):
            tono_grid.addWidget(w, 3, i * 2 + 1)
        t3.addLayout(tono_grid)
        t3.addStretch(1)
        tab3_scroll.setWidget(tab3)
        self.tabs.addTab(tab3_scroll, "Офт. статус")

        # ── Вкладка 4: Лечение ────────────────────────────────────────────
        tab4 = QWidget()
        t4 = QVBoxLayout(tab4)
        t4.addWidget(QLabel("Лечение:"))
        self.treatment_summary = QTextEdit()
        self.treatment_summary.setPlaceholderText("Препараты через запятую (авто или вручную)")
        t4.addWidget(self.treatment_summary)
        self.tabs.addTab(tab4, "Лечение")

        # ── Вкладка 5: Эпикриз ───────────────────────────────────────────
        tab5_scroll = QScrollArea()
        tab5_scroll.setWidgetResizable(True)
        tab5 = QWidget()
        t5 = QVBoxLayout(tab5)

        # Местный статус при выписке
        t5.addWidget(QLabel("<b>Местный статус при выписке:</b>"))
        local_grid = QGridLayout()
        local_grid.setHorizontalSpacing(8)
        local_grid.setVerticalSpacing(4)
        local_grid.addWidget(QLabel("<b>Позиция</b>"), 0, 0)
        local_grid.addWidget(QLabel("<b>OD</b>"), 0, 1, Qt.AlignCenter)
        local_grid.addWidget(QLabel("<b>OS</b>"), 0, 2, Qt.AlignCenter)
        self.discharge_local_fields = {}
        _row = 1
        for _label, _opts in LOCAL_ROWS_CONFIG.items():
            local_grid.addWidget(QLabel(_label), _row, 0)
            if _opts is None and _label == "Передняя камера":
                def _make_ac():
                    w = QWidget()
                    lay = QHBoxLayout(w); lay.setContentsMargins(0,0,0,0); lay.setSpacing(4)
                    depth = QComboBox(); depth.setEditable(True)
                    depth.addItems(["", "нормальная", "мелкая", "глубокая"]); depth.setFixedWidth(120)
                    fluid = QComboBox(); fluid.setEditable(True)
                    fluid.addItems(["", "прозрачная", "мутная", "гифема", "гипопион", "фибрин"]); fluid.setFixedWidth(140)
                    lay.addWidget(QLabel("гл.")); lay.addWidget(depth)
                    lay.addWidget(QLabel("вл.")); lay.addWidget(fluid); lay.addStretch()
                    return w, depth, fluid
                od_w, od_depth, od_fluid = _make_ac()
                os_w, os_depth, os_fluid = _make_ac()
                local_grid.addWidget(od_w, _row, 1)
                local_grid.addWidget(os_w, _row, 2)
                self.discharge_local_fields[_label] = ((od_depth, od_fluid), (os_depth, os_fluid))
            else:
                od_btn = MultiSelectButton(f"{_label} (OD)", _opts)
                os_btn = MultiSelectButton(f"{_label} (OS)", _opts)
                local_grid.addWidget(od_btn, _row, 1)
                local_grid.addWidget(os_btn, _row, 2)
                self.discharge_local_fields[_label] = (od_btn, os_btn)
            _row += 1
        t5.addLayout(local_grid)

        t5.addWidget(QLabel("<b>Эпикриз:</b>"))
        self.epicrisis = QTextEdit()
        t5.addWidget(self.epicrisis)
        epicrisis_actions = QHBoxLayout()
        insert_diagnostics_button = QPushButton("Добавить исследования в эпикриз")
        insert_diagnostics_button.setStyleSheet("background-color: #f1c40f; color: #222;")
        insert_diagnostics_button.clicked.connect(self._insert_diagnostics_into_epicrisis)
        epicrisis_actions.addWidget(insert_diagnostics_button)
        self._insert_complaints_button = QPushButton("Жалобы из осмотра")
        self._insert_complaints_button.clicked.connect(self._insert_complaints_into_epicrisis)
        epicrisis_actions.addWidget(self._insert_complaints_button)
        self._insert_local_od_button = QPushButton("OD")
        self._insert_local_od_button.setFixedWidth(44)
        self._insert_local_od_button.clicked.connect(lambda: self._insert_local_status_into_epicrisis("OD"))
        epicrisis_actions.addWidget(self._insert_local_od_button)
        self._insert_local_os_button = QPushButton("OS")
        self._insert_local_os_button.setFixedWidth(44)
        self._insert_local_os_button.clicked.connect(lambda: self._insert_local_status_into_epicrisis("OS"))
        epicrisis_actions.addWidget(self._insert_local_os_button)
        self._insert_local_ou_button = QPushButton("OU")
        self._insert_local_ou_button.setFixedWidth(44)
        self._insert_local_ou_button.clicked.connect(lambda: self._insert_epicrisis_marker("OU"))
        epicrisis_actions.addWidget(self._insert_local_ou_button)
        epicrisis_actions.addStretch(1)
        t5.addLayout(epicrisis_actions)
        tab5_scroll.setWidget(tab5)
        self.tabs.addTab(tab5_scroll, "Эпикриз")

        # ── Вкладка 6: Рекомендации ───────────────────────────────────────
        tab6 = QWidget()
        t6 = QVBoxLayout(tab6)
        t6.addWidget(QLabel("Лечебные и трудовые рекомендации:"))
        self.recommendations = QTextEdit()
        t6.addWidget(self.recommendations)
        self.tabs.addTab(tab6, "Рекомендации")

        # ── Нижняя панель (вне вкладок) ──────────────────────────────────
        sig_row = QHBoxLayout()
        sig_row.addWidget(QLabel("Подписи на печати:"))
        self.sig_dep_chief = QCheckBox("Зам. гл. врача")
        self.sig_chief = QCheckBox("Гл. врач")
        sig_row.addWidget(self.sig_dep_chief)
        sig_row.addWidget(self.sig_chief)
        sig_row.addStretch(1)
        main_layout.addLayout(sig_row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.next_button = QPushButton("Далее")
        self.next_button.clicked.connect(self._handle_next_or_save)
        buttons.addWidget(self.next_button)
        main_layout.addLayout(buttons)
        self.tabs.currentChanged.connect(self._update_navigation_button)
        self._update_navigation_button()

        # Авто-заполнить лечение при создании новой выписки
        if self.db and self.patient_id and self.history_id:
            ts = self._collect_treatment_summary()
            if ts:
                self.treatment_summary.setPlainText(ts)

    def load_existing(self, history, case=None):
        payload = _load_discharge_payload(history[7] if history else "")
        plain = _html_plain(history[4] if history else "")
        self.destination.setText(_extract_after_label(plain, "Куда направляется выписка"))
        if case and case[5]:
            self.discharge_date.setText(case[5])
        else:
            date_text = _extract_after_label(plain, "Дата выписки")
            if date_text:
                self.discharge_date.setText(date_text[:10])
        if case and case[6]:
            self.discharge_time.setText(case[6])
        self.workplace.setText(_extract_after_label(plain, "Место работы и род занятий"))
        if case and case[7]:
            self.outcome_combo.setCurrentText(case[7])
        self.final_diagnosis.setPlainText((case[9] if case else "") or (history[5] if history else ""))
        self.epicrisis.setPlainText((case[10] if case else "") or payload.get("epicrisis", ""))
        self.recommendations.setPlainText((case[11] if case else "") or payload.get("recommendations", "") or (history[6] if history else ""))
        self.vis_od.setText(payload.get("vis_od", ""))
        self.vis_os.setText(payload.get("vis_os", ""))
        self.vis_correction_od.setCurrentText(payload.get("vis_correction_od", "пусто"))
        self.vis_correction_os.setCurrentText(payload.get("vis_correction_os", "пусто"))
        self.vis_od_corr.setText(payload.get("vis_od_corr", ""))
        self.vis_os_corr.setText(payload.get("vis_os_corr", ""))
        self.vis_od_result.setText(payload.get("vis_od_result", ""))
        self.vis_os_result.setText(payload.get("vis_os_result", ""))
        self.vgd_od.setText(payload.get("vgd_od", ""))
        self.vgd_os.setText(payload.get("vgd_os", ""))
        self.vgd_od_max.setText(payload.get("vgd_od_max", ""))
        self.vgd_od_min.setText(payload.get("vgd_od_min", ""))
        self.vgd_os_max.setText(payload.get("vgd_os_max", ""))
        self.vgd_os_min.setText(payload.get("vgd_os_min", ""))
        self.elasto_od.setText(payload.get("elasto_od", ""))
        self.elasto_os.setText(payload.get("elasto_os", ""))
        self.tono_od_ro.setText(payload.get("tono_od_ro", ""))
        self.tono_od_c.setText(payload.get("tono_od_c", ""))
        self.tono_od_kb.setText(payload.get("tono_od_kb", ""))
        self.tono_od_f.setText(payload.get("tono_od_f", ""))
        self.tono_os_ro.setText(payload.get("tono_os_ro", ""))
        self.tono_os_c.setText(payload.get("tono_os_c", ""))
        self.tono_os_kb.setText(payload.get("tono_os_kb", ""))
        self.tono_os_f.setText(payload.get("tono_os_f", ""))
        # Лечение: из payload или авто-собрать
        _saved_ts = payload.get("treatment_summary", "")
        if _saved_ts:
            self.treatment_summary.setPlainText(_saved_ts)
        else:
            self.treatment_summary.setPlainText(self._collect_treatment_summary())
        self.sig_dep_chief.setChecked(bool(payload.get("sig_dep_chief", False)))
        self.sig_chief.setChecked(bool(payload.get("sig_chief", False)))
        self._apply_discharge_local(payload.get("discharge_local") or {})
        self._update_stay_days()

    def _update_navigation_button(self, *_args):
        if self.tabs.currentIndex() >= self.tabs.count() - 1:
            self.next_button.setText("Сохранить выписку")
        else:
            self.next_button.setText("Далее")

    def _handle_next_or_save(self):
        current_index = self.tabs.currentIndex()
        last_index = self.tabs.count() - 1
        if current_index >= last_index:
            self.accept()
            return
        self.tabs.setCurrentIndex(current_index + 1)

    def _insert_diagnostics_into_epicrisis(self):
        if not self.diagnostics:
            QMessageBox.information(self, "Исследования", "В этой истории пока нет диагностических исследований.")
            return

        dialog = DiagnosticSelectionDialog(self, self.diagnostics)
        if dialog.exec() != QDialog.Accepted:
            return

        selected = dialog.selected_diagnostics()
        if not selected:
            QMessageBox.warning(self, "Исследования", "Выберите хотя бы одно исследование.")
            return

        lines = []
        for diagnostic in selected:
            study_date = (diagnostic[3] or "").strip()
            name = (diagnostic[4] or "Исследование").strip()
            result_text = _diagnostic_results_text(name, diagnostic[5] or "").strip().replace("\n", "; ")
            line = f"{study_date} {name}".strip()
            if result_text:
                line = f"{line}: {result_text}" if line else result_text
            if line:
                lines.append(line)

        if not lines:
            return

        block = "Диагностические исследования:\n" + "\n".join(lines)
        current = self.epicrisis.toPlainText().strip()
        self.epicrisis.setPlainText(f"{current}\n\n{block}".strip() if current else block)

    def _insert_main_diagnosis(self):
        if not self.main_diagnosis:
            QMessageBox.information(self, "Диагноз", "Основной диагноз в первичном осмотре не указан.")
            return
        self.final_diagnosis.setPlainText(self.main_diagnosis)
        self.final_diagnosis.setFocus()

    def _insert_comorbid_diagnosis(self):
        if not self.comorbid_diagnosis:
            QMessageBox.information(self, "Диагноз", "Сопутствующий диагноз в первичном осмотре не указан.")
            return
        current = self.final_diagnosis.toPlainText().strip()
        sep = "\n" if current else ""
        self.final_diagnosis.setPlainText(f"{current}{sep}{self.comorbid_diagnosis}")
        self.final_diagnosis.setFocus()

    def _insert_complaints_into_epicrisis(self):
        if not self.complaints:
            QMessageBox.information(self, "Жалобы", "В первичном осмотре нет данных о жалобах.")
            return
        cursor = self.epicrisis.textCursor()
        cursor.insertText(f"Со слов пациента жалобы {self.complaints}")
        self.epicrisis.setTextCursor(cursor)
        self.epicrisis.setFocus()

    def _insert_epicrisis_marker(self, marker):
        cursor = self.epicrisis.textCursor()
        prefix = ""
        if self.epicrisis.toPlainText() and not cursor.atBlockStart():
            prefix = "\n"
        cursor.insertText(f"{prefix}{marker}: ")
        self.epicrisis.setTextCursor(cursor)
        self.epicrisis.setFocus()

    def _insert_local_status_into_epicrisis(self, eye):
        line = self._build_local_status_line_for_eye(eye)
        if not line:
            QMessageBox.information(self, "Местный статус", f"Для {eye} в форме пока нет заполненных данных.")
            return
        cursor = self.epicrisis.textCursor()
        prefix = ""
        if self.epicrisis.toPlainText() and not cursor.atBlockStart():
            prefix = "\n"
        cursor.insertText(prefix + line)
        self.epicrisis.setTextCursor(cursor)
        self.epicrisis.setFocus()

    def _build_vis_row(self, grid, row, eye):
        grid.addWidget(QLabel(eye), row, 0)
        value = QLineEdit()
        value.setFixedWidth(60)
        grid.addWidget(value, row, 1)

        correction = QComboBox()
        correction.addItems([
            "пусто",
            "с коррекцией",
            "n.k. (не коррег.)",
            "счет пальцев у лица",
            "движ. руки у лица",
            "pr. certa",
            "pr. incerta",
            "(ноль)",
            "анофтальм",
            "эксцентрично",
        ])
        correction.setFixedWidth(155)
        grid.addWidget(correction, row, 2)

        corr_value = QLineEdit()
        corr_value.setFixedWidth(60)
        grid.addWidget(corr_value, row, 3)
        eq_label = QLabel("=")
        grid.addWidget(eq_label, row, 4, Qt.AlignCenter)
        result = QLineEdit()
        result.setFixedWidth(60)
        grid.addWidget(result, row, 5)

        setattr(self, f"vis_{eye.lower()}", value)
        setattr(self, f"vis_correction_{eye.lower()}", correction)
        setattr(self, f"vis_{eye.lower()}_corr", corr_value)
        setattr(self, f"vis_{eye.lower()}_result", result)
        setattr(self, f"vis_eq_{eye.lower()}_label", eq_label)

        correction.currentTextChanged.connect(lambda _text, e=eye: self._update_vis_corr_fields(e))
        self._update_vis_corr_fields(eye)

    def _update_vis_corr_fields(self, eye):
        correction = getattr(self, f"vis_correction_{eye.lower()}")
        corr_value = getattr(self, f"vis_{eye.lower()}_corr")
        result = getattr(self, f"vis_{eye.lower()}_result")
        eq_label = getattr(self, f"vis_eq_{eye.lower()}_label")
        enabled = correction.currentText() == "с коррекцией"
        for widget in (corr_value, result):
            widget.setEnabled(enabled)
            widget.setStyleSheet("" if enabled else "background-color: #e0e0e0; color: #888;")
            if not enabled:
                widget.clear()
        eq_label.setEnabled(enabled)

    def _stay_days(self):
        start = _parse_ru_date(self.admission_date)
        end = _parse_ru_date(self.discharge_date.text())
        if not start or not end:
            return ""
        return str((end - start).days + 1)

    def _get_discharge_local(self):
        local = {}
        for label, widgets in self.discharge_local_fields.items():
            if label == "Передняя камера":
                (od_depth, od_fluid), (os_depth, os_fluid) = widgets
                local[label] = {
                    "od_depth": od_depth.currentText(),
                    "od_fluid": od_fluid.currentText(),
                    "os_depth": os_depth.currentText(),
                    "os_fluid": os_fluid.currentText(),
                }
            else:
                od_btn, os_btn = widgets
                local[label] = {
                    "od_selected": list(getattr(od_btn, '_selected', [])),
                    "od_note": getattr(od_btn, '_note', ''),
                    "os_selected": list(getattr(os_btn, '_selected', [])),
                    "os_note": getattr(os_btn, '_note', ''),
                }
        return local

    def _apply_discharge_local(self, local):
        if not local:
            return
        for label, widgets in self.discharge_local_fields.items():
            data = local.get(label)
            if not data:
                continue
            if label == "Передняя камера":
                (od_depth, od_fluid), (os_depth, os_fluid) = widgets
                od_depth.setCurrentText(data.get("od_depth", ""))
                od_fluid.setCurrentText(data.get("od_fluid", ""))
                os_depth.setCurrentText(data.get("os_depth", ""))
                os_fluid.setCurrentText(data.get("os_fluid", ""))
            else:
                od_btn, os_btn = widgets
                od_btn._selected = list(data.get("od_selected") or [])
                od_btn._note = data.get("od_note", "")
                od_btn._refresh_text()
                os_btn._selected = list(data.get("os_selected") or [])
                os_btn._note = data.get("os_note", "")
                os_btn._refresh_text()

    def _build_local_status_line_for_eye(self, eye):
        eye_key = eye.lower()
        parts = []
        for label, widgets in self.discharge_local_fields.items():
            if isinstance(widgets[0], tuple):  # Передняя камера
                (od_depth, od_fluid), (os_depth, os_fluid) = widgets
                if eye_key == "od":
                    depth = od_depth.currentText().strip()
                    fluid = od_fluid.currentText().strip()
                else:
                    depth = os_depth.currentText().strip()
                    fluid = os_fluid.currentText().strip()
                if depth or fluid:
                    subparts = []
                    if depth:
                        subparts.append(f"глубина {depth}")
                    if fluid:
                        subparts.append(f"влага {fluid}")
                    parts.append(f"{label} - {', '.join(subparts)}")
            else:
                od_btn, os_btn = widgets
                text = (od_btn.get_text() if eye_key == "od" else os_btn.get_text()).strip()
                if text:
                    parts.append(f"{label} - {text}")
        if not parts:
            return ""
        return f"{eye}: " + ", ".join(parts)

    def _build_local_status_lines(self):
        lines = []
        od_line = self._build_local_status_line_for_eye("OD")
        os_line = self._build_local_status_line_for_eye("OS")
        if od_line:
            lines.append(od_line)
        if os_line:
            lines.append(os_line)
        return lines

    def _collect_treatment_summary(self):
        """Собрать список названий лекарств из первички и дневников."""
        import re as _re
        _TREAT_CATS = [
            "angio_retino", "metabolism", "desensitization", "antibiotics",
            "angioprotectors", "myotics", "biostimulators", "vasodilators",
            "analgesics", "antiaggregants", "antifungal", "mydriatics",
            "k_sparing", "anesthetics", "hypoglycemic", "hypotensive",
            "diuretic", "antithrombotic",
        ]
        def _name_only(med):
            m = _re.match(r'^([А-яA-Za-zёЁ][А-яA-Za-zёЁ-]*)', med.strip())
            return m.group(1) if m else med.split()[0] if med.strip() else ""

        def _extract(basis_dict, seen):
            result = []
            for cat in _TREAT_CATS:
                for v in ((basis_dict or {}).get(cat) or {}).get("selected") or []:
                    name = _name_only(str(v))
                    if name and name not in seen:
                        seen.add(name)
                        result.append(name)
            return result

        meds, seen = [], set()
        try:
            _pe = self.db.get_history_record(self.patient_id, "primary_exam", self.history_id)
            if _pe:
                _pn = json.loads(_pe[7] or "")
                if isinstance(_pn, dict):
                    meds.extend(_extract(_pn.get("treatment") or {}, seen))
        except Exception:
            pass
        try:
            for _dr in self.db.get_diary_records_for_case(self.patient_id, self.history_id):
                if _dr[3] != "diary":
                    continue
                try:
                    _dn = json.loads(_dr[7] or "")
                    if isinstance(_dn, dict):
                        meds.extend(_extract(_dn.get("basis") or {}, seen))
                except Exception:
                    pass
        except Exception:
            pass
        return ", ".join(meds)

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
            "epicrisis": self.epicrisis.toPlainText().strip(),
            "recommendations": self.recommendations.toPlainText().strip(),
            "vis_od": self.vis_od.text().strip(),
            "vis_os": self.vis_os.text().strip(),
            "vis_correction_od": self.vis_correction_od.currentText().strip(),
            "vis_correction_os": self.vis_correction_os.currentText().strip(),
            "vis_od_corr": self.vis_od_corr.text().strip(),
            "vis_os_corr": self.vis_os_corr.text().strip(),
            "vis_od_result": self.vis_od_result.text().strip(),
            "vis_os_result": self.vis_os_result.text().strip(),
            "vgd_od": self.vgd_od.text().strip(),
            "vgd_os": self.vgd_os.text().strip(),
            "vgd_od_max": self.vgd_od_max.text().strip(),
            "vgd_od_min": self.vgd_od_min.text().strip(),
            "vgd_os_max": self.vgd_os_max.text().strip(),
            "vgd_os_min": self.vgd_os_min.text().strip(),
            "elasto_od": self.elasto_od.text().strip(),
            "elasto_os": self.elasto_os.text().strip(),
            "tono_od_ro": self.tono_od_ro.text().strip(),
            "tono_od_c": self.tono_od_c.text().strip(),
            "tono_od_kb": self.tono_od_kb.text().strip(),
            "tono_od_f": self.tono_od_f.text().strip(),
            "tono_os_ro": self.tono_os_ro.text().strip(),
            "tono_os_c": self.tono_os_c.text().strip(),
            "tono_os_kb": self.tono_os_kb.text().strip(),
            "tono_os_f": self.tono_os_f.text().strip(),
            "treatment_summary": self.treatment_summary.toPlainText().strip(),
            "sig_dep_chief": self.sig_dep_chief.isChecked(),
            "sig_chief": self.sig_chief.isChecked(),
            "discharge_local": self._get_discharge_local(),
            "local_status_text": "\n".join(self._build_local_status_lines()).strip(),
        }


class DiagnosticDialog(QDialog):
    def __init__(self, parent, done_callback=None):
        super().__init__(parent)
        self.setWindowTitle("Исследование")
        self.setModal(True)
        self.done_callback = done_callback
        self.form_widgets = {}
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Дата исследования:"))
        self.date_edit = QLineEdit()
        self.date_edit.setText(datetime.now().strftime("%d.%m.%Y"))
        layout.addWidget(self.date_edit)

        layout.addWidget(QLabel("Тип исследования:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(DIAGNOSTIC_TYPES)
        layout.addWidget(self.type_combo)

        self.form_stack = QStackedWidget()
        layout.addWidget(self.form_stack)

        self.form_stack.addWidget(self._build_fg_form())
        self.form_stack.addWidget(self._build_mrs_form())
        self.form_stack.addWidget(self._build_oam_form())
        self.form_stack.addWidget(self._build_sugar_form())
        self.form_stack.addWidget(self._build_oak_form())
        self.form_stack.addWidget(self._build_ekg_form())
        self.form_stack.addWidget(self._build_free_form())
        self.type_combo.currentIndexChanged.connect(self.form_stack.setCurrentIndex)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        ok = QPushButton("Сохранить")
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._on_ok)

    def _make_form_host(self):
        host = QWidget()
        host.setLayout(QFormLayout())
        host.layout().setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        host.layout().setLabelAlignment(Qt.AlignLeft)
        return host

    def _add_line(self, host, key, label, width=None, default=""):
        edit = QLineEdit()
        edit.setText(default)
        if width is not None:
            edit.setFixedWidth(width)
        host.layout().addRow(label, edit)
        self.form_widgets[key] = edit
        return edit

    def _add_combo(self, host, key, label, items, editable=True):
        combo = QComboBox()
        combo.addItems(items)
        combo.setEditable(editable)
        host.layout().addRow(label, combo)
        self.form_widgets[key] = combo
        return combo

    def _add_text(self, host, key, label, height=70):
        edit = QTextEdit()
        edit.setMaximumHeight(height)
        host.layout().addRow(label, edit)
        self.form_widgets[key] = edit
        return edit

    def _build_fg_form(self):
        host = self._make_form_host()
        self._add_line(host, "fg_number", "Номер флюорографии:")
        self._add_combo(host, "fg_result", "Результат:", ["без патологии", "норма", "патология выявлена"])
        return host

    def _build_mrs_form(self):
        host = self._make_form_host()
        self._add_combo(host, "mrs_result", "Результат:", ["отрицательная", "положительная", "сомнительная"])
        self._add_line(host, "mrs_titer", "Титр:")
        self._add_text(host, "mrs_comment", "Комментарий:")
        return host

    def _build_oam_form(self):
        host = self._make_form_host()
        self._add_line(host, "oam_gravity", "Уд. вес:")
        self._add_line(host, "oam_ph", "pH:")
        self._add_line(host, "oam_protein", "Белок:")
        self._add_line(host, "oam_glucose", "Сахар:")
        self._add_line(host, "oam_leukocytes", "Лейкоциты:")
        self._add_line(host, "oam_erythrocytes", "Эритроциты:")
        self._add_line(host, "oam_epithelium", "Эпителий:")
        self._add_line(host, "oam_salts", "Соли:")
        self._add_line(host, "oam_bacteria", "Бактерии:")
        self._add_text(host, "oam_note", "Примечание:")
        return host

    def _build_sugar_form(self):
        host = self._make_form_host()
        self._add_line(host, "sugar_value", "Глюкоза, ммоль/л:")
        self._add_text(host, "sugar_note", "Примечание:")
        return host

    def _build_oak_form(self):
        host = self._make_form_host()
        self._add_line(host, "oak_hemoglobin", "Hb, г/л:")
        self._add_line(host, "oak_rbc", "Эритроциты:")
        self._add_line(host, "oak_wbc", "Лейкоциты:")
        self._add_line(host, "oak_platelets", "Тромбоциты:")
        self._add_line(host, "oak_esr", "СОЭ, мм/ч:")
        self._add_line(host, "oak_stab", "Палочкоядерные, %:")
        self._add_line(host, "oak_segmented", "Сегментоядерные, %:")
        self._add_line(host, "oak_eosinophils", "Эозинофилы, %:")
        self._add_line(host, "oak_lymphocytes", "Лимфоциты, %:")
        self._add_line(host, "oak_monocytes", "Моноциты, %:")
        self._add_line(host, "oak_color_index", "Цветовой показатель:")
        self._add_text(host, "oak_note", "Примечание:")
        return host

    def _build_ekg_form(self):
        host = self._make_form_host()
        self._add_text(host, "ekg_results", "Результаты:", height=120)
        return host

    def _build_free_form(self):
        host = self._make_form_host()
        self._add_line(host, "free_name", "Название:")
        self._add_text(host, "free_results", "Результаты:", height=120)
        return host

    def _widget_value(self, key):
        widget = self.form_widgets[key]
        if isinstance(widget, QTextEdit):
            return widget.toPlainText().strip()
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        return widget.text().strip()

    def _set_widget_value(self, key, value):
        widget = self.form_widgets[key]
        text = value or ""
        if isinstance(widget, QTextEdit):
            widget.setPlainText(text)
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(text)
        else:
            widget.setText(text)

    def load_existing(self, name, results):
        payload = _diagnostic_payload_from_results(results)
        if not payload:
            self.type_combo.setCurrentText("Свободная форма")
            self._set_widget_value("free_name", name or "")
            self._set_widget_value("free_results", results or "")
            return

        diag_type = payload.get("type") or "Свободная форма"
        self.type_combo.setCurrentText(diag_type if diag_type in DIAGNOSTIC_TYPES else "Свободная форма")
        fields = payload.get("fields") or {}
        mapping = {
            "Флюорография (ФГ)": {
                "fg_number": "number",
                "fg_result": "result",
            },
            "МРС": {
                "mrs_result": "result",
                "mrs_titer": "titer",
                "mrs_comment": "comment",
            },
            "ОАМ": {
                "oam_gravity": "gravity",
                "oam_ph": "ph",
                "oam_protein": "protein",
                "oam_glucose": "glucose",
                "oam_leukocytes": "leukocytes",
                "oam_erythrocytes": "erythrocytes",
                "oam_epithelium": "epithelium",
                "oam_salts": "salts",
                "oam_bacteria": "bacteria",
                "oam_note": "note",
            },
            "Сахар крови": {
                "sugar_value": "value",
                "sugar_note": "note",
            },
            "ОАК": {
                "oak_hemoglobin": "hemoglobin",
                "oak_rbc": "rbc",
                "oak_wbc": "wbc",
                "oak_platelets": "platelets",
                "oak_esr": "esr",
                "oak_stab": "stab",
                "oak_segmented": "segmented",
                "oak_eosinophils": "eosinophils",
                "oak_lymphocytes": "lymphocytes",
                "oak_monocytes": "monocytes",
                "oak_color_index": "color_index",
                "oak_note": "note",
            },
            "ЭКГ": {
                "ekg_results": "results",
            },
        }
        if diag_type == "Свободная форма":
            self._set_widget_value("free_name", name or payload.get("name") or "")
            self._set_widget_value("free_results", payload.get("text") or results or "")
            return
        for widget_key, field_key in mapping.get(diag_type, {}).items():
            self._set_widget_value(widget_key, fields.get(field_key, ""))

    def _build_payload(self):
        diag_type = self.type_combo.currentText().strip()
        if diag_type == "Флюорография (ФГ)":
            fields = {
                "number": self._widget_value("fg_number"),
                "result": self._widget_value("fg_result"),
            }
            return diag_type, {
                "schema": "diagnostic_form_v1",
                "type": diag_type,
                "fields": fields,
            }
        if diag_type == "МРС":
            fields = {
                "result": self._widget_value("mrs_result"),
                "titer": self._widget_value("mrs_titer"),
                "comment": self._widget_value("mrs_comment"),
            }
            return diag_type, {
                "schema": "diagnostic_form_v1",
                "type": diag_type,
                "fields": fields,
            }
        if diag_type == "ОАМ":
            fields = {
                "gravity": self._widget_value("oam_gravity"),
                "ph": self._widget_value("oam_ph"),
                "protein": self._widget_value("oam_protein"),
                "glucose": self._widget_value("oam_glucose"),
                "leukocytes": self._widget_value("oam_leukocytes"),
                "erythrocytes": self._widget_value("oam_erythrocytes"),
                "epithelium": self._widget_value("oam_epithelium"),
                "salts": self._widget_value("oam_salts"),
                "bacteria": self._widget_value("oam_bacteria"),
                "note": self._widget_value("oam_note"),
            }
            return diag_type, {
                "schema": "diagnostic_form_v1",
                "type": diag_type,
                "fields": fields,
            }
        if diag_type == "Сахар крови":
            fields = {
                "value": self._widget_value("sugar_value"),
                "note": self._widget_value("sugar_note"),
            }
            return diag_type, {
                "schema": "diagnostic_form_v1",
                "type": diag_type,
                "fields": fields,
            }
        if diag_type == "ОАК":
            fields = {
                "hemoglobin": self._widget_value("oak_hemoglobin"),
                "rbc": self._widget_value("oak_rbc"),
                "wbc": self._widget_value("oak_wbc"),
                "platelets": self._widget_value("oak_platelets"),
                "esr": self._widget_value("oak_esr"),
                "stab": self._widget_value("oak_stab"),
                "segmented": self._widget_value("oak_segmented"),
                "eosinophils": self._widget_value("oak_eosinophils"),
                "lymphocytes": self._widget_value("oak_lymphocytes"),
                "monocytes": self._widget_value("oak_monocytes"),
                "color_index": self._widget_value("oak_color_index"),
                "note": self._widget_value("oak_note"),
            }
            return diag_type, {
                "schema": "diagnostic_form_v1",
                "type": diag_type,
                "fields": fields,
            }
        if diag_type == "ЭКГ":
            fields = {"results": self._widget_value("ekg_results")}
            return diag_type, {
                "schema": "diagnostic_form_v1",
                "type": diag_type,
                "fields": fields,
            }
        name = self._widget_value("free_name")
        text = self._widget_value("free_results")
        return (name or "Исследование"), text

    def _name_and_results(self):
        name, payload = self._build_payload()
        if isinstance(payload, dict):
            return name, json.dumps(payload, ensure_ascii=False)
        return name, payload

    def _on_ok(self):
        name, results = self._name_and_results()
        res = {
            "date": self.date,
            "name": name,
            "results": results,
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
        name, _ = self._name_and_results()
        return name

    @property
    def results(self):
        _, results = self._name_and_results()
        return results
