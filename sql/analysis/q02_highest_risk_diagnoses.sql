-- Question: Which diagnoses drive readmissions, and how many readmissions does each one cause?
-- Skills: CTEs, share of total with a window SUM, running total
WITH by_dx AS (
    SELECT
        diagnosis,
        COUNT(*)                                                        AS index_stays,
        SUM(is_readmitted_30d)                                          AS readmissions
    FROM fct_admissions
    WHERE is_index_stay = 1
    GROUP BY diagnosis
)
SELECT
    diagnosis,
    index_stays,
    readmissions,
    ROUND(100.0 * readmissions / index_stays, 1)                        AS readmission_rate_pct,
    ROUND(100.0 * readmissions / SUM(readmissions) OVER (), 1)          AS share_of_readmissions_pct,
    ROUND(100.0 * SUM(readmissions) OVER (ORDER BY readmissions DESC)
          / SUM(readmissions) OVER (), 1)                               AS cumulative_share_pct
FROM by_dx
ORDER BY readmissions DESC
LIMIT 8;
