"""
SQLite Database for Trend History v1.0
Хранение истории просмотров для расчёта velocity
"""
import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional
import json


class TrendDB:
    """База данных для хранения истории трендов"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(base_dir, 'trends.db')

        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Инициализация таблиц"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Таблица источников для отслеживания
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watch_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                name TEXT,
                account_size INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            )
        ''')

        # Таблица истории видео
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS video_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_url TEXT NOT NULL,
                platform TEXT NOT NULL,
                title TEXT,
                source_url TEXT,
                publish_date TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                shares INTEGER DEFAULT 0,
                hashtags TEXT,
                sound_name TEXT
            )
        ''')

        # Индексы для быстрого поиска
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_video_url ON video_history(video_url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_recorded_at ON video_history(recorded_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON video_history(source_url)')

        # Добавляем новые колонки для метрик (если не существуют)
        try:
            cursor.execute('ALTER TABLE video_history ADD COLUMN viral_score REAL DEFAULT 0')
        except:
            pass
        try:
            cursor.execute('ALTER TABLE video_history ADD COLUMN engagement_rate REAL DEFAULT 0')
        except:
            pass
        try:
            cursor.execute('ALTER TABLE video_history ADD COLUMN potential TEXT DEFAULT ""')
        except:
            pass
        try:
            cursor.execute('ALTER TABLE video_history ADD COLUMN category TEXT DEFAULT ""')
        except:
            pass
        try:
            cursor.execute('ALTER TABLE video_history ADD COLUMN uploader TEXT DEFAULT ""')
        except:
            pass

        # Таблица трендов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detected_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trend_type TEXT,
                trend_key TEXT,
                video_urls TEXT,
                description TEXT,
                score REAL DEFAULT 0
            )
        ''')

        conn.commit()
        conn.close()

    def add_watch_source(self, platform: str, url: str, name: str = None) -> bool:
        """Добавить источник для отслеживания"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO watch_sources (platform, url, name)
                VALUES (?, ?, ?)
            ''', (platform, url, name or url))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error adding source: {e}")
            return False

    def remove_watch_source(self, url: str) -> bool:
        """Удалить источник"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE watch_sources SET active = 0 WHERE url = ?', (url,))
            conn.commit()
            conn.close()
            return True
        except:
            return False

    def get_watch_sources(self, active_only: bool = True) -> List[Dict]:
        """Получить список источников"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if active_only:
            cursor.execute('SELECT * FROM watch_sources WHERE active = 1')
        else:
            cursor.execute('SELECT * FROM watch_sources')

        sources = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return sources

    def record_video_snapshot(self, video_data: Dict) -> bool:
        """Записать снимок состояния видео с метриками вирусности"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            hashtags = json.dumps(video_data.get('hashtags', []))

            cursor.execute('''
                INSERT INTO video_history
                (video_url, platform, title, source_url, publish_date, views, likes, comments, shares,
                 hashtags, sound_name, viral_score, engagement_rate, potential, category, uploader)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                video_data.get('url', ''),
                video_data.get('platform', ''),
                video_data.get('title', ''),
                video_data.get('source_url', video_data.get('source', '')),
                video_data.get('upload_date', video_data.get('publish_date', '')),
                video_data.get('views', 0),
                video_data.get('likes', 0),
                video_data.get('comments', 0),
                video_data.get('shares', 0),
                hashtags,
                video_data.get('sound_name', ''),
                video_data.get('viral_score', 0),
                video_data.get('engagement_rate', 0),
                video_data.get('potential', ''),
                video_data.get('category', ''),
                video_data.get('uploader', '')
            ))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error recording snapshot: {e}")
            return False

    def get_video_history(self, video_url: str, limit: int = 10) -> List[Dict]:
        """Получить историю видео"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM video_history
            WHERE video_url = ?
            ORDER BY recorded_at DESC
            LIMIT ?
        ''', (video_url, limit))

        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return history

    def get_latest_snapshots(self) -> List[Dict]:
        """Получить последние снимки для каждого видео"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT vh.* FROM video_history vh
            INNER JOIN (
                SELECT video_url, MAX(recorded_at) as max_recorded
                FROM video_history
                GROUP BY video_url
            ) latest ON vh.video_url = latest.video_url AND vh.recorded_at = latest.max_recorded
            ORDER BY vh.recorded_at DESC
        ''')

        snapshots = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return snapshots

    def get_previous_snapshot(self, video_url: str) -> Optional[Dict]:
        """Получить предыдущий снимок видео (не самый последний)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM video_history
            WHERE video_url = ?
            ORDER BY recorded_at DESC
            LIMIT 1 OFFSET 1
        ''', (video_url,))

        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def save_trend(self, trend_type: str, trend_key: str, video_urls: List[str], description: str, score: float):
        """Сохранить обнаруженный тренд"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO detected_trends (trend_type, trend_key, video_urls, description, score)
                VALUES (?, ?, ?, ?, ?)
            ''', (trend_type, trend_key, json.dumps(video_urls), description, score))
            conn.commit()
            conn.close()
            return True
        except:
            return False

    def get_recent_trends(self, limit: int = 20) -> List[Dict]:
        """Получить недавние тренды"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM detected_trends
            ORDER BY detected_at DESC
            LIMIT ?
        ''', (limit,))

        trends = []
        for row in cursor.fetchall():
            trend = dict(row)
            trend['video_urls'] = json.loads(trend['video_urls'])
            trends.append(trend)

        conn.close()
        return trends

    def get_recent_videos(self, limit: int = 50) -> List[Dict]:
        """Получить недавно обнаруженные видео (по времени записи)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Получаем последние уникальные видео по времени первого обнаружения
        cursor.execute('''
            SELECT vh.*,
                   (SELECT COUNT(*) FROM video_history WHERE video_url = vh.video_url) as snapshot_count
            FROM video_history vh
            INNER JOIN (
                SELECT video_url, MAX(recorded_at) as max_recorded
                FROM video_history
                GROUP BY video_url
            ) latest ON vh.video_url = latest.video_url AND vh.recorded_at = latest.max_recorded
            ORDER BY vh.recorded_at DESC
            LIMIT ?
        ''', (limit,))

        videos = []
        for row in cursor.fetchall():
            video = dict(row)
            video['hashtags'] = json.loads(video['hashtags']) if video['hashtags'] else []
            videos.append(video)

        conn.close()
        return videos

    def get_stats(self) -> Dict:
        """Статистика базы"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM watch_sources WHERE active = 1')
        sources_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(DISTINCT video_url) FROM video_history')
        videos_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM video_history')
        snapshots_count = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) FROM detected_trends')
        trends_count = cursor.fetchone()[0]

        conn.close()

        return {
            'sources': sources_count,
            'videos_tracked': videos_count,
            'total_snapshots': snapshots_count,
            'trends_detected': trends_count
        }
