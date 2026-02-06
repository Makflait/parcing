"""
Парсер для TikTok v5.0
Использует yt-dlp для надёжного получения данных
Оптимизирован для скорости
"""
import re
from typing import Optional, Dict, List
from datetime import datetime

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False
    print("ВНИМАНИЕ: yt-dlp не установлен. Установите: pip install yt-dlp")


class TikTokParser:
    """Парсер для получения данных с TikTok через yt-dlp"""

    def __init__(self, use_selenium=True):
        self.use_selenium = use_selenium

    def get_all_videos(self, profile_url: str, max_videos: int = 50) -> List[Dict]:
        """
        Получает все видео с профиля TikTok через yt-dlp
        Оптимизированная версия
        """
        if not YT_DLP_AVAILABLE:
            print("TikTok: yt-dlp не установлен")
            return []

        videos = []

        try:
            # Извлекаем username из URL
            username_match = re.search(r'@([^/\?]+)', profile_url)
            username = username_match.group(1) if username_match else ''

            if not username:
                print("TikTok: не удалось определить username")
                return []

            # Оптимизированные настройки для быстрого извлечения
            list_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': 'in_playlist',
                'ignoreerrors': True,
                'playlistend': max_videos,
                'skip_download': True,
                'no_check_certificate': True,
                'socket_timeout': 10,
            }

            print(f"TikTok: получаем видео @{username}...")

            with yt_dlp.YoutubeDL(list_opts) as ydl:
                result = ydl.extract_info(profile_url, download=False)

                if not result:
                    print("TikTok: не удалось получить данные")
                    return []

                entries = result.get('entries', [])
                valid_entries = [e for e in entries if e]

                if not valid_entries:
                    print("TikTok: видео не найдены")
                    return []

                print(f"TikTok: найдено {len(valid_entries)} видео")

                # Обрабатываем каждое видео
                for entry in valid_entries[:max_videos]:
                    video_data = self._extract_video_from_entry(entry, username)
                    if video_data:
                        videos.append(video_data)

            return videos

        except Exception as e:
            print(f"TikTok ошибка: {e}")
            return []

    def _extract_video_from_entry(self, entry: dict, username: str) -> Optional[Dict]:
        """Извлекает данные видео из entry"""
        try:
            video_id = entry.get('id', '')
            if not video_id:
                return None

            title = entry.get('title', '') or entry.get('description', '') or 'Без названия'
            views = entry.get('view_count', 0) or 0
            likes = entry.get('like_count', 0) or 0
            comments = entry.get('comment_count', 0) or 0
            shares = entry.get('repost_count', 0) or 0

            # Дата публикации
            timestamp = entry.get('timestamp', 0)
            if timestamp:
                publish_date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            else:
                # Извлекаем из video ID (первые 32 бита - timestamp)
                try:
                    ts = int(video_id) >> 32
                    if ts > 1577836800:  # после 2020
                        publish_date = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                    else:
                        publish_date = datetime.now().strftime('%Y-%m-%d')
                except:
                    publish_date = datetime.now().strftime('%Y-%m-%d')

            # URL видео
            url = entry.get('url', '') or f"https://www.tiktok.com/@{username}/video/{video_id}"

            return {
                'title': title[:200] if title else 'Без названия',
                'url': url,
                'views': views,
                'likes': likes,
                'comments': comments,
                'shares': shares,
                'publish_date': publish_date,
                'watch_time': 'N/A'
            }
        except Exception as e:
            return None

    def get_latest_video(self, profile_url: str) -> Optional[Dict]:
        """Получает последний видеоролик (для совместимости)"""
        videos = self.get_all_videos(profile_url, max_videos=1)
        return videos[0] if videos else None

    def get_user_videos(self, profile_url: str, max_videos: int = 50) -> List[Dict]:
        return self.get_all_videos(profile_url, max_videos=max_videos)

    def close(self):
        """Закрывает ресурсы (для совместимости)"""
        return
