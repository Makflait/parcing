"""
Parser Service
Сервис для парсинга блогеров с сохранением в БД
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
import time

# Добавляем путь к парсерам
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Лимит видео на платформу (по умолчанию 50, настраивается через env)
MAX_VIDEOS = int(os.getenv('MAX_VIDEOS_PER_PLATFORM', '50'))

try:
    from parsers import YouTubeParser, TikTokParser, InstagramParser
    PARSERS_AVAILABLE = True
except ImportError:
    PARSERS_AVAILABLE = False
    print("[ParserService] Parsers not available")


class ParserService:
    """Сервис для парсинга блогеров"""

    def __init__(self, app=None):
        self.app = app
        self.yt_parser = YouTubeParser() if PARSERS_AVAILABLE else None
        self.tt_parser = TikTokParser() if PARSERS_AVAILABLE else None
        self.ig_parser = InstagramParser() if PARSERS_AVAILABLE else None

        # Статус парсинга
        self.status = {
            'running': False,
            'blogger_id': None,
            'blogger_name': '',
            'platform': '',
            'progress': 0,
            'total_parsed': 0,
            'errors': [],
            'last_run': None
        }

        self._lock = threading.Lock()

    def parse_blogger(self, blogger_id: int, user_id: int) -> Dict:
        """
        Парсит конкретного блогера и сохраняет данные в БД
        """
        if not PARSERS_AVAILABLE:
            return {'success': False, 'error': 'Parsers not available'}

        try:
            from web.database import db, Blogger, VideoHistory
        except ImportError:
            from database import db, Blogger, VideoHistory

        with self.app.app_context():
            blogger = Blogger.query.get(blogger_id)
            if not blogger:
                return {'success': False, 'error': 'Blogger not found'}

            if blogger.user_id != user_id:
                return {'success': False, 'error': 'Access denied'}

            results = {
                'blogger_id': blogger_id,
                'blogger_name': blogger.name,
                'youtube': {'videos': 0, 'views': 0},
                'tiktok': {'videos': 0, 'views': 0},
                'instagram': {'videos': 0, 'views': 0},
                'errors': []
            }

            # YouTube
            if blogger.youtube_url and self.yt_parser:
                try:
                    self._update_status(blogger_id, blogger.name, 'youtube', 10)
                    videos = self.yt_parser.get_all_videos(blogger.youtube_url, max_videos=MAX_VIDEOS)

                    for video in (videos or []):
                        self._save_video(user_id, blogger_id, 'youtube', video)
                        results['youtube']['videos'] += 1
                        results['youtube']['views'] += video.get('views', 0)

                    self._update_status(blogger_id, blogger.name, 'youtube', 33)
                except Exception as e:
                    results['errors'].append(f"YouTube: {str(e)}")

            # TikTok
            if blogger.tiktok_url and self.tt_parser:
                try:
                    self._update_status(blogger_id, blogger.name, 'tiktok', 40)
                    videos = self.tt_parser.get_all_videos(blogger.tiktok_url, max_videos=MAX_VIDEOS)

                    for video in (videos or []):
                        self._save_video(user_id, blogger_id, 'tiktok', video)
                        results['tiktok']['videos'] += 1
                        results['tiktok']['views'] += video.get('views', 0)

                    self._update_status(blogger_id, blogger.name, 'tiktok', 66)
                except Exception as e:
                    results['errors'].append(f"TikTok: {str(e)}")

            # Instagram
            if blogger.instagram_url and self.ig_parser:
                try:
                    self._update_status(blogger_id, blogger.name, 'instagram', 70)
                    videos = self.ig_parser.get_all_videos(blogger.instagram_url, max_videos=MAX_VIDEOS)

                    for video in (videos or []):
                        self._save_video(user_id, blogger_id, 'instagram', video)
                        results['instagram']['videos'] += 1
                        results['instagram']['views'] += video.get('views', 0)

                    self._update_status(blogger_id, blogger.name, 'instagram', 90)
                except Exception as e:
                    results['errors'].append(f"Instagram: {str(e)}")

            # Обновляем время парсинга блогера
            blogger.updated_at = datetime.utcnow()
            db.session.commit()

            self._update_status(blogger_id, blogger.name, 'done', 100)

            results['success'] = True
            results['total_videos'] = (
                results['youtube']['videos'] +
                results['tiktok']['videos'] +
                results['instagram']['videos']
            )

            return results

    def _save_video(self, user_id: int, blogger_id: int, platform: str, video: Dict):
        """Сохраняет видео в БД (или обновляет если уже есть)"""
        try:
            from web.database import db, VideoHistory
        except ImportError:
            from database import db, VideoHistory

        video_url = video.get('url', video.get('video_url', ''))
        if not video_url:
            return

        # Проверяем существует ли видео
        existing = VideoHistory.query.filter_by(
            user_id=user_id,
            video_url=video_url
        ).first()

        if existing:
            # Обновляем метрики
            existing.views = video.get('views', existing.views)
            existing.likes = video.get('likes', existing.likes)
            existing.comments = video.get('comments', existing.comments)
            existing.shares = video.get('shares', existing.shares)
            existing.recorded_at = datetime.utcnow()
        else:
            # Создаём новую запись
            vh = VideoHistory(
                user_id=user_id,
                blogger_id=blogger_id,
                video_url=video_url,
                platform=platform,
                title=video.get('title', ''),
                uploader=video.get('uploader', video.get('channel', '')),
                views=video.get('views', 0),
                likes=video.get('likes', 0),
                comments=video.get('comments', 0),
                shares=video.get('shares', 0),
                engagement_rate=video.get('engagement_rate', 0),
                viral_score=video.get('viral_score', 0),
                hashtags=video.get('hashtags', [])
            )
            db.session.add(vh)

        db.session.commit()

    def _update_status(self, blogger_id: int, blogger_name: str, platform: str, progress: int):
        """Обновляет статус парсинга"""
        with self._lock:
            self.status['blogger_id'] = blogger_id
            self.status['blogger_name'] = blogger_name
            self.status['platform'] = platform
            self.status['progress'] = progress

    def parse_blogger_async(self, blogger_id: int, user_id: int):
        """Запуск парсинга в фоне"""
        if self.status['running']:
            return {'success': False, 'error': 'Parser already running'}

        def run():
            with self._lock:
                self.status['running'] = True

            try:
                result = self.parse_blogger(blogger_id, user_id)
                with self._lock:
                    self.status['total_parsed'] = result.get('total_videos', 0)
                    self.status['errors'] = result.get('errors', [])
                    self.status['last_run'] = datetime.utcnow().isoformat()
            finally:
                with self._lock:
                    self.status['running'] = False

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        return {'success': True, 'message': 'Parsing started'}

    def parse_all_user_bloggers(self, user_id: int) -> Dict:
        """Парсит всех блогеров пользователя"""
        try:
            from web.database import Blogger
        except ImportError:
            from database import Blogger

        with self.app.app_context():
            bloggers = Blogger.query.filter_by(user_id=user_id, is_active=True).all()

            results = {
                'total_bloggers': len(bloggers),
                'parsed': 0,
                'errors': []
            }

            for blogger in bloggers:
                try:
                    result = self.parse_blogger(blogger.id, user_id)
                    if result.get('success'):
                        results['parsed'] += 1
                    else:
                        results['errors'].append(f"{blogger.name}: {result.get('error')}")
                except Exception as e:
                    results['errors'].append(f"{blogger.name}: {str(e)}")

            return results

    def get_blogger_stats(self, blogger_id: int, user_id: int) -> Dict:
        """Получает статистику по блогеру из БД"""
        try:
            from web.database import db, Blogger, VideoHistory
        except ImportError:
            from database import db, Blogger, VideoHistory
        from sqlalchemy import func

        with self.app.app_context():
            blogger = Blogger.query.filter_by(id=blogger_id, user_id=user_id).first()
            if not blogger:
                return None

            # Агрегация по платформам
            stats = db.session.query(
                VideoHistory.platform,
                func.count(VideoHistory.id).label('videos'),
                func.sum(VideoHistory.views).label('views'),
                func.sum(VideoHistory.likes).label('likes'),
                func.sum(VideoHistory.comments).label('comments')
            ).filter(
                VideoHistory.blogger_id == blogger_id,
                VideoHistory.user_id == user_id
            ).group_by(VideoHistory.platform).all()

            result = {
                'id': blogger.id,
                'name': blogger.name,
                'youtube': blogger.youtube_url,
                'tiktok': blogger.tiktok_url,
                'instagram': blogger.instagram_url,
                'created_at': blogger.created_at.isoformat() if blogger.created_at else None,
                'updated_at': blogger.updated_at.isoformat() if blogger.updated_at else None,
                'platforms': {},
                'total': {
                    'videos': 0,
                    'views': 0,
                    'likes': 0,
                    'comments': 0
                }
            }

            for stat in stats:
                platform = stat.platform or 'unknown'
                result['platforms'][platform] = {
                    'videos': stat.videos or 0,
                    'views': int(stat.views or 0),
                    'likes': int(stat.likes or 0),
                    'comments': int(stat.comments or 0)
                }
                result['total']['videos'] += stat.videos or 0
                result['total']['views'] += int(stat.views or 0)
                result['total']['likes'] += int(stat.likes or 0)
                result['total']['comments'] += int(stat.comments or 0)

            if result['total']['views'] > 0:
                result['total']['engagement'] = round(
                    result['total']['likes'] / result['total']['views'] * 100, 2
                )
            else:
                result['total']['engagement'] = 0

            return result

    def get_blogger_videos(self, blogger_id: int, user_id: int, limit: int = 50) -> List[Dict]:
        """Получает видео блогера"""
        try:
            from web.database import VideoHistory
        except ImportError:
            from database import VideoHistory

        with self.app.app_context():
            videos = VideoHistory.query.filter_by(
                blogger_id=blogger_id,
                user_id=user_id
            ).order_by(
                VideoHistory.views.desc()
            ).limit(limit).all()

            return [v.to_dict() for v in videos]


# Глобальный экземпляр
parser_service = None

def init_parser_service(app):
    """Инициализация сервиса парсинга"""
    global parser_service
    parser_service = ParserService(app)
    return parser_service

def get_parser_service():
    """Получить экземпляр сервиса"""
    return parser_service
