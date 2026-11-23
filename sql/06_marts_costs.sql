-- =====================================================================================
-- 06 MARTS - COSTS AND LENGTH OF STAY, plus the KPI summary and a BI-ready detail table.
-- Costs are in Guatemalan quetzales (GTQ). Unbilled stays (no cost yet) are excluded
-- from cost metrics but kept in volume and length-of-stay metrics.
-- =====================================================================================

-- Cost per diagnosis -------------------------------------------------------------------
DROP TABLE IF EXISTS mart_cost_by_diagnosis;
CREATE TABLE mart_cost_by_diagnosis AS
WITH ranked AS (
    SELECT
        icd10_code, total_cost_gtq,
        ROW_NUMBER() OVER (PARTITION BY icd10_code ORDER BY total_cost_gtq) AS rn,
        COUNT(*)     OVER (PARTITION BY icd10_code)                         AS n
    FROM fct_admissions
    WHERE is_billed = 1
),
pct AS (
    SELECT icd10_code,
           MIN(CASE WHEN 1.0 * rn / n >= 0.5 THEN total_cost_gtq END)   AS median_cost_gtq,
           MIN(CASE WHEN 1.0 * rn / n >= 0.9 THEN total_cost_gtq END)   AS p90_cost_gtq
    FROM ranked GROUP BY icd10_code
)
SELECT
    f.icd10_code,
    f.diagnosis,
    f.clinical_category,
    COUNT(*)                                                            AS stays,
    SUM(f.is_billed)                                                    AS billed_stays,
    ROUND(SUM(f.total_cost_gtq), 0)                                     AS total_cost_gtq,
    ROUND(SUM(f.total_cost_gtq) / SUM(f.is_billed), 0)                  AS avg_cost_gtq,
    ROUND(p.median_cost_gtq, 0)                                         AS median_cost_gtq,
    ROUND(p.p90_cost_gtq, 0)                                            AS p90_cost_gtq,
    ROUND(SUM(f.total_cost_gtq) / SUM(CASE WHEN f.is_billed = 1 THEN f.los_days END), 0) AS cost_per_day_gtq,
    ROUND(AVG(f.los_days), 2)                                           AS avg_los_days,
    ROUND(AVG(f.had_icu), 4)                                            AS icu_share,
    ROUND(AVG(f.died_in_hospital), 4)                                   AS mortality_rate,
    ROUND(SUM(f.total_cost_gtq) * 1.0 / (SELECT SUM(total_cost_gtq) FROM fct_admissions), 4) AS share_of_total_cost
FROM fct_admissions f
JOIN pct p ON p.icd10_code = f.icd10_code
GROUP BY f.icd10_code, f.diagnosis, f.clinical_category, p.median_cost_gtq, p.p90_cost_gtq
ORDER BY total_cost_gtq DESC;


-- Monthly cost and activity (additive) ------------------------------------------------
DROP TABLE IF EXISTS mart_cost_monthly;
CREATE TABLE mart_cost_monthly AS
SELECT
    f.discharge_month                                                   AS month_start,
    f.hospital_id,
    h.hospital_name,
    f.clinical_category,
    f.payer_type,
    COUNT(*)                                                            AS stays,
    SUM(f.is_billed)                                                    AS billed_stays,
    ROUND(SUM(f.total_cost_gtq), 2)                                     AS total_cost_gtq,
    ROUND(SUM(f.los_days), 2)                                           AS total_los_days,
    SUM(f.icu_days)                                                     AS total_icu_days,
    SUM(f.died_in_hospital)                                             AS deaths,
    SUM(f.is_readmission)                                               AS readmission_stays,
    ROUND(SUM(CASE WHEN f.is_readmission = 1 THEN f.total_cost_gtq END), 2) AS readmission_cost_gtq
FROM fct_admissions f
JOIN dim_hospital h ON h.hospital_id = f.hospital_id
GROUP BY 1, 2, 3, 4, 5;


-- Cost of readmissions, attributed to the diagnosis of the index stay -----------------
DROP TABLE IF EXISTS mart_readmission_cost;
CREATE TABLE mart_readmission_cost AS
SELECT
    i.icd10_code                                                        AS index_icd10_code,
    i.diagnosis                                                         AS index_diagnosis,
    COUNT(*)                                                            AS readmission_stays,
    ROUND(SUM(r.total_cost_gtq), 0)                                     AS readmission_cost_gtq,
    ROUND(AVG(r.total_cost_gtq), 0)                                     AS avg_readmission_cost_gtq,
    ROUND(AVG(r.los_days), 2)                                           AS avg_readmission_los_days
FROM fct_admissions r
JOIN fct_admissions i ON i.admission_id = r.readmission_of
WHERE r.is_readmission = 1
GROUP BY 1, 2
ORDER BY readmission_cost_gtq DESC;


