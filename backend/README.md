# Backend (модульный монолит)

## Быстрый старт

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -e .
```

## Запуск всего проекта одной командой (root compose)

Из корня репозитория:

```bash
docker compose up -d --build
```

Проверка:
- backend: `http://localhost:8000/health`
- frontend: `http://localhost:5173`
- postgres: `localhost:15432`

Остановка:

```bash
docker compose down
```

## Запуск полного контура (backend + frontend)

1. Backend:
```bash
cd backend
copy .env.example .env
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```
2. Frontend:
```bash
cd ../frontend
copy .env.example .env
npm install
npm run dev
```

## Запуск с PostgreSQL

```bash
copy .env.example .env
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```

## Запуск тестов

```bash
pytest -q
```

## Переменные окружения

Файл `.env` в `backend/`:

```env
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:15432/vkr_db
AI_PROVIDER=stub
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=
AI_MODEL=gpt-4o-mini
AI_TIMEOUT_SECONDS=20
AI_MAX_RETRIES=1
TRANSLATION_STRICT_REMOTE=true
JWT_SECRET=change_me
JWT_ISSUER=vkr
JWT_ACCESS_TTL_MINUTES=1440
```

Провайдер AI:
- `AI_PROVIDER=stub` — локальные deterministic-ответы (режим по умолчанию)
- `AI_PROVIDER=openai_compatible` + `AI_API_KEY` — удаленный LLM через OpenAI-compatible `/chat/completions`
- `AI_PROVIDER=ollama` — удаленный LLM через локальный Ollama (`/chat/completions` совместимый `/v1`)
- `AI_MAX_RETRIES` — количество повторных попыток remote-запроса при ошибках сети/провайдера
- `TRANSLATION_STRICT_REMOTE=true` — строгий режим перевода: если remote AI недоступен, `/translate/*` и `study-flow` возвращают `503` вместо локального fallback

Пример `.env` для Ollama (если backend запущен в Docker, Ollama на хосте):

```env
AI_PROVIDER=ollama
AI_BASE_URL=http://host.docker.internal:11434/v1
AI_API_KEY=
AI_MODEL=llama3.1:8b
TRANSLATION_STRICT_REMOTE=true
```

Диагностика AI:
- `GET /api/v1/ai/status` — текущая конфигурация AI (provider/model/remote_enabled/timeout/retries)

## Аутентификация (JWT)

`POST /api/v1/auth/token`:
- принимает `email`
- возвращает `access_token` (JWT) и `user_id`

`POST /api/v1/auth/login-or-register`:
- принимает `email`, `full_name`, `cefr_level`
- если пользователя нет, создает его и сразу возвращает JWT
- если пользователь уже есть, выполняет вход и возвращает JWT

`POST /api/v1/auth/verify`:
- принимает `token`
- возвращает `valid` и `user_id`, если токен валиден

`GET /api/v1/auth/me`:
- возвращает `user_id` из токена

Примечание:
- для user-bound эндпоинтов требуется `Authorization: Bearer <token>`
- большинство эндпоинтов принимают `user_id`, но если он не передан, используется `user_id` из JWT
- для новых endpoint-first сценариев доступны `me`-маршруты (например, `/api/v1/vocabulary/me`, `/api/v1/context/me/*`)

## Словарь

`GET /api/v1/vocabulary/me`:
- возвращает словарь текущего пользователя из JWT

`POST /api/v1/vocabulary/me`:
- добавляет слово в словарь текущего пользователя
- принимает `english_lemma`, `russian_translation`, `source_sentence`, `source_url`

## Capture

`GET /api/v1/capture/me`:
- возвращает историю capture текущего пользователя

`POST /api/v1/capture/me`:
- сохраняет выделение текущего пользователя
- принимает `selected_text`, `source_url`, `source_sentence`

## Перевод и упражнения

`POST /api/v1/translate/me`:
- перевод EN->RU для текущего пользователя
- принимает `text`, `source_context`
- в строгом режиме (`TRANSLATION_STRICT_REMOTE=true`) требует доступный remote AI (`AI_PROVIDER=ollama` или `AI_PROVIDER=openai_compatible` + `AI_API_KEY`), иначе вернет `503`

