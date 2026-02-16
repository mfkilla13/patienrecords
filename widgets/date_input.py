from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QCalendarWidget, QDialog, QVBoxLayout
from PySide6.QtCore import QDate, Signal, Qt


class DateInput(QWidget):
    """A small composite widget: a line edit with a calendar button.

    - Click the button to open a popup calendar and pick a date.
    - Text is formatted as DD.MM.YYYY.
    - Exposes `date()` / `setDate()` and `text()` / `setText()` helpers.
    - Emits `dateChanged(QDate)` when a date is picked from the calendar.
    """

    dateChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(self)
        self.button = QPushButton("📅", self)
        self.button.setFixedSize(28, 22)
        self._layout.addWidget(self.edit)
        self._layout.addWidget(self.button)

        self.button.clicked.connect(self._open_calendar)

    def _open_calendar(self):
        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.Popup)
        dlg.setWindowTitle("Календарь")
        dlg_layout = QVBoxLayout(dlg)
        cal = QCalendarWidget(dlg)
        cal.setGridVisible(True)
        # try to preselect a valid date from the text
        current = QDate.fromString(self.edit.text().strip(), "dd.MM.yyyy")
        if current.isValid():
            cal.setSelectedDate(current)
        cal.clicked.connect(lambda d: self._on_date_selected(d, dlg))
        dlg_layout.addWidget(cal)
        dlg.exec()

    def _on_date_selected(self, qdate: QDate, dlg: QDialog):
        txt = qdate.toString("dd.MM.yyyy")
        self.edit.setText(txt)
        try:
            self.dateChanged.emit(qdate)
        except Exception:
            pass
        dlg.accept()

    def setDate(self, qdate: QDate):
        if isinstance(qdate, QDate) and qdate.isValid():
            self.edit.setText(qdate.toString("dd.MM.yyyy"))

    def date(self) -> QDate:
        return QDate.fromString(self.edit.text().strip(), "dd.MM.yyyy")

    def setText(self, text: str):
        self.edit.setText(text)

    def text(self) -> str:
        return self.edit.text()
