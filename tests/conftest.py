"""Shared fixtures: a small warehouse built once per test session."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import PipelineConfig  # noqa: E402
from src.generate_data import generate_all  # noqa: E402
from src.load import load_raw  # noqa: E402
from src.transform import run_sql_models  # noqa: E402


@pytest.fixture(scope="session")
def small_warehouse(tmp_path_factory) -> Path:
    """Full pipeline (without export) on 3,000 simulated patients."""
    db = tmp_path_factory.mktemp("wh") / "warehouse.db"
    load_raw(generate_all(n_patients=3_000, seed=7), db)
    run_sql_models(db, PipelineConfig().sql_dir)
    return db
