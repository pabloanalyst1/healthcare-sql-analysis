-- Question: How do readmissions, length of stay and cost differ by payer?
-- Skills: grouping on a dimension attribute, multiple metrics with conditional logic
SELECT
    payer_type,
    COUNT(*)                                                            AS stays,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)                  AS share_of_stays_pct,
    ROUND(100.0 * SUM(is_readmitted_30d) / SUM(is_index_stay), 1)       AS readmission_rate_pct,
    ROUND(100.0 * SUM(discharge_disposition = 'Left against medical advice') / COUNT(*), 2) AS left_ama_pct,
    ROUND(AVG(los_days), 2)                                             AS avg_los_days,
    ROUND(SUM(total_cost_gtq) / SUM(is_billed), 0)                      AS avg_cost_gtq
FROM fct_admissions
GROUP BY payer_type
ORDER BY stays DESC;
