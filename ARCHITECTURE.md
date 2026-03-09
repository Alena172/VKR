# Архитектура платформы ContextVocab

## Обзор системы

**ContextVocab** — образовательная платформа для изучения английского языка носителями русского языка. Система использует модульный монолит на backend, современное SPA на frontend и браузерное расширение для захвата контекста из веб-страниц.

### Ключевые характеристики

| Параметр | Значение |
|----------|----------|
| **Тип приложения** | Модульный монолит + SPA + браузерное расширение |
| **Языки** | Родной — русский (RU), Изучаемый — английский (EN) |
| **Основная функция** | Контекстное изучение слов с AI-помощником и SRS-повторением |
| **Асинхронные задачи** | Celery + Redis (фоновая обработка) |
| **Мониторинг задач** | Flower (веб-интерфейс) |

---

## Архитектурная диаграмма

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Клиентские приложения                          │
├─────────────────────┬─────────────────────┬─────────────────────────────────┤
│  Browser Extension  │   Frontend (React)  │         API Clients             │
│  (Manifest V3)      │   + Vite + Tailwind │                                 │
│  - content.js       │   - App.jsx         │  - Chrome Storage API           │
│  - popup.html/js    │   - pages/*         │  - localStorage (token, userId) │
│  - захват текста    │   - components/*    │  - JWT Authorization            │
└─────────┬───────────┴──────────┬──────────┴────────────┬────────────────────┘
          │                      │                       │
          │ HTTP/JSON            │ HTTP/JSON             │ HTTP/JSON
          │ JWT Bearer           │ JWT Bearer            │ JWT Bearer
          ▼                      ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Backend (FastAPI)                                 │
│                     Модульный монолит (Python 3.11+)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  API Router (api/v1)                                                        │
│  ├── /auth/*         — аутентификация и идентификация                       │
│  ├── /users/*        — управление пользователями                            │
│  ├── /vocabulary/*   — словарь пользователя                                 │
│  ├── /capture/*      — прием данных из расширения                           │
│  ├── /translate/*    — AI-перевод EN→RU                                     │
│  ├── /exercises/*    — генерация упражнений                                 │
│  ├── /sessions/*     — учебные сессии и ответы                              │
│  ├── /context/*      — контекстная память и SRS                             │
│  ├── /learning-graph/* — персональный граф обучения                         │
│  ├── /study-flow/*   — сквозные orchestration-сценарии                      │
│  ├── /analytics/*    — метрики прогресса                                    │
│  ├── /ai/*           — диагностика AI-провайдера                            │
│  └── /tasks/*        — polling статуса фоновых задач                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  Модули (app/modules/)                                                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │   auth     │ │   users    │ │ vocabulary │ │  capture   │               │
│  │  (JWT)     │ │  (CEFR)    │ │  (слова)   │ │ (захват)   │               │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘               │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │translation │ │ exercise   │ │  learning  │ │  context   │               │
│  │    (AI)    │ │  engine    │ │  session   │ │   memory   │               │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘               │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐               │
│  │    ai_     │ │ analytics  │ │  learning  │ │  study_    │               │
│  │  services  │ │ (метрики)  │ │   graph    │ │   flow     │               │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘               │
│  ┌────────────┐ ┌────────────┐                                              │
│  │   tasks    │ │learning_   │                                              │
│  │ (polling)  │ │   path     │ (empty)                                      │
│  └────────────┘ └────────────┘                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Фоновые задачи (app/tasks/)                                                │
│  ├── vocabulary_tasks.py — асинхронные операции со словарём                │
│  └── exercise_tasks.py — генерация упражнений в фоне                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  Celery Worker                                                              │
│  ├── Broker: Redis (db/0) — очередь задач                                  │
│  ├── Backend: Redis (db/1) — хранение результатов                          │
│  └── Concurrency: 4 worker'а                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  Core (app/core/)                                                           │
│  ├── config.py     — настройки через pydantic-settings                      │
│  ├── db.py         — SQLAlchemy сессии и Base модель                        │
│  └── api.py        — централизованная регистрация роутеров                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  AI Services (фасад)                                                        │
│  ├── stub — локальные deterministic-ответы (по умолчанию)                   │
│  ├── openai_compatible — внешний /chat/completions API                      │
│  └── ollama — локальный LLM через совместимый API                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Слой персистентности                                   │
├─────────────────────────────────┬───────────────────────────────────────────┤
│  PostgreSQL 16 (порт 15432)     │  Redis 7 (порт 6379)                      │
│  ┌─────────────────────────┐   │  ┌─────────────────────────────────────┐  │
│  │  Таблицы по модулям:    │   │  │  Redis DB/0 — Celery Broker         │  │
│  │  - users                │   │  │  Redis DB/1 — Celery Backend        │  │
│  │  - vocabulary_items     │   │  │  - очередь задач                    │  │
│  │  - captures             │   │  │  - результаты задач                 │  │
│  │  - learning_sessions    │   │  │  - временные данные сессий          │  │
│  │  - learning_session_ans.│   │  └─────────────────────────────────────┘  │
│  │  - word_progress        │   │                                           │
│  │  - context_memory       │   │                                           │
│  │  - learning_graph_*     │   │                                           │
│  └─────────────────────────┘   │                                           │
└─────────────────────────────────┴───────────────────────────────────────────┘
```

---

## Технологический стек

### Backend
| Компонент | Технология | Версия |
|-----------|------------|--------|
| Фреймворк | FastAPI | ≥0.115.0 |
| Язык | Python | ≥3.11 |
| ORM | SQLAlchemy | ≥2.0.32 |
| Миграции | Alembic | ≥1.13.2 |
| Валидация | Pydantic | ≥2.8.0 |
| JWT | PyJWT | ≥2.9.0 |
| Тесты | pytest | ≥8.3.0 |
| HTTP-клиент | httpx | ≥0.27.0 |
| Очереди | Celery | latest |
| Брокер | Redis | 7-alpine |
| БД | PostgreSQL | 16-alpine |

### Frontend
| Компонент | Технология | Версия |
|-----------|------------|--------|
| Фреймворк | React | 18.3.1 |
| Роутинг | react-router-dom | 6.28.2 |
| Сборка | Vite | 5.4.2 |
| Стили | Tailwind CSS | 3.4.10 |
| Иконки | lucide-react | 0.545.0 |

### Browser Extension
| Компонент | Технология |
|-----------|------------|
| Manifest | Manifest V3 |
| API | Chrome Extension API |
| Хранение | chrome.storage.local |

### Инфраструктура
| Компонент | Назначение |
|-----------|------------|
| Redis DB/0 | Celery broker (очередь задач) |
| Redis DB/1 | Celery backend (результаты) |
| Flower | Веб-интерфейс мониторинга Celery (порт 5555) |

---

## Модули backend

### 1. auth (Аутентификация)
**Ответственность**: JWT-аутентификация и идентификация пользователей

**Эндпоинты**:
- `POST /auth/token` — получение токена по email
- `POST /auth/login-or-register` — вход или регистрация одним запросом
- `POST /auth/verify` — проверка валидности токена
- `GET /auth/me` — получение user_id из токена
- `GET /auth/ping` — healthcheck модуля

**Ключевые файлы**:
- `router.py` — HTTP-обработчики
- `service.py` — бизнес-логика (создание/верификация JWT)
- `dependencies.py` — зависимости для получения current_user_id
- `schemas.py` — Pydantic-схемы запросов/ответов

---

### 2. users (Пользователи)
**Ответственность**: Управление профилями пользователей и CEFR-уровнем

**Модель данных**:
- `id` — первичный ключ
- `email` — уникальный email
- `full_name` — имя пользователя
- `cefr_level` — уровень владения языком (A1-C2)

**Репозиторий**: `users_repository` — CRUD-операции

---

### 3. vocabulary (Словарь)
**Ответственность**: Хранение словаря пользователя (английская лемма + русский перевод)

**Модель данных**:
- `id` — первичный ключ
- `user_id` — внешний ключ на users
- `english_lemma` — английское слово (уникально в пределах пользователя)
- `russian_translation` — перевод
- `context_definition_ru` — AI-сгенерированное определение контекста
- `source_sentence` — предложение-источник
- `source_url` — URL источника

**Эндпоинты**:
- `GET /vocabulary/me` — список слов текущего пользователя
- `POST /vocabulary/me` — добавление слова (с AI-генерацией контекста)
- `PUT /vocabulary/me/{item_id}` — обновление слова
- `DELETE /vocabulary/me/{item_id}` — удаление слова

**Асинхронные задачи**:
- `vocabulary_tasks.py` — фоновая обработка операций со словарём

**Правила**:
- Прямой доступ к таблицам другого модуля запрещён
- Контекстное определение генерируется через `ai_services`

---

### 4. capture (Захват контекста)
**Ответственность**: Прием данных из браузерного расширения

**Модель данных**:
- `id` — первичный ключ
- `user_id` — внешний ключ на users
- `selected_text` — выделенный текст
- `source_sentence` — предложение-контекст
- `source_url` — URL страницы
- `created_at` — время захвата

**Эндпоинты**:
- `GET /capture/me` — история захватов пользователя
- `POST /capture/me` — сохранение нового выделения

---

### 5. translation (Перевод)
**Ответственность**: AI-перевод английского текста на русский

**Интеграция с AI**:
- Использует `ai_services` как фасад
- Поддерживает строгий режим (`TRANSLATION_STRICT_REMOTE`)
- В строгом режиме возвращает `503` при недоступности remote AI

**Эндпоинты**:
- `POST /translate/me` — перевод текста для текущего пользователя

**Параметры запроса**:
- `text` — текст для перевода
- `source_context` — опциональный контекст

---

### 6. exercise_engine (Генерация упражнений)
**Ответственность**: Создание учебных заданий на основе словаря пользователя

**Типы упражнений**:
- Перевод предложений
- Выбор правильного перевода
- Сопоставление слов и определений

**Эндпоинты**:
- `POST /exercises/me/generate` — генерация упражнений

**Параметры**:
- `size` — количество упражнений
- `vocabulary_ids` — опциональный фильтр по словам

**Асинхронные задачи**:
- `exercise_tasks.py` — фоновая генерация упражнений

---

### 7. learning_session (Учебные сессии)
**Ответственность**: Сохранение результатов сессий и AI-обратная связь

**Модель данных**:
- `learning_sessions`:
  - `id`, `user_id`, `total`, `correct`, `accuracy`, `created_at`
- `learning_session_answers`:
  - `id`, `session_id`, `exercise_id`, `prompt`, `expected_answer`, `user_answer`, `is_correct`, `explanation_ru`

**Эндпоинты**:
- `POST /sessions/submit` — отправка результатов сессии
- `GET /sessions/me` — история сессий (с фильтрами и пагинацией)
- `GET /sessions/me/{session_id}/answers` — ответы конкретной сессии

**AI-сценарии**:
- Объяснение ошибок (`explain_error`)
- Семантическая проверка перевода (`is_translation_semantically_correct`)
- Советы по улучшению (`suggest_improvement`)

**Автоматические действия**:
- Слова из ошибок добавляются в `difficult_words`
- События ошибок сохраняются в `learning_graph`
- Обновляется SRS-прогресс (`word_progress`)

---

### 8. context_memory (Контекстная память)
**Ответственность**: Хранение учебных сигналов и SRS-прогресса

**Модель данных**:
- `context_memory`:
  - `user_id`, `difficult_words` (JSONB)
- `word_progress`:
  - `user_id`, `word`, `russian_translation`, `error_count`, `correct_streak`, `next_review_at`

**Эндпоинты**:
- `GET /context/me/review-queue` — очередь слов на повторение
- `POST /context/me/review-queue/submit` — отправка результата повторения
- `POST /context/me/review-queue/submit-bulk` — пакетное обновление SRS
- `GET /context/me/word-progress` — прогресс слов (с фильтрами)
- `DELETE /context/me/word-progress/{word}` — удаление прогресса
- `GET /context/me/review-plan` — план повторения

**SRS-алгоритм**:
- `correct_streak` увеличивается при правильном ответе
- `error_count` увеличивается при ошибке
- `next_review_at` рассчитывается на основе интервалов
- Слова с ошибками автоматически попадают в `difficult_words`

---

### 9. learning_graph (Персональный граф обучения)
**Ответственность**: Моделирование интересов, семантических связей и ошибок

**Модель данных**:
- `learning_graph_interests`:
  - `user_id`, `interest`, `weight`
- `learning_graph_word_senses`:
  - `user_id`, `english_lemma`, `semantic_key`, `russian_translation`, `topic_cluster_id`
- `learning_graph_topic_clusters`:
  - `user_id`, `cluster_key`, `name`, `description`
- `learning_graph_mistake_events`:
  - `user_id`, `english_lemma`, `prompt`, `expected_answer`, `user_answer`, `created_at`

**Эндпоинты**:
- `GET /learning-graph/me/overview` — агрегированная картина графа
- `GET /learning-graph/me/interests` — список интересов
- `PUT /learning-graph/me/interests` — upsert интересов
- `POST /learning-graph/me/semantic-upsert` — семантическая дедупликация
- `GET /learning-graph/me/recommendations` — рекомендации (interest|weakness|mixed)

**Режимы рекомендаций**:
- `interest` — слова по интересам пользователя
- `weakness` — слова с наибольшим количеством ошибок
- `mixed` — комбинация обоих сигналов

---

### 10. study_flow (Сквозные сценарии)
**Ответственность**: Orchestration между модулями для клиентских сценариев

**Эндпоинты**:
- `POST /study-flow/me/capture-to-vocabulary` — полный цикл:
  1. Сохранение `capture`
  2. Перевод через AI
  3. Добавление в `vocabulary` (с дедупликацией)
  4. Инициализация SRS-прогресса
  5. Синхронизация `learning_graph.word_senses`

**Параметры**:
- `selected_text` — выделенный текст
- `source_sentence` — предложение-контекст
- `source_url` — URL источника
- `force_new_vocabulary_item` — принудительно создать новую запись

---

### 11. analytics (Аналитика)
**Ответственность**: Агрегация метрик прогресса

**Эндпоинты**:
- `GET /analytics/review-summary/me` — сводка SRS-состояния:
  - `total_tracked` — всего слов в трекинге
  - `due_now` — готовы к повторению сейчас
  - `mastered` — стабилизированные слова
  - `troubled` — проблемные слова

---

### 12. ai_services (AI-фасад)
**Ответственность**: Централизованный доступ к AI/ML-инференсу

**Поддерживаемые провайдеры**:
- `stub` — локальные deterministic-ответы (по умолчанию)
- `openai_compatible` — внешний API через `/chat/completions`
- `ollama` — локальный LLM

**Конфигурация**:
- `AI_PROVIDER` — выбор провайдера
- `AI_BASE_URL` — базовый URL API
- `AI_API_KEY` — опциональный ключ
- `AI_MODEL` — название модели
- `AI_TIMEOUT_SECONDS` — таймаут запроса
- `AI_MAX_RETRIES` — количество повторных попыток

**Эндпоинты**:
- `GET /ai/status` — диагностика текущей конфигурации

**AI-функции**:
- `generate_context_definition()` — определение слова в контексте
- `translate_text()` — перевод EN→RU
- `explain_error()` — объяснение ошибки
- `is_translation_semantically_correct()` — семантическая проверка
- `suggest_improvement()` — совет по улучшению

---

### 13. tasks (Polling задач)
**Ответственность**: Предоставление API для polling статуса фоновых задач Celery

**Эндпоинты**:
- `GET /tasks/{task_id}` — получение статуса задачи:
  - `PENDING` — задача ещё не началась
  - `STARTED` — задача выполняется
  - `SUCCESS` — задача завершена успешно
  - `FAILURE` — задача завершилась ошибкой
  - `RETRY` — задача выполняется повторно
  - `REVOKED` — задача отменена

**Ответ**:
```json
{
  "task_id": "uuid",
  "status": "SUCCESS",
  "result": {...},
  "error": null
}
```

---

### 14. learning_path (Заготовки)
**Статус**: Пустой модуль (резерв для будущего функционала)

**Потенциальное назначение**:
- Индивидуальные траектории обучения
- План изучения тем
- Прогресс по уровням CEFR

---

## Интеграционные правила

### Межмодульное взаимодействие
1. **Явные интерфейсы**: Модули взаимодействуют через сервисные интерфейсы или API-контракты
2. **Запрет прямого доступа**: Прямой доступ к таблицам другого модуля запрещён
3. **Централизованный AI**: Все AI-вызовы через `ai_services`

### Аутентификация
1. **JWT-токены**: Все user-bound эндпоинты требуют `Authorization: Bearer <token>`
2. **user_id из токена**: Если `user_id` передан в query, он должен совпадать с токеном (иначе `403`)
3. **me-маршруты**: Новые эндпоинты используют `me` (например, `/vocabulary/me`) без явного `user_id`

### Ошибки доступа
- `401 Unauthorized` — отсутствие или невалидность токена
- `403 Forbidden` — несовпадение `user_id` и токена

---

## Асинхронная обработка (Celery)

### Архитектура
```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   FastAPI    │ ──►  │    Redis     │ ──► │   Celery     │
│   (задача)   │      │   (broker)   │      │   Worker     │
└──────────────┘      └──────────────┘      └──────────────┘
                              │                     │
                              ▼                     ▼
                       ┌──────────────┐      ┌──────────────┐
                       │    Redis     │      │   Flower     │
                       │   (backend)  │      │  (monitor)   │
                       └──────────────┘      └──────────────┘
```

### Конфигурация Celery
- **Broker**: `redis://redis:6379/0`
- **Backend**: `redis://redis:6379/1`
- **Worker concurrency**: 4
- **Task serializer**: JSON
- **Result expires**: 3600 секунд (1 час)
- **Ack late**: true (подтверждение после выполнения)
- **Prefetch multiplier**: 1

### Задачи
| Задача | Модуль | Назначение |
|--------|--------|------------|
| `vocabulary_tasks` | vocabulary | Фоновые операции со словарём |
| `exercise_tasks` | exercise_engine | Генерация упражнений |

### Мониторинг (Flower)
- **URL**: `http://localhost:5555`
- **Возможности**:
  - Просмотр активных задач
  - История выполненных задач
  - Статистика worker'ов
  - Управление задачами (revoke, terminate)

---

## Слои данных

### Персистентные модули (SQLAlchemy + PostgreSQL)
- `users`
- `vocabulary`
- `capture`
- `context_memory`
- `learning_sessions`
- `learning_session_answers`
- `analytics` (рассчитывается агрегацией)
- `learning_graph_*`

### Временное хранилище (Redis)
- Очередь задач Celery
- Результаты выполнения задач
- Сессионные данные

### AI-сценарии (локальный stub или remote)
- `translation`
- `exercise_engine`
- `explain_error` (в `learning_session`)
- `ai_services` (фасад)

---

## Миграции БД

**Инструмент**: Alembic

**Команды**:
```bash
# Применить все миграции
alembic upgrade head

# Откатить последнюю миграцию
alembic downgrade -1

# Создать новую миграцию
alembic revision --autogenerate -m "description"
```

**Расположение**: `backend/alembic/versions/`

**Начальная миграция**: `0001_initial_schema.py`

---

## Развертывание

### Docker Compose (полный стек)

**Файл**: `docker-compose.yml` (в корне)

**Сервисы**:

| Сервис | Порт | Описание |
|--------|------|----------|
| **postgres** | 15432 | PostgreSQL 16-alpine |
| **redis** | 6379 | Redis 7-alpine |
| **backend** | 8000 | FastAPI приложение |
| **celery_worker** | — | Worker для фоновых задач |
| **flower** | 5555 | Мониторинг Celery |
| **frontend** | 5173 | React + Vite |

**Команды**:
```bash
# Запуск всего стека
docker compose up -d --build

# Просмотр логов
docker compose logs -f

# Остановка
docker compose down

# Остановка с удалением томов
docker compose down -v
```

**Проверка**:
- Backend: `http://localhost:8000/health`
- Frontend: `http://localhost:5173`
- Flower: `http://localhost:5555`
- PostgreSQL: `localhost:15432`
- Redis: `localhost:6379`

---

## Переменные окружения

### Backend (.env)

```env
# Database
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:15432/vkr_db

# AI Provider
AI_PROVIDER=stub
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=
AI_MODEL=gpt-4o-mini
AI_TIMEOUT_SECONDS=20
AI_MAX_RETRIES=1
TRANSLATION_STRICT_REMOTE=true

# JWT
JWT_SECRET=change_me
JWT_ISSUER=vkr
JWT_ACCESS_TTL_MINUTES=1440

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
REDIS_URL=redis://localhost:6379/0
```

### Frontend (.env)

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

---

## Клиентские сценарии

### 1. Вход в систему
```
Frontend → POST /auth/login-or-register {email, full_name, cefr_level}
          ← {access_token, user_id, is_new_user}
Frontend → localStorage.setItem('vkr_auth_token', token)
Frontend → GET /auth/me (подтверждение user_id из токена)
```

### 2. Добавление слова из расширения
```
Extension → захват выделения (content.js)
          → popup.js: POST /study-flow/me/capture-to-vocabulary
          ← {vocabulary_item, word_progress, capture}
Extension → отображение результата в popup
```

### 3. Учебная сессия
```
Frontend → POST /exercises/me/generate {size, vocabulary_ids}
          ← exercises[]

Frontend → отображение упражнений
         → ввод ответов пользователем

Frontend → POST /sessions/submit {answers[]}
          ← {session, incorrect_feedback[], advice_feedback[]}

Backend → AI-объяснения ошибок
        → обновление SRS
        → добавление в difficult_words
        → сохранение mistake_event в learning_graph
```

### 4. Повторение по SRS
```
Frontend → GET /context/me/review-queue?limit=20
          ← {total_due, items[]}

Frontend → POST /context/me/review-queue/submit-bulk {items[]}
          ← {updated[]}

Backend → обновление correct_streak / error_count
        → пересчёт next_review_at
```

### 5. Фоновая генерация упражнений (Celery)
```
Frontend → POST /exercises/me/generate-async {size}
          ← {task_id: "uuid"}

Frontend → GET /tasks/{task_id} (polling)
          ← {status: "PENDING"}
          ← {status: "STARTED"}
          ← {status: "SUCCESS", result: exercises[]}
```

---

## Безопасность

### JWT-аутентификация
- **Алгоритм**: HS256 (подразумевается)
- **Время жизни**: 1440 минут (24 часа)
- **Issuer**: `vkr`
- **Секрет**: `JWT_SECRET` (из .env)

### CORS
- Backend разрешает все origins (`allow_origins=["*"]`)
- **В продакшене**: ограничить список разрешённых origins

### Валидация данных
- Pydantic-схемы для всех запросов/ответов
- Email-валидация через `email-validator`
- Строгая типизация через mypy

### Хранение токенов
- **Frontend**: localStorage
- **Extension**: chrome.storage.local
- **Рекомендация для продакшена**: httpOnly cookies

---

## Тестирование

**Фреймворк**: pytest

**Запуск**:
```bash
cd backend
pytest -q

# С покрытием
pytest --cov=app

# С выводом логов
pytest -v -s
```

**Расположение тестов**: `backend/tests/`

---

## Структура репозитория

```
VKR_V3_Curs/
├── backend/
│   ├── app/
│   │   ├── core/              # config, db, api router
│   │   ├── modules/           # 14 модулей
│   │   ├── tasks/             # Celery tasks
│   │   ├── main.py            # точка входа FastAPI
│   │   └── celery_app.py      # Celery application
│   ├── alembic/               # миграции БД
│   ├── tests/                 # тесты
│   ├── .env.example
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── lib/               # API-клиент
│   │   └── App.jsx
│   ├── .env.example
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── package.json
├── extension/
│   ├── content.js             # content script
│   ├── popup.html
│   ├── popup.js
│   ├── manifest.json
│   └── README.md
├── docker-compose.yml          # root compose (full stack)
├── docker-compose.dev.yml      # dev-конфигурация
└── ARCHITECTURE.md             # этот документ
```

---

## Расширения и развитие

### Потенциальные улучшения
1. **Real-time уведомления**: WebSocket для мгновенной синхронизации
2. **Мобильное приложение**: React Native с общим API
3. **Оффлайн-режим**: Service Worker для frontend
4. **Мультиязычность**: Поддержка других пар языков
5. **Голосовые упражнения**: Интеграция с Speech-to-Text API
6. **Расширение модуля learning_path**: индивидуальные траектории

### Масштабирование
- **Горизонтальное**: Backend stateless, легко масштабируется
- **БД**: Репликация PostgreSQL, шардирование по user_id
- **Кэширование**: Redis для сессионных данных и AI-ответов
- **Celery**: Увеличение количества worker'ов

### Оптимизация
- **Database indexing**: индексы на foreign key и часто используемых полях
- **Connection pooling**: PgBouncer для PostgreSQL
- **Async views**: перевод тяжёлых endpoint'ов на async/await
- **CDN**: для статических файлов frontend

---

## Глоссарий

| Термин | Определение |
|--------|-------------|
| **CEFR** | Common European Framework of Reference for Languages (A1-C2) |
| **SRS** | Spaced Repetition System — система интервального повторения |
| **Lemma** | Лемма — базовая форма слова (например, "go" вместо "went") |
| **Semantic Key** | Уникальный ключ для семантической дедупликации слов |
| **Orchestration** | Координация нескольких модулей в одном сценарии |
| **Stub** | Заглушка для AI, возвращающая deterministic-ответы |
| **Broker** | Посредник для обмена сообщениями (Redis для Celery) |
| **Worker** | Процесс, выполняющий фоновые задачи |

---

## Контакты и поддержка

Документация:
- `backend/README.md` — руководство по запуску backend
- `backend/ARCHITECTURE.md` — архитектурные заметки backend
- `frontend/README.md` — руководство по запуску frontend
- `extension/README.md` — документация расширения
