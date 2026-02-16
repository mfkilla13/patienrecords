import json
import os
from .config import LOCAL_ROWS_CONFIG
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QTabWidget,
    QWidget,
    QMessageBox,
    QComboBox,
    QCheckBox,
    QListWidget,
    QInputDialog,
    QTableWidget,
    QHeaderView,
    QScrollArea,
)
from PySide6.QtCore import Qt


class MultiSelectDialog(QDialog):
    """
    Диалог множественного выбора (чекбоксы) + необязательное примечание.
    Возвращает:
      - список выбранных пунктов
      - строку примечания
    """

    def __init__(self, parent, title, options, selected=None, note_text=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(520, 420)

        self._options = options
        self._selected = set(selected or [])
        self._note_text = note_text or ""

        main = QVBoxLayout(self)

        # чекбоксы
        self.checkboxes = []
        for opt in options:
            cb = QCheckBox(opt)
            cb.setChecked(opt in self._selected)
            self.checkboxes.append(cb)
            main.addWidget(cb)

        main.addWidget(QLabel("Примечание (если нужно):"))
        self.note_edit = QLineEdit(self._note_text)
        main.addWidget(self.note_edit)

        btns = QHBoxLayout()
        btn_cancel = QPushButton("Отмена")
        btn_ok = QPushButton("ОК")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        main.addLayout(btns)

    def get_result(self):
        selected = [cb.text() for cb in self.checkboxes if cb.isChecked()]
        note = self.note_edit.text().strip()
        return selected, note


class EnhancedMultiSelectDialog(QDialog):
    """
    Диалог множественного выбора с QListWidget (стрелками) + возможность добавить новый диагноз + примечание.
    Поддерживает работу как с простым списком [], так и со словарем {"category": []}.
    """

    def __init__(self, parent, title, options, selected=None, note_text="", file_path=None, category=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(600, 500)

        self._options = list(options)
        self._selected = list(selected or [])
        self._note_text = note_text or ""
        self._file_path = file_path
        self._category = category

        main = QVBoxLayout(self)

        # Верхняя часть: доступные и выбранные списки
        lists_layout = QHBoxLayout()

        # Левый список: доступные
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Доступные:"))
        self.available_list = QListWidget()
        self.available_list.addItems([opt for opt in self._options if opt not in self._selected])
        left_layout.addWidget(self.available_list)

        # Кнопки управления доступными
        avail_btns = QVBoxLayout()
        self.add_avail_btn = QPushButton("+")
        self.add_avail_btn.clicked.connect(self._add_available)
        avail_btns.addWidget(self.add_avail_btn)
        self.edit_avail_btn = QPushButton("✎")
        self.edit_avail_btn.clicked.connect(self._edit_available)
        avail_btns.addWidget(self.edit_avail_btn)
        self.del_avail_btn = QPushButton("–")
        self.del_avail_btn.clicked.connect(self._delete_available)
        avail_btns.addWidget(self.del_avail_btn)
        avail_btns.addStretch()
        left_layout.addLayout(avail_btns)
        lists_layout.addLayout(left_layout)

        # Кнопки в центре
        buttons_layout = QVBoxLayout()
        buttons_layout.addStretch()
        self.add_button = QPushButton(">")
        self.add_button.clicked.connect(self._add_selected)
        buttons_layout.addWidget(self.add_button)
        self.remove_button = QPushButton("<")
        self.remove_button.clicked.connect(self._remove_selected)
        buttons_layout.addWidget(self.remove_button)
        buttons_layout.addStretch()
        lists_layout.addLayout(buttons_layout)

        # Правый список: выбранные
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("Выбранные:"))
        self.selected_list = QListWidget()
        self.selected_list.addItems(self._selected)
        right_layout.addWidget(self.selected_list)
        self.delete_button = QPushButton("Удалить")
        self.delete_button.clicked.connect(self._delete_selected)
        right_layout.addWidget(self.delete_button)
        lists_layout.addLayout(right_layout)

        main.addLayout(lists_layout)

        # Добавить новое
        add_layout = QHBoxLayout()
        add_layout.addWidget(QLabel("Добавить новое:"))
        self.new_diag_edit = QLineEdit()
        add_layout.addWidget(self.new_diag_edit)
        self.add_new_button = QPushButton("Добавить")
        self.add_new_button.clicked.connect(self._add_new_diag)
        add_layout.addWidget(self.add_new_button)
        main.addLayout(add_layout)

        # Примечание
        main.addWidget(QLabel("Примечание (если нужно):"))
        self.note_edit = QTextEdit(self._note_text)
        main.addWidget(self.note_edit)

        # Кнопки
        btns = QHBoxLayout()
        btn_cancel = QPushButton("Отмена")
        btn_ok = QPushButton("ОК")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        main.addLayout(btns)

    def _add_selected(self):
        current = self.available_list.currentItem()
        if current:
            self.selected_list.addItem(current.text())
            self.available_list.takeItem(self.available_list.row(current))

    def _remove_selected(self):
        current = self.selected_list.currentItem()
        if current:
            self.available_list.addItem(current.text())
            self.selected_list.takeItem(self.selected_list.row(current))

    def _add_new_diag(self):
        new_diag = self.new_diag_edit.text().strip()
        if new_diag and new_diag not in [self.selected_list.item(i).text() for i in range(self.selected_list.count())]:
            self.selected_list.addItem(new_diag)
            # Добавить в общий список и сохранить
            if new_diag not in self._options:
                self._options.append(new_diag)
                self._save_options()
            self.new_diag_edit.clear()

    def _delete_selected(self):
        current = self.selected_list.currentItem()
        if current:
            self.selected_list.takeItem(self.selected_list.row(current))

    def _add_available(self):
        text, ok = QInputDialog.getText(self, "Добавить вариант", "Введите название:")
        if ok and text.strip() and text.strip() not in self._options:
            self._options.append(text.strip())
            self.available_list.addItem(text.strip())
            self._save_options()

    def _edit_available(self):
        current = self.available_list.currentItem()
        if current:
            text, ok = QInputDialog.getText(self, "Редактировать", "Измените название:", text=current.text())
            if ok and text.strip():
                idx = self._options.index(current.text())
                self._options[idx] = text.strip()
                current.setText(text.strip())
                self._save_options()

    def _delete_available(self):
        current = self.available_list.currentItem()
        if current:
            reply = QMessageBox.question(self, "Удалить", f"Удалить '{current.text()}' из списка доступных?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self._options.remove(current.text())
                self.available_list.takeItem(self.available_list.row(current))
                self._save_options()

    def _save_options(self):
        if self._file_path:
            try:
                data_to_save = self._options
                if self._category:
                    # Если работаем со словарем категорий
                    all_data = {}
                    if os.path.exists(self._file_path):
                        with open(self._file_path, "r", encoding="utf-8") as f:
                            all_data = json.load(f)
                    all_data[self._category] = self._options
                    data_to_save = all_data

                with open(self._file_path, 'w', encoding='utf-8') as f:
                    json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить: {e}")

    def get_result(self):
        selected = [self.selected_list.item(i).text() for i in range(self.selected_list.count())]
        note = self.note_edit.toPlainText().strip()
        return selected, note


class DiagnosisManagerDialog(QDialog):
    """
    Диалог для управления списками диагнозов: просмотр, добавление, удаление, редактирование.
    """

    def __init__(self, parent, data_dir):
        super().__init__(parent)
        self.setWindowTitle("Управление диагнозами")
        self.setModal(True)
        self.resize(600, 400)
        self.data_dir = data_dir

        main = QVBoxLayout(self)

        # Выбор типа диагнозов
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Тип диагнозов:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Офтальмологические", "Сопутствующие"])
        self.type_combo.currentTextChanged.connect(self._load_diagnoses)
        type_layout.addWidget(self.type_combo)
        main.addLayout(type_layout)

        # Список диагнозов
        self.diag_list = QListWidget()
        main.addWidget(self.diag_list)

        # Кнопки управления
        buttons_layout = QHBoxLayout()
        self.add_button = QPushButton("Добавить")
        self.add_button.clicked.connect(self._add_diagnosis)
        buttons_layout.addWidget(self.add_button)

        self.edit_button = QPushButton("Редактировать")
        self.edit_button.clicked.connect(self._edit_diagnosis)
        buttons_layout.addWidget(self.edit_button)

        self.delete_button = QPushButton("Удалить")
        self.delete_button.clicked.connect(self._delete_diagnosis)
        buttons_layout.addWidget(self.delete_button)

        main.addLayout(buttons_layout)

        # Кнопки диалога
        dialog_buttons = QHBoxLayout()
        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self._save_diagnoses)
        dialog_buttons.addWidget(save_button)

        close_button = QPushButton("Закрыть")
        close_button.clicked.connect(self.accept)
        dialog_buttons.addWidget(close_button)

        main.addLayout(dialog_buttons)

        self._load_diagnoses()

    def _load_diagnoses(self):
        diag_type = self.type_combo.currentText()
        if diag_type == "Офтальмологические":
            file_path = os.path.join(self.data_dir, 'ophthalmic_diagnoses.json')
        else:
            file_path = os.path.join(self.data_dir, 'comorbid_diagnoses.json')

        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                diagnoses = json.load(f)
        else:
            diagnoses = []

        self.diag_list.clear()
        self.diag_list.addItems(diagnoses)
        self.current_file = file_path

    def _add_diagnosis(self):
        text, ok = QInputDialog.getText(self, "Добавить диагноз", "Введите название диагноза:")
        if ok and text.strip():
            self.diag_list.addItem(text.strip())

    def _edit_diagnosis(self):
        current = self.diag_list.currentItem()
        if current:
            text, ok = QInputDialog.getText(self, "Редактировать диагноз", "Измените название:", text=current.text())
            if ok and text.strip():
                current.setText(text.strip())

    def _delete_diagnosis(self):
        current = self.diag_list.currentItem()
        if current:
            reply = QMessageBox.question(self, "Удалить диагноз", f"Удалить '{current.text()}'?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.diag_list.takeItem(self.diag_list.row(current))

    def _save_diagnoses(self):
        diagnoses = [self.diag_list.item(i).text() for i in range(self.diag_list.count())]
        try:
            with open(self.current_file, 'w', encoding='utf-8') as f:
                json.dump(diagnoses, f, ensure_ascii=False, indent=4)
            QMessageBox.information(self, "Сохранено", "Диагнозы сохранены!")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить: {e}")


class MultiSelectButton(QPushButton):
    """
    Кнопка, открывающая MultiSelectDialog.
    Хранит выбранные значения + примечание.
    В тексте кнопки показывает краткое резюме.
    """

    def __init__(self, title, options, parent=None):
        super().__init__(parent)
        self._title = title
        self._options = options
        self._selected = []
        self._note = ""

        self.setText("выбрать…")
        self.setMinimumWidth(260)
        self.clicked.connect(self.open_dialog)

    def open_dialog(self):
        dlg = MultiSelectDialog(
            self,
            title=self._title,
            options=self._options,
            selected=self._selected,
            note_text=self._note,
        )
        if dlg.exec() == QDialog.Accepted:
            self._selected, self._note = dlg.get_result()
            self._refresh_text()

    def _refresh_text(self):
        if not self._selected and not self._note:
            self.setText("выбрать…")
            return

        # короткий вывод на кнопке
        parts = []
        if self._selected:
            joined = "; ".join(self._selected)
            # ограничим длину, чтобы UI не разъезжался
            if len(joined) > 40:
                joined = joined[:37] + "…"
            parts.append(joined)
        if self._note:
            note = self._note
            if len(note) > 20:
                note = note[:17] + "…"
            parts.append(f"прим.: {note}")
        self.setText(" | ".join(parts))

    def get_text(self) -> str:
        """
        Полное текстовое значение для сохранения (без обрезаний).
        """
        if not self._selected and not self._note:
            return ""
        out = "; ".join(self._selected) if self._selected else ""
        if self._note:
            if out:
                out += f" (прим.: {self._note})"
            else:
                out = f"(прим.: {self._note})"
        return out

    def set_value(self, selected_list, note=""):
        self._selected = list(selected_list or [])
        self._note = note or ""
        self._refresh_text()


class EnhancedMultiSelectButton(QPushButton):
    """
    Кнопка, открывающая EnhancedMultiSelectDialog.
    Хранит выбранные значения + примечание.
    В тексте кнопки показывает краткое резюме.
    """

    def __init__(self, title, options, parent=None, file_path=None, category=None):
        super().__init__(parent)
        self._title = title
        self._options = list(options)
        self._file_path = file_path
        self._category = category
        self._selected = []
        self._note = ""

        self.setText("выбрать…")
        self.setMinimumWidth(260)
        self.clicked.connect(self.open_dialog)

    def open_dialog(self):
        # Refresh options from file if exists
        if self._file_path and os.path.exists(self._file_path):
            try:
                with open(self._file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if self._category and isinstance(data, dict):
                        self._options = data.get(self._category, [])
                    elif isinstance(data, list):
                        self._options = data
            except Exception:
                pass

        dlg = EnhancedMultiSelectDialog(
            self,
            title=self._title,
            options=self._options,
            selected=self._selected,
            note_text=self._note,
            file_path=self._file_path,
            category=self._category
        )
        if dlg.exec() == QDialog.Accepted:
            self._selected, self._note = dlg.get_result()
            self._refresh_text()

    def _refresh_text(self):
        if not self._selected and not self._note:
            self.setText("выбрать…")
            return

        parts = []
        if self._selected:
            joined = "; ".join(self._selected)
            if len(joined) > 40:
                joined = joined[:37] + "…"
            parts.append(joined)
        if self._note:
            note = self._note
            if len(note) > 20:
                note = note[:17] + "…"
            parts.append(f"прим.: {note}")
        self.setText(" | ".join(parts))

    def get_text(self) -> str:
        if not self._selected and not self._note:
            return ""
        out = "; ".join(self._selected) if self._selected else ""
        if self._note:
            if out:
                out += f" (прим.: {self._note})"
            else:
                out = f"(прим.: {self._note})"
        return out


class PrimaryExamWindow(QDialog):
    def __init__(self, parent, db, patient_id, records_table, load_records_list_callback, history_id=None):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.history_id = history_id
        self.records_table = records_table
        self.load_records_list = load_records_list_callback
        self.setWindowTitle("Первичный осмотр")
        self.setModal(True)
        self.resize(820, 680)
        self.create_widgets()

    def create_widgets(self):
        main_layout = QVBoxLayout(self)

        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # =========================
        # Tab 1: Жалобы и анамнез
        # =========================
        complaints_widget = QWidget()
        complaints_layout = QVBoxLayout(complaints_widget)

        complaints_layout.addWidget(QLabel("Жалобы:"))
        self.complaints_text = QTextEdit()
        complaints_layout.addWidget(self.complaints_text)

        # Кнопки быстрого ввода для жалоб
        complaints_tags_layout = QHBoxLayout()

        comp_tag1 = QPushButton("на")
        comp_tag1.clicked.connect(lambda: self.insert_tag(self.complaints_text, "на"))
        complaints_tags_layout.addWidget(comp_tag1)

        comp_tag2 = QPushButton("боли")
        comp_tag2.clicked.connect(lambda: self.insert_tag(self.complaints_text, "боли"))
        complaints_tags_layout.addWidget(comp_tag2)

        comp_tag3 = QPushButton("в")
        comp_tag3.clicked.connect(lambda: self.insert_tag(self.complaints_text, "в"))
        complaints_tags_layout.addWidget(comp_tag3)

        comp_tag4 = QPushButton("обеих глазах")
        comp_tag4.clicked.connect(lambda: self.insert_tag(self.complaints_text, "обеих глазах"))
        complaints_tags_layout.addWidget(comp_tag4)

        comp_tag5 = QPushButton("правом глазу")
        comp_tag5.clicked.connect(lambda: self.insert_tag(self.complaints_text, "правом глазу"))
        complaints_tags_layout.addWidget(comp_tag5)

        comp_tag6 = QPushButton("левом глазу")
        comp_tag6.clicked.connect(lambda: self.insert_tag(self.complaints_text, "левом глазу"))
        complaints_tags_layout.addWidget(comp_tag6)

        comp_tag7 = QPushButton("снижение зрения")
        comp_tag7.clicked.connect(lambda: self.insert_tag(self.complaints_text, "снижение зрения"))
        complaints_tags_layout.addWidget(comp_tag7)

        comp_tag8 = QPushButton(",")
        comp_tag8.clicked.connect(lambda: self.insert_tag(self.complaints_text, ","))
        complaints_tags_layout.addWidget(comp_tag8)

        complaints_layout.addLayout(complaints_tags_layout)

        complaints_tags_layout2 = QHBoxLayout()

        comp_tag5 = QPushButton("OU")
        comp_tag5.clicked.connect(lambda: self.insert_tag(self.complaints_text, "OU"))
        complaints_tags_layout2.addWidget(comp_tag5)

        comp_tag6 = QPushButton("OD")
        comp_tag6.clicked.connect(lambda: self.insert_tag(self.complaints_text, "OD"))
        complaints_tags_layout2.addWidget(comp_tag6)

        comp_tag7 = QPushButton("OS")
        comp_tag7.clicked.connect(lambda: self.insert_tag(self.complaints_text, "OS"))
        complaints_tags_layout2.addWidget(comp_tag7)

        comp_tag8 = QPushButton("отсутствие зрения")
        comp_tag8.clicked.connect(lambda: self.insert_tag(self.complaints_text, "отсутствие зрения"))
        complaints_tags_layout2.addWidget(comp_tag8)

        comp_tag9 = QPushButton("искажение изображения")
        comp_tag9.clicked.connect(lambda: self.insert_tag(self.complaints_text, "искажение изображения"))
        complaints_tags_layout2.addWidget(comp_tag9)

        comp_tag10 = QPushButton("зрительный дискомфорт")
        comp_tag10.clicked.connect(lambda: self.insert_tag(self.complaints_text, "зрительный дискомфорт"))
        complaints_tags_layout2.addWidget(comp_tag10)

        complaints_layout.addLayout(complaints_tags_layout2)

        complaints_layout.addWidget(QLabel("История настоящего заболевания:"))
        self.disease_anamnesis_text = QTextEdit()
        complaints_layout.addWidget(self.disease_anamnesis_text)

        tags_layout = QHBoxLayout()
        tag1_button = QPushButton("болеет около")
        tag1_button.clicked.connect(lambda: self.insert_tag(self.disease_anamnesis_text, "болеет около"))
        tags_layout.addWidget(tag1_button)

        tag2_button = QPushButton("ухудшение отмечает за последние")
        tag2_button.clicked.connect(lambda: self.insert_tag(self.disease_anamnesis_text, "ухудшение отмечает за последние"))
        tags_layout.addWidget(tag2_button)

        complaints_layout.addLayout(tags_layout)

        complaints_layout.addWidget(QLabel("Анамнез жизни:"))

        anamnez_layout = QVBoxLayout()
        anamnez_layout.addWidget(QLabel("туберкулез, кожвен-заболевания:"))
        self.tb_entry = QLineEdit("отрицает")
        anamnez_layout.addWidget(self.tb_entry)

        anamnez_layout.addWidget(QLabel("аллергологический анамнез:"))
        allergy_layout = QHBoxLayout()
        self.allergy_combo = QComboBox()
        self.allergy_combo.setEditable(True)
        self.allergy_combo.addItems(["не отягощен", "отмечается аллергия на"])
        self.allergy_combo.setCurrentText("не отягощен")
        self.set_combo_width(self.allergy_combo)
        allergy_layout.addWidget(self.allergy_combo)
        self.allergy_text = QLineEdit()
        self.allergy_text.setPlaceholderText("указать аллергены")
        allergy_layout.addWidget(self.allergy_text)
        anamnez_layout.addLayout(allergy_layout)

        anamnez_layout.addWidget(QLabel("страховой анамнез:"))
        self.insurance_combo = QComboBox()
        self.insurance_combo.setEditable(True)
        self.insurance_combo.addItems([
            "Гражданин ПМР (пенсионер, работает)",
            "Гражданин ПМР (пенсионер, не работает)",
            "Гражданин ПМР (не работает)",
            "Гражданин ПМР (работает)",
            "Гражданства ПМР не имеет (платная основа)"
        ])
        self.set_combo_width(self.insurance_combo)
        anamnez_layout.addWidget(self.insurance_combo)

        complaints_layout.addLayout(anamnez_layout)

        button_layout1 = QHBoxLayout()
        back_button1 = QPushButton("Назад")
        back_button1.clicked.connect(self._close_window)
        button_layout1.addWidget(back_button1)

        forward_button1 = QPushButton("Вперед")
        forward_button1.clicked.connect(lambda: self.tab_widget.setCurrentIndex(1))
        button_layout1.addWidget(forward_button1)

        complaints_layout.addLayout(button_layout1)

        self.tab_widget.addTab(complaints_widget, "Жалобы и анамнез")

        # =========================
        # Tab 2: Объективный осмотр
        # =========================
        systems_widget = QWidget()
        systems_layout = QVBoxLayout(systems_widget)

        form = QFormLayout()

        self.general_state_combo = QComboBox()
        self.general_state_combo.setEditable(True)
        self.general_state_combo.addItems(["удовлетворительное", "средней тяжести", "тяжёлое"])
        self.general_state_combo.setCurrentText("удовлетворительное")
        self.general_state_combo.setFixedWidth(220)
        form.addRow("Общее состояние", self.general_state_combo)

        self.lymph_nodes_combo = QComboBox()
        self.lymph_nodes_combo.setEditable(True)
        self.lymph_nodes_combo.addItems(["не увеличены", "увеличены"])
        self.lymph_nodes_combo.setCurrentText("не увеличены")
        self.lymph_nodes_combo.setFixedWidth(220)
        form.addRow("Периферические лимфоузлы", self.lymph_nodes_combo)

        self.skin_state_combo = QComboBox()
        self.skin_state_combo.setEditable(True)
        self.skin_state_combo.addItems(["чистые", "сыпь", "высыпания"])
        self.skin_state_combo.setCurrentText("чистые")
        self.skin_state_combo.setFixedWidth(220)

        self.skin_color_combo = QComboBox()
        self.skin_color_combo.setEditable(True)
        self.skin_color_combo.addItems(["обычной окраски", "бледные", "гиперемированные"])
        self.skin_color_combo.setCurrentText("обычной окраски")
        self.skin_color_combo.setFixedWidth(220)

        skin_layout = QHBoxLayout()
        skin_layout.addWidget(self.skin_state_combo)
        skin_layout.addWidget(self.skin_color_combo)
        form.addRow("Кожные покровы", skin_layout)

        self.breathing_combo = QComboBox()
        self.breathing_combo.setEditable(True)
        self.breathing_combo.addItems(["везикулярное", "жёсткое", "ослабленное"])
        self.breathing_combo.setCurrentText("везикулярное")
        self.breathing_combo.setFixedWidth(220)

        self.breathing_side_combo = QComboBox()
        self.breathing_side_combo.setEditable(True)
        self.breathing_side_combo.addItems(["симметричное", "асимметричное"])
        self.breathing_side_combo.setCurrentText("симметричное")
        self.breathing_side_combo.setFixedWidth(220)

        self.wheeze_combo = QComboBox()
        self.wheeze_combo.setEditable(True)
        self.wheeze_combo.addItems(["нет", "сухие", "влажные"])
        self.wheeze_combo.setCurrentText("нет")
        self.wheeze_combo.setFixedWidth(220)

        breathing_layout = QHBoxLayout()
        breathing_layout.addWidget(self.breathing_combo)
        breathing_layout.addWidget(self.breathing_side_combo)
        form.addRow("Дыхание", breathing_layout)
        form.addRow("Хрипы", self.wheeze_combo)

        self.heart_tones_combo = QComboBox()
        self.heart_tones_combo.setEditable(True)
        self.heart_tones_combo.addItems(["ясные", "приглушённые"])
        self.heart_tones_combo.setCurrentText("ясные")
        self.heart_tones_combo.setFixedWidth(220)

        self.heart_rhythm_combo = QComboBox()
        self.heart_rhythm_combo.setEditable(True)
        self.heart_rhythm_combo.addItems(["ритмичные", "аритмичные"])
        self.heart_rhythm_combo.setCurrentText("ритмичные")
        self.heart_rhythm_combo.setFixedWidth(220)

        self.hr_edit = QLineEdit()
        self.hr_edit.setFixedWidth(60)

        form.addRow("Тоны сердца", self.heart_tones_combo)
        form.addRow("Ритм", self.heart_rhythm_combo)
        form.addRow("ЧСС, уд/мин", self.hr_edit)

        self.pulse_edit = QLineEdit()
        self.pulse_edit.setFixedWidth(60)

        self.pulse_rhythm_combo = QComboBox()
        self.pulse_rhythm_combo.setEditable(True)
        self.pulse_rhythm_combo.addItems(["ритмичный", "аритмичный"])
        self.pulse_rhythm_combo.setCurrentText("ритмичный")
        self.pulse_rhythm_combo.setFixedWidth(160)

        self.pulse_quality_combo = QComboBox()
        self.pulse_quality_combo.setEditable(True)
        self.pulse_quality_combo.addItems(["удовлетворительных свойств", "слабого наполнения"])
        self.pulse_quality_combo.setCurrentText("удовлетворительных свойств")
        self.pulse_quality_combo.setFixedWidth(220)

        pulse_layout = QHBoxLayout()
        pulse_layout.addWidget(self.pulse_edit)
        pulse_layout.addWidget(self.pulse_rhythm_combo)
        pulse_layout.addWidget(self.pulse_quality_combo)
        form.addRow("Пульс, уд/мин", pulse_layout)

        self.bp_sys_edit = QLineEdit()
        self.bp_sys_edit.setFixedWidth(50)
        self.bp_dia_edit = QLineEdit()
        self.bp_dia_edit.setFixedWidth(50)

        bp_layout = QHBoxLayout()
        bp_layout.setSpacing(1)
        bp_layout.addWidget(self.bp_sys_edit)
        bp_layout.addWidget(QLabel("/"))
        bp_layout.addWidget(self.bp_dia_edit)
        bp_layout.addStretch()
        form.addRow("АД, мм рт. ст.", bp_layout)

        self.abdomen_size_combo = QComboBox()
        self.abdomen_size_combo.setEditable(True)
        self.abdomen_size_combo.addItems(["не вздут", "умеренно вздут"])
        self.abdomen_size_combo.setCurrentText("не вздут")
        self.abdomen_size_combo.setFixedWidth(160)

        self.abdomen_state_combo = QComboBox()
        self.abdomen_state_combo.setEditable(True)
        self.abdomen_state_combo.addItems(["мягкий", "напряжённый"])
        self.abdomen_state_combo.setCurrentText("мягкий")
        self.abdomen_state_combo.setFixedWidth(160)

        self.abdomen_pain_combo = QComboBox()
        self.abdomen_pain_combo.setEditable(True)
        self.abdomen_pain_combo.addItems(["безболезненный", "умеренно болезненный"])
        self.abdomen_pain_combo.setCurrentText("безболезненный")
        self.abdomen_pain_combo.setFixedWidth(220)

        abdomen_layout = QHBoxLayout()
        abdomen_layout.addWidget(self.abdomen_size_combo)
        abdomen_layout.addWidget(self.abdomen_state_combo)
        abdomen_layout.addWidget(QLabel("Болезненность"))
        abdomen_layout.addWidget(self.abdomen_pain_combo)
        abdomen_layout.addStretch()
        form.addRow("Живот", abdomen_layout)

        self.liver_position_combo = QComboBox()
        self.liver_position_combo.setEditable(True)
        self.liver_position_combo.addItems(["по краю реберной дуги", "ниже реберной дуги"])
        self.liver_position_combo.setCurrentText("по краю реберной дуги")
        self.liver_position_combo.setFixedWidth(220)

        self.liver_edge_combo = QComboBox()
        self.liver_edge_combo.setEditable(True)
        self.liver_edge_combo.addItems(["край", "заострённый", "закруглённый"])
        self.liver_edge_combo.setCurrentText("край")
        self.liver_edge_combo.setFixedWidth(160)

        self.liver_consistency_combo = QComboBox()
        self.liver_consistency_combo.setEditable(True)
        self.liver_consistency_combo.addItems(["плотно-эластической консистенции", "плотная"])
        self.liver_consistency_combo.setCurrentText("плотно-эластической консистенции")
        self.liver_consistency_combo.setFixedWidth(260)

        self.liver_pain_combo = QComboBox()
        self.liver_pain_combo.setEditable(True)
        self.liver_pain_combo.addItems(["безболезненная", "умеренно болезненная"])
        self.liver_pain_combo.setCurrentText("безболезненная")
        self.liver_pain_combo.setFixedWidth(220)

        liver_layout = QHBoxLayout()
        liver_layout.addWidget(self.liver_position_combo)
        liver_layout.addWidget(self.liver_edge_combo)
        liver_layout.addWidget(self.liver_consistency_combo)
        liver_layout.addWidget(self.liver_pain_combo)
        form.addRow("Печень", liver_layout)

        self.stool_combo = QComboBox()
        self.stool_combo.setEditable(True)
        self.stool_combo.addItems(["регулярный", "задержка стула"])
        self.stool_combo.setCurrentText("регулярный")
        self.stool_combo.setFixedWidth(160)

        self.stool_form_combo = QComboBox()
        self.stool_form_combo.setEditable(True)
        self.stool_form_combo.addItems(["оформленный", "кашицеобразный"])
        self.stool_form_combo.setCurrentText("оформленный")
        self.stool_form_combo.setFixedWidth(180)

        stool_layout = QHBoxLayout()
        stool_layout.addWidget(self.stool_combo)
        stool_layout.addWidget(self.stool_form_combo)
        form.addRow("Стул", stool_layout)

        self.urination_combo = QComboBox()
        self.urination_combo.setEditable(True)
        self.urination_combo.addItems(["свободное", "затруднённое"])
        self.urination_combo.setCurrentText("свободное")
        self.urination_combo.setFixedWidth(160)

        self.urination_pain_combo = QComboBox()
        self.urination_pain_combo.setEditable(True)
        self.urination_pain_combo.addItems(["безболезненное", "болезненное"])
        self.urination_pain_combo.setCurrentText("безболезненное")
        self.urination_pain_combo.setFixedWidth(180)

        urination_layout = QHBoxLayout()
        urination_layout.addWidget(self.urination_combo)
        urination_layout.addWidget(self.urination_pain_combo)
        form.addRow("Мочеиспускание", urination_layout)

        systems_layout.addLayout(form)

        button_layout2 = QHBoxLayout()
        back_button2 = QPushButton("Назад")
        back_button2.clicked.connect(lambda: self.tab_widget.setCurrentIndex(0))
        button_layout2.addWidget(back_button2)

        forward_button2 = QPushButton("Вперед")
        forward_button2.clicked.connect(lambda: self.tab_widget.setCurrentIndex(2))
        button_layout2.addWidget(forward_button2)

        systems_layout.addLayout(button_layout2)
        self.tab_widget.addTab(systems_widget, "Объективный осмотр")

        # =========================
        # Tab 3: Локальный статус
        # =========================
        local_widget = QWidget()
        local_layout = QVBoxLayout(local_widget)
        local_layout.setSpacing(12)
        local_layout.setContentsMargins(20, 20, 20, 20)

        # Vis и ВГД
        vis_vgd_layout = QHBoxLayout()
        vis_vgd_layout.setSpacing(20)

        vis_label = QLabel("Vis")
        vis_label.setStyleSheet("font-weight: bold;")
        vis_vgd_layout.addWidget(vis_label)

        vis_fields = QVBoxLayout()
        vis_fields.setSpacing(4)

        vis_od_row = QHBoxLayout()
        vis_od_row.addWidget(QLabel("OD"))
        self.vis_od = QLineEdit()
        self.vis_od.setFixedWidth(150)
        vis_od_row.addWidget(self.vis_od)
        vis_fields.addLayout(vis_od_row)

        vis_os_row = QHBoxLayout()
        vis_os_row.addWidget(QLabel("OS"))
        self.vis_os = QLineEdit()
        self.vis_os.setFixedWidth(150)
        vis_os_row.addWidget(self.vis_os)
        vis_fields.addLayout(vis_os_row)

        vis_vgd_layout.addLayout(vis_fields)
        vis_vgd_layout.addSpacing(60)

        vgd_label = QLabel("ВГД")
        vgd_label.setStyleSheet("font-weight: bold;")
        vis_vgd_layout.addWidget(vgd_label)

        vgd_fields = QVBoxLayout()
        vgd_fields.setSpacing(4)

        vgd_od_row = QHBoxLayout()
        vgd_od_row.addWidget(QLabel("OD"))
        self.vgd_od = QLineEdit()
        self.vgd_od.setFixedWidth(150)
        vgd_od_row.addWidget(self.vgd_od)
        vgd_fields.addLayout(vgd_od_row)

        vgd_os_row = QHBoxLayout()
        vgd_os_row.addWidget(QLabel("OS"))
        self.vgd_os = QLineEdit()
        self.vgd_os.setFixedWidth(150)
        vgd_os_row.addWidget(self.vgd_os)
        vgd_fields.addLayout(vgd_os_row)

        vis_vgd_layout.addLayout(vgd_fields)
        vis_vgd_layout.addStretch()

        local_layout.addLayout(vis_vgd_layout)
        local_layout.addSpacing(20)

        # ─── Таблица параметров ─────────────────────────────────────────────
        local_grid = QGridLayout()
        local_grid.setHorizontalSpacing(15)
        local_grid.setVerticalSpacing(8)

        local_grid.addWidget(QLabel("<b>Позиция</b>"), 0, 0)
        local_grid.addWidget(QLabel("<b>OD</b>"), 0, 1, Qt.AlignCenter)
        local_grid.addWidget(QLabel("<b>OS</b>"), 0, 2, Qt.AlignCenter)

        # Конфиг: для каждого пункта — набор флагов (множественный выбор).
        # Для "Передняя камера" сделаем отдельные комбобоксы (глубина/влага).

        self.local_status_fields = {}

        row_idx = 1
        for label, options in LOCAL_ROWS_CONFIG.items():
            local_grid.addWidget(QLabel(label), row_idx, 0)

            if options is None and label == "Передняя камера":
                # Разделим на два параметра: глубина и влага.
                # В одной строке показываем "глубина / влага" через два комбобокса.
                def make_ac_widget():
                    w = QWidget()
                    lay = QHBoxLayout(w)
                    lay.setContentsMargins(0, 0, 0, 0)
                    lay.setSpacing(6)

                    depth = QComboBox()
                    depth.setEditable(True)
                    depth.addItems(["", "нормальная", "мелкая", "глубокая"])
                    depth.setFixedWidth(130)

                    fluid = QComboBox()
                    fluid.setEditable(True)
                    fluid.addItems(["", "прозрачная", "мутная", "гифема", "гипопион", "фибрин"])
                    fluid.setFixedWidth(150)

                    lay.addWidget(QLabel("гл."))
                    lay.addWidget(depth)
                    lay.addWidget(QLabel("вл."))
                    lay.addWidget(fluid)
                    lay.addStretch()
                    return w, depth, fluid

                od_w, od_depth, od_fluid = make_ac_widget()
                os_w, os_depth, os_fluid = make_ac_widget()

                local_grid.addWidget(od_w, row_idx, 1)
                local_grid.addWidget(os_w, row_idx, 2)

                # Сохраним как кортеж глубина/влага, чтобы правильно сериализовать
                self.local_status_fields[label] = ((od_depth, od_fluid), (os_depth, os_fluid))
            else:
                od_btn = MultiSelectButton(f"{label} (OD)", options)
                os_btn = MultiSelectButton(f"{label} (OS)", options)
                local_grid.addWidget(od_btn, row_idx, 1)
                local_grid.addWidget(os_btn, row_idx, 2)
                self.local_status_fields[label] = (od_btn, os_btn)

            row_idx += 1

        local_layout.addLayout(local_grid)

        button_layout3 = QHBoxLayout()
        back_button3 = QPushButton("Назад")
        back_button3.clicked.connect(lambda: self.tab_widget.setCurrentIndex(1))
        button_layout3.addWidget(back_button3)

        forward_button3 = QPushButton("Вперед")
        forward_button3.clicked.connect(lambda: self.tab_widget.setCurrentIndex(3))
        button_layout3.addWidget(forward_button3)

        local_layout.addLayout(button_layout3)
        self.tab_widget.addTab(local_widget, "Офтальмологический осмотр")

        # =========================
        # Tab 4: Диагноз
        # =========================
        diag_widget = QWidget()
        diag_layout = QVBoxLayout(diag_widget)

        # Текст с жалобами и т.д.
        comp = self.complaints_text.toPlainText().strip()
        dis_an = self.disease_anamnesis_text.toPlainText().strip()
        basis_text = f"На основании жалоб {comp}, истории заболевания, данных биомикроскопии и офтальмоскопии выставлен"
        diag_layout.addWidget(QLabel(basis_text))

        # Выпадающее меню для типа диагноза
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("диагноз:"))
        self.diag_type_combo = QComboBox()
        self.diag_type_combo.addItems(["клинический", "предварительный"])
        self.diag_type_combo.setCurrentText("клинический")
        type_layout.addWidget(self.diag_type_combo)
        diag_layout.addLayout(type_layout)

        # Секции для выбора диагнозов по глазам
        # OD
        od_layout = QHBoxLayout()
        od_layout.addWidget(QLabel("Диагнозы OD:"))
        self.select_diag_od_button = QPushButton("Выбрать диагнозы OD")
        self.select_diag_od_button.clicked.connect(lambda: self.select_diagnoses("OD"))
        od_layout.addWidget(self.select_diag_od_button)
        diag_layout.addLayout(od_layout)
        self.selected_diag_od_label = QLabel("Выбранные диагнозы OD: (еще не выбраны)")
        diag_layout.addWidget(self.selected_diag_od_label)

        # OS
        os_layout = QHBoxLayout()
        os_layout.addWidget(QLabel("Диагнозы OS:"))
        self.select_diag_os_button = QPushButton("Выбрать диагнозы OS")
        self.select_diag_os_button.clicked.connect(lambda: self.select_diagnoses("OS"))
        os_layout.addWidget(self.select_diag_os_button)
        diag_layout.addLayout(os_layout)
        self.selected_diag_os_label = QLabel("Выбранные диагнозы OS: (еще не выбраны)")
        diag_layout.addWidget(self.selected_diag_os_label)

        # OU
        ou_layout = QHBoxLayout()
        ou_layout.addWidget(QLabel("Диагнозы OU:"))
        self.select_diag_ou_button = QPushButton("Выбрать диагнозы OU")
        self.select_diag_ou_button.clicked.connect(lambda: self.select_diagnoses("OU"))
        ou_layout.addWidget(self.select_diag_ou_button)
        diag_layout.addLayout(ou_layout)
        self.selected_diag_ou_label = QLabel("Выбранные диагнозы OU: (еще не выбраны)")
        diag_layout.addWidget(self.selected_diag_ou_label)

        # Сопутствующие диагнозы
        comorbid_layout = QHBoxLayout()
        comorbid_layout.addWidget(QLabel("Сопутствующие диагнозы:"))
        self.select_comorbid_button = QPushButton("Выбрать сопутствующие диагнозы")
        self.select_comorbid_button.clicked.connect(self.select_comorbid_diagnoses)
        comorbid_layout.addWidget(self.select_comorbid_button)
        diag_layout.addLayout(comorbid_layout)
        self.selected_comorbid_label = QLabel("Выбранные сопутствующие диагнозы: (еще не выбраны)")
        diag_layout.addWidget(self.selected_comorbid_label)

        # Инициализировать
        self.selected_diagnoses_od = []
        self.custom_diagnosis_od = ""
        self.selected_diagnoses_os = []
        self.custom_diagnosis_os = ""
        self.selected_diagnoses_ou = []
        self.custom_diagnosis_ou = ""
        self.selected_comorbid_diagnoses = []
        self.custom_comorbid_diagnosis = ""
        self.update_diag_labels()
        self.update_comorbid_label()

        # Загрузка списков диагнозов из файлов
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        ophthalmic_file = os.path.join(data_dir, 'ophthalmic_diagnoses.json')
        if os.path.exists(ophthalmic_file):
            with open(ophthalmic_file, 'r', encoding='utf-8') as f:
                self.ophthalmic_diagnoses = json.load(f)
        else:
            self.ophthalmic_diagnoses = []

        comorbid_file = os.path.join(data_dir, 'comorbid_diagnoses.json')
        if os.path.exists(comorbid_file):
            with open(comorbid_file, 'r', encoding='utf-8') as f:
                self.comorbid_diagnoses = json.load(f)
        else:
            self.comorbid_diagnoses = []

        button_layout4 = QHBoxLayout()
        back_button4 = QPushButton("Назад")
        back_button4.clicked.connect(lambda: self.tab_widget.setCurrentIndex(2))
        button_layout4.addWidget(back_button4)

        forward_button4 = QPushButton("Вперед")
        forward_button4.clicked.connect(lambda: self.tab_widget.setCurrentIndex(4))
        button_layout4.addWidget(forward_button4)

        diag_layout.addLayout(button_layout4)
        self.tab_widget.addTab(diag_widget, "Диагноз")

        # =========================
        # Tab 5: План обследования
        # =========================
        plan_widget = QWidget()
        plan_layout = QVBoxLayout(plan_widget)

        exam_layout = QHBoxLayout()
        exam_layout.addWidget(QLabel("План обследования:"))
        self.select_exam_button = QPushButton("Выбрать обследования")
        self.select_exam_button.clicked.connect(self.select_examinations)
        exam_layout.addWidget(self.select_exam_button)
        plan_layout.addLayout(exam_layout)
        self.selected_exam_label = QLabel("Выбранные обследования: (еще не выбраны)")
        plan_layout.addWidget(self.selected_exam_label)

        # Инициализировать
        self.selected_examinations = []
        self.update_exam_label()

        button_layout_plan = QHBoxLayout()
        back_button_plan = QPushButton("Назад")
        back_button_plan.clicked.connect(lambda: self.tab_widget.setCurrentIndex(3))
        button_layout_plan.addWidget(back_button_plan)

        forward_button_plan = QPushButton("Вперед")
        forward_button_plan.clicked.connect(lambda: self.tab_widget.setCurrentIndex(5))
        button_layout_plan.addWidget(forward_button_plan)

        plan_layout.addLayout(button_layout_plan)
        self.tab_widget.addTab(plan_widget, "План обследования")

        # =========================
        # Tab 6: Обоснование лечения
        # =========================
        treatment_widget = QWidget()
        treatment_layout = QVBoxLayout(treatment_widget)

        treatment_scroll = QScrollArea()
        treatment_scroll.setWidgetResizable(True)
        treatment_scroll_content = QWidget()
        treatment_scroll_lay = QVBoxLayout(treatment_scroll_content)

        treatment_grid = QGridLayout()
        treatment_grid.setColumnStretch(1, 1)

        self.treatment_basis_fields = {}
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        treatment_json = os.path.join(data_dir, "treatment_basis.json")

        treatment_cats = [
            ("Ангиоретинопротектор", "angio_retino"),
            ("Для улучшения обмена веществ", "metabolism"),
            ("Десенсибилизанты", "desensitization"),
            ("Антибиотики", "antibiotics"),
            ("Ангиопротекторы", "angioprotectors"),
            ("Миотики", "myotics"),
            ("Биостимуляторы", "biostimulators"),
            ("Сосудорасширяющие", "vasodilators"),
            ("Анальгетики", "analgesics"),
            ("Антиагреганты", "antiaggregants"),
            ("Противогрибковые", "antifungal"),
            ("Мидриатики", "mydriatics"),
            ("К-сберегающий", "k_sparing"),
            ("Анестетики", "anesthetics"),
        ]

        # Загружаем все данные один раз
        all_tr_data = {}
        if os.path.exists(treatment_json):
            try:
                with open(treatment_json, "r", encoding="utf-8") as f:
                    all_tr_data = json.load(f)
            except:
                pass

        for i, (label_text, category) in enumerate(treatment_cats):
            lbl = QLabel(label_text + ":")
            opts = all_tr_data.get(category, [])
            btn = EnhancedMultiSelectButton(label_text, opts, file_path=treatment_json, category=category)
            treatment_grid.addWidget(lbl, i, 0)
            treatment_grid.addWidget(btn, i, 1)
            self.treatment_basis_fields[category] = btn

        treatment_scroll_lay.addLayout(treatment_grid)
        treatment_scroll_lay.addStretch()
        treatment_scroll.setWidget(treatment_scroll_content)
        treatment_layout.addWidget(treatment_scroll)

        button_layout_tr = QHBoxLayout()
        back_btn_tr = QPushButton("Назад")
        back_btn_tr.clicked.connect(lambda: self.tab_widget.setCurrentIndex(4))
        button_layout_tr.addWidget(back_btn_tr)

        save_button_tr = QPushButton("Сохранить")
        save_button_tr.clicked.connect(self.save_primary_exam)
        button_layout_tr.addWidget(save_button_tr)

        treatment_layout.addLayout(button_layout_tr)
        self.tab_widget.addTab(treatment_widget, "Обоснование лечения")

        # Список обследований
        self.examinations = [
            "Общий анализ мочи",
            "Биохимический анализ крови",
            "Флюорография",
            "Маммография",
            "ЭКГ",
            "УЗИ органов брюшной полости",
            "Рентген грудной клетки",
            "Анализ кала",
        ]

    def select_comorbid_diagnoses(self):
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        comorbid_file = os.path.join(data_dir, 'comorbid_diagnoses.json')
        dialog = EnhancedMultiSelectDialog(self, "Выбор сопутствующих диагнозов", self.comorbid_diagnoses, self.selected_comorbid_diagnoses, self.custom_comorbid_diagnosis, comorbid_file)
        if dialog.exec() == QDialog.Accepted:
            self.selected_comorbid_diagnoses, self.custom_comorbid_diagnosis = dialog.get_result()
            self.update_comorbid_label()

    def select_diagnoses(self, eye):
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        ophthalmic_file = os.path.join(data_dir, 'ophthalmic_diagnoses.json')
        if eye == "OD":
            selected = self.selected_diagnoses_od
            custom = self.custom_diagnosis_od
        elif eye == "OS":
            selected = self.selected_diagnoses_os
            custom = self.custom_diagnosis_os
        elif eye == "OU":
            selected = self.selected_diagnoses_ou
            custom = self.custom_diagnosis_ou
        else:
            return

        dialog = EnhancedMultiSelectDialog(self, f"Выбор диагнозов {eye}", self.ophthalmic_diagnoses, selected, custom, ophthalmic_file)
        if dialog.exec() == QDialog.Accepted:
            new_selected, new_custom = dialog.get_result()
            if eye == "OD":
                self.selected_diagnoses_od = new_selected
                self.custom_diagnosis_od = new_custom
            elif eye == "OS":
                self.selected_diagnoses_os = new_selected
                self.custom_diagnosis_os = new_custom
            elif eye == "OU":
                self.selected_diagnoses_ou = new_selected
                self.custom_diagnosis_ou = new_custom
            self.update_diag_labels()

    def select_examinations(self):
        dialog = EnhancedMultiSelectDialog(self, "Выбор обследований", self.examinations, self.selected_examinations, "", None)
        if dialog.exec() == QDialog.Accepted:
            self.selected_examinations, _ = dialog.get_result()
            self.update_exam_label()



    def update_diag_labels(self):
        # OD
        selected_text_od = ", ".join(self.selected_diagnoses_od) if self.selected_diagnoses_od else "(еще не выбраны)"
        if self.custom_diagnosis_od:
            selected_text_od += f"; {self.custom_diagnosis_od}" if selected_text_od != "(еще не выбраны)" else self.custom_diagnosis_od
        self.selected_diag_od_label.setText(f"Выбранные диагнозы OD: {selected_text_od}")

        # OS
        selected_text_os = ", ".join(self.selected_diagnoses_os) if self.selected_diagnoses_os else "(еще не выбраны)"
        if self.custom_diagnosis_os:
            selected_text_os += f"; {self.custom_diagnosis_os}" if selected_text_os != "(еще не выбраны)" else self.custom_diagnosis_os
        self.selected_diag_os_label.setText(f"Выбранные диагнозы OS: {selected_text_os}")

        # OU
        selected_text_ou = ", ".join(self.selected_diagnoses_ou) if self.selected_diagnoses_ou else "(еще не выбраны)"
        if self.custom_diagnosis_ou:
            selected_text_ou += f"; {self.custom_diagnosis_ou}" if selected_text_ou != "(еще не выбраны)" else self.custom_diagnosis_ou
        self.selected_diag_ou_label.setText(f"Выбранные диагнозы OU: {selected_text_ou}")

    def update_comorbid_label(self):
        selected_text = ", ".join(self.selected_comorbid_diagnoses) if self.selected_comorbid_diagnoses else "(еще не выбраны)"
        if self.custom_comorbid_diagnosis:
            selected_text += f"; {self.custom_comorbid_diagnosis}" if selected_text != "(еще не выбраны)" else self.custom_comorbid_diagnosis
        self.selected_comorbid_label.setText(f"Выбранные сопутствующие диагнозы: {selected_text}")

    def update_exam_label(self):
        selected_text = ", ".join(self.selected_examinations) if self.selected_examinations else "(еще не выбраны)"
        self.selected_exam_label.setText(f"Выбранные обследования: {selected_text}")

    def insert_tag(self, text_edit, tag):
        current = text_edit.toPlainText().strip()
        text_edit.setPlainText((current + " " + tag).strip() if current else tag)

    def _get_widget_text(self, w) -> str:
        if w is None:
            return ""
        if isinstance(w, QLineEdit):
            return w.text().strip()
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        # Supports both MultiSelectButton and EnhancedMultiSelectButton
        if hasattr(w, "get_text"):
            return w.get_text().strip()
        return ""

    def set_combo_width(self, combo):
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(combo.font())
        max_width = 0
        for i in range(combo.count()):
            text = combo.itemText(i)
            width = fm.horizontalAdvance(text)
            if width > max_width:
                max_width = width
        combo.setFixedWidth(max_width + 30)  # extra for arrow and padding

    def save_primary_exam(self):
        comp = self.complaints_text.toPlainText().strip()
        dis_an = self.disease_anamnesis_text.toPlainText().strip()
        tb_val = self.tb_entry.text().strip()
        if self.allergy_combo.currentText() == "не отягощен":
            allergy_val = "не отягощен"
        else:
            allergy_text = self.allergy_text.text().strip()
            allergy_val = f"отмечается аллергия на {allergy_text}" if allergy_text else "отмечается аллергия"
        insurance_val = self.insurance_combo.currentText()

        systems_lines = []
        systems_lines.append(f"Общее состояние: {self.general_state_combo.currentText()}")
        if self.lymph_nodes_combo.currentText() == "увеличены":
            systems_lines.append("Периферические лимфоузлы: увеличены")
        systems_lines.append(
            f"Кожные покровы: {self.skin_state_combo.currentText()}, {self.skin_color_combo.currentText()}"
        )
        systems_lines.append(
            f"Дыхание: {self.breathing_combo.currentText()}, {self.breathing_side_combo.currentText()}, "
            f"хрипы: {self.wheeze_combo.currentText()}"
        )
        systems_lines.append(
            f"Сердечно-сосудистая система: тоны сердца {self.heart_tones_combo.currentText()}, "
            f"ритм {self.heart_rhythm_combo.currentText()}, "
            f"ЧСС {self.hr_edit.text().strip() or '-'} уд/мин, "
            f"пульс {self.pulse_edit.text().strip() or '-'} уд/мин, "
            f"{self.pulse_rhythm_combo.currentText()}, "
            f"{self.pulse_quality_combo.currentText()}"
        )
        if self.bp_sys_edit.text().strip() or self.bp_dia_edit.text().strip():
            systems_lines.append(
                f"АД {self.bp_sys_edit.text().strip() or '-'} / {self.bp_dia_edit.text().strip() or '-'} мм рт. ст."
            )
        systems_lines.append(
            f"Пищеварительная система: живот {self.abdomen_size_combo.currentText()}, "
            f"{self.abdomen_state_combo.currentText()}, "
            f"{self.abdomen_pain_combo.currentText()}, "
            f"печень {self.liver_position_combo.currentText()}, "
            f"{self.liver_edge_combo.currentText()}, "
            f"{self.liver_consistency_combo.currentText()}, "
            f"{self.liver_pain_combo.currentText()}"
        )
        systems_lines.append(f"Стул: {self.stool_combo.currentText()}, {self.stool_form_combo.currentText()}")
        systems_lines.append(f"Мочеиспускание: {self.urination_combo.currentText()}, {self.urination_pain_combo.currentText()}")

        local_lines = []
        for label, widgets in self.local_status_fields.items():
            # Особый случай: Передняя камера — (depth, fluid)
            if label == "Передняя камера":
                (od_depth, od_fluid), (os_depth, os_fluid) = widgets
                od_text = f"глубина {self._get_widget_text(od_depth)}, влага {self._get_widget_text(od_fluid)}"
                os_text = f"глубина {self._get_widget_text(os_depth)}, влага {self._get_widget_text(os_fluid)}"
            else:
                od_widget, os_widget = widgets
                od_text = self._get_widget_text(od_widget)
                os_text = self._get_widget_text(os_widget)

            if od_text or os_text:
                local_lines.append((label, od_text, os_text))

        # Собрать диагноз
        diag_type = self.diag_type_combo.currentText()
        diag_parts = []

        # OD
        od_diag = []
        if self.selected_diagnoses_od:
            od_diag.extend(self.selected_diagnoses_od)
        if self.custom_diagnosis_od:
            od_diag.append(self.custom_diagnosis_od)
        if od_diag:
            diag_parts.append(f"{', '.join(od_diag)} OD")

        # OS
        os_diag = []
        if self.selected_diagnoses_os:
            os_diag.extend(self.selected_diagnoses_os)
        if self.custom_diagnosis_os:
            os_diag.append(self.custom_diagnosis_os)
        if os_diag:
            diag_parts.append(f"{', '.join(os_diag)} OS")

        # OU
        ou_diag = []
        if self.selected_diagnoses_ou:
            ou_diag.extend(self.selected_diagnoses_ou)
        if self.custom_diagnosis_ou:
            ou_diag.append(self.custom_diagnosis_ou)
        if ou_diag:
            diag_parts.append(f"{', '.join(ou_diag)} OU")

        diag_text = ". ".join(diag_parts) if diag_parts else "(не указан)"

        # Сопутствующие диагнозы
        comorbid_parts = []
        if self.selected_comorbid_diagnoses:
            comorbid_parts.extend(self.selected_comorbid_diagnoses)
        if self.custom_comorbid_diagnosis:
            comorbid_parts.append(self.custom_comorbid_diagnosis)
        comorbid_text = ", ".join(comorbid_parts) if comorbid_parts else ""

        full_diag = f"На основании жалоб {comp}, истории заболевания, данных биомикроскопии и офтальмоскопии выставлен <u>{diag_type} диагноз</u>: <b>{diag_text}</b>"
        if comorbid_text:
            full_diag += f"<br><b>Сопутствующий диагноз:</b> {comorbid_text}"
        diag = full_diag

        # Собрать Обоснование лечения
        # Обоснование лечения
        treatment_labels_map = {
            "angio_retino": "Ангиоретинопротектор",
            "metabolism": "Для улучшения обмена веществ",
            "desensitization": "Десенсибилизанты",
            "antibiotics": "Антибиотики",
            "angioprotectors": "Ангиопротекторы",
            "myotics": "Миотики",
            "biostimulators": "Биостимуляторы",
            "vasodilators": "Сосудорасширяющие",
            "analgesics": "Анальгетики",
            "antiaggregants": "Антиагреганты",
            "antifungal": "Противогрибковые",
            "mydriatics": "Мидриатики",
            "k_sparing": "К-сберегающий",
            "anesthetics": "Анестетики",
        }
        treatment_basis_lines = []
        for key, btn in self.treatment_basis_fields.items():
            val = btn.get_text().strip()
            if val:
                label = treatment_labels_map.get(key, key)
                treatment_basis_lines.append(f"<b>{label}:</b> {val}")

        # Собрать план обследования
        treat = ", ".join(self.selected_examinations) if self.selected_examinations else ""

        vis_od_text = self.vis_od.text().strip()
        vis_os_text = self.vis_os.text().strip()
        vgd_od_text = self.vgd_od.text().strip()
        vgd_os_text = self.vgd_os.text().strip()

        # HTML
        html_lines = ["""
                <style>
                    body{
                        margin:0;
                        font-family: Arial, sans-serif;
                        font-size: 10.5pt;
                        line-height: 1.05;
                    }

                    .section{ margin:0 0 1mm 0; }
                    .title{ font-weight:700; }

                    /* УБРАТЬ лишние интервалы между блоками div */
                    div{ margin:0; padding:0; }

                    /* Таблицы максимально плотные */
                    table{ margin:0.6mm 0; border-collapse:collapse; }
                    th, td{
                        padding: 1px 3px;
                        vertical-align: top;
                        line-height: 1.05;
                    }

                    /* Визуально плотнее заголовки */
                    b{ line-height:1.05; }
                </style>
                """]

        if comp:
            html_lines.append(
        f'<div class="section"><span class="title">Жалобы:</span> {comp}</div>'
    )
        if dis_an:
            html_lines.append(f'<div class="section"><span class="title">История настоящего заболевания:</span> {dis_an}</div>')

        html_lines.append("<b>Анамнез жизни:</b><br>")
        html_lines.append(f"- Туберкулез, кожвен-заболевания: {tb_val}<br>")
        html_lines.append(f"- Аллергологический анамнез: {allergy_val}<br>")
        html_lines.append(f"- Страховой анамнез: {insurance_val}")

        html_lines.append('<div class="section"><span class="title">Объективный осмотр:</span></div>')

        for line in systems_lines:
            html_lines.append(f'<div>{line}</div>')
        html_lines.append("<br>")

        html_lines.append("<b>Офтальмологический осмотр:</b><br>")

        # Vis и ВГД в виде дробей
        if vis_od_text or vis_os_text or vgd_od_text or vgd_os_text:
            html_lines.append('<table border="0" cellpadding="0" cellspacing="0"><tr>')

            if vis_od_text or vis_os_text:
                vis_html = f'''
                <td style="text-align:center; padding:0 5px; vertical-align:middle;"><b>Vis</b></td>
                <td style="text-align:center; padding:0 5px; vertical-align:middle;">
                    <table border="0" cellpadding="2" cellspacing="0">
                        <tr><td style="text-align:center; border-bottom:1px solid black;">OD</td></tr>
                        <tr><td style="text-align:center;">OS</td></tr>
                    </table>
                </td>
                <td style="text-align:center; padding:0 5px; vertical-align:middle;">=</td>
                <td style="text-align:center; padding:0 5px; vertical-align:middle;">
                    <table border="0" cellpadding="2" cellspacing="0">
                        <tr><td style="text-align:center; border-bottom:1px solid black;">{vis_od_text or '—'}</td></tr>
                        <tr><td style="text-align:center;">{vis_os_text or '—'}</td></tr>
                    </table>
                </td>
                <td style="padding:0 20px;"></td>
                '''
                html_lines.append(vis_html)

            if vgd_od_text or vgd_os_text:
                vgd_html = f'''
                <td style="text-align:center; padding:0 5px; vertical-align:middle;"><b>ВГД</b></td>
                <td style="text-align:center; padding:0 5px; vertical-align:middle;">
                    <table border="0" cellpadding="2" cellspacing="0">
                        <tr><td style="text-align:center; border-bottom:1px solid black;">OD</td></tr>
                        <tr><td style="text-align:center;">OS</td></tr>
                    </table>
                </td>
                <td style="text-align:center; padding:0 5px; vertical-align:middle;">=</td>
                <td style="text-align:center; padding:0 5px; vertical-align:middle;">
                    <table border="0" cellpadding="2" cellspacing="0">
                        <tr><td style="text-align:center; border-bottom:1px solid black;">{vgd_od_text or '—'}</td></tr>
                        <tr><td style="text-align:center;">{vgd_os_text or '—'}</td></tr>
                    </table>
                </td>
                <td style="text-align:left; padding:0 5px; vertical-align:middle;">мм.рт.ст.</td>
                '''
                html_lines.append(vgd_html)

            html_lines.append("</tr></table><br>")

        # Таблица офтальмологического статуса
        if local_lines:
            html_lines.append('<table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;">')
            html_lines.append('<tr><th style="text-align:left;">Позиция</th><th style="text-align:left;">OD</th><th style="text-align:left;">OS</th></tr>')
            for label, od_text, os_text in local_lines:
                html_lines.append(f"<tr><td><b>{label}</b></td><td>{od_text}</td><td>{os_text}</td></tr>")
            html_lines.append("</table><br>")

        if full_diag:
            html_lines.append(f"{full_diag}<br>")

        # План обследования
        if self.selected_examinations:
            html_lines.append('<div class="section"><span class="title">План обследования:</span></div>')
            html_lines.append(f'<div>{", ".join(self.selected_examinations)}</div>')
            html_lines.append("<br>")

        # Обоснование лечения
        if treatment_basis_lines:
            html_lines.append('<div class="section"><span class="title">Обоснование лечения:</span></div>')
            for line in treatment_basis_lines:
                html_lines.append(f'<div>{line}</div>')
            html_lines.append("<br>")

        html_record = "".join(html_lines)

        # Сохраняем в зависимости от типа
        diag_adm = ""
        diag_clin = ""
        if diag_type == "предварительный":
            diag_adm = diag_text
        else:
            diag_clin = diag_text

        self.db.add_history(self.patient_id, "primary_exam", html_record, 
                            diagnosis=diag_text, 
                            treatment=treat, 
                            diag_admission=diag_adm,
                            diag_clinical=diag_clin, 
                            diag_comorbid=comorbid_text,
                            history_id=self.history_id)
        QMessageBox.information(self, "Успешно", "Первичный осмотр сохранён.")
        self.load_records_list(self.records_table, self.patient_id)
        self._close_window()

    def _close_window(self):
        # Если мы в навигационном стеке, возвращаемся назад
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, '_nav_back'):
                parent._nav_back()
                return
            parent = parent.parent()

        self.accept()

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    # Заглушка DB для теста
    class _DB:
        def add_history(self, *args, **kwargs):
            print("Saved record:", args, kwargs)

    window = PrimaryExamWindow(None, _DB(), 1, None, lambda *args: None)
    window.show()
    sys.exit(app.exec())