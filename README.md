# Telegram-бот: «Тест — Какой ты тип женщины в отношениях»

MVP-бот на Python + aiogram 3 + SQLite: 15 вопросов, подсчёт результата (A/B/C/D), продажа мини-курса и админка внутри Telegram.

---

## 🚀 Deploy на Railway (через GitHub)

1. Запушьте этот репозиторий в GitHub.
2. На [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → выберите ваш репозиторий.
3. В разделе **Variables** добавьте:
   - `BOT_TOKEN` — токен вашего Telegram-бота (обязательно)
   - `ADMIN_IDS` — Telegram ID админов через запятую (например `123456789,987654321`)
   - `PARSE_MODE` — `HTML` (опционально, по умолчанию HTML)
   - `QUESTION_DELAY_SEC` — задержка между вопросами в сек. (опционально, по умолчанию `0.0`)
   - `DB_PATH` — путь к SQLite файлу (опционально, по умолчанию `bot.db`)
   - `PUBLIC_BASE_URL` — публичный **https://…** URL сервиса **без** завершающего `/` (обязательно для оплаты BePaid)
   - `BEPAID_SHOP_ID`, `BEPAID_SECRET_KEY` — Shop ID и секретный ключ ([идентификация](https://docs.bepaid.by/en/using_api/id_key/))
   - `BEPAID_TEST` — `true`/`false` (тестовый режим checkout)
   - `PAYMENT_AMOUNT`, `PAYMENT_CURRENCY` — сумма в минимальных единицах валюты и ISO-код (например `1` и `BYN` для проверки)
   - `PORT` — порт HTTP-сервера (на Railway задаётся платформой автоматически)
4. Railway автоматически соберёт контейнер по `Dockerfile` и запустит бота.
5. Назначьте сервису публичный **HTTPS** домен (Railway **Generate Domain**) и пропишите его в `PUBLIC_BASE_URL` без завершающего `/` — это нужно для hosted checkout BePaid и webhook `POST /webhooks/bepaid`.
6. Логи смотрите во вкладке **Deployments → Logs**.

> ⚙️ Telegram всё ещё на **long polling**, но процесс также слушает HTTP **`PORT`** (health-check `GET /health` и webhook для BePaid).

Документация BePaid: [Create a payment token / checkout](https://docs.bepaid.by/en/integration/widget/payment_token/), [Webhook notifications](https://docs.bepaid.by/en/using_api/webhooks/).

### ⚠️ Важно: SQLite не персистентна на Railway

Файловая система контейнера на Railway **эфемерна**. При каждом редеплое (новый коммит, рестарт сервиса, изменение переменных) файл `bot.db` **пересоздаётся с нуля**. Это значит, что сбрасываются:

- все зарегистрированные пользователи и их ответы;
- статистика и события;
- настройки админ-панели (приветственное сообщение, ссылка на канал, текст продажи) — возвращаются к дефолтам из `app/db.py`.

**Если данные нужно сохранять между деплоями**, есть два варианта:

1. **Подключить Railway Volume** — в настройках сервиса смонтировать том в `/data` и задать переменную `DB_PATH=/data/bot.db`. SQLite будет переживать редеплои.
2. **Мигрировать на PostgreSQL** — добавить Postgres-плагин в Railway и переписать `app/db.py` на `asyncpg` или `SQLAlchemy`.

---

## 🧑‍💻 Local development

### Через Python напрямую

```bash
python -m venv .venv
source .venv/bin/activate         # Linux/Mac
# .\.venv\Scripts\Activate.ps1     # Windows PowerShell

pip install -r requirements.txt
cp .env.example .env              # и впишите BOT_TOKEN
python -m app
```

### Через Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f
```

---

## 📦 Структура проекта

```
.
├── app/
│   ├── __init__.py
│   ├── __main__.py        # entrypoint: python -m app
│   ├── main.py            # запуск бота, роутинг, хендлеры
│   ├── admin.py           # админ-панель
│   ├── config.py          # загрузка .env
│   ├── content.py         # вопросы, тексты результатов
│   ├── db.py              # SQLite + миграции + дефолтные настройки
│   ├── keyboards.py       # инлайн-клавиатуры
│   ├── logic.py           # подсчёт результата теста
│   ├── bepaid_api.py      # BePaid hosted checkout + разбор webhook
│   └── http_server.py     # aiohttp: /health, /webhooks/bepaid, return URLs
├── Dockerfile
├── docker-compose.yml
├── railway.toml
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔧 Переменные окружения

| Переменная           | Обязательно | Описание                                            |
|----------------------|-------------|-----------------------------------------------------|
| `BOT_TOKEN`          | ✅          | Токен Telegram-бота от [@BotFather](https://t.me/BotFather) |
| `ADMIN_IDS`          | —           | Telegram ID админов через запятую                   |
| `DB_PATH`            | —           | Путь к SQLite файлу (по умолчанию `bot.db`)         |
| `PARSE_MODE`         | —           | `HTML` (рекомендуется)                              |
| `QUESTION_DELAY_SEC` | —           | Задержка между вопросами в секундах (например `0.4`) |
| `PUBLIC_BASE_URL`    | ✅ для оплаты | Публичный `https://…` без `/` в конце; webhook: `{PUBLIC_BASE_URL}/webhooks/bepaid` |
| `BEPAID_SHOP_ID`     | ✅ для оплаты | Shop ID ([документация](https://docs.bepaid.by/en/using_api/id_key/)) |
| `BEPAID_SECRET_KEY`  | ✅ для оплаты | Секретный ключ магазина (только в переменных окружения) |
| `BEPAID_TEST`        | —           | `true`/`false`, см. [payment token](https://docs.bepaid.by/en/integration/widget/payment_token/) |
| `PAYMENT_AMOUNT`     | —           | Сумма в минимальных единицах валюты (по умолчанию `1`) |
| `PAYMENT_CURRENCY`   | —           | ISO-код валюты (по умолчанию `BYN`) |
| `PORT`               | —           | Порт HTTP (Railway задаёт сама; локально можно `8080`) |

Webhook принимает **HTTP Basic** с тем же Shop ID / Secret Key ([раздел Webhooks](https://docs.bepaid.by/en/using_api/webhooks/)). Дополнительно BePaid может прислать заголовок **`Content-Signature`** (RSA/SHA256) — для параноидального уровня можно верифицировать по публичному ключу из личного кабинета (в коде пока не реализовано, только Basic-auth).

---

## 💬 Команды бота

- `/start` — начать или перезапустить тест
- `/admin` — админ-панель (доступна только пользователям из `ADMIN_IDS`)

---

## 🖥 VPS: отдельная папка и автозапуск

Ниже команды для Linux VPS, чтобы проект работал из отдельной директории и автоматически поднимался после перезагрузки.

```bash
# 1) Отдельная директория под проекты
sudo mkdir -p /opt/projects
cd /opt/projects

# 2) Клонируем проект в отдельную папку
sudo git clone https://github.com/SiteCraftorCPP/marina-main.git marina-main
cd /opt/projects/marina-main

# 3) Создаём .env
sudo cp .env.example .env
sudo nano .env

# 4) Делаем скрипт обновления исполняемым
sudo chmod +x /opt/projects/marina-main/deploy/vps/update.sh

# 5) Устанавливаем systemd unit-файлы
sudo cp /opt/projects/marina-main/deploy/systemd/marina-main.service /etc/systemd/system/
sudo cp /opt/projects/marina-main/deploy/systemd/marina-main-update.service /etc/systemd/system/
sudo cp /opt/projects/marina-main/deploy/systemd/marina-main-update.timer /etc/systemd/system/

# 6) Релоад systemd
sudo systemctl daemon-reload

# 7) Автозапуск стека при старте VPS
sudo systemctl enable --now marina-main.service

# 8) Автообновление с git каждые 5 минут
sudo systemctl enable --now marina-main-update.timer

# 9) Проверка
sudo systemctl status marina-main.service --no-pager
sudo systemctl status marina-main-update.timer --no-pager
sudo systemctl list-timers --all | grep marina-main
```

### Ручное обновление

```bash
cd /opt/projects/marina-main
sudo /opt/projects/marina-main/deploy/vps/update.sh
```
