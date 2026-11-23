-- Question: How has the network's 30-day readmission rate evolved, year over year?
-- Skills: aggregation, LAG window function
WITH yearly AS (
    SELECT
        STRFTIME('%Y', discharge_date)                                  AS year,
        COUNT(*)                                                        AS index_stays,
        SUM(is_readmitted_30d)                                          AS readmissions,
        ROUND(100.0 * SUM(is_readmitted_30d) / COUNT(*), 2)             AS readmission_rate_pct
    FROM fct_admissions
    WHERE is_index_stay = 1
    GROUP BY 1
)
SELECT
    year,
    index_stays,
    readmissions,
    readmission_rate_pct,
    ROUND(readmission_rate_pct - LAG(readmission_rate_pct) OVER (ORDER BY year), 2) AS change_pp
FROM yearly
ORDER BY year;
