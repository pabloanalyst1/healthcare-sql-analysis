-- Question: Which hospitals readmit more patients than their case mix predicts?
-- Skills: indirect standardization with window AVG over risk strata, RANK
SELECT
    rank_best_to_worst                                                  AS rank,
    hospital_name,
    index_stays,
    ROUND(100 * observed_rate, 1)                                       AS observed_rate_pct,
    ROUND(100 * expected_rate, 1)                                       AS expected_rate_pct,
    oe_ratio,
    ROUND(100 * risk_standardized_rate, 1)                              AS risk_standardized_rate_pct,
    CASE WHEN oe_ratio > 1.05 THEN 'Worse than expected'
         WHEN oe_ratio < 0.95 THEN 'Better than expected'
         ELSE 'As expected' END                                         AS assessment
FROM mart_hospital_readmissions_risk_adjusted
ORDER BY rank_best_to_worst;
