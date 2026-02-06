# Blogger Analytics Platform

Платформа аналитики блогеров YouTube, TikTok, Instagram.
Multi-tenant, JWT-авторизация, PostgreSQL, Docker.

---

## Стек

| Компонент | Технология |
|-----------|-----------|
| Backend | Flask 3.x + SQLAlchemy |
| Database | PostgreSQL 15 |
| Cache/Queue | Redis 7 |
| Workers | Celery (фоновый парсинг) |
| Parsers | yt-dlp (YT/TT), instaloader (IG) |
| Auth | JWT (flask-jwt-extended) |
| Proxy | Nginx (production) |
| Frontend | SPA (vanilla JS + Chart.js) |

---

## Структура проекта

```
├── web/
│   ├── app.py              # Flask API + роуты
│   ├── database.py          # SQLAlchemy модели
│   ├── auth.py              # JWT авторизация
│   ├── admin.py             # Админ-панель API
│   ├── parser_service.py    # Оркестрация парсеров
│   ├── scheduler.py         # APScheduler (авто-парсинг 03:00)
│   ├── celery_app.py        # Celery конфигурация
│   └── static/
│       ├── index.html       # Главный дашборд (SPA)
│       ├── login.html       # Страница логина
│       └── admin.html       # Админ-панель
├── parsers/
│   ├── youtube_parser.py    # YouTube (yt-dlp)
│   ├── tiktok_parser.py     # TikTok (yt-dlp)
│   └── instagram_parser.py  # Instagram (instaloader + yt-dlp fallback)
├── trends/
│   ├── watcher.py           # Мониторинг трендов
│   ├── discovery.py         # Автообнаружение
│   ├── spy_service.py       # Шпион конкурентов
│   └── db.py                # Trend DB
├── docker-compose.yml       # 4 сервиса: db, redis, web, worker
├── Dockerfile               # Python 3.11 + gunicorn
├── nginx.conf               # Reverse proxy (production profile)
├── init.sql                 # Схема PostgreSQL (справочно)
├── requirements.txt         # Python зависимости
└── .env.example             # Шаблон переменных окружения
```

---

## Деплой (Docker)

### 1. Клонировать и настроить

```bash
git clone <repo-url> && cd blogger-analytics
cp .env.example .env
```

### 2. Заполнить `.env`

```env
# Обязательные
DB_PASSWORD=ваш_сложный_пароль
SECRET_KEY=случайная_строка_минимум_32_символа

# Админ (создаётся автоматически при старте)
ADMIN_EMAIL=admin@company.com
ADMIN_PASSWORD=надёжный_пароль

# Instagram авторизация (для корректных просмотров)
# Без логина Instagram отдаёт views=0 для фото-постов
INSTAGRAM_USERNAME=сервисный_аккаунт
INSTAGRAM_PASSWORD=пароль_аккаунта

# Лимит видео на платформу (по умолчанию 50)
MAX_VIDEOS_PER_PLATFORM=50
```

> **Instagram аккаунт**: используйте отдельный сервисный аккаунт.
> Instagram блокирует за частые запросы с основного.
> Если включена 2FA -- отключите или используйте app password.

### 3. Запуск

```bash
# Стандартный (web + db + redis + worker)
docker compose up -d

# Проверка
docker compose ps
curl http://localhost:5000/health
```

### 4. Проверка логов

```bash
docker logs blogger_web --tail 50
docker logs blogger_worker --tail 50
```

---

## Docker-сервисы

| Сервис | Контейнер | Порт | Описание |
|--------|-----------|------|----------|
| db | blogger_db | 5432 | PostgreSQL 15 |
| redis | blogger_redis | 6379 | Redis 7 (кэш + очередь Celery) |
| web | blogger_web | 5000 | Flask API + фронтенд (gunicorn, 4 воркера) |
| worker | blogger_worker | -- | Celery (фоновый парсинг + beat расписание) |
| nginx | blogger_nginx | 80/443 | Reverse proxy (только `--profile production`) |

### Запуск с Nginx (production)

```bash
docker compose --profile production up -d
```

---

## API

### Авторизация
| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/auth/login` | Логин: `{email, password}` -> `{access_token, refresh_token}` |
| POST | `/api/auth/register` | Регистрация |
| GET | `/api/auth/me` | Текущий пользователь |
| POST | `/api/auth/refresh` | Обновить токен |

### Блогеры (JWT required)
| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/bloggers` | Список блогеров + агрегированная статистика |
| POST | `/api/bloggers` | Добавить блогера (запускает авто-парсинг) |
| PUT | `/api/bloggers/:id` | Обновить ссылки блогера |
| DELETE | `/api/bloggers/:id` | Удалить (soft delete) |
| POST | `/api/bloggers/:id/parse` | Перепарсить конкретного блогера |

