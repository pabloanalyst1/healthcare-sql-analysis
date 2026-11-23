-- =====================================================================================
-- 02 DIMENSIONS: hospitals, diagnoses, patients, triage levels and a calendar.
-- =====================================================================================

DROP TABLE IF EXISTS dim_hospital;
CREATE TABLE dim_hospital AS
SELECT
    hospital_id,
    hospital_name,
    city,
    department,
    beds,
    transitional_care_start,
    CASE WHEN transitional_care_start IS NOT NULL THEN 1 ELSE 0 END    AS has_transitional_care,
    CASE WHEN transitional_care_start IS NOT NULL
         THEN 'Program hospitals' ELSE 'Comparison hospitals' END       AS program_group
FROM ref_hospitals;


DROP TABLE IF EXISTS dim_diagnosis;
CREATE TABLE dim_diagnosis AS
SELECT
    icd10_code,
    description                                                         AS diagnosis,
    clinical_category,
    is_program_target
FROM ref_diagnoses;


DROP TABLE IF EXISTS dim_patient;
CREATE TABLE dim_patient AS
SELECT
    p.patient_id,
    p.sex,
    p.birth_date,
    p.home_department,
    p.payer_type,
    COUNT(a.admission_id)                                               AS lifetime_admissions,
    MIN(DATE(a.admit_ts))                                               AS first_admission_date
FROM stg_patients p
LEFT JOIN stg_admissions a ON a.patient_id = p.patient_id
GROUP BY p.patient_id;


DROP TABLE IF EXISTS dim_triage_level;
CREATE TABLE dim_triage_level AS
SELECT triage_level, triage_name, triage_color, target_minutes
FROM ref_triage_levels;


-- Calendar built with a recursive CTE (one row per day of the study period)
DROP TABLE IF EXISTS dim_date;
CREATE TABLE dim_date AS
WITH RECURSIVE days(d) AS (
    SELECT DATE(study_start) FROM ref_parameters
    UNION ALL
    SELECT DATE(d, '+1 day') FROM days WHERE d < (SELECT study_end FROM ref_parameters)
)
SELECT
    d                                                                   AS date,
    CAST(STRFTIME('%Y', d) AS INTEGER)                                  AS year,
    CAST(STRFTIME('%m', d) AS INTEGER)                                  AS month,
    DATE(d, 'start of month')                                           AS month_start,
    'Q' || ((CAST(STRFTIME('%m', d) AS INTEGER) + 2) / 3)               AS quarter,
    CAST(STRFTIME('%w', d) AS INTEGER)                                  AS day_of_week_num,  -- 0 = Sunday
    CASE STRFTIME('%w', d)
        WHEN '0' THEN 'Sun' WHEN '1' THEN 'Mon' WHEN '2' THEN 'Tue' WHEN '3' THEN 'Wed'
        WHEN '4' THEN 'Thu' WHEN '5' THEN 'Fri' ELSE 'Sat'
    END                                                                 AS day_of_week,
    CASE WHEN STRFTIME('%w', d) IN ('0', '6') THEN 1 ELSE 0 END         AS is_weekend,
    -- Guatemala's rainy season (May-October) brings the respiratory peak
    CASE WHEN CAST(STRFTIME('%m', d) AS INTEGER) BETWEEN 5 AND 10 THEN 1 ELSE 0 END AS is_rainy_season
FROM days;

CREATE UNIQUE INDEX ux_dim_date ON dim_date (date);
