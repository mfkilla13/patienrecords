from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QTimeEdit, QDialog, QVBoxLayout
from PySide6.QtCore import QTime, Signal, Qt


class TimeInput(QWidget):
    """A small composite widget: a line edit with a time picker button.

    - Click the button to open a popup time picker and pick a time.
    - Text is formatted as HH:MM.
    - Exposes `time()` / `setTime()` and `text()` / `setText()` helpers.
    - Emits `timeChanged(QTime)` when a time is picked.
    """

    timeChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(self)
        self.button = QPushButton("🕒", self)
        self.button.setFixedSize(28, 22)
        self._layout.addWidget(self.edit)
        self._layout.addWidget(self.button)

        self.button.clicked.connect(self._set_current_time)

    def _set_current_time(self):
        current_time = QTime.currentTime()
        self.edit.setText(current_time.toString("HH:mm"))
        try:
            self.timeChanged.emit(current_time)
        except Exception:
            pass

    def time(self):
        return QTime.fromString(self.edit.text().strip(), "HH:mm")

    def setTime(self, qtime: QTime):
        if qtime.isValid():
            self.edit.setText(qtime.toString("HH:mm"))

    def text(self):
        return self.edit.text()

    def setText(self, txt: str):
        self.edit.setText(txt)