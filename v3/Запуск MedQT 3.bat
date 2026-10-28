@echo off
rem MedQT 3 (dev): opens the app in its own window.
cd /d "%~dp0backend"
start "" "%~dp0.venv\Scripts\pythonw.exe" -m medqt3.desktop
