# Telegram bot

Бот использует те же endpoints, что и веб-сервис:

- `GET /api/v1/companies/lookup` для поиска по УНП или названию;
- `GET /api/v1/companies/{unp}` для карточки компании.

Поисковая логика не дублируется в боте: Elasticsearch/SQL fallback и нормализация остаются в API.

## Переменные окружения

```env
TELEGRAM_BOT_TOKEN=123456:telegram-token
TELEGRAM_API_BASE_URL=http://egr-api:8000
TELEGRAM_API_KEY=
TELEGRAM_LOOKUP_LIMIT=5
```

- `TELEGRAM_BOT_TOKEN` обязателен.
- `TELEGRAM_API_BASE_URL` по умолчанию указывает на API внутри Docker Compose.
- `TELEGRAM_API_KEY` опционален; если задан, бот отправляет его в заголовке `X-API-Key`.
- `TELEGRAM_LOOKUP_LIMIT` задает максимальное число кнопок в выдаче.

## Запуск

```bash
docker compose --profile telegram up -d telegram-bot
```

После запуска напишите боту УНП или часть названия компании. 9-значный УНП сразу открывает карточку, а поиск по названию возвращает список вариантов с кнопками.
