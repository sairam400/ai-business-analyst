"""Loads one or more CSVs into a fresh SQLite database, one table per file.

Deliberately schema-agnostic: table columns and types come from whatever
pandas infers from the CSV, not a fixed e-commerce schema. This is what lets
the profiler degrade gracefully on an arbitrary business CSV instead of only
working on the shipped sample data.
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

from src.config import SETTINGS

_TABLE_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_]")


class CSVLoadError(Exception):
    pass


def _table_name(csv_path: Path) -> str:
    name = _TABLE_NAME_PATTERN.sub("_", csv_path.stem).strip("_").lower()
    if not name or name[0].isdigit():
        name = f"t_{name}"
    return name


def load_csvs(csv_paths: list[Path], db_path: Path = None) -> dict[str, int]:
    """Replaces db_path with a fresh database built from csv_paths.
    Returns {table_name: row_count}."""
    db_path = db_path or SETTINGS.db_path
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    row_counts = {}
    conn = sqlite3.connect(db_path)
    try:
        for csv_path in csv_paths:
            if not csv_path.exists():
                raise CSVLoadError(f"csv not found: {csv_path}")
            table = _table_name(csv_path)
            try:
                df = pd.read_csv(csv_path)
            except Exception as exc:
                raise CSVLoadError(f"could not parse {csv_path.name} as CSV: {exc}") from exc
            if len(df) > SETTINGS.max_upload_rows_per_table:
                raise CSVLoadError(
                    f"{csv_path.name} has {len(df)} rows, exceeds the "
                    f"{SETTINGS.max_upload_rows_per_table}-row limit"
                )
            df.columns = [_TABLE_NAME_PATTERN.sub("_", str(c)).strip("_").lower() for c in df.columns]
            df.to_sql(table, conn, if_exists="replace", index=False)
            row_counts[table] = len(df)
        conn.commit()
    finally:
        conn.close()
    return row_counts


def load_directory(dir_path: Path, db_path: Path = None) -> dict[str, int]:
    csv_paths = sorted(dir_path.glob("*.csv"))
    if not csv_paths:
        raise CSVLoadError(f"no CSV files found in {dir_path}")
    return load_csvs(csv_paths, db_path)


if __name__ == "__main__":
    counts = load_directory(SETTINGS.sample_data_dir)
    print(f"loaded into {SETTINGS.db_path}: {counts}")
