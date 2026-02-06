"""
Celery Application
Фоновые задачи для парсинга и мониторинга трендов
"""
import os
import sys
from celery import Celery
from celery.schedules import crontab
from datetime import datetime, timedelta

# Добавляем корень проекта в PATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Celery configuration
celery_app = Celery(
    'blogger_analytics',
    broker=os.getenv('REDIS_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('REDIS_URL', 'redis://localhost:6379/0')
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max
    worker_prefetch_multiplier=1,
    task_acks_late=True
)

# Periodic tasks schedule
celery_app.conf.beat_schedule = {
    # Daily parsing: ежедневно в 3:00
    'daily-parsing': {
        'task': 'web.celery_app.daily_parse_all',
        'schedule': crontab(minute=0, hour=3),
    },
    # Cleanup: ежедневно в 4:00
    'trend-cleanup': {
        'task': 'web.celery_app.cleanup_old_videos',
        'schedule': crontab(minute=0, hour=4),
    }
}


def _get_flask_app():
    """Создаёт Flask app для использования в Celery задачах"""
    from flask import Flask
    from web.database import db, init_db
    from web.auth import init_auth

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')

    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(BASE_DIR, 'data', 'blogger_analytics.db')
        if os.path.exists(db_path):
            DATABASE_URL = f'sqlite:///{db_path}'

    if DATABASE_URL:
        app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        init_db(app)
        init_auth(app)

    return app


# Lazy Flask app (создаётся один раз при первом вызове задачи)
_flask_app = None


def get_flask_app():
    global _flask_app
    if _flask_app is None:
        _flask_app = _get_flask_app()
    return _flask_app


# ==================== Tasks ====================


def _upsert_video(db, VideoHistory, payload: dict):
    existing = VideoHistory.query.filter_by(
        user_id=payload.get('user_id'),
        video_url=payload.get('video_url')
    ).first()
    if existing:
        existing.views = payload.get('views', existing.views)
        existing.likes = payload.get('likes', existing.likes)
        existing.comments = payload.get('comments', existing.comments)
        existing.engagement_rate = payload.get('engagement_rate', existing.engagement_rate)
        existing.viral_score = payload.get('viral_score', existing.viral_score)
        existing.hashtags = payload.get('hashtags', existing.hashtags)
        existing.recorded_at = datetime.utcnow()
        return existing
    vh = VideoHistory(**payload)
    db.session.add(vh)
    return vh

@celery_app.task(bind=True, max_retries=3)
def daily_parse_all(self):
    """
    Ежедневный парсинг всех блогеров всех пользователей
    Запускается в 3:00
    """
    try:
        app = get_flask_app()

        with app.app_context():
            from web.database import db, User, Blogger, VideoHistory
            from parsers.youtube_parser import YouTubeParser
            from parsers.tiktok_parser import TikTokParser

            users = User.query.filter_by(is_active=True).all()

            total_bloggers = 0
            total_parsed = 0

            yt_parser = YouTubeParser()
            tt_parser = TikTokParser()

            for user in users:
                bloggers = Blogger.query.filter_by(
                    user_id=user.id, is_active=True
                ).all()

                for blogger in bloggers:
                    total_bloggers += 1
                    try:
                        videos_added = 0

                        # YouTube
                        if blogger.youtube_url:
                            try:
                                videos = yt_parser.get_all_videos(blogger.youtube_url, max_videos=30)
                                for video in (videos or []):
                                    payload = {
                                        'user_id': user.id,
                                        'blogger_id': blogger.id,
                                        'video_url': video.get('url', ''),
                                        'platform': 'youtube',
                                        'title': video.get('title', ''),
                                        'views': video.get('views', 0),
                                        'likes': video.get('likes', 0),
                                        'comments': video.get('comments', 0),
                                        'engagement_rate': video.get('engagement_rate', 0),
                                        'viral_score': video.get('viral_score', 0),
                                        'hashtags': video.get('hashtags', [])
                                    }
                                    _upsert_video(db, VideoHistory, payload)
                                    videos_added += 1
                            except Exception:
                                pass

                        # TikTok
                        if blogger.tiktok_url:
                            try:
                                videos = tt_parser.get_all_videos(blogger.tiktok_url, max_videos=30)
                                for video in (videos or []):
                                    payload = {
                                        'user_id': user.id,
                                        'blogger_id': blogger.id,
                                        'video_url': video.get('url', ''),
                                        'platform': 'tiktok',
                                        'title': video.get('title', ''),
                                        'views': video.get('views', 0),
                                        'likes': video.get('likes', 0),
                                        'comments': video.get('comments', 0),
                                        'engagement_rate': video.get('engagement_rate', 0),
                                        'viral_score': video.get('viral_score', 0),
                                        'hashtags': video.get('hashtags', [])
                                    }
                                    _upsert_video(db, VideoHistory, payload)
                                    videos_added += 1
                            except Exception:
                                pass

                        db.session.commit()
                        if videos_added > 0:
                            total_parsed += 1

                    except Exception:
                        db.session.rollback()

        return {
            'status': 'success',
            'total_bloggers': total_bloggers,
            'parsed': total_parsed,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task
def cleanup_old_videos():
    """
    Очистка старых trend-видео (> 7 дней)
    Запускается ежедневно
    """
    try:
        app = get_flask_app()

        with app.app_context():
            from web.database import db, TrendVideo

            week_ago = datetime.utcnow() - timedelta(days=7)

            old_videos = TrendVideo.query\
                .filter(TrendVideo.first_seen < week_ago)\
                .filter(TrendVideo.status != 'archived')\
                .all()

            for video in old_videos:
                video.status = 'archived'

            db.session.commit()

        return {
            'status': 'success',
            'archived': len(old_videos),
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@celery_app.task(bind=True, max_retries=3)
def parse_blogger_task(self, blogger_id: int, user_id: int):
    """
    Фоновый парсинг одного блогера (вызывается из API)
    """
    try:
        app = get_flask_app()

        with app.app_context():
            from web.database import db, Blogger, VideoHistory
            from parsers.youtube_parser import YouTubeParser
            from parsers.tiktok_parser import TikTokParser

            blogger = db.session.get(Blogger, blogger_id)
            if not blogger:
                return {'status': 'error', 'error': 'Blogger not found'}

            yt_parser = YouTubeParser()
            tt_parser = TikTokParser()

            results = {'youtube': 0, 'tiktok': 0}

            # YouTube
            if blogger.youtube_url:
                try:
                    videos = yt_parser.get_all_videos(blogger.youtube_url, max_videos=30)
                    for video in (videos or []):
                        payload = {
                            'user_id': user_id,
                            'blogger_id': blogger_id,
                            'video_url': video.get('url', ''),
                            'platform': 'youtube',
                            'title': video.get('title', ''),
                            'views': video.get('views', 0),
                            'likes': video.get('likes', 0),
                            'comments': video.get('comments', 0),
                            'engagement_rate': video.get('engagement_rate', 0),
                            'viral_score': video.get('viral_score', 0),
                            'hashtags': video.get('hashtags', [])
                        }
                        _upsert_video(db, VideoHistory, payload)
                        results['youtube'] += 1
                except Exception:
                    pass

            # TikTok
            if blogger.tiktok_url:
                try:
                    videos = tt_parser.get_all_videos(blogger.tiktok_url, max_videos=30)
                    for video in (videos or []):
                        payload = {
                            'user_id': user_id,
                            'blogger_id': blogger_id,
                            'video_url': video.get('url', ''),
                            'platform': 'tiktok',
                            'title': video.get('title', ''),
                            'views': video.get('views', 0),
                            'likes': video.get('likes', 0),
                            'comments': video.get('comments', 0),
                            'engagement_rate': video.get('engagement_rate', 0),
                            'viral_score': video.get('viral_score', 0),
                            'hashtags': video.get('hashtags', [])
                        }
                        _upsert_video(db, VideoHistory, payload)
                        results['tiktok'] += 1
                except Exception:
                    pass

            db.session.commit()

        return {
            'status': 'success',
            'blogger_id': blogger_id,
            'youtube_count': results['youtube'],
            'tiktok_count': results['tiktok']
        }

    except Exception as e:
        self.retry(exc=e, countdown=30)
