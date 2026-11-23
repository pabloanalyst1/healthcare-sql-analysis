-- =====================================================================================
-- 01 STAGING: clean the raw extract. One staging table per source table.
-- Fixes: mixed timestamp formats, ICD-10 codes without the dot or in lower case,
-- sex coded four ways, legacy placeholder birth dates, duplicate rows, impossible stays
-- and ED clock errors. Nothing is silently dropped: rejected rows go to stg_rejected_*.
-- =====================================================================================

-- Patients ---------------------------------------------------------------------------
DROP TABLE IF EXISTS stg_patients;
CREATE TABLE stg_patients AS
SELECT
    TRIM(patient_id)                                                    AS patient_id,
    CASE
        WHEN UPPER(TRIM(sex)) IN ('M', 'MALE', 'MASCULINO') THEN 'M'
        WHEN UPPER(TRIM(sex)) IN ('F', 'FEMALE', 'FEMENINO') THEN 'F'
    END                                                                 AS sex,
    -- 1900-01-01 is the legacy system's default when the birth date was not captured
    CASE
        WHEN birth_date = '1900-01-01' THEN NULL
        WHEN birth_date > (SELECT study_end FROM ref_parameters) THEN NULL
        ELSE DATE(birth_date)
    END                                                                 AS birth_date,
    TRIM(home_department)                                               AS home_department,
    TRIM(payer_type)                                                    AS payer_type
FROM raw_patients;

CREATE UNIQUE INDEX ux_stg_patients ON stg_patients (patient_id);


-- Admissions -------------------------------------------------------------------------
DROP TABLE IF EXISTS stg_admissions_cleaned;
CREATE TABLE stg_admissions_cleaned AS
WITH typed AS (
    SELECT
        TRIM(admission_id)                                              AS admission_id,
        TRIM(patient_id)                                                AS patient_id,
        TRIM(hospital_id)                                               AS hospital_id,
        DATETIME(REPLACE(TRIM(admit_ts), 'T', ' '))                     AS admit_ts,
        DATETIME(REPLACE(TRIM(discharge_ts), 'T', ' '))                 AS discharge_ts,
        TRIM(admission_type)                                            AS admission_type,
        UPPER(REPLACE(TRIM(primary_icd10), '.', ''))                    AS icd_compact,
        CAST(charlson_index AS INTEGER)                                 AS charlson_index,
        CAST(icu_days AS INTEGER)                                       AS icu_days,
        TRIM(discharge_disposition)                                     AS discharge_disposition,
        CAST(total_cost_gtq AS REAL)                                    AS total_cost_gtq,
        -- the extract repeats some rows; keep one copy per admission
        ROW_NUMBER() OVER (PARTITION BY TRIM(admission_id) ORDER BY rowid) AS copy_number
    FROM raw_admissions
)
SELECT
    admission_id, patient_id, hospital_id, admit_ts, discharge_ts, admission_type,
    -- ICD-10 format: letter + 2 digits, then a dot before any further characters (I509 -> I50.9)
    CASE WHEN LENGTH(icd_compact) > 3
         THEN SUBSTR(icd_compact, 1, 3) || '.' || SUBSTR(icd_compact, 4)
         ELSE icd_compact
    END                                                                 AS icd10_code,
    charlson_index, icu_days, discharge_disposition, total_cost_gtq,
    CASE WHEN discharge_ts < admit_ts THEN 'Discharge before admission' END AS reject_reason
FROM typed
WHERE copy_number = 1;

DROP TABLE IF EXISTS stg_rejected_admissions;
CREATE TABLE stg_rejected_admissions AS
SELECT * FROM stg_admissions_cleaned WHERE reject_reason IS NOT NULL;

DROP TABLE IF EXISTS stg_admissions;
CREATE TABLE stg_admissions AS
SELECT
    admission_id, patient_id, hospital_id, admit_ts, discharge_ts, admission_type, icd10_code,
    charlson_index, icu_days, discharge_disposition, total_cost_gtq
FROM stg_admissions_cleaned
WHERE reject_reason IS NULL;

DROP TABLE stg_admissions_cleaned;

CREATE UNIQUE INDEX ux_stg_admissions ON stg_admissions (admission_id);
CREATE INDEX ix_stg_admissions_patient ON stg_admissions (patient_id, admit_ts);


-- Follow-up calls (transitional care program) ----------------------------------------
DROP TABLE IF EXISTS stg_followup_calls;
CREATE TABLE stg_followup_calls AS
SELECT
    TRIM(call_id)                                                       AS call_id,
    TRIM(admission_id)                                                  AS admission_id,
    DATETIME(REPLACE(TRIM(call_ts), 'T', ' '))                          AS call_ts,
    TRIM(call_status)                                                   AS call_status
FROM raw_followup_calls;

CREATE INDEX ix_stg_calls_admission ON stg_followup_calls (admission_id);


-- Emergency department visits --------------------------------------------------------
DROP TABLE IF EXISTS stg_ed_visits;
CREATE TABLE stg_ed_visits AS
WITH typed AS (
    SELECT
        TRIM(visit_id)                                                  AS visit_id,
        TRIM(hospital_id)                                               AS hospital_id,
        DATETIME(REPLACE(TRIM(arrival_ts), 'T', ' '))                   AS arrival_ts,
        DATETIME(REPLACE(TRIM(triage_ts), 'T', ' '))                    AS triage_ts,
        DATETIME(REPLACE(TRIM(provider_ts), 'T', ' '))                  AS provider_ts,
        DATETIME(REPLACE(TRIM(departure_ts), 'T', ' '))                 AS departure_ts,
        CAST(triage_level AS INTEGER)                                   AS triage_level,
        TRIM(ed_disposition)                                            AS ed_disposition,
        NULLIF(TRIM(admission_id), '')                                  AS admission_id
    FROM raw_ed_visits
)
SELECT
    *,
    -- a provider time before arrival is a clock / keying error: keep the visit, drop the wait time
    CASE WHEN provider_ts < arrival_ts THEN 1 ELSE 0 END                AS is_clock_error
FROM typed;

CREATE UNIQUE INDEX ux_stg_ed_visits ON stg_ed_visits (visit_id);
