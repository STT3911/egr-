#!/bin/bash
# Скрипт для ручного запуска парсинга данных

BATCH_SIZE=${1:-5000}
ASYNC=${2:-true}

echo "🚀 Запуск парсинга данных..."
echo "Размер батча: $BATCH_SIZE"
echo "Асинхронный режим: $ASYNC"
echo ""

if [ "$ASYNC" = "true" ]; then
    echo "Отправка задачи в Celery..."
    curl -X POST "http://localhost:8002/api/v1/companies/raw/parse-pending?limit=$BATCH_SIZE&async_run=true"
else
    echo "Синхронный парсинг (может занять время)..."
    curl -X POST "http://localhost:8002/api/v1/companies/raw/parse-pending?limit=$BATCH_SIZE"
fi

echo ""
echo ""
echo "✅ Команда выполнена!"
echo ""
echo "Проверить статус:"
echo "  docker exec egr_db psql -U postgres -d egr_db -c \"SELECT COUNT(*) FILTER (WHERE processed_at IS NULL) AS pending FROM egr_raw_company_data;\""
echo ""
echo "Запустить ещё раз:"
echo "  ./run-parsing.sh $BATCH_SIZE $ASYNC"
