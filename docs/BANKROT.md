# Интеграция с bankrot.gov.by

## Архитектура

Проект использует единый контур источников данных:

- `FastAPI` публикует данные компаний;
- `SQLAlchemy` и PostgreSQL хранят нормализованные и сырые ответы;
- `Celery` выполняет длительные синхронизации;
- React-клиент показывает краткий профиль и лениво загружает тяжёлые разделы.

До расширения интеграция с ЕГРСБ сохраняла только:

- элемент списка `POST /v1/cases`;
- карточку `GET /v1/cases/{id}`;
- сгруппированные судебные решения `GET /v1/cases/{id}/judgements/group`.

Остальные разделы карточки дела не загружались. Теперь они сохраняются отдельно в
`bankrot_case_datasets`, чтобы изменение схемы внешнего API не приводило к потере полей.

## Собираемые наборы

Для каждого дела поддерживаются следующие публичные разделы:

| `dataset_type` | Endpoint | Содержание |
| --- | --- | --- |
| `publications` | `POST /messages` | публичные объявления по наименованию должника |
| `properties` | `POST /cases/{id}/properties` | имущество должника |
| `property_reports` | `POST /cases/{id}/property-reports` | отчёты об имуществе |
| `property_valuations` | `POST /cases/{id}/property-reports/valuation` | результаты оценки |
| `sales` | `POST /cases/{id}/sales` | реализация, аукционы и прямые продажи |
| `creditor_meetings` | `POST /cases/{id}/meetings` | собрания кредиторов |
| `creditor_committees` | `POST /cases/{id}/committees` | комитеты кредиторов |
| `creditor_requirements` | `POST /cases/{id}/creditor-requirements` | требования кредиторов |
| `property_write_off` | `POST /cases/{id}/property-write-off` | списание имущества |
| `transfer_remaining_properties` | `POST /cases/{id}/transfer-remaining-properties` | передача оставшегося имущества |
| `transfer_unsold_properties` | `POST /cases/{id}/transfer-unsold-properties` | передача непроданного имущества |
| `readjustments` | `GET /cases/{id}/readjustments` | корректировки планов и отчётов |
| `fund_balance_reports` | `GET /cases/{id}/fund-balance-reports` | отчёты о движении денежных средств |
| `debtor_bank_accounts` | `GET /debtors/{debtorId}/bank-accounts` | банковские счета должника |
| `debtor_online_wallets` | `GET /debtors/{debtorId}/online-wallets` | электронные кошельки должника |
| `manager_full_info` | `GET /manager/{managerId}/fullinfo` | полная карточка управляющего и контакты |
| `manager_accreditation` | `GET /manager/{managerId}/accreditation` | аккредитация управляющего |
| `manager_documents` | `GET /manager/{managerId}/manager-documents` | аттестационные документы |
| `manager_education` | `GET /manager/{managerId}/education` | образование и повышение квалификации |
| `manager_debtors` | `GET /manager/debtors/?id={managerId}` | активные и завершённые дела управляющего |
| `manager_bank_accounts` | `GET /manager/{managerId}/bank-accounts` | банковские реквизиты управляющего |
| `manager_online_wallets` | `GET /manager/{managerId}/online-wallets` | электронные кошельки управляющего |

Для пагинированных ответов клиент автоматически проходит все страницы и объединяет
коллекции. Повтор одинаковой страницы определяется как игнорирование пагинации и
останавливает цикл.

Разделы должника и управляющего кэшируются в пределах одного запуска по их внутренним ID:
если один управляющий связан с несколькими делами, внешний endpoint вызывается один раз,
но снимок сохраняется для каждого соответствующего дела.

`POST /cases` требует полный объект фильтров и числовой `sort.sortOrder`. Клиент всегда
добавляет обязательные поля, а переданные фильтры накладывает поверх значений по умолчанию.
По умолчанию `status` пустой, поэтому синхронизируются и активные, и закрытые дела;
значения `1` и `0` позволяют явно ограничить выборку активными или закрытыми делами.
Контракт списка, карточка дела, судебные решения и дочерние разделы `/cases/{id}/...`
проверены на действующем API 13 июля 2026 года. Маршруты `/messages`, `/debtors/...`
и `/manager/...` дополнительно сверены с актуальным production-bundle сайта; ошибка одного
такого раздела изолируется и не останавливает синхронизацию остальных данных.

Бинарные документы, кабинетные операции изменения данных и закрытые административные
разделы намеренно не скачиваются. Метаданные и ссылки, присутствующие в публичных JSON,
сохраняются без изменений.

Отдельные карточки объектов (`/messages/{id}`, `/judgments/{id}`, `/property/{id}`),
договоры по конкретному лоту и бинарные файлы не обходятся массово: одно дело может
содержать тысячи объектов имущества, поэтому такой обход создал бы тысячи дополнительных
запросов. Их идентификаторы, документы и доступные поля уже сохраняются внутри ответов
соответствующих наборов и могут загружаться адресно при необходимости.

## Хранение

- `bankrot_cases` — нормализованные поля дела и три исходных ответа;
- `bankrot_case_datasets` — текущий полный JSON каждого дочернего раздела;
- `bankrot_cases_history` — предыдущие версии основной карточки;
- `bankrot_sync_runs` — журнал запусков и счётчики ошибок.

Ключ `bankrot_case_datasets` — `(case_id, dataset_type)`. При временной ошибке новый
`fetch_error` сохраняется, но последний успешный `payload` не затирается `NULL`.

## Авторизация

API ЕГРСБ возвращает `401` без действующего Bearer-токена. Рекомендуемый режим —
`BANKROT_REFRESH_TOKEN`: `BankrotTokenManager` обновляет access-токен через OIDC и
сохраняет ротированный refresh-токен в `BANKROT_REFRESH_TOKEN_FILE`.

Статический `BANKROT_API_TOKEN` пригоден только для короткого ручного запуска: access-токен
имеет ограниченный срок жизни. При `401` без рабочего refresh-токена синхронизация
завершается ошибкой авторизации.

## Настройки

```env
BANKROT_FETCH_RELATED_DATA=true
BANKROT_PAGE_SIZE=20
BANKROT_RELATED_PAGE_SIZE=20
BANKROT_RELATED_MAX_PAGES=1000
BANKROT_RELATED_DATASETS=
```

`BANKROT_RELATED_DATASETS` — необязательный CSV-фильтр, например:

```env
BANKROT_RELATED_DATASETS=publications,properties,sales
```

Пустое значение включает все поддерживаемые наборы.

## API проекта

Краткая информация остаётся в профиле компании:

```http
GET /api/v1/companies/{unp}
```

Полные сохранённые сведения загружаются отдельно:

```http
GET /api/v1/companies/{unp}/bankruptcy
```

Ответ содержит основную карточку, исходные ответы, судебные решения, ошибки загрузки и
массив `datasets`. Интерфейс вызывает этот endpoint только после нажатия
«Показать все сведения реестра».

## Развёртывание

1. Применить миграцию `bank1datasets`.
2. Настроить действующий refresh-токен или access-токен.
3. Запустить `app.tasks.bankrot_tasks.sync_bankrot_cases` вручную либо включить
   `BANKROT_SCHEDULE_ENABLED=true`.
4. Проверить `bankrot_sync_runs.stats_json`: счётчики `datasets_fetched` и
   `datasets_failed` показывают полноту дочерних разделов.
