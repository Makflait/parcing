# Blogger Analytics SaaS - System Design

## Архитектура системы

```
┌─────────────────────────────────────────────────────────────────┐
│                         NGINX (Reverse Proxy)                    │
│                    Port 80/443, SSL termination                  │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                      Flask Application                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Auth API   │  │  Blogger API │  │  Trends API  │          │
│  │  /api/auth/* │  │ /api/blogger │  │ /api/trends  │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Admin API   │  │  Stats API   │  │   SSE API    │          │
│  │  /api/admin  │  │  /api/stats  │  │  /api/stream │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────┬───────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼───────┐   ┌─────────▼─────────┐   ┌──────▼──────┐
│  PostgreSQL   │   │      Redis        │   │   Celery    │
│   Database    │   │  Cache + Queue    │   │   Workers   │
│  Port 5432    │   │    Port 6379      │   │             │
└───────────────┘   └───────────────────┘   └─────────────┘
```

## Компоненты

### 1. База данных (PostgreSQL)

**Преимущества над SQLite:**
- Многопользовательский доступ
- ACID транзакции
- Масштабируемость
- Row-level security для multi-tenancy

### 2. Redis

**Использование:**
- Кэширование API ответов
- Session storage
- Очередь задач для Celery
- Rate limiting

### 3. Celery Workers

**Задачи:**
- Фоновый парсинг видео
- Trend Watch spy service (24h мониторинг)
- Scheduled tasks (cron-like)
- Email уведомления

### 4. Multi-tenancy модель

**Подход: Shared Database, Shared Schema с tenant_id**

```sql
-- Каждая таблица содержит user_id для изоляции данных
CREATE TABLE bloggers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name VARCHAR(255),
    ...
);
```

## Модели данных

### Users (Пользователи)
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',  -- user, admin
    plan VARCHAR(50) DEFAULT 'free',  -- free, pro, enterprise
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

### User Limits (Лимиты по плану)
```sql
CREATE TABLE user_limits (
    id SERIAL PRIMARY KEY,
    plan VARCHAR(50) UNIQUE,
    max_bloggers INTEGER,
    max_videos_per_day INTEGER,
    trend_watch_enabled BOOLEAN,
    api_rate_limit INTEGER
);

INSERT INTO user_limits VALUES
('free', 5, 100, FALSE, 100),
('pro', 50, 1000, TRUE, 1000),
('enterprise', -1, -1, TRUE, -1);  -- -1 = unlimited
```

### Bloggers (с tenant isolation)
```sql
CREATE TABLE bloggers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    youtube_url VARCHAR(500),
    tiktok_url VARCHAR(500),
    instagram_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_bloggers_user ON bloggers(user_id);
```

### Video History
```sql
CREATE TABLE video_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    blogger_id INTEGER REFERENCES bloggers(id),
    video_url VARCHAR(500) NOT NULL,
    platform VARCHAR(50),
    title TEXT,
    views BIGINT DEFAULT 0,
    likes BIGINT DEFAULT 0,
    comments BIGINT DEFAULT 0,
    shares BIGINT DEFAULT 0,
    engagement_rate REAL DEFAULT 0,
    viral_score REAL DEFAULT 0,
    recorded_at TIMESTAMP DEFAULT NOW(),
    hashtags JSONB,
    metadata JSONB
);

CREATE INDEX idx_video_user ON video_history(user_id);
CREATE INDEX idx_video_recorded ON video_history(recorded_at);
```

### Trend Watch (Spy Service)
```sql
CREATE TABLE trend_videos (
    id SERIAL PRIMARY KEY,
    video_url VARCHAR(500) UNIQUE,
    platform VARCHAR(50),
    title TEXT,
    uploader VARCHAR(255),
    first_seen TIMESTAMP DEFAULT NOW(),
    last_checked TIMESTAMP,
    initial_views BIGINT,
    current_views BIGINT,
    velocity REAL DEFAULT 0,
    acceleration REAL DEFAULT 0,
    status VARCHAR(50) DEFAULT 'monitoring',  -- monitoring, trending, archived
    hashtags JSONB,
    topics JSONB,
    metadata JSONB
);

CREATE TABLE trend_snapshots (
    id SERIAL PRIMARY KEY,
    video_id INTEGER REFERENCES trend_videos(id),
    views BIGINT,
    likes BIGINT,
    comments BIGINT,
    recorded_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE detected_trends (
    id SERIAL PRIMARY KEY,
    trend_type VARCHAR(50),  -- hashtag, topic, sound, format
    trend_key VARCHAR(255),
    video_count INTEGER,
    avg_velocity REAL,
    score REAL,
    detected_at TIMESTAMP DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'active'
);
```

## API Endpoints

### Auth API
```
POST /api/auth/register    - Регистрация
POST /api/auth/login       - Вход (возвращает JWT)
POST /api/auth/logout      - Выход
POST /api/auth/refresh     - Обновление токена
GET  /api/auth/me          - Текущий пользователь
```

### Blogger API (требует auth)
```
GET    /api/bloggers           - Список блогеров пользователя
POST   /api/bloggers           - Добавить блогера
PUT    /api/bloggers/:id       - Обновить блогера
DELETE /api/bloggers/:id       - Удалить блогера
GET    /api/bloggers/:id/stats - Статистика блогера
```

### Trends API (требует auth + plan)
```
GET  /api/trends/discover     - Запустить discovery
GET  /api/trends/videos       - Мониторящиеся видео
GET  /api/trends/trending     - Обнаруженные тренды
GET  /api/trends/topics       - Трендовые темы
```

### Admin API (требует role=admin)
```
GET    /api/admin/users       - Список пользователей
PUT    /api/admin/users/:id   - Изменить пользователя
DELETE /api/admin/users/:id   - Удалить пользователя
GET    /api/admin/stats       - Общая статистика
GET    /api/admin/logs        - Логи системы
```

## Docker Compose структура

```yaml
services:
  web:        # Flask приложение
  db:         # PostgreSQL
  redis:      # Cache + Queue
  worker:     # Celery worker
  beat:       # Celery beat (scheduler)
  nginx:      # Reverse proxy
```

## Безопасность

1. **JWT токены** с коротким временем жизни (15 min) + refresh tokens
2. **Rate limiting** через Redis
3. **CORS** настройки
4. **SQL injection** защита через SQLAlchemy ORM
5. **Password hashing** через bcrypt
6. **HTTPS** через nginx + Let's Encrypt

## Trend Watch Spy Service

### Логика работы:

1. **Discovery Phase** (каждые 4 часа)
   - Берем случайные видео из YouTube/TikTok рекомендаций
   - Фильтруем по возрасту (< 7 дней)
   - Записываем начальные метрики

2. **Monitoring Phase** (каждые 2 часа)
   - Проверяем все видео в статусе "monitoring"
   - Записываем snapshot метрик
   - Рассчитываем velocity и acceleration

3. **Analysis Phase** (каждые 6 часов)
   - Группируем по хэштегам, звукам, темам
   - Выявляем паттерны роста
   - Детектим emerging trends

4. **Cleanup Phase** (ежедневно)
   - Архивируем видео старше 7 дней
   - Удаляем неинтересные видео (velocity < threshold)
