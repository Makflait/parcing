"""
Парсер для Instagram v4.0
Использует instaloader (основной) и yt-dlp (fallback)
Поддержка авторизации для доступа к просмотрам
"""
import os
import re
from typing import Optional, Dict, List
from datetime import datetime

try:
    import instaloader
    INSTALOADER_AVAILABLE = True
except ImportError:
    INSTALOADER_AVAILABLE = False

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False


class InstagramParser:
    """Парсер для получения данных с Instagram"""

    def __init__(self, use_selenium=False):
        self._loader = None
        self._logged_in = False
        if INSTALOADER_AVAILABLE:
            self._loader = instaloader.Instaloader(
                download_pictures=False,
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                quiet=True,
            )
            self._try_login()

    def _try_login(self):
        """Авторизация в Instagram через env переменные"""
        ig_user = os.getenv('INSTAGRAM_USERNAME', '').strip()
        ig_pass = os.getenv('INSTAGRAM_PASSWORD', '').strip()

        if not ig_user or not ig_pass or not self._loader:
            return

        # Пробуем загрузить сохранённую сессию
        session_dir = os.getenv('INSTAGRAM_SESSION_DIR', '/app/data')
        session_file = os.path.join(session_dir, f'ig_session_{ig_user}')

        try:
            if os.path.exists(session_file):
                self._loader.load_session_from_file(ig_user, session_file)
                # Проверяем что сессия жива
                try:
                    self._loader.test_login()
                    self._logged_in = True
                    print(f"Instagram: восстановлена сессия @{ig_user}")
                    return
                except Exception:
                    print("Instagram: сессия истекла, логинимся заново")
        except Exception:
            pass

        # Логинимся с нуля
        try:
            self._loader.login(ig_user, ig_pass)
            self._logged_in = True
            print(f"Instagram: авторизация @{ig_user} успешна")

            # Сохраняем сессию
            try:
                os.makedirs(session_dir, exist_ok=True)
                self._loader.save_session_to_file(session_file)
            except Exception:
                pass
        except instaloader.exceptions.TwoFactorAuthRequiredException:
            print("Instagram: требуется 2FA — отключите или используйте app password")
        except instaloader.exceptions.BadCredentialsException:
            print("Instagram: неверный логин/пароль")
        except instaloader.exceptions.ConnectionException as e:
            print(f"Instagram: ошибка подключения при логине — {e}")
        except Exception as e:
            print(f"Instagram: ошибка авторизации — {e}")

    def get_all_videos(self, profile_url: str, max_videos: int = 30) -> List[Dict]:
        """Получает видео/посты с профиля Instagram"""
        username = self._extract_username(profile_url)
        if not username:
            print("Instagram: не удалось определить username")
            return []

        # Основной метод: instaloader
        if INSTALOADER_AVAILABLE and self._loader:
            videos = self._parse_with_instaloader(username, max_videos)
            if videos:
                return videos

        # Fallback: yt-dlp
        if YT_DLP_AVAILABLE:
            videos = self._parse_with_ytdlp(username, max_videos)
            if videos:
                return videos

        print(f"Instagram: не удалось получить данные для @{username}")
        return []

    def _parse_with_instaloader(self, username: str, max_videos: int) -> List[Dict]:
        """Парсинг через instaloader"""
        videos = []
        try:
            print(f"Instagram: получаем данные @{username} (instaloader)...")
            profile = instaloader.Profile.from_username(self._loader.context, username)

            posts = profile.get_posts()
            count = 0
            for post in posts:
                if count >= max_videos:
                    break

                try:
                    views = 0
                    if post.is_video:
                        views = post.video_view_count or 0
                    # Для авторизованных — пробуем получить engagement-метрики
                    if views == 0 and self._logged_in:
                        try:
                            views = post.video_view_count or 0
                        except Exception:
                            pass

                    caption = post.caption or ''
                    title = caption[:200] if caption else f'Post by @{username}'

                    publish_date = post.date_utc.strftime('%Y-%m-%d') if post.date_utc else datetime.now().strftime('%Y-%m-%d')

                    # Хэштеги
                    hashtags = list(post.caption_hashtags) if post.caption_hashtags else []

                    videos.append({
                        'title': title,
                        'url': f'https://www.instagram.com/p/{post.shortcode}/',
                        'views': views,
                        'likes': post.likes or 0,
                        'comments': post.comments or 0,
                        'shares': 0,
                        'publish_date': publish_date,
                        'channel': username,
                        'uploader': username,
                        'hashtags': hashtags,
                    })
                    count += 1
                except Exception:
                    count += 1
                    continue

            if videos:
                print(f"Instagram: получено {len(videos)} постов")
            return videos

        except instaloader.exceptions.ProfileNotExistsException:
            print(f"Instagram: профиль @{username} не найден")
            return []
        except instaloader.exceptions.ConnectionException as e:
            print(f"Instagram: ошибка соединения - {e}")
            return []
        except Exception as e:
            print(f"Instagram instaloader ошибка: {e}")
            return []

    def _parse_with_ytdlp(self, username: str, max_videos: int) -> List[Dict]:
        """Fallback парсинг через yt-dlp"""
        videos = []
        clean_url = f"https://www.instagram.com/{username}/"

        list_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'ignoreerrors': True,
            'playlistend': max_videos,
            'skip_download': True,
            'no_check_certificate': True,
            'socket_timeout': 15,
        }

        print(f"Instagram: получаем данные @{username} (yt-dlp)...")

        try:
            with yt_dlp.YoutubeDL(list_opts) as ydl:
                result = ydl.extract_info(clean_url, download=False)

            if result and result.get('entries'):
                entries = [e for e in result.get('entries', []) if e]
                for entry in entries[:max_videos]:
                    video_data = self._extract_video_from_entry(entry, username)
                    if video_data:
                        videos.append(video_data)

                if videos:
                    print(f"Instagram: получено {len(videos)} постов (yt-dlp)")
        except Exception as e:
            print(f"Instagram yt-dlp ошибка: {e}")

        return videos

    def _extract_username(self, profile_url: str) -> str:
        """Извлекает username из URL"""
        profile_url = profile_url.strip().rstrip('/')
        profile_url = profile_url.split('?')[0]

        patterns = [
            r'instagram\.com/([A-Za-z0-9_.]+)',
            r'^@?([A-Za-z0-9_.]+)$',
        ]

        for pattern in patterns:
            match = re.search(pattern, profile_url)
            if match:
                username = match.group(1)
                if username not in ('p', 'reel', 'reels', 'stories', 'explore', 'accounts'):
                    return username

        return ''

    def _extract_video_from_entry(self, entry: dict, username: str) -> Optional[Dict]:
        """Извлекает данные видео из entry yt-dlp"""
        try:
            video_id = entry.get('id', '')
            if not video_id:
                url = entry.get('url', '')
                match = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', url)
                video_id = match.group(1) if match else url

            if not video_id:
                return None

            title = entry.get('title', '') or entry.get('description', '') or 'Без описания'
            views = entry.get('view_count', 0) or 0
            likes = entry.get('like_count', 0) or 0
            comments = entry.get('comment_count', 0) or 0

            timestamp = entry.get('timestamp', 0)
            if timestamp:
                publish_date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            else:
                upload_date = entry.get('upload_date', '')
                if upload_date and len(upload_date) == 8:
                    publish_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
                else:
                    publish_date = datetime.now().strftime('%Y-%m-%d')

            url = entry.get('url', '') or entry.get('webpage_url', '')
            if not url or not url.startswith('http'):
                url = f"https://www.instagram.com/p/{video_id}/"

            return {
                'title': title[:200] if title else 'Без описания',
                'url': url,
                'views': views,
                'likes': likes,
                'comments': comments,
                'shares': 0,
                'publish_date': publish_date,
                'channel': username,
                'uploader': username,
            }
        except Exception:
            return None

    def get_latest_video(self, profile_url: str) -> Optional[Dict]:
        """Получает последний видеоролик (для совместимости)"""
        videos = self.get_all_videos(profile_url, max_videos=1)
        return videos[0] if videos else None

    def get_user_videos(self, profile_url: str, max_videos: int = 30) -> List[Dict]:
        return self.get_all_videos(profile_url, max_videos=max_videos)

    def close(self):
        """Для совместимости"""
        return
