"""CLI for explicitly creating/resetting the local demo database."""

import argparse
import os
from pathlib import Path

from production_control.demo.bootstrap import (
    DEFAULT_DEMO_DB_PATH,
    initialize_demo_database,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize the local production-control demo DB")
    parser.add_argument(
        "--db",
        default=os.environ.get("PRODUCTION_CONTROL_DB_PATH", str(DEFAULT_DEMO_DB_PATH)),
        help="SQLite DB path (default: data/demo.db or PRODUCTION_CONTROL_DB_PATH)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="replace an existing demo DB with the deterministic initial fixture",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        path = initialize_demo_database(Path(args.db), reset=args.reset)
    except FileExistsError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"demo database initialized: {path}")


if __name__ == "__main__":
    main()
