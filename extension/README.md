# Browser Extension (Manifest V3)

## Что умеет
- Получает выделенный текст с активной страницы
- Переводит выделение через `POST /api/v1/translate/me`
- Добавляет слово в словарь через `POST /api/v1/vocabulary/me/from-capture`

## Установка (Chrome/Edge)
1. Открой страницу `chrome://extensions` (или `edge://extensions`)
2. Включи режим разработчика
3. Нажми "Load unpacked" и выбери папку `extension`

## Требования
- Backend запущен на `http://localhost:8000`
- Существует пользователь в системе (расширение получает `user_id` из `/api/v1/auth/me`)
- Для работы нужно получить JWT через кнопку "Получить токен" (email пользователя)

