"""End-to-end: marts reconcile with the facts, exports are written and every case-study query runs."""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from src.export import export_marts

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_case_study import run_queries  # noqa: E402

EXPECTED_MARTS = {
    "mart_readmissions_monthly", "mart_readmissions_by_diagnosis", "mart_hospital_readmissions_risk_adjusted",
    "mart_program_evaluation", "mart_program_quarterly", "mart_followup_call_outcomes", "mart_ed_hourly",
    "mart_ed_monthly", "mart_ed_triage_compliance", "mart_ed_lwbs_by_wait_band", "mart_cost_by_diagnosis",
    "mart_cost_monthly", "mart_readmission_cost", "mart_kpi_summary", "mart_admissions_detail",
}


def test_marts_reconcile_with_facts(small_warehouse):
    with sqlite3.connect(small_warehouse) as conn:
        q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        index_stays = q("SELECT SUM(is_index_stay) FROM fct_admissions")
        readmissions = q("SELECT SUM(is_readmitted_30d) FROM fct_admissions")
        assert q("SELECT SUM(index_stays) FROM mart_readmissions_monthly") == index_stays
        assert q("SELECT SUM(readmissions_30d) FROM mart_readmissions_monthly") == readmissions
        assert q("SELECT SUM(index_stays) FROM mart_program_evaluation") == index_stays
        assert q("SELECT SUM(visits) FROM mart_ed_hourly") == q("SELECT COUNT(*) FROM fct_ed_visits")
        assert abs(q("SELECT SUM(total_cost_gtq) FROM mart_cost_monthly")
                   - q("SELECT SUM(total_cost_gtq) FROM fct_admissions")) < 1
        # risk adjustment: expected readmissions add up to observed across the network
        assert abs(q("SELECT SUM(expected_readmissions) FROM mart_hospital_readmissions_risk_adjusted") - readmissions) < 1


def test_export_writes_every_mart(small_warehouse, tmp_path):
    written = export_marts(small_warehouse, tmp_path)
    assert {p.stem for p in written} == EXPECTED_MARTS
    kpis = pd.read_csv(tmp_path / "mart_kpi_summary.csv").set_index("kpi")
    assert 0.03 < kpis.loc["30-day readmission rate", "last_12_months"] < 0.25


def test_every_case_study_query_runs(small_warehouse):
    results = run_queries(small_warehouse)
    assert len(results) == 12
    for name, question, _, df in results:
        assert question, name
        assert len(df) > 0, name
