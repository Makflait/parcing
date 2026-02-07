# Blogger Analytics Platform

Платформа аналитики блогеров YouTube, TikTok, Instagram.
Multi-tenant, JWT-авторизация, PostgreSQL, Docker.

---

## Быстрый старт (для тех.отдела)

```bash
# 1. Клонировать
git clone <repo-url> && cd parcing

# 2. Создать .env из шаблона
cp .env.example .env

# 3. Заполнить .env (креды получить у руководителя)
nano .env

# 4. Запуск
docker compose up -d

# 5. Проверка
docker compose ps                    # все 4 контейнера UP
curl http://localhost:5000/health    # {"status":"ok"}
```

После старта:
- Дашборд: `http://<server-ip>:5000`
- Логин: email/password из `ADMIN_EMAIL`/`ADMIN_PASSWORD` в `.env`
- Админка: `http://<server-ip>:5000/admin.html`

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
git clone <repo-url> && cd parcing
cp .env.example .env
```

### 2. Заполнить `.env`

Минимально нужно заполнить:

```env
# Обязательные -- придумать свои
DB_PASSWORD=ваш_сложный_пароль
SECRET_KEY=случайная_строка_минимум_32_символа
FLASK_ENV=production

# Админ (создаётся автоматически при первом старте)
ADMIN_EMAIL=admin@company.com
ADMIN_PASSWORD=надёжный_пароль

# Instagram авторизация (креды получить у руководителя)
# Без логина Instagram отдаёт views=0 для видео
INSTAGRAM_USERNAME=
INSTAGRAM_PASSWORD=
INSTAGRAM_TOTP_SECRET=

# Лимит видео на платформу
MAX_VIDEOS_PER_PLATFORM=1000
```

> **Instagram**: креды сервисного аккаунта (логин, пароль, TOTP секрет) передаются отдельно от репозитория. НЕ коммитить в git.
> 2FA проходится автоматически -- парсер сам генерирует TOTP-код при логине.
> Сессия сохраняется в `./data/` и переживает рестарты контейнеров.

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

# Проверить что Instagram авторизовался:
docker logs blogger_web 2>&1 | grep -i instagram
# Ожидаемый вывод: "Instagram: 2FA авторизация @... успешна (TOTP)"
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

### Данные и volumes

- `postgres_data` -- база данных (PostgreSQL)
- `redis_data` -- кэш и очередь
- `./data/` -- сессии Instagram (ig_session_*)
- `./logs/` -- логи приложения

Все данные сохраняются между рестартами.

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
| GET | `/api/stats` | Сводка: видео, просмотры, лайки, шеры по платформам |
| GET | `/api/blogger/:id` | Детали блогера + все видео с метриками |

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
| `FLASK_ENV` | `production` | Режим Flask |
| `ADMIN_EMAIL` | `admin@blogger-analytics.local` | Email админа (создаётся при старте) |
| `ADMIN_PASSWORD` | `admin2026!` | Пароль админа |
| `ADMIN_NAME` | `Admin` | Имя админа |
| `REQUIRE_AUTH` | `true` | Требовать JWT для API |
| `ENABLE_SCHEDULER` | `false` | APScheduler (авто-парсинг в 03:00) |
| `MAX_VIDEOS_PER_PLATFORM` | `1000` | Макс. видео на платформу при парсинге |
| `INSTAGRAM_USERNAME` | -- | Логин Instagram (получить у руководителя) |
| `INSTAGRAM_PASSWORD` | -- | Пароль Instagram |
| `INSTAGRAM_TOTP_SECRET` | -- | TOTP секрет 2FA (base32, без пробелов) |

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
Авторизация + автоматическая 2FA через TOTP (библиотека `pyotp`).

| Режим | Views фото | Views видео/Reels | Лайки | Комменты |
|-------|:----------:|:-----------------:|:-----:|:--------:|
| Без авторизации | 0 | да | да | да |
| С авторизацией | 0* | да | да | да |

*Instagram не отдаёт views для фото-постов через API. Views доступны только для видео/Reels.

**С авторизацией** (`INSTAGRAM_USERNAME` + `INSTAGRAM_PASSWORD` + `INSTAGRAM_TOTP_SECRET`):
- 2FA проходится автоматически (TOTP код генерируется на лету)
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
1. Проверить `INSTAGRAM_USERNAME`, `INSTAGRAM_PASSWORD`, `INSTAGRAM_TOTP_SECRET` в `.env`
2. Пересобрать: `docker compose up -d --build web worker`
3. Проверить лог: `docker logs blogger_web 2>&1 | grep -i instagram`
4. Если "ошибка 2FA" -- проверить `INSTAGRAM_TOTP_SECRET` (base32, без пробелов)
5. Если "BadCredentials" -- проверить логин/пароль

### PostgreSQL не поднимается
```bash
docker compose down
docker volume rm parcing_postgres_data  # УДАЛИТ ВСЕ ДАННЫЕ
docker compose up -d
```

### Мало видео
Увеличить `MAX_VIDEOS_PER_PLATFORM` в `.env` (по умолчанию 1000).

### Порт 5000 занят
```bash
# Linux
lsof -i :5000
kill -9 <pid>

# Windows
netstat -ano | findstr :5000
taskkill /PID <pid> /F
```

---

## Лицензия

MIT