-- Headline KPIs: last 12 months vs the previous 12 months ------------------------------
DROP TABLE IF EXISTS mart_kpi_summary;
CREATE TABLE mart_kpi_summary AS
WITH periods AS (
    SELECT DATE(study_end, '-12 months', '+1 day') AS cur_start,
           study_end                               AS cur_end,
           DATE(study_end, '-24 months', '+1 day') AS prev_start,
           DATE(study_end, '-12 months')           AS prev_end
    FROM ref_parameters
),
adm AS (
    SELECT CASE WHEN f.discharge_date BETWEEN p.cur_start AND p.cur_end THEN 'current'
                WHEN f.discharge_date BETWEEN p.prev_start AND p.prev_end THEN 'previous' END AS period, f.*
    FROM fct_admissions f CROSS JOIN periods p
),
ed AS (
    SELECT CASE WHEN v.arrival_date BETWEEN p.cur_start AND p.cur_end THEN 'current'
                WHEN v.arrival_date BETWEEN p.prev_start AND p.prev_end THEN 'previous' END AS period, v.*
    FROM fct_ed_visits v CROSS JOIN periods p
),
ed_ranked AS (
    SELECT period, wait_minutes,
           ROW_NUMBER() OVER (PARTITION BY period ORDER BY wait_minutes) AS rn,
           COUNT(*) OVER (PARTITION BY period) AS n
    FROM ed WHERE period IS NOT NULL AND wait_minutes IS NOT NULL
),
kpis AS (
    SELECT period, 'Admissions' AS kpi, 1 AS sort_order, COUNT(*) * 1.0 AS value
    FROM adm WHERE period IS NOT NULL GROUP BY period
    UNION ALL
    SELECT period, '30-day readmission rate', 2, 1.0 * SUM(is_readmitted_30d) / SUM(is_index_stay)
    FROM adm WHERE period IS NOT NULL GROUP BY period
    UNION ALL
    SELECT period, 'Average length of stay (days)', 3, AVG(los_days)
    FROM adm WHERE period IS NOT NULL GROUP BY period
    UNION ALL
    SELECT period, 'Average cost per stay (GTQ)', 4, SUM(total_cost_gtq) / SUM(is_billed)
    FROM adm WHERE period IS NOT NULL GROUP BY period
    UNION ALL
    SELECT period, 'In-hospital mortality', 5, AVG(died_in_hospital)
    FROM adm WHERE period IS NOT NULL GROUP BY period
    UNION ALL
    SELECT period, 'ED visits', 6, COUNT(*) * 1.0
    FROM ed WHERE period IS NOT NULL GROUP BY period
    UNION ALL
    SELECT period, 'Median door-to-provider (min)', 7, MIN(CASE WHEN 1.0 * rn / n >= 0.5 THEN wait_minutes END)
    FROM ed_ranked GROUP BY period
    UNION ALL
    SELECT period, 'ED left without being seen', 8, AVG(is_lwbs)
    FROM ed WHERE period IS NOT NULL GROUP BY period
    UNION ALL
    SELECT period, 'Triage target compliance', 9, 1.0 * SUM(met_triage_target) / COUNT(wait_minutes)
    FROM ed WHERE period IS NOT NULL GROUP BY period
)
SELECT
    k.sort_order,
    k.kpi,
    ROUND(MAX(CASE WHEN k.period = 'current'  THEN k.value END), 4)     AS last_12_months,
    ROUND(MAX(CASE WHEN k.period = 'previous' THEN k.value END), 4)     AS previous_12_months,
    ROUND(MAX(CASE WHEN k.period = 'current' THEN k.value END)
          / MAX(CASE WHEN k.period = 'previous' THEN k.value END) - 1, 4) AS change_pct,
    (SELECT cur_start || ' to ' || cur_end FROM periods)                AS current_period
FROM kpis k
GROUP BY k.sort_order, k.kpi
ORDER BY k.sort_order;


-- One row per admission, ready for Looker Studio and the R report ----------------------
DROP TABLE IF EXISTS mart_admissions_detail;
CREATE TABLE mart_admissions_detail AS
SELECT
    f.admission_id, f.patient_id, f.hospital_id, h.hospital_name, f.admit_date, f.discharge_date,
    f.discharge_month, f.admission_type, f.icd10_code, f.diagnosis, f.clinical_category, f.is_program_target,
    f.sex, f.payer_type, f.age_at_admission, f.age_band, f.charlson_index, f.charlson_band,
    f.los_days, f.icu_days, f.discharge_disposition, f.total_cost_gtq, f.is_index_stay, f.is_readmitted_30d,
    f.days_to_readmission, f.is_readmission, f.program_group, f.program_period, f.is_program_eligible, f.call_status
FROM fct_admissions f
JOIN dim_hospital h ON h.hospital_id = f.hospital_id;
