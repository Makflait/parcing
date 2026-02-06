"""
Скрипт для проверки данных в Google Sheets
"""
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Подключение к Google Sheets
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

credentials = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(credentials)

# Открываем таблицу
sheet = client.open('Blogger Stats').sheet1

# Получаем все данные
all_data = sheet.get_all_values()

# Показываем заголовки
print("Заголовки:", all_data[0])
print("\n" + "="*100 + "\n")

# Показываем последние 15 записей
print("Последние 15 записей:\n")
for i, row in enumerate(all_data[-15:], 1):
    print(f"{i}. Блогер: {row[0]}")
    print(f"   Платформа: {row[1]}")
    print(f"   Название: {row[4][:50]}...")
    print(f"   URL: {row[5]}")
    print(f"   Просмотры: {row[6]}")
    print(f"   Лайки: {row[7]}")
    print(f"   Комментарии: {row[8]}")
    print()
