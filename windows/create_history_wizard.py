from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QCompleter,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStackedLayout,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QDateEdit,
)


@dataclass(frozen=True)
class WizardPatient:
    patient_id: int
    surname: str
    name: str
    dob: str
    address: str

    @property
    def display_name(self) -> str:
        full = f"{self.surname} {self.name}".strip()
        return full if full else self.surname


class CreateHistoryWizard(QDialog):
    """
    Визард "Создание истории болезни":
    - Шаг 1: выбор/создание пациента
    - Шаг 2: статистические данные (2 вкладки)
    Поддерживает опциональный `done_callback(patient_id)` для использования внутри навигационной
    стеки вместо modal `exec()`.
    """

    def __init__(self, parent, db, done_callback=None):
        super().__init__(parent)
        self.db = db
        self.patient_id: int | None = None
        self.done_callback = done_callback

        self.setWindowTitle("Создание истории болезни")
        self.setModal(True)
        self.resize(900, 650)

        root = QVBoxLayout(self)
        self._stack = QStackedLayout()
        root.addLayout(self._stack)

        self._page1 = self._build_step1()
        self._page2 = self._build_step2()
        self._stack.addWidget(self._page1)
        self._stack.addWidget(self._page2)

        self._set_step(1)

    # -----------------
    # Step 1 (patient)
    # -----------------
    def _build_step1(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Создание истории болезни")
        title.setStyleSheet("font-weight: 700; font-size: 20px; color: #0b4aa2;")
        layout.addWidget(title)

        subtitle = QLabel("шаг 1: выберите пациента")
        subtitle.setStyleSheet("color: #0b4aa2;")
        layout.addWidget(subtitle)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        layout.addWidget(QLabel("Выберите из списка"))

        toolbar = QHBoxLayout()
        self.add_btn = QPushButton("Добавить")
        self.add_btn.clicked.connect(self._add_patient)
        # green = add
        self.add_btn.setStyleSheet("background-color: #2ecc71; color: white; font-weight: 600;")
        toolbar.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Изменить")
        self.edit_btn.clicked.connect(self._edit_selected_patient)
        # yellow = edit
        self.edit_btn.setStyleSheet("background-color: #f1c40f; color: black; font-weight: 600;")
        toolbar.addWidget(self.edit_btn)

        self.del_btn = QPushButton("Удалить")
        self.del_btn.clicked.connect(self._delete_selected_patient)
        # red = delete
        self.del_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: 600;")
        toolbar.addWidget(self.del_btn)

        toolbar.addStretch(1)

        toolbar.addWidget(QLabel("Поиск:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Фамилия или имя…")
        self.search_edit.textChanged.connect(self._reload_patients)
        toolbar.addWidget(self.search_edit)

        layout.addLayout(toolbar)

        self.patients_tree = QTreeWidget()
        self.patients_tree.setHeaderLabels(["ФИО", "Дата рождения", "Адрес"])
        self.patients_tree.setRootIsDecorated(False)
        self.patients_tree.setAlternatingRowColors(True)
        self.patients_tree.itemSelectionChanged.connect(self._on_patient_selection_changed)
        layout.addWidget(self.patients_tree, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.next_btn = QPushButton("Далее >>>")
        self.next_btn.clicked.connect(self._go_next_from_step1)
        self.next_btn.setEnabled(False)
        bottom.addWidget(self.next_btn)
        layout.addLayout(bottom)

        self._reload_patients()
        return page

    def _patients_from_db(self) -> list[WizardPatient]:
        patients = []
        for p in self.db.get_patients():
            # patients: (id, surname, name, dob, created_at, address?)
            pid = int(p[0])
            surname = p[1] or ""
            name = (p[2] or "") if len(p) > 2 else ""
            dob = (p[3] or "") if len(p) > 3 else ""
            # compose address from components if present
            address = ""
            try:
                city = p[5] if len(p) > 5 and p[5] else ''
                street = p[6] if len(p) > 6 and p[6] else ''
                house = p[7] if len(p) > 7 and p[7] else ''
                apt = p[8] if len(p) > 8 and p[8] else ''
                parts = []
                if city:
                    parts.append(city)
                if street:
                    parts.append(street)
                if house:
                    parts.append(house)
                if apt:
                    parts.append(apt)
                address = ", ".join(parts)
            except Exception:
                address = ""
            patients.append(
                WizardPatient(
                    patient_id=pid,
                    surname=surname,
                    name=name,
                    dob=dob,
                    address=address,
                )
            )
        return patients

    def _reload_patients(self) -> None:
        query = (self.search_edit.text() or "").strip().lower()
        self.patients_tree.clear()

        for p in self._patients_from_db():
            if query:
                hay = f"{p.surname} {p.name}".lower()
                if query not in hay:
                    continue
            item = QTreeWidgetItem([p.display_name, p.dob, p.address])
            item.setData(0, Qt.UserRole, p.patient_id)
            self.patients_tree.addTopLevelItem(item)

        self.patients_tree.resizeColumnToContents(0)
        self._on_patient_selection_changed()

    def _selected_patient_id(self) -> int | None:
        sel = self.patients_tree.selectedItems()
        if not sel:
            return None
        return sel[0].data(0, Qt.UserRole)

    def _on_patient_selection_changed(self) -> None:
        has_selection = self._selected_patient_id() is not None
        self.next_btn.setEnabled(has_selection)
        self.edit_btn.setEnabled(has_selection)
        self.del_btn.setEnabled(has_selection)

    def _add_patient(self) -> None:
        dialog = _PatientEditDialog(self, title="Новый пациент")
        # If main application navigation is available, push non-blocking dialog into nav stack
        app_main = self.parent()
        def _on_accept_new():
            # collect components from dialog
            city = getattr(dialog, 'city', None)
            street = getattr(dialog, 'street', None)
            house = getattr(dialog, 'house', None)
            apartment = getattr(dialog, 'apartment', None) or ''
            patient_id = self.db.add_patient(
                dialog.surname,
                dialog.name,
                dialog.dob,
                city=city or '',
                street=street or '',
                house=house or '',
                apartment=apartment,
            )
            self._reload_patients()
            self._select_patient_in_tree(patient_id)
            try:
                if app_main is not None and hasattr(app_main, '_nav_back'):
                    app_main._nav_back()
            except Exception:
                pass

        dialog.accepted.connect(_on_accept_new)
        try:
            if app_main is not None and hasattr(app_main, 'nav_push'):
                app_main.nav_push(dialog)
                return
        except Exception:
            pass
        # Non-blocking fallback: show dialog and rely on `accepted` handler
        try:
            dialog.show()
        except Exception:
            pass

    def _select_patient_in_tree(self, patient_id: int) -> None:
        for i in range(self.patients_tree.topLevelItemCount()):
            item = self.patients_tree.topLevelItem(i)
            if item.data(0, Qt.UserRole) == patient_id:
                self.patients_tree.setCurrentItem(item)
                break

    def _edit_selected_patient(self) -> None:
        patient_id = self._selected_patient_id()
        if patient_id is None:
            return

        patient = self.db.get_patient_by_id(patient_id)
        if not patient:
            return

        surname = patient[1] or ""
        name = patient[2] or ""
        dob = patient[3] or ""
        # compose address from stored components (city, street, house, apartment)
        address = ""
        try:
            city = patient[5] if len(patient) > 5 and patient[5] else ''
            street = patient[6] if len(patient) > 6 and patient[6] else ''
            house = patient[7] if len(patient) > 7 and patient[7] else ''
            apt = patient[8] if len(patient) > 8 and patient[8] else ''
            parts = []
            if city:
                parts.append(city)
            if street:
                parts.append(street)
            if house:
                parts.append(house)
            if apt:
                parts.append(apt)
            address = ", ".join(parts)
        except Exception:
            address = ""

        dialog = _PatientEditDialog(
            self,
            title="Редактирование пациента",
            surname=surname,
            name=name,
            dob=dob,
            address=address,
        )

        app_main = self.parent()

        def _on_accept_edit():
            city = getattr(dialog, 'city', None)
            street = getattr(dialog, 'street', None)
            house = getattr(dialog, 'house', None)
            apartment = getattr(dialog, 'apartment', None) or ''
            self.db.update_patient(
                patient_id,
                dialog.surname,
                dialog.name,
                dialog.dob,
                city=city or '',
                street=street or '',
                house=house or '',
                apartment=apartment,
            )
            self._reload_patients()
            self._select_patient_in_tree(int(patient_id))
            try:
                if app_main is not None and hasattr(app_main, '_nav_back'):
                    app_main._nav_back()
            except Exception:
                pass

        dialog.accepted.connect(_on_accept_edit)
        try:
            if app_main is not None and hasattr(app_main, 'nav_push'):
                app_main.nav_push(dialog)
                return
        except Exception:
            pass

        # Non-blocking fallback: show dialog and rely on `accepted` handler
        try:
            dialog.show()
        except Exception:
            pass

    def _delete_selected_patient(self) -> None:
        patient_id = self._selected_patient_id()
        if patient_id is None:
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Удалить этого пациента и все его истории?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.db.delete_patient(patient_id)
        self._reload_patients()

    def _go_next_from_step1(self) -> None:
        patient_id = self._selected_patient_id()
        if patient_id is None:
            QMessageBox.warning(self, "Ошибка", "Выберите пациента.")
            return

        self.patient_id = int(patient_id)
        self._prepare_step2_header()
        self._set_step(2)

    # -----------------
    # Step 2 (stats)
    # -----------------
    def _build_step2(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("Создание истории болезни")
        title.setStyleSheet("font-weight: 700; font-size: 20px; color: #0b4aa2;")
        layout.addWidget(title)

        subtitle = QLabel("шаг 2: внесите статистические данные")
        subtitle.setStyleSheet("color: #0b4aa2;")
        layout.addWidget(subtitle)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        self.step2_patient_label = QLabel("")
        layout.addWidget(self.step2_patient_label)

        top_grid = QGridLayout()
        layout.addLayout(top_grid)

        top_grid.addWidget(QLabel("Номер карты"), 0, 0)
        self.card_number_edit = QLineEdit()
        self.card_number_edit.setReadOnly(True)
        top_grid.addWidget(self.card_number_edit, 0, 1)

        top_grid.addWidget(QLabel("Поступил в приемное отделение"), 0, 2)
        date_wrap = QWidget()
        date_wrap_lay = QHBoxLayout(date_wrap)
        date_wrap_lay.setContentsMargins(0, 0, 0, 0)
        date_wrap_lay.setSpacing(6)
        self.admission_date_edit = QLineEdit()
        self.admission_date_edit.setPlaceholderText("__.__.____")
        date_wrap_lay.addWidget(self.admission_date_edit)
        self.admission_date_now_btn = QPushButton("Сегодня")
        self.admission_date_now_btn.setMaximumWidth(90)
        self.admission_date_now_btn.clicked.connect(self._set_admission_date_now)
        date_wrap_lay.addWidget(self.admission_date_now_btn)
        top_grid.addWidget(date_wrap, 0, 3)

        top_grid.addWidget(QLabel("время"), 0, 4)
        time_wrap = QWidget()
        time_wrap_lay = QHBoxLayout(time_wrap)
        time_wrap_lay.setContentsMargins(0, 0, 0, 0)
        time_wrap_lay.setSpacing(6)
        self.admission_time_edit = QLineEdit()
        self.admission_time_edit.setPlaceholderText("__:__")
        time_wrap_lay.addWidget(self.admission_time_edit)
        self.admission_time_now_btn = QPushButton("Сейчас")
        self.admission_time_now_btn.setMaximumWidth(90)
        self.admission_time_now_btn.clicked.connect(self._set_admission_time_now)
        time_wrap_lay.addWidget(self.admission_time_now_btn)
        top_grid.addWidget(time_wrap, 0, 5)

        top_grid.addWidget(QLabel("Диагноз при поступлении"), 1, 0)
        self.admission_diag_edit = QLineEdit()
        top_grid.addWidget(self.admission_diag_edit, 1, 1, 1, 2)

        top_grid.addWidget(QLabel("Клинический диагноз"), 1, 3)
        self.clinical_diag_edit = QLineEdit()
        top_grid.addWidget(self.clinical_diag_edit, 1, 4, 1, 2)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self._tab_page1 = QWidget()
        self.tabs.addTab(self._tab_page1, "Страница 1")

        self._build_tab_page1(self._tab_page1)

        bottom = QHBoxLayout()
        self.back_btn = QPushButton("<<< Назад")
        self.back_btn.clicked.connect(lambda: self._set_step(1))
        bottom.addWidget(self.back_btn)
        bottom.addStretch(1)
        self.done_btn = QPushButton("Готово")
        self.done_btn.clicked.connect(self._finish)
        bottom.addWidget(self.done_btn)
        layout.addLayout(bottom)

        return page

    def _build_tab_page1(self, parent: QWidget) -> None:
        lay = QVBoxLayout(parent)

        # Адрес фактического проживания с автодополнением по населенным пунктам и улицам ПМР
        lay.addWidget(QLabel("Адрес фактического проживания"))
        addr_grid = QGridLayout()
        lay.addLayout(addr_grid)

        addr_grid.addWidget(QLabel("Населенный пункт"), 0, 0)
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
        city_completer = QCompleter(pmr_cities, self.city_combo)
        city_completer.setCaseSensitivity(Qt.CaseInsensitive)
        city_completer.setFilterMode(Qt.MatchContains)
        self.city_combo.setCompleter(city_completer)
        addr_grid.addWidget(self.city_combo, 0, 1, 1, 3)

        addr_grid.addWidget(QLabel("Улица"), 1, 0)
        self.street_combo = QComboBox()
        self.street_combo.setEditable(True)
        pmr_streets = [
            "",
            "ул. Ленина",
            "ул. 25 Октября",
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
            "ул. Интернациональная",
            "ул. Юности",
            "пер. Школьный",
        ]
        self.street_combo.addItems(pmr_streets)
        street_completer = QCompleter(pmr_streets, self.street_combo)
        street_completer.setCaseSensitivity(Qt.CaseInsensitive)
        street_completer.setFilterMode(Qt.MatchContains)
        self.street_combo.setCompleter(street_completer)
        addr_grid.addWidget(self.street_combo, 1, 1, 1, 3)

        addr_grid.addWidget(QLabel("Дом, кв."), 2, 0)
        self.house_edit = QLineEdit()
        addr_grid.addWidget(self.house_edit, 2, 1)

        lay.addStretch(1)

    def _prepare_step2_header(self) -> None:
        if self.patient_id is None:
            self.step2_patient_label.setText("")
            return

        patient = self.db.get_patient_by_id(self.patient_id)
        if not patient:
            self.step2_patient_label.setText("")
            return

        surname = patient[1] or ""
        name = patient[2] or ""
        dob = patient[3] or ""
        fio = f"{surname} {name}".strip()
        self.step2_patient_label.setText(f"{fio}, {dob}".strip(", "))

        # Автозаполнение полей шага 2
        self.card_number_edit.setText(self._generate_history_number())
        self._set_admission_date_now()
        self._set_admission_time_now()
        # If patient has address components stored, prefill the fields directly
        try:
            city = patient[5] if len(patient) > 5 and patient[5] else ''
            street = patient[6] if len(patient) > 6 and patient[6] else ''
            house = patient[7] if len(patient) > 7 and patient[7] else ''
            apt = patient[8] if len(patient) > 8 and patient[8] else ''
            try:
                if city:
                    self.city_combo.setEditText(city)
            except Exception:
                pass
            try:
                if street:
                    self.street_combo.setEditText(street)
            except Exception:
                pass
            try:
                if house:
                    self.house_edit.setText(house)
            except Exception:
                pass
        except Exception:
            pass

    def _generate_history_number(self) -> str:
        """
        Генерируем простой последовательный номер истории болезни, начиная с 1.
        Используем следующий свободный id из таблицы histories.
        """
        try:
            next_id = self.db.get_next_history_number()
        except Exception:
            # запасной вариант, если метод недоступен
            next_id = 1
        return str(next_id)

    def _set_admission_date_now(self) -> None:
        self.admission_date_edit.setText(datetime.now().strftime("%d.%m.%Y"))

    def _set_admission_time_now(self) -> None:
        self.admission_time_edit.setText(datetime.now().strftime("%H:%M"))

    def _set_discharge_date_now(self) -> None:
        self.discharge_date_edit.setText(datetime.now().strftime("%d.%m.%Y"))

    def _finish(self) -> None:
        if self.patient_id is None:
            QMessageBox.warning(self, "Ошибка", "Не выбран пациент.")
            return

        try:
            # Сохраняем паспортную часть истории болезни
            passport_info = (
                f"Номер карты: {self.card_number_edit.text().strip()}\n"
                f"Дата поступления: {self.admission_date_edit.text().strip()} {self.admission_time_edit.text().strip()}\n"
                f"Диагноз при поступлении: {self.admission_diag_edit.text().strip()}\n"
                f"Клинический диагноз: {self.clinical_diag_edit.text().strip()}\n"
            )
            diag_admission = self.admission_diag_edit.text().strip()
            diag_clinical = self.clinical_diag_edit.text().strip()
            history_id_val = int(self.card_number_edit.text().strip())
            
            self.db.add_history(self.patient_id, "passport", passport_info, 
                                diagnosis=diag_admission, 
                                diag_admission=diag_admission, 
                                diag_clinical=diag_clinical,
                                history_id=history_id_val)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при сохранении: {e}")
            return

        # Сохраняем ссылки до закрытия/удаления объекта
        pid = self.patient_id
        cb = self.done_callback

        # 1. Закрываем текущее окно
        closed_via_nav = False
        anc = self.parent()
        while anc is not None:
            if hasattr(anc, '_nav_back') and hasattr(anc, '_nav_stack'):
                if self in anc._nav_stack:
                    anc._nav_back()
                    closed_via_nav = True
                    break
            try:
                anc = anc.parent()
            except Exception:
                anc = None

        if not closed_via_nav:
            self.accept()
            self.close()

        # 2. Вызываем колбэк (обновление списка и открытие карты)
        # Используем QTimer.singleShot для вызова после завершения цикла обработки событий закрытия
        if cb and callable(cb):
            QTimer.singleShot(0, lambda: cb(pid))

    # -----------------
    # Shared
    # -----------------
    def _set_step(self, step: int) -> None:
        if step == 1:
            self._stack.setCurrentIndex(0)
        else:
            self._stack.setCurrentIndex(1)

class _PatientEditDialog(QDialog):
    def __init__(
        self,
        parent,
        title: str,
        surname: str = "",
        name: str = "",
        dob: str = "",
        address: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 220)

        layout = QVBoxLayout(self)
        grid = QGridLayout()
        layout.addLayout(grid)

        grid.addWidget(QLabel("Фамилия*"), 0, 0)
        self._surname_edit = QLineEdit(surname)
        grid.addWidget(self._surname_edit, 0, 1)

        grid.addWidget(QLabel("Имя"), 0, 2)
        self._name_edit = QLineEdit(name)
        grid.addWidget(self._name_edit, 0, 3)

        grid.addWidget(QLabel("Дата рождения"), 1, 0)
        from PySide6.QtCore import QDate, QLocale
        self._dob_edit = QDateEdit()
        # try to parse incoming dob string
        if dob:
            d = QDate.fromString(dob, "yyyy-MM-dd")
            if not d.isValid():
                d = QDate.fromString(dob, "dd.MM.yyyy")
            if d.isValid():
                self._dob_edit.setDate(d)
            else:
                self._dob_edit.setDate(QDate.currentDate())
        else:
            self._dob_edit.setDate(QDate.currentDate())
        self._dob_edit.setCalendarPopup(True)
        self._dob_edit.setLocale(QLocale(QLocale.Russian))
        self._dob_edit.setDisplayFormat("dd.MM.yyyy")
        grid.addWidget(self._dob_edit, 1, 1)

        # Address: city, street, house with autocompletion
        grid.addWidget(QLabel("Город/населенный пункт"), 1, 2)
        self._city_combo = QComboBox()
        self._city_combo.setEditable(True)
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
        self._city_combo.addItems(pmr_cities)
        try:
            completer = QCompleter(pmr_cities, self._city_combo)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            self._city_combo.setCompleter(completer)
        except Exception:
            pass
        grid.addWidget(self._city_combo, 1, 3)

        grid.addWidget(QLabel("Улица"), 2, 2)
        self._street_combo = QComboBox()
        self._street_combo.setEditable(True)
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
        self._street_combo.addItems(pmr_streets)
        try:
            street_comp = QCompleter(pmr_streets, self._street_combo)
            street_comp.setCaseSensitivity(Qt.CaseInsensitive)
            street_comp.setFilterMode(Qt.MatchContains)
            self._street_combo.setCompleter(street_comp)
        except Exception:
            pass
        grid.addWidget(self._street_combo, 2, 3)

        grid.addWidget(QLabel("Дом, кв."), 3, 2)
        self._house_edit = QLineEdit()
        grid.addWidget(self._house_edit, 3, 3)

        # If an address string was provided, try to parse into components
        if address:
            try:
                import re
                parts = [p.strip() for p in address.split(',') if p.strip()]
                city = parts[0] if parts else ''
                street = ''
                house = ''
                if len(parts) >= 2:
                    street = parts[1]
                if len(parts) >= 3:
                    house = parts[2]
                if not house and street:
                    m = re.search(r"(\d+[A-Za-zА-Яа-я\-\/\w]*)$", street)
                    if m:
                        house = m.group(1).strip()
                        street = street[:m.start()].strip()
                try:
                    if city:
                        self._city_combo.setEditText(city)
                except Exception:
                    pass
                try:
                    if street:
                        self._street_combo.setEditText(street)
                except Exception:
                    pass
                try:
                    if house:
                        self._house_edit.setText(house)
                except Exception:
                    pass
            except Exception:
                try:
                    self._city_combo.setEditText(address)
                except Exception:
                    self._house_edit.setText(address)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        ok = QPushButton("Сохранить")
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

        cancel.clicked.connect(self._close_window)
        ok.clicked.connect(self._on_ok)

    def _close_window(self):
        # Если мы в навигационном стеке, возвращаемся назад
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, '_nav_back'):
                parent._nav_back()
                return
            parent = parent.parent()

        self.reject()

    @property
    def surname(self) -> str:
        return self._surname_edit.text().strip()

    @property
    def name(self) -> str:
        return self._name_edit.text().strip()

    @property
    def dob(self) -> str:
        return self._dob_edit.date().toString("yyyy-MM-dd")

    @property
    def address(self) -> str:
        parts = []
        try:
            c = self._city_combo.currentText().strip()
            if c:
                parts.append(c)
        except Exception:
            pass
        try:
            s = self._street_combo.currentText().strip()
            if s:
                parts.append(s)
        except Exception:
            pass
        try:
            h = self._house_edit.text().strip()
            if h:
                parts.append(h)
        except Exception:
            pass
        return ", ".join(parts)

    @property
    def city(self) -> str:
        try:
            return self._city_combo.currentText().strip()
        except Exception:
            return ""

    @property
    def street(self) -> str:
        try:
            return self._street_combo.currentText().strip()
        except Exception:
            return ""

    @property
    def house(self) -> str:
        try:
            return self._house_edit.text().strip()
        except Exception:
            return ""

    @property
    def apartment(self) -> str:
        return ""

    def _on_ok(self) -> None:
        if not self.surname:
            QMessageBox.warning(self, "Ошибка", "Фамилия обязательна.")
            return
        self.accept()

    def _close_window(self):
        self.reject()

