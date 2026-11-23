"""Project settings: study period, business rules and paths.

Business rules that the SQL models need (study window, program start, triage targets) are also loaded
into reference tables (`ref_parameters`, `ref_triage_levels`), so the SQL never hard-codes them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Study period of the hospital extract (admissions discharged in this window)
START_DATE = "2023-01-01"
END_DATE = "2026-06-30"

# 30-day all-cause readmission window (CMS-style definition)
READMISSION_WINDOW_DAYS = 30

# Transitional care program: nurse follow-up call 24-72 h after discharge for target conditions
PROGRAM_START = "2025-01-01"
PROGRAM_HOSPITALS = ("H01", "H03")

# Manchester Triage System: maximum minutes from arrival to first provider contact.
# Level 1 is "immediate"; it is measured as seen within 5 minutes.
TRIAGE_LEVELS = {
    1: ("Immediate", "Red", 5),
    2: ("Very urgent", "Orange", 10),
    3: ("Urgent", "Yellow", 60),
    4: ("Standard", "Green", 120),
    5: ("Non-urgent", "Blue", 240),
}


@dataclass
class PipelineConfig:
    n_patients: int = 24_000
    seed: int = 42
    raw_dir: Path = ROOT / "data" / "raw"
    db_path: Path = ROOT / "data" / "warehouse.db"
    sql_dir: Path = ROOT / "sql"
    export_dir: Path = ROOT / "exports"
