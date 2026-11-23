"""Synthetic extract from the EHR and billing systems of a fictional private hospital network in Guatemala.

The data is simulated, but the mechanics behind it are realistic, so the analysis has real signal to find:

* **Admissions** follow diagnosis-specific length of stay, ICU use, mortality and cost. Respiratory
  admissions peak in the rainy season (May-October).
* **Readmissions are not random.** The chance of an unplanned readmission within 30 days rises with
  age, comorbidities (Charlson index), self-pay status and leaving against medical advice, and varies
  by hospital. Patients can be readmitted to any hospital in the network.
* **Planned readmissions** (chemotherapy cycles, scheduled procedures) exist and must be excluded.
* **A transitional care program** (nurse follow-up call after discharge) starts in January 2025 at
  two hospitals for four target conditions. A completed call lowers the odds of readmission.
  Readmissions also drift down slowly everywhere, so a naive before/after comparison overstates
  the program effect; a difference-in-differences design is needed.
* **Emergency department waits** depend on triage level, hour of day and crowding, and one hospital is
  understaffed. Long waits make low-acuity patients leave without being seen.
* **The raw extract is messy** on purpose (see `make_messy`): inconsistent codes, duplicates,
  clock errors, placeholder birth dates and unbilled stays. The SQL staging layer cleans it.

Same seed -> same data, so every number in the README is reproducible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import END_DATE, PROGRAM_HOSPITALS, PROGRAM_START, START_DATE, TRIAGE_LEVELS

# hospital_id, name, city, department, beds, volume share, cost multiplier, readmission logit shift,
# ED staffing factor (>1 = slower), share of self-pay patients
HOSPITALS = [
    ("H01", "Volcán Central", "Guatemala City", "Guatemala", 220, 0.30, 1.15, 0.00, 1.00, 0.25),
    ("H02", "Volcán Mixco", "Mixco", "Guatemala", 140, 0.22, 1.05, 0.10, 1.40, 0.28),
    ("H03", "Volcán Occidente", "Quetzaltenango", "Quetzaltenango", 150, 0.20, 1.00, 0.05, 1.05, 0.32),
    ("H04", "Volcán Sur", "Escuintla", "Escuintla", 100, 0.15, 0.95, 0.10, 1.10, 0.42),
    ("H05", "Volcán Norte", "Cobán", "Alta Verapaz", 80, 0.13, 0.90, 0.30, 1.15, 0.45),
]

# code, description, category, target condition, frequency weight, mean age, sd age, share male,
# mean LOS (days), ICU share, mortality, readmission prob. at reference profile,
# admission type mix (Emergency, Urgent, Elective), procedure cost (GTQ), respiratory seasonality
DIAGNOSES = [
    ("I50.9", "Heart failure", "Cardiology", 1, 7, 72, 11, 0.52, 5.5, 0.10, 0.04, 0.17, (0.85, 0.10, 0.05), 0, 0),
    ("I21.9", "Acute myocardial infarction", "Cardiology", 1, 4, 64, 11, 0.68, 4.5, 0.35, 0.06, 0.12, (0.95, 0.05, 0.00), 45_000, 0),
    ("J18.9", "Pneumonia", "Pulmonology", 1, 9, 62, 22, 0.52, 5.0, 0.12, 0.05, 0.12, (0.85, 0.15, 0.00), 0, 1),
    ("J44.1", "COPD with acute exacerbation", "Pulmonology", 1, 5, 70, 10, 0.55, 4.5, 0.08, 0.03, 0.16, (0.85, 0.15, 0.00), 0, 1),
    ("I63.9", "Ischemic stroke", "Neurology", 0, 4, 68, 12, 0.53, 6.5, 0.20, 0.08, 0.10, (0.95, 0.05, 0.00), 0, 0),
    ("A41.9", "Sepsis", "Infectious disease", 0, 4, 63, 18, 0.50, 8.0, 0.40, 0.15, 0.13, (0.95, 0.05, 0.00), 0, 0),
    ("E11.65", "Type 2 diabetes with hyperglycemia", "Endocrinology", 0, 6, 58, 13, 0.47, 4.0, 0.05, 0.01, 0.11, (0.75, 0.20, 0.05), 0, 0),
    ("N17.9", "Acute kidney failure", "Nephrology", 0, 3, 66, 13, 0.55, 5.0, 0.12, 0.05, 0.12, (0.85, 0.15, 0.00), 0, 0),
    ("N39.0", "Urinary tract infection", "Infectious disease", 0, 6, 55, 22, 0.30, 3.0, 0.02, 0.005, 0.07, (0.70, 0.30, 0.00), 0, 0),
    ("A09", "Infectious gastroenteritis", "Infectious disease", 0, 5, 35, 25, 0.48, 2.0, 0.01, 0.002, 0.04, (0.70, 0.30, 0.00), 0, 0),
    ("K35.80", "Acute appendicitis", "General surgery", 0, 6, 28, 13, 0.55, 2.5, 0.02, 0.001, 0.035, (0.90, 0.10, 0.00), 18_000, 0),
    ("K80.20", "Gallstones (cholecystectomy)", "General surgery", 0, 6, 45, 14, 0.30, 2.0, 0.01, 0.001, 0.035, (0.15, 0.05, 0.80), 16_000, 0),
    ("S72.00", "Hip fracture", "Orthopedics", 0, 3, 79, 9, 0.30, 7.0, 0.05, 0.03, 0.08, (0.90, 0.10, 0.00), 38_000, 0),
    ("M17.11", "Knee osteoarthritis (knee replacement)", "Orthopedics", 0, 3, 66, 9, 0.40, 3.0, 0.01, 0.001, 0.04, (0.00, 0.05, 0.95), 55_000, 0),
    ("O80", "Normal delivery", "Obstetrics", 0, 10, 27, 6, 0.00, 1.5, 0.00, 0.0002, 0.02, (0.00, 1.00, 0.00), 4_000, 0),
    ("O82", "Cesarean delivery", "Obstetrics", 0, 8, 29, 6, 0.00, 2.5, 0.01, 0.0003, 0.03, (0.00, 0.50, 0.50), 12_000, 0),
    ("C18.9", "Colon cancer", "Oncology", 0, 2, 63, 11, 0.50, 6.0, 0.08, 0.02, 0.12, (0.20, 0.10, 0.70), 30_000, 0),
]
DX = pd.DataFrame(DIAGNOSES, columns=[
    "code", "description", "category", "is_target", "freq", "age_mu", "age_sd", "p_male", "los", "icu",
    "mortality", "readmit", "type_mix", "procedure_cost", "seasonal"])
DX_INDEX = {c: i for i, c in enumerate(DX["code"])}
ADMISSION_TYPES = np.array(["Emergency", "Urgent", "Elective"])
PAYERS = np.array(["Private insurance", "Self-pay", "Corporate agreement"])
CHRONIC = {"I50.9", "J44.1", "E11.65", "N17.9", "C18.9"}

WARD_DAY_GTQ = 2_800
ICU_DAY_GTQ = 9_500
ANCILLARY_DAY_GTQ = 650

# Share of ED arrivals by hour of day (two peaks: late morning and evening)
ED_HOURLY = np.array([2.0, 1.6, 1.3, 1.1, 1.0, 1.1, 1.6, 2.8, 4.2, 5.6, 6.4, 6.6,
                      6.2, 5.8, 5.5, 5.4, 5.6, 6.0, 6.3, 6.2, 5.4, 4.3, 3.3, 2.5])
ED_HOURLY = ED_HOURLY / ED_HOURLY.sum()
ED_DOW = np.array([1.18, 1.05, 1.00, 0.98, 1.02, 0.92, 0.85])  # Monday ... Sunday


def _ts(series: pd.Series) -> pd.Series:
    """Format timestamps the way the source system exports them."""
    return series.dt.strftime("%Y-%m-%d %H:%M:%S")


def _day_weights(dates: pd.DatetimeIndex, seasonal: bool) -> np.ndarray:
    years = np.arange(len(dates)) / 365.25
    w = 1 + 0.04 * years  # the network grows ~4% a year
    if seasonal:
        m = dates.month
        w = w * np.where((m >= 5) & (m <= 10), 1.35, np.where((m == 12) | (m == 1), 1.15, 1.0))
    return w / w.sum()


def _admit_hours(types: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    hours = rng.choice(24, size=len(types), p=ED_HOURLY).astype(float)
    elective = types == "Elective"
    hours[elective] = rng.integers(6, 10, elective.sum())
    return hours + rng.random(len(types))


def _sample_admission_type(dx_idx: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    mixes = np.stack(DX["type_mix"].to_numpy())[dx_idx]
    u = rng.random(len(dx_idx))[:, None]
    return ADMISSION_TYPES[(u > np.cumsum(mixes, axis=1)).sum(axis=1).clip(0, 2)]


def _charlson(age: np.ndarray, dx_idx: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    codes = DX["code"].to_numpy()[dx_idx]
    lam = np.clip((age - 35) / 18, 0.05, None) * np.where(np.isin(codes, list(CHRONIC)), 1.4, 1.0)
    lam = np.where(DX["category"].to_numpy()[dx_idx] == "Obstetrics", 0.02, lam)
    score = rng.poisson(lam) + (codes == "C18.9") * 2 + (codes == "E11.65") * 1
    return np.clip(score, 0, 10)


def generate_reference_tables() -> dict[str, pd.DataFrame]:
    hospitals = pd.DataFrame([h[:5] for h in HOSPITALS],
                             columns=["hospital_id", "hospital_name", "city", "department", "beds"])
    hospitals["transitional_care_start"] = np.where(hospitals["hospital_id"].isin(PROGRAM_HOSPITALS), PROGRAM_START, None)
    diagnoses = DX[["code", "description", "category", "is_target"]].rename(
        columns={"code": "icd10_code", "category": "clinical_category", "is_target": "is_program_target"})
    triage = pd.DataFrame([(k, *v) for k, v in TRIAGE_LEVELS.items()],
                          columns=["triage_level", "triage_name", "triage_color", "target_minutes"])
    return {"hospitals": hospitals, "diagnoses": diagnoses, "triage_levels": triage}


def _first_episodes(n_patients: int, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One first admission per patient, plus the patient master records."""
    dates = pd.date_range(START_DATE, END_DATE, freq="D")
    dx_idx = rng.choice(len(DX), size=n_patients, p=(DX["freq"] / DX["freq"].sum()).to_numpy())
    seasonal = DX["seasonal"].to_numpy()[dx_idx] == 1
    day = np.where(seasonal,
                   rng.choice(len(dates), n_patients, p=_day_weights(dates, True)),
                   rng.choice(len(dates), n_patients, p=_day_weights(dates, False)))

    obst = DX["category"].to_numpy()[dx_idx] == "Obstetrics"
    age = rng.normal(DX["age_mu"].to_numpy()[dx_idx], DX["age_sd"].to_numpy()[dx_idx])
    age = np.where(obst, age.clip(16, 45), age.clip(1, 97))
    sex = np.where(rng.random(n_patients) < DX["p_male"].to_numpy()[dx_idx], "M", "F")

    hosp_idx = rng.choice(len(HOSPITALS), size=n_patients, p=[h[5] for h in HOSPITALS])
    self_pay = np.array([h[9] for h in HOSPITALS])[hosp_idx]
    u = rng.random(n_patients)
    payer = np.where(u < self_pay, PAYERS[1], np.where(u < self_pay + (1 - self_pay) * 0.75, PAYERS[0], PAYERS[2]))

    types = _sample_admission_type(dx_idx, rng)
    admit_ts = dates[day] + pd.to_timedelta(_admit_hours(types, rng), unit="h")
    patient_ids = np.array([f"P{i:06d}" for i in range(1, n_patients + 1)])

    birth = admit_ts - pd.to_timedelta(age * 365.25, unit="D")
    home_dept = np.array([h[3] for h in HOSPITALS])[hosp_idx]
    patients = pd.DataFrame({"patient_id": patient_ids, "birth_date": birth.strftime("%Y-%m-%d"), "sex": sex,
                             "home_department": home_dept, "payer_type": payer})

    episodes = pd.DataFrame({
        "patient_id": patient_ids, "hosp_idx": hosp_idx, "dx_idx": dx_idx, "admit_ts": admit_ts,
        "admission_type": types, "age": age, "sex": sex, "charlson": _charlson(age, dx_idx, rng),
        "payer": payer, "frailty": rng.normal(0, 0.35, n_patients), "home_hosp": hosp_idx,
        "is_planned_child": False,
    })
    return episodes, patients


