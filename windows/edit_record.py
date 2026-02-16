from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, QMessageBox
from PySide6.QtGui import QTextCursor, QFont
from PySide6.QtCore import Qt

class EditRecordWindow(QDialog):
    def __init__(self, parent, db, patient_id, records_table, load_records_list_callback):
        super().__init__(parent)
        self.db = db
        self.patient_id = patient_id
        self.records_table = records_table
        self.load_records_list = load_records_list_callback
        self.setWindowTitle("Редактировать запись")
        self.setModal(True)
        self.resize(500, 400)
        self.create_window()

    def create_window(self):
        selected = self.records_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите запись для редактирования.")
            self.reject()
            return
        row = selected[0].row()
        
        # Get physical record ID from table data
        record_id = self.records_table.item(row, 0).data(Qt.UserRole)
        h = self.db.get_history_by_id(record_id)
        if not h:
            QMessageBox.warning(self, "Ошибка", "Запись не найдена.")
            self.reject()
            return

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Запись:"))
        
        # Панель форматирования
        format_layout = QHBoxLayout()
        
        bold_button = QPushButton("Ж")
        bold_button.setFont(QFont("Arial", 10, QFont.Bold))
        bold_button.setFixedWidth(40)
        bold_button.clicked.connect(self.toggle_bold)
        format_layout.addWidget(bold_button)
        
        italic_button = QPushButton("К")
        italic_button.setFont(QFont("Arial", 10, QFont.Normal, True))
        italic_button.setFixedWidth(40)
        italic_button.clicked.connect(self.toggle_italic)
        format_layout.addWidget(italic_button)
        
        underline_button = QPushButton("Ч")
        underline_font = QFont("Arial", 10)
        underline_font.setUnderline(True)
        underline_button.setFont(underline_font)
        underline_button.setFixedWidth(40)
        underline_button.clicked.connect(self.toggle_underline)
        format_layout.addWidget(underline_button)
        
        clear_button = QPushButton("Сбросить форматирование")
        clear_button.clicked.connect(self.clear_formatting)
        format_layout.addWidget(clear_button)
        
        format_layout.addStretch()
        layout.addLayout(format_layout)
        
        self.record_text = QTextEdit()
        self.record_text.setHtml(h[4])  # examination
        layout.addWidget(self.record_text)

        save_button = QPushButton("Сохранить")
        save_button.clicked.connect(lambda: self.save_edit_record(h[0], h[3]))  # pass history_id and record_type
        layout.addWidget(save_button)

    def toggle_bold(self):
        cursor = self.record_text.textCursor()
        if cursor.hasSelection():
            fmt = cursor.charFormat()
            if fmt.fontWeight() == QFont.Bold:
                fmt.setFontWeight(QFont.Normal)
            else:
                fmt.setFontWeight(QFont.Bold)
            cursor.mergeCharFormat(fmt)
        else:
            fmt = self.record_text.currentCharFormat()
            if fmt.fontWeight() == QFont.Bold:
                fmt.setFontWeight(QFont.Normal)
            else:
                fmt.setFontWeight(QFont.Bold)
            self.record_text.setCurrentCharFormat(fmt)

    def toggle_italic(self):
        cursor = self.record_text.textCursor()
        if cursor.hasSelection():
            fmt = cursor.charFormat()
            fmt.setFontItalic(not fmt.fontItalic())
            cursor.mergeCharFormat(fmt)
        else:
            fmt = self.record_text.currentCharFormat()
            fmt.setFontItalic(not fmt.fontItalic())
            self.record_text.setCurrentCharFormat(fmt)

    def toggle_underline(self):
        cursor = self.record_text.textCursor()
        if cursor.hasSelection():
            fmt = cursor.charFormat()
            fmt.setFontUnderline(not fmt.fontUnderline())
            cursor.mergeCharFormat(fmt)
        else:
            fmt = self.record_text.currentCharFormat()
            fmt.setFontUnderline(not fmt.fontUnderline())
            self.record_text.setCurrentCharFormat(fmt)

    def clear_formatting(self):
        cursor = self.record_text.textCursor()
        if cursor.hasSelection():
            plain_text = cursor.selectedText()
            cursor.removeSelectedText()
            cursor.insertText(plain_text)
        else:
            # Сбросить форматирование всего текста
            plain_text = self.record_text.toPlainText()
            self.record_text.setPlainText(plain_text)

    def save_edit_record(self, history_id_row, record_type):
        record = self.record_text.toHtml()
        if record:
            # Need to get the existing history_id for this record
            histories = self.db.get_histories(self.patient_id)
            current_h = None
            for h in histories:
                if h[0] == history_id_row:
                    current_h = h
                    break
            
            logical_history_id = current_h[11] if current_h else None
            
            self.db.update_history(history_id_row, record_type, record, "", "", "", logical_history_id=logical_history_id)
            QMessageBox.information(self, "Успех", "Запись обновлена.")
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