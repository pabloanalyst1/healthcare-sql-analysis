-- =====================================================================================
-- 04 MARTS - READMISSIONS
-- Numerators and denominators are stored separately so the BI tool can re-aggregate
-- correctly: rate = SUM(readmissions) / SUM(index_stays), never an average of rates.
-- =====================================================================================

-- Monthly readmissions by hospital and clinical category ------------------------------
DROP TABLE IF EXISTS mart_readmissions_monthly;
CREATE TABLE mart_readmissions_monthly AS
SELECT
    f.discharge_month                                                   AS month_start,
    f.hospital_id,
    h.hospital_name,
    h.program_group,
    f.clinical_category,
    f.is_program_target,
    COUNT(*)                                                            AS index_stays,
    SUM(f.is_readmitted_30d)                                            AS readmissions_30d,
    ROUND(1.0 * SUM(f.is_readmitted_30d) / COUNT(*), 4)                 AS readmission_rate
FROM fct_admissions f
JOIN dim_hospital h ON h.hospital_id = f.hospital_id
WHERE f.is_index_stay = 1
GROUP BY 1, 2, 3, 4, 5, 6;


-- Readmissions by diagnosis ------------------------------------------------------------
DROP TABLE IF EXISTS mart_readmissions_by_diagnosis;
CREATE TABLE mart_readmissions_by_diagnosis AS
WITH network AS (
    SELECT 1.0 * SUM(is_readmitted_30d) / COUNT(*) AS network_rate
    FROM fct_admissions WHERE is_index_stay = 1
)
SELECT
    f.icd10_code,
    f.diagnosis,
    f.clinical_category,
    f.is_program_target,
    COUNT(*)                                                            AS index_stays,
    SUM(f.is_readmitted_30d)                                            AS readmissions_30d,
    ROUND(1.0 * SUM(f.is_readmitted_30d) / COUNT(*), 4)                 AS readmission_rate,
    ROUND(1.0 * SUM(f.is_readmitted_30d) / COUNT(*) / n.network_rate, 2) AS rate_vs_network,
    ROUND(AVG(f.days_to_readmission), 1)                                AS avg_days_to_readmission,
    -- share of readmissions in the first week: a sign of premature discharge
    ROUND(1.0 * SUM(CASE WHEN f.days_to_readmission <= 7 THEN 1 ELSE 0 END)
          / NULLIF(SUM(f.is_readmitted_30d), 0), 4)                     AS share_within_7_days
FROM fct_admissions f
CROSS JOIN network n
WHERE f.is_index_stay = 1
GROUP BY f.icd10_code, f.diagnosis, f.clinical_category, f.is_program_target, n.network_rate
ORDER BY readmission_rate DESC;


-- Risk-adjusted readmissions by hospital (indirect standardization) -------------------
-- Each index stay's expected risk = the network rate for stays with the same diagnosis,
-- age band and comorbidity band. Observed / Expected > 1 means worse than its case mix predicts.
DROP TABLE IF EXISTS mart_hospital_readmissions_risk_adjusted;
CREATE TABLE mart_hospital_readmissions_risk_adjusted AS
WITH expected AS (
    SELECT
        hospital_id,
        is_readmitted_30d,
        AVG(is_readmitted_30d) OVER (PARTITION BY icd10_code, age_band, charlson_band) AS expected_risk
    FROM fct_admissions
    WHERE is_index_stay = 1
),
network AS (
    SELECT AVG(is_readmitted_30d) AS network_rate FROM expected
),
by_hospital AS (
    SELECT
        hospital_id,
        COUNT(*)                                                        AS index_stays,
        SUM(is_readmitted_30d)                                          AS observed_readmissions,
        SUM(expected_risk)                                              AS expected_readmissions
    FROM expected
    GROUP BY hospital_id
)
SELECT
    b.hospital_id,
    h.hospital_name,
    h.city,
    b.index_stays,
    b.observed_readmissions,
    ROUND(b.expected_readmissions, 1)                                   AS expected_readmissions,
    ROUND(1.0 * b.observed_readmissions / b.index_stays, 4)             AS observed_rate,
    ROUND(b.expected_readmissions / b.index_stays, 4)                   AS expected_rate,
    ROUND(b.observed_readmissions / b.expected_readmissions, 3)         AS oe_ratio,
    ROUND(b.observed_readmissions / b.expected_readmissions * n.network_rate, 4) AS risk_standardized_rate,
    RANK() OVER (ORDER BY b.observed_readmissions / b.expected_readmissions) AS rank_best_to_worst
FROM by_hospital b
JOIN dim_hospital h ON h.hospital_id = b.hospital_id
CROSS JOIN network n;


-- Transitional care program: 2x2 table for the difference-in-differences --------------
DROP TABLE IF EXISTS mart_program_evaluation;
CREATE TABLE mart_program_evaluation AS
SELECT
    program_group,
    program_period,
    CASE WHEN is_program_target = 1 THEN 'Target conditions' ELSE 'Other conditions' END AS condition_group,
    COUNT(*)                                                            AS index_stays,
    SUM(is_readmitted_30d)                                              AS readmissions_30d,
    ROUND(1.0 * SUM(is_readmitted_30d) / COUNT(*), 4)                   AS readmission_rate,
    SUM(is_program_eligible)                                            AS eligible_for_call,
    SUM(CASE WHEN call_status = 'Completed' THEN 1 ELSE 0 END)          AS calls_completed
FROM fct_admissions
WHERE is_index_stay = 1
GROUP BY 1, 2, 3;


-- Program trend: quarterly readmission rate for the target conditions ------------------
DROP TABLE IF EXISTS mart_program_quarterly;
CREATE TABLE mart_program_quarterly AS
SELECT
    STRFTIME('%Y', discharge_date) || '-Q' || ((CAST(STRFTIME('%m', discharge_date) AS INTEGER) + 2) / 3) AS quarter,
    program_group,
    COUNT(*)                                                            AS index_stays,
    SUM(is_readmitted_30d)                                              AS readmissions_30d,
    ROUND(1.0 * SUM(is_readmitted_30d) / COUNT(*), 4)                   AS readmission_rate
FROM fct_admissions
WHERE is_index_stay = 1 AND is_program_target = 1
GROUP BY 1, 2;


-- Follow-up call outcome vs readmission (inside the program) --------------------------
DROP TABLE IF EXISTS mart_followup_call_outcomes;
CREATE TABLE mart_followup_call_outcomes AS
SELECT
    COALESCE(call_status, 'No call') AS call_status,
    COUNT(*)                                                            AS index_stays,
    SUM(is_readmitted_30d)                                              AS readmissions_30d,
    ROUND(1.0 * SUM(is_readmitted_30d) / COUNT(*), 4)                   AS readmission_rate
FROM fct_admissions
WHERE is_index_stay = 1 AND is_program_eligible = 1
GROUP BY 1;