def _simulate_stays(ep: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Length of stay, ICU, discharge disposition, cost, follow-up call and readmission risk."""
    n = len(ep)
    d = DX.iloc[ep["dx_idx"]].reset_index(drop=True)
    age, ch = ep["age"].to_numpy(), ep["charlson"].to_numpy()
    elective = ep["admission_type"].to_numpy() == "Elective"

    los = (d["los"].to_numpy() * np.exp(rng.normal(0, 0.45, n)) * (1 + 0.06 * ch)
           * (1 + np.clip(age - 65, 0, None) * 0.01) * np.where(elective, 0.85, 1.0))
    los = np.clip(los, 0.25, 60)
    icu = rng.random(n) < d["icu"].to_numpy() * (1 + 0.1 * ch)
    icu_days = np.where(icu, np.ceil(los * rng.uniform(0.2, 0.6, n)), 0)

    p_death = np.clip(d["mortality"].to_numpy() * np.exp(0.03 * (age - 65)) * (1 + 0.15 * ch), 0, 0.6)
    died = rng.random(n) < p_death
    u = rng.random(n)
    self_pay = ep["payer"].to_numpy() == "Self-pay"
    ama_p = 0.008 + 0.02 * self_pay
    home_health_p = np.where(age > 70, 0.25, 0.05)
    disposition = np.select(
        [died, u < 0.015, u < 0.015 + ama_p, u < 0.015 + ama_p + home_health_p],
        ["Died", "Transferred", "Left against medical advice", "Home with home health"], "Home")

    cost_mult = np.array([h[6] for h in HOSPITALS])[ep["hosp_idx"]]
    cost = (los * WARD_DAY_GTQ + icu_days * (ICU_DAY_GTQ - WARD_DAY_GTQ)
            + d["procedure_cost"].to_numpy() * np.exp(rng.normal(0, 0.15, n))
            + los * ANCILLARY_DAY_GTQ * np.exp(rng.normal(0, 0.35, n))) * cost_mult

    discharge_ts = ep["admit_ts"] + pd.to_timedelta(los * 24, unit="h")

    # Transitional care program: nurse call for target conditions discharged home
    in_program = (ep["hosp_idx"].map(lambda i: HOSPITALS[i][0]).isin(PROGRAM_HOSPITALS).to_numpy()
                  & (discharge_ts >= pd.Timestamp(PROGRAM_START)).to_numpy()
                  & (d["is_target"].to_numpy() == 1)
                  & np.isin(disposition, ["Home", "Home with home health"]))
    call_status = np.where(~in_program, None,
                           rng.choice(["Completed", "No answer", "Wrong number"], n, p=[0.86, 0.10, 0.04]))

    years = ((ep["admit_ts"] - pd.Timestamp(START_DATE)).dt.days / 365.25).to_numpy()
    base = d["readmit"].to_numpy()
    logit = (np.log(base / (1 - base)) + 0.012 * (age - 65) + 0.15 * ch + 0.25 * self_pay
             + 0.6 * (disposition == "Left against medical advice") - 0.10 * (disposition == "Home with home health")
             + np.array([h[7] for h in HOSPITALS])[ep["hosp_idx"]] + ep["frailty"].to_numpy()
             - 0.06 * years                                   # slow network-wide improvement
             + np.log(0.62) * (call_status == "Completed"))   # program effect
    p_readmit = 1 / (1 + np.exp(-logit))
    p_readmit[np.isin(disposition, ["Died", "Transferred"])] = 0

    out = ep.copy()
    out["discharge_ts"] = discharge_ts
    out["icu_days"] = icu_days.astype(int)
    out["disposition"] = disposition
    out["total_cost_gtq"] = cost.round(2)
    out["call_status"] = call_status
    out["readmit_hit"] = rng.random(n) < p_readmit
    return out


def _children(stays: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Next admissions caused by each stay: unplanned readmissions, planned readmissions, later visits."""
    alive = stays["disposition"].to_numpy() != "Died"
    codes = DX["code"].to_numpy()[stays["dx_idx"]]
    medical = np.where(~DX["category"].isin(["Obstetrics", "General surgery", "Orthopedics"]).to_numpy())[0]
    medical_p = (DX["freq"].iloc[medical] / DX["freq"].iloc[medical].sum()).to_numpy()
    non_obst = np.where(DX["category"].to_numpy() != "Obstetrics")[0]
    non_obst_p = (DX["freq"].iloc[non_obst] / DX["freq"].iloc[non_obst].sum()).to_numpy()
    parts = []

    def child(mask, days, dx_idx, types, planned):
        c = stays.loc[mask].copy()
        if c.empty:
            return
        gap = pd.to_timedelta(days, unit="D")
        c["admit_ts"] = c["discharge_ts"].dt.normalize() + gap + pd.to_timedelta(_admit_hours(types, rng), unit="h")
        c["admit_ts"] = np.maximum(c["admit_ts"], c["discharge_ts"] + pd.Timedelta(hours=2))
        c["dx_idx"] = dx_idx
        c["admission_type"] = types
        c["age"] = c["age"] + days / 365.25
        c["charlson"] = np.clip(c["charlson"] + (rng.random(len(c)) < 0.2), 0, 10)
        stay_elsewhere = rng.random(len(c)) < 0.15
        c["hosp_idx"] = np.where(stay_elsewhere, rng.integers(0, len(HOSPITALS), len(c)), c["home_hosp"])
        c["is_planned_child"] = planned
        parts.append(c)

    # 1) Unplanned readmissions within 30 days
    m = stays["readmit_hit"].to_numpy()
    k = m.sum()
    days = 1 + np.minimum(29, np.floor(rng.gamma(1.4, 9.0, k))).astype(int) - 1
    same = rng.random(k) < 0.55
    dx_new = np.where(same, stays["dx_idx"].to_numpy()[m], rng.choice(medical, k, p=medical_p))
    child(m, days, dx_new, np.where(rng.random(k) < 0.9, "Emergency", "Urgent"), False)

    # 2) Planned readmissions: chemotherapy cycles and scheduled cardiac procedures
    planned = alive & ~m & (((codes == "C18.9") & (rng.random(len(stays)) < 0.6))
                            | ((codes == "I50.9") & (rng.random(len(stays)) < 0.05)))
    k = planned.sum()
    child(planned, rng.integers(10, 28, k), stays["dx_idx"].to_numpy()[planned], np.full(k, "Elective"), True)

    # 3) Unrelated admissions later on (more likely for patients with comorbidities)
    later = alive & ~m & (rng.random(len(stays)) < 0.10 + 0.03 * stays["charlson"].to_numpy())
    k = later.sum()
    dx_new = rng.choice(non_obst, k, p=non_obst_p)
    child(later, rng.integers(31, 500, k), dx_new, _sample_admission_type(dx_new, rng), False)

    return pd.concat(parts, ignore_index=True) if parts else stays.iloc[0:0]


def generate_admissions(n_patients: int, rng: np.random.Generator
                        ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns admissions, patients, follow-up calls and the internal simulation frame (used for ED visits)."""
    episodes, patients = _first_episodes(n_patients, rng)
    end = pd.Timestamp(END_DATE) + pd.Timedelta(days=1)
    stays_all = []
    for _ in range(6):  # each generation creates the next admissions of the same patients
        episodes = episodes[episodes["admit_ts"] < end]
        if episodes.empty:
            break
        stays = _simulate_stays(episodes.reset_index(drop=True), rng)
        stays_all.append(stays)
        episodes = _children(stays, rng)

    adm = pd.concat(stays_all, ignore_index=True)
    adm = adm[adm["discharge_ts"] < end]  # the extract only contains completed stays
    adm = adm.sort_values("admit_ts").reset_index(drop=True)
    adm["admission_id"] = [f"A{i:07d}" for i in range(1, len(adm) + 1)]
    adm["hospital_id"] = [HOSPITALS[i][0] for i in adm["hosp_idx"]]
    adm["icd10_code"] = DX["code"].to_numpy()[adm["dx_idx"]]

    admissions = pd.DataFrame({
        "admission_id": adm["admission_id"], "patient_id": adm["patient_id"], "hospital_id": adm["hospital_id"],
        "admit_ts": _ts(adm["admit_ts"]), "discharge_ts": _ts(adm["discharge_ts"]),
        "admission_type": adm["admission_type"], "primary_icd10": adm["icd10_code"],
        "charlson_index": adm["charlson"].astype(int), "icu_days": adm["icu_days"],
        "discharge_disposition": adm["disposition"], "total_cost_gtq": adm["total_cost_gtq"],
    })

    calls = adm[adm["call_status"].notna()]
    call_ts = calls["discharge_ts"] + pd.to_timedelta(rng.uniform(20, 72, len(calls)), unit="h")
    followup_calls = pd.DataFrame({
        "call_id": [f"C{i:06d}" for i in range(1, len(calls) + 1)], "admission_id": calls["admission_id"].to_numpy(),
        "call_ts": _ts(call_ts).to_numpy(), "call_status": calls["call_status"].to_numpy(),
    })
    return admissions, patients, followup_calls, adm


def generate_ed_visits(adm: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """ED visits: one per emergency admission (admitted via ED) plus visits that end in discharge or LWBS."""
    dates = pd.date_range(START_DATE, END_DATE, freq="D")
    n_days, n_h = len(dates), len(HOSPITALS)

    # Visits that do not end in an admission
    growth = 1 + 0.04 * np.arange(n_days) / 365.25
    rainy = np.where((dates.month >= 5) & (dates.month <= 10), 1.08, 1.0)
    lam = (np.array([h[4] for h in HOSPITALS])[:, None] * 0.11) * (ED_DOW[dates.dayofweek] * growth * rainy)[None, :]
    counts = rng.poisson(lam)
    h_idx = np.repeat(np.repeat(np.arange(n_h), n_days), counts.ravel())
    d_idx = np.repeat(np.tile(np.arange(n_days), n_h), counts.ravel())
    n = len(h_idx)
    arrival = dates[d_idx] + pd.to_timedelta(rng.choice(24, n, p=ED_HOURLY) + rng.random(n), unit="h")
    level = rng.choice([1, 2, 3, 4, 5], n, p=[0.002, 0.04, 0.33, 0.45, 0.178])
    walk_in = pd.DataFrame({"hosp_idx": h_idx, "arrival": arrival, "triage_level": level, "admission_id": None})

    # Visits that became an emergency admission
    em = adm[adm["admission_type"] == "Emergency"]
    board_h = rng.uniform(2, 10, len(em))
    admitted = pd.DataFrame({
        "hosp_idx": em["hosp_idx"].to_numpy(),
        "arrival": (em["admit_ts"] - pd.to_timedelta(board_h, unit="h")).to_numpy(),
        "triage_level": rng.choice([1, 2, 3, 4], len(em), p=[0.08, 0.35, 0.50, 0.07]),
        "admission_id": em["admission_id"].to_numpy(),
    })
    admitted["admit_ts"] = em["admit_ts"].to_numpy()

    v = pd.concat([walk_in, admitted], ignore_index=True)
    v = v[(v["arrival"] >= dates[0]) & (v["arrival"] < dates[-1] + pd.Timedelta(days=1))].reset_index(drop=True)
    n = len(v)

    # Crowding: arrivals in the same hospital and clock hour vs. that hospital's typical hour
    hour_key = v["arrival"].dt.floor("h")
    in_hour = v.groupby([v["hosp_idx"], hour_key])["arrival"].transform("size").to_numpy()
    typical = v.groupby("hosp_idx")["arrival"].transform("size").to_numpy() / (n_days * 24)
    hour = v["arrival"].dt.hour.to_numpy()
    night = np.where((hour >= 23) | (hour < 7), 1.2, 1.0)  # fewer doctors on the night shift
    crowd = (in_hour / typical) ** 0.55 * night * np.array([h[8] for h in HOSPITALS])[v["hosp_idx"]]

    base = np.array([0, 2.5, 9, 34, 62, 80])[v["triage_level"]]
    wait = np.clip(base * crowd * np.exp(rng.normal(0, 0.45, n)), 0.5, 900)
    level = v["triage_level"].to_numpy()
    wait = np.where(level == 1, np.minimum(wait, rng.uniform(0.5, 8, n)), wait)
    to_triage = np.where(level == 1, rng.uniform(0, 1, n), rng.uniform(2, 20, n))
    to_triage = np.minimum(to_triage, wait * 0.8)

    p_lwbs = np.where(level >= 3, 0.45 / (1 + np.exp(-(wait - 180) / 35)), 0)
    lwbs = (rng.random(n) < p_lwbs) & v["admission_id"].isna().to_numpy()

    treat = np.exp(rng.normal(0, 0.4, n)) * np.array([0, 240, 220, 170, 90, 60])[level]
    arrival = v["arrival"]
    triage_ts = arrival + pd.to_timedelta(to_triage, unit="m")
    provider_ts = arrival + pd.to_timedelta(wait, unit="m")
    departure = np.where(lwbs, triage_ts + pd.to_timedelta(wait * rng.uniform(0.5, 1.0, n), unit="m"),
                         provider_ts + pd.to_timedelta(treat, unit="m"))
    departure = pd.Series(pd.to_datetime(departure))
    is_adm = v["admission_id"].notna().to_numpy()
    departure = departure.where(~is_adm, pd.to_datetime(v["admit_ts"]))
    provider_ts = provider_ts.where(~lwbs, pd.NaT)
    # Admitted patients must see a provider before admission
    provider_ts = provider_ts.where(~is_adm, np.minimum(provider_ts, departure - pd.Timedelta(minutes=30)))

    v = v.assign(arrival=arrival, triage_ts=triage_ts, provider_ts=provider_ts, departure=departure)
    return v.sort_values("arrival").reset_index(drop=True)


def build_ed_table(v: pd.DataFrame) -> pd.DataFrame:
    disp = np.where(v["admission_id"].notna(), "Admitted",
                    np.where(v["provider_ts"].isna(), "Left without being seen", "Discharged"))
    return pd.DataFrame({
        "visit_id": [f"E{i:07d}" for i in range(1, len(v) + 1)],
        "hospital_id": [HOSPITALS[i][0] for i in v["hosp_idx"]],
        "arrival_ts": _ts(v["arrival"]), "triage_ts": _ts(v["triage_ts"]),
        "provider_ts": _ts(v["provider_ts"]), "departure_ts": _ts(v["departure"]),
        "triage_level": v["triage_level"].astype(int), "ed_disposition": disp,
        "admission_id": v["admission_id"],
    })


def make_messy(tables: dict[str, pd.DataFrame], rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    """Add the data quality problems a real hospital extract has. The SQL staging layer fixes each one."""
    t = {k: v.copy() for k, v in tables.items()}

    # Patients: sex coded four different ways, and a legacy placeholder birth date
    p = t["patients"]
    variants = {"M": ["M", "m", "Male", "MASCULINO"], "F": ["F", "f", "Female", "FEMENINO"]}
    p["sex"] = [variants[s][rng.choice(4, p=[0.7, 0.1, 0.1, 0.1])] for s in p["sex"]]
    p.loc[rng.random(len(p)) < 0.003, "birth_date"] = "1900-01-01"

    # Admissions: ICD-10 codes typed without the dot / in lower case, unbilled stays, duplicate rows,
    # and a few records where the discharge was keyed before the admission
    a = t["admissions"]
    r = rng.random(len(a))
    a.loc[r < 0.08, "primary_icd10"] = a.loc[r < 0.08, "primary_icd10"].str.replace(".", "", regex=False)
    a.loc[(r >= 0.08) & (r < 0.12), "primary_icd10"] = a.loc[(r >= 0.08) & (r < 0.12), "primary_icd10"].str.lower() + " "
    a.loc[rng.random(len(a)) < 0.012, "total_cost_gtq"] = np.nan
    bad = rng.random(len(a)) < 0.001
    a.loc[bad, ["admit_ts", "discharge_ts"]] = a.loc[bad, ["discharge_ts", "admit_ts"]].to_numpy()
    a["admit_ts"] = np.where(rng.random(len(a)) < 0.2, a["admit_ts"].str.replace(" ", "T"), a["admit_ts"])
    dups = a.sample(frac=0.004, random_state=int(rng.integers(1e9)))
    t["admissions"] = pd.concat([a, dups]).sample(frac=1, random_state=int(rng.integers(1e9))).reset_index(drop=True)

    # ED: clock errors (provider time before arrival) and mixed timestamp formats
    e = t["ed_visits"]
    clock = (rng.random(len(e)) < 0.003) & e["provider_ts"].notna()
    e.loc[clock, "provider_ts"] = (pd.to_datetime(e.loc[clock, "arrival_ts"]) - pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d %H:%M:%S")
    e["arrival_ts"] = np.where(rng.random(len(e)) < 0.2, e["arrival_ts"].str.replace(" ", "T"), e["arrival_ts"])
    return t


def generate_all(n_patients: int = 24_000, seed: int = 42, messy: bool = True) -> dict[str, pd.DataFrame]:
    """Generate every source table. Same seed -> same data."""
    rng = np.random.default_rng(seed)
    tables = generate_reference_tables()
    admissions, patients, calls, adm_sim = generate_admissions(n_patients, rng)
    ed_sim = generate_ed_visits(adm_sim, rng)
    tables.update({"patients": patients, "admissions": admissions, "followup_calls": calls,
                   "ed_visits": build_ed_table(ed_sim)})
    return make_messy(tables, rng) if messy else tables
