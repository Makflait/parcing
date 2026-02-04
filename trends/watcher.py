"""
Trend Watcher v2.0
Автоматическое отслеживание velocity и детекция трендов
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import defaultdict
import json
import re

from .db import TrendDB

# Импорт discovery
try:
    from .discovery import TrendDiscovery
    HAS_DISCOVERY = True
except ImportError:
    HAS_DISCOVERY = False

# Попробуем импортировать парсеры
try:
    from parsers.youtube_parser import YouTubeParser
    from parsers.tiktok_parser import TikTokParser
    HAS_PARSERS = True
except ImportError:
    HAS_PARSERS = False


class TrendWatcher:
    """
    Сервис отслеживания трендов

    Логика:
    1. Периодически собирает данные с источников
    2. Записывает снимки в историю
    3. Рассчитывает velocity (скорость роста)
    4. Выявляет аномально быстрорастущие видео
    5. Группирует по хэштегам/звукам для определения трендов
    """

    def __init__(self, db: TrendDB = None):
        self.db = db or TrendDB()

        if HAS_PARSERS:
            self.yt_parser = YouTubeParser()
            self.tt_parser = TikTokParser()
        else:
            self.yt_parser = None
            self.tt_parser = None

        if HAS_DISCOVERY:
            self.discovery = TrendDiscovery()
        else:
            self.discovery = None

    def auto_discover(self, max_per_source: int = 20) -> Dict:
        """
        Автоматически обнаружить и записать трендовый контент

        Не требует ручного добавления источников - сам ищет тренды
        Использует умный анализ вирусного потенциала
        """
        if not self.discovery:
            return {'error': 'Discovery module not available', 'collected': 0}

        results = {
            'collected': 0,
            'youtube_trending': 0,
            'youtube_shorts': 0,
            'tiktok_trending': 0,
            'viral_candidates': [],
            'trending_topics': [],
            'errors': 0
        }

        try:
            # Запускаем discovery с новым алгоритмом
            discovered = self.discovery.discover_all(max_per_source=max_per_source)

            # Записываем все найденные видео
            all_videos = (
                discovered.get('youtube_trending', []) +
                discovered.get('youtube_shorts', []) +
                discovered.get('tiktok_trending', [])
            )

            for video in all_videos:
                try:
                    self.db.record_video_snapshot(video)
                    results['collected'] += 1

                    source = video.get('source', '')
                    if video.get('is_short'):
                        results['youtube_shorts'] += 1
                    elif 'tiktok' in source.lower():
                        results['tiktok_trending'] += 1
                    else:
                        results['youtube_trending'] += 1
                except:
                    results['errors'] += 1

            # Добавляем вирусные кандидаты и тренды из discovery
            results['viral_candidates'] = discovered.get('viral_candidates', [])[:15]
            results['trending_topics'] = discovered.get('trending_topics', [])[:10]
            results['discovered_at'] = datetime.now().isoformat()
            results['total'] = discovered.get('total', results['collected'])

        except Exception as e:
            results['error'] = str(e)
            results['errors'] += 1

        return results

    def add_source(self, url: str, name: str = None) -> Dict:
        """Добавить источник для отслеживания"""
        platform = self._detect_platform(url)
        if not platform:
            return {'success': False, 'error': 'Неизвестная платформа'}

        success = self.db.add_watch_source(platform, url, name)
        return {
            'success': success,
            'platform': platform,
            'url': url,
            'name': name
        }

    def remove_source(self, url: str) -> bool:
        """Удалить источник"""
        return self.db.remove_watch_source(url)

    def get_sources(self) -> List[Dict]:
        """Получить список источников"""
        return self.db.get_watch_sources()

    def _detect_platform(self, url: str) -> Optional[str]:
        """Определить платформу по URL"""
        if 'youtube.com' in url or 'youtu.be' in url:
            return 'YouTube'
        elif 'tiktok.com' in url:
            return 'TikTok'
        elif 'instagram.com' in url:
            return 'Instagram'
        return None

    def collect_snapshots(self) -> Dict:
        """
        Собрать свежие данные со всех источников
        Основной метод для периодического запуска
        """
        sources = self.db.get_watch_sources()
        results = {
            'collected': 0,
            'errors': 0,
            'sources_processed': 0
        }

        for source in sources:
            try:
                videos = self._fetch_source_videos(source)
                for video in videos:
                    video['source_url'] = source['url']
                    self.db.record_video_snapshot(video)
                    results['collected'] += 1
                results['sources_processed'] += 1
            except Exception as e:
                print(f"Error fetching {source['url']}: {e}")
                results['errors'] += 1

        return results

    def _fetch_source_videos(self, source: Dict) -> List[Dict]:
        """Получить видео с источника"""
        platform = source['platform']
        url = source['url']

        if platform == 'YouTube' and self.yt_parser:
            videos = self.yt_parser.get_channel_videos(url, max_videos=20)
            return videos if videos else []

        elif platform == 'TikTok' and self.tt_parser:
            videos = self.tt_parser.get_user_videos(url, max_videos=20)
            return videos if videos else []

        return []

    def calculate_velocity(self, video_url: str) -> Optional[Dict]:
        """
        Рассчитать velocity для видео

        Velocity = (views_now - views_prev) / hours_diff
        Acceleration = velocity_now / velocity_prev
        """
        history = self.db.get_video_history(video_url, limit=3)

        if len(history) < 2:
            return None

        current = history[0]
        previous = history[1]

        # Парсим временные метки
        try:
            current_time = datetime.fromisoformat(current['recorded_at'].replace('Z', '+00:00'))
            previous_time = datetime.fromisoformat(previous['recorded_at'].replace('Z', '+00:00'))
        except:
            current_time = datetime.now()
            previous_time = datetime.now() - timedelta(hours=3)

        hours_diff = max((current_time - previous_time).total_seconds() / 3600, 0.1)

        views_diff = current['views'] - previous['views']
        likes_diff = current['likes'] - previous['likes']

        velocity = views_diff / hours_diff
        likes_velocity = likes_diff / hours_diff

        # Acceleration (если есть 3+ записи)
        acceleration = 1.0
        if len(history) >= 3:
            older = history[2]
            try:
                older_time = datetime.fromisoformat(older['recorded_at'].replace('Z', '+00:00'))
            except:
                older_time = previous_time - timedelta(hours=3)

            older_hours = max((previous_time - older_time).total_seconds() / 3600, 0.1)
            older_velocity = (previous['views'] - older['views']) / older_hours

            if older_velocity > 0:
                acceleration = velocity / older_velocity

        return {
            'video_url': video_url,
            'current_views': current['views'],
            'previous_views': previous['views'],
            'views_gained': views_diff,
            'hours_diff': round(hours_diff, 2),
            'velocity': round(velocity, 1),  # views per hour
            'likes_velocity': round(likes_velocity, 1),
            'acceleration': round(acceleration, 2),
            'title': current['title'],
            'platform': current['platform'],
            'hashtags': json.loads(current['hashtags']) if current['hashtags'] else [],
            'sound_name': current.get('sound_name', ''),
            'publish_date': current.get('publish_date', '')
        }

    def analyze_trends(self) -> Dict:
        """
        Главный метод анализа трендов

        Returns:
            {
                'rising_videos': [...],  # Быстрорастущие видео
                'potential_trends': [...],  # Группы по хэштегам/звукам
                'top_velocity': [...],  # Топ по скорости
                'small_account_gems': [...]  # Находки на малых аккаунтах
            }
        """
        snapshots = self.db.get_latest_snapshots()

        # Рассчитываем velocity для всех видео
        velocities = []
        for snap in snapshots:
            vel = self.calculate_velocity(snap['video_url'])
            if vel and vel['velocity'] > 0:
                velocities.append(vel)

        if not velocities:
            return {
                'rising_videos': [],
                'potential_trends': [],
                'top_velocity': [],
                'small_account_gems': [],
                'stats': self.db.get_stats()
            }

        # Средняя velocity
        avg_velocity = sum(v['velocity'] for v in velocities) / len(velocities)

        # Rising videos (velocity > 2x average OR acceleration > 2)
        rising = [v for v in velocities if v['velocity'] > avg_velocity * 2 or v['acceleration'] > 2]
        rising.sort(key=lambda x: x['velocity'], reverse=True)

        # Top velocity
        top_velocity = sorted(velocities, key=lambda x: x['velocity'], reverse=True)[:10]

        # Группировка по хэштегам
        hashtag_groups = defaultdict(list)
        for v in velocities:
            for tag in v.get('hashtags', []):
                if tag and v['velocity'] > avg_velocity:
                    hashtag_groups[tag.lower()].append(v)

        # Потенциальные тренды (хэштеги с 2+ видео)
        potential_trends = []
        for tag, videos in hashtag_groups.items():
            if len(videos) >= 2:
                avg_vel = sum(v['velocity'] for v in videos) / len(videos)
                potential_trends.append({
                    'type': 'hashtag',
                    'key': tag,
                    'videos_count': len(videos),
                    'avg_velocity': round(avg_vel, 1),
                    'videos': videos[:5],  # Топ 5
                    'score': round(avg_vel * len(videos), 1)
                })

        # Группировка по звукам (для TikTok)
        sound_groups = defaultdict(list)
        for v in velocities:
            sound = v.get('sound_name', '')
            if sound and v['velocity'] > avg_velocity:
                sound_groups[sound.lower()].append(v)

        for sound, videos in sound_groups.items():
            if len(videos) >= 2:
                avg_vel = sum(v['velocity'] for v in videos) / len(videos)
                potential_trends.append({
                    'type': 'sound',
                    'key': sound,
                    'videos_count': len(videos),
                    'avg_velocity': round(avg_vel, 1),
                    'videos': videos[:5],
                    'score': round(avg_vel * len(videos), 1)
                })

        potential_trends.sort(key=lambda x: x['score'], reverse=True)

        # Small account gems (высокая velocity на аккаунтах с малым числом просмотров)
        # Используем acceleration как индикатор
        small_gems = [v for v in velocities if v['acceleration'] > 3 and v['current_views'] < 100000]
        small_gems.sort(key=lambda x: x['acceleration'], reverse=True)

        # Сохраняем обнаруженные тренды в БД
        for trend in potential_trends[:5]:
            self.db.save_trend(
                trend_type=trend['type'],
                trend_key=trend['key'],
                video_urls=[v['video_url'] for v in trend['videos']],
                description=f"{trend['videos_count']} videos, avg velocity: {trend['avg_velocity']}/h",
                score=trend['score']
            )

        return {
            'rising_videos': rising[:20],
            'potential_trends': potential_trends[:10],
            'top_velocity': top_velocity,
            'small_account_gems': small_gems[:10],
            'avg_velocity': round(avg_velocity, 1),
            'total_tracked': len(velocities),
            'stats': self.db.get_stats()
        }

    def get_video_detail(self, video_url: str) -> Optional[Dict]:
        """Получить детальную информацию о видео с историей"""
        history = self.db.get_video_history(video_url, limit=20)
        if not history:
            return None

        velocity = self.calculate_velocity(video_url)

        # Построить график роста
        growth_data = []
        for h in reversed(history):
            growth_data.append({
                'time': h['recorded_at'],
                'views': h['views'],
                'likes': h['likes']
            })

        return {
            'current': history[0],
            'velocity': velocity,
            'history': history,
            'growth_chart': growth_data
        }

    def get_trending_report(self) -> str:
        """Генерация текстового отчёта о трендах"""
        analysis = self.analyze_trends()

        report = []
        report.append("=" * 50)
        report.append("TREND WATCH REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        report.append("=" * 50)

        report.append(f"\nTracked videos: {analysis['total_tracked']}")
        report.append(f"Average velocity: {analysis['avg_velocity']} views/hour")

        if analysis['rising_videos']:
            report.append("\n--- RISING VIDEOS ---")
            for v in analysis['rising_videos'][:5]:
                report.append(f"  {v['title'][:40]}...")
                report.append(f"    Velocity: {v['velocity']}/h | Acceleration: {v['acceleration']}x")

        if analysis['potential_trends']:
            report.append("\n--- POTENTIAL TRENDS ---")
            for t in analysis['potential_trends'][:5]:
                report.append(f"  #{t['key']} ({t['type']})")
                report.append(f"    {t['videos_count']} videos | Avg velocity: {t['avg_velocity']}/h")

        if analysis['small_account_gems']:
            report.append("\n--- SMALL ACCOUNT GEMS ---")
            for v in analysis['small_account_gems'][:3]:
                report.append(f"  {v['title'][:40]}...")
                report.append(f"    Acceleration: {v['acceleration']}x | Views: {v['current_views']}")

        report.append("\n" + "=" * 50)

        return "\n".join(report)


# CLI для тестирования
if __name__ == '__main__':
    watcher = TrendWatcher()

    print("Trend Watcher CLI")
    print("-" * 30)

    # Показать статистику
    stats = watcher.db.get_stats()
    print(f"Sources: {stats['sources']}")
    print(f"Videos tracked: {stats['videos_tracked']}")
    print(f"Snapshots: {stats['total_snapshots']}")

    # Если есть данные, показать анализ
    if stats['videos_tracked'] > 0:
        print("\nAnalyzing trends...")
        print(watcher.get_trending_report())