`POST /api/v1/exercises/me/generate`:
- генерирует упражнения для текущего пользователя
- принимает `size`, `vocabulary_ids`

## Миграции

```bash
alembic upgrade head
alembic downgrade -1
```

## Ответ `sessions/submit`

`POST /api/v1/sessions/submit` возвращает:
- `session`: агрегированную статистику по сессии (`total`, `correct`, `accuracy`)
- `incorrect_feedback`: AI-объяснения на русском для неверных ответов, где переданы `prompt` и `expected_answer`
- при неверных ответах слово из `prompt` автоматически добавляется в `context_memory.difficult_words`

## История ответов сессии

`GET /api/v1/sessions/{session_id}/answers?user_id={user_id}` возвращает ответы по упражнениям (параметр `user_id` опционален):
- `prompt`, `expected_answer`, `user_answer`
- `is_correct`
- `explanation_ru` для ошибочных ответов (если была сгенерирована)

`GET /api/v1/sessions/me`:
- возвращает историю сессий текущего пользователя c серверными фильтрами и пагинацией
- query-параметры: `limit`, `offset`, `min_accuracy`, `max_accuracy`, `date_from`, `date_to`
- ответ: `total`, `limit`, `offset`, `items[]`

`GET /api/v1/sessions/me/{session_id}/answers`:
- возвращает ответы конкретной сессии текущего пользователя

## Рекомендации на повторение

`GET /api/v1/context/{user_id}/recommendations?limit=10` возвращает (есть аналог `/api/v1/context/me/recommendations`):
- `words`: объединенный приоритетный список слов на повторение
- `recent_error_words`: слова из последних ошибок пользователя
- `difficult_words`: слова из `context_memory`
- `scores`: числовой вес слова для ранжирования (чем выше, тем выше приоритет)
- `next_review_at`: дата/время следующего рекомендованного повторения по каждому слову

Приоритизация `words`:
- частота ошибок (чем чаще слово ошибочно, тем выше)
- свежесть ошибок (последние ошибки весят больше)
- бонус словам из `difficult_words`
- бонус словам, у которых наступило время повторения (`next_review_at <= now`)

## Очередь повторения (SRS)

`GET /api/v1/context/{user_id}/review-queue?limit=20` возвращает только слова, у которых уже наступило время повторения (есть аналог `/api/v1/context/me/review-queue`):
- `total_due`: сколько слов сейчас ожидает повторения
- `items`: элементы очереди
- для каждого элемента: `word`, `russian_translation`, `next_review_at`, `error_count`, `correct_streak`

`POST /api/v1/context/{user_id}/review-queue/submit` принимает результат повторения (есть аналог `/api/v1/context/me/review-queue/submit`):
- тело запроса: `word`, `is_correct`
- обновляет SRS-прогресс слова (`error_count`, `correct_streak`, `next_review_at`)
- при ошибке автоматически добавляет слово в `difficult_words`
- в ответе возвращает `russian_translation`, если слово есть в словаре пользователя

`POST /api/v1/context/{user_id}/review-queue/submit-bulk` принимает пачку результатов (есть аналог `/api/v1/context/me/review-queue/submit-bulk`):
- тело запроса: `items[]` с полями `word`, `is_correct`
- возвращает `updated[]` с обновленным состоянием SRS по каждому слову
- `updated[]` также содержит `russian_translation`, если перевод найден в словаре

## Просмотр прогресса слов

`GET /api/v1/context/{user_id}/word-progress?limit=20&offset=0&status=all&q=&sort_by=next_review_at&sort_order=asc&min_streak=3&min_errors=3` возвращает список SRS-прогресса (есть аналог `/api/v1/context/me/word-progress`):
- `total`, `limit`, `offset`
- `items` с полями `word`, `russian_translation`, `error_count`, `correct_streak`, `next_review_at`
- `status`: `all | due | upcoming | mastered | troubled`
- `q`: фильтр по подстроке слова
- `sort_by`: `next_review_at | error_count | correct_streak`
- `sort_order`: `asc | desc`
- `min_streak`: порог для статуса `mastered`
- `min_errors`: порог для статуса `troubled`

