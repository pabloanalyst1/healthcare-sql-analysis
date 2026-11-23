"""The simulated extract is reproducible, consistent, and messy in the documented ways."""
import pandas as pd

from src.generate_data import generate_all


def test_same_seed_same_data():
    a = generate_all(n_patients=500, seed=1)
    b = generate_all(n_patients=500, seed=1)
    for name in a:
        pd.testing.assert_frame_equal(a[name], b[name])


def test_clean_extract_is_consistent():
    t = generate_all(n_patients=1_000, seed=3, messy=False)
    adm, pat = t["admissions"], t["patients"]
    assert adm["admission_id"].is_unique
    assert set(adm["patient_id"]) <= set(pat["patient_id"])
    assert set(adm["primary_icd10"]) <= set(t["diagnoses"]["icd10_code"])
    assert (pd.to_datetime(adm["discharge_ts"]) > pd.to_datetime(adm["admit_ts"])).all()
    # every follow-up call belongs to a program hospital
    called = adm[adm["admission_id"].isin(t["followup_calls"]["admission_id"])]
    assert set(called["hospital_id"]) <= {"H01", "H03"}


def test_messy_extract_has_the_issues_staging_fixes():
    t = generate_all(n_patients=3_000, seed=5)
    adm = t["admissions"]
    assert adm["admission_id"].duplicated().any()                     # duplicate rows
    assert adm["primary_icd10"].str.contains(r"^[a-z]", regex=True).any()  # lower-case codes
    assert adm["admit_ts"].str.contains("T").any()                     # mixed timestamp formats
    assert adm["total_cost_gtq"].isna().any()                          # unbilled stays
    assert {"Male", "FEMENINO"} & set(t["patients"]["sex"])            # sex coded several ways
