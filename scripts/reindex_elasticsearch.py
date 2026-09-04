"""Build or refresh the Elasticsearch company index from PostgreSQL."""

import argparse

from app.core.database import SessionLocal
from app.services.search_index import reindex_companies


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindex EGR companies into Elasticsearch")
    parser.add_argument("--limit", type=int, default=None, help="Maximum rows to index")
    parser.add_argument("--batch-size", type=int, default=None, help="Bulk batch size")
    parser.add_argument("--recreate", action="store_true", help="Drop and recreate the index")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore a saved checkpoint and start a new pass from the first UNP",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = reindex_companies(
            db,
            batch_size=args.batch_size,
            limit=args.limit,
            recreate=args.recreate,
            resume=not args.no_resume,
        )
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
