"""Load step: save the raw extract as CSV files (as received) and load them into raw_* tables."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pandas as pd

from src.config import END_DATE, PROGRAM_START, READMISSION_WINDOW_DAYS, START_DATE

log = logging.getLogger(__name__)

REFERENCE_TABLES = {"hospitals", "diagnoses", "triage_levels"}


def parameters_table() -> pd.DataFrame:
    """Business rules as a one-row table, so the SQL models read them instead of hard-coding them."""
    return pd.DataFrame([{
        "study_start": START_DATE,
        "study_end": END_DATE,
        "readmission_window_days": READMISSION_WINDOW_DAYS,
        # Index stays discharged after this date cannot complete a 30-day follow-up inside the extract
        "last_index_discharge": (pd.Timestamp(END_DATE) - pd.Timedelta(days=READMISSION_WINDOW_DAYS)).strftime("%Y-%m-%d"),
        "program_start": PROGRAM_START,
    }])


def save_raw_files(tables: dict[str, pd.DataFrame], raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(raw_dir / f"{name}.csv", index=False)


def load_raw(tables: dict[str, pd.DataFrame], db_path: Path) -> None:
    """Replace the database with a fresh copy of the raw extract and the reference tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    with sqlite3.connect(db_path) as conn:
        for name, df in tables.items():
            prefix = "ref" if name in REFERENCE_TABLES else "raw"
            df.to_sql(f"{prefix}_{name}", conn, index=False)
            log.info("Loaded %s_%s (%d rows)", prefix, name, len(df))
        parameters_table().to_sql("ref_parameters", conn, index=False)
