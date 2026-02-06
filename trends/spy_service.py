"""
Trend Spy Service v3.0
Автоматический сбор и анализ вирусного контента

Логика работы:
1. Discovery: Находим случайные видео из рекомендаций
2. Monitor: Отслеживаем метрики каждые 2 часа в течение 24ч
3. Analyze: Выявляем паттерны роста и группируем по темам
4. Report: Генерируем отчеты по трендам
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict
import json
import re

try:
    from .db import TrendDB
except Exception:
    TrendDB = None

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False


class TrendSpyService:
    """
    Spy Service для автоматического обнаружения трендов

    Работает без привязки к конкретным аккаунтам:
    - Парсит рекомендации YouTube/TikTok
    - Ищет вирусный контент по паттернам
    - Мониторит 24 часа для расчета velocity
    """

    # Поисковые запросы для discovery
    DISCOVERY_QUERIES = {
        'youtube': [
            'viral 2026', 'trending now', 'blowing up',
            '#shorts viral', 'new trend', 'going viral today',
            'most viewed today', 'trending music 2026',
            'viral challenge', 'satisfying video'
        ],
        'tiktok': [
            'fyp viral', 'trending sound', 'new trend 2026',
            'viral dance', 'trending challenge'
        ]
    }

    # Паттерны вирусного контента
    VIRAL_PATTERNS = [
        r'#viral', r'#fyp', r'#foryou', r'#trending',
        r'#challenge', r'#trend', r'going viral',
        r'blowing up', r'must watch'
    ]

    def __init__(self, db=None):
        """
        db: SQLAlchemy db instance или None для standalone
        """
        self.db = db
        if self.db is None and TrendDB is not None:
            try:
                self.db = TrendDB()
            except Exception:
                self.db = None
        self.yt_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'socket_timeout': 15,
            'retries': 2
        }

    def discover_videos(self, max_per_source: int = 30) -> Dict:
        """
        ???????? 1: Discovery
        ?????????????? ?????????? ?????????? ???? ???????????????????????? ?? ????????????

        Returns:
            {
                'youtube': [...],
                'tiktok': [...],
                'total': N,
                'discovered_at': '...'
            }
        """
        if not HAS_YTDLP:
            return {'error': 'yt-dlp not available', 'total': 0}

        results = {
            'youtube': [],
            'tiktok': [],
            'total': 0,
            'discovered_at': datetime.now().isoformat()
        }

        # YouTube Discovery
        yt_videos = self._discover_youtube(max_per_source)
        results['youtube'] = yt_videos

        # TikTok Discovery
        tt_videos = self._discover_tiktok(max_per_source)
        results['tiktok'] = tt_videos

        results['total'] = len(yt_videos) + len(tt_videos)
        self._store_discovered(results['youtube'] + results['tiktok'])
        return results

    def _store_discovered(self, videos: List[Dict]):
        if not self.db:
            return
        for v in videos:
            try:
                self.db.record_video_snapshot(v)
            except Exception:
                continue

    def _store_snapshot(self, video_url: str, metrics: Dict):
        if not self.db or not metrics:
            return
        payload = {
            'url': video_url,
            'platform': metrics.get('platform', ''),
            'title': metrics.get('title', ''),
            'views': metrics.get('views', 0),
            'likes': metrics.get('likes', 0),
            'comments': metrics.get('comments', 0),
            'shares': metrics.get('shares', 0),
            'upload_date': metrics.get('upload_date', ''),
            'hashtags': metrics.get('hashtags', []),
            'sound_name': metrics.get('sound_name', ''),
        }
        try:
            self.db.record_video_snapshot(payload)
        except Exception:
            pass

    def _load_recent_videos_for_analysis(self, limit: int = 200) -> List[Dict]:
        if not self.db:
            return []
        videos = self.db.get_recent_videos(limit=limit)
        enriched = []
        for v in videos:
            try:
                history = self.db.get_video_history(v.get('video_url', ''), limit=3)
                # Normalize history to spy format
                snapshots = []
                for h in reversed(history):
                    snapshots.append({
                        'views': h.get('views', 0),
                        'likes': h.get('likes', 0),
                        'comments': h.get('comments', 0),
                        'checked_at': h.get('recorded_at')
                    })
                vel = self.calculate_velocity(snapshots) if snapshots else {'velocity': 0, 'acceleration': 1.0}
                v['velocity'] = vel.get('velocity', 0)
                v['acceleration'] = vel.get('acceleration', 1.0)
                enriched.append(v)
            except Exception:
                enriched.append(v)
        return enriched

    def _discover_youtube(self, max_videos: int = 30) -> List[Dict]:
        """Поиск видео на YouTube"""
        videos = []
        seen_urls = set()

        # Случайные запросы
        queries = random.sample(self.DISCOVERY_QUERIES['youtube'], min(5, len(self.DISCOVERY_QUERIES['youtube'])))

        for query in queries:
            try:
                search_url = f"ytsearch20:{query}"
                opts = {
                    **self.yt_opts,
                    'playlistend': 20
                }

                with yt_dlp.YoutubeDL(opts) as ydl:
                    result = ydl.extract_info(search_url, download=False)

                    if not result or 'entries' not in result:
                        continue

                    for entry in result['entries'][:20]:
                        if not entry:
                            continue

                        url = entry.get('url') or f"https://youtube.com/watch?v={entry.get('id', '')}"

                        if url in seen_urls:
                            continue
                        seen_urls.add(url)

                        # Фильтруем по возрасту (< 7 дней)
                        upload_date = entry.get('upload_date', '')
                        if upload_date:
                            try:
                                video_date = datetime.strptime(upload_date, '%Y%m%d')
                                if (datetime.now() - video_date).days > 7:
                                    continue
                            except:
                                pass

                        video = {
                            'url': url,
                            'platform': 'YouTube',
                            'title': entry.get('title', ''),
                            'uploader': entry.get('uploader', ''),
                            'views': entry.get('view_count', 0) or 0,
                            'likes': entry.get('like_count', 0) or 0,
                            'duration': entry.get('duration', 0) or 0,
                            'upload_date': upload_date,
                            'is_short': (entry.get('duration', 0) or 0) <= 60,
                            'hashtags': self._extract_hashtags(entry.get('title', '')),
                            'discovered_at': datetime.now().isoformat(),
                            'source_query': query
                        }

                        # Вирусный потенциал
                        video['viral_score'] = self._calculate_viral_potential(video)
                        videos.append(video)

                        if len(videos) >= max_videos:
                            break

            except Exception as e:
                print(f"Error searching YouTube for '{query}': {e}")
                continue

            if len(videos) >= max_videos:
                break

        # Сортируем по viral_score
        videos.sort(key=lambda x: x.get('viral_score', 0), reverse=True)
        return videos[:max_videos]

    def _discover_tiktok(self, max_videos: int = 20) -> List[Dict]:
        """Поиск видео на TikTok"""
        videos = []
        seen_urls = set()

        queries = random.sample(self.DISCOVERY_QUERIES['tiktok'], min(3, len(self.DISCOVERY_QUERIES['tiktok'])))

        for query in queries:
            try:
                search_url = f"https://www.tiktok.com/search?q={query.replace(' ', '%20')}"

                opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                    'socket_timeout': 20,
                    'playlistend': 15
                }

                with yt_dlp.YoutubeDL(opts) as ydl:
                    result = ydl.extract_info(search_url, download=False)

                    if not result:
                        continue

                    entries = result.get('entries', [result]) if result.get('entries') else [result]

                    for entry in entries[:15]:
                        if not entry:
                            continue

                        url = entry.get('webpage_url') or entry.get('url', '')
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)

                        video = {
                            'url': url,
                            'platform': 'TikTok',
                            'title': entry.get('title', entry.get('description', '')),
                            'uploader': entry.get('uploader', entry.get('creator', '')),
                            'views': entry.get('view_count', 0) or 0,
                            'likes': entry.get('like_count', 0) or 0,
                            'comments': entry.get('comment_count', 0) or 0,
                            'shares': entry.get('repost_count', 0) or 0,
                            'duration': entry.get('duration', 0) or 0,
                            'hashtags': self._extract_hashtags(entry.get('description', '')),
                            'sound_name': entry.get('track', ''),
                            'discovered_at': datetime.now().isoformat(),
                            'source_query': query
                        }

                        video['viral_score'] = self._calculate_viral_potential(video)
                        videos.append(video)

                        if len(videos) >= max_videos:
                            break

            except Exception as e:
                print(f"Error searching TikTok for '{query}': {e}")
                continue

            if len(videos) >= max_videos:
                break

        videos.sort(key=lambda x: x.get('viral_score', 0), reverse=True)
        return videos[:max_videos]

    def _extract_hashtags(self, text: str) -> List[str]:
        """Извлечь хэштеги из текста"""
        if not text:
            return []
        hashtags = re.findall(r'#(\w+)', text)
        return list(set(hashtags))[:10]

    def _calculate_viral_potential(self, video: Dict) -> float:
        """
        Рассчитать вирусный потенциал видео (0-100)

        Факторы:
        - Views velocity (views / hours since upload)
        - Engagement rate
        - Hashtag match
        - Duration (shorts score higher)
        """
        score = 0

        # Views component (0-30 points)
        views = video.get('views', 0)
        if views > 1000000:
            score += 30
        elif views > 100000:
            score += 25
        elif views > 10000:
            score += 15
        elif views > 1000:
            score += 5

        # Engagement (0-30 points)
        likes = video.get('likes', 0)
        comments = video.get('comments', 0)
        if views > 0:
            engagement = (likes + comments) / views
            if engagement > 0.1:
                score += 30
            elif engagement > 0.05:
                score += 20
            elif engagement > 0.02:
                score += 10

        # Hashtag match (0-20 points)
        title = video.get('title', '').lower()
        hashtags = [h.lower() for h in video.get('hashtags', [])]
        viral_matches = 0
        for pattern in self.VIRAL_PATTERNS:
            if re.search(pattern, title) or any(re.search(pattern, f'#{h}') for h in hashtags):
                viral_matches += 1

        score += min(viral_matches * 5, 20)

        # Duration bonus for shorts (0-10 points)
        duration = video.get('duration', 0)
        if 0 < duration <= 60:
            score += 10
        elif duration <= 180:
            score += 5

        # Freshness (0-10 points)
        upload_date = video.get('upload_date', '')
        if upload_date:
            try:
                video_date = datetime.strptime(upload_date, '%Y%m%d')
                days_old = (datetime.now() - video_date).days
                if days_old <= 1:
                    score += 10
                elif days_old <= 3:
                    score += 7
                elif days_old <= 7:
                    score += 3
            except:
                pass

        return min(score, 100)

    def get_video_metrics(self, video_url: str) -> Optional[Dict]:
        """
        Получить текущие метрики видео для мониторинга
        """
        if not HAS_YTDLP:
            return None

        try:
            opts = {
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 15
            }

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

                if not info:
                    return None

                return {
                    'url': video_url,
                    'views': info.get('view_count', 0) or 0,
                    'likes': info.get('like_count', 0) or 0,
                    'comments': info.get('comment_count', 0) or 0,
                    'checked_at': datetime.now().isoformat()
                }

        except Exception as e:
            print(f"Error getting metrics for {video_url}: {e}")
            return None

    def calculate_velocity(self, snapshots: List[Dict]) -> Dict:
        """
        Рассчитать velocity и acceleration на основе снимков

        Args:
            snapshots: Список снимков в хронологическом порядке (старые первые)

        Returns:
            {
                'velocity': views/hour,
                'acceleration': velocity_change,
                'growth_rate': percentage
            }
        """
        if len(snapshots) < 2:
            return {'velocity': 0, 'acceleration': 1.0, 'growth_rate': 0}

        # Последние два снимка
        current = snapshots[-1]
        previous = snapshots[-2]

        # Временной интервал
        try:
            current_time = datetime.fromisoformat(current['checked_at'].replace('Z', '+00:00'))
            previous_time = datetime.fromisoformat(previous['checked_at'].replace('Z', '+00:00'))
            hours_diff = max((current_time - previous_time).total_seconds() / 3600, 0.1)
        except:
            hours_diff = 2  # Default 2 hours

        views_diff = current['views'] - previous['views']
        velocity = views_diff / hours_diff

        # Acceleration (если есть 3+ снимка)
        acceleration = 1.0
        if len(snapshots) >= 3:
            older = snapshots[-3]
            try:
                older_time = datetime.fromisoformat(older['checked_at'].replace('Z', '+00:00'))
                older_hours = max((previous_time - older_time).total_seconds() / 3600, 0.1)
                older_velocity = (previous['views'] - older['views']) / older_hours
                if older_velocity > 0:
                    acceleration = velocity / older_velocity
            except:
                pass

        # Growth rate
        growth_rate = 0
        if previous['views'] > 0:
            growth_rate = (views_diff / previous['views']) * 100

        return {
            'velocity': round(velocity, 1),
            'acceleration': round(acceleration, 2),
            'growth_rate': round(growth_rate, 2)
        }

    def analyze_trends(self, videos: List[Dict]) -> Dict:
        """
        Анализ трендов по группам

        Args:
            videos: Список видео с метриками velocity

        Returns:
            {
                'hashtag_trends': [...],
                'sound_trends': [...],
                'rising_videos': [...],
                'topics': [...]
            }
        """
        if not videos:
            return {
                'hashtag_trends': [],
                'sound_trends': [],
                'rising_videos': [],
                'topics': []
            }

        # Фильтруем видео с положительной velocity
        active_videos = [v for v in videos if v.get('velocity', 0) > 0]

        if not active_videos:
            return {
                'hashtag_trends': [],
                'sound_trends': [],
                'rising_videos': videos[:10],
                'topics': []
            }

        avg_velocity = sum(v.get('velocity', 0) for v in active_videos) / len(active_videos)

        # Группировка по хэштегам
        hashtag_groups = defaultdict(list)
        for video in active_videos:
            for tag in video.get('hashtags', []):
                if tag and video.get('velocity', 0) > avg_velocity * 0.5:
                    hashtag_groups[tag.lower()].append(video)

        hashtag_trends = []
        for tag, vids in hashtag_groups.items():
            if len(vids) >= 2:
                avg_vel = sum(v.get('velocity', 0) for v in vids) / len(vids)
                hashtag_trends.append({
                    'type': 'hashtag',
                    'key': f'#{tag}',
                    'videos_count': len(vids),
                    'avg_velocity': round(avg_vel, 1),
                    'score': round(avg_vel * len(vids), 1),
                    'sample_videos': [v.get('url') for v in vids[:3]]
                })

        hashtag_trends.sort(key=lambda x: x['score'], reverse=True)

        # Группировка по звукам (TikTok)
        sound_groups = defaultdict(list)
        for video in active_videos:
            sound = video.get('sound_name', '')
            if sound and video.get('velocity', 0) > avg_velocity * 0.5:
                sound_groups[sound.lower()].append(video)

        sound_trends = []
        for sound, vids in sound_groups.items():
            if len(vids) >= 2:
                avg_vel = sum(v.get('velocity', 0) for v in vids) / len(vids)
                sound_trends.append({
                    'type': 'sound',
                    'key': sound,
                    'videos_count': len(vids),
                    'avg_velocity': round(avg_vel, 1),
                    'score': round(avg_vel * len(vids), 1),
                    'sample_videos': [v.get('url') for v in vids[:3]]
                })

        sound_trends.sort(key=lambda x: x['score'], reverse=True)

        # Rising videos (высокая velocity или acceleration)
        rising = [v for v in active_videos if v.get('velocity', 0) > avg_velocity * 2 or v.get('acceleration', 1) > 2]
        rising.sort(key=lambda x: x.get('velocity', 0), reverse=True)

        # Topic detection (простой - по частым словам)
        word_freq = defaultdict(int)
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
                      'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                      'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
                      'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
                      'into', 'through', 'during', 'before', 'after', 'above', 'below',
                      'and', 'or', 'but', 'if', 'because', 'until', 'while', 'this', 'that',
                      'i', 'me', 'my', 'you', 'your', 'he', 'she', 'it', 'we', 'they'}

        for video in active_videos:
            title = video.get('title', '').lower()
            words = re.findall(r'\b[a-z]{4,}\b', title)
            for word in words:
                if word not in stop_words:
                    word_freq[word] += 1

        topics = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        topics = [{'topic': t[0], 'mentions': t[1]} for t in topics if t[1] >= 2]

        return {
            'hashtag_trends': hashtag_trends[:10],
            'sound_trends': sound_trends[:10],
            'rising_videos': rising[:20],
            'topics': topics,
            'avg_velocity': round(avg_velocity, 1),
            'total_analyzed': len(videos)
        }

    def generate_report(self, analysis: Dict) -> str:
        """Генерация текстового отчета"""
        report = []
        report.append("=" * 60)
        report.append("TREND SPY REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        report.append("=" * 60)

        report.append(f"\nVideos analyzed: {analysis.get('total_analyzed', 0)}")
        report.append(f"Average velocity: {analysis.get('avg_velocity', 0)} views/hour")

        if analysis.get('hashtag_trends'):
            report.append("\n--- TRENDING HASHTAGS ---")
            for t in analysis['hashtag_trends'][:5]:
                report.append(f"  {t['key']}")
                report.append(f"    {t['videos_count']} videos | Velocity: {t['avg_velocity']}/h | Score: {t['score']}")

        if analysis.get('sound_trends'):
            report.append("\n--- TRENDING SOUNDS ---")
            for t in analysis['sound_trends'][:5]:
                report.append(f"  {t['key'][:40]}...")
                report.append(f"    {t['videos_count']} videos | Velocity: {t['avg_velocity']}/h")

        if analysis.get('rising_videos'):
            report.append("\n--- RISING VIDEOS ---")
            for v in analysis['rising_videos'][:5]:
                report.append(f"  {v.get('title', 'Untitled')[:50]}...")
                report.append(f"    Velocity: {v.get('velocity', 0)}/h | Accel: {v.get('acceleration', 1)}x")

        if analysis.get('topics'):
            report.append("\n--- HOT TOPICS ---")
            for t in analysis['topics'][:5]:
                report.append(f"  {t['topic']} ({t['mentions']} mentions)")

        report.append("\n" + "=" * 60)

        return "\n".join(report)


# Celery Tasks (для фоновой работы)
def create_celery_tasks(celery_app, spy_service):
    """Создать Celery задачи для spy service"""

    @celery_app.task
    def discover_task():
        """Задача discovery - каждые 4 часа"""
        results = spy_service.discover_videos(max_per_source=30)
        # TODO: сохранить в БД
        return results

    @celery_app.task
    def monitor_task(video_url):
        """Задача мониторинга - каждые 2 часа"""
        metrics = spy_service.get_video_metrics(video_url)
        # TODO: сохранить snapshot в БД
        return metrics

    @celery_app.task
    def analyze_task():
        """Задача анализа - каждые 6 часов"""
        # TODO: получить videos из БД
        # analysis = spy_service.analyze_trends(videos)
        pass

    return {
        'discover': discover_task,
        'monitor': monitor_task,
        'analyze': analyze_task
    }


# CLI для тестирования
if __name__ == '__main__':
    spy = TrendSpyService()

    print("Trend Spy Service CLI")
    print("-" * 40)

    print("\n[1] Running discovery...")
    discovered = spy.discover_videos(max_per_source=10)

    print(f"\nFound {discovered['total']} videos:")
    print(f"  YouTube: {len(discovered['youtube'])}")
    print(f"  TikTok: {len(discovered['tiktok'])}")

    if discovered['youtube']:
        print("\nTop YouTube discoveries:")
        for v in discovered['youtube'][:5]:
            print(f"  [{v.get('viral_score', 0):.0f}] {v.get('title', 'Untitled')[:40]}...")
            print(f"       Views: {v.get('views', 0):,} | {v.get('url', '')[:50]}")

    print("\n[2] Analyzing trends...")
    all_videos = discovered['youtube'] + discovered['tiktok']

    # Симулируем velocity данные
    for v in all_videos:
        v['velocity'] = v.get('views', 0) / max(24, 1)  # Примерная velocity
        v['acceleration'] = 1.0 + random.random()

    analysis = spy.analyze_trends(all_videos)
    print(spy.generate_report(analysis))
