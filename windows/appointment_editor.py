from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QLineEdit,
    QComboBox,
    QDateEdit,
    QMessageBox,
    QInputDialog,
)
from PySide6.QtCore import QDate, QLocale


class AppointmentEditorDialog(QDialog):
    def __init__(self, parent=None, templates=None, initial=None, done_callback=None, category=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование назначения")
        self.setModal(True)
        # optional callback to call with result when OK pressed
        self.done_callback = done_callback

        self.templates = templates[:] if templates else [
            "стол 15", "стол 9", "стол 14", "режим общий", "режим постельный"
        ]

        self.resize(700, 420)

        main = QVBoxLayout(self)

        grid = QGridLayout()

        # Left: appointment list
        grid.addWidget(QLabel("Лист назначений"), 0, 0)
        self.app_list = QListWidget()
        grid.addWidget(self.app_list, 1, 0, 6, 1)

        # Middle: add/remove buttons
        mid_layout = QVBoxLayout()
        add_btn = QPushButton("<<")
        add_btn.clicked.connect(self.add_from_templates)
        mid_layout.addWidget(add_btn)
        remove_btn = QPushButton("×")
        remove_btn.clicked.connect(self.remove_selected)
        mid_layout.addWidget(remove_btn)
        mid_layout.addStretch()
        grid.addLayout(mid_layout, 1, 1, 6, 1)

        # Right: templates
        grid.addWidget(QLabel("Шаблоны"), 0, 2)
        self.template_list = QListWidget()
        self.template_list.addItems(self.templates)
        grid.addWidget(self.template_list, 1, 2, 5, 1)

        tbtn_layout = QVBoxLayout()
        t_add = QPushButton("+")
        t_add.clicked.connect(self.add_template)
        tbtn_layout.addWidget(t_add)
        t_edit = QPushButton("✎")
        t_edit.clicked.connect(self.edit_template)
        tbtn_layout.addWidget(t_edit)
        t_del = QPushButton("–")
        t_del.clicked.connect(self.delete_template)
        tbtn_layout.addWidget(t_del)
        tbtn_layout.addStretch()
        grid.addLayout(tbtn_layout, 1, 3, 5, 1)

        # Up/down for left list
        ud_layout = QVBoxLayout()
        up_btn = QPushButton("↑")
        up_btn.clicked.connect(self.move_up)
        ud_layout.addWidget(up_btn)
        down_btn = QPushButton("↓")
        down_btn.clicked.connect(self.move_down)
        ud_layout.addWidget(down_btn)
        grid.addLayout(ud_layout, 1, 4, 2, 1)

        main.addLayout(grid)

        # Method and frequency
        form_layout = QGridLayout()
        form_layout.addWidget(QLabel("Способ применения"), 0, 0)
        self.method_combo = QComboBox()
        self.method_combo.setEditable(True)
        self.method_combo.addItems(["в/в", "в/м", "перорально", "местно"]) 
        form_layout.addWidget(self.method_combo, 0, 1)
        self.method_edit_btn = QPushButton("изменить...")
        self.method_edit_btn.clicked.connect(self.edit_method_items)
        form_layout.addWidget(self.method_edit_btn, 0, 2)

        form_layout.addWidget(QLabel("Кратность"), 1, 0)
        self.freq_combo = QComboBox()
        self.freq_combo.setEditable(True)
        self.freq_combo.addItems(["1 раз в сутки", "2 раза в сутки", "3 раза в сутки"]) 
        form_layout.addWidget(self.freq_combo, 1, 1)
        self.freq_edit_btn = QPushButton("изменить...")
        self.freq_edit_btn.clicked.connect(self.edit_freq_items)
        form_layout.addWidget(self.freq_edit_btn, 1, 2)

        # Dates
        form_layout.addWidget(QLabel("Дата назначения"), 2, 0)
        self.date_assign = QDateEdit(QDate.currentDate())
        self.date_assign.setCalendarPopup(True)
        self.date_assign.setLocale(QLocale(QLocale.Russian))
        form_layout.addWidget(self.date_assign, 2, 1)

        form_layout.addWidget(QLabel("Дата отмены"), 2, 2)
        self.date_cancel = QDateEdit()
        self.date_cancel.setCalendarPopup(True)
        self.date_cancel.setDate(QDate.currentDate())
        self.date_cancel.setLocale(QLocale(QLocale.Russian))
        form_layout.addWidget(self.date_cancel, 2, 3)

        main.addLayout(form_layout)

        # Bottom buttons
        bottom = QHBoxLayout()
        bottom.addStretch()
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        bottom.addWidget(ok)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        main.addLayout(bottom)

        # store category and load initial data
        self.category = category
        if initial:
            self.load_initial(initial)
        # hide method/frequency controls for certain template categories
        try:
            if category in ("exam", "lfk", "stol"):
                self.method_combo.hide()
                self.method_edit_btn.hide()
                self.freq_combo.hide()
                self.freq_edit_btn.hide()
        except Exception:
            pass

    def add_from_templates(self):
        item = self.template_list.currentItem()
        if item:
            self.app_list.addItem(item.text())

    def remove_selected(self):
        row = self.app_list.currentRow()
        if row >= 0:
            self.app_list.takeItem(row)

    def add_template(self):
        text, ok = QInputDialog.getText(self, "Добавить шаблон", "Название:")
        if ok and text:
            self.template_list.addItem(text)

    def edit_template(self):
        row = self.template_list.currentRow()
        if row < 0:
            return
        item = self.template_list.item(row)
        text, ok = QInputDialog.getText(self, "Редактировать шаблон", "Название:", text=item.text())
        if ok:
            item.setText(text)

    def delete_template(self):
        row = self.template_list.currentRow()
        if row >= 0:
            self.template_list.takeItem(row)

    def move_up(self):
        row = self.app_list.currentRow()
        if row > 0:
            item = self.app_list.takeItem(row)
            self.app_list.insertItem(row - 1, item)
            self.app_list.setCurrentRow(row - 1)

    def move_down(self):
        row = self.app_list.currentRow()
        if 0 <= row < self.app_list.count() - 1:
            item = self.app_list.takeItem(row)
            self.app_list.insertItem(row + 1, item)
            self.app_list.setCurrentRow(row + 1)

    def edit_method_items(self):
        text, ok = QInputDialog.getText(self, "Изменить способы", "Добавить новый способ:")
        if ok and text:
            self.method_combo.addItem(text)

    def edit_freq_items(self):
        text, ok = QInputDialog.getText(self, "Изменить кратности", "Добавить новую кратность:")
        if ok and text:
            self.freq_combo.addItem(text)

    def load_initial(self, data: dict):
        # data can include: name, method, freq, date_assign, date_cancel, templates
        if data.get("templates"):
            self.template_list.clear()
            self.template_list.addItems(data.get("templates"))
        if data.get("name"):
            self.app_list.addItem(data.get("name"))
        if data.get("method"):
            self.method_combo.setCurrentText(data.get("method"))
        if data.get("freq"):
            self.freq_combo.setCurrentText(data.get("freq"))
        if data.get("date_assign"):
            self.date_assign.setDate(QDate.fromString(data.get("date_assign"), "dd.MM.yyyy"))
        if data.get("date_cancel"):
            self.date_cancel.setDate(QDate.fromString(data.get("date_cancel"), "dd.MM.yyyy"))

    def get_result(self) -> dict:
        # Return dict representing the appointment. Include all items from app_list.
        items = [self.app_list.item(i).text() for i in range(self.app_list.count())]
        method = self.method_combo.currentText()
        freq = self.freq_combo.currentText()
        # If category indicates templates like exams/stol/lfk, ignore method/freq
        if getattr(self, 'category', None) in ("exam", "lfk", "stol"):
            method = ""
            freq = ""
        return {
            "items": items,
            "name": items[0] if items else "",
            "method": method,
            "freq": freq,
            "date_assign": self.date_assign.date().toString("dd.MM.yyyy"),
            "date_cancel": self.date_cancel.date().toString("dd.MM.yyyy") if self.date_cancel.date().isValid() else "",
            "templates": [self.template_list.item(i).text() for i in range(self.template_list.count())],
        }

    def accept(self):
        # gather result
        res = self.get_result()
        # call done callback if provided
        try:
            if hasattr(self, 'done_callback') and callable(self.done_callback):
                self.done_callback(res)
        except Exception:
            pass
        # if parent has navigation, pop this page; else fall back to default accept
        parent = self.parent()
        if parent is not None and hasattr(parent, '_nav_back'):
            try:
                parent._nav_back()
                return
            except Exception:
                pass
        super().accept()

    def reject(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, '_nav_back'):
            try:
                parent._nav_back()
                return
            except Exception:
                pass
        super().reject()
