"""
Celery Application
Фоновые задачи для парсинга и мониторинга трендов
"""
import os
from celery import Celery
from celery.schedules import crontab
from datetime import datetime, timedelta

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
    # Discovery: каждые 4 часа
    'trend-discovery': {
        'task': 'web.celery_app.discover_trends',
        'schedule': crontab(minute=0, hour='*/4'),
    },
    # Monitor: каждые 2 часа
    'trend-monitor': {
        'task': 'web.celery_app.monitor_trends',
        'schedule': crontab(minute=30, hour='*/2'),
    },
    # Analyze: каждые 6 часов
    'trend-analyze': {
        'task': 'web.celery_app.analyze_trends',
        'schedule': crontab(minute=0, hour='*/6'),
    },
    # Cleanup: ежедневно в 3:00
    'trend-cleanup': {
        'task': 'web.celery_app.cleanup_old_videos',
        'schedule': crontab(minute=0, hour=3),
    }
}


# Tasks

@celery_app.task(bind=True, max_retries=3)
def discover_trends(self):
    """
    Поиск новых видео для мониторинга
    Запускается каждые 4 часа
    """
    try:
        from trends.spy_service import TrendSpyService

        spy = TrendSpyService()
        results = spy.discover_videos(max_per_source=30)

        # Сохраняем в БД
        from web.database import db, TrendVideo
        from flask import current_app

        with current_app.app_context():
            for platform in ['youtube', 'tiktok']:
                for video in results.get(platform, []):
                    existing = TrendVideo.query.filter_by(video_url=video['url']).first()
                    if not existing:
                        tv = TrendVideo(
                            video_url=video['url'],
                            platform=video.get('platform', platform),
                            title=video.get('title', ''),
                            uploader=video.get('uploader', ''),
                            initial_views=video.get('views', 0),
                            current_views=video.get('views', 0),
                            hashtags=video.get('hashtags', []),
                            status='monitoring'
                        )
                        db.session.add(tv)

            db.session.commit()

        return {
            'status': 'success',
            'discovered': results['total'],
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=3)
def monitor_trends(self):
    """
    Мониторинг метрик видео
    Запускается каждые 2 часа
    """
    try:
        from trends.spy_service import TrendSpyService
        from web.database import db, TrendVideo, TrendSnapshot
        from flask import current_app

        spy = TrendSpyService()

        with current_app.app_context():
            # Получаем видео в статусе monitoring
            videos = TrendVideo.query.filter_by(status='monitoring').all()

            updated = 0
            for video in videos:
                metrics = spy.get_video_metrics(video.video_url)

                if metrics:
                    # Создаем snapshot
                    snapshot = TrendSnapshot(
                        video_id=video.id,
                        views=metrics['views'],
                        likes=metrics['likes'],
                        comments=metrics.get('comments', 0)
                    )
                    db.session.add(snapshot)

                    # Обновляем видео
                    video.current_views = metrics['views']
                    video.last_checked = datetime.utcnow()

                    # Рассчитываем velocity
                    snapshots = TrendSnapshot.query\
                        .filter_by(video_id=video.id)\
                        .order_by(TrendSnapshot.recorded_at)\
                        .all()

                    if len(snapshots) >= 2:
                        snap_data = [{'views': s.views, 'checked_at': s.recorded_at.isoformat()} for s in snapshots]
                        vel_data = spy.calculate_velocity(snap_data)
                        video.velocity = vel_data['velocity']
                        video.acceleration = vel_data['acceleration']

                        # Помечаем как trending если velocity высокая
                        if video.velocity > 1000:  # 1000 views/hour threshold
                            video.status = 'trending'

                    updated += 1

            db.session.commit()

        return {
            'status': 'success',
            'updated': updated,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        self.retry(exc=e, countdown=60)


@celery_app.task(bind=True)
def analyze_trends(self):
    """
    Анализ и группировка трендов
    Запускается каждые 6 часов
    """
    try:
        from trends.spy_service import TrendSpyService
        from web.database import db, TrendVideo, DetectedTrend
        from flask import current_app

        spy = TrendSpyService()

        with current_app.app_context():
            # Получаем все активные видео
            videos = TrendVideo.query\
                .filter(TrendVideo.status.in_(['monitoring', 'trending']))\
                .all()

            video_data = [v.to_dict() for v in videos]
            analysis = spy.analyze_trends(video_data)

            # Сохраняем обнаруженные тренды
            for trend in analysis.get('hashtag_trends', [])[:10]:
                dt = DetectedTrend(
                    trend_type='hashtag',
                    trend_key=trend['key'],
                    video_count=trend['videos_count'],
                    avg_velocity=trend['avg_velocity'],
                    score=trend['score'],
                    video_urls=trend['sample_videos'],
                    status='active'
                )
                db.session.add(dt)

            for trend in analysis.get('sound_trends', [])[:10]:
                dt = DetectedTrend(
                    trend_type='sound',
                    trend_key=trend['key'],
                    video_count=trend['videos_count'],
                    avg_velocity=trend['avg_velocity'],
                    score=trend['score'],
                    video_urls=trend['sample_videos'],
                    status='active'
                )
                db.session.add(dt)

            db.session.commit()

        return {
            'status': 'success',
            'hashtag_trends': len(analysis.get('hashtag_trends', [])),
            'sound_trends': len(analysis.get('sound_trends', [])),
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@celery_app.task
def cleanup_old_videos():
    """
    Очистка старых видео (> 7 дней)
    Запускается ежедневно
    """
    try:
        from web.database import db, TrendVideo
        from flask import current_app

        with current_app.app_context():
            week_ago = datetime.utcnow() - timedelta(days=7)

            # Архивируем старые видео
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
    Фоновый парсинг блогера
    """
    try:
        from web.database import db, Blogger, VideoHistory
        from parsers import YouTubeParser, TikTokParser
        from flask import current_app

        with current_app.app_context():
            blogger = Blogger.query.get(blogger_id)
            if not blogger:
                return {'status': 'error', 'error': 'Blogger not found'}

            yt_parser = YouTubeParser()
            tt_parser = TikTokParser()

            results = {'youtube': [], 'tiktok': []}

            # YouTube
            if blogger.youtube_url:
                try:
                    videos = yt_parser.get_all_videos(blogger.youtube_url, max_videos=30)
                    results['youtube'] = videos or []
                except:
                    pass

            # TikTok
            if blogger.tiktok_url:
                try:
                    videos = tt_parser.get_all_videos(blogger.tiktok_url, max_videos=30)
                    results['tiktok'] = videos or []
                except:
                    pass

            # Сохраняем в БД
            for platform, videos in results.items():
                for video in videos:
                    vh = VideoHistory(
                        user_id=user_id,
                        blogger_id=blogger_id,
                        video_url=video.get('url', ''),
                        platform=platform,
                        title=video.get('title', ''),
                        views=video.get('views', 0),
                        likes=video.get('likes', 0),
                        comments=video.get('comments', 0),
                        engagement_rate=video.get('engagement_rate', 0),
                        viral_score=video.get('viral_score', 0),
                        hashtags=video.get('hashtags', [])
                    )
                    db.session.add(vh)

            db.session.commit()

        return {
            'status': 'success',
            'blogger_id': blogger_id,
            'youtube_count': len(results['youtube']),
            'tiktok_count': len(results['tiktok'])
        }

    except Exception as e:
        self.retry(exc=e, countdown=30)
