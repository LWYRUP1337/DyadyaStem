# Сущности и контракты API — ДядяStem

Единый источник для бэкенда, фронта и воркера!!! Имена полей совпадают со схемой БД один в один!!! У всех!!! Основано на макете
---

## Общие правила

- Все эндпоинты, кроме `POST /auth/email/check`, `POST /auth/register`, `POST /auth/login`, требуют заголовок `Authorization: Bearer <token>`.
- Чужой или несуществующий ресурс всегда отдаёт `404` (не `403`), чтобы не раскрывать чужие id.
- Ошибки в формате FastAPI по умолчанию: `{ "detail": "..." }`. Ошибки валидации — `422`.
- Именование: `snake_case` в JSON, время в секундах (float), id — UUID строкой.
- Темп: `tempo_ratio` — доля от оригинала (`1.0` = 100%, `0.85` = 85%, `1.5` = 150%). Проценты в JSON не используются, кроме `speed_ramp_config` (см. ниже). В xlsx-экспорте темп выводится в процентах.
- Порядок дорожек: бэкенд всегда отдаёт `tracks` в фиксированном порядке `vocals, drums, bass, other, guitar, piano` (отсутствующие пропускаются). Поля `order` нет.
- Длины: `name` проекта 1–100 символов, `song_title` до 100, имя фрагмента 1–50.


### Общие JSON-структуры

**`stem_volumes`** — состояние микшера. Ключ — тип стема (не id дорожки), передаётся всегда целиком:

```json
{
  "vocals": { "volume": 0.8, "muted": false, "solo": false },
  "drums":  { "volume": 1.0, "muted": true,  "solo": false },
  "bass":   { "volume": 0.3, "muted": false, "solo": false },
  "other":  { "volume": 1.0, "muted": false, "solo": false }
}
```

Если ключа нет или `stem_volumes = null`, фронт использует `volume 1.0, muted false, solo false`.

**`speed_ramp_config`** — настройки Speed Ramp или `null`:

```json
{ "repeats_to_speedup": 3, "step_percent": 5, "max_percent": 150 }
```

`step_percent` — прибавка за шаг в процентах от оригинала (`5` → `tempo_ratio += 0.05`). `max_percent` — потолок в процентах от оригинала (`150` → `tempo_ratio` не больше `1.5`). Границы: `repeats_to_speedup` 1–10, `step_percent` 2–25, `max_percent` 100–150. Валидируется на фронте и на бэке.

---
внешний порт postgres 5433, внутренний 5432

## Сущности (БД)

### User

| Поле | Тип | Описание |
| --- | --- | --- |
| id | UUID | PK |
| email | varchar, unique |  |
| password_hash | varchar |  |
| created_at | timestamp |  |

### Project

| Поле | Тип | Описание |
| --- | --- | --- |
| id | UUID | PK |
| user_id | UUID | FK → users, cascade, индекс |
| name | varchar | название проекта |
| **song_title** | varchar, nullable | **название песни; заполняется при импорте или вручную** |
| status | enum | `processing` \| `ready` \| `error` |
| model | enum | `htdemucs` \| `htdemucs_6s` |
| duration_sec | int, nullable | заполняется воркером после обработки |
| **source_url** | varchar(2048), nullable | **прямая ссылка на mp3, если проект создан из ссылки (импорт xlsx)** |
| source_file_key | varchar, nullable | исходный mp3 в garage: при загрузке файлом ставится сразу, при `source_url` — воркером после скачивания; нужен для retry, после `ready` можно удалять |
| error_message | text, nullable | если `status = error` |
| created_at, updated_at | timestamp |  |

### Track

| Поле | Тип | Описание |
| --- | --- | --- |
| id | UUID | PK |
| project_id | UUID | FK → projects, cascade, индекс |
| stem_type | enum | `vocals` \| `drums` \| `bass` \| `other` \| `guitar` \| `piano` (последние два только для `htdemucs_6s`) |
| file_key | varchar | путь в garage; наружу только через presigned URL |
| created_at | timestamp |  |

Уникальный индекс `(project_id, stem_type)`.

### ProjectState (общий «черновик», 1:1 с Project)

| Поле | Тип | Описание |
| --- | --- | --- |
| project_id | UUID | PK и FK → projects, cascade |
| active_fragment_id | UUID, nullable | FK → fragments, set null; `null` = открыт черновик |
| master_volume | float | 0–1, по умолчанию 1.0 |
| tempo_ratio | float | по умолчанию 1.0 |
| stem_volumes | jsonb | см. выше |
| loop_start, loop_end | float, nullable | точки A и B в секундах |
| speed_ramp_config | jsonb, nullable | см. выше |
| updated_at | timestamp |  |

### Fragment (сохранённый луп = полный снэпшот)