`GET /api/v1/context/{user_id}/word-progress/{word}` возвращает прогресс по конкретному слову (есть аналог `/api/v1/context/me/word-progress/{word}`).

`DELETE /api/v1/context/{user_id}/word-progress/{word}` удаляет прогресс слова (есть аналог `/api/v1/context/me/word-progress/{word}`):
- `progress_deleted`: удалена ли запись SRS-прогресса
- `removed_from_difficult_words`: удалено ли слово из `difficult_words`

## План повторения

`GET /api/v1/context/{user_id}/review-plan?limit=10&horizon_hours=24` возвращает единый план для UI (есть аналог `/api/v1/context/me/review-plan`):
- `due_count`: количество слов для повторения сейчас (в рамках `limit`)
- `upcoming_count`: количество слов, которые станут due в заданном горизонте (в рамках `limit`)
- `due_now`: слова, которые нужно повторять прямо сейчас
- `upcoming`: слова, которые станут due в заданном горизонте `horizon_hours`
- `recommended_words`: ранжированный список слов по сигналам ошибок и контекста

## SRS-аналитика

`GET /api/v1/analytics/review-summary?user_id={user_id}&min_streak=3&min_errors=3` возвращает (есть аналог `/api/v1/analytics/review-summary/me`):
- `total_tracked`: всего слов в SRS-трекинге
- `due_now`: сколько слов нужно повторять сейчас
- `mastered`: сколько слов стабилизированы (по текущему порогу streak)
- `troubled`: сколько слов остаются проблемными (по текущему порогу ошибок)

## Personal Learning Graph

`GET /api/v1/learning-graph/me/overview`:
- агрегаты графа пользователя: интересы, кластеры, senses, события ошибок, количество связей
- топ интересов, топ кластеров, топ тегов ошибок

`GET /api/v1/learning-graph/me/interests`:
- список интересов пользователя с весами

`PUT /api/v1/learning-graph/me/interests`:
- upsert интересов пользователя
- тело: `interests[]` с полями `interest`, `weight`

`POST /api/v1/learning-graph/me/semantic-upsert`:
- семантическая дедупликация словаря по паре (`english_lemma`, `semantic_key`)
- автоматически назначает `topic_cluster`
- может создать связь с существующим `vocabulary_item` через `vocabulary_item_id`

`GET /api/v1/learning-graph/me/recommendations?mode=mixed&limit=10`:
- рекомендации слов из графа
- режимы: `interest`, `weakness`, `mixed`
- для каждого слова возвращаются `score`, `reasons`, `topic_cluster`, `mistake_count`

## Сквозной orchestration-flow

`POST /api/v1/study-flow/capture-to-vocabulary` выполняет в одном запросе:
- сохранение `capture` (данные из расширения)
- перевод выбранного слова через AI
- добавление в `vocabulary` (с дедупликацией по лемме)
- инициализацию SRS-прогресса в `word_progress`

Параметры:
- `force_new_vocabulary_item`: принудительно создать новую словарную запись даже при дубле

`POST /api/v1/study-flow/me/capture-to-vocabulary`:
- тот же orchestration-flow для текущего пользователя из JWT
- рекомендуется для frontend/extension как основной endpoint

## Интеграция с расширением

Расширение браузера использует backend endpoints:
- `POST /api/v1/translate/me`
- `POST /api/v1/study-flow/me/capture-to-vocabulary`

Папка расширения:
- `../extension`

## Текущие модули
- auth
- users
- vocabulary
- capture
- translation
- exercise_engine
- learning_session
- context_memory
- ai_services
- analytics

Языки зафиксированы бизнес-правилом:
- Родной язык: русский (RU)
- Изучаемый язык: английский (EN)
