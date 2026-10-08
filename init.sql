-- 1. ТАБЛИЦА КАРТОЧЕК (Отели, мотели, хостелы, туры, перелеты)
CREATE TABLE IF NOT EXISTS travel_cards (
    id SERIAL PRIMARY KEY,
    type VARCHAR(50) NOT NULL,         -- 'hotel', 'motel', 'hostel', 'tour', 'flight'
    name VARCHAR(255) NOT NULL,
    country VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,     -- Цена (за ночь или за тур)
    rating NUMERIC(3, 1) NOT NULL,     -- Рейтинг (например, 4.8)
    image_url TEXT NOT NULL,           -- Ссылка на фотографию карточки
    
    -- JSONB-массив для гибких тегов Островка, например: ["spa", "pool", "low_cost"]
    amenities JSONB DEFAULT '[]'::jsonb, 
    
    -- Поле для короткой выжимки отзывов от ИИ
    ai_summary TEXT,           
    
    -- Встроенный вектор для честного полнотекстового поиска ИИ-агентом
    search_vector tsvector
);

-- Индексы для обеспечения молниеносной скорости поиска на Go-бэкенде
CREATE INDEX IF NOT EXISTS travel_cards_search_idx ON travel_cards USING gin(search_vector);
CREATE INDEX IF NOT EXISTS travel_cards_amenities_idx ON travel_cards USING gin(amenities);


-- 2. ТАБЛИЦА ВЗАИМОДЕЙСТВИЙ (Лог Tinder-свайпов для рекомендаций)
CREATE TABLE IF NOT EXISTS user_swipes (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,     -- ID сессии или пользователя с мобилки
    card_id INT NOT NULL REFERENCES travel_cards(id) ON DELETE CASCADE,
    action VARCHAR(20) NOT NULL,       -- 'like' (свайп вправо), 'dislike' (свайп влево)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индекс для быстрой выборки истории лайков пользователя
CREATE INDEX IF NOT EXISTS user_swipes_user_idx ON user_swipes(user_id);
