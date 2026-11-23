-- Question: Which diagnoses concentrate the hospital spend, and why (volume, length of stay or ICU)?
-- Skills: reading percentiles computed with ROW_NUMBER (nearest rank) in the mart
SELECT
    diagnosis,
    stays,
    ROUND(total_cost_gtq / 1e6, 1)                                      AS total_cost_m_gtq,
    ROUND(100 * share_of_total_cost, 1)                                 AS share_of_cost_pct,
    avg_cost_gtq,
    median_cost_gtq,
    p90_cost_gtq,
    avg_los_days,
    ROUND(100 * icu_share, 1)                                           AS icu_pct
FROM mart_cost_by_diagnosis
ORDER BY total_cost_gtq DESC
LIMIT 8;
