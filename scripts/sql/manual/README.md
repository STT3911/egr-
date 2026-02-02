# SQL в manual/ не выполняются при старте контейнера

Скрипты здесь нужно запускать вручную (тяжёлые или разовые).

- **08-fill-ref-authorities-null-safe.sql** — заполнение ref_authorities из egr_raw_company_data (минуты при 1.6M строк). Запуск:  
  `docker exec -i egr_db psql -U postgres -d egr_db < scripts/sql/manual/08-fill-ref-authorities-null-safe.sql`
