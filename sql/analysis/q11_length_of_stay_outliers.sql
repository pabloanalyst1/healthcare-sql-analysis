-- Question: Which stays are length-of-stay outliers (above Q3 + 1.5 x IQR for their diagnosis),
-- and how much extra cost do they carry?
-- Skills: quartiles with NTILE, joins back to the detail, outlier rule
WITH quartiles AS (
    SELECT icd10_code, los_days, NTILE(4) OVER (PARTITION BY icd10_code ORDER BY los_days) AS q
    FROM fct_admissions
),
bounds AS (
    SELECT icd10_code,
           MAX(CASE WHEN q = 1 THEN los_days END)                       AS q1,
           MAX(CASE WHEN q = 3 THEN los_days END)                       AS q3
    FROM quartiles GROUP BY icd10_code
),
flagged AS (
    SELECT f.*, b.q3 + 1.5 * (b.q3 - b.q1) AS upper_fence
    FROM fct_admissions f JOIN bounds b USING (icd10_code)
)
SELECT
    diagnosis,
    COUNT(*)                                                            AS stays,
    SUM(los_days > upper_fence)                                         AS outlier_stays,
    ROUND(100.0 * SUM(los_days > upper_fence) / COUNT(*), 1)            AS outlier_pct,
    ROUND(MAX(upper_fence), 1)                                          AS los_fence_days,
    ROUND(100.0 * SUM(CASE WHEN los_days > upper_fence THEN total_cost_gtq END)
          / SUM(total_cost_gtq), 1)                                     AS share_of_dx_cost_pct
FROM flagged
GROUP BY diagnosis
ORDER BY outlier_stays DESC
LIMIT 6;
