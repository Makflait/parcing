# Пошаговая инструкция по установке

## Шаг 1: Проверка Python

Убедитесь, что у вас установлен Python 3.8 или выше:

```bash
python --version
# или
python3 --version
```

Если Python не установлен:
- **Windows:** Скачайте с [python.org](https://www.python.org/downloads/)
- **Linux:** `sudo apt install python3 python3-pip`
- **MacOS:** `brew install python3`

## Шаг 2: Создание виртуального окружения (рекомендуется)

### Windows

```bash
# Переход в директорию проекта
cd C:\Users\YourName\parcing

# Создание виртуального окружения
python -m venv venv

# Активация
venv\Scripts\activate

# Проверка
python --version
```

### Linux/MacOS

```bash
# Переход в директорию проекта
cd /path/to/parcing

# Создание виртуального окружения
python3 -m venv venv

# Активация
source venv/bin/activate

# Проверка
python --version
```

## Шаг 3: Установка зависимостей

После активации виртуального окружения:

```bash
pip install -r requirements.txt
```

Если возникают ошибки при установке, попробуйте:

```bash
# Обновление pip
python -m pip install --upgrade pip

# Установка зависимостей по одной
pip install gspread
pip install oauth2client
pip install requests
pip install beautifulsoup4
pip install selenium
pip install webdriver-manager
pip install google-api-python-client
pip install python-dateutil
pip install tqdm
pip install lxml
```

## Шаг 4: Настройка Google Sheets API

### 4.1 Создание проекта в Google Cloud

1. Перейдите на [Google Cloud Console](https://console.cloud.google.com/)
2. Войдите с вашим Google аккаунтом
3. Нажмите на выпадающий список проектов (вверху)
4. Нажмите "Новый проект"
5. Введите название: `blogger-stats-parser`
6. Нажмите "Создать"
7. Дождитесь создания проекта и выберите его

### 4.2 Включение Google Sheets API

1. В меню слева выберите "APIs & Services" → "Library"
2. В поиске введите "Google Sheets API"
3. Нажмите на результат
4. Нажмите кнопку "Enable" (Включить)
5. Дождитесь активации (может занять минуту)

### 4.3 Создание Service Account

1. В меню слева выберите "APIs & Services" → "Credentials"
2. Нажмите "+ CREATE CREDENTIALS" → "Service Account"
3. Заполните форму:
   - **Service account name:** `blogger-parser`
   - **Service account ID:** `blogger-parser` (заполнится автоматически)
   - **Service account description:** `Service account for blogger stats parser`
4. Нажмите "CREATE AND CONTINUE"
5. В поле "Role" можно пропустить (нажмите "CONTINUE")
6. Нажмите "DONE"

### 4.4 Создание ключа JSON

1. На странице "Credentials" найдите созданный Service Account
2. Нажмите на него (на email вида `blogger-parser@...`)
3. Перейдите на вкладку "KEYS"
4. Нажмите "ADD KEY" → "Create new key"
5. Выберите формат "JSON"
6. Нажмите "CREATE"
7. Файл автоматически скачается (название вида `blogger-stats-parser-xxxxx.json`)

### 4.5 Сохранение credentials

1. Переименуйте скачанный файл в `credentials.json`
2. Переместите его в корень проекта:
   ```
   parcing/
   ├── credentials.json  ← сюда
   ├── main.py
   └── ...
   ```

### 4.6 Создание Google Sheets таблицы

1. Откройте [Google Sheets](https://sheets.google.com/)
2. Нажмите "+ Создать" или "Blank spreadsheet"
3. Назовите таблицу: `Blogger Stats`
4. **Важный шаг - предоставление доступа:**
   - Откройте файл `credentials.json` в текстовом редакторе
   - Найдите поле `"client_email"`, оно выглядит так:
     ```json
     "client_email": "blogger-parser@blogger-stats-parser-xxxxx.iam.gserviceaccount.com"
     ```
   - Скопируйте этот email
   - В Google Sheets таблице нажмите "Поделиться" (Share) вверху справа
   - Вставьте скопированный email
   - Установите права: "Редактор" (Editor)
   - Снимите галочку "Уведомить пользователей"
   - Нажмите "Поделиться" (Share)

## Шаг 5: Настройка конфигурации блогеров

Откройте файл `config.json` и замените примеры на реальные данные:

```json
{
  "spreadsheet_name": "Blogger Stats",
  "bloggers": [
    {
      "name": "Дудь",
      "youtube": "https://www.youtube.com/@vdud",
      "tiktok": "",
      "instagram": ""
    },
    {
      "name": "Амиран Сардаров",
      "youtube": "https://www.youtube.com/@amiransardarov",
      "tiktok": "https://www.tiktok.com/@amiransardarov",
      "instagram": "https://www.instagram.com/amiransardarov"
    }
  ]
}
```

**Важно:**
- Используйте полные URL
- Если у блогера нет канала на платформе, оставьте пустую строку: `""`
- `spreadsheet_name` должен точно совпадать с названием таблицы в Google Sheets

## Шаг 6: Первый запуск

```bash
# Убедитесь, что виртуальное окружение активировано
# (должно быть (venv) в начале строки)

python main.py
```

### Ожидаемый результат

```
2026-01-23 15:30:45 - blogger_stats - INFO - ============================================================
2026-01-23 15:30:45 - blogger_stats - INFO - Запуск сбора статистики блогеров
2026-01-23 15:30:45 - blogger_stats - INFO - ============================================================
2026-01-23 15:30:45 - blogger_stats - INFO - Загружена конфигурация: 2 блогеров
2026-01-23 15:30:46 - blogger_stats - INFO - Успешно подключено к таблице 'Blogger Stats'
...
```

## Шаг 7: Проверка результатов

1. Откройте вашу Google Sheets таблицу
2. Вы должны увидеть заголовки и данные о роликах
3. Проверьте папку `logs/` - там должен появиться лог-файл

## Возможные проблемы и решения

### Ошибка: "ModuleNotFoundError: No module named 'gspread'"

**Решение:** Убедитесь, что виртуальное окружение активировано и зависимости установлены:
```bash
pip install -r requirements.txt
```

### Ошибка: "FileNotFoundError: credentials.json"

**Решение:** Проверьте, что файл `credentials.json` находится в корне проекта рядом с `main.py`

### Ошибка: "SpreadsheetNotFound"

**Решение:**
1. Проверьте название таблицы в `config.json` - оно должно точно совпадать с Google Sheets
2. Убедитесь, что вы предоставили доступ Service Account (email из `credentials.json`)

### Ошибка: "PermissionDenied" при работе с Google Sheets

**Решение:**
1. Откройте Google Sheets таблицу
2. Нажмите "Поделиться"
3. Добавьте email из файла `credentials.json` (поле `client_email`)
4. Установите права "Редактор"

### Selenium/WebDriver ошибки

**Решение:**
1. Убедитесь, что Chrome установлен
2. При первом запуске WebDriver автоматически скачает нужный драйвер
3. Если не работает, установите вручную:
   ```bash
   pip install --upgrade webdriver-manager
   ```

### Парсер не находит видео

**Решение:**
1. Проверьте правильность URL в `config.json`
2. Попробуйте открыть URL в браузере - доступен ли канал?
3. YouTube/TikTok/Instagram могут блокировать автоматические запросы - попробуйте через VPN

## Шаг 8: Настройка автоматизации

После успешного первого запуска настройте автоматический запуск:

- Смотрите [AUTOMATION.md](AUTOMATION.md) для подробных инструкций

## Деактивация виртуального окружения

Когда закончите работу:

```bash
deactivate
```

## Обновление зависимостей

Если в будущем нужно обновить библиотеки:

```bash
# Активируйте виртуальное окружение
source venv/bin/activate  # Linux/MacOS
# или
venv\Scripts\activate  # Windows

# Обновите все зависимости
pip install --upgrade -r requirements.txt
```

## Резервное копирование

Рекомендуется регулярно делать backup:

```bash
# Скопируйте важные файлы
cp config.json config.json.backup
cp credentials.json credentials.json.backup
cp processed_videos.json processed_videos.json.backup
```

## Переход на другой компьютер

Чтобы перенести проект на другой компьютер:

1. Скопируйте всю папку `parcing/`
2. На новом компьютере установите Python
3. Создайте виртуальное окружение
4. Установите зависимости: `pip install -r requirements.txt`
5. Убедитесь, что файлы `credentials.json` и `config.json` на месте
6. Запустите: `python main.py`

## Дополнительная информация

- Основная документация: [README.md](README.md)
- Настройка автоматизации: [AUTOMATION.md](AUTOMATION.md)
- Часто задаваемые вопросы: [FAQ.md](FAQ.md)

---

**Поддержка:** Если что-то не работает, проверьте логи в папке `logs/`
