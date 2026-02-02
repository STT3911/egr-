#!/bin/bash
# Скрипт для ручного запуска парсинга данных
# Требует: API доступен на порту 8002. Если задан API_KEY или ALLOWED_API_KEYS — передайте: API_KEY=xxx ./scripts/run-parsing.sh

BATCH_SIZE=${1:-5000}
ASYNC=${2:-true}
API_URL="${API_BASE_URL:-http://localhost:8002}/api/v1/companies/raw/parse-pending"

CURL_OPTS=()
if [ -n "$API_KEY" ]; then
  CURL_OPTS+=(-H "X-API-Key: $API_KEY")
fi

echo "🚀 Запуск парсинга данных..."
echo "Размер батча: $BATCH_SIZE"
echo "Асинхронный режим: $ASYNC"
echo ""

if [ "$ASYNC" = "true" ]; then
    echo "Отправка задачи в Celery..."
    curl -s -X POST "${CURL_OPTS[@]}" "$API_URL?limit=$BATCH_SIZE&async_run=true"
else
    echo "Синхронный парсинг (может занять время)..."
    curl -s -X POST "${CURL_OPTS[@]}" "$API_URL?limit=$BATCH_SIZE"
fi
echo ""
echo "✅ Команда выполнена!"
echo ""
echo "Проверить статус:"
echo "  docker compose exec egr_db psql -U postgres -d egr_db -c \"SELECT COUNT(*) FILTER (WHERE processed_at IS NULL) AS pending FROM egr_raw_company_data;\""
echo ""
echo "Запустить ещё раз:"
echo "  ./scripts/run-parsing.sh $BATCH_SIZE $ASYNC"
