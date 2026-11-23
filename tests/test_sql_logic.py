"""Business rules tested on a hand-made extract where the right answer is known."""
import sqlite3

import pandas as pd
import pytest

from src.config import PipelineConfig
from src.generate_data import generate_reference_tables
from src.load import load_raw
from src.transform import run_sql_models

PATIENTS = [
    # patient_id, birth_date, sex, home_department, payer_type
    ("P1", "1950-01-01", "M", "Guatemala", "Self-pay"),
    ("P2", "1960-01-01", "Female", "Guatemala", "Private insurance"),
    ("P3", "1900-01-01", "masculino", "Guatemala", "Private insurance"),  # placeholder birth date
    ("P4", "1970-01-01", " f", "Escuintla", "Corporate agreement"),
    ("P5", "1945-01-01", "F", "Guatemala", "Self-pay"),
    ("P6", "1955-01-01", "M", "Guatemala", "Self-pay"),
]

ADMISSIONS = [
    # id, patient, hospital, admit, discharge, type, icd10, charlson, icu, disposition, cost
    ("A1", "P1", "H01", "2025-01-01 10:00:00", "2025-01-10 10:00:00", "Emergency", "I50.9", 3, 0, "Home", 30000),
    ("A2", "P1", "H02", "2025-01-20T08:00:00", "2025-01-25 08:00:00", "Emergency", "i509 ", 3, 0, "Home", 25000),  # readmission at another hospital, dirty code
    ("A2", "P1", "H02", "2025-01-20T08:00:00", "2025-01-25 08:00:00", "Emergency", "i509 ", 3, 0, "Home", 25000),  # duplicate row
    ("A3", "P2", "H01", "2025-02-01 10:00:00", "2025-02-05 10:00:00", "Elective", "C18.9", 2, 0, "Home", 50000),
    ("A4", "P2", "H01", "2025-02-15 10:00:00", "2025-02-20 10:00:00", "Elective", "C189", 2, 0, "Home", 50000),  # planned -> not a readmission
    ("A5", "P3", "H03", "2025-03-01 10:00:00", "2025-03-05 10:00:00", "Emergency", "A41.9", 4, 2, "Died", 60000),  # died -> not an index stay
    ("A6", "P4", "H04", "2025-04-01 10:00:00", "2025-04-03 10:00:00", "Urgent", "N39.0", 0, 0, "Home", 10000),
    ("A7", "P4", "H04", "2025-05-10 10:00:00", "2025-05-12 10:00:00", "Emergency", "N39.0", 0, 0, "Home", None),  # 37 days later -> not counted, unbilled
    ("A8", "P5", "H05", "2025-06-01 10:00:00", "2025-06-04 10:00:00", "Emergency", "J18.9", 2, 0, "Transferred", 20000),  # transfer -> not index
    ("A9", "P5", "H05", "2025-06-10 10:00:00", "2025-06-09 10:00:00", "Emergency", "J18.9", 2, 0, "Home", 20000),  # discharge before admission -> rejected
    ("A10", "P6", "H01", "2026-06-10 10:00:00", "2026-06-15 10:00:00", "Emergency", "J44.1", 1, 0, "Home", 15000),  # < 30 days of follow-up left
]

ED_VISITS = [
    # visit, hospital, arrival, triage, provider, departure, level, disposition, admission
    ("E1", "H01", "2025-01-01 08:00:00", "2025-01-01 08:05:00", "2025-01-01 08:40:00", "2025-01-01 10:00:00", 3, "Admitted", "A1"),
    ("E2", "H01", "2025-01-02 08:00:00", "2025-01-02 08:05:00", "2025-01-02 07:00:00", "2025-01-02 09:00:00", 4, "Discharged", None),  # clock error
    ("E3", "H02", "2025-01-03T20:00:00", "2025-01-03 20:10:00", None, "2025-01-03 23:00:00", 5, "Left without being seen", None),
]


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    tables = generate_reference_tables()
    tables["patients"] = pd.DataFrame(PATIENTS, columns=["patient_id", "birth_date", "sex", "home_department", "payer_type"])
    tables["admissions"] = pd.DataFrame(ADMISSIONS, columns=[
        "admission_id", "patient_id", "hospital_id", "admit_ts", "discharge_ts", "admission_type", "primary_icd10",
        "charlson_index", "icu_days", "discharge_disposition", "total_cost_gtq"])
    tables["followup_calls"] = pd.DataFrame([("C1", "A1", "2025-01-11 10:00:00", "Completed")],
                                            columns=["call_id", "admission_id", "call_ts", "call_status"])
    tables["ed_visits"] = pd.DataFrame(ED_VISITS, columns=[
        "visit_id", "hospital_id", "arrival_ts", "triage_ts", "provider_ts", "departure_ts", "triage_level",
        "ed_disposition", "admission_id"])
    path = tmp_path_factory.mktemp("logic") / "test.db"
    load_raw(tables, path)
    run_sql_models(path, PipelineConfig().sql_dir)
    conn = sqlite3.connect(path)
    yield conn
    conn.close()


