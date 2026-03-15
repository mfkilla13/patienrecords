import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPalette, QColor
from gui import MedicalApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Включаем High DPI поддержку
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # Используем Fusion стиль для единообразия на всех платформах
    app.setStyle("Fusion")
    
    # Явно задаем СВЕТЛУЮ палитру
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(240, 240, 240))
    palette.setColor(QPalette.WindowText, Qt.black)
    palette.setColor(QPalette.Base, Qt.white)
    palette.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
    palette.setColor(QPalette.ToolTipBase, Qt.white)
    palette.setColor(QPalette.ToolTipText, Qt.black)
    palette.setColor(QPalette.Text, Qt.black)
    palette.setColor(QPalette.Button, QColor(240, 240, 240))
    palette.setColor(QPalette.ButtonText, Qt.black)
    palette.setColor(QPalette.BrightText, Qt.white)
    palette.setColor(QPalette.Link, QColor(0, 0, 255))
    palette.setColor(QPalette.Highlight, QColor(76, 163, 224))
    palette.setColor(QPalette.HighlightedText, Qt.white)
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 120))
    app.setPalette(palette)
    
    # Явно задаем шрифт для всего приложения
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    # Глобальный stylesheet для унификации
    app.setStyleSheet("""
        QWidget {
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 9pt;
            color: black;
            background-color: #f0f0f0;
        }
        QTableWidget {
            font-size: 9pt;
            font-family: "Segoe UI", Arial, sans-serif;
            background-color: white;
            color: black;
        }
        QTableWidget::item {
            background-color: white;
            color: black;
            padding: 2px;
        }
        QTextEdit {
            font-size: 9pt;
            font-family: "Segoe UI", Arial, sans-serif;
            background-color: white;
            color: black;
        }
        QLineEdit {
            background-color: white;
            color: black;
            border: 1px solid #cccccc;
            padding: 2px;
        }
        QPushButton {
            background-color: #e0e0e0;
            color: black;
            border: 1px solid #999999;
            padding: 3px;
            border-radius: 2px;
        }
        QPushButton:hover {
            background-color: #d0d0d0;
        }
        QPushButton:pressed {
            background-color: #c0c0c0;
        }
    """)
    
    window = MedicalApp()
    window.show()
    sys.exit(app.exec())