| Поле | Тип | Описание |
| --- | --- | --- |
| id | UUID | PK |
| project_id | UUID | FK → projects, cascade, индекс |
| name | varchar | до 50 символов |
| loop_start, loop_end | float | секунды, `loop_end - loop_start >= 1` |
| master_volume | float |  |
| tempo_ratio | float | текущая (последняя) скорость фрагмента |
| **best_tempo_ratio** | float | **максимум `tempo_ratio` за всё время («рекорд»)** |
| **practice_count** | int | **сколько раз фрагмент открывали из сайдбара; при создании = 1** |
| stem_volumes | jsonb |  |
| speed_ramp_config | jsonb, nullable |  |
| last_practiced_at | timestamp | обновляется при открытии и при каждом автосохранении в этот фрагмент |
| created_at | timestamp |  |

**Два уровня состояния.** Пока фрагмент не открыт, автосохранения идут в `ProjectState`. Когда юзер открывает фрагмент, `ProjectState.active_fragment_id` указывает на него, и дальнейшие автосохранения пишутся в сам `Fragment`. Так работает «доиграл до 85%, завтра продолжил с 85%».

---

## Эндпоинты

### Аутентификация

**`POST /auth/email/check`**

```json
// Request
{ "email": "user@example.com" }
// Response 200
{ "exists": true }
```

**`POST /auth/register`**

```json
// Request
{ "email": "user@example.com", "password": "...", "password_confirm": "..." }
// Response 201
{ "access_token": "...", "user": { "id": "...", "email": "..." } }
```

Ошибки: `409` — email уже занят, `422` — пароли не совпадают или слабый пароль.

**`POST /auth/login`**

```json
// Request
{ "email": "user@example.com", "password": "..." }
// Response 200
{ "access_token": "...", "user": { "id": "...", "email": "..." } }
```

Ошибка: `401` — неверный пароль.

**`POST /auth/logout`** — `204`. Токен удаляется на клиенте, серверного blacklist в MVP нет.

**`GET /auth/me`**

```json
{ "id": "...", "email": "..." }
```

---

### Проекты

**`GET /projects`** — список для дашборда (все проекты юзера, поиск на клиенте)

```json
{
  "projects": [
    { "id": "...", "name": "Название проекта", "status": "ready", "duration_sec": 193 }
  ]
}
```

Для `processing` и `error` `duration_sec` может быть `null`.

**`POST /projects`** — `multipart/form-data`. Источник трека — **ровно одно из двух**: `file` или `source_url`.

```
name: "Untitled1"                 // обязательно, 1–100
model: "htdemucs" | "htdemucs_6s" // обязательно
song_title: "Название песни"      // необязательно, до 100
file: <mp3 binary>                // ИЛИ
source_url: "https://example.com/track.mp3"
```

```json
// Response 202
{ "id": "...", "status": "processing" }
```

Проверки на API:

- ни `file`, ни `source_url`, либо оба сразу → `422`;
- `file`: не mp3 или повреждён → `400`; больше 25 МБ или длиннее 10 минут → `413`;
- `source_url`: только `http`/`https`, до 2048 символов, иначе `422`. Скачивание и остальные проверки делает воркер (ниже), поэтому ошибки по ссылке видны как `status = error`, а не как ответ на этот запрос;
- у пользователя уже 10 проектов в статусе `processing` → `409` (`"detail": "too_many_processing"`).

Бэкенд создаёт проект и ставит Celery-задачу **по имени**: `celery_app.send_task("process_audio", args=[project_id])`.

**Скачивание по `source_url` (шаг воркера перед Demucs).** Правила обязательны:

1. Только `http`/`https`, порты 80 и 443.
2. Хост резолвится в IP, адреса loopback, private, link-local, reserved и metadata-сервисов (в т.ч. `169.254.169.254`) отклоняются. Проверка повторяется на каждом редиректе, редиректов не больше 3.
3. Таймауты: соединение 5 с, всего 60 с.
4. Читается потоком, обрыв при превышении 25 МБ.
5. Тип проверяется по содержимому (признак mp3: тег `ID3` или MPEG frame sync), а не только по `Content-Type`.
6. После скачивания проверяется длительность ≤ 10 минут.
7. Файл кладётся в garage, пишется `source_file_key`. При любом нарушении: `status = error`, `error_message` с понятной причиной (например, «Не удалось скачать файл по ссылке: файл больше 25 МБ»).

**`GET /projects/{id}/status`** — polling каждые 1–2 секунды, остановка на `ready` или `error`

```json
{ "status": "processing" }
{ "status": "ready" }
{ "status": "error", "error_message": "..." }
```

**`GET /projects/{id}`** — открытие workspace