def fact(conn):
    return pd.read_sql("SELECT * FROM fct_admissions", conn).set_index("admission_id")


def test_staging_deduplicates_and_rejects(db):
    f = fact(db)
    assert sorted(f.index) == sorted({"A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A10"})
    rejected = pd.read_sql("SELECT admission_id, reject_reason FROM stg_rejected_admissions", db)
    assert rejected.to_dict("records") == [{"admission_id": "A9", "reject_reason": "Discharge before admission"}]


def test_staging_cleans_codes_sex_and_birth_dates(db):
    f = fact(db)
    assert f.loc["A2", "icd10_code"] == "I50.9"
    assert f.loc["A4", "icd10_code"] == "C18.9"
    p = pd.read_sql("SELECT * FROM stg_patients", db).set_index("patient_id")
    assert p["sex"].to_dict() == {"P1": "M", "P2": "F", "P3": "M", "P4": "F", "P5": "F", "P6": "M"}
    assert pd.isna(p.loc["P3", "birth_date"])
    assert f.loc["A5", "age_band"] == "Unknown"


def test_unplanned_readmission_at_another_hospital_counts(db):
    f = fact(db)
    assert f.loc["A1", "is_readmitted_30d"] == 1
    assert f.loc["A1", "readmission_id"] == "A2"
    assert f.loc["A1", "days_to_readmission"] == pytest.approx(9.92, abs=0.01)
    assert f.loc["A2", "is_readmission"] == 1 and f.loc["A2", "readmission_of"] == "A1"


def test_planned_late_died_transferred_and_censored_stays(db):
    f = fact(db)
    assert f.loc["A3", "is_index_stay"] == 1 and f.loc["A3", "is_readmitted_30d"] == 0  # planned follow-up
    assert f.loc["A4", "is_readmission"] == 0
    assert f.loc["A6", "is_readmitted_30d"] == 0                                          # 37 days later
    assert f.loc["A5", "is_index_stay"] == 0                                              # died
    assert f.loc["A8", "is_index_stay"] == 0                                              # transferred
    assert f.loc["A10", "is_index_stay"] == 0                                             # incomplete follow-up


def test_program_flags(db):
    f = fact(db)
    assert f.loc["A1", "program_group"] == "Program hospitals"
    assert f.loc["A1", "program_period"] == "Post"
    assert f.loc["A1", "is_program_eligible"] == 1 and f.loc["A1", "call_status"] == "Completed"
    assert f.loc["A2", "is_program_eligible"] == 0  # comparison hospital


def test_ed_wait_times_and_clock_errors(db):
    v = pd.read_sql("SELECT * FROM fct_ed_visits", db).set_index("visit_id")
    assert v.loc["E1", "wait_minutes"] == pytest.approx(40)
    assert v.loc["E1", "met_triage_target"] == 1          # level 3 target is 60 minutes
    assert pd.isna(v.loc["E2", "wait_minutes"]) and v.loc["E2", "is_clock_error"] == 1
    assert v.loc["E3", "is_lwbs"] == 1 and v.loc["E3", "arrival_hour"] == 20


def test_cost_metrics_skip_unbilled_stays(db):
    c = pd.read_sql("SELECT * FROM mart_cost_by_diagnosis WHERE icd10_code = 'N39.0'", db).iloc[0]
    assert c["stays"] == 2 and c["billed_stays"] == 1
    assert c["avg_cost_gtq"] == 10000
