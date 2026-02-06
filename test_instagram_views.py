"""
Тестовый скрипт для проверки парсинга просмотров Instagram
"""
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time

# URL одного из Reels для тестирования
test_url = "https://www.instagram.com/thompsonmilana1/reel/DT2HDKEiN6H/"

print(f"Тестируем: {test_url}\n")

# Инициализация Chrome
chrome_options = Options()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

try:
    service = Service(ChromeDriverManager(cache_valid_range=365).install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
except:
    driver = webdriver.Chrome(options=chrome_options)

# Открываем страницу
driver.get(test_url)
time.sleep(8)

# Скроллим
driver.execute_script("window.scrollTo(0, 300);")
time.sleep(2)

# Получаем page source
page_source = driver.page_source

print("=== Поиск просмотров в page_source ===\n")

# Паттерны для просмотров
view_patterns = [
    (r'"video_view_count":(\d+)', 'video_view_count'),
    (r'"play_count":(\d+)', 'play_count'),
    (r'"view_count":(\d+)', 'view_count'),
    (r'video_view_count&quot;:(\d+)', 'HTML encoded video_view_count'),
    (r'play_count&quot;:(\d+)', 'HTML encoded play_count'),
    (r'"views":"(\d+)"', 'views string'),
    (r'"playCount":(\d+)', 'playCount'),
    (r'(\d+)\s+views', 'X views text'),
    (r'(\d+)\s+просмотр', 'X просмотров text'),
]

for pattern, name in view_patterns:
    matches = re.findall(pattern, page_source, re.IGNORECASE)
    if matches:
        print(f"✓ Найдено по паттерну '{name}':")
        for match in matches[:5]:  # Показываем первые 5 совпадений
            print(f"  - {match}")
    else:
        print(f"✗ Не найдено по паттерну '{name}'")

# Ищем любые большие числа которые могут быть просмотрами
print("\n=== Поиск больших чисел (возможные просмотры) ===\n")
big_numbers = re.findall(r':\s*(\d{3,})', page_source)
unique_numbers = sorted(set([int(n) for n in big_numbers if int(n) > 100 and int(n) < 1000000]))
print(f"Найдено уникальных чисел (100-1000000): {unique_numbers[:20]}")

# Сохраняем page_source для анализа
with open('instagram_page_source.html', 'w', encoding='utf-8') as f:
    f.write(page_source)
print("\n✓ Page source сохранен в instagram_page_source.html для анализа")

driver.quit()
print("\n✓ Тест завершен")
