"""Read a company's event history directly from the source tables."""
from datetime import date
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session


EventSource = Literal['egr', 'mart', 'license', 'inspection', 'bankrot', 'gias', 'belltpp', 'sez']


class TimelineEvent(BaseModel):
    id: str
    source: EventSource
    date: str | None
    title: str
    details: list[str]
    contract_id: str | None = None


class TimelinePage(BaseModel):
    company_name: str | None
    items: list[TimelineEvent]
    next_cursor: str | None


COMPANY = text("""
    SELECT c.id, coalesce(n.short_name_ru, n.full_name_ru) AS name
    FROM egr_companies c
    LEFT JOIN LATERAL (
        SELECT nullif(btrim(short_name_ru), '') AS short_name_ru,
               nullif(btrim(full_name_ru), '') AS full_name_ru
        FROM egr_company_names_history WHERE company_id = c.id
        ORDER BY (valid_to IS NULL) DESC, valid_to DESC NULLS LAST,
                 valid_from DESC NULLS LAST, id
        LIMIT 1
    ) n ON true
    WHERE c.unp = :unp
""")

# 11100 = initial registration. 21600/21601 = notices of location change.
# Only pair a one-to-one event and history entry of the corresponding kind/day.
EVENTS = text("""
    WITH registry_events AS (
        SELECT e.*, r.name AS event_name, a.name AS authority_name,
               count(*) FILTER (WHERE e.event_type_id IN (11100, 21600, 21601))
                   OVER (PARTITION BY e.event_date) AS location_event_count
        FROM egr_company_events e
        LEFT JOIN ref_events r ON r.id = e.event_type_id
        LEFT JOIN ref_authorities a ON a.id = e.decision_authority_id
        WHERE e.company_id = :company_id AND CAST(:source AS text) IN ('all', 'egr')
    ), addresses AS (
        SELECT id, valid_from, full_address, count(*) OVER (PARTITION BY valid_from) AS same_day
        FROM egr_company_addresses_history
        WHERE company_id = :company_id AND CAST(:source AS text) IN ('all', 'egr')
          AND valid_from IS NOT NULL AND nullif(btrim(full_address), '') IS NOT NULL
    ), names AS (
        SELECT id, valid_from, coalesce(nullif(btrim(full_name_ru), ''), short_name_ru, full_name_by) AS name,
               count(*) OVER (PARTITION BY valid_from) AS same_day
        FROM egr_company_names_history
        WHERE company_id = :company_id AND CAST(:source AS text) IN ('all', 'egr')
          AND valid_from IS NOT NULL
    ), linked AS (
        SELECT e.*, a.id AS address_id, a.full_address, n.id AS name_id, n.name AS company_name
        FROM registry_events e
        LEFT JOIN addresses a ON a.valid_from = e.event_date AND a.same_day = 1
            AND e.location_event_count = 1 AND e.event_type_id IN (11100, 21600, 21601)
        LEFT JOIN names n ON n.valid_from = e.event_date AND n.same_day = 1
            AND e.location_event_count = 1 AND e.event_type_id = 11100
    ), sez_parts AS (
        SELECT s.*, CASE
            WHEN btrim(registry_entry_date) ~ '^[0-9]{1,2}[.][0-9]{1,2}[.][0-9]{4}$'
            THEN ARRAY[split_part(btrim(registry_entry_date), '.', 3),
                       split_part(btrim(registry_entry_date), '.', 2),
                       split_part(btrim(registry_entry_date), '.', 1)]
            WHEN btrim(registry_entry_date) ~ '^[0-9]{4}(-[0-9]{2}(-[0-9]{2}([T ].*)?)?)?$'
            THEN string_to_array(left(btrim(registry_entry_date), 10), '-')
        END AS parts
        FROM eaeu_sez_resident_records s
        WHERE s.unp = :unp AND CAST(:source AS text) IN ('all', 'sez')
    ), sez_dates AS (
        SELECT s.*, CASE WHEN CAST(parts[1] AS int) BETWEEN 1 AND 9999 AND
                           coalesce(CAST(parts[2] AS int), 1) BETWEEN 1 AND 12
                      THEN make_date(CAST(parts[1] AS int), coalesce(CAST(parts[2] AS int), 1), 1)
                      END AS month_start, coalesce(CAST(parts[3] AS int), 1) AS day_number
        FROM sez_parts s
    ), events AS (
        SELECT 'egr:event:' || coalesce(CAST(event_record_id AS text), CAST(id AS text)) AS id,
               'egr' AS source, event_date AS event_day, 'day' AS precision,
               coalesce(event_name, 'Регистрационное событие') AS title,
               ARRAY['Документ №' || nullif(btrim(document_number), ''),
                     CASE WHEN authority_name !~ '^(Орган [0-9]+|[0-9]+|Неизвестный орган)$'
                          THEN authority_name END,
                     notes, 'Наименование: ' || company_name, 'Адрес: ' || full_address] AS details,
               CAST(NULL AS text) AS contract_id
        FROM linked
        UNION ALL
        SELECT 'egr:address:' || CAST(id AS text), 'egr', valid_from, 'day', 'Начало действия адреса',
               ARRAY[full_address], NULL
        FROM addresses a WHERE NOT EXISTS (SELECT 1 FROM linked e WHERE e.address_id = a.id)
        UNION ALL
        SELECT 'egr:name:' || CAST(id AS text), 'egr', valid_from, 'day', 'Начало действия наименования',
               ARRAY[name], NULL
        FROM names n WHERE NOT EXISTS (SELECT 1 FROM linked e WHERE e.name_id = n.id)
        UNION ALL
        SELECT 'egr:ved:' || CAST(id AS text), 'egr', valid_from, 'day', 'Начало действия вида деятельности',
               ARRAY[concat_ws(' — ', ved_code, ved_name)], NULL
        FROM egr_company_ved_history
        WHERE company_id = :company_id AND valid_from IS NOT NULL AND CAST(:source AS text) IN ('all', 'egr')
        UNION ALL
        SELECT 'mart:' || CAST(id AS text), 'mart', inclusion_date, 'day', 'Запись в торговом реестре',
               ARRAY[coalesce(object_name, object_type, legal_name), 'Регистрация №' || registration_number], NULL
        FROM trade_registry_records WHERE unp = :unp AND CAST(:source AS text) IN ('all', 'mart')
        UNION ALL
        SELECT 'license:' || CAST(license_id AS text), 'license', CAST(activity_date_start AS date),
               'day', 'Начало действия лицензии', ARRAY[generated_number, activity_type_name], NULL
        FROM license_records WHERE holder_unp = :unp AND CAST(:source AS text) IN ('all', 'license')
        UNION ALL
        SELECT 'inspection:' || CAST(id AS text), 'inspection',
               CASE WHEN plan_year BETWEEN 1 AND 9999 THEN make_date(plan_year,
                   CASE WHEN start_month_no BETWEEN 1 AND 12 THEN start_month_no ELSE 1 END, 1) END,
               CASE WHEN start_month_no BETWEEN 1 AND 12 THEN 'month' ELSE 'year' END,
               'Плановая проверка', ARRAY[plan_title, controller_authority], NULL
        FROM inspection_plan_records WHERE subject_unp = :unp AND CAST(:source AS text) IN ('all', 'inspection')
        UNION ALL
        SELECT 'bankrot:' || CAST(case_id AS text), 'bankrot', start_date, 'day', 'Дело о банкротстве',
               ARRAY[number, court], NULL
        FROM bankrot_cases WHERE debtor_unp = :unp AND CAST(:source AS text) IN ('all', 'bankrot')
        UNION ALL
        SELECT 'gias:' || CAST(contract_id AS text), 'gias',
               CAST(contract_date AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Minsk' AS date),
               'day', 'Договор ГИАС',
               ARRAY[title, 'Договор №' || coalesce(registration_number, contract_number)], CAST(contract_id AS text)
        FROM gias_contracts
        WHERE CAST(:source AS text) IN ('all', 'gias')
          AND (provider_unp = :unp OR customer_unp = :unp
               OR (provider_unp IS NULL AND provider_company_id = :company_id)
               OR (customer_unp IS NULL AND customer_company_id = :company_id))
        UNION ALL
        SELECT 'belltpp:' || CAST(id AS text), 'belltpp', issue_date, 'day', 'Сертификат БелТПП',
               ARRAY['Сертификат №' || cert_number], NULL
        FROM belltpp_own_certificates WHERE holder_unp = :unp AND CAST(:source AS text) IN ('all', 'belltpp')
        UNION ALL
        SELECT 'sez:' || CAST(item_id AS text), 'sez',
               CASE WHEN day_number BETWEEN 1 AND 31 AND
                         month_start + (day_number - 1) < month_start + interval '1 month'
                    THEN month_start + (day_number - 1) END,
               CASE array_length(parts, 1) WHEN 1 THEN 'year' WHEN 2 THEN 'month' ELSE 'day' END,
               'Запись в реестре СЭЗ', ARRAY[coalesce(sez_name, project_name, full_name)], NULL
        FROM sez_dates
    ), ordered AS (
        SELECT *, coalesce(event_day, DATE '0001-01-01') AS sort_day,
               CASE precision WHEN 'year' THEN event_day + interval '1 year' - interval '1 day'
                              WHEN 'month' THEN event_day + interval '1 month' - interval '1 day'
                              ELSE event_day END AS last_day
        FROM events
    )
    SELECT id, source, precision, event_day, sort_day, title, details, contract_id
    FROM ordered
    WHERE (CAST(:date_from AS date) IS NULL OR last_day >= :date_from)
      AND (CAST(:date_to AS date) IS NULL OR event_day <= :date_to)
      AND (CAST(:cursor_day AS date) IS NULL OR (sort_day, id) < (:cursor_day, :cursor_id))
    ORDER BY sort_day DESC, id DESC
    LIMIT :limit
""")


