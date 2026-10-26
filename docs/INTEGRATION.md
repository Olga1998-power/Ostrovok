# Интеграция с GrekEv/ostrovok

Исходный публичный проект: https://github.com/GrekEv/ostrovok

По публичному README (26.10.2026) оригинальная система использует Go API, PostgreSQL, Flutter, `backend/webapp` и endpoints `/v1/agent/chat`, `/v1/swipes`, `/v1/saved`, `/v1/profile`. Этот архив является самостоятельным дополнением, а не форком оригинального дерева: загрузить исходный GitHub ZIP в рабочей среде не удалось.

## План встраивания

1. Оставить оригинальный Go API и PostgreSQL ответственными за свайпы, гостевые профили и бронирования.
2. Разместить сервис Intelligence за `/intelligence/*` и UI за `/tg/intelligence/` через reverse proxy.
3. Добавить вызов `POST /intelligence/v1/search` в Go `POST /v1/agent/chat` для запросов, предполагающих поиск по характеристикам.
4. Связать `hotel_id` двух каталогов через отдельную `external_hotel_ids(provider,provider_id,intelligence_id)`.
5. Для внешнего запуска перенести SQLite-схему в PostgreSQL с миграциями; не смешивать демонстрационные отели с рабочим каталогом.
6. Передавать проверенную идентичность Telegram через подписанный серверный токен и ввести RBAC для отельеров.

## Контракты

`POST /v1/search`: `{ "query": "тихий номер с видом на закат у моря" }`.

`POST /v1/agent/chat`: `{ "message": "можно с собакой рядом с морем", "guestId": "demo" }`.

`POST /v1/hotelier/questions/{id}/answer`: `{ "text": "Пускаем собак до 10 кг" }`.

`POST /v1/features`: `{ "key": "has_garden", "label": "Сад", "description": "Есть сад" }`.

Обратите внимание: парсер отвечает за одно назначенное поле вопроса. Несколько полей из одного ответа требуют последовательных вопросов либо более развитого парсера.
