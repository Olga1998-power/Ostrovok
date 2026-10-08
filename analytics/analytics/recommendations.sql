-- Алгоритм: вытаскиваем карточки, которые пользователь еще НЕ свайпал, 
-- и сортируем их по релевантности на основе его прошлых ЛАЙКОВ.

WITH user_favorite_tags AS (
    -- Шаг 1: Берем все лайкнутые пользователем карточки и «разворачиваем» их JSONB-теги в список
    SELECT jsonb_array_elements_text(tc.amenities) AS tag,
           COUNT(*) AS tag_weight
    FROM user_swipes us
    JOIN travel_cards tc ON us.card_id = tc.id
    WHERE us.user_id = 'test_user_ios_123' AND us.action = 'like'
    GROUP BY tag
)
-- Шаг 2: Выбираем новые карточки и считаем их суммарный вес на основе любимых тегов юзера
SELECT tc.id, tc.name, tc.city, tc.price, tc.ai_summary,
       COALESCE(SUM(uft.tag_weight), 0) AS relevance_score
FROM travel_cards tc
LEFT JOIN user_favorite_tags uft ON uft.tag ?| ARRAY[tc.amenities->>0, tc.amenities->>1, tc.amenities->>2] -- проверка пересечения тегов
WHERE tc.id NOT IN (
    -- Исключаем отели, которые пользователь уже свайпнул (хоть влево, хоть вправо)
    SELECT card_id FROM user_swipes WHERE user_id = 'test_user_ios_123'
)
GROUP BY tc.id, tc.name, tc.city, tc.price, tc.ai_summary
ORDER BY relevance_score DESC, tc.rating DESC -- Сначала самые релевантные по вкусу, затем по рейтингу
LIMIT 10;
