"""
Парсер для YouTube v5.0
Использует yt-dlp для надёжного получения данных
Оптимизирован для скорости - параллельная обработка
"""
import re
from typing import Optional, Dict, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False
    print("ВНИМАНИЕ: yt-dlp не установлен. Установите: pip install yt-dlp")


class YouTubeParser:
    """Парсер для получения данных с YouTube через yt-dlp"""

    def __init__(self, use_selenium=True):
        # Кэш для ускорения повторных запросов
        self._cache = {}

    def get_all_videos(self, channel_url: str, max_videos: int = 30) -> List[Dict]:
        """
        Получает все видео с канала YouTube (включая Shorts)
        Оптимизированная версия - минимум запросов
        """
        if not YT_DLP_AVAILABLE:
            print("YouTube: yt-dlp не установлен")
            return []

        videos = []

        try:
            base_url = channel_url.rstrip('/')

            # Используем /videos напрямую - самый надёжный таб
            videos_url = base_url + '/videos'

            # Оптимизированные настройки для быстрого извлечения
            list_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',  # Быстрее чем просто True
                'ignoreerrors': True,
                'playlistend': max_videos,
                'skip_download': True,
                'no_check_certificate': True,
                'socket_timeout': 10,
            }

            print(f"YouTube: получаем видео с {videos_url}...")

            result = None
            try:
                with yt_dlp.YoutubeDL(list_opts) as ydl:
                    result = ydl.extract_info(videos_url, download=False)
            except Exception as e:
                # Fallback на базовый URL
                print(f"YouTube: пробуем базовый URL...")
                try:
                    with yt_dlp.YoutubeDL(list_opts) as ydl:
                        result = ydl.extract_info(base_url, download=False)
                except:
                    pass

            if not result:
                print("YouTube: не удалось получить данные канала")
                return []

            entries = result.get('entries', [])
            valid_entries = [e for e in entries if e]

            if not valid_entries:
                if result.get('id') and result.get('title'):
                    video_data = self._extract_video_from_result(result)
                    if video_data:
                        return [video_data]
                print("YouTube: видео не найдены на канале")
                return []

            print(f"YouTube: найдено {len(valid_entries)} видео")

            # Быстрое извлечение из entries
            for entry in valid_entries[:max_videos]:
                video_id = entry.get('id', '')
                if not video_id:
                    url = entry.get('url', '')
                    match = re.search(r'[?&]v=([^&]+)', url)
                    if match:
                        video_id = match.group(1)
                    else:
                        # Для Shorts формат /shorts/VIDEO_ID
                        match = re.search(r'/shorts/([^/?]+)', url)
                        if match:
                            video_id = match.group(1)

                if not video_id:
                    continue

                video_data = self._extract_video_from_entry(entry, video_id)
                if video_data:
                    videos.append(video_data)

            # Если нет просмотров - параллельно получаем детали
            needs_details = [v for v in videos if v.get('views', 0) == 0]
            if needs_details and len(needs_details) == len(videos):
                print("YouTube: получаем детальную информацию (параллельно)...")
                videos = self._get_videos_details_parallel(videos[:max_videos])

            return videos

        except Exception as e:
            print(f"YouTube ошибка: {e}")
            return []

    def _get_videos_details_parallel(self, videos: List[Dict], max_workers: int = 5) -> List[Dict]:
        """Параллельно получает детали для списка видео"""
        detailed_videos = []

        def fetch_details(video):
            video_id = video['url'].split('v=')[-1]
            detailed = self._get_video_details(video_id)
            return detailed if detailed else video

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_details, v): i for i, v in enumerate(videos)}
            results = [None] * len(videos)

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except:
                    results[idx] = videos[idx]

        return [r for r in results if r]

    def _extract_video_from_entry(self, entry: dict, video_id: str) -> Optional[Dict]:
        """Извлекает данные видео из entry без дополнительного запроса"""
        try:
            title = entry.get('title', 'Без названия')
            views = entry.get('view_count', 0) or 0
            likes = entry.get('like_count', 0) or 0

            # Дата публикации
            upload_date = entry.get('upload_date', '')
            if upload_date and len(upload_date) == 8:
                publish_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
            else:
                publish_date = datetime.now().strftime('%Y-%m-%d')

            return {
                'title': title[:200] if title else 'Без названия',
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'views': views,
                'likes': likes,
                'comments': 0,
                'shares': 0,
                'publish_date': publish_date,
                'watch_time': 'N/A'
            }
        except:
            return None

    def _extract_video_from_result(self, result: dict) -> Optional[Dict]:
        """Извлекает данные из полного результата"""
        try:
            video_id = result.get('id', '')
            title = result.get('title', 'Без названия')
            views = result.get('view_count', 0) or 0
            likes = result.get('like_count', 0) or 0
            comments = result.get('comment_count', 0) or 0

            upload_date = result.get('upload_date', '')
            if upload_date and len(upload_date) == 8:
                publish_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
            else:
                publish_date = datetime.now().strftime('%Y-%m-%d')

            return {
                'title': title[:200] if title else 'Без названия',
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'views': views,
                'likes': likes,
                'comments': comments,
                'shares': 0,
                'publish_date': publish_date,
                'watch_time': 'N/A'
            }
        except:
            return None

    def _get_video_details(self, video_id: str) -> Optional[Dict]:
        """Получает детальную информацию о видео"""
        try:
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            detail_opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'skip_download': True,
            }

            with yt_dlp.YoutubeDL(detail_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

                if not info:
                    return None

                return self._extract_video_from_result(info)

        except Exception as e:
            return None

    def get_latest_video(self, channel_url: str) -> Optional[Dict]:
        """Получает последний видеоролик"""
        videos = self.get_all_videos(channel_url, max_videos=1)
        return videos[0] if videos else None

    def close(self):
        """Закрывает ресурсы"""
        pass
