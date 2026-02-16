from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QTextEdit, QMessageBox
from PySide6.QtCore import Qt

class AddRecordWindow(QDialog):
    def __init__(self, parent, db, patient_id, records_table, open_primary_exam_callback, load_records_list_callback, history_id=None):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.history_id = history_id
        self.records_table = records_table
        self.open_primary_exam = open_primary_exam_callback
        self.load_records_list = load_records_list_callback
        self.setWindowTitle("Добавить запись")
        self.setModal(True)
        self.resize(500, 400)
        self.create_widgets()

    def create_widgets(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Выберите тип записи:"))

        button_layout = QVBoxLayout()
        primary_button = QPushButton("Первичный осмотр")
        primary_button.clicked.connect(lambda: self.process_template("Первичный осмотр"))
        button_layout.addWidget(primary_button)

        plan_button = QPushButton("План обследования и лечения")
        plan_button.clicked.connect(lambda: self.process_template("План обследования и лечения"))
        button_layout.addWidget(plan_button)

        diary_button = QPushButton("Дневник")
        diary_button.clicked.connect(lambda: self.process_template("Дневник"))
        button_layout.addWidget(diary_button)

        preop_button = QPushButton("Предоперационный эпикриз")
        preop_button.clicked.connect(lambda: self.process_template("Предоперационный эпикриз"))
        button_layout.addWidget(preop_button)

        protocol_button = QPushButton("Протокол операции")
        protocol_button.clicked.connect(lambda: self.process_template("Протокол операции"))
        button_layout.addWidget(protocol_button)

        extension_button = QPushButton("Продление листка нетрудоспособности")
        extension_button.clicked.connect(lambda: self.process_template("Продление листка нетрудоспособности"))
        button_layout.addWidget(extension_button)

        consilium_button = QPushButton("Консилиум")
        consilium_button.clicked.connect(lambda: self.process_template("Консилиум"))
        button_layout.addWidget(consilium_button)

        discharge_button = QPushButton("Выписной эпикриз")
        discharge_button.clicked.connect(lambda: self.process_template("Выписной эпикриз"))
        button_layout.addWidget(discharge_button)

        postmortem_button = QPushButton("Посмертный эпикриз")
        postmortem_button.clicked.connect(lambda: self.process_template("Посмертный эпикриз"))
        button_layout.addWidget(postmortem_button)

        back_button = QPushButton("Назад")
        back_button.clicked.connect(self.reject)
        button_layout.addWidget(back_button)

        layout.addLayout(button_layout)

    def process_template(self, template):
        # Окно открывается как popup, поэтому после выбора действия просто закрываем его
        if template == "Первичный осмотр":
            self.open_primary_exam(self.patient_id, self.records_table)
        elif template == "Дневник":
            self.open_diary(self.patient_id, self.records_table)
        elif template == "План обследования и лечения":
            self.open_plan(self.patient_id, self.records_table)
        else:
            self.open_add_record_window(template)
        
        self.accept()

    def open_diary(self, patient_id, records_table):
        from .diary import DiaryWindow
        # Ищем главное окно для навигации
        anc = self.parent()
        while anc is not None and not hasattr(anc, 'nav_push'):
            anc = anc.parent()
            
        if anc is not None:
            dlg = DiaryWindow(anc, self.db, patient_id, records_table, self.load_records_list, history_id=self.history_id)
            anc.nav_push(dlg)
        else:
            dlg = DiaryWindow(self.parent(), self.db, patient_id, records_table, self.load_records_list, history_id=self.history_id)
            dlg.show()

    def open_plan(self, patient_id, records_table):
        from .plan_window import PlanPage
        # Ищем главное окно для навигации
        anc = self.parent()
        while anc is not None and not hasattr(anc, 'nav_push'):
            anc = anc.parent()
            
        if anc is not None:
            anc.nav_push(PlanPage(anc, self.db, patient_id, records_table, self.load_records_list, history_id=self.history_id))
        else:
            # fallback: show a simple dialog (minimal UI)
            from PySide6.QtWidgets import QDialog
            dlg = QDialog(self.parent())
            dlg.setWindowTitle("План обследования и лечения")
            dlg.show()

    def open_add_record_window(self, template):
        dlg = AddRecordDialog(self, self.db, self.patient_id, template, self.records_table, self.load_records_list, history_id=self.history_id)
        dlg.exec()

class AddRecordDialog(QDialog):
    def __init__(self, parent, db, patient_id, template, records_table, load_records_list_callback, history_id=None):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.history_id = history_id
        self.template = template
        self.records_table = records_table
        self.load_records_list = load_records_list_callback
        self.setWindowTitle(f"Добавить запись: {template}")
        self.setModal(True)
        self.resize(400, 200)
        self.create_widgets()

    def create_widgets(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Введите запись для {self.template}:"))
        self.record_text = QTextEdit()
        layout.addWidget(self.record_text)

        button_layout = QHBoxLayout()
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.save_record)
        button_layout.addWidget(ok_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    def save_record(self):
        record = self.record_text.toPlainText().strip()
        if record:
            self.db.add_history(self.patient_id, "other", f"{self.template}: {record}", "", "", "", history_id=self.history_id)
            QMessageBox.information(self, "Успех", "Запись добавлена.")
            self.load_records_list(self.records_table, self.patient_id)
            self.accept()