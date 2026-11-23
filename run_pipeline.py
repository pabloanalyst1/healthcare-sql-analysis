"""Hospital analytics pipeline: readmissions, ED waiting times and costs by diagnosis.

Steps:
  1/5 EXTRACT    - generate the synthetic EHR + billing extract (messy, like the real thing)
  2/5 LOAD       - save raw CSV files and load raw_* / ref_* tables into SQLite
  3/5 TRANSFORM  - run the SQL models: staging -> dimensions -> facts -> marts
  4/5 QUALITY    - data quality checks (the pipeline stops if any fails)
  5/5 EXPORT     - marts to CSV for the dashboard

Usage:
  python run_pipeline.py                  # default: 24,000 patients, seed 42
  python run_pipeline.py --patients 5000 --seed 7
"""
from __future__ import annotations

import argparse
import logging
import time

from src.config import PipelineConfig
from src.export import export_marts
from src.generate_data import generate_all
from src.load import load_raw, save_raw_files
from src.quality import run_quality_checks
from src.transform import run_sql_models

log = logging.getLogger("pipeline")


def run(cfg: PipelineConfig) -> None:
    t0 = time.perf_counter()
    log.info("1/5 EXTRACT   - simulating %s patients (seed %s)", f"{cfg.n_patients:,}", cfg.seed)
    tables = generate_all(n_patients=cfg.n_patients, seed=cfg.seed)

    log.info("2/5 LOAD      - raw files and raw tables")
    save_raw_files(tables, cfg.raw_dir)
    load_raw(tables, cfg.db_path)

    log.info("3/5 TRANSFORM - SQL models")
    run_sql_models(cfg.db_path, cfg.sql_dir)

    log.info("4/5 QUALITY   - data quality checks")
    run_quality_checks(cfg.db_path)

    log.info("5/5 EXPORT    - marts to CSV")
    export_marts(cfg.db_path, cfg.export_dir)

    log.info("Done in %.1f s. Warehouse: %s", time.perf_counter() - t0, cfg.db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--patients", type=int, default=24_000, help="number of patients to simulate")
    parser.add_argument("--seed", type=int, default=42, help="random seed (same seed = same data)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    run(PipelineConfig(n_patients=args.patients, seed=args.seed))


if __name__ == "__main__":
    main()
