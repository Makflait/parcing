# Инструкции по автоматизации парсера

## Windows - Task Scheduler (Планировщик заданий)

### Способ 1: Через GUI

1. Нажмите `Win + R` и введите `taskschd.msc`
2. В правой панели нажмите "Создать простую задачу..."

#### Шаг 1: Общие настройки
- Имя: `Blogger Stats Parser`
- Описание: `Автоматический сбор статистики роликов блогеров`
- Нажмите "Далее"

#### Шаг 2: Триггер
- Выберите "Ежедневно"
- Нажмите "Далее"
- Время начала: `23:00:00` (или любое другое время)
- Повторять каждые: `1` дней
- Нажмите "Далее"

#### Шаг 3: Действие
- Выберите "Запустить программу"
- Нажмите "Далее"
- Программа или сценарий: укажите путь к Python
  - Пример: `C:\Python311\python.exe`
  - Найти путь можно командой: `where python`
- Добавить аргументы: `main.py`
- Рабочая папка: укажите полный путь к проекту
  - Пример: `C:\Users\YourName\parcing`
- Нажмите "Далее"

#### Шаг 4: Завершение
- Установите галочку "Открыть окно свойств после нажатия кнопки Готово"
- Нажмите "Готово"

#### Шаг 5: Дополнительные настройки (в окне свойств)
- Вкладка "Общие":
  - Установите "Выполнять с наивысшими правами"
  - Настроить для: Windows 10
- Вкладка "Условия":
  - Снимите галочку "Запускать задачу только при питании от электросети"
- Вкладка "Параметры":
  - Снимите галочку "Останавливать задачу, выполняемую более чем"
- Нажмите "ОК"

### Способ 2: Через командную строку (PowerShell)

Создайте файл `setup_task.ps1`:

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Python311\python.exe" -Argument "main.py" -WorkingDirectory "C:\Users\YourName\parcing"
$trigger = New-ScheduledTaskTrigger -Daily -At 23:00
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "Blogger Stats Parser" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Автоматический сбор статистики роликов блогеров"
```

Запустите в PowerShell от имени администратора:
```powershell
powershell -ExecutionPolicy Bypass -File setup_task.ps1
```

### Проверка работы задачи

1. Откройте Планировщик заданий
2. Найдите задачу "Blogger Stats Parser"
3. Нажмите правой кнопкой → "Выполнить"
4. Проверьте логи в папке `logs/`

---

## Linux - Cron

### Шаг 1: Определите путь к Python

```bash
which python3
# Пример вывода: /usr/bin/python3
```

### Шаг 2: Определите полный путь к проекту

```bash
cd /path/to/parcing
pwd
# Пример вывода: /home/username/parcing
```

### Шаг 3: Откройте crontab для редактирования

```bash
crontab -e
```

### Шаг 4: Добавьте задание

Добавьте одну из следующих строк:

#### Запуск каждый день в 23:00
```bash
0 23 * * * cd /home/username/parcing && /usr/bin/python3 main.py >> /home/username/parcing/logs/cron.log 2>&1
```

#### Запуск каждый час
```bash
0 * * * * cd /home/username/parcing && /usr/bin/python3 main.py >> /home/username/parcing/logs/cron.log 2>&1
```

#### Запуск каждые 6 часов
```bash
0 */6 * * * cd /home/username/parcing && /usr/bin/python3 main.py >> /home/username/parcing/logs/cron.log 2>&1
```

### Шаг 5: Сохраните и выйдите

- В `nano`: Ctrl+X, затем Y, затем Enter
- В `vim`: ESC, затем `:wq`, затем Enter

### Шаг 6: Проверьте список заданий

```bash
crontab -l
```

### Формат cron

```
* * * * * команда
│ │ │ │ │
│ │ │ │ └─── День недели (0-7, 0 и 7 = воскресенье)
│ │ │ └───── Месяц (1-12)
│ │ └─────── День месяца (1-31)
│ └───────── Час (0-23)
└─────────── Минута (0-59)
```

### Примеры расписаний cron

```bash
# Каждые 30 минут
*/30 * * * * команда

# Каждый день в 9:00 и 18:00
0 9,18 * * * команда

# Каждый понедельник в 8:00
0 8 * * 1 команда

