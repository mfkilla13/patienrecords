# 🚀 Сборка MedQT для Windows и Linux

## Что вы получили

✅ **Linux:** готовый исполняемый файл `dist/MedQT` (69 МБ)  
✅ **Windows:** автоматическая сборка через GitHub Actions

---

## 📥 Как собрать .exe (Windows)

### Вариант 1️⃣: GitHub Actions (РЕКОМЕНДУЕТСЯ - автоматически)

1. **Загрузите проект на GitHub:**
   ```bash
   git push origin main
   ```

2. **Перейдите в Actions:**
   - GitHub → Ваш репозиторий → вкладка **Actions**
   
3. **Запустите workflow:**
   - Найдите "Build Windows EXE"
   - Нажмите **Run workflow**
   - Подождите 3-5 минут
   - Скачайте .exe из **Artifacts**

✅ **Плюсы:**
- Абсолютно бесплатно
- Собирается на реальном Windows
- Автоматический процесс
- Работает на любой машине

❌ **Минусы:**
- Требует GitHub账户
- Нужно немного подождать

---

### Вариант 2️⃣: На своей Windows машине

Если у вас есть Windows:

```bash
# 1. Установите Python 3.12+
# 2. Клонируйте проект
git clone https://github.com/вашблюд/patienrecords.git
cd med_qt

# 3. Создайте виртуальное окружение
python -m venv venv
venv\Scripts\activate

# 4. Установите зависимости
pip install -r requirements.txt
pip install pyinstaller

# 5. Соберите
python build.py
```

Файл будет в `dist/MedQT.exe` (~200-250 МБ)

---

### Вариант 3️⃣: Docker на Linux (для опытных)

```bash
# Собрать Docker образ с Windows внутри
docker build -f Dockerfile.windows -t medqt-builder .

# Запустить сборку
docker run -v $(pwd)/dist:/app/dist medqt-builder
```

---

## 📦 Файлы для распространения

### Linux:
```
dist/MedQT          ← 69 МБ, один файл, готов к использованию
```

Просто отправьте пользователям этот файл, больше ничего не нужно.

### Windows:
```
dist/MedQT.exe      ← ~200-250 МБ, один файл, готов к использованию
```

Просто отправьте пользователям этот .exe, больше ничего не нужно.

---

## 🔧 Автоматическое создание Release

Если вы хотите автоматически создавать Release с .exe:

```bash
# 1. Создайте тег
git tag v1.0.0
git push origin v1.0.0

# 2. Workflow автоматически создаст Release с MedQT.exe
```

---

## 📋 Файлы конфигурации

- **requirements.txt** — все зависимости проекта
- **build.py** — скрипт сборки для локальной машины
- **.github/workflows/build-windows-exe.yml** — автоматическая сборка на GitHub

---

## ❓ FAQ

**Q: Можно ли собрать .exe на Linux?**  
A: Технически да (cross-compilation), но очень сложно и часто не работает с PySide6.

**Q: Какой размер .exe будет?**  
A: Обычно 200-250 МБ для Windows (больше чем Linux 69 МБ, потому что Windows требует больше) 

**Q: Нужно ли устанавливать Python на целевой машине?**  
A: **Нет!** .exe полностью standalone.

**Q: Как часто обновляется .exe?**  
A: После каждого `git push` автоматически собирается новая версия.

---

## 🚀 Быстрый старт (GitHub Actions)

```bash
# 1. Залитель в GitHub
git add .
git commit -m "Add Windows build"
git push origin main

# 2. Зайдите на GitHub → Actions → Run "Build Windows EXE"
# 3. Подождите 5 минут
# 4. Скачайте MedQT.exe из Artifacts ✅
```
