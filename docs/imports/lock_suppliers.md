# Таблицы для реестра недобросовестных поставщиков (`data/imports/locked_suppliers/locked_suppliers.json`)

## 1. Основная таблица `locked_suppliers`

- **id** — `bigserial`, PK  
- **uuid** — `uuid`, уникальный идентификатор записи (из `uuid`)  
- **chain_uuid** — `uuid`, идентификатор цепочки версий (из `chainUuid`)  
- **author_id** — `bigint`, FK → `locked_supplier_authors.id`  
- **state** — `varchar(32)`, состояние записи (например, `ACTUAL`)  
- **name** — `text`, наименование поставщика (из `name`)  
- **provider_unp** — `varchar(32)`, УНП / ИНН поставщика (из `providerunp`)  
- **location** — `text`, адрес местонахождения (из `location`)  
- **reg_number** — `varchar(32)`, регистрационный номер в реестре (из `regnumber`)  
- **add_date** — `timestamp`, дата включения в реестр (из `adddate`, мс → timestamp)  
- **del_date** — `timestamp`, дата исключения из реестра (из `deldate`, мс → timestamp, nullable)  
- **base_incl_id** — `bigint`, FK → `locked_supplier_reasons.id` (основание включения, из `baseincl`)  
- **base_excl_id** — `bigint`, FK → `locked_supplier_reasons.id` (основание исключения, из `baseexcl`, nullable)  
- **created_at** — `timestamp`, дата создания записи (по умолчанию `now()`)  
- **updated_at** — `timestamp`, дата обновления записи (по умолчанию `now()`)  

Индексы:
- `UNIQUE (uuid)`  
- `INDEX locked_suppliers_provider_unp_idx (provider_unp)`  
- `INDEX locked_suppliers_state_idx (state)`  

## 2. Справочник авторов `locked_supplier_authors`

- **id** — `bigserial`, PK  
- **uuid** — `uuid`, идентификатор автора (из `author.uuid`)  
- **initials** — `text`, ФИО автора (из `author.initials`)  
- **summary** — `text`, дополнительная информация (из `author.summary`, nullable)  
- **created_at** — `timestamp`  
- **updated_at** — `timestamp`  

Индексы:
- `UNIQUE (uuid)`  

## 3. Справочник оснований `locked_supplier_reasons`

- **id** — `bigserial`, PK  
- **kind** — `varchar(16)`, тип основания (`INCLUDE` / `EXCLUDE`)  
- **text** — `text`, текст основания (из `baseincl` / `baseexcl`)  
- **created_at** — `timestamp`  
- **updated_at** — `timestamp`  

Индексы:
- `UNIQUE (kind, text)`  
