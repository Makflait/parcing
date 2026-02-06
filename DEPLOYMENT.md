# Blogger Analytics - Инструкция по деплою

## Оглавление
1. [Архитектура](#архитектура)
2. [Локальная разработка](#локальная-разработка)
3. [Production деплой](#production-деплой)
4. [API документация](#api-документация)
5. [Администрирование](#администрирование)

---

## Архитектура

### Компоненты системы:
- **Flask Web App** - основное приложение (API + UI)
- **PostgreSQL** - база данных (production)
- **SQLite** - база данных (локальная разработка)
- **Redis** - очереди и кэширование
- **Celery Worker** - фоновые задачи (парсинг)
- **Celery Beat** - планировщик задач
- **Nginx** - reverse proxy (production)

### Структура проекта:
```
parcing/
├── web/
│   ├── app.py           # Flask приложение
│   ├── database.py      # SQLAlchemy модели
│   ├── auth.py          # JWT авторизация
│   ├── admin.py         # Админ API
│   └── static/          # Frontend файлы
│       ├── index.html   # Главная страница
│       ├── login.html   # Страница входа
│       └── admin.html   # Админ-панель
├── data/                # SQLite база (локально)
├── logs/                # Логи
├── config.json          # Конфигурация блогеров
├── docker-compose.yml   # Docker конфигурация
├── requirements.txt     # Python зависимости
├── init_admin.py        # Создание первого админа
└── .env.example         # Пример переменных окружения
```

---

## Локальная разработка

### Требования:
- Python 3.10+
- Git

### 1. Клонирование и настройка

```bash
# Клонировать репозиторий
git clone <repository_url>
cd parcing

# Переключиться на ветку разработки
git checkout dev

# Создать виртуальное окружение
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt
```

### 2. Инициализация базы данных (SQLite)

```bash
python init_admin.py
```

Или с указанием своих данных:
```bash
python init_admin.py your@email.com your_password "Admin Name"
```

**Результат:**
- Создается папка `data/` с файлом `blogger_analytics.db`
- Создается первый администратор

### 3. Запуск сервера

```bash
cd web
python app.py
```

Сервер будет доступен: http://localhost:5000

### 4. Вход в систему

- Откройте http://localhost:5000/login.html
- Введите данные администратора:
  - Email: `admin@blogger-analytics.local` (или ваш)
  - Пароль: `admin2026!` (или ваш)

---

## Production деплой

### Требования:
- Docker 20+
- Docker Compose 2+
- 2GB RAM минимум
- 10GB дискового пространства

### 1. Подготовка сервера

```bash
# Клонировать репозиторий
git clone <repository_url>
cd parcing

# Переключиться на production ветку
git checkout production
```

### 2. Настройка окружения

```bash
# Создать .env файл
cp .env.example .env

# Отредактировать .env
nano .env
```

**Обязательные переменные:**
```env
DB_PASSWORD=<сильный_пароль_для_БД>
SECRET_KEY=<случайная_строка_минимум_32_символа>
FLASK_ENV=production
```

Генерация секретного ключа:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Запуск Docker

```bash
# Сборка и запуск
docker-compose up -d

# Проверка статуса
docker-compose ps

# Просмотр логов
docker-compose logs -f web
```

### 4. Инициализация базы данных

```bash
# Войти в контейнер
docker-compose exec web bash

# Создать таблицы и первого админа
python init_admin.py admin@yourdomain.com secure_password "Admin"

# Выйти
exit
```

### 5. Настройка Nginx (опционально)

Для production с HTTPS добавьте профиль nginx:

```bash
docker-compose --profile production up -d
```

Не забудьте настроить SSL сертификаты в `nginx.conf`.

### 6. Мониторинг

```bash
# Статус контейнеров
docker-compose ps

# Логи приложения
docker-compose logs -f web

# Логи воркера
docker-compose logs -f worker

# Статус Celery
docker-compose exec worker celery -A web.celery_app:celery_app status
```

---

## API документация

### Аутентификация

Все защищенные эндпоинты требуют JWT токен:
```
Authorization: Bearer <access_token>
```

#### POST /api/auth/login
Вход в систему.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "success": true,
  "user": {
    "id": 1,
    "email": "user@example.com",
    "name": "User Name",
    "role": "admin"
  },
  "access_token": "eyJ...",
  "refresh_token": "eyJ..."
}
```

#### POST /api/auth/refresh
Обновление access токена.

**Headers:** `Authorization: Bearer <refresh_token>`

**Response:**
```json
{
  "access_token": "eyJ..."
}
```

#### GET /api/auth/me
Информация о текущем пользователе.

**Response:**
```json
{
  "user": {...},
  "bloggers_count": 5
}
```

#### POST /api/auth/logout
Выход из системы.

### Основное API

#### GET /api/stats
Общая статистика по всем блогерам.

#### GET /api/bloggers
Список блогеров из конфигурации.

#### GET /api/blogger/{name}
Детальная статистика по блогеру.

#### POST /api/bloggers
Добавить нового блогера.

**Request:**
```json
{
  "name": "Blogger Name",
  "youtube": "https://youtube.com/@channel",
  "tiktok": "https://tiktok.com/@user",
  "instagram": "https://instagram.com/user"
}
```

#### DELETE /api/bloggers/{name}
Удалить блогера.

#### POST /api/parser/start
Запустить парсинг.

#### GET /api/parser/status
Статус парсинга.

### Админ API

Требуется роль `admin`.

#### GET /api/admin/stats
Статистика системы (пользователи, планы, блогеры).

#### GET /api/admin/users
Список всех пользователей.

#### POST /api/admin/users
Создать нового пользователя.

**Request:**
```json
{
  "email": "newuser@example.com",
  "password": "password123",
  "name": "New User",
  "role": "user"
}
```

#### PUT /api/admin/users/{id}
Обновить пользователя.

#### DELETE /api/admin/users/{id}
Удалить пользователя.

---

## Администрирование

### Доступ к админ-панели

1. Войдите в систему с правами администратора
2. Перейдите по адресу `/admin.html`
3. Или нажмите "Админ-панель" в боковом меню главной страницы

### Управление пользователями

#### Создание пользователя
1. Нажмите "+ Добавить пользователя"
2. Заполните форму:
   - Email (обязательно)
   - Пароль (мин. 6 символов)
   - Имя
   - Роль: `user` или `admin`
3. Нажмите "Создать"

#### Деактивация пользователя
Деактивированный пользователь не сможет войти в систему.

### Git ветки

| Ветка | Назначение |
|-------|------------|
| `main` | Стабильная версия |
| `dev` | Локальная разработка |
| `production` | Production серверы |

### Резервное копирование

#### Docker (PostgreSQL)
```bash
# Бэкап
docker-compose exec db pg_dump -U blogger_user blogger_analytics > backup.sql

# Восстановление
cat backup.sql | docker-compose exec -T db psql -U blogger_user blogger_analytics
```

#### Локальная разработка (SQLite)
```bash
cp data/blogger_analytics.db data/blogger_analytics.db.backup
```

### Логи

- Flask: `logs/app.log`
- Celery: `docker-compose logs worker`
- PostgreSQL: `docker-compose logs db`

---

## Поддержка

При возникновении проблем:
1. Проверьте логи: `docker-compose logs -f`
2. Перезапустите сервисы: `docker-compose restart`
3. Обратитесь к разработчику с описанием ошибки и логами
