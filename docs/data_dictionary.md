# Data dictionary

The warehouse (`data/warehouse.db`) is rebuilt by `python run_pipeline.py`. Layers: `raw_*` (as received), `ref_*` (reference data and business rules), `stg_*` (cleaned), `dim_*` / `fct_*` (star schema) and `mart_*` (exported to `exports/`).

## `fct_admissions`

One row per hospital stay (admission). Grain: admission_id.

| Column | Type | Description |
|---|---|---|
| `admission_id` | TEXT |  |
| `patient_id` | TEXT |  |
| `hospital_id` | TEXT |  |
| `admit_ts` | TEXT |  |
| `discharge_ts` | TEXT |  |
| `admit_date` | TEXT |  |
| `discharge_date` | TEXT |  |
| `discharge_month` | TEXT |  |
| `admission_type` | TEXT |  |
| `is_planned` | TEXT | 1 for elective admissions; planned stays never count as readmissions |
| `icd10_code` | TEXT |  |
| `diagnosis` | TEXT |  |
| `clinical_category` | TEXT |  |
| `is_program_target` | INT |  |
| `sex` | TEXT |  |
| `payer_type` | TEXT |  |
| `age_at_admission` | INT |  |
| `age_band` | TEXT |  |
| `charlson_index` | INT | Charlson comorbidity index (0 = no comorbidities) |
| `charlson_band` | TEXT |  |
| `icu_days` | INT |  |
| `had_icu` | TEXT |  |
| `los_days` | TEXT | Length of stay in days |
| `discharge_disposition` | TEXT |  |
| `died_in_hospital` | TEXT |  |
| `total_cost_gtq` | REAL | Cost of the stay in Guatemalan quetzales; NULL if not billed yet |
| `is_billed` | TEXT |  |
| `patient_admission_seq` | TEXT |  |
| `days_since_prev_discharge` | TEXT |  |
| `is_index_stay` | TEXT | 1 if the stay can start a 30-day readmission window (discharged alive, not transferred, not AMA, 30 days of follow-up left) |
| `is_readmitted_30d` | TEXT | 1 if an index stay was followed by an unplanned admission to any network hospital within 30 days |
| `readmission_id` | TEXT | The first unplanned readmission after this index stay |
| `days_to_readmission` | TEXT | Days from index discharge to readmission |
| `is_readmission` | TEXT | 1 if this stay is an unplanned readmission within 30 days of a qualifying index stay |
| `readmission_of` | TEXT | The index stay this readmission is attributed to (most recent one) |
| `program_group` | TEXT | Program hospitals (H01, H03) or Comparison hospitals |
| `program_period` | TEXT | Pre / Post the program start (2025-01-01), by discharge date |
| `is_program_eligible` | TEXT | 1 if the stay qualified for a follow-up call (program hospital, after start, target condition, discharged home) |
| `call_status` | TEXT | Outcome of the follow-up call: Completed, No answer, Wrong number |

## `fct_ed_visits`

One row per emergency department visit. Grain: visit_id.

| Column | Type | Description |
|---|---|---|
| `visit_id` | TEXT |  |
| `hospital_id` | TEXT |  |
| `arrival_ts` | TEXT |  |
| `arrival_date` | TEXT |  |
| `arrival_month` | TEXT |  |
| `arrival_hour` | INT |  |
| `day_of_week` | TEXT |  |
| `day_of_week_num` | INT |  |
| `triage_level` | INT |  |
| `triage_name` | TEXT |  |
| `target_minutes` | INT | Maximum wait to first provider contact for the triage level |
| `ed_disposition` | TEXT |  |
| `is_lwbs` | TEXT | 1 if the patient left without being seen |
| `is_admitted` | TEXT |  |
| `admission_id` | TEXT |  |
| `is_clock_error` | TEXT | 1 if the provider time was recorded before arrival |
| `wait_minutes` | TEXT | Door-to-provider time in minutes; NULL if the patient left without being seen or the clocks were wrong |
| `met_triage_target` | TEXT | 1 if seen within the triage level target |
| `ed_length_of_stay_minutes` | TEXT | Arrival to departure |

## `dim_hospital`

The five hospitals of the network and whether they run the transitional care program.

| Column | Type | Description |
|---|---|---|
| `hospital_id` | TEXT |  |
| `hospital_name` | TEXT |  |
| `city` | TEXT |  |
| `department` | TEXT |  |
| `beds` | INT |  |
| `transitional_care_start` | TEXT | Date the hospital started the follow-up call program (NULL = no program) |
| `has_transitional_care` | TEXT |  |
| `program_group` | TEXT | Program hospitals (H01, H03) or Comparison hospitals |

## `dim_diagnosis`

ICD-10 primary diagnoses, clinical category and program target flag.

| Column | Type | Description |
|---|---|---|
| `icd10_code` | TEXT |  |
| `diagnosis` | TEXT |  |
| `clinical_category` | TEXT |  |
| `is_program_target` | INT |  |

## `dim_patient`

Patient master data (cleaned).

| Column | Type | Description |
|---|---|---|
| `patient_id` | TEXT |  |
| `sex` | TEXT |  |
| `birth_date` | TEXT |  |
| `home_department` | TEXT |  |
| `payer_type` | TEXT |  |
| `lifetime_admissions` | TEXT |  |
| `first_admission_date` | TEXT |  |

## `dim_triage_level`

Manchester Triage System levels and their maximum wait targets.

| Column | Type | Description |
|---|---|---|
| `triage_level` | INT |  |
| `triage_name` | TEXT |  |
| `triage_color` | TEXT |  |
| `target_minutes` | INT | Maximum wait to first provider contact for the triage level |

## `dim_date`

Calendar, one row per day of the study period.

| Column | Type | Description |
|---|---|---|
| `date` | TEXT |  |
| `year` | INT |  |
| `month` | INT |  |
| `month_start` | TEXT |  |
| `quarter` | TEXT |  |
| `day_of_week_num` | INT |  |
| `day_of_week` | TEXT |  |
| `is_weekend` | TEXT |  |
| `is_rainy_season` | TEXT |  |

## Marts

| Table | Grain / content |
|---|---|
| `mart_readmissions_monthly` | Month × hospital × clinical category: index stays and readmissions |
| `mart_readmissions_by_diagnosis` | Diagnosis: readmission rate, vs network, days to readmission |
| `mart_hospital_readmissions_risk_adjusted` | Hospital: observed, expected, O/E ratio, risk-standardized rate |
| `mart_program_evaluation` | Program group × period × condition group: the 2×2 difference-in-differences table |
| `mart_program_quarterly` | Quarter × program group: readmission rate for target conditions |
| `mart_followup_call_outcomes` | Call outcome: readmission rate among eligible stays |
| `mart_ed_hourly` | Hospital × weekday × hour: visits, total wait, LWBS (additive) |
| `mart_ed_monthly` | Hospital × month: visits, median / p90 wait, LWBS, triage compliance |
| `mart_ed_triage_compliance` | Hospital × triage level: compliance, median / p90 wait |
| `mart_ed_lwbs_by_wait_band` | Wait band: LWBS rate |
| `mart_cost_by_diagnosis` | Diagnosis: total / average / median / p90 cost, LOS, ICU share, mortality |
| `mart_cost_monthly` | Month × hospital × category × payer: cost, LOS, ICU days, readmission cost (additive) |
| `mart_readmission_cost` | Index diagnosis: number and cost of the readmissions it caused |
| `mart_kpi_summary` | Headline KPIs, last 12 months vs previous 12 |
| `mart_admissions_detail` | One row per admission with every attribute, for the dashboard and the R report |