### Статистика (JWT required)
| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/api/stats` | Сводка: видео, просмотры, лайки по платформам |
| GET | `/api/blogger/:id` | Детали блогера + все его видео |

### Парсер
| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/parser/start` | Запуск парсинга ВСЕХ блогеров |
| GET | `/api/parser/status` | Статус (running, progress, errors) |

### Тренды
| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/spy/discover` | Обнаружить новые трендовые видео |
| POST | `/api/spy/analyze` | Анализ трендов |
| GET | `/api/spy/report` | Полный отчёт (discover + analyze) |

### Системные
| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/health` | Healthcheck (статус, режим, БД) |
| GET | `/` | Дашборд (SPA) |
| GET | `/admin.html` | Админ-панель |

---

## Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|:------------:|----------|
| `DB_PASSWORD` | `secure_password_change_me` | Пароль PostgreSQL |
| `SECRET_KEY` | `dev-secret-key` | Ключ JWT (менять обязательно!) |
| `ADMIN_EMAIL` | `admin@blogger-analytics.local` | Email админа (создаётся при старте) |
| `ADMIN_PASSWORD` | `admin2026!` | Пароль админа |
| `ADMIN_NAME` | `Admin` | Имя админа |
| `REQUIRE_AUTH` | `true` | Требовать JWT для API |
| `ENABLE_SCHEDULER` | `false` | APScheduler (авто-парсинг в 03:00) |
| `MAX_VIDEOS_PER_PLATFORM` | `50` | Макс. видео на платформу при парсинге |
| `INSTAGRAM_USERNAME` | -- | Логин Instagram для views |
| `INSTAGRAM_PASSWORD` | -- | Пароль Instagram |
| `FLASK_ENV` | `production` | Режим Flask |

---

## База данных

### Модели

- **User** -- пользователи (email, role: `admin` / `user`)
- **Blogger** -- блогеры (привязан к user через `user_id`)
- **VideoHistory** -- видео + метрики (views, likes, comments, shares, engagement_rate)
- **TrendVideo** -- видео для мониторинга трендов
- **TrendSnapshot** -- снимки метрик во времени
- **DetectedTrend** -- обнаруженные тренды

Схема создаётся автоматически (`db.create_all()` при старте).

### Бэкап / восстановление

```bash
# Бэкап
docker exec blogger_db pg_dump -U blogger_user blogger_analytics > backup.sql

# Восстановление
docker exec -i blogger_db psql -U blogger_user blogger_analytics < backup.sql
```

---

## Парсеры

### YouTube + TikTok
Используют **yt-dlp**. Работают без авторизации.
- Получают список видео с канала/профиля
- Извлекают: title, views, likes, comments, shares
- YouTube: параллельная загрузка деталей (5 потоков)
- Дедупликация по URL (upsert)

### Instagram
Использует **instaloader** (основной) + yt-dlp (fallback).

| Режим | Views фото | Views видео/Reels | Лайки | Комменты |
|-------|:----------:|:-----------------:|:-----:|:--------:|
| Без авторизации | 0 | да | да | да |
| С авторизацией | 0* | да | да | да |

*Instagram не отдаёт views для фото-постов через API. Views доступны только для видео/Reels.

**С авторизацией** (`INSTAGRAM_USERNAME` + `INSTAGRAM_PASSWORD`):
- Сессия сохраняется в `/app/data/ig_session_*` (переживает рестарты)
- Меньше rate-limit ошибок
- Доступ к закрытым профилям (если подписан)

---

## Обновление

```bash
git pull origin main
docker compose up -d --build web worker
```

PostgreSQL и Redis данные сохраняются в Docker volumes.

---

## Troubleshooting

### Контейнер не стартует
```bash
docker logs blogger_web --tail 100
```

### Instagram не парсит / views = 0
1. Проверить `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` в `.env`
2. `docker compose up -d --build web worker`
3. `docker logs blogger_web | grep Instagram`
4. Если "требуется 2FA" -- отключить 2FA или использовать app password

### PostgreSQL не поднимается
```bash
docker compose down
docker volume rm parcing_postgres_data  # УДАЛИТ ВСЕ ДАННЫЕ
docker compose up -d
```

### Мало видео
Увеличить `MAX_VIDEOS_PER_PLATFORM` в `.env` (по умолчанию 50).

### Порт 5000 занят (Windows)
```bash
netstat -ano | findstr :5000
taskkill /PID <pid> /F
```

---

## Лицензия

MIT
