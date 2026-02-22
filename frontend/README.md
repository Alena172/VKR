# Frontend (React + Tailwind)

## Быстрый старт

```bash
cd frontend
copy .env.example .env
npm install
npm run dev
```

## Быстрый запуск всего контура через Docker Compose

Из корня репозитория:

```bash
docker compose up -d --build
```

После запуска:
- frontend: `http://localhost:5173`
- backend API: `http://localhost:8000`

По умолчанию фронт обращается к backend:
- `VITE_API_BASE_URL=http://localhost:8000/api/v1`

## Что уже реализовано
- Панель статуса AI (`/ai/status`) с индикацией remote ON/OFF
- Блок Auth (JWT): вход/регистрация одним шагом (`/auth/login-or-register`) + проверка токена (`/auth/verify`)
- `auth/me` для подтягивания `user_id` из JWT
- Словарь через `vocabulary/me` + добавление слов через `study-flow/me/capture-to-vocabulary`
- Экран повторения (review queue, review plan, review summary) через `context/me` + `analytics/review-summary/me`
- Отправка результатов повторения (`review-queue/submit`)
- Генерация упражнений и отправка сессии (`exercises/me/generate`, `sessions/submit`)
- Экран истории сессий через `sessions/me` и `sessions/me/{session_id}/answers`
- В истории сессий есть серверные фильтры по `accuracy` и дате, а также серверная пагинация
