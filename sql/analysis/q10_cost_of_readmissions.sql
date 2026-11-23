-- Question: How much do readmissions cost the network per year, and which index diagnoses cause it?
-- Skills: self-join (readmission -> index stay), annualizing a multi-year total
WITH span AS (
    SELECT (JULIANDAY(study_end) - JULIANDAY(study_start) + 1) / 365.25 AS years FROM ref_parameters
)
SELECT
    i.diagnosis                                                         AS index_diagnosis,
    COUNT(*)                                                            AS readmission_stays,
    ROUND(SUM(r.total_cost_gtq) / 1e6, 2)                               AS total_cost_m_gtq,
    ROUND(SUM(r.total_cost_gtq) / (SELECT years FROM span) / 1e6, 2)    AS cost_per_year_m_gtq,
    ROUND(AVG(r.total_cost_gtq), 0)                                     AS avg_cost_per_readmission_gtq
FROM fct_admissions r
JOIN fct_admissions i ON i.admission_id = r.readmission_of
WHERE r.is_readmission = 1
GROUP BY i.diagnosis
ORDER BY total_cost_m_gtq DESC
LIMIT 6;
