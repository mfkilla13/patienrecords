# Инструкция по сборке MedQT для Windows

## Требования:
- Windows 10/11
- Python 3.8+ (рекомендуется 3.11)
- Git

## Шаги сборки:

### 1. Клонирование репозитория
```cmd
git clone https://github.com/mfkilla13/patienrecords.git
cd patienrecords
```

### 2. Создание виртуального окружения
```cmd
python -m venv venv
venv\Scripts\activate
```

### 3. Установка зависимостей
```cmd
pip install -r requirements.txt
pip install pyinstaller
```

### 4. Сборка exe файла
```cmd
python build.py
```

### 5. Результат
После успешной сборки в папке `medqt/` будет:
```
medqt/
└── MedQT/
    ├── MedQT.exe    # Исполняемый файл для Windows
    ├── data/        # Данные приложения
    └── _internal/   # Внутренние файлы PyInstaller
```

## Запуск:
- Скопируйте всю папку `MedQT/` на целевую Windows машину
- Запустите `MedQT.exe`
- Приложение не требует установки Python

## Примечания:
- Сборка занимает 2-3 минуты
- Финальный размер exe около 50-70 МБ (включая все зависимости)
- Приложение полностью standalone