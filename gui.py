import sys
import os
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QScrollArea, QTextEdit, QComboBox, QFrame, QMessageBox, QMenu,
    QSplitter, QTabWidget, QListWidget, QAbstractItemView, QDialog,
    QTableWidget, QTableWidgetItem, QDateEdit
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QAction, QFont, QTextDocument
from database import Database
from windows.stationary_card import StationaryCardPage
from windows.add_record import AddRecordWindow
from windows.primary_exam import PrimaryExamWindow
from windows.edit_record import EditRecordWindow
from windows.create_history_wizard import CreateHistoryWizard
from PySide6.QtWidgets import QStackedWidget, QToolBar

class MedicalApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.setWindowTitle("Medical Patient Records")
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
        search_layout.addWidget(QLabel("Поиск пациентов:"))
        self.search_entry = QLineEdit()
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

        # Patients list
        self.tree = QTableWidget()
        self.tree.setColumnCount(7)
        self.tree.setHorizontalHeaderLabels(["Дата", "Фамилия", "Имя", "Дата рожд.", "Диагноз", "Исход", "Дней"])
        self.tree.setColumnWidth(0, 90)  # Дата
        self.tree.setColumnWidth(1, 140)  # Фамилия
        self.tree.setColumnWidth(2, 120)  # Имя
        self.tree.setColumnWidth(3, 100)  # Дата рожд.
        self.tree.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)  # Диагноз
        self.tree.setColumnWidth(5, 120)  # Исход
        self.tree.setColumnWidth(6, 60)  # Дней
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.verticalHeader().setDefaultSectionSize(20)
        self.tree.setStyleSheet("QTableWidget::item { padding: 0px; margin: 0px; }")
        self.tree.cellDoubleClicked.connect(self.view_histories)
        self.tree.itemSelectionChanged.connect(self.on_patient_select)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.tree)

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
        histories = self.db.get_histories(pid)
        if not histories:
            return None

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
            'dob': dob,
            'diag_admission': diag_admission,
            'diag_clinical': diag_clinical,
            'outcome': outcome,
            'days': days_str,
            'pid': pid,
            'hid': h_latest[11]
        }

    def load_patients(self):
        rows_data = []
        for p in self.db.get_patients():
            summary = self._get_patient_summary(p)
            if summary:
                rows_data.append(summary)

        # sort by visit_date raw desc
        rows_data.sort(key=lambda x: x['visit_date_raw'] or '', reverse=True)

        self.tree.setRowCount(0)
        for s in rows_data:
            row = self.tree.rowCount()
            self.tree.insertRow(row)
            
            self.tree.setItem(row, 0, QTableWidgetItem(s['admission_date']))
            
            item_surname = QTableWidgetItem(s['surname'])
            item_surname.setData(Qt.UserRole, s['pid'])
            item_surname.setData(Qt.UserRole + 1, s['hid'])
            self.tree.setItem(row, 1, item_surname)
            
            self.tree.setItem(row, 2, QTableWidgetItem(s['name']))
            self.tree.setItem(row, 3, QTableWidgetItem(s['dob']))
            
            # Show clinical diagnosis if available, otherwise fallback to admission diagnosis
            diag_to_show = s['diag_clinical'] if s['diag_clinical'] else s['diag_admission']
            self.tree.setItem(row, 4, QTableWidgetItem(diag_to_show))
            
            self.tree.setItem(row, 5, QTableWidgetItem(s['outcome']))
            self.tree.setItem(row, 6, QTableWidgetItem(s['days']))

    def filter_patients(self):
        query = self.search_entry.text().lower()
        rows_data = []
        for p in self.db.get_patients():
            if query and query not in (p[1] or '').lower() and query not in (p[2] or '').lower():
                continue
            summary = self._get_patient_summary(p)
            if summary:
                rows_data.append(summary)

        # sort by visit_date raw desc
        rows_data.sort(key=lambda x: x['visit_date_raw'] or '', reverse=True)

        self.tree.setRowCount(0)
        for s in rows_data:
            row = self.tree.rowCount()
            self.tree.insertRow(row)
            
            self.tree.setItem(row, 0, QTableWidgetItem(s['admission_date']))
            
            item_surname = QTableWidgetItem(s['surname'])
            item_surname.setData(Qt.UserRole, s['pid'])
            item_surname.setData(Qt.UserRole + 1, s['hid'])
            self.tree.setItem(row, 1, item_surname)
            
            self.tree.setItem(row, 2, QTableWidgetItem(s['name']))
            self.tree.setItem(row, 3, QTableWidgetItem(s['dob']))
            
            # Show clinical diagnosis if available, otherwise fallback to admission diagnosis
            diag_to_show = s['diag_clinical'] if s['diag_clinical'] else s['diag_admission']
            self.tree.setItem(row, 4, QTableWidgetItem(diag_to_show))
            
            self.tree.setItem(row, 5, QTableWidgetItem(s['outcome']))
            self.tree.setItem(row, 6, QTableWidgetItem(s['days']))

    def new_patient(self):
        self.open_create_history_wizard()

    def open_create_history_wizard(self):
        def _on_wizard_done(patient_id):
            try:
                if patient_id is not None:
                    # Refresh the list
                    self.load_patients()
                    
                    # Also automatically open the stationary card for this patient
                    patient = self.db.get_patient_by_id(patient_id)
                    if patient:
                        # Find the card number we just created
                        histories = self.db.get_histories(patient_id)
                        card_number = str(patient_id)
                        if histories:
                            for h in histories:
                                if h[3] == "passport":
                                    if h[11]: # logical history_id
                                        card_number = str(h[11])
                                        break
                                    # Fallback to parsing text
                                    examination = h[4]
                                    for line in examination.split('\n'):
                                        if line.startswith("Номер карты:"):
                                            cnum = line.split(":", 1)[1].strip()
                                            if cnum:
                                                card_number = cnum
                                            break
                                    break
                        page = StationaryCardPage(self, self.db, patient_id, patient, card_number)
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
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите пациента для удаления.")
            return
        reply = QMessageBox.question(self, "Подтверждение", "Удалить этого пациента и все его истории?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            row = selected[0].row()
            patient_id = self.tree.item(row, 1).data(Qt.UserRole)
            self.db.delete_patient(patient_id)
            self.load_patients()

    def view_histories(self, row, column):
        patient_id = self.tree.item(row, 1).data(Qt.UserRole)
        history_id = self.tree.item(row, 1).data(Qt.UserRole + 1)
        patient = self.db.get_patient_by_id(patient_id)
        if not patient:
            return
        self.open_history_window(patient_id, patient, history_id)

    def open_history_window(self, patient_id, patient, history_id=None):
        dlg = HistoryDialog(patient_id, patient, self.db, self)
        try:
            self.nav_push(dlg)
            # if a particular history id is provided, select it after showing
            if history_id is not None:
                try:
                    # load list and find index
                    dlg.load_histories_list()
                    histories = self.db.get_histories(patient_id)
                    for idx, h in enumerate(histories):
                        if h[0] == history_id:
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
                        histories = self.db.get_histories(patient_id)
                        for idx, h in enumerate(histories):
                            if h[0] == history_id:
                                dlg.histories_list.setCurrentRow(idx)
                                break
                    except Exception:
                        pass
            except Exception:
                pass

    def show_context_menu(self, pos):
        menu = QMenu()
        fill_action = menu.addAction("Заполнить")
        fill_action.triggered.connect(self.fill_patient)
        menu.exec(self.tree.mapToGlobal(pos))

    def on_patient_select(self):
        selected = bool(self.tree.selectedItems())
        self.edit_button.setEnabled(selected)
        self.delete_history_button.setEnabled(selected)

    def fill_patient(self):
        selected = self.tree.selectedItems()
        if selected:
            row = selected[0].row()
            patient_id = self.tree.item(row, 1).data(Qt.UserRole)
            logical_hid = self.tree.item(row, 1).data(Qt.UserRole + 1)
            patient = self.db.get_patient_by_id(patient_id)
            if patient:
                card_number = str(logical_hid) if logical_hid else str(patient_id)
                page = StationaryCardPage(self, self.db, patient_id, patient, card_number)
                try:
                    # push into main navigation if available
                    self.nav_push(page)
                except Exception:
                    # fallback to modal dialog behavior if navigation unavailable
                    page.show()

    def delete_history(self):
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите запись для удаления.")
            return
        row = selected[0].row()
        # history_id is the logical history number stored in UserRole+1
        logical_history_id = self.tree.item(row, 1).data(Qt.UserRole + 1)
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
        pmr_cities = [
            "",
            "Тирасполь",
            "Бендеры",
            "Рыбница",
            "Дубоссары",
            "Слободзея",
            "Григориополь",
            "Каменка",
            "Днестровск",
            "Парканы",
            "Гиска",
            "Суклея",
            "Косница",
            "Бутучаны",
            "Бычок",
            "Маяк",
            "Глиное",
            "Сергиевка",
            "Первомайск",
            "Солнечное",
        ]
        self.city_combo.addItems(pmr_cities)
        from PySide6.QtWidgets import QCompleter
        city_completer = QCompleter(pmr_cities, self.city_combo)
        city_completer.setCaseSensitivity(Qt.CaseInsensitive)
        city_completer.setFilterMode(Qt.MatchContains)
        self.city_combo.setCompleter(city_completer)
        layout.addWidget(self.city_combo)

        self.street_combo = QComboBox()
        self.street_combo.setEditable(True)
        pmr_streets = [
            "",
            "ул. Ленина",
            "ул. 25 Октября",
            "ул. Карла Либкнехта",
            "ул. Краснодонская",
            "ул. Комсомольская",
            "ул. Чернышевского",
            "ул. Шевченко",
            "ул. Одесская",
            "ул. Киевская",
            "ул. Транспортная",
            "ул. Советская",
            "ул. Гагарина",
        ]
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
    def __init__(self, patient_id, patient, db, parent):
        super().__init__(parent)
        self.patient_id = patient_id
        self.patient = patient
        self.db = db
        self.setWindowTitle(f"Histories for {patient[1]}")
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
        self.db.add_history(self.patient_id, "history", exam, diag, treat, notes)
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
        for h in histories:
            # Convert possible HTML to plain text and create a single-line preview
            try:
                doc = QTextDocument()
                doc.setHtml(h[3])
                plain = doc.toPlainText()
            except Exception:
                plain = h[3] or ""
            preview = ' '.join(plain.split())[:120]
            if len(plain) > 120:
                preview = preview + '...'
            self.histories_list.addItem(preview)

    def load_history(self):
        selected = self.histories_list.selectedItems()
        if selected:
            index = self.histories_list.row(selected[0])
            histories = self.db.get_histories(self.patient_id)
            h = histories[index]
            # If stored as HTML, convert to plain text to preserve newlines
            try:
                doc = QTextDocument()
                doc.setHtml(h[3])
                plain = doc.toPlainText()
            except Exception:
                plain = h[3] or ""
            self.exam_text.setPlainText(plain)
            self.diag_entry.setText(h[4])
            self.treat_entry.setText(h[5])
            self.notes_text.setPlainText(h[6])

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
            self.histories_list.addItem(f"{h[3][:50]}...")

    def load_history(self):
        selected = self.histories_list.selectedItems()
        if selected:
            index = self.histories_list.row(selected[0])
            histories = self.db.get_histories(self.patient_id)
            h = histories[index]
            try:
                doc = QTextDocument()
                doc.setHtml(h[3])
                plain = doc.toPlainText()
            except Exception:
                plain = h[3] or ""
            self.exam_text.setPlainText(plain)
            self.diag_entry.setText(h[4])
            self.treat_entry.setText(h[5])
            self.notes_text.setPlainText(h[6])