"""
Тестовый скрипт для проверки работы парсеров
Запустите этот скрипт чтобы убедиться, что все работает правильно
"""
import sys
from parsers import YouTubeParser, TikTokParser, InstagramParser
from utils import logger


def test_youtube():
    """Тест YouTube парсера"""
    print("\n" + "="*60)
    print("ТЕСТ: YouTube Parser")
    print("="*60)

    # Тестовый канал (используем популярный публичный канал)
    test_url = "https://www.youtube.com/@TEDx"

    try:
        parser = YouTubeParser(use_selenium=False)
        print(f"Парсинг канала: {test_url}")

        video_data = parser.get_latest_video(test_url)

        if video_data:
            print("\n✓ YouTube парсер работает!")
            print(f"  Название: {video_data.get('title', 'N/A')[:60]}...")
            print(f"  URL: {video_data.get('url', 'N/A')}")
            print(f"  Просмотры: {video_data.get('views', 0):,}")
            print(f"  Лайки: {video_data.get('likes', 0):,}")
            return True
        else:
            print("\n✗ YouTube парсер не смог получить данные")
            print("  Возможные причины:")
            print("  - Изменилась структура YouTube")
            print("  - Проблемы с интернет-соединением")
            print("  - YouTube временно недоступен")
            return False

    except Exception as e:
        print(f"\n✗ Ошибка при тестировании YouTube: {e}")
        return False
    finally:
        parser.close()


def test_tiktok():
    """Тест TikTok парсера"""
    print("\n" + "="*60)
    print("ТЕСТ: TikTok Parser")
    print("="*60)

    # Тестовый профиль
    test_url = "https://www.tiktok.com/@tiktok"

    print("⚠️  ВНИМАНИЕ: TikTok парсер использует Selenium (может быть медленным)")
    print("⚠️  TikTok часто блокирует автоматические запросы")

    try:
        parser = TikTokParser(use_selenium=True)
        print(f"Парсинг профиля: {test_url}")

        video_data = parser.get_latest_video(test_url)

        if video_data:
            print("\n✓ TikTok парсер работает!")
            print(f"  Название: {video_data.get('title', 'N/A')[:60]}...")
            print(f"  URL: {video_data.get('url', 'N/A')}")
            print(f"  Просмотры: {video_data.get('views', 0):,}")
            print(f"  Лайки: {video_data.get('likes', 0):,}")
            return True
        else:
            print("\n✗ TikTok парсер не смог получить данные")
            print("  Возможные причины:")
            print("  - TikTok заблокировал запрос")
            print("  - Изменилась структура TikTok")
            print("  - Требуется VPN")
            return False

    except Exception as e:
        print(f"\n✗ Ошибка при тестировании TikTok: {e}")
        return False
    finally:
        parser.close()


def test_instagram():
    """Тест Instagram парсера"""
    print("\n" + "="*60)
    print("ТЕСТ: Instagram Parser")
    print("="*60)

    # Тестовый профиль
    test_url = "https://www.instagram.com/instagram"

    print("⚠️  ВНИМАНИЕ: Instagram парсер использует Selenium (может быть медленным)")
    print("⚠️  Instagram часто требует авторизацию для просмотра данных")

    try:
        parser = InstagramParser(use_selenium=True)
        print(f"Парсинг профиля: {test_url}")

        video_data = parser.get_latest_video(test_url)

        if video_data:
            print("\n✓ Instagram парсер работает!")
            print(f"  Описание: {video_data.get('title', 'N/A')[:60]}...")
            print(f"  URL: {video_data.get('url', 'N/A')}")
            print(f"  Просмотры: {video_data.get('views', 0):,}")
            print(f"  Лайки: {video_data.get('likes', 0):,}")
            return True
        else:
            print("\n✗ Instagram парсер не смог получить данные")
            print("  Возможные причины:")
            print("  - Instagram заблокировал запрос")
            print("  - Изменилась структура Instagram")
            print("  - Требуется авторизация")
            return False

    except Exception as e:
        print(f"\n✗ Ошибка при тестировании Instagram: {e}")
        return False
    finally:
        parser.close()