```json
{
  "id": "...",
  "name": "Название проекта",
  "song_title": null,
  "status": "ready",
  "model": "htdemucs",
  "duration_sec": 193,
  "tracks": [
    { "id": "...", "stem_type": "vocals", "url": "https://.../presigned" },
    { "id": "...", "stem_type": "drums",  "url": "..." },
    { "id": "...", "stem_type": "bass",   "url": "..." },
    { "id": "...", "stem_type": "other",  "url": "..." }
  ]
}
```

Если `status != ready`, `tracks` пустой массив.

**`POST /projects/{id}/retry`** — для карточки «ошибка». Тело не нужно.

```json
// Response 202
{ "id": "...", "status": "processing" }
```

Ошибки: `409` — проект не в `error`, `404` — не найден. Воркер идемпотентен: перед повтором удаляет старые `tracks` и файлы стемов. Если проект создан из `source_url`, повтор скачивает файл заново.

**`DELETE /projects/{id}`** — `204`. Удаляет проект, строки в БД (cascade) и файлы в MinIO.

**Поиск проектов — только на клиенте.** Регистр не важен; запрос делится на слова; проект подходит, если каждое слово есть в названии как подстрока; пустой запрос показывает всё.

---

### Импорт из xlsx (на клиенте, отдельного эндпоинта нет)

Фронт разбирает файл (SheetJS) и для каждой строки вызывает `POST /projects` с `source_url`. Бэкенд каждую строку проверяет заново.

**Шаблон** (`frontend/public/import-template.xlsx`, кнопка «Скачать шаблон»): первая строка — заголовки, вторая — пример, в столбце «Модель» выпадающий список.

| Столбец | Поле запроса | Правила |
| --- | --- | --- |
| Название проекта | `name` | обязательно, 1–100 символов |
| Название песни | `song_title` | необязательно, до 100 |
| Модель | `model` | `htdemucs` или `htdemucs_6s` (допустимы также `4` и `6`) |
| Ссылка на mp3 | `source_url` | обязательно, `http`/`https`, прямая ссылка на mp3-файл |

Правила разбора:

- столбцы ищутся по заголовкам, лишние столбцы игнорируются (поэтому лист «Проекты» из экспорта можно импортировать обратно);
- файл `.xlsx` до 1 МБ, до 10 строк с данными, пустые строки пропускаются;
- перед созданием показывается таблица предпросмотра (название, песня, модель, ссылка, статус проверки); поля имени и модели в форме в этом режиме заблокированы;
- строки с ошибками не отменяют импорт остальных, причина показывается у строки;
- строки отправляются последовательно; при ответе `409 too_many_processing` оставшиеся строки помечаются «не создано: слишком много проектов в обработке».

---

### Экспорт в xlsx

**`GET /export`** — отдаёт файл `dyadyastem_export_<MM-DD-YYYY>.xlsx` (`Content-Disposition: attachment`). Данные только текущего пользователя.

**Лист «Проекты»**

| № | Столбец | Источник |
| --- | --- | --- |
| A | Название проекта | `name` |
| B | Название песни | `song_title` |
| C | Модель | `model` |
| D | Ссылка на mp3 | `source_url` (пусто, если трек загружен файлом) |
| E | Длительность | `duration_sec` в формате мм:сс |
| F | Статус | Готов / В обработке / Ошибка |
| G | Создан | `created_at`, формат MM/DD/YYYY |

Столбцы A–D совпадают с шаблоном импорта. Проекты без ссылки при повторном импорте будут показаны как ошибочные строки («нет ссылки»).

**Лист «Фрагменты»**

| № | Столбец | Источник |
| --- | --- | --- |
| A | Проект | `projects.name` |
| B | Фрагмент | `fragments.name` |
| C | Начало | `loop_start`, мм:сс |
| D | Конец | `loop_end`, мм:сс |
| E | Текущий темп, % | `tempo_ratio × 100` |
| F | Рекорд темпа, % | `best_tempo_ratio × 100` |
| G | Открыт раз | `practice_count` |
| H | Последняя практика | `last_practiced_at`, MM/DD/YYYY чч:мм |
| I | Speed Ramp | например `3 повт. · +5% · до 150%`, или `—` |

**Защита от инъекции формул.** Весь текст пользователя (названия проектов, песен, фрагментов) записывается в ячейки только как строка, не как формула. Тест: проект с названием `=1+1` открывается в Excel и Google Таблицах как текст.

---

### Состояние workspace (автосохранение)

**`GET /projects/{id}/state`** — вызывается при открытии workspace. Возвращает *эффективное* состояние: если `active_fragment_id` не `null`, значения берутся из этого фрагмента, иначе из черновика.

```json
{
  "active_fragment_id": null,
  "master_volume": 1.0,
  "tempo_ratio": 1.0,
  "stem_volumes": { "vocals": { "volume": 0.8, "muted": false, "solo": false } },
  "loop_start": null,
  "loop_end": null,
  "speed_ramp_config": null
}
```

