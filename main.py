"""
Парсер статистики блогеров v4.0
Оптимизированная версия с параллельной обработкой
"""
import json
import os
import sys
from typing import Dict, List
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import logger, SheetsManager
from parsers import YouTubeParser, TikTokParser


class BloggerStatsCollector:
    """Главный класс для сбора статистики блогеров"""

    def __init__(self, config_file='config.json', credentials_file='credentials.json'):
        self.config_file = config_file
        self.credentials_file = credentials_file
        self.config = None
        self.sheets_manager = None
        self.youtube_parser = None
        self.tiktok_parser = None

    def load_config(self) -> bool:
        """Загружает конфигурацию"""
        try:
            if not os.path.exists(self.config_file):
                logger.error(f"Файл конфигурации {self.config_file} не найден")
                return False

            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)

            logger.info(f"Загружена конфигурация: {len(self.config.get('bloggers', []))} блогеров")
            return True

        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            return False

    def init_parsers(self):
        """Инициализирует парсеры"""
        logger.info("Инициализация парсеров...")

        self.youtube_parser = YouTubeParser(use_selenium=True)
        logger.info("YouTube парсер готов")

        self.tiktok_parser = TikTokParser(use_selenium=True)
        logger.info("TikTok парсер готов")

    def cleanup_parsers(self):
        """Закрывает парсеры"""
        if self.youtube_parser:
            self.youtube_parser.close()
        if self.tiktok_parser:
            self.tiktok_parser.close()
        logger.info("Парсеры закрыты")

    def process_blogger(self, blogger: Dict) -> Dict:
        """
        Обрабатывает одного блогера
        Оптимизировано: YouTube и TikTok парсятся параллельно
        Returns: статистика {added: int, updated: int, errors: int}
        """
        blogger_name = blogger.get('name', 'Unknown')
        stats = {'added': 0, 'updated': 0, 'errors': 0}

        logger.info(f"\n{'='*50}")
        logger.info(f"Обработка: {blogger_name}")
        logger.info(f"{'='*50}")

        # Создаём/открываем лист для этого блогера
        if not self.sheets_manager.get_or_create_blogger_sheet(blogger_name):
            logger.error(f"Не удалось создать лист для {blogger_name}")
            return stats

        # Получаем существующие видео с листа
        existing_videos = self.sheets_manager.get_existing_videos()
        logger.info(f"На листе уже {len(existing_videos)} видео")

        # Параллельно парсим YouTube и TikTok
        all_videos = []

        def fetch_youtube():
            if not blogger.get('youtube'):
                return []
            try:
                videos = self.youtube_parser.get_all_videos(blogger['youtube'])
                if videos:
                    for v in videos:
                        v['platform'] = 'YouTube'
                    return videos
            except Exception as e:
                logger.error(f"    YouTube ошибка: {e}")
            return []

        def fetch_tiktok():
            if not blogger.get('tiktok'):
                return []
            try:
                videos = self.tiktok_parser.get_all_videos(blogger['tiktok'])
                if videos:
                    for v in videos:
                        v['platform'] = 'TikTok'
                    return videos
            except Exception as e:
                logger.error(f"    TikTok ошибка: {e}")
            return []

        # Параллельный запуск
        logger.info(f"  Парсинг платформ (параллельно)...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            yt_future = executor.submit(fetch_youtube)
            tt_future = executor.submit(fetch_tiktok)

            yt_videos = yt_future.result()
            tt_videos = tt_future.result()

            if yt_videos:
                all_videos.extend(yt_videos)
                logger.info(f"    YouTube: найдено {len(yt_videos)} видео")
            else:
                logger.warning(f"    YouTube: видео не найдены")

            if tt_videos:
                all_videos.extend(tt_videos)
                logger.info(f"    TikTok: найдено {len(tt_videos)} видео")
            else:
                logger.warning(f"    TikTok: видео не найдены")

        # Обрабатываем найденные видео
        logger.info(f"  Обработка {len(all_videos)} видео...")

        for video in all_videos:
            url = video.get('url', '')

            if url in existing_videos:
                # Обновляем существующее видео
                row_num = existing_videos[url]
                success = self.sheets_manager.update_video(
                    row_num=row_num,
                    views=video.get('views', 0),
                    likes=video.get('likes', 0),
                    comments=video.get('comments', 0)
                )
                if success:
                    stats['updated'] += 1
                else:
                    stats['errors'] += 1
            else:
                # Добавляем новое видео
                success = self.sheets_manager.add_video(video)
                if success:
                    stats['added'] += 1
                    existing_videos[url] = len(existing_videos) + 2
                else:
                    stats['errors'] += 1

        logger.info(f"  Результат: +{stats['added']} новых, {stats['updated']} обновлено")

        return stats

    def print_final_report(self):
        """Выводит итоговый отчёт"""
        try:
            stats = self.sheets_manager.get_all_bloggers_stats()

            if not stats or stats.get('total_videos', 0) == 0:
                return

            logger.info("")
            logger.info("=" * 60)
            logger.info("ИТОГОВЫЙ ОТЧЁТ")
            logger.info("=" * 60)
            logger.info(f"Всего видео: {stats['total_videos']}")
            logger.info(f"Общие просмотры: {stats['total_views']:,}")

            logger.info("")
            logger.info("По блогерам:")
            sorted_bloggers = sorted(
                stats.get('bloggers', {}).items(),
                key=lambda x: x[1]['views'],
                reverse=True
            )
            for i, (blogger, bstats) in enumerate(sorted_bloggers, 1):
                logger.info(f"  {i}. {blogger}: {bstats['views']:,} просмотров ({bstats['videos']} видео)")

            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Ошибка формирования отчёта: {e}")

    def run(self):
        """Основной метод запуска"""
        logger.info("=" * 60)
        logger.info("Парсер статистики блогеров v3.0")
        logger.info("Каждый блогер - отдельный лист")
        logger.info("=" * 60)

        # Загрузка конфигурации
        if not self.load_config():
            return False

        # Подключение к Google Sheets
        spreadsheet_name = self.config.get('spreadsheet_name', 'Blogger Stats')
        self.sheets_manager = SheetsManager(self.credentials_file, spreadsheet_name)

        if not self.sheets_manager.connect():
            return False

        # Инициализация парсеров
        self.init_parsers()

        # Обработка каждого блогера
        bloggers = self.config.get('bloggers', [])
        total_stats = {'added': 0, 'updated': 0, 'errors': 0}

        try:
            for blogger in tqdm(bloggers, desc="Блогеры", unit="блогер"):
                stats = self.process_blogger(blogger)
                total_stats['added'] += stats['added']
                total_stats['updated'] += stats['updated']
                total_stats['errors'] += stats['errors']

            logger.info("")
            logger.info("=" * 60)
            logger.info("ЗАВЕРШЕНО!")
            logger.info(f"  Добавлено новых: {total_stats['added']}")
            logger.info(f"  Обновлено: {total_stats['updated']}")
            if total_stats['errors'] > 0:
                logger.info(f"  Ошибок: {total_stats['errors']}")
            logger.info("=" * 60)

            # Итоговый отчёт
            self.print_final_report()

            return True

        except KeyboardInterrupt:
            logger.warning("\nПрервано пользователем")
            return False

        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
            return False

        finally:
            self.cleanup_parsers()


def main():
    collector = BloggerStatsCollector()
    try:
        success = collector.run()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