def test_google_sheets():
    """Тест подключения к Google Sheets"""
    print("\n" + "="*60)
    print("ТЕСТ: Google Sheets Connection")
    print("="*60)

    import os
    from utils import SheetsManager

    # Проверка наличия credentials.json
    if not os.path.exists('credentials.json'):
        print("✗ Файл credentials.json не найден")
        print("  Создайте credentials.json согласно инструкции в README.md")
        return False

    # Проверка config.json
    if not os.path.exists('config.json'):
        print("✗ Файл config.json не найден")
        return False

    try:
        import json
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)

        spreadsheet_name = config.get('spreadsheet_name', 'Blogger Stats')
        print(f"Подключение к таблице: {spreadsheet_name}")

        sheets_manager = SheetsManager('credentials.json', spreadsheet_name)

        if sheets_manager.connect():
            print("\n✓ Подключение к Google Sheets успешно!")
            print(f"  Таблица: {spreadsheet_name}")
            return True
        else:
            print("\n✗ Не удалось подключиться к Google Sheets")
            print("  Проверьте:")
            print("  - Правильность credentials.json")
            print("  - Название таблицы в config.json")
            print("  - Доступ Service Account к таблице")
            return False

    except Exception as e:
        print(f"\n✗ Ошибка при тестировании Google Sheets: {e}")
        return False


def main():
    """Основная функция тестирования"""
    print("\n" + "#"*60)
    print("# ТЕСТИРОВАНИЕ BLOGGER STATS PARSER")
    print("#"*60)

    results = {
        'google_sheets': False,
        'youtube': False,
        'tiktok': False,
        'instagram': False
    }

    # Тест Google Sheets (обязательный)
    results['google_sheets'] = test_google_sheets()

    # Тест парсеров
    print("\n⚠️  Тестирование парсеров может занять несколько минут...")
    print("⚠️  Вы можете пропустить тесты нажав Ctrl+C\n")

    try:
        # YouTube (быстрый)
        results['youtube'] = test_youtube()

        # TikTok (медленный)
        response = input("\nТестировать TikTok? (медленно, может не работать) [y/N]: ")
        if response.lower() == 'y':
            results['tiktok'] = test_tiktok()

        # Instagram (медленный)
        response = input("\nТестировать Instagram? (медленно, может не работать) [y/N]: ")
        if response.lower() == 'y':
            results['instagram'] = test_instagram()

    except KeyboardInterrupt:
        print("\n\nТестирование прервано пользователем")

    # Итоги
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
    print("="*60)

    for test_name, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name.upper():20} {status}")

    # Рекомендации
    print("\n" + "="*60)
    print("РЕКОМЕНДАЦИИ")
    print("="*60)

    if not results['google_sheets']:
        print("\n❌ Google Sheets не работает - это критично!")
        print("   Без этого основная функциональность недоступна.")
        print("   Смотрите SETUP.md для настройки.")

    if results['youtube']:
        print("\n✓ YouTube работает - основной парсер готов к использованию")
    else:
        print("\n⚠️  YouTube парсер не работает")
        print("   Попробуйте включить Selenium режим в main.py")

    if not results['tiktok'] and not results['instagram']:
        print("\n⚠️  TikTok и Instagram парсеры могут не работать без дополнительной настройки")
        print("   Это нормально - эти платформы активно борются с парсингом")
        print("   Рекомендуется:")
        print("   - Использовать VPN")
        print("   - Настроить прокси")
        print("   - Увеличить задержки между запросами")

    # Финальный вердикт
    print("\n" + "="*60)
    if results['google_sheets'] and results['youtube']:
        print("✓ Система готова к работе!")
        print("  Запустите: python main.py")
    elif results['google_sheets']:
        print("⚠️  Система частично готова")
        print("  Google Sheets работает, но есть проблемы с парсерами")
    else:
        print("✗ Система не готова")
        print("  Необходимо настроить Google Sheets")
        print("  Смотрите SETUP.md")

    print("="*60 + "\n")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n✗ Критическая ошибка: {e}")
        logger.error(f"Критическая ошибка при тестировании: {e}", exc_info=True)
        sys.exit(1)
