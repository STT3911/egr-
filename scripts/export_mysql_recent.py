#!/usr/bin/env python3
"""Inspect a remote read-only MySQL database and export selected rows to SQLite.

The password is requested interactively and is never stored in the output file.
Tables are exported only when explicitly configured with --date-column or
--full-table; all other tables are created locally without data.
"""

from __future__ import annotations

import argparse
import calendar
import getpass
import json
import sqlite3
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

try:
    import pymysql
except ImportError:  # pragma: no cover - user-facing dependency check
    raise SystemExit("PyMySQL is required: python -m pip install PyMySQL")


DATE_TYPES = {"date", "datetime", "timestamp"}
INTEGER_TYPES = {
    "bigint",
    "bit",
    "int",
    "integer",
    "mediumint",
    "smallint",
    "tinyint",
    "year",
}
REAL_TYPES = {"double", "float", "real"}
BLOB_TYPES = {
    "binary",
    "blob",
    "longblob",
    "mediumblob",
    "tinyblob",
    "varbinary",
}


def mysql_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def subtract_months(value: datetime, months: int) -> datetime:
    absolute_month = value.year * 12 + value.month - 1 - months
    year, month_zero = divmod(absolute_month, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def parse_mapping(values: Iterable[str], option: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"{option} expects TABLE=COLUMN, got: {value!r}")
        table, column = (part.strip() for part in value.split("=", 1))
        if not table or not column:
            raise SystemExit(f"{option} expects TABLE=COLUMN, got: {value!r}")
        result[table] = column
    return result


def connect(args: argparse.Namespace):
    password = getpass.getpass(f"Password for {args.user}@{args.host}: ")
    return pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=password,
        database=args.database,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
        write_timeout=args.read_timeout,
    )


