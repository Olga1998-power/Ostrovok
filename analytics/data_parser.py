import json
import pandas as pd

# 1. ЗАГРУЗКА ДАННЫХ (в пятницу поменяй название файла на то, что даст Островок)
# Если дадут JSON, то df = pd.read_json('ostrovok_data.json')
try:
    df = pd.read_csv('ostrovok_raw_data.csv')
    print(f"Успешно загружено {len(df)} строк от Островка.")
except Exception as e:
    print("Ошибка загрузки файла. Проверь формат и путь:", e)
    exit()

# 2. ОЧИСТКА И ФИЛЬТРАЦИЯ (Оставляем топ-30 лучших отелей для демо)
# Очищаем пустые значения в критически важных полях
df = df.dropna(subset=['id', 'name', 'city', 'price', 'rating'])

# Оставляем, например, только отели с высоким рейтингом, чтобы демо выглядело сочно
df = df[df['rating'] >= 4.0]

# Берем первые 30 отелей для нашего Тиндера
df_sample = df.head(30)

# 3. ГЕНЕРАЦИЯ ГОТОВОГО SQL-СКРИПТА
sql_statements = [
    "-- Скрипт сгенерирован автоматически из датасета Островка",
    "TRUNCATE TABLE user_swipes, travel_cards CASCADE;"
]

print("\nНачинаем парсинг отелей...")

for index, row in df_sample.iterrows():
    hotel_id = int(row['id'])
    name = str(row['name']).replace("'", "''")  # Экранируем кавычки в названии
    city = str(row['city']).replace("'", "''")
    price = float(row['price'])
    rating = float(row['rating'])

    # Обработка удобств (если пришли строкой 'wifi, pool', превращаем в JSON-массив)
    raw_amenities = row.get('amenities', '["wifi"]')
    if isinstance(raw_amenities, str):
        # Если пришло строкой через запятую, делим и пакуем в JSON
        if ',' in raw_amenities:
            amenities_list = [t.strip().lower() for t in raw_amenities.split(',')]
            amenities_json = json.dumps(amenities_list)
        else:
            amenities_json = json.dumps([raw_amenities.strip().lower()])
    else:
        amenities_json = json.dumps(["wifi", "center"]) # Заглушка, если поле пустое

    # Обработка фото (если ссылки нет, берем красивую заглушку с Unsplash)
    image_url = row.get('image_url', 'https://unsplash.com')
    if pd.isna(image_url) or not str(image_url).startswith('http'):
        image_url = 'https://unsplash.com'

    # Твоя продуктовая зона: ИИ-выжимка из отзывов
    # В пятницу сюда можно подключить API ChatGPT, но для скорости 
    # мы сгенерируем шаблон на основе реального рейтинга отеля
    if rating >= 4.7:
        ai_summary = f"🤖 ИИ: Великолепный отель в городе {city}. Гости отмечают безупречный сервис, чистоту и удобное расположение. Минусов практически нет."
    else:
        ai_summary = f"🤖 ИИ: Хороший сбалансированный вариант в городе {city}. Из плюсов: цена-качество и вежливый персонал. Минусы: мелкие недочеты в ремонте."

    # Собираем токен для полнотекстового поиска Postgres
    search_keywords = f"{city} отель {name} {raw_amenities}".lower()

    # Формируем итоговую SQL-команду INSERT
    sql = f"""INSERT INTO travel_cards (id, type, name, country, city, price, rating, image_url, amenities, ai_summary, search_vector) VALUES 
({hotel_id}, 'hotel', '{name}', 'Россия', '{city}', {price}, {rating}, '{image_url}', '{amenities_json}'::jsonb, '{ai_summary}', to_tsvector('russian', '{search_keywords}'));"""
    
    sql_statements.append(sql)

# Добавляем сброс счетчика автоинкремента в конец
sql_statements.append("\nSELECT setval(pg_get_serial_sequence('travel_cards', 'id'), COALESCE(MAX(id), 1)) FROM travel_cards;")

# 4. СОХРАНЕНИЕ В ФАЙЛ
with open('mock_data.sql', 'w', encoding='utf-8') as f:
    f.write('\n'.join(sql_statements))

print(f"\n🔥 Готово! Создан файл 'mock_data.sql' с {len(df_sample)} реальными отелями Островка.")
