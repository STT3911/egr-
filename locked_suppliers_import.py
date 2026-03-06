#!/usr/bin/env python3
import json
import logging
import os
from datetime import datetime
from typing import Optional

import psycopg2


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_connection():
    """Create a synchronous psycopg2 connection using the same env vars as GIAS workers."""
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "db"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "egr_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )
    conn.autocommit = False
    return conn


def create_locked_suppliers_tables(conn):
    """Create tables for locked suppliers if they don't exist."""
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS locked_supplier_authors (
            id          BIGSERIAL PRIMARY KEY,
            uuid        UUID UNIQUE NOT NULL,
            initials    TEXT NOT NULL,
            summary     TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS locked_supplier_reasons (
            id          BIGSERIAL PRIMARY KEY,
            kind        VARCHAR(16) NOT NULL, -- INCLUDE / EXCLUDE
            text        TEXT NOT NULL,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT locked_supplier_reasons_kind_text_uniq
                UNIQUE (kind, text)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS locked_suppliers (
            id              BIGSERIAL PRIMARY KEY,
            uuid            UUID UNIQUE NOT NULL,
            chain_uuid      UUID NOT NULL,
            author_id       BIGINT REFERENCES locked_supplier_authors(id),
            state           VARCHAR(32) NOT NULL,
            name            TEXT NOT NULL,
            provider_unp    VARCHAR(32),
            location        TEXT,
            reg_number      VARCHAR(32),
            add_date        TIMESTAMP,
            del_date        TIMESTAMP,
            base_incl_id    BIGINT REFERENCES locked_supplier_reasons(id),
            base_excl_id    BIGINT REFERENCES locked_supplier_reasons(id),
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS locked_suppliers_provider_unp_idx ON locked_suppliers(provider_unp)",
        "CREATE INDEX IF NOT EXISTS locked_suppliers_state_idx ON locked_suppliers(state)",
    ]

    with conn.cursor() as cur:
        for ddl in ddl_statements:
            cur.execute(ddl)
    conn.commit()
    logger.info("locked_suppliers tables created/verified")


def upsert_author(cur, author: dict) -> Optional[int]:
    """Insert or update author and return id."""
    if not author:
        return None

    cur.execute(
        """
        INSERT INTO locked_supplier_authors (uuid, initials, summary)
        VALUES (%s, %s, %s)
        ON CONFLICT (uuid) DO UPDATE SET
            initials = EXCLUDED.initials,
            summary = EXCLUDED.summary,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
        """,
        (author.get("uuid"), author.get("initials"), author.get("summary")),
    )
    row = cur.fetchone()
    return row[0] if row else None


def upsert_reason(cur, kind: str, text: Optional[str]) -> Optional[int]:
    """Insert or get reason id for given kind/text."""
    if not text:
        return None

    cur.execute(
        """
        INSERT INTO locked_supplier_reasons (kind, text)
        VALUES (%s, %s)
        ON CONFLICT (kind, text) DO UPDATE SET
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
        """,
        (kind, text),
    )
    row = cur.fetchone()
    return row[0] if row else None


def ms_to_ts(value: Optional[int]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0)
    except Exception:
        return None


def import_locked_suppliers(json_path: str = "locked_suppliers.json"):
    logger.info("Loading locked suppliers from %s", json_path)

    if not os.path.exists(json_path):
        raise FileNotFoundError(f"File not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("locked_suppliers.json must contain a JSON array")

    conn = get_connection()
    try:
        create_locked_suppliers_tables(conn)

        with conn.cursor() as cur:
            total = len(data)
            for idx, item in enumerate(data, start=1):
                author = item.get("author") or {}
                author_id = upsert_author(cur, author) if author else None

                base_incl_text = item.get("baseincl")
                base_excl_text = item.get("baseexcl")

                base_incl_id = upsert_reason(cur, "INCLUDE", base_incl_text)
                base_excl_id = upsert_reason(cur, "EXCLUDE", base_excl_text)

                add_date = ms_to_ts(item.get("adddate"))
                del_date = ms_to_ts(item.get("deldate"))

                cur.execute(
                    """
                    INSERT INTO locked_suppliers (
                        uuid,
                        chain_uuid,
                        author_id,
                        state,
                        name,
                        provider_unp,
                        location,
                        reg_number,
                        add_date,
                        del_date,
                        base_incl_id,
                        base_excl_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (uuid) DO UPDATE SET
                        chain_uuid = EXCLUDED.chain_uuid,
                        author_id = EXCLUDED.author_id,
                        state = EXCLUDED.state,
                        name = EXCLUDED.name,
                        provider_unp = EXCLUDED.provider_unp,
                        location = EXCLUDED.location,
                        reg_number = EXCLUDED.reg_number,
                        add_date = EXCLUDED.add_date,
                        del_date = EXCLUDED.del_date,
                        base_incl_id = EXCLUDED.base_incl_id,
                        base_excl_id = EXCLUDED.base_excl_id,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        item.get("uuid"),
                        item.get("chainUuid"),
                        author_id,
                        item.get("state"),
                        item.get("name"),
                        item.get("providerunp"),
                        item.get("location"),
                        item.get("regnumber"),
                        add_date,
                        del_date,
                        base_incl_id,
                        base_excl_id,
                    ),
                )

                if idx % 100 == 0:
                    conn.commit()
                    logger.info("Imported %s/%s locked suppliers", idx, total)

            conn.commit()
            logger.info("Imported all %s locked suppliers", total)
    finally:
        conn.close()


if __name__ == "__main__":
    path = os.getenv("LOCKED_SUPPLIERS_PATH", "locked_suppliers.json")
    import_locked_suppliers(path)