**`PATCH /projects/{id}/state`** — debounce 1.5–2 сек. При уходе со страницы (`visibilitychange`, `pagehide`) запрос отправляется немедленно через `fetch` с `keepalive: true` (тело до 64 КБ). `navigator.sendBeacon` не подходит: он умеет только POST и не передаёт заголовок `Authorization`.

Правила:

1. Клиент **каждый раз** отправляет текущий `active_fragment_id` (id или `null`).
2. Остальные поля частичные, `stem_volumes` целиком.
3. Если `active_fragment_id` не `null`, сервер пишет поля в этот `Fragment`, обновляет `last_practiced_at`, а `best_tempo_ratio = max(best_tempo_ratio, tempo_ratio)`. Если `null` — пишет в `ProjectState`.
4. **Смена контекста** (открыл фрагмент / вышел в черновик) — запрос только с `active_fragment_id`. Сервер переставляет указатель, ничего не перезаписывает. Если указан фрагмент: `practice_count += 1`, `last_practiced_at = now`.

```json
// Обычное автосохранение
{ "active_fragment_id": "frag-uuid", "tempo_ratio": 1.1, "stem_volumes": { ... } }
// Смена контекста
{ "active_fragment_id": "frag-uuid" }
// Response 200 — эффективное состояние целиком (как в GET)
```

Ошибка: `404`, если фрагмент не принадлежит проекту.

Ограничение: `practice_count` считает открытия из сайдбара. Если юзер вернулся в проект, где фрагмент уже был активным, и продолжил играть, счётчик не растёт.

---

### Фрагменты

**`GET /projects/{id}/fragments`** — сайдбар «Мои фрагменты»

```json
{
  "fragments": [
    {
      "id": "...",
      "name": "Новый фрагмент",
      "loop_start": 84.0,
      "loop_end": 110.0,
      "tempo_ratio": 0.85,
      "last_practiced_at": "2026-10-10T18:30:00Z"
    }
  ]
}
```

Сортировка по `last_practiced_at`, свежие сверху.

**`POST /projects/{id}/fragments`** — кнопка «Сохранить фрагмент», без модалки. Имя генерирует фронт с автоинкрементом («Новый фрагмент», «Новый фрагмент 2», ...).

```json
// Request
{
  "name": "Новый фрагмент",
  "loop_start": 84.0,
  "loop_end": 110.0,
  "master_volume": 1.0,
  "tempo_ratio": 0.85,
  "stem_volumes": { ... },
  "speed_ramp_config": { "repeats_to_speedup": 3, "step_percent": 5, "max_percent": 150 }
}
// Response 201 — полный объект фрагмента (все поля сущности)
```

Сервер ставит `best_tempo_ratio = tempo_ratio`, `practice_count = 1`. Ошибка `422`: пустое имя, длина больше 50, `loop_end - loop_start < 1`. Создание **не** переключает контекст: фронт сам шлёт `PATCH /state` с `active_fragment_id`, если хочет сделать фрагмент активным.

**`GET /projects/{id}/fragments/{fragment_id}`** — полный снэпшот, включая `best_tempo_ratio` и `practice_count`. Чистый запрос без побочных эффектов; для активации фронт после него делает `PATCH /state`.

**`PATCH /projects/{id}/fragments/{fragment_id}`** — переименование (инлайн в сайдбаре)

```json
{ "name": "Новое имя" }
```

**`DELETE /projects/{id}/fragments/{fragment_id}`** — `204`. Если фрагмент был активным, `active_fragment_id` сбрасывается в `null` (set null в БД).

---

## Технические решения

1. **Polling статуса** — 1–2 секунды, остановка на `ready` / `error`.
2. **Лимиты файла** — 10 минут и 25 МБ, на фронте после выбора файла и на бэке (для ссылок — в воркере).
3. **JWT** — один access-токен, срок \~7 дней, без refresh в MVP, на фронте в `localStorage`.
4. **Celery** — бэкенд ставит задачу по имени через `send_task`, код воркера не импортирует.
5. **Воркер пишет в Postgres напрямую** (синхронная сессия SQLAlchemy, минимальные модели `projects` и `tracks`).
6. **Presigned URL и Docker.**Ссылки подписываются публичным адресом Garage (MINIO_PUBLIC_ENDPOINT или S3_PUBLIC_ENDPOINT), доступным из браузера. (Примечание: имя переменной в .env для совместимости можно оставить MINIO_PUBLIC_ENDPOINT, но по смыслу это адрес Garage).
7. **Импорт xlsx разбирается на клиенте**, создание проектов идёт через обычный `POST /projects`. Лимиты: 1 МБ, 10 строк, не более 10 проектов в `processing` у одного пользователя.
8. **Экспорт xlsx генерируется на бэкенде** одним запросом (`GET /export`).
9. **Скачивание по ссылке — только в воркере**, с защитой от SSRF (правила в `POST /projects`).
