"""
Trend Discovery v4.0
Реальный алгоритмический анализ трендов с прогрессом
"""
import subprocess
import json
import re
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Generator
from collections import defaultdict
import time


class TrendDiscovery:
    """
    Реальный алгоритмический анализ трендов

    Этапы анализа:
    1. Сбор данных с популярных каналов в Tier 1 странах
    2. Получение полных метрик каждого видео
    3. Расчёт engagement rate и сравнение с бенчмарками
    4. Анализ velocity (скорость набора просмотров)
    5. Группировка по хэштегам и темам
    6. Ранжирование по вирусному потенциалу
    """

    # Tier 1 страны
    TIER1_COUNTRIES = ['US', 'GB', 'CA', 'AU', 'DE']

    # Бенчмарки engagement rate по платформам (средние показатели)
    BENCHMARKS = {
        'YouTube': {
            'avg_engagement': 0.035,  # 3.5% - средний engagement
            'good_engagement': 0.05,  # 5%+ - хороший
            'viral_engagement': 0.08, # 8%+ - вирусный потенциал
        },
        'YouTube_Shorts': {
            'avg_engagement': 0.05,
            'good_engagement': 0.08,
            'viral_engagement': 0.12,
        },
        'TikTok': {
            'avg_engagement': 0.06,
            'good_engagement': 0.10,
            'viral_engagement': 0.15,
        }
    }

    # Популярные каналы для мониторинга трендов (разные ниши)
    TREND_CHANNELS = {
        'entertainment': [
            'https://www.youtube.com/@MrBeast',
            'https://www.youtube.com/@PrestonPlayz',
            'https://www.youtube.com/@Sidemen',
        ],
        'shorts_creators': [
            'https://www.youtube.com/@IShowSpeed',
            'https://www.youtube.com/@BenAzelart',
        ],
        'viral_compilations': [
            'https://www.youtube.com/@FailArmy',
            'https://www.youtube.com/@DailyDoseOfInternet',
        ]
    }

    def __init__(self):
        self.progress_callback = None
        self.current_step = 0
        self.total_steps = 0

    def set_progress_callback(self, callback):
        """Установить callback для отслеживания прогресса"""
        self.progress_callback = callback

    def _report_progress(self, step: int, total: int, message: str, details: str = ""):
        """Отправить прогресс"""
        if self.progress_callback:
            self.progress_callback({
                'step': step,
                'total': total,
                'percent': round(step / total * 100),
                'message': message,
                'details': details
            })
        print(f"[{step}/{total}] {message} {details}")

    def _run_ytdlp(self, args: List[str], timeout: int = 120) -> str:
        """Запуск yt-dlp"""
        try:
            import sys
            cmd = [sys.executable, '-m', 'yt_dlp', '--no-warnings', '--ignore-errors'] + args

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='replace'
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            return ""
        except Exception as e:
            print(f"yt-dlp error: {e}")
            return ""

    def get_video_full_info(self, url: str) -> Optional[Dict]:
        """Получить ПОЛНУЮ информацию о видео (не flat-playlist)"""
        output = self._run_ytdlp([
            '--dump-json',
            '--no-playlist',
            url
        ], timeout=30)

        if output.strip():
            try:
                return json.loads(output.strip().split('\n')[0])
            except:
                pass
        return None

    def get_channel_recent_videos(self, channel_url: str, max_videos: int = 10) -> List[Dict]:
        """Получить последние видео с канала"""
        videos = []

        output = self._run_ytdlp([
            '--flat-playlist',
            '--dump-json',
            '--playlist-end', str(max_videos),
            f'{channel_url}/videos'
        ], timeout=60)

        for line in output.strip().split('\n'):
            if line:
                try:
                    data = json.loads(line)
                    if data.get('id'):
                        videos.append({
                            'id': data.get('id'),
                            'url': f"https://www.youtube.com/watch?v={data.get('id')}",
                            'title': data.get('title', ''),
                        })
                except:
                    continue

        return videos

    def search_trending_videos(self, query: str, country: str = 'US', max_results: int = 10) -> List[Dict]:
        """Поиск с получением полных метрик"""
        videos = []

        # Сначала получаем список видео
        output = self._run_ytdlp([
            '--flat-playlist',
            '--dump-json',
            '--geo-bypass-country', country,
            f'ytsearch{max_results}:{query}'
        ], timeout=90)

        video_ids = []
        for line in output.strip().split('\n'):
            if line:
                try:
                    data = json.loads(line)
                    if data.get('id'):
                        video_ids.append(data['id'])
                except:
                    continue

        # Получаем полные метрики для каждого видео
        for vid in video_ids[:max_results]:
            url = f"https://www.youtube.com/watch?v={vid}"
            full_info = self.get_video_full_info(url)
            if full_info:
                parsed = self._parse_full_video(full_info)
                if parsed:
                    parsed['search_query'] = query
                    parsed['country'] = country
                    videos.append(parsed)

        return videos

    def _parse_full_video(self, data: Dict) -> Optional[Dict]:
        """Парсинг полной информации о видео с расчётом метрик"""
        try:
            video_id = data.get('id', '')
            if not video_id:
                return None

            title = data.get('title', '')
            if not title:
                return None

            views = data.get('view_count', 0) or 0
            likes = data.get('like_count', 0) or 0
            comments = data.get('comment_count', 0) or 0
            duration = data.get('duration', 0) or 0

            # Данные канала
            channel_name = data.get('uploader', '') or data.get('channel', '')
            channel_subs = data.get('channel_follower_count', 0) or 0

            # Дата публикации
            upload_date = data.get('upload_date', '')
            hours_since_upload = self._calculate_hours_since_upload(upload_date)

            # Определяем тип контента
            is_short = duration < 65 if duration else False
            platform_type = 'YouTube_Shorts' if is_short else 'YouTube'

            # Расчёт engagement rate
            engagement_rate = (likes + comments) / views if views > 0 else 0

            # Сравнение с бенчмарками
            benchmarks = self.BENCHMARKS.get(platform_type, self.BENCHMARKS['YouTube'])
            engagement_vs_avg = engagement_rate / benchmarks['avg_engagement'] if benchmarks['avg_engagement'] > 0 else 1

            # Velocity (просмотры в час)
            velocity = views / max(hours_since_upload, 1)

            # Views per subscriber (если известно кол-во подписчиков)
            views_per_sub = views / channel_subs if channel_subs > 0 else 0

            # Viral Score - комплексная оценка
            viral_score = self._calculate_viral_score_v2(
                engagement_rate=engagement_rate,
                engagement_vs_avg=engagement_vs_avg,
                velocity=velocity,
                views=views,
                views_per_sub=views_per_sub,
                hours_since_upload=hours_since_upload,
                benchmarks=benchmarks
            )

            # Определение потенциала
            potential = self._determine_potential_v2(viral_score, engagement_rate, benchmarks)

            # Хэштеги
            hashtags = self._extract_hashtags(title + ' ' + data.get('description', '')[:500])

            # Категория/теги
            categories = data.get('categories', [])
            tags = data.get('tags', [])[:10] if data.get('tags') else []

            return {
                'platform': 'YouTube',
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'title': title[:200],
                'views': views,
                'likes': likes,
                'comments': comments,
                'shares': 0,
                'duration': duration,
                'upload_date': upload_date,
                'hours_since_upload': round(hours_since_upload, 1),
                'uploader': channel_name,
                'uploader_url': data.get('uploader_url', ''),
                'channel_subs': channel_subs,
                'hashtags': hashtags,
                'tags': tags,
                'categories': categories,
                'is_short': is_short,
                # Расчётные метрики
                'engagement_rate': round(engagement_rate * 100, 2),
                'engagement_vs_avg': round(engagement_vs_avg, 2),
                'velocity': round(velocity, 1),
                'views_per_sub': round(views_per_sub, 2),
                'viral_score': round(viral_score, 1),
                'potential': potential,
                'source': 'algorithmic_analysis'
            }
        except Exception as e:
            print(f"Parse error: {e}")
            return None

    def _calculate_hours_since_upload(self, upload_date: str) -> float:
        """Рассчитать часы с момента загрузки"""
        if not upload_date:
            return 168
        try:
            if len(upload_date) == 8:
                dt = datetime.strptime(upload_date, '%Y%m%d')
            else:
                dt = datetime.fromisoformat(upload_date.replace('Z', '+00:00'))
            diff = datetime.now() - dt.replace(tzinfo=None)
            return max(diff.total_seconds() / 3600, 1)
        except:
            return 168

    def _calculate_viral_score_v2(self, engagement_rate: float, engagement_vs_avg: float,
                                   velocity: float, views: int, views_per_sub: float,
                                   hours_since_upload: float, benchmarks: dict) -> float:
        """
        Улучшенный расчёт вирусного потенциала

        Факторы:
        1. Engagement выше среднего (40 баллов макс)
        2. Velocity - скорость набора просмотров (25 баллов макс)
        3. Views per subscriber - охват аудитории (15 баллов макс)
        4. Свежесть контента (10 баллов макс)
        5. Абсолютные цифры (10 баллов макс)
        """
        score = 0

        # 1. Engagement vs average (0-40 баллов)
        if engagement_vs_avg >= 3:
            score += 40  # 3x выше среднего = максимум
        elif engagement_vs_avg >= 2:
            score += 30
        elif engagement_vs_avg >= 1.5:
            score += 20
        elif engagement_vs_avg >= 1:
            score += 10

        # 2. Velocity score (0-25 баллов)
        # Нормализуем: 10K просмотров/час = отлично
        velocity_normalized = min(velocity / 10000, 1) * 25
        score += velocity_normalized

        # 3. Views per subscriber (0-15 баллов)
        # Если views > subscribers, это вирусный потенциал
        if views_per_sub >= 2:
            score += 15
        elif views_per_sub >= 1:
            score += 10
        elif views_per_sub >= 0.5:
            score += 5

        # 4. Freshness bonus (0-10 баллов)
        if hours_since_upload < 24:
            score += 10
        elif hours_since_upload < 48:
            score += 7
        elif hours_since_upload < 168:
            score += 3

        # 5. Scale bonus (0-10 баллов)
        if views >= 1000000:
            score += 10
        elif views >= 100000:
            score += 7
        elif views >= 10000:
            score += 3

        return min(score, 100)

    def _determine_potential_v2(self, viral_score: float, engagement_rate: float, benchmarks: dict) -> str:
        """Определить потенциал на основе score и engagement"""
        if viral_score >= 70 or engagement_rate >= benchmarks['viral_engagement']:
            return 'viral'
        elif viral_score >= 50 or engagement_rate >= benchmarks['good_engagement']:
            return 'high'
        elif viral_score >= 30:
            return 'medium'
        elif engagement_rate >= benchmarks['avg_engagement']:
            return 'growing'
        else:
            return 'low'

    def _extract_hashtags(self, text: str) -> List[str]:
        """Извлечь хэштеги"""
        if not text:
            return []
        hashtags = re.findall(r'#(\w+)', text)
        return list(set(hashtags))[:15]

    def discover_with_progress(self, max_per_source: int = 5) -> Generator[Dict, None, Dict]:
        """
        Поиск трендов с отчётом о прогрессе (generator)

        Yields прогресс, Returns итоговый результат
        """
        all_videos = []
        trending_topics = defaultdict(lambda: {'count': 0, 'total_views': 0, 'total_engagement': 0, 'videos': []})
        errors = []

        # Этапы анализа
        stages = [
            ('search_viral', 'Поиск вирусного контента', ['viral video 2026', 'going viral']),
            ('search_trending', 'Анализ трендов', ['trending now 2026', 'blowing up']),
            ('search_shorts', 'Анализ Shorts', ['shorts viral 2026', '#shorts trending']),
            ('channels_entertainment', 'Анализ развлекательных каналов', self.TREND_CHANNELS.get('entertainment', [])),
            ('channels_viral', 'Анализ вирусных каналов', self.TREND_CHANNELS.get('viral_compilations', [])),
            ('analysis', 'Финальный анализ и ранжирование', []),
        ]

        total_steps = len(stages)
        current_step = 0

        for stage_id, stage_name, stage_data in stages:
            current_step += 1

            yield {
                'type': 'progress',
                'step': current_step,
                'total': total_steps,
                'percent': round(current_step / total_steps * 100),
                'stage': stage_id,
                'message': stage_name,
                'videos_found': len(all_videos)
            }

            try:
                if stage_id.startswith('search_'):
                    # Поиск по запросам
                    for query in stage_data:
                        for country in self.TIER1_COUNTRIES[:2]:  # US и UK
                            videos = self.search_trending_videos(query, country, max_per_source)
                            for v in videos:
                                v['category'] = stage_id.replace('search_', '')
                                all_videos.append(v)
                                # Обновляем trending topics
                                for tag in v.get('hashtags', []):
                                    tag_lower = tag.lower()
                                    trending_topics[tag_lower]['count'] += 1
                                    trending_topics[tag_lower]['total_views'] += v.get('views', 0)
                                    trending_topics[tag_lower]['total_engagement'] += v.get('engagement_rate', 0)
                                    if len(trending_topics[tag_lower]['videos']) < 5:
                                        trending_topics[tag_lower]['videos'].append(v)

                elif stage_id.startswith('channels_'):
                    # Анализ каналов
                    for channel_url in stage_data[:2]:  # Макс 2 канала на категорию
                        recent = self.get_channel_recent_videos(channel_url, max_videos=3)
                        for vid_info in recent:
                            full_info = self.get_video_full_info(vid_info['url'])
                            if full_info:
                                parsed = self._parse_full_video(full_info)
                                if parsed:
                                    parsed['category'] = stage_id.replace('channels_', '')
                                    all_videos.append(parsed)
                                    # Обновляем trending topics
                                    for tag in parsed.get('hashtags', []):
                                        tag_lower = tag.lower()
                                        trending_topics[tag_lower]['count'] += 1
                                        trending_topics[tag_lower]['total_views'] += parsed.get('views', 0)
                                        trending_topics[tag_lower]['total_engagement'] += parsed.get('engagement_rate', 0)
                                        if len(trending_topics[tag_lower]['videos']) < 5:
                                            trending_topics[tag_lower]['videos'].append(parsed)

                elif stage_id == 'analysis':
                    # Финальный анализ
                    pass

            except Exception as e:
                errors.append(f"{stage_name}: {str(e)}")

        # Удаляем дубликаты
        seen_urls = set()
        unique_videos = []
        for v in all_videos:
            if v.get('url') and v['url'] not in seen_urls:
                seen_urls.add(v['url'])
                unique_videos.append(v)

        # Сортируем по viral_score
        unique_videos.sort(key=lambda x: x.get('viral_score', 0), reverse=True)

        # Формируем trending topics
        topics_list = []
        for tag, data in trending_topics.items():
            if data['count'] >= 2:  # Минимум 2 видео с тегом
                avg_engagement = data['total_engagement'] / data['count'] if data['count'] > 0 else 0
                topics_list.append({
                    'hashtag': tag,
                    'video_count': data['count'],
                    'total_views': data['total_views'],
                    'avg_engagement': round(avg_engagement, 2),
                    'videos': data['videos'][:3]
                })

        topics_list.sort(key=lambda x: x['total_views'], reverse=True)

        # Вирусные кандидаты
        viral_candidates = [v for v in unique_videos if v.get('potential') in ['viral', 'high']]

        # Финальный результат
        result = {
            'type': 'complete',
            'videos': unique_videos,
            'youtube_trending': [v for v in unique_videos if not v.get('is_short')],
            'youtube_shorts': [v for v in unique_videos if v.get('is_short')],
            'tiktok_trending': [],
            'viral_candidates': viral_candidates[:20],
            'trending_topics': topics_list[:15],
            'total': len(unique_videos),
            'viral_count': len(viral_candidates),
            'discovered_at': datetime.now().isoformat(),
            'errors': errors
        }

        yield {
            'type': 'progress',
            'step': total_steps,
            'total': total_steps,
            'percent': 100,
            'stage': 'complete',
            'message': 'Анализ завершён',
            'videos_found': len(unique_videos)
        }

        return result

    def discover_all(self, max_per_source: int = 5) -> Dict:
        """Синхронная обёртка для совместимости"""
        result = None
        for item in self.discover_with_progress(max_per_source):
            if item.get('type') == 'complete':
                result = item
            elif 'videos' in item and 'total' in item:
                result = item

        # Если generator вернул результат через return
        if result is None:
            result = {
                'videos': [],
                'youtube_trending': [],
                'youtube_shorts': [],
                'tiktok_trending': [],
                'viral_candidates': [],
                'trending_topics': [],
                'total': 0,
                'errors': ['No results']
            }

        return result


# Тест
if __name__ == '__main__':
    print("Testing TrendDiscovery v4.0...")
    discovery = TrendDiscovery()

    print("\nПоиск трендов с прогрессом:")
    for progress in discovery.discover_with_progress(max_per_source=3):
        if progress.get('type') == 'progress':
            print(f"  [{progress['percent']}%] {progress['message']} - найдено {progress['videos_found']} видео")
        else:
            print(f"\nРезультат: {progress.get('total', 0)} видео")
            print(f"Вирусных: {progress.get('viral_count', 0)}")
            print(f"Тем: {len(progress.get('trending_topics', []))}")
