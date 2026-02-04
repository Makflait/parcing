"""
Генератор отчётов v2.0
Работает с листами для каждого блогера
"""
import json
import csv
from datetime import datetime
from typing import Dict

from utils import logger, SheetsManager


def load_config(config_file='config.json') -> Dict:
    """Загружает конфигурацию"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки конфигурации: {e}")
        return {}


def export_blogger_to_csv(sheets_manager: SheetsManager, blogger_name: str, filename: str = None) -> bool:
    """Экспортирует данные блогера в CSV"""
    try:
        if not sheets_manager.get_or_create_blogger_sheet(blogger_name):
            print(f"Лист для {blogger_name} не найден")
            return False

        if not filename:
            filename = f"{blogger_name}_{datetime.now().strftime('%Y-%m-%d')}.csv"

        all_data = sheets_manager.current_sheet.get_all_values()

        if not all_data:
            print(f"Нет данных для {blogger_name}")
            return False

        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(all_data)

        print(f"Данные {blogger_name} экспортированы в {filename}")
        return True

    except Exception as e:
        print(f"Ошибка экспорта: {e}")
        return False


def export_all_to_csv(sheets_manager: SheetsManager, config: Dict, filename: str = None) -> bool:
    """Экспортирует данные всех блогеров в один CSV"""
    try:
        if not filename:
            filename = f"all_bloggers_{datetime.now().strftime('%Y-%m-%d')}.csv"

        all_rows = []
        headers = ['Блогер', 'Платформа', 'Дата публикации', 'Последнее обновление',
                   'Название', 'URL', 'Просмотры', 'Лайки', 'Комментарии', 'Репосты']
        all_rows.append(headers)

        for blogger in config.get('bloggers', []):
            blogger_name = blogger.get('name')
            if not blogger_name:
                continue

            if sheets_manager.get_or_create_blogger_sheet(blogger_name):
                data = sheets_manager.current_sheet.get_all_values()
                # Пропускаем заголовок (первая строка)
                for row in data[1:]:
                    all_rows.append([blogger_name] + row)

        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerows(all_rows)

        print(f"Все данные экспортированы в {filename}")
        return True

    except Exception as e:
        print(f"Ошибка экспорта: {e}")
        return False


def print_blogger_report(sheets_manager: SheetsManager, blogger_name: str):
    """Выводит отчёт по одному блогеру"""
    if not sheets_manager.get_or_create_blogger_sheet(blogger_name):
        print(f"Лист для {blogger_name} не найден")
        return

    stats = sheets_manager.get_sheet_stats()

    print(f"\n{'='*50}")
    print(f"ОТЧЁТ: {blogger_name}")
    print(f"{'='*50}")
    print(f"Всего видео: {stats.get('total_videos', 0)}")
    print(f"Просмотры: {stats.get('total_views', 0):,}")
    print(f"Лайки: {stats.get('total_likes', 0):,}")

    if stats.get('platforms'):
        print("\nПо платформам:")
        for platform, pstats in stats['platforms'].items():
            print(f"  {platform}: {pstats['videos']} видео, {pstats['views']:,} просмотров")

    # Engagement rate
    if stats.get('total_views', 0) > 0:
        engagement = (stats.get('total_likes', 0)) / stats['total_views'] * 100
        print(f"\nEngagement (лайки/просмотры): {engagement:.2f}%")

    print(f"{'='*50}")


def print_full_report(sheets_manager: SheetsManager, config: Dict):
    """Выводит полный отчёт по всем блогерам"""

    print("\n" + "=" * 60)
    print("ПОЛНЫЙ ОТЧЁТ ПО ВСЕМ БЛОГЕРАМ")
    print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    stats = sheets_manager.get_all_bloggers_stats()

    if not stats or stats.get('total_videos', 0) == 0:
        print("\nНет данных")
        return

    print(f"\nОБЩАЯ СТАТИСТИКА:")
    print(f"  Всего видео: {stats['total_videos']}")
    print(f"  Общие просмотры: {stats['total_views']:,}")

    # По каждому блогеру
    print(f"\nПО БЛОГЕРАМ:")
    print("-" * 60)

    sorted_bloggers = sorted(
        stats.get('bloggers', {}).items(),
        key=lambda x: x[1]['views'],
        reverse=True
    )

    for i, (blogger, bstats) in enumerate(sorted_bloggers, 1):
        avg_views = bstats['views'] // bstats['videos'] if bstats['videos'] > 0 else 0
        print(f"  {i}. {blogger}:")
        print(f"     Видео: {bstats['videos']}")
        print(f"     Просмотры: {bstats['views']:,} (сред. {avg_views:,})")

    print("\n" + "=" * 60)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Генератор отчётов v2.0')
    parser.add_argument('--export-csv', action='store_true', help='Экспорт в CSV')
    parser.add_argument('--export-all', action='store_true', help='Экспорт всех блогеров в один CSV')
    parser.add_argument('--output', '-o', type=str, help='Имя выходного файла')
    parser.add_argument('--blogger', '-b', type=str, help='Отчёт по конкретному блогеру')
    args = parser.parse_args()

    config = load_config()
    if not config:
        print("Ошибка загрузки конфигурации")
        return

    spreadsheet_name = config.get('spreadsheet_name', 'Blogger Stats')
    sheets_manager = SheetsManager('credentials.json', spreadsheet_name)

    if not sheets_manager.connect():
        print("Ошибка подключения к Google Sheets")
        return

    # Экспорт в CSV
    if args.export_csv and args.blogger:
        export_blogger_to_csv(sheets_manager, args.blogger, args.output)

    elif args.export_all or args.export_csv:
        export_all_to_csv(sheets_manager, config, args.output)

    # Отчёт по блогеру
    elif args.blogger:
        print_blogger_report(sheets_manager, args.blogger)

    # Полный отчёт
    else:
        print_full_report(sheets_manager, config)


if __name__ == '__main__':
    main()
