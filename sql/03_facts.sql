-- =====================================================================================
-- 03 FACTS: one row per admission and one row per ED visit, with the business logic.
--
-- 30-day readmission definition (simplified CMS all-cause measure):
--   * Index stay: patient discharged alive, not transferred to another acute facility and not
--     against medical advice, with at least 30 days of follow-up left inside the extract.
--   * Readmission: an UNPLANNED (emergency or urgent) admission to ANY hospital of the network
--     within 30 days of the index discharge. Elective admissions (chemotherapy cycles, scheduled
--     procedures) are planned and never count as readmissions.
-- =====================================================================================

-- Admissions enriched with patient, diagnosis and sequence information -------------------
DROP TABLE IF EXISTS int_admissions;
CREATE TABLE int_admissions AS
SELECT
    a.admission_id,
    a.patient_id,
    a.hospital_id,
    a.admit_ts,
    a.discharge_ts,
    DATE(a.admit_ts)                                                    AS admit_date,
    DATE(a.discharge_ts)                                                AS discharge_date,
    a.admission_type,
    CASE WHEN a.admission_type = 'Elective' THEN 1 ELSE 0 END           AS is_planned,
    a.icd10_code,
    d.diagnosis,
    d.clinical_category,
    d.is_program_target,
    p.sex,
    p.payer_type,
    CAST((JULIANDAY(a.admit_ts) - JULIANDAY(p.birth_date)) / 365.25 AS INTEGER) AS age_at_admission,
    a.charlson_index,
    a.icu_days,
    ROUND(JULIANDAY(a.discharge_ts) - JULIANDAY(a.admit_ts), 2)         AS los_days,
    a.discharge_disposition,
    a.total_cost_gtq,
    ROW_NUMBER() OVER w                                                 AS patient_admission_seq,
    ROUND(JULIANDAY(a.admit_ts) - JULIANDAY(LAG(a.discharge_ts) OVER w), 1) AS days_since_prev_discharge,
    CASE
        WHEN a.discharge_disposition IN ('Died', 'Transferred', 'Left against medical advice') THEN 0
        WHEN DATE(a.discharge_ts) > prm.last_index_discharge THEN 0      -- incomplete follow-up
        ELSE 1
    END                                                                 AS is_index_stay
FROM stg_admissions a
JOIN stg_patients p   ON p.patient_id = a.patient_id
JOIN dim_diagnosis d  ON d.icd10_code = a.icd10_code
CROSS JOIN ref_parameters prm
WINDOW w AS (PARTITION BY a.patient_id ORDER BY a.admit_ts);

CREATE UNIQUE INDEX ux_int_admissions ON int_admissions (admission_id);
CREATE INDEX ix_int_admissions_patient ON int_admissions (patient_id, admit_ts);


-- Every (qualifying index stay -> unplanned readmission within 30 days) pair -------------------------
DROP TABLE IF EXISTS int_readmission_pairs;
CREATE TABLE int_readmission_pairs AS
WITH pairs AS (
    SELECT
        i.admission_id                                                  AS index_admission_id,
        r.admission_id                                                  AS readmission_id,
        ROUND(JULIANDAY(r.admit_ts) - JULIANDAY(i.discharge_ts), 2)     AS days_to_readmission,
        -- first readmission after each index stay
        ROW_NUMBER() OVER (PARTITION BY i.admission_id ORDER BY r.admit_ts) AS nth_after_index,
        -- most recent index stay before each readmission (a planned stay in between can also be an index)
        ROW_NUMBER() OVER (PARTITION BY r.admission_id ORDER BY i.discharge_ts DESC) AS nth_before_readmission
    FROM int_admissions i
    JOIN int_admissions r
      ON r.patient_id = i.patient_id
     AND r.admit_ts > i.discharge_ts
     AND JULIANDAY(r.admit_ts) - JULIANDAY(i.discharge_ts)
         <= (SELECT readmission_window_days FROM ref_parameters)
     AND r.is_planned = 0
    WHERE i.is_index_stay = 1
)
SELECT * FROM pairs;

CREATE INDEX ix_pairs_index ON int_readmission_pairs (index_admission_id);
CREATE INDEX ix_pairs_readm ON int_readmission_pairs (readmission_id);