def load_schema(connection, database: str) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    with connection.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            """
            SELECT TABLE_NAME, COALESCE(TABLE_ROWS, 0) AS TABLE_ROWS
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
            """,
            (database,),
        )
        tables = list(cursor.fetchall())
        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE,
                   COLUMN_KEY, ORDINAL_POSITION
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """,
            (database,),
        )
        columns: dict[str, list[dict[str, Any]]] = {}
        for row in cursor.fetchall():
            columns.setdefault(str(row["TABLE_NAME"]), []).append(row)
    return tables, columns


def inspect_schema(
    tables: list[dict[str, Any]], columns: dict[str, list[dict[str, Any]]]
) -> None:
    print("table\testimated_rows\tdate_columns")
    for table in tables:
        name = str(table["TABLE_NAME"])
        date_columns = [
            str(column["COLUMN_NAME"])
            for column in columns.get(name, [])
            if str(column["DATA_TYPE"]).lower() in DATE_TYPES
        ]
        print(
            f"{name}\t{int(table['TABLE_ROWS'] or 0)}\t"
            f"{','.join(date_columns) or '-'}"
        )


def sqlite_type(mysql_type: str) -> str:
    value = mysql_type.lower()
    if value in INTEGER_TYPES:
        return "INTEGER"
    if value in REAL_TYPES:
        return "REAL"
    if value in BLOB_TYPES:
        return "BLOB"
    return "TEXT"


def normalize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bytes)):
        return value
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def create_sqlite_table(
    local: sqlite3.Connection,
    table: str,
    columns: list[dict[str, Any]],
) -> None:
    primary_columns = [
        str(column["COLUMN_NAME"])
        for column in columns
        if str(column.get("COLUMN_KEY") or "") == "PRI"
    ]
    definitions: list[str] = []
    for column in columns:
        name = str(column["COLUMN_NAME"])
        definition = f"{sqlite_identifier(name)} {sqlite_type(str(column['DATA_TYPE']))}"
        if str(column.get("IS_NULLABLE")) == "NO":
            definition += " NOT NULL"
        definitions.append(definition)
    if primary_columns:
        definitions.append(
            "PRIMARY KEY ("
            + ", ".join(sqlite_identifier(name) for name in primary_columns)
            + ")"
        )
    local.execute(
        f"CREATE TABLE {sqlite_identifier(table)} ({', '.join(definitions)})"
    )


def export_table(
    remote,
    local: sqlite3.Connection,
    table: str,
    columns: list[dict[str, Any]],
    *,
    date_column: str | None,
    cutoff: datetime,
    copy_data: bool,
    batch_size: int,
) -> int:
    create_sqlite_table(local, table, columns)
    if not copy_data:
        return 0

    column_names = [str(column["COLUMN_NAME"]) for column in columns]
    select_sql = f"SELECT * FROM {mysql_identifier(table)}"
    params: tuple[Any, ...] = ()
    if date_column:
        select_sql += f" WHERE {mysql_identifier(date_column)} >= %s"
        params = (cutoff,)

    placeholders = ", ".join("?" for _ in column_names)
    insert_sql = (
        f"INSERT INTO {sqlite_identifier(table)} ("
        + ", ".join(sqlite_identifier(name) for name in column_names)
        + f") VALUES ({placeholders})"
    )

    copied = 0
    with remote.cursor(pymysql.cursors.SSCursor) as cursor:
        cursor.execute(select_sql, params)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            local.executemany(
                insert_sql,
                [tuple(normalize_value(value) for value in row) for row in rows],
            )
            local.commit()
            copied += len(rows)
            print(f"  {table}: {copied} rows", flush=True)
    return copied


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--date-column", action="append", default=[], metavar="TABLE=COLUMN")
    parser.add_argument("--full-table", action="append", default=[], metavar="TABLE")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--connect-timeout", type=int, default=15)
    parser.add_argument("--read-timeout", type=int, default=120)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.months < 1 or args.batch_size < 1:
        raise SystemExit("--months and --batch-size must be positive")

    date_map = parse_mapping(args.date_column, "--date-column")
    full_tables = {value.strip() for value in args.full_table if value.strip()}
    if not args.inspect and args.output is None:
        raise SystemExit("--output is required unless --inspect is used")

    remote = connect(args)
    try:
        tables, columns = load_schema(remote, args.database)
        table_names = {str(row["TABLE_NAME"]) for row in tables}
        unknown_tables = (set(date_map) | full_tables) - table_names
        if unknown_tables:
            raise SystemExit(f"Unknown tables: {', '.join(sorted(unknown_tables))}")
        for table, column in date_map.items():
            known_columns = {str(item["COLUMN_NAME"]) for item in columns[table]}
            if column not in known_columns:
                raise SystemExit(f"Unknown date column: {table}.{column}")

        if args.inspect:
            inspect_schema(tables, columns)
            if args.output is None:
                return 0

        output = args.output.resolve()
        if output.exists():
            if not args.overwrite:
                raise SystemExit(f"Output already exists: {output}; use --overwrite")
            output.unlink()
        output.parent.mkdir(parents=True, exist_ok=True)
        cutoff = subtract_months(datetime.now(), args.months)

        local = sqlite3.connect(output)
        try:
            local.execute(
                """
                CREATE TABLE _export_manifest (
                    table_name TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    date_column TEXT,
                    cutoff TEXT,
                    rows_copied INTEGER NOT NULL
                )
                """
            )
            for table_row in tables:
                table = str(table_row["TABLE_NAME"])
                date_column = None if table in full_tables else date_map.get(table)
                copy_data = table in full_tables or date_column is not None
                mode = "full" if table in full_tables else "recent" if date_column else "schema_only"
                print(f"Exporting {table} ({mode})", flush=True)
                copied = export_table(
                    remote,
                    local,
                    table,
                    columns[table],
                    date_column=date_column,
                    cutoff=cutoff,
                    copy_data=copy_data,
                    batch_size=args.batch_size,
                )
                local.execute(
                    "INSERT INTO _export_manifest VALUES (?, ?, ?, ?, ?)",
                    (table, mode, date_column, cutoff.isoformat(sep=" "), copied),
                )
                local.commit()
        finally:
            local.close()
        print(f"Done: {output}")
        print(f"Cutoff: {cutoff.isoformat(sep=' ')}")
        return 0
    finally:
        remote.close()


if __name__ == "__main__":
    sys.exit(main())
