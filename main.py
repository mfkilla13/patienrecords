import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from gui import MedicalApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setStyleSheet("QWidget { font-size: 10pt; }")
    window = MedicalApp()
    window.show()
    sys.exit(app.exec())