import sys
import os
import re
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QScrollArea, QTextEdit, QComboBox, QFrame, QMessageBox, QMenu,
    QSplitter, QTabWidget, QListWidget, QAbstractItemView, QDialog,
    QTableWidget, QTableWidgetItem, QDateEdit
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction, QFont, QTextDocument, QColor
from database import Database
from windows.stationary_card import StationaryCardPage
from windows.add_record import AddRecordWindow
from windows.primary_exam import PrimaryExamWindow
from windows.edit_record import EditRecordWindow
from windows.create_history_wizard import CreateHistoryWizard
from PySide6.QtWidgets import QStackedWidget, QToolBar
from address_book import get_cities, get_streets, remember_address
from app_version import app_title

SORT_ROLE = Qt.UserRole + 50

class SortableTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        left = self.data(SORT_ROLE)
        right = other.data(SORT_ROLE) if other is not None else None
        if left is not None and right is not None:
            return left < right
        return super().__lt__(other)

class MedicalApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.setWindowTitle(app_title())
        self.resize(1024, 768)
        self.center_on_screen()
        self.create_widgets()
        self.load_patients()
        # Navigation manager (stack of pages)
        self.navigation = QStackedWidget()
        # We'll place navigation on top of central layout when needed
        # Initially hidden
        self.navigation.hide()
        # attach navigation to main layout created in create_widgets
        try:
            self.main_layout.addWidget(self.navigation)
        except Exception:
            pass
        # Back action in a toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        self.back_action = QAction("Назад", self)
        self.back_action.triggered.connect(self._nav_back)
        self.back_action.setEnabled(False)
        toolbar.addAction(self.back_action)
        self.manage_diag_action = QAction("Управление диагнозами", self)
        self.manage_diag_action.triggered.connect(self._open_diagnosis_manager)
        toolbar.addAction(self.manage_diag_action)
        self._nav_stack = []

    def center_on_screen(self):
        # Center the main window on the available screen area
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen().availableGeometry()
        size = self.geometry()
        x = (screen.width() - size.width()) // 2
        y = (screen.height() - size.height()) // 2
        self.move(x, y)

    def create_widgets(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        # store main layout so other methods can access it
        self.main_layout = layout

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Поиск по ФИО, номеру карты, диагнозу:"))
        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("ФИО, номер карты или диагноз")
        self.search_entry.textChanged.connect(self.filter_patients)
        search_layout.addWidget(self.search_entry)

        # Buttons
        button_layout = QHBoxLayout()
        self.new_button = QPushButton("Добавить")
        self.new_button.clicked.connect(self.new_patient)
        # green = add
        self.new_button.setStyleSheet("background-color: #2ecc71; color: white; font-weight: 600;")
        button_layout.addWidget(self.new_button)

        self.edit_button = QPushButton("Редактировать")
        self.edit_button.clicked.connect(self.fill_patient)
        self.edit_button.setEnabled(False)
        # yellow = edit
        self.edit_button.setStyleSheet("background-color: #f1c40f; color: black; font-weight: 600;")
        button_layout.addWidget(self.edit_button)

        self.refresh_button = QPushButton("🔄 Обновить")
        self.refresh_button.clicked.connect(self.load_patients)
        # blue = refresh
        self.refresh_button.setStyleSheet("background-color: #3498db; color: white; font-weight: 600;")
        button_layout.addWidget(self.refresh_button)

        self.delete_history_button = QPushButton("Удалить историю")
        self.delete_history_button.clicked.connect(self.delete_history)
        self.delete_history_button.setEnabled(False)
        # red = delete
        self.delete_history_button.setStyleSheet("background-color: #e74c3c; color: white; font-weight: 600;")
        button_layout.addWidget(self.delete_history_button)

        self.delete_button = QPushButton("Удалить пациента")
        self.delete_button.clicked.connect(self.delete_patient)
        # red = delete
        self.delete_button.setStyleSheet("background-color: #e74c3c; color: white; font-weight: 600;")
        button_layout.addWidget(self.delete_button)

        search_layout.addLayout(button_layout)
        layout.addLayout(search_layout)

        self.inpatient_count_label = QLabel("0")
        self.inpatient_count_label.setAlignment(Qt.AlignCenter)
        self.inpatient_count_label.setStyleSheet("""
            font-size: 12pt;
            font-weight: 700;
            color: #1f1f1f;
            padding: 0;
            background-color: #2ecc71;
        """)
        self.inpatient_caption_label = QLabel("В отделении")
        self.inpatient_caption_label.setAlignment(Qt.AlignCenter)
        self.inpatient_caption_label.setStyleSheet("""
            font-size: 6pt;
            font-weight: 400;
            color: #4a4a4a;
            padding: 0;
        """)
        census_box = QFrame()
        census_box.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #cfcfcf;
                border-radius: 6px;
                padding: 1px 1px;
            }
        """)
        census_layout = QVBoxLayout(census_box)
        census_layout.setContentsMargins(8, 3, 8, 3)
        census_layout.setSpacing(0)
        census_layout.addWidget(self.inpatient_count_label)
        census_layout.addWidget(self.inpatient_caption_label)
        census_box.setFixedWidth(86)

        archive_filters = QHBoxLayout()
        archive_filters.addWidget(QLabel("Фильтр:"))
        archive_filters.addWidget(QLabel("Год выписки:"))
        self.archive_year_combo = QComboBox()
        self.archive_year_combo.addItem("Все")
        self.archive_year_combo.currentTextChanged.connect(self.filter_patients)
        archive_filters.addWidget(self.archive_year_combo)
        archive_filters.addWidget(QLabel("Месяц:"))
        self.archive_month_combo = QComboBox()
        self.archive_month_combo.addItems(["Все", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"])
        self.archive_month_combo.currentTextChanged.connect(self.filter_patients)
        archive_filters.addWidget(self.archive_month_combo)
        archive_filters.addWidget(QLabel("Исход:"))
        self.archive_outcome_combo = QComboBox()
        self.archive_outcome_combo.addItem("Все")
        self.archive_outcome_combo.currentTextChanged.connect(self.filter_patients)
        archive_filters.addWidget(self.archive_outcome_combo)
        self.archive_reset_button = QPushButton("Сбросить")
        self.archive_reset_button.clicked.connect(self._reset_archive_filters)
        archive_filters.addWidget(self.archive_reset_button)
        archive_filters.addStretch(1)
        archive_filters.addWidget(census_box)
        layout.addLayout(archive_filters)

        self.case_tabs = QTabWidget()
        self.tree = self._create_case_table(archive=False)
        self.archive_tree = self._create_case_table(archive=True)
        self.case_tabs.addTab(self.tree, "В отделении")
        self.case_tabs.addTab(self.archive_tree, "Архив")
        self.case_tabs.setStyleSheet("""
            QTabBar::tab {
                color: black;
                font-weight: 400;
                padding: 6px 14px;
                border: 1px solid #999999;
                border-bottom: none;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                margin-right: 2px;
            }
            QTabBar::tab:first {
                background-color: #2ecc71;
            }
            QTabBar::tab:last {
                background-color: #f1c40f;
            }
            QTabBar::tab:selected {
                font-weight: 700;
                border: 2px solid #555555;
                border-bottom: none;
            }
            QTabWidget::pane {
                border: 1px solid #999999;
            }
        """)
        self.case_tabs.currentChanged.connect(lambda _idx: self.on_patient_select())
        layout.addWidget(self.case_tabs)

    def _create_case_table(self, archive=False):
        table = QTableWidget()
        if archive:
            table.setColumnCount(8)
            table.setHorizontalHeaderLabels(["Дата пост.", "Дата вып.", "№ карты", "ФИО", "Дата рожд.", "Диагноз", "Исход", "Дней"])
        else:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["Дата", "№ карты", "ФИО", "Дата рожд.", "Диагноз", "Дней"])
        table.setColumnWidth(0, 90)
        table.setColumnWidth(1, 90)
        table.setColumnWidth(2, 120 if archive else 200)
        if archive:
            table.setColumnWidth(3, 200)
            table.setColumnWidth(4, 100)
            table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
            table.setColumnWidth(6, 120)
            table.setColumnWidth(7, 60)
        else:
            table.setColumnWidth(3, 100)
            table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
            table.setColumnWidth(5, 60)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setDefaultSectionSize(20)
        table.setStyleSheet("QTableWidget::item { padding: 0px; margin: 0px; }")
        table.setSortingEnabled(True)
        table.cellDoubleClicked.connect(self.view_histories)
        table.itemSelectionChanged.connect(self.on_patient_select)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self.show_context_menu)
        return table

    # Navigation API
    def _nav_back(self):
        if not self._nav_stack:
            return
        # pop current
        widget = self.navigation.currentWidget()
        if widget:
            self.navigation.removeWidget(widget)
            widget.deleteLater()
        if self._nav_stack:
            self._nav_stack.pop()
        if not self._nav_stack:
            self.navigation.hide()
            self.back_action.setEnabled(False)
            # restore main content visibility
            try:
                self._set_main_visible(True)
            except Exception:
                pass
        else:
            previous_widget = self._nav_stack[-1]
            try:
                self.navigation.setCurrentWidget(previous_widget)
            except Exception:
                pass
            self.navigation.show()
            self.back_action.setEnabled(True)

    def _open_diagnosis_manager(self):
        from windows.primary_exam import DiagnosisManagerDialog
        # Поддержка PyInstaller: используем sys._MEIPASS для exe, иначе текущую директорию
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_path, 'data')
        dialog = DiagnosisManagerDialog(self, data_dir)
        dialog.exec()

    def nav_push(self, widget):
        # show widget in stack
        self.navigation.addWidget(widget)
        self.navigation.setCurrentWidget(widget)
        self.navigation.show()
        # hide main content area while showing page
        try:
            self._set_main_visible(False)
        except Exception:
            pass
        self._nav_stack.append(widget)
        self.back_action.setEnabled(True)

    def _set_main_visible(self, visible: bool):
        # iterate top-level items in main_layout and show/hide widgets except the navigation widget
        for i in range(self.main_layout.count()):
            item = self.main_layout.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w:
                if w is self.navigation:
                    continue
                try:
                    w.setVisible(visible)
                except Exception:
                    pass
            else:
                # handle nested layouts
                l = item.layout()
                if l:
                    for j in range(l.count()):
                        sub = l.itemAt(j)
                        if sub is None:
                            continue
                        sw = sub.widget()
                        if sw and sw is not self.navigation:
                            try:
                                sw.setVisible(visible)
                            except Exception:
                                pass
                        else:
                            subl = sub.layout()
                            if subl:
                                for k in range(subl.count()):
                                    sw2 = subl.itemAt(k).widget()
                                    if sw2 and sw2 is not self.navigation:
                                        try:
                                            sw2.setVisible(visible)
                                        except Exception:
                                            pass

    def _get_patient_summary(self, patient_data):
        p = patient_data
        pid = p[0]
        all_histories = self.db.get_histories(pid)
        if not all_histories:
            return None
        current_history_id = all_histories[0][11]
        histories = [h for h in all_histories if h[11] == current_history_id] if current_history_id is not None else all_histories

        # Logic for diagnoses
        diag_clinical = ""
        diag_admission = ""
        diag_comorbid = ""
        outcome = ""
        
        # 1. Look for Clinical Diagnosis (prioritize most recent)
        for h in histories:
            if h[9]: # diag_clinical
                diag_clinical = h[9]
                if h[10]: # diag_comorbid
                    diag_comorbid = h[10]
                break
        
        # 2. Look for Admission Diagnosis (prioritize most recent)
        for h in histories:
            if h[8]: # diag_admission
                diag_admission = h[8]
                break

        # If clinical found, add comorbid if available
        if diag_clinical and diag_comorbid:
            diag_clinical += f" (Соп: {diag_comorbid})"
            
        # 3. Extract Admission Date and Outcome from examination text
        h_latest = histories[0]
        visit_date = h_latest[2] or ''
        admission_date = ''
        
        for h in histories:
            exam_text = h[4] or ''
            if not admission_date and 'Дата поступления:' in exam_text:
                for line in exam_text.split('\n'):
                    if line.startswith('Дата поступления:'):
                        admission_date = line.split(':', 1)[1].strip()
                        # Убираем время, если оно есть (берем первые 10 символов формата ДД.ММ.ГГГГ)
                        if len(admission_date) > 10:
                            admission_date = admission_date[:10]
                        break
            if not outcome and 'Исход:' in exam_text:
                for line in exam_text.split('\n'):
                    if line.startswith('Исход:'):
                        outcome = line.split(':', 1)[1].strip()
                        break
            if admission_date and outcome:
                break

        if not admission_date and visit_date:
            try:
                admission_date = datetime.fromisoformat(visit_date).strftime('%d.%m.%Y')
            except:
                admission_date = visit_date.split('T')[0]

        dob = p[3] or ''
        try:
            dob = datetime.fromisoformat(dob).strftime('%d.%m.%Y') if dob else ''
        except:
            pass

        days_str = ""
        if visit_date:
            try:
                visit_dt = datetime.fromisoformat(visit_date)
                now = datetime.now()
                days = (now - visit_dt).days + 1
                days_str = str(days)
            except:
                pass

        return {
            'visit_date_raw': visit_date,
            'admission_date': admission_date,
            'surname': p[1] or '',
            'name': p[2] or '',
            'patronymic': p[9] if len(p) > 9 else '',
            'dob': dob,
            'diag_admission': diag_admission,
            'diag_clinical': diag_clinical,
            'outcome': outcome,
            'days': days_str,
            'pid': pid,
            'hid': current_history_id
        }

    def _format_date(self, value):
        if not value:
            return ""
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(value[:10], fmt).strftime("%d.%m.%Y")
            except Exception:
                pass
        try:
            return datetime.fromisoformat(value).strftime("%d.%m.%Y")
        except Exception:
            return value[:10]

    def _get_case_summary(self, case):
        case_id = case[0]
        patient_id = case[1]
        card_number = case[2] or str(case_id)
        admission_date = case[3] or ""
        discharge_date = case[5] or ""
        outcome = case[7] or ""
        status = case[8] or "active"
        final_diagnosis = case[9] or ""
        surname = case[14] or ""
        name = case[15] or ""
        dob = self._format_date(case[16] or "")
        patronymic = case[17] or ""

        histories = self.db.get_histories(patient_id)
        histories = [h for h in histories if h[11] == case_id]
        diag_clinical = final_diagnosis
        diag_admission = ""
        if not admission_date:
            for h in histories:
                exam_text = h[4] or ""
                if "Дата поступления:" in exam_text:
                    for line in exam_text.split("\n"):
                        if line.startswith("Дата поступления:"):
                            admission_date = line.split(":", 1)[1].strip()[:10]
                            break
                if admission_date:
                    break
        for h in histories:
            if not diag_clinical and h[9]:
                diag_clinical = h[9]
            if not diag_admission and h[8]:
                diag_admission = h[8]
            if not outcome:
                exam_text = h[4] or ""
                if "Исход:" in exam_text:
                    for line in exam_text.split("\n"):
                        if line.startswith("Исход:"):
                            outcome = line.split(":", 1)[1].strip()
                            break
            if diag_clinical and diag_admission and outcome:
                break

        days_str = ""
        try:
            start = datetime.strptime(admission_date[:10], "%d.%m.%Y")
            if discharge_date:
                end = datetime.strptime(discharge_date[:10], "%d.%m.%Y")
            else:
                end = datetime.now()
            days_str = str((end - start).days + 1)
        except Exception:
            pass

        return {
            "case_id": case_id,
            "patient_id": patient_id,
            "card_number": card_number,
            "admission_date": self._format_date(admission_date),
            "discharge_date": self._format_date(discharge_date),
            "fio": f"{surname} {name} {patronymic}".strip(),
            "dob": dob,
            "diagnosis": diag_clinical or diag_admission,
            "outcome": outcome,
            "days": days_str,
            "status": status,
        }

    def _current_table(self):
        if hasattr(self, 'case_tabs') and self.case_tabs.currentIndex() == 1:
            return self.archive_tree
        return self.tree

    def _case_item(self, table, row):
        return table.item(row, 0)

    def _reset_archive_filters(self):
        self.archive_year_combo.setCurrentText("Все")
        self.archive_month_combo.setCurrentText("Все")
        self.archive_outcome_combo.setCurrentText("Все")
        self.load_patients()

    def _refresh_archive_filters(self, summaries):
        current_year = self.archive_year_combo.currentText()
        current_outcome = self.archive_outcome_combo.currentText()
        years = sorted({s["discharge_date"][-4:] for s in summaries if len(s["discharge_date"]) >= 10}, reverse=True)
        outcomes = sorted({s["outcome"] for s in summaries if s["outcome"]})

        self.archive_year_combo.blockSignals(True)
        self.archive_outcome_combo.blockSignals(True)
        self.archive_year_combo.clear()
        self.archive_year_combo.addItem("Все")
        self.archive_year_combo.addItems(years)
        self.archive_year_combo.setCurrentText(current_year if current_year in ["Все"] + years else "Все")
        self.archive_outcome_combo.clear()
        self.archive_outcome_combo.addItem("Все")
        self.archive_outcome_combo.addItems(outcomes)
        self.archive_outcome_combo.setCurrentText(current_outcome if current_outcome in ["Все"] + outcomes else "Все")
        self.archive_year_combo.blockSignals(False)
        self.archive_outcome_combo.blockSignals(False)

    def _passes_archive_filters(self, summary):
        if summary["status"] != "archived":
            return True
        year = self.archive_year_combo.currentText()
        month = self.archive_month_combo.currentText()
        outcome = self.archive_outcome_combo.currentText()
        discharge_date = summary["discharge_date"]
        if year != "Все" and not discharge_date.endswith(year):
            return False
        date_parts = discharge_date.split(".")
        discharge_month = date_parts[1] if len(date_parts) >= 2 else ""
        if month != "Все" and discharge_month != month:
            return False
        if outcome != "Все" and summary["outcome"] != outcome:
            return False
        return True

    def _outcome_color(self, outcome):
        text = (outcome or "").lower()
        if "улучш" in text:
            return QColor(220, 245, 225)
        if "перевод" in text:
            return QColor(220, 235, 250)
        if "ухудш" in text or "смер" in text:
            return QColor(245, 220, 220)
        if text:
            return QColor(245, 240, 210)
        return None

    def _date_sort_value(self, value):
        value = (value or "").strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return int(datetime.strptime(value[:10], fmt).strftime("%Y%m%d"))
            except Exception:
                pass
        return -1

    def _natural_sort_value(self, value):
        parts = re.split(r'(\d+)', value or "")
        return tuple(int(part) if part.isdigit() else part.lower() for part in parts)

    def _case_sort_value(self, table, col, text):
        is_archive = table is self.archive_tree
        date_columns = {0, 1} if is_archive else {0}
        dob_col = 4 if is_archive else 3
        card_col = 2 if is_archive else 1
        days_col = 7 if is_archive else 5
        if col in date_columns or col == dob_col:
            return (0, self._date_sort_value(text))
        if col == card_col:
            return (1, self._natural_sort_value(text))
        if col == days_col:
            try:
                return (2, int(text))
            except (TypeError, ValueError):
                return (2, -1)
        return (3, (text or "").lower())

    def _set_case_item(self, table, row, col, text, summary, color=None):
        item = SortableTableWidgetItem(text)
        item.setData(SORT_ROLE, self._case_sort_value(table, col, text))
        item.setData(Qt.UserRole, summary["patient_id"])
        item.setData(Qt.UserRole + 1, summary["case_id"])
        item.setData(Qt.UserRole + 2, summary["card_number"])
        item.setData(Qt.UserRole + 3, summary["status"])
        if color is not None:
            item.setBackground(color)
        table.setItem(row, col, item)

    def _populate_case_table(self, table, cases):
        table.setSortingEnabled(False)
        table.setRowCount(0)
        query = self.search_entry.text().strip().lower() if hasattr(self, 'search_entry') else ""
        is_archive = table is self.archive_tree
        for case in cases:
            summary = self._get_case_summary(case)
            if query and query not in summary["fio"].lower() and query not in summary["diagnosis"].lower() and query not in summary["card_number"].lower():
                continue
            if is_archive and not self._passes_archive_filters(summary):
                continue
            row = table.rowCount()
            table.insertRow(row)
            row_color = self._outcome_color(summary["outcome"]) if is_archive else None
            if is_archive:
                values = [
                    summary["admission_date"],
                    summary["discharge_date"],
                    summary["card_number"],
                    summary["fio"],
                    summary["dob"],
                    summary["diagnosis"],
                    summary["outcome"],
                    summary["days"],
                ]
            else:
                values = [
                    summary["admission_date"],
                    summary["card_number"],
                    summary["fio"],
                    summary["dob"],
                    summary["diagnosis"],
                    summary["days"],
                ]
            for col, value in enumerate(values):
                self._set_case_item(table, row, col, value, summary, row_color)
        table.setSortingEnabled(True)

    def load_patients(self):
        active_cases = self.db.get_cases("active")
        archived_cases = self.db.get_cases("archived")
        self.inpatient_count_label.setText(str(len(active_cases)))
        archived_summaries = [self._get_case_summary(case) for case in archived_cases]
        self._refresh_archive_filters(archived_summaries)
        self._populate_case_table(self.tree, active_cases)
        self._populate_case_table(self.archive_tree, archived_cases)

    def filter_patients(self):
        self.load_patients()

    def new_patient(self):
        self.open_create_history_wizard()

    def open_create_history_wizard(self):
        def _on_wizard_done(patient_id, case_id=None):
            try:
                if patient_id is not None:
                    # Refresh the list
                    self.load_patients()
                    
                    # Also automatically open the stationary card for this patient
                    patient = self.db.get_patient_by_id(patient_id)
                    if patient:
                        case = self.db.get_case_by_id(case_id) if case_id is not None else None
                        card_number = case[2] if case else str(case_id or patient_id)
                        page = StationaryCardPage(self, self.db, patient_id, patient, card_number, case_id=case_id)
                        self.nav_push(page)
            except Exception:
                pass

        wizard = CreateHistoryWizard(self, self.db, done_callback=_on_wizard_done)
        try:
            self.nav_push(wizard)
        except Exception:
            # non-blocking fallback: show the wizard; the done_callback will refresh patients
            try:
                wizard.show()
            except Exception:
                pass

    def open_new_patient_window(self):
        dlg = NewPatientDialog(self)
        try:
            self.nav_push(dlg)
        except Exception:
            try:
                dlg.show()
            except Exception:
                pass

    def delete_patient(self):
        table = self._current_table()
        selected = table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите пациента для удаления.")
            return
        reply = QMessageBox.question(self, "Подтверждение", "Удалить этого пациента и все его истории?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            row = selected[0].row()
            patient_id = self._case_item(table, row).data(Qt.UserRole)
            self.db.delete_patient(patient_id)
            self.load_patients()

    def view_histories(self, row, column):
        table = self.sender() if isinstance(self.sender(), QTableWidget) else self._current_table()
        case_item = self._case_item(table, row)
        patient_id = case_item.data(Qt.UserRole)
        history_id = case_item.data(Qt.UserRole + 1)
        card_number = case_item.data(Qt.UserRole + 2)
        status = case_item.data(Qt.UserRole + 3)
        patient = self.db.get_patient_by_id(patient_id)
        if not patient:
            return
        page = StationaryCardPage(self, self.db, patient_id, patient, card_number or str(history_id), case_id=history_id, read_only=(status == "archived"))
        self.nav_push(page)

    def open_history_window(self, patient_id, patient, history_id=None):
        dlg = HistoryDialog(patient_id, patient, self.db, self, history_id)
        try:
            self.nav_push(dlg)
            # if a particular history id is provided, select it after showing
            if history_id is not None:
                try:
                    # load list and find index
                    dlg.load_histories_list()
                    histories = getattr(dlg, '_visible_histories', self.db.get_histories(patient_id))
                    for idx, h in enumerate(histories):
                        if h[11] == history_id:
                            dlg.histories_list.setCurrentRow(idx)
                            break
                except Exception:
                    pass
        except Exception:
            try:
                dlg.show()
                if history_id is not None:
                    try:
                        dlg.load_histories_list()
                        histories = getattr(dlg, '_visible_histories', self.db.get_histories(patient_id))
                        for idx, h in enumerate(histories):
                            if h[11] == history_id:
                                dlg.histories_list.setCurrentRow(idx)
                                break
                    except Exception:
                        pass
            except Exception:
                pass

    def show_context_menu(self, pos):
        table = self.sender() if isinstance(self.sender(), QTableWidget) else self._current_table()
        menu = QMenu()
        fill_action = menu.addAction("Заполнить")
        fill_action.triggered.connect(self.fill_patient)
        menu.exec(table.mapToGlobal(pos))

    def on_patient_select(self):
        selected = bool(self._current_table().selectedItems())
        self.edit_button.setEnabled(selected)
        self.delete_history_button.setEnabled(selected)

    def fill_patient(self):
        table = self._current_table()
        selected = table.selectedItems()
        if selected:
            row = selected[0].row()
            case_item = self._case_item(table, row)
            patient_id = case_item.data(Qt.UserRole)
            logical_hid = case_item.data(Qt.UserRole + 1)
            card_number = case_item.data(Qt.UserRole + 2)
            status = case_item.data(Qt.UserRole + 3)
            patient = self.db.get_patient_by_id(patient_id)
            if patient:
                card_number = card_number or (str(logical_hid) if logical_hid else str(patient_id))
                page = StationaryCardPage(self, self.db, patient_id, patient, card_number, case_id=logical_hid, read_only=(status == "archived"))
                try:
                    # push into main navigation if available
                    self.nav_push(page)
                except Exception:
                    # fallback to modal dialog behavior if navigation unavailable
                    page.show()

    def delete_history(self):
        table = self._current_table()
        selected = table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите запись для удаления.")
            return
        row = selected[0].row()
        # history_id is the logical history number stored in UserRole+1
        logical_history_id = self._case_item(table, row).data(Qt.UserRole + 1)
        if not logical_history_id:
            QMessageBox.warning(self, "Ошибка", "Не удалось определить выбранную историю.")
            return
        reply = QMessageBox.question(self, "Подтверждение", f"Удалить историю болезни №{logical_history_id} и ВСЕ связанные записи?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        # delete entire logical history group
        try:
            self.db.delete_entire_history_group(logical_history_id)
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось удалить историю.")
            return
        QMessageBox.information(self, "Успех", "История болезни полностью удалена.")
        self.load_patients()

class NewPatientDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.db = parent.db
        self.setWindowTitle("Новый пациент")
        self.setModal(True)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Фамилия:"))
        self.surname_entry = QLineEdit()
        layout.addWidget(self.surname_entry)

        layout.addWidget(QLabel("Имя:"))
        self.name_entry = QLineEdit()
        layout.addWidget(self.name_entry)

        layout.addWidget(QLabel("Дата рождения:"))
        from PySide6.QtCore import QDate, QLocale
        self.dob_entry = QDateEdit(QDate.currentDate())
        self.dob_entry.setCalendarPopup(True)
        self.dob_entry.setLocale(QLocale(QLocale.Russian))
        self.dob_entry.setDisplayFormat("dd.MM.yyyy")
        layout.addWidget(self.dob_entry)

        # Address components with autocompletion (reuse lists similar to wizard)
        layout.addWidget(QLabel("Адрес фактического проживания"))
        self.city_combo = QComboBox()
        self.city_combo.setEditable(True)
        pmr_cities = get_cities()
        self.city_combo.addItems(pmr_cities)
        from PySide6.QtWidgets import QCompleter
        city_completer = QCompleter(pmr_cities, self.city_combo)
        city_completer.setCaseSensitivity(Qt.CaseInsensitive)
        city_completer.setFilterMode(Qt.MatchContains)
        self.city_combo.setCompleter(city_completer)
        layout.addWidget(self.city_combo)

        self.street_combo = QComboBox()
        self.street_combo.setEditable(True)
        pmr_streets = get_streets()
        self.street_combo.addItems(pmr_streets)
        street_completer = QCompleter(pmr_streets, self.street_combo)
        street_completer.setCaseSensitivity(Qt.CaseInsensitive)
        street_completer.setFilterMode(Qt.MatchContains)
        self.street_combo.setCompleter(street_completer)
        layout.addWidget(self.street_combo)

        addr_row = QHBoxLayout()
        addr_row.addWidget(QLabel("Дом, кв."))
        self.house_entry = QLineEdit()
        addr_row.addWidget(self.house_entry)
        layout.addLayout(addr_row)

        button_layout = QHBoxLayout()
        ok_button = QPushButton("ОК")
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)

        cancel_button = QPushButton("Отмена")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    def accept(self):
        surname = self.surname_entry.text()
        name = self.name_entry.text()
        dob = self.dob_entry.date().toString("yyyy-MM-dd")
        # collect address components
        city = self.city_combo.currentText().strip() if hasattr(self, 'city_combo') else ''
        street = self.street_combo.currentText().strip() if hasattr(self, 'street_combo') else ''
        house = self.house_entry.text().strip() if hasattr(self, 'house_entry') else ''
        apartment = ''
        if surname:
            self.db.add_patient(surname, name, dob, city=city, street=street, house=house, apartment=apartment)
            remember_address(city, street)
            parent = self.parent()
            try:
                if parent is not None and hasattr(parent, 'load_patients'):
                    parent.load_patients()
                if parent is not None and hasattr(parent, '_nav_back'):
                    parent._nav_back()
                    return
            except Exception:
                pass
            super().accept()
        else:
            QMessageBox.warning(self, "Ошибка", "Фамилия обязательна.")

class HistoryDialog(QDialog):
    def __init__(self, patient_id, patient, db, parent, logical_history_id=None):
        super().__init__(parent)
        self.patient_id = patient_id
        self.patient = patient
        self.db = db
        self.logical_history_id = logical_history_id
        self.setWindowTitle(f"Histories for {patient[1]} {patient[2]} {patient[9] if len(patient) > 9 else ''}".strip())
        self.setModal(True)
        self.resize(800, 600)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Осмотр:"))
        self.exam_text = QTextEdit()
        layout.addWidget(self.exam_text)

        layout.addWidget(QLabel("Диагноз:"))
        self.diag_entry = QLineEdit()
        layout.addWidget(self.diag_entry)

        layout.addWidget(QLabel("Лечение:"))
        self.treat_entry = QLineEdit()
        layout.addWidget(self.treat_entry)

        layout.addWidget(QLabel("Заметки:"))
        self.notes_text = QTextEdit()
        layout.addWidget(self.notes_text)

        save_button = QPushButton("Сохранить историю")
        save_button.clicked.connect(self.save_history)
        layout.addWidget(save_button)

        layout.addWidget(QLabel("Предыдущие истории:"))
        self.histories_list = QListWidget()
        self.histories_list.itemSelectionChanged.connect(self.load_history)
        layout.addWidget(self.histories_list)

        self.load_histories_list()

    def save_history(self):
        exam = self.exam_text.toPlainText()
        diag = self.diag_entry.text()
        treat = self.treat_entry.text()
        notes = self.notes_text.toPlainText()
        self.db.add_history(self.patient_id, "history", exam, diag, treat, notes, history_id=self.logical_history_id)
        QMessageBox.information(self, "Успех", "История сохранена.")
        # If this dialog was shown as a page in the main navigation, go back to main view
        # find nearest ancestor that implements _nav_back()
        anc = self.parent()
        while anc is not None and not hasattr(anc, '_nav_back'):
            try:
                anc = anc.parent()
            except Exception:
                anc = None
        if anc is not None and hasattr(anc, '_nav_back'):
            try:
                anc._nav_back()
                return
            except Exception:
                pass
        self.load_histories_list()

    def load_histories_list(self):
        self.histories_list.clear()
        histories = self.db.get_histories(self.patient_id)
        if self.logical_history_id is not None:
            histories = [h for h in histories if h[11] == self.logical_history_id]
        self._visible_histories = histories
        for h in histories:
            # Convert possible HTML to plain text and create a single-line preview
            try:
                doc = QTextDocument()
                doc.setHtml(h[4] or "")
                plain = doc.toPlainText()
            except Exception:
                plain = h[4] or ""
            preview = ' '.join(plain.split())[:120]
            if len(plain) > 120:
                preview = preview + '...'
            self.histories_list.addItem(preview)

    def load_history(self):
        selected = self.histories_list.selectedItems()
        if selected:
            index = self.histories_list.row(selected[0])
            histories = getattr(self, '_visible_histories', self.db.get_histories(self.patient_id))
            h = histories[index]
            # If stored as HTML, convert to plain text to preserve newlines
            try:
                doc = QTextDocument()
                doc.setHtml(h[4] or "")
                plain = doc.toPlainText()
            except Exception:
                plain = h[4] or ""
            self.exam_text.setPlainText(plain)
            self.diag_entry.setText(h[5] or "")
            self.treat_entry.setText(h[6] or "")
            self.notes_text.setPlainText(h[7] or "")

class EditPatientDialog(QDialog):
    def __init__(self, patient_id, patient, db, parent):
        super().__init__(parent)
        self.patient_id = patient_id
        self.patient = patient
        self.db = db
        self.setWindowTitle(f"Edit Patient: {patient[1]}")
        self.setModal(True)
        self.resize(600, 400)
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Personal Info Tab
        personal_widget = QWidget()
        personal_layout = QVBoxLayout(personal_widget)

        personal_layout.addWidget(QLabel("Surname:"))
        self.surname_entry = QLineEdit(patient[1])
        personal_layout.addWidget(self.surname_entry)

        personal_layout.addWidget(QLabel("Name:"))
        self.name_entry = QLineEdit(patient[2] or '')
        personal_layout.addWidget(self.name_entry)

        personal_layout.addWidget(QLabel("DOB:"))
        self.dob_entry = QLineEdit(patient[3] or '')
        personal_layout.addWidget(self.dob_entry)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_personal_info)
        personal_layout.addWidget(save_button)

        self.tabs.addTab(personal_widget, "Личные данные")

        # Histories Tab
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)

        history_layout.addWidget(QLabel("Examination:"))
        self.exam_text = QTextEdit()
        history_layout.addWidget(self.exam_text)

        history_layout.addWidget(QLabel("Diagnosis:"))
        self.diag_entry = QLineEdit()
        history_layout.addWidget(self.diag_entry)

        history_layout.addWidget(QLabel("Treatment:"))
        self.treat_entry = QLineEdit()
        history_layout.addWidget(self.treat_entry)

        history_layout.addWidget(QLabel("Notes:"))
        self.notes_text = QTextEdit()
        history_layout.addWidget(self.notes_text)

        save_hist_button = QPushButton("Save History")
        save_hist_button.clicked.connect(self.save_history)
        history_layout.addWidget(save_hist_button)

        history_layout.addWidget(QLabel("Previous Histories:"))
        self.histories_list = QListWidget()
        self.histories_list.itemSelectionChanged.connect(self.load_history)
        history_layout.addWidget(self.histories_list)

        self.tabs.addTab(history_widget, "Истории")

        self.load_histories_list()

    def save_personal_info(self):
        surname = self.surname_entry.text()
        name = self.name_entry.text()
        dob = self.dob_entry.text()
        self.db.update_patient(self.patient_id, surname, name, dob)
        QMessageBox.information(self, "Успех", "Информация о пациенте обновлена.")
        self.accept()

    def save_history(self):
        exam = self.exam_text.toPlainText()
        diag = self.diag_entry.text()
        treat = self.treat_entry.text()
        notes = self.notes_text.toPlainText()
        self.db.add_history(self.patient_id, "history", exam, diag, treat, notes)
        QMessageBox.information(self, "Успех", "История сохранена.")
        anc = self.parent()
        while anc is not None and not hasattr(anc, '_nav_back'):
            try:
                anc = anc.parent()
            except Exception:
                anc = None
        if anc is not None and hasattr(anc, '_nav_back'):
            try:
                anc._nav_back()
                return
            except Exception:
                pass
        self.load_histories_list()

    def load_histories_list(self):
        self.histories_list.clear()
        histories = self.db.get_histories(self.patient_id)
        for h in histories:
            self.histories_list.addItem(f"{(h[4] or '')[:50]}...")

    def load_history(self):
        selected = self.histories_list.selectedItems()
        if selected:
            index = self.histories_list.row(selected[0])
            histories = self.db.get_histories(self.patient_id)
            h = histories[index]
            try:
                doc = QTextDocument()
                doc.setHtml(h[4] or "")
                plain = doc.toPlainText()
            except Exception:
                plain = h[4] or ""
            self.exam_text.setPlainText(plain)
            self.diag_entry.setText(h[5] or "")
            self.treat_entry.setText(h[6] or "")
            self.notes_text.setPlainText(h[7] or "")