def company_timeline(
    db: Session, unp: int, *, source: EventSource | None = None,
    date_from: date | None = None, date_to: date | None = None,
    cursor: str | None = None, limit: int = 20,
) -> TimelinePage | None:
    if date_from and date_to and date_from > date_to:
        raise ValueError('Дата начала периода позже даты окончания')
    cursor_day = cursor_id = None
    if cursor:
        day, separator, cursor_id = cursor.partition('|')
        if not separator or not cursor_id:
            raise ValueError('Некорректный указатель страницы')
        try:
            cursor_day = date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError('Некорректный указатель страницы') from exc

    company = db.execute(COMPANY, {'unp': unp}).mappings().one_or_none()
    if company is None:
        return None
    rows = db.execute(EVENTS, {
        'company_id': company['id'], 'unp': unp, 'source': source or 'all',
        'date_from': date_from, 'date_to': date_to, 'cursor_day': cursor_day,
        'cursor_id': cursor_id, 'limit': limit + 1,
    }).mappings().all()
    items = []
    date_lengths = {'year': 4, 'month': 7, 'day': 10}
    for row in rows[:limit]:
        event_date = row['event_day']
        items.append(TimelineEvent(
            id=row['id'], source=row['source'],
            date=event_date.isoformat()[:date_lengths[row['precision']]] if event_date else None,
            title=row['title'], details=[part.strip() for part in row['details'] if part and part.strip()],
            contract_id=row['contract_id'],
        ))
    last = rows[limit - 1] if len(rows) > limit else None
    next_cursor = f"{last['sort_day'].isoformat()}|{last['id']}" if last else None
    return TimelinePage(company_name=company['name'], items=items, next_cursor=next_cursor)
