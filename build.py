#!/usr/bin/env python
"""
Build MedQT as standalone executable
Supports both Nuitka (preferred - smaller size) and PyInstaller
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

def check_dependencies():
    """Check if required build tools are installed"""
    print("📋 Проверка зависимостей...")
    
    # PyInstaller проще на всех платформах
    try:
        import PyInstaller
        print("✅ PyInstaller установлена")
        return "pyinstaller"
    except ImportError:
        print("❌ PyInstaller не установлена!")
        print("\nУстановите:")
        print("  pip install pyinstaller")
        return None

def build_with_nuitka():
    """Build with Nuitka (smallest, fastest)"""
    print("\n🔨 Сборка с Nuitka...")
    print("⏱️  Это может занять несколько минут...")
    
    cmd = [
        sys.executable, '-m', 'nuitka',
        '--onefile',
        '--windows-disable-console',
        '--windows-uac-admin',
        '--output-dir=dist',
        '--remove-output',
        '--follow-imports',
        'main.py'
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        exe_path = Path('dist/main.exe')
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\n✅ Сборка успешна!")
            print(f"📦 Файл: {exe_path.absolute()}")
            print(f"💾 Размер: {size_mb:.1f} МБ")
            print(f"\n🚀 Приложение полностью standalone (не требует Python)")
            return True
        else:
            print("❌ Файл .exe не найден")
            return False
    else:
        print("❌ Ошибка сборки Nuitka")
        return False

def build_with_pyinstaller():
    """Build with PyInstaller (fallback)"""
    print("\n🔨 Сборка с PyInstaller...")
    print("⏱️  Это может занять 1-2 минуты...")
    
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--windowed',
        '--name=MedQT',
        '--add-data=data:data',
        '--add-data=widgets:widgets',
        '--add-data=windows:windows',
        '--strip',
        '--optimize=2',
        '--distpath=dist',
        'main.py'
    ]
    
    # Добавьте иконку если она есть
    if Path('icon.ico').exists():
        cmd.insert(cmd.index('--output-dir=dist'), '--icon=icon.ico')
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        # На Windows .exe, на Linux/Mac исполняемый файл
        exe_path = Path('dist/MedQT.exe') if sys.platform == 'win32' else Path('dist/MedQT')
        
        # Если файл не найден по обычному пути
        if not exe_path.exists():
            dist_files = list(Path('dist').glob('*'))
            for f in dist_files:
                if f.is_file() and ('MedQT' in f.name or 'main' in f.name):
                    exe_path = f
                    break
        
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\n✅ Сборка успешна!")
            print(f"📦 Файл: {exe_path.absolute()}")
            print(f"💾 Размер: {size_mb:.1f} МБ")
            return True
        else:
            print("❌ Файл не найден после сборки")
            print(f"Содержимое dist/: {list(Path('dist').iterdir())}")
            return False
    else:
        print("❌ Ошибка сборки PyInstaller")
        return False

def main():
    print("=" * 60)
    print("🏗️  MedQT Build System")
    print("=" * 60)
    
    # Проверка зависимостей
    builder = check_dependencies()
    
    if builder is None:
        print("\n❌ Установите инструмент сборки:")
        print("  pip install nuitka zstandard")
        print("\nДля максимально малого размера файла рекомендуется Nuitka!")
        sys.exit(1)
    
    # Очистка старых сборок
    if Path('build').exists():
        print("\n🧹 Очистка старых файлов сборки...")
        shutil.rmtree('build', ignore_errors=True)
    
    # Сборка
    success = False
    success = build_with_pyinstaller()
    
    # Результат
    print("\n" + "=" * 60)
    if success:
        print("🎉 Сборка завершена успешно!")
        print("\n📌 Что дальше:")
        print("  1. Найдите .exe в папке 'dist/'")
        print("  2. Можете поделиться файлом с другими")
        print("  3. На целевой машине достаточно .exe файла")
        print("  4. Python не требуется!")
    else:
        print("❌ Сборка не удалась. Проверьте логи выше.")
        sys.exit(1)
    print("=" * 60)

if __name__ == '__main__':
    main()