-- Fact: admissions --------------------------------------------------------------------
DROP TABLE IF EXISTS fct_admissions;
CREATE TABLE fct_admissions AS
WITH flags AS (
    SELECT
        a.*,
        h.program_group,
        CASE WHEN a.discharge_date >= prm.program_start THEN 'Post' ELSE 'Pre' END AS program_period
    FROM int_admissions a
    CROSS JOIN ref_parameters prm
    JOIN dim_hospital h ON h.hospital_id = a.hospital_id
)
SELECT
    f.admission_id,
    f.patient_id,
    f.hospital_id,
    f.admit_ts,
    f.discharge_ts,
    f.admit_date,
    f.discharge_date,
    DATE(f.discharge_date, 'start of month')                            AS discharge_month,
    f.admission_type,
    f.is_planned,
    f.icd10_code,
    f.diagnosis,
    f.clinical_category,
    f.is_program_target,
    f.sex,
    f.payer_type,
    f.age_at_admission,
    CASE
        WHEN f.age_at_admission IS NULL THEN 'Unknown'
        WHEN f.age_at_admission < 18 THEN '0-17'
        WHEN f.age_at_admission < 45 THEN '18-44'
        WHEN f.age_at_admission < 65 THEN '45-64'
        WHEN f.age_at_admission < 80 THEN '65-79'
        ELSE '80+'
    END                                                                 AS age_band,
    f.charlson_index,
    CASE
        WHEN f.charlson_index = 0 THEN '0'
        WHEN f.charlson_index <= 2 THEN '1-2'
        WHEN f.charlson_index <= 4 THEN '3-4'
        ELSE '5+'
    END                                                                 AS charlson_band,
    f.icu_days,
    CASE WHEN f.icu_days > 0 THEN 1 ELSE 0 END                          AS had_icu,
    f.los_days,
    f.discharge_disposition,
    CASE WHEN f.discharge_disposition = 'Died' THEN 1 ELSE 0 END        AS died_in_hospital,
    f.total_cost_gtq,
    CASE WHEN f.total_cost_gtq IS NULL THEN 0 ELSE 1 END                AS is_billed,
    f.patient_admission_seq,
    f.days_since_prev_discharge,
    f.is_index_stay,
    CASE WHEN f.is_index_stay = 1 AND nxt.readmission_id IS NOT NULL THEN 1 ELSE 0 END AS is_readmitted_30d,
    CASE WHEN f.is_index_stay = 1 THEN nxt.readmission_id END           AS readmission_id,
    CASE WHEN f.is_index_stay = 1 THEN nxt.days_to_readmission END      AS days_to_readmission,
    CASE WHEN prv.index_admission_id IS NOT NULL THEN 1 ELSE 0 END      AS is_readmission,
    prv.index_admission_id                                              AS readmission_of,
    f.program_group,
    f.program_period,
    CASE WHEN f.program_group = 'Program hospitals' AND f.program_period = 'Post'
          AND f.is_program_target = 1 AND f.discharge_disposition IN ('Home', 'Home with home health')
         THEN 1 ELSE 0 END                                              AS is_program_eligible,
    c.call_status
FROM flags f
LEFT JOIN int_readmission_pairs nxt
       ON nxt.index_admission_id = f.admission_id AND nxt.nth_after_index = 1
LEFT JOIN int_readmission_pairs prv
       ON prv.readmission_id = f.admission_id AND prv.nth_before_readmission = 1
LEFT JOIN stg_followup_calls c ON c.admission_id = f.admission_id;

CREATE UNIQUE INDEX ux_fct_admissions ON fct_admissions (admission_id);
CREATE INDEX ix_fct_admissions_hosp ON fct_admissions (hospital_id, discharge_month);


-- Fact: ED visits -----------------------------------------------------------------------
DROP TABLE IF EXISTS fct_ed_visits;
CREATE TABLE fct_ed_visits AS
SELECT
    v.visit_id,
    v.hospital_id,
    v.arrival_ts,
    DATE(v.arrival_ts)                                                  AS arrival_date,
    DATE(v.arrival_ts, 'start of month')                                AS arrival_month,
    CAST(STRFTIME('%H', v.arrival_ts) AS INTEGER)                       AS arrival_hour,
    dd.day_of_week,
    dd.day_of_week_num,
    v.triage_level,
    t.triage_name,
    t.target_minutes,
    v.ed_disposition,
    CASE WHEN v.ed_disposition = 'Left without being seen' THEN 1 ELSE 0 END AS is_lwbs,
    CASE WHEN v.ed_disposition = 'Admitted' THEN 1 ELSE 0 END           AS is_admitted,
    v.admission_id,
    v.is_clock_error,
    -- door-to-provider time, the main ED waiting-time KPI
    CASE WHEN v.provider_ts IS NOT NULL AND v.is_clock_error = 0
         THEN ROUND((JULIANDAY(v.provider_ts) - JULIANDAY(v.arrival_ts)) * 1440, 1)
    END                                                                 AS wait_minutes,
    CASE WHEN v.provider_ts IS NOT NULL AND v.is_clock_error = 0
         THEN CASE WHEN (JULIANDAY(v.provider_ts) - JULIANDAY(v.arrival_ts)) * 1440 <= t.target_minutes
                   THEN 1 ELSE 0 END
    END                                                                 AS met_triage_target,
    ROUND((JULIANDAY(v.departure_ts) - JULIANDAY(v.arrival_ts)) * 1440, 1) AS ed_length_of_stay_minutes
FROM stg_ed_visits v
JOIN dim_triage_level t ON t.triage_level = v.triage_level
JOIN dim_date dd        ON dd.date = DATE(v.arrival_ts);

CREATE UNIQUE INDEX ux_fct_ed_visits ON fct_ed_visits (visit_id);
CREATE INDEX ix_fct_ed_visits_hosp ON fct_ed_visits (hospital_id, arrival_month);
