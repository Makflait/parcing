"""
Парсер для Instagram
"""
import re
import json
import time
from typing import Optional, Dict
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service


class InstagramParser:
    """Парсер для получения данных с Instagram"""

    def __init__(self, use_selenium=True):
        """
        Инициализация парсера

        Args:
            use_selenium: использовать ли Selenium (рекомендуется для Instagram)
        """
        self.use_selenium = use_selenium
        self.driver = None

        if use_selenium:
            self._init_driver()

    def _init_driver(self):
        """Инициализация Selenium WebDriver с улучшенной маскировкой"""
        try:
            chrome_options = Options()

            # Базовые настройки (старый стабильный headless)
            chrome_options.add_argument('--headless')  # Стандартный headless режим
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')

            # Более реалистичный User-Agent
            chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            # Дополнительные настройки для обхода детекта
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--lang=en-US')
            chrome_options.add_argument('--disable-notifications')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)

            # Добавляем prefs для отключения всплывающих окон
            prefs = {
                "profile.default_content_setting_values.notifications": 2,
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            }
            chrome_options.add_experimental_option("prefs", prefs)

            # Сначала пробуем без webdriver-manager (используем уже установленный драйвер)
            try:
                self.driver = webdriver.Chrome(options=chrome_options)
            except:
                # Если не получилось, пробуем с webdriver-manager
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)

            # Маскируем webdriver
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        except Exception as e:
            print(f"Ошибка инициализации WebDriver для Instagram: {e}")
            self.driver = None

    def get_latest_video(self, profile_url: str) -> Optional[Dict]:
        """
        Получает последний видеоролик/пост с профиля Instagram

        Args:
            profile_url: URL профиля Instagram

        Returns:
            Dict с данными о видео или None если не удалось получить
        """
        # Сначала пробуем через requests API (быстрее)
        result = self._get_video_requests(profile_url)
        if result:
            return result

        # Если не получилось - пробуем Selenium
        if self.use_selenium and self.driver:
            return self._get_video_selenium(profile_url)

        return None

    def _get_video_requests(self, profile_url: str) -> Optional[Dict]:
        """
        Получение данных через Instagram Graph API (публичный доступ)
        """
        try:
            # Извлекаем username из URL
            username = profile_url.rstrip('/').split('/')[-1]

            # Убираем query параметры если есть
            username = username.split('?')[0]

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }

            # Пробуем получить HTML страницу профиля
            response = requests.get(f"https://www.instagram.com/{username}/", headers=headers, timeout=15)

            if response.status_code != 200:
                return None

            # Ищем JSON данные в HTML
            html = response.text

            # Instagram встраивает данные в script tag
            pattern = r'window\._sharedData = ({.*?});</script>'
            match = re.search(pattern, html)

            if not match:
                # Пробуем другой паттерн
                pattern = r'<script type="application/ld\+json">({.*?})</script>'
                match = re.search(pattern, html)

            if not match:
                return None

            try:
                data = json.loads(match.group(1))

                # Пытаемся извлечь данные о первом посте
                # Структура может меняться, поэтому пробуем разные пути

                # Вариант 1: через entry_data
                if 'entry_data' in data:
                    profile_page = data.get('entry_data', {}).get('ProfilePage', [])
                    if profile_page:
                        user = profile_page[0].get('graphql', {}).get('user', {})
                        edge_media = user.get('edge_owner_to_timeline_media', {})
                        edges = edge_media.get('edges', [])

                        if edges:
                            first_post = edges[0].get('node', {})
                            return self._parse_post_data(first_post)

                # Вариант 2: ищем в других местах
                # Instagram может возвращать разную структуру

            except json.JSONDecodeError:
                pass

            return None

        except Exception as e:
            print(f"Ошибка при парсинге Instagram (requests): {e}")
            return None

    def _get_video_selenium(self, profile_url: str) -> Optional[Dict]:
        """Получение данных через Selenium с улучшенной логикой для 2026"""
        if not self.driver:
            return None

        try:
            # Переходим на профиль
            self.driver.get(profile_url)
            time.sleep(8)  # Увеличиваем задержку для полной загрузки

            # Имитируем человеческое поведение - скроллим
            self.driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(2)
            self.driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(3)

            # Получаем page source для парсинга
            page_source = self.driver.page_source

            # Ищем данные в JSON-структурах Instagram
            # Паттерн 1: Ищем shortcode в graphql данных
            shortcode_patterns = [
                r'"shortcode":"([A-Za-z0-9_-]{11})"',
                r'/p/([A-Za-z0-9_-]{11})/',
                r'"code":"([A-Za-z0-9_-]{11})"',
            ]

            found_shortcodes = []
            for pattern in shortcode_patterns:
                matches = re.findall(pattern, page_source)
                if matches:
                    found_shortcodes.extend(matches)

            # Убираем дубликаты
            seen = set()
            unique_shortcodes = []
            for code in found_shortcodes:
                if code not in seen and len(code) == 11:
                    seen.add(code)
                    unique_shortcodes.append(code)

            if unique_shortcodes:
                # Берем первый найденный пост
                first_post_url = f"https://www.instagram.com/p/{unique_shortcodes[0]}/"
                return self._scrape_post_page(first_post_url)

            # Если не нашли через regex, пробуем через элементы
            post_links = []

            selectors_to_try = [
                'a[href*="/p/"]',
                'a[href*="/reel/"]',
                'article a',
                'div[role="button"] a',
            ]

            for selector in selectors_to_try:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elements:
                        href = elem.get_attribute('href')
                        if href and ('/p/' in href or '/reel/' in href):
                            post_links.append(href)
                    if post_links:
                        break
                except:
                    continue

            if post_links:
                return self._scrape_post_page(post_links[0])

            print("Instagram: не найдены посты на странице")
            return None

        except Exception as e:
            print(f"Ошибка Selenium парсинга Instagram: {e}")
            return None

    def _scrape_post_page(self, post_url: str) -> Optional[Dict]:
        """Парсит страницу поста с улучшенной логикой для 2026"""
        try:
            self.driver.get(post_url)
            time.sleep(6)

            # Прокручиваем чтобы загрузить все элементы
            self.driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(2)

            # Получаем page source для парсинга
            page_source = self.driver.page_source

            # Пробуем найти просмотры в элементах страницы (для Reels)
            views_from_elements = self._extract_views_from_elements()

            # Сначала пробуем извлечь данные из JSON структур
            result = self._extract_from_json(page_source, post_url)
            if result:
                # Если просмотры не найдены, пробуем извлечь их отдельно
                if result['views'] == 0:
                    if views_from_elements > 0:
                        result['views'] = views_from_elements
                    else:
                        views = self._extract_views_from_source(page_source)
                        if views > 0:
                            result['views'] = views
                return result

            # Если JSON не сработал, пробуем через LD+JSON
            pattern = r'<script type="application/ld\+json">({.*?})</script>'
            matches = re.findall(pattern, page_source, re.DOTALL)

            for match in matches:
                try:
                    data = json.loads(match)

                    # Проверяем что это данные о посте
                    if '@type' in data and 'Post' in str(data.get('@type', '')):
                        caption = data.get('caption', data.get('articleBody', 'Без описания'))

                        # Извлекаем статистику
                        interactions = data.get('interactionStatistic', [])
                        likes = 0
                        comments = 0
                        views = 0

                        for stat in interactions:
                            stat_type = stat.get('@type', '')
                            value = stat.get('userInteractionCount', 0)

                            if 'LikeAction' in stat_type:
                                likes = int(value)
                            elif 'CommentAction' in stat_type:
                                comments = int(value)
                            elif 'WatchAction' in stat_type:
                                views = int(value)

                        result_data = {
                            'title': caption[:200] if caption else 'Без описания',
                            'url': post_url,
                            'views': views,
                            'likes': likes,
                            'comments': comments,
                            'shares': 0,
                            'publish_date': datetime.now().strftime('%Y-%m-%d'),
                            'watch_time': 'N/A'
                        }

                        # Если просмотры не найдены, пробуем из элементов
                        if views == 0 and views_from_elements > 0:
                            result_data['views'] = views_from_elements

                        return result_data
                except:
                    continue

            # Если JSON не нашли, пробуем парсить HTML
            result = self._parse_html_fallback(page_source, post_url)

            # Пытаемся дополнительно извлечь просмотры
            if result and result['views'] == 0:
                if views_from_elements > 0:
                    result['views'] = views_from_elements
                else:
                    views = self._extract_views_from_source(page_source)
                    if views > 0:
                        result['views'] = views

            return result

        except Exception as e:
            print(f"Ошибка при парсинге страницы поста: {e}")
            return None

    def _extract_from_json(self, page_source: str, post_url: str) -> Optional[Dict]:
        """Извлекает данные из JSON структур Instagram"""
        try:
            # Ищем graphql данные
            patterns = [
                r'window\.__additionalDataLoaded\([^,]+,({.+?})\);',
                r'window\._sharedData = ({.+?});</script>',
            ]

            for pattern in patterns:
                match = re.search(pattern, page_source)
                if match:
                    try:
                        data = json.loads(match.group(1))

                        # Пытаемся найти данные поста в разных местах
                        # Структура может быть разной
                        caption = 'Без описания'
                        likes = 0
                        comments = 0
                        views = 0

                        # Рекурсивно ищем нужные поля
                        def find_in_dict(d, key):
                            if isinstance(d, dict):
                                if key in d:
                                    return d[key]
                                for v in d.values():
                                    result = find_in_dict(v, key)
                                    if result is not None:
                                        return result
                            elif isinstance(d, list):
                                for item in d:
                                    result = find_in_dict(item, key)
                                    if result is not None:
                                        return result
                            return None

                        # Ищем caption
                        caption_data = find_in_dict(data, 'edge_media_to_caption')
                        if caption_data and isinstance(caption_data, dict):
                            edges = caption_data.get('edges', [])
                            if edges:
                                caption = edges[0].get('node', {}).get('text', 'Без описания')

                        # Ищем лайки
                        likes_data = find_in_dict(data, 'edge_media_preview_like')
                        if likes_data:
                            likes = likes_data.get('count', 0)

                        # Ищем комментарии
                        comments_data = find_in_dict(data, 'edge_media_to_comment')
                        if comments_data:
                            comments = comments_data.get('count', 0)

                        # Ищем просмотры (для видео/Reels) - несколько ключей
                        views = 0
                        view_keys = ['video_view_count', 'play_count', 'view_count', 'views']
                        for key in view_keys:
                            view_data = find_in_dict(data, key)
                            if view_data and isinstance(view_data, (int, str)):
                                try:
                                    views = int(view_data)
                                    if views > 0:
                                        break
                                except:
                                    continue

                        if caption != 'Без описания' or likes > 0 or comments > 0:
                            return {
                                'title': caption[:200] if caption else 'Без описания',
                                'url': post_url,
                                'views': views,
                                'likes': likes,
                                'comments': comments,
                                'shares': 0,
                                'publish_date': datetime.now().strftime('%Y-%m-%d'),
                                'watch_time': 'N/A'
                            }
                    except:
                        continue

            return None
        except:
            return None

    def _extract_views_from_elements(self) -> int:
        """Извлекает просмотры из элементов страницы"""
        try:
            if not self.driver:
                return 0

            # Паттерны текста для поиска просмотров
            view_text_patterns = [
                (By.XPATH, "//*[contains(text(), 'views')]"),
                (By.XPATH, "//*[contains(text(), 'просмотр')]"),
                (By.XPATH, "//*[contains(@aria-label, 'views')]"),
                (By.CSS_SELECTOR, "span[class*='view']"),
                (By.CSS_SELECTOR, "div[class*='view']"),
            ]

            for by, selector in view_text_patterns:
                try:
                    elements = self.driver.find_elements(by, selector)
                    for elem in elements:
                        text = elem.text.strip()
                        # Ищем числа с K, M или просто числа
                        match = re.search(r'([\d,]+\.?\d*)\s*([KMB]?)\s*(views|просмотр)', text, re.IGNORECASE)
                        if match:
                            number = match.group(1).replace(',', '')
                            multiplier = match.group(2).upper()

                            views = float(number)
                            if multiplier == 'K':
                                views *= 1000
                            elif multiplier == 'M':
                                views *= 1000000
                            elif multiplier == 'B':
                                views *= 1000000000

                            return int(views)
                except:
                    continue

            return 0
        except:
            return 0

    def _extract_views_from_source(self, page_source: str) -> int:
        """Извлекает просмотры из page_source через regex с улучшенным поиском"""
        try:
            # Паттерны для поиска просмотров в JSON данных
            json_view_patterns = [
                r'"video_view_count":(\d+)',
                r'"play_count":(\d+)',
                r'"view_count":(\d+)',
                r'video_view_count&quot;:(\d+)',
                r'play_count&quot;:(\d+)',
                r'"views":"(\d+)"',
                r'"playCount":(\d+)',
                r'"viewCount":(\d+)',
                r'&quot;video_view_count&quot;:(\d+)',
                r'&quot;play_count&quot;:(\d+)',
                r'playCount\\u0022:(\d+)',
                r'viewCount\\u0022:(\d+)',
            ]

            for pattern in json_view_patterns:
                matches = re.findall(pattern, page_source)
                if matches:
                    # Берем максимальное значение из всех найденных
                    try:
                        max_views = max([int(m) for m in matches])
                        if max_views > 0:
                            return max_views
                    except:
                        continue

            # Паттерны для поиска в читаемом виде (типа "1.2K views")
            text_view_patterns = [
                r'([\d,]+\.?\d*)\s*([KMB])?\s*views',
                r'([\d,]+\.?\d*)\s*([KMB])?\s*просмотр',
                r'views.*?([\d,]+\.?\d*)\s*([KMB])?',
                r'view_count.*?([\d,]+)',
            ]

            for pattern in text_view_patterns:
                match = re.search(pattern, page_source, re.IGNORECASE)
                if match:
                    try:
                        number = match.group(1).replace(',', '')
                        multiplier = match.group(2) if len(match.groups()) > 1 else ''

                        views = float(number)
                        if multiplier:
                            if multiplier.upper() == 'K':
                                views *= 1000
                            elif multiplier.upper() == 'M':
                                views *= 1000000
                            elif multiplier.upper() == 'B':
                                views *= 1000000000

                        if views > 0:
                            return int(views)
                    except:
                        continue

            return 0
        except:
            return 0

    def _parse_html_fallback(self, html: str, post_url: str) -> Optional[Dict]:
        """Запасной метод парсинга через HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Ищем мета-теги
            description = soup.find('meta', property='og:description')
            title_text = description['content'][:200] if description else 'Без описания'

            # Пытаемся найти лайки в тексте страницы
            likes_pattern = r'(\d+(?:,\d+)*)\s+like'
            likes_match = re.search(likes_pattern, html, re.IGNORECASE)
            likes = int(likes_match.group(1).replace(',', '')) if likes_match else 0

            return {
                'title': title_text,
                'url': post_url,
                'views': 0,
                'likes': likes,
                'comments': 0,
                'shares': 0,
                'publish_date': datetime.now().strftime('%Y-%m-%d'),
                'watch_time': 'N/A'
            }
        except:
            return None

    def _parse_post_data(self, post_node: dict) -> Dict:
        """Парсит данные поста из JSON"""
        try:
            shortcode = post_node.get('shortcode', '')
            post_url = f"https://www.instagram.com/p/{shortcode}/"

            # Извлекаем caption
            caption_edges = post_node.get('edge_media_to_caption', {}).get('edges', [])
            caption = ''
            if caption_edges:
                caption = caption_edges[0].get('node', {}).get('text', '')

            # Извлекаем статистику
            likes = post_node.get('edge_liked_by', {}).get('count', 0)
            comments = post_node.get('edge_media_to_comment', {}).get('count', 0)
            views = post_node.get('video_view_count', 0)

            # Дата публикации
            timestamp = post_node.get('taken_at_timestamp', 0)
            publish_date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d') if timestamp else datetime.now().strftime('%Y-%m-%d')

            return {
                'title': caption[:200] if caption else 'Без описания',
                'url': post_url,
                'views': views,
                'likes': likes,
                'comments': comments,
                'shares': 0,
                'publish_date': publish_date,
                'watch_time': 'N/A'
            }
        except Exception as e:
            print(f"Ошибка парсинга данных поста: {e}")
            return None

    def _parse_number(self, text: str) -> int:
        """Парсит число из текста (1.2K -> 1200, 1M -> 1000000)"""
        if not text:
            return 0

        text = text.strip().upper().replace(',', '')
        text = re.sub(r'[^\d.KMB]', '', text)

        try:
            if 'K' in text:
                return int(float(text.replace('K', '')) * 1000)
            elif 'M' in text:
                return int(float(text.replace('M', '')) * 1000000)
            elif 'B' in text:
                return int(float(text.replace('B', '')) * 1000000000)
            else:
                digits = re.sub(r'\D', '', text)
                return int(digits) if digits else 0
        except:
            return 0

    def close(self):
        """Закрывает WebDriver"""
        if self.driver:
            self.driver.quit()

    def __del__(self):
        """Деструктор"""
        self.close()
