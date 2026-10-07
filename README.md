# Онлайн-запись в салоны через Telegram

Мультисалонная платформа записи: **бот + Telegram Mini App**. Клиент записывается в несколько касаний
(салон → услуга → мастер → время → подтверждение), мастер и администратор ведут расписание в том же
Mini App, суперадмин платформы управляет салонами в веб-админке.

| Часть | Стек |
|---|---|
| `backend/` | Python 3.12, FastAPI, aiogram 3 (webhook), SQLAlchemy 2 async + asyncpg, Alembic, SQLAdmin |
| `frontend/` | React 18, TypeScript, Vite, TanStack Query, React Router, Telegram WebApp SDK |
| `deploy/` | Docker Compose: `api`, `worker`, `postgres`, `caddy` |

## Как это устроено

- **Один бот на платформу.** Ссылка салона: `https://t.me/<bot>?startapp=s_<slug>`.
  Mini App маршрутизирует по `start_param`: `s_<slug>` — витрина, `r_<id>` — перенос записи,
  `m_<salon_id>` — кабинет.
- **Аутентификация** — заголовок `Authorization: tma <initData>`, подпись проверяется по алгоритму
  Telegram (`backend/app/services/telegram_auth.py`), `auth_date` не старше 24 ч.
- **Слоты** считаются чистыми функциями (`backend/app/services/slots.py`), загрузка данных —
  `services/availability.py`. Двойную запись предотвращает ограничение
  `EXCLUDE USING gist` (расширение `btree_gist`); конфликт превращается в `409 slot_taken`.
- **Уведомления** ставятся в таблицу `notification`; отдельный процесс `worker` отправляет их
  (повторы с backoff `2^n` мин, до 5 попыток, ≤25 сообщений/с, учёт заблокировавших бота).
- **Телефон клиента** приходит через `Telegram.WebApp.requestContact()` → бот сохраняет контакт
  (только свой: `contact.user_id == from_user.id`) → Mini App опрашивает `/api/me/contact-status`.
  Если пользователь отказал — ручной ввод.

## Развёртывание

Нужен VPS (2 vCPU / 4 ГБ) с Docker и доменом, указывающим на сервер.

### 1. Бот в BotFather

1. `/newbot` → получите `BOT_TOKEN` и имя бота (`BOT_USERNAME`, без `@`).
2. `/newapp` или *Bot Settings → Configure Mini App → Enable Mini App* — укажите URL
   `https://<домен>/app/`. Это **Main Mini App**: без него не работают ссылки `t.me/<bot>?startapp=…`.
3. Кнопку меню (Menu Button) и webhook бэкенд настраивает сам при старте.

### 2. Конфигурация

```bash
git clone <repo> /opt/salon && cd /opt/salon/deploy
cp .env.example .env
nano .env   # DOMAIN, BOT_TOKEN, BOT_USERNAME, WEBHOOK_*, POSTGRES_PASSWORD, DATABASE_URL, ADMIN_*, SENTRY_DSN
```

- `WEBHOOK_SECRET` — случайная строка (`openssl rand -hex 24`).
- `DATABASE_URL` должен содержать тот же пароль, что `POSTGRES_PASSWORD`.
- `MINIAPP_URL=https://<домен>/app/`, `UPLOADS_BASE_URL=https://<домен>/uploads/`.

### 3. Запуск

```bash
docker compose up -d --build
docker compose logs -f api   # миграции применяются автоматически при старте api
curl https://<домен>/health  # {"status":"ok"}
```

Caddy сам получает TLS-сертификат. Маршруты: `/app/*` — Mini App, `/uploads/*` — изображения,
`/api/*`, `/tg/webhook/<secret>`, `/admin`, `/privacy`, `/health` — бэкенд.

### 4. Первый салон

1. Откройте `https://<домен>/admin`, войдите с `ADMIN_USERNAME` / `ADMIN_PASSWORD`.
2. **Салоны → Create**: название, `slug` (латиница, цифры, дефис), часовой пояс.
3. **Сотрудники → Create**: салон, имя, роль `owner`.
4. В списке сотрудников выберите владельца → действие **«Создать приглашение»** → в разделе
   **Приглашения** скопируйте ссылку `https://t.me/<bot>?start=inv_…` и отправьте владельцу.
5. Владелец открывает ссылку, нажимает «Открыть кабинет», заполняет услуги, мастеров
   (приглашая их такими же ссылками из кабинета), график и витрину.
6. Ссылку для записи клиентов владелец копирует в кабинете: **Салон → Ссылка для записи**.

### 5. Бэкап

`deploy/backup.sh` делает `pg_dump` и загружает его в S3-совместимое хранилище
(Selectel / Yandex Object Storage / Timeweb), удаляя копии старше `BACKUP_KEEP_DAYS`.
Нужен `aws` CLI на хосте и переменные `BACKUP_*`/`AWS_*` в `.env`. Ежедневный запуск:

```cron
15 3 * * * /opt/salon/deploy/backup.sh >> /var/log/salon-backup.log 2>&1
```

Восстановление: `gunzip -c dump.sql.gz | docker compose exec -T postgres psql -U app -d app`.

### 6. Политика ПДн

Страница `/privacy` отдаёт встроенную заглушку. Чтобы опубликовать свой текст, положите HTML-файл
в контейнер `api` (например, смонтируйте volume) и укажите путь в `PRIVACY_HTML_PATH`.

### Обновление

```bash
cd /opt/salon && git pull && cd deploy && docker compose up -d --build
```

## Разработка

Нужны Python 3.12 + [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16.

```bash
# база
createuser -s app && createdb -O app app && createdb -O app app_test   # пароль app

# backend
cd backend
uv sync
uv run alembic upgrade head
BOT_TOKEN=123:dev TELEGRAM_SETUP_ON_STARTUP=false ENVIRONMENT=dev UPLOADS_DIR=/tmp/uploads \
  uv run uvicorn app.main:app --reload            # http://localhost:8000, документация /api/docs
uv run python -m app.worker                        # воркер уведомлений (нужен настоящий BOT_TOKEN)

# проверки
uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
uv run pytest --cov=app/services                   # использует БД app_test (TEST_DATABASE_URL)

# frontend
cd ../frontend
npm install
VITE_DEV_INIT_DATA='<initData>' npm run dev        # http://localhost:5173/app/, /api проксируется на :8000
npm test && npm run build
```

Вне Telegram Mini App берёт `initData` из `VITE_DEV_INIT_DATA` (подпишите её тем же `BOT_TOKEN`,
см. `make_init_data` в `backend/tests/conftest.py`) и рисует обычную кнопку вместо `MainButton`.

## Структура

```
backend/app
  main.py            FastAPI, webhook бота, /health, /privacy
  config.py          переменные окружения
  models/            SQLAlchemy-модели
  schemas/           Pydantic-схемы API
  api/               public.py (витрина, слоты, запись), me.py (мои записи), manage/ (кабинет)
  bot/               хэндлеры, клавиатуры, тексты
  services/          slots.py, availability.py, booking.py, notifications.py, invites.py, telegram_auth.py
  worker.py          отправка уведомлений
  admin.py           SQLAdmin
backend/migrations   Alembic
frontend/src
  api/ telegram/ components/ lib/
  pages/client/      витрина, запись, мои записи, перенос
  pages/manage/      расписание, записи, график, клиенты, услуги, сотрудники, салон
deploy/              docker-compose.yml, Caddyfile, Dockerfile.caddy, .env.example, backup.sh
```
