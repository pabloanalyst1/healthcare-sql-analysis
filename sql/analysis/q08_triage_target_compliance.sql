-- Question: Which hospitals miss the Manchester triage targets, and for which levels?
-- Skills: pivot with conditional aggregation
SELECT
    hospital_name,
    ROUND(100.0 * SUM(visits_within_target) / SUM(visits_seen), 1)      AS overall_pct,
    ROUND(100 * MAX(CASE WHEN triage_level = 2 THEN compliance_rate END), 1) AS very_urgent_10min_pct,
    ROUND(100 * MAX(CASE WHEN triage_level = 3 THEN compliance_rate END), 1) AS urgent_60min_pct,
    ROUND(100 * MAX(CASE WHEN triage_level = 4 THEN compliance_rate END), 1) AS standard_120min_pct,
    MAX(CASE WHEN triage_level = 3 THEN median_wait_minutes END)        AS urgent_median_wait_min,
    ROUND(100.0 * SUM(lwbs_visits) / SUM(visits), 1)                    AS lwbs_pct
FROM mart_ed_triage_compliance
GROUP BY hospital_name
ORDER BY overall_pct;
