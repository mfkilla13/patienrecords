from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QMessageBox,
    QDateEdit,
    QTimeEdit,
    QComboBox,
    QScrollArea,
    QWidget,
)
from PySide6.QtCore import QDate, QTime

class DiaryWindow(QDialog):
    def __init__(self, parent, db, patient_id, records_table, load_records_list_callback, history_id=None):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.history_id = history_id
        self.records_table = records_table
        self.load_records_list = load_records_list_callback
        self.setWindowTitle("Дневник")
        self.setModal(True)
        self.resize(900, 700)
        self.create_widgets()

    def create_widgets(self):
        main_layout = QVBoxLayout(self)
        
        # Создаём область прокрутки
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QGridLayout(scroll_widget)
        
        row = 0
        
        # Дата и Время
        layout.addWidget(QLabel("Дата"), row, 0)
        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd.MM.yyyy")
        layout.addWidget(self.date_edit, row, 1)
        
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime.currentTime())
        self.time_edit.setDisplayFormat("HH:mm")
        layout.addWidget(self.time_edit, row, 2)
        row += 1
        
        # Общее состояние и Температура тела
        layout.addWidget(QLabel("Общее состояние"), row, 0)
        self.general_state_combo = QComboBox()
        self.general_state_combo.addItems(["удовлетворительное", "средней тяжести", "тяжёлое"])
        layout.addWidget(self.general_state_combo, row, 1, 1, 2)
        
        layout.addWidget(QLabel("Температура тела"), row, 3)
        self.temperature_edit = QLineEdit("36.6")
        layout.addWidget(self.temperature_edit, row, 4)
        row += 1
        
        # Жалобы
        layout.addWidget(QLabel("Жалобы"), row, 0)
        self.complaints_combo = QComboBox()
        self.complaints_combo.addItems(["прежние", "новые", "отсутствуют"])
        layout.addWidget(self.complaints_combo, row, 1)
        
        self.complaints_text = QLineEdit()
        layout.addWidget(self.complaints_text, row, 2, 1, 3)
        row += 1
        
        # Кожные покровы и Видимые слизистые
        layout.addWidget(QLabel("Кожные покровы"), row, 0)
        self.skin_state_combo = QComboBox()
        self.skin_state_combo.addItems(["чистые", "сыпь", "высыпания"])
        layout.addWidget(self.skin_state_combo, row, 1)
        
        self.skin_color_combo = QComboBox()
        self.skin_color_combo.addItems(["обычной окраски", "бледные", "гиперемированные"])
        layout.addWidget(self.skin_color_combo, row, 2)
        
        layout.addWidget(QLabel("Видимые слизистые"), row, 3)
        self.mucosa_combo = QComboBox()
        self.mucosa_combo.addItems(["розовые", "бледные", "гиперемированные"])
        layout.addWidget(self.mucosa_combo, row, 4)
        row += 1
        
        # Дыхание
        layout.addWidget(QLabel("Дыхание"), row, 0)
        self.breathing_combo = QComboBox()
        self.breathing_combo.addItems(["везикулярное", "жёсткое", "ослабленное"])
        layout.addWidget(self.breathing_combo, row, 1)
        
        self.breathing_side_combo = QComboBox()
        self.breathing_side_combo.addItems(["симметричное", "асимметричное"])
        layout.addWidget(self.breathing_side_combo, row, 2)
        
        self.wheeze_combo = QComboBox()
        self.wheeze_combo.addItems(["хрипы нет", "сухие хрипы", "влажные хрипы"])
        layout.addWidget(self.wheeze_combo, row, 3, 1, 2)
        row += 1
        
        # SpO2, Тоны сердца, ЧСС
        layout.addWidget(QLabel("SpO₂"), row, 0)
        self.spo2_edit = QLineEdit()
        layout.addWidget(self.spo2_edit, row, 1)
        layout.addWidget(QLabel("%"), row, 2)
        
        layout.addWidget(QLabel("Тоны сердца"), row, 3)
        self.heart_tones_combo = QComboBox()
        self.heart_tones_combo.addItems(["ясные", "приглушённые"])
        layout.addWidget(self.heart_tones_combo, row, 4)
        row += 1
        
        self.heart_rhythm_combo = QComboBox()
        self.heart_rhythm_combo.addItems(["ритмичные", "аритмичные"])
        layout.addWidget(self.heart_rhythm_combo, row, 0)
        
        layout.addWidget(QLabel("ЧСС"), row, 1)
        self.hr_edit = QLineEdit("76")
        layout.addWidget(self.hr_edit, row, 2)
        layout.addWidget(QLabel("уд. в мин"), row, 3)
        row += 1
        
        # Пульс и АД
        layout.addWidget(QLabel("Пульс"), row, 0)
        self.pulse_edit = QLineEdit("76")
        layout.addWidget(self.pulse_edit, row, 1)
        layout.addWidget(QLabel("уд. в мин"), row, 2)
        
        self.pulse_rhythm_combo = QComboBox()
        self.pulse_rhythm_combo.addItems(["ритмичный", "аритмичный"])
        layout.addWidget(self.pulse_rhythm_combo, row, 3)
        row += 1
        
        self.pulse_quality_combo = QComboBox()
        self.pulse_quality_combo.addItems(["удовлетворительных свойств", "слабого наполнения"])
        layout.addWidget(self.pulse_quality_combo, row, 0, 1, 2)
        
        layout.addWidget(QLabel("АД"), row, 2)
        self.bp_edit = QLineEdit("120/80")
        layout.addWidget(self.bp_edit, row, 3)
        layout.addWidget(QLabel("мм. рт. ст."), row, 4)
        row += 1
        
        # Язык
        layout.addWidget(QLabel("Язык"), row, 0)
        self.tongue_state_combo = QComboBox()
        self.tongue_state_combo.addItems(["чистый", "обложен"])
        layout.addWidget(self.tongue_state_combo, row, 1)
        
        self.tongue_moisture_combo = QComboBox()
        self.tongue_moisture_combo.addItems(["влажный", "сухой"])
        layout.addWidget(self.tongue_moisture_combo, row, 2)
        row += 1
        
        # Живот
        layout.addWidget(QLabel("Живот"), row, 0)
        self.abdomen_size_combo = QComboBox()
        self.abdomen_size_combo.addItems(["не вздут", "умеренно вздут"])
        layout.addWidget(self.abdomen_size_combo, row, 1)
        
        self.abdomen_state_combo = QComboBox()
        self.abdomen_state_combo.addItems(["мягкий", "напряжённый"])
        layout.addWidget(self.abdomen_state_combo, row, 2)
        
        self.abdomen_text = QLineEdit()
        layout.addWidget(self.abdomen_text, row, 3, 1, 2)
        row += 1
        
        self.abdomen_pain_combo = QComboBox()
        self.abdomen_pain_combo.addItems(["безболезненный", "умеренно болезненный"])
        layout.addWidget(self.abdomen_pain_combo, row, 0)
        
        self.abdomen_pain_text = QLineEdit()
        layout.addWidget(self.abdomen_pain_text, row, 1, 1, 4)
        row += 1
        
        # Симптомы раздражения брюшины
        layout.addWidget(QLabel("Симптомы раздражения брюшины"), row, 0)
        self.peritoneal_symptoms_combo = QComboBox()
        self.peritoneal_symptoms_combo.addItems(["нет", "положительные"])
        layout.addWidget(self.peritoneal_symptoms_combo, row, 1)
        
        self.peritoneal_text = QLineEdit()
        layout.addWidget(self.peritoneal_text, row, 2, 1, 3)
        row += 1
        
        # Печень
        layout.addWidget(QLabel("Печень"), row, 0)
        self.liver_position_combo = QComboBox()
        self.liver_position_combo.addItems(["по краю реберной дуги", "ниже реберной дуги"])
        layout.addWidget(self.liver_position_combo, row, 1)
        
        layout.addWidget(QLabel("Край"), row, 2)
        self.liver_consistency_combo = QComboBox()
        self.liver_consistency_combo.addItems(["плотно-эластической консистенции", "плотная"])
        layout.addWidget(self.liver_consistency_combo, row, 3, 1, 2)
        row += 1
        
        self.liver_pain_combo = QComboBox()
        self.liver_pain_combo.addItems(["безболезненная", "умеренно болезненная"])
        layout.addWidget(self.liver_pain_combo, row, 0, 1, 2)
        row += 1
        
        # Симптом Пастернацкого
        layout.addWidget(QLabel("Симптом Пастернацкого"), row, 0)
        self.pasternatsky_combo = QComboBox()
        self.pasternatsky_combo.addItems(["отрицательный с обеих сторон", "положительный справа", "положительный слева"])
        layout.addWidget(self.pasternatsky_combo, row, 1, 1, 4)
        row += 1
        
        # Стул и мочеиспускание
        layout.addWidget(QLabel("Стул"), row, 0)
        self.stool_combo = QComboBox()
        self.stool_combo.addItems(["регулярный", "задержка стула"])
        layout.addWidget(self.stool_combo, row, 1)
        
        self.stool_form_combo = QComboBox()
        self.stool_form_combo.addItems(["оформленный", "кашицеобразный"])
        layout.addWidget(self.stool_form_combo, row, 2)
        
        layout.addWidget(QLabel("Мочеиспускание"), row, 3)
        self.urination_combo = QComboBox()
        self.urination_combo.addItems(["свободное", "затруднённое"])
        layout.addWidget(self.urination_combo, row, 4)
        row += 1
        
        self.urination_pain_combo = QComboBox()
        self.urination_pain_combo.addItems(["безболезненное", "болезненное"])
        layout.addWidget(self.urination_pain_combo, row, 0, 1, 2)
        row += 1
        
        # Отеки
        layout.addWidget(QLabel("Отеки"), row, 0)
        self.edema_combo = QComboBox()
        self.edema_combo.addItems(["нет", "есть"])
        layout.addWidget(self.edema_combo, row, 1)
        
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)
        
        # Кнопка сохранить
        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(self.save_diary)
        main_layout.addWidget(save_button)

    def save_diary(self):
        date = self.date_edit.date().toString("dd.MM.yyyy")
        time = self.time_edit.time().toString("HH:mm")
        
        lines = []
        lines.append(f"Дневник {date} {time}")
        lines.append(f"Общее состояние: {self.general_state_combo.currentText()}")
        lines.append(f"Температура тела: {self.temperature_edit.text()}")
        
        if self.complaints_text.text():
            lines.append(f"Жалобы: {self.complaints_combo.currentText()} - {self.complaints_text.text()}")
        else:
            lines.append(f"Жалобы: {self.complaints_combo.currentText()}")
            
        lines.append(f"Кожные покровы: {self.skin_state_combo.currentText()}, {self.skin_color_combo.currentText()}")
        lines.append(f"Видимые слизистые: {self.mucosa_combo.currentText()}")
        lines.append(f"Дыхание: {self.breathing_combo.currentText()}, {self.breathing_side_combo.currentText()}, {self.wheeze_combo.currentText()}")
        
        if self.spo2_edit.text():
            lines.append(f"SpO₂: {self.spo2_edit.text()}%")
            
        lines.append(f"Тоны сердца: {self.heart_tones_combo.currentText()}, {self.heart_rhythm_combo.currentText()}, ЧСС: {self.hr_edit.text()} уд/мин")
        lines.append(f"Пульс: {self.pulse_edit.text()} уд/мин, {self.pulse_rhythm_combo.currentText()}, {self.pulse_quality_combo.currentText()}, АД: {self.bp_edit.text()} мм рт. ст.")
        lines.append(f"Язык: {self.tongue_state_combo.currentText()}, {self.tongue_moisture_combo.currentText()}")
        
        abdomen_line = f"Живот: {self.abdomen_size_combo.currentText()}, {self.abdomen_state_combo.currentText()}"
        if self.abdomen_text.text():
            abdomen_line += f", {self.abdomen_text.text()}"
        lines.append(abdomen_line)
        
        pain_line = f"{self.abdomen_pain_combo.currentText()}"
        if self.abdomen_pain_text.text():
            pain_line += f", {self.abdomen_pain_text.text()}"
        lines.append(pain_line)
        
        peritoneal_line = f"Симптомы раздражения брюшины: {self.peritoneal_symptoms_combo.currentText()}"
        if self.peritoneal_text.text():
            peritoneal_line += f", {self.peritoneal_text.text()}"
        lines.append(peritoneal_line)
        
        lines.append(f"Печень: {self.liver_position_combo.currentText()}, край {self.liver_consistency_combo.currentText()}, {self.liver_pain_combo.currentText()}")
        lines.append(f"Симптом Пастернацкого: {self.pasternatsky_combo.currentText()}")
        lines.append(f"Стул: {self.stool_combo.currentText()}, {self.stool_form_combo.currentText()}")
        lines.append(f"Мочеиспускание: {self.urination_combo.currentText()}, {self.urination_pain_combo.currentText()}")
        lines.append(f"Отеки: {self.edema_combo.currentText()}")
        
        # Build an HTML-formatted diary record similar to primary exam
        html_lines = []
        # html_lines.append(f"<b>Дневник {date} {time}:</b><br><br>")  # Remove, title from record_type
        # Add each plain-text line as its own HTML line
        for ln in lines:
            # simple escaping: replace '<' and '>' to avoid breaking HTML
            safe = ln.replace('<', '&lt;').replace('>', '&gt;')
            html_lines.append(f"{safe}<br>")
        html_record = ''.join(html_lines)
        self.db.add_history(self.patient_id, "diary", html_record, "", "", "", history_id=self.history_id)
        QMessageBox.information(self, "Успех", "Дневник сохранен.")
        self.load_records_list(self.records_table, self.patient_id)
        parent = self.parent()
        if parent is not None and hasattr(parent, '_nav_back'):
            try:
                parent._nav_back()
                return
            except Exception:
                pass
        try:
            self.accept()
        except Exception:
            pass