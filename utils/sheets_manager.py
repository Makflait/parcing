"""
Модуль для работы с Google Sheets API v3.1
Каждый блогер - отдельный лист
Исправлена обработка ошибок квоты (429)
"""
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from typing import List, Dict, Optional
import time
from .logger import logger


class SheetsManager:
    """Класс для управления Google Sheets таблицей с отдельными листами для блогеров"""

    def __init__(self, credentials_file: str, spreadsheet_name: str):
        self.credentials_file = credentials_file
        self.spreadsheet_name = spreadsheet_name
        self.client = None
        self.spreadsheet = None
        self.current_sheet = None
        self.current_blogger = None

        # Заголовки для листа блогера
        self.headers = [
            'Платформа',        # A
            'Дата публикации',  # B
            'Последнее обновление',  # C
            'Название',         # D
            'URL',              # E
            'Просмотры',        # F
            'Лайки',            # G
            'Комментарии',      # H
            'Репосты'           # I
        ]

    def connect(self) -> bool:
        """Подключение к Google Sheets"""
        try:
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]

            credentials = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_file, scope
            )
            self.client = gspread.authorize(credentials)
            self.spreadsheet = self.client.open(self.spreadsheet_name)

            logger.info(f"Подключено к таблице '{self.spreadsheet_name}'")
            return True

        except FileNotFoundError:
            logger.error(f"Файл credentials не найден: {self.credentials_file}")
            return False
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Таблица '{self.spreadsheet_name}' не найдена")
            return False
        except Exception as e:
            logger.error(f"Ошибка подключения к Google Sheets: {e}")
            return False

    def get_or_create_blogger_sheet(self, blogger_name: str) -> bool:
        """
        Получает или создаёт лист для блогера
        """
        try:
            # Пробуем найти существующий лист
            try:
                self.current_sheet = self.spreadsheet.worksheet(blogger_name)
                logger.debug(f"Найден лист для блогера: {blogger_name}")
            except gspread.exceptions.WorksheetNotFound:
                # Создаём новый лист
                self.current_sheet = self.spreadsheet.add_worksheet(
                    title=blogger_name,
                    rows=1000,
                    cols=10
                )
                # Добавляем заголовки
                self.current_sheet.update('A1:I1', [self.headers])
                logger.info(f"Создан новый лист для блогера: {blogger_name}")

            self.current_blogger = blogger_name
            return True

        except Exception as e:
            logger.error(f"Ошибка получения/создания листа для {blogger_name}: {e}")
            return False

    def get_existing_videos(self) -> Dict[str, int]:
        """
        Получает все существующие видео с текущего листа
        Returns: {url: row_number}
        """
        if not self.current_sheet:
            return {}

        try:
            all_data = self.current_sheet.get_all_values()
            videos = {}

            # Пропускаем заголовок (строка 1)
            for row_num, row in enumerate(all_data[1:], start=2):
                if len(row) >= 5:  # Минимум до URL (столбец E)
                    url = row[4]  # URL в столбце E (индекс 4)
                    if url:
                        videos[url] = row_num

            return videos

        except Exception as e:
            logger.error(f"Ошибка получения видео с листа: {e}")
            return {}

    def update_video(self, row_num: int, views: int, likes: int, comments: int) -> bool:
        """Обновляет статистику существующего видео"""
        max_retries = 5
        retry_delay = 3

        for attempt in range(max_retries):
            try:
                update_time = datetime.now().strftime('%Y-%m-%d %H:%M')

                # Batch update - обновляем дату и статистику
                updates = [
                    {'range': f'C{row_num}', 'values': [[update_time]]},
                    {'range': f'F{row_num}', 'values': [[views]]},
                    {'range': f'G{row_num}', 'values': [[likes]]},
                    {'range': f'H{row_num}', 'values': [[comments]]}
                ]

                self.current_sheet.batch_update(updates, value_input_option='USER_ENTERED')
                # Пауза между запросами
                time.sleep(1.2)
                return True

            except Exception as e:
                error_str = str(e)
                if '429' in error_str or 'Quota' in error_str:
                    # Ошибка квоты - ждём больше минуты
                    wait_time = 65
                    logger.warning(f"Превышена квота API, ожидание {wait_time} сек...")
                    time.sleep(wait_time)
                elif attempt < max_retries - 1:
                    logger.warning(f"Попытка {attempt + 1}/{max_retries} обновления строки {row_num}: {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Не удалось обновить строку {row_num}: {e}")
                    return False

        return False

    def add_video(self, video_data: Dict) -> bool:
        """Добавляет новое видео на текущий лист"""
        max_retries = 5
        retry_delay = 3

        for attempt in range(max_retries):
            try:
                row = [
                    video_data.get('platform', ''),
                    video_data.get('publish_date', ''),
                    datetime.now().strftime('%Y-%m-%d %H:%M'),  # Последнее обновление
                    str(video_data.get('title', ''))[:100],
                    video_data.get('url', ''),
                    video_data.get('views', 0),
                    video_data.get('likes', 0),
                    video_data.get('comments', 0),
                    video_data.get('shares', 0)
                ]

                self.current_sheet.append_row(row, value_input_option='USER_ENTERED')
                # Пауза между запросами чтобы не превысить лимит (60 запросов/мин)
                time.sleep(1.2)
                return True

            except Exception as e:
                error_str = str(e)
                if '429' in error_str or 'Quota' in error_str:
                    # Ошибка квоты - ждём больше минуты
                    wait_time = 65
                    logger.warning(f"Превышена квота API, ожидание {wait_time} сек...")
                    time.sleep(wait_time)
                elif attempt < max_retries - 1:
                    logger.warning(f"Попытка {attempt + 1}/{max_retries} добавления видео: {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Не удалось добавить видео: {e}")
                    return False

        return False

    def get_sheet_stats(self) -> Dict:
        """Получает статистику с текущего листа"""
        if not self.current_sheet:
            return {}

        try:
            all_data = self.current_sheet.get_all_values()
            stats = {
                'total_videos': 0,
                'total_views': 0,
                'total_likes': 0,
                'platforms': {}
            }

            for row in all_data[1:]:
                if len(row) >= 8:
                    stats['total_videos'] += 1

                    try:
                        views = int(row[5]) if row[5] else 0
                        likes = int(row[6]) if row[6] else 0
                    except ValueError:
                        views = likes = 0

                    stats['total_views'] += views
                    stats['total_likes'] += likes

                    platform = row[0]
                    if platform not in stats['platforms']:
                        stats['platforms'][platform] = {'videos': 0, 'views': 0}
                    stats['platforms'][platform]['videos'] += 1
                    stats['platforms'][platform]['views'] += views

            return stats

        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}

    def get_all_bloggers_stats(self) -> Dict:
        """Получает статистику по всем блогерам"""
        try:
            all_sheets = self.spreadsheet.worksheets()
            total_stats = {
                'total_videos': 0,
                'total_views': 0,
                'bloggers': {}
            }

            for sheet in all_sheets:
                blogger_name = sheet.title
                if blogger_name in ['Sheet1', 'Лист1']:  # Пропускаем стандартный лист
                    continue

                try:
                    all_data = sheet.get_all_values()
                    blogger_stats = {'videos': 0, 'views': 0}

                    for row in all_data[1:]:
                        if len(row) >= 6:
                            blogger_stats['videos'] += 1
                            try:
                                views = int(row[5]) if row[5] else 0
                                blogger_stats['views'] += views
                                total_stats['total_views'] += views
                            except ValueError:
                                pass

                    total_stats['total_videos'] += blogger_stats['videos']
                    total_stats['bloggers'][blogger_name] = blogger_stats

                except Exception as e:
                    logger.warning(f"Ошибка чтения листа {blogger_name}: {e}")

            return total_stats

        except Exception as e:
            logger.error(f"Ошибка получения общей статистики: {e}")
            return {}