# Первого числа каждого месяца в 00:00
0 0 1 * * команда
```

### Отладка cron

Если cron не работает:

1. Проверьте логи cron:
```bash
grep CRON /var/log/syslog
```

2. Убедитесь, что cron запущен:
```bash
sudo service cron status
```

3. Создайте отдельный скрипт запуска:

Создайте файл `run_parser.sh`:
```bash
#!/bin/bash
cd /home/username/parcing
source venv/bin/activate  # если используете virtual environment
/usr/bin/python3 main.py >> /home/username/parcing/logs/cron.log 2>&1
```

Сделайте его исполняемым:
```bash
chmod +x run_parser.sh
```

Добавьте в cron:
```bash
0 23 * * * /home/username/parcing/run_parser.sh
```

---

## MacOS - Cron или launchd

### Способ 1: Cron (аналогично Linux)

Следуйте инструкциям для Linux выше.

### Способ 2: launchd (рекомендуется для MacOS)

#### Шаг 1: Создайте файл plist

Создайте файл `~/Library/LaunchAgents/com.blogger.stats.parser.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.blogger.stats.parser</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>main.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/YourName/parcing</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>23</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/YourName/parcing/logs/launchd.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/YourName/parcing/logs/launchd_error.log</string>
</dict>
</plist>
```

#### Шаг 2: Загрузите задание

```bash
launchctl load ~/Library/LaunchAgents/com.blogger.stats.parser.plist
```

#### Шаг 3: Проверьте статус

```bash
launchctl list | grep blogger
```

#### Управление заданием

Остановить:
```bash
launchctl unload ~/Library/LaunchAgents/com.blogger.stats.parser.plist
```

Перезапустить:
```bash
launchctl unload ~/Library/LaunchAgents/com.blogger.stats.parser.plist
launchctl load ~/Library/LaunchAgents/com.blogger.stats.parser.plist
```

Запустить вручную:
```bash
launchctl start com.blogger.stats.parser
```

---

## Docker (опционально)

Если хотите запускать в контейнере:

### Создайте Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей для Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

### Создайте docker-compose.yml

```yaml
version: '3.8'

services:
  parser:
    build: .
    volumes:
      - ./credentials.json:/app/credentials.json
      - ./config.json:/app/config.json
      - ./processed_videos.json:/app/processed_videos.json
      - ./logs:/app/logs
    restart: unless-stopped
```

### Запуск

```bash
docker-compose up -d
```

---

## Проверка работы автоматизации

### 1. Проверьте логи

```bash
# Windows
type logs\parser_YYYYMMDD.log

# Linux/MacOS
cat logs/parser_YYYYMMDD.log
```

### 2. Проверьте Google Sheets таблицу

Откройте таблицу и убедитесь, что данные добавляются.

### 3. Проверьте processed_videos.json

Файл должен содержать URL обработанных роликов с датами.

---

## Уведомления о результатах (опционально)

### Email уведомления

Добавьте в конец `main.py`:

```python
import smtplib
from email.mime.text import MIMEText

def send_email_notification(subject, body):
    sender = 'your_email@gmail.com'
    receiver = 'your_email@gmail.com'
    password = 'your_app_password'

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
```

### Telegram уведомления

Установите библиотеку:
```bash
pip install python-telegram-bot
```

Добавьте в `main.py`:
```python
import telegram

def send_telegram_notification(message):
    bot = telegram.Bot(token='YOUR_BOT_TOKEN')
    bot.send_message(chat_id='YOUR_CHAT_ID', text=message)
```

---

## Мониторинг

### Создайте скрипт проверки работы

Создайте `check_parser.py`:

```python
import os
from datetime import datetime, timedelta

# Проверяем когда последний раз обновлялись логи
log_dir = 'logs'
today_log = f'parser_{datetime.now().strftime("%Y%m%d")}.log'
log_path = os.path.join(log_dir, today_log)

if os.path.exists(log_path):
    modified_time = datetime.fromtimestamp(os.path.getmtime(log_path))
    if datetime.now() - modified_time < timedelta(hours=25):
        print("✓ Парсер работает нормально")
    else:
        print("✗ Парсер не запускался больше 24 часов!")
else:
    print("✗ Лог-файл за сегодня не найден!")
```

Запускайте его отдельным заданием в cron/Task Scheduler.

---

## Отладка проблем

### Проблема: Задача не запускается

**Windows:**
1. Проверьте "Журнал планировщика заданий"
2. Убедитесь, что пути абсолютные
3. Проверьте права на папку

**Linux/MacOS:**
1. Проверьте логи: `grep CRON /var/log/syslog`
2. Убедитесь, что cron запущен: `service cron status`
3. Проверьте права на скрипт: `chmod +x run_parser.sh`

### Проблема: Задача запускается, но не работает

1. Запустите вручную и проверьте ошибки
2. Проверьте пути в конфигурации
3. Убедитесь, что `credentials.json` доступен
4. Проверьте логи в `logs/`

---

**Дополнительная информация:** Смотрите основной [README.md](README.md)
