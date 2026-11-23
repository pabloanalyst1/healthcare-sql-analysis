-- Question: Which patients had 3+ admissions within any 12-month window ("frequent flyers"),
-- and what share of total cost do they represent?
-- Skills: window frame with RANGE over a numeric date (rolling 365 days per patient)
WITH rolling AS (
    SELECT
        patient_id,
        admission_id,
        total_cost_gtq,
        COUNT(*) OVER (
            PARTITION BY patient_id
            ORDER BY JULIANDAY(admit_date)
            RANGE BETWEEN 365 PRECEDING AND CURRENT ROW
        )                                                               AS admissions_last_365d
    FROM fct_admissions
),
flyers AS (
    SELECT DISTINCT patient_id FROM rolling WHERE admissions_last_365d >= 3
)
SELECT
    (SELECT COUNT(*) FROM flyers)                                       AS frequent_flyer_patients,
    ROUND(100.0 * (SELECT COUNT(*) FROM flyers)
          / (SELECT COUNT(DISTINCT patient_id) FROM fct_admissions), 1) AS share_of_patients_pct,
    ROUND(100.0 * SUM(CASE WHEN patient_id IN (SELECT patient_id FROM flyers) THEN total_cost_gtq END)
          / SUM(total_cost_gtq), 1)                                     AS share_of_cost_pct,
    ROUND(100.0 * SUM(CASE WHEN patient_id IN (SELECT patient_id FROM flyers) THEN 1 END)
          / COUNT(*), 1)                                                AS share_of_admissions_pct
FROM fct_admissions;
