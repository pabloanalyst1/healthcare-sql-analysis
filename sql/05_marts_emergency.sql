-- =====================================================================================
-- 05 MARTS - EMERGENCY DEPARTMENT WAITING TIMES
-- Percentiles use the nearest-rank method (SQLite has no PERCENTILE_CONT):
-- the p-th percentile is the first value whose rank / count >= p.
-- =====================================================================================

-- Arrivals and waits by hospital, weekday and hour (additive, for heatmaps) -----------
DROP TABLE IF EXISTS mart_ed_hourly;
CREATE TABLE mart_ed_hourly AS
SELECT
    hospital_id,
    day_of_week_num,
    day_of_week,
    arrival_hour,
    COUNT(*)                                                            AS visits,
    SUM(CASE WHEN wait_minutes IS NOT NULL THEN 1 ELSE 0 END)           AS visits_seen,
    ROUND(SUM(wait_minutes), 1)                                         AS total_wait_minutes,
    ROUND(AVG(wait_minutes), 1)                                         AS avg_wait_minutes,
    SUM(is_lwbs)                                                        AS lwbs_visits,
    ROUND(1.0 * SUM(is_lwbs) / COUNT(*), 4)                             AS lwbs_rate
FROM fct_ed_visits
GROUP BY 1, 2, 3, 4;


-- Monthly ED performance by hospital ---------------------------------------------------
DROP TABLE IF EXISTS mart_ed_monthly;
CREATE TABLE mart_ed_monthly AS
WITH ranked AS (
    SELECT
        hospital_id, arrival_month, wait_minutes,
        ROW_NUMBER() OVER (PARTITION BY hospital_id, arrival_month ORDER BY wait_minutes) AS rn,
        COUNT(*)     OVER (PARTITION BY hospital_id, arrival_month)                     AS n
    FROM fct_ed_visits
    WHERE wait_minutes IS NOT NULL
),
pct AS (
    SELECT hospital_id, arrival_month,
           MIN(CASE WHEN 1.0 * rn / n >= 0.5 THEN wait_minutes END)     AS median_wait_minutes,
           MIN(CASE WHEN 1.0 * rn / n >= 0.9 THEN wait_minutes END)     AS p90_wait_minutes
    FROM ranked GROUP BY 1, 2
)
SELECT
    v.arrival_month                                                     AS month_start,
    v.hospital_id,
    h.hospital_name,
    COUNT(*)                                                            AS visits,
    SUM(v.is_admitted)                                                  AS admitted_visits,
    SUM(v.is_lwbs)                                                      AS lwbs_visits,
    SUM(CASE WHEN v.wait_minutes IS NOT NULL THEN 1 ELSE 0 END)         AS visits_seen,
    SUM(v.met_triage_target)                                            AS visits_within_target,
    ROUND(SUM(v.wait_minutes), 1)                                       AS total_wait_minutes,
    p.median_wait_minutes,
    p.p90_wait_minutes,
    ROUND(1.0 * SUM(v.is_lwbs) / COUNT(*), 4)                           AS lwbs_rate,
    ROUND(1.0 * SUM(v.met_triage_target) / SUM(CASE WHEN v.wait_minutes IS NOT NULL THEN 1 ELSE 0 END), 4) AS triage_compliance
FROM fct_ed_visits v
JOIN dim_hospital h ON h.hospital_id = v.hospital_id
LEFT JOIN pct p ON p.hospital_id = v.hospital_id AND p.arrival_month = v.arrival_month
GROUP BY v.arrival_month, v.hospital_id, h.hospital_name, p.median_wait_minutes, p.p90_wait_minutes;


-- Manchester triage compliance by hospital and level -----------------------------------
DROP TABLE IF EXISTS mart_ed_triage_compliance;
CREATE TABLE mart_ed_triage_compliance AS
WITH ranked AS (
    SELECT
        hospital_id, triage_level, wait_minutes,
        ROW_NUMBER() OVER (PARTITION BY hospital_id, triage_level ORDER BY wait_minutes) AS rn,
        COUNT(*)     OVER (PARTITION BY hospital_id, triage_level)                     AS n
    FROM fct_ed_visits
    WHERE wait_minutes IS NOT NULL
),
pct AS (
    SELECT hospital_id, triage_level,
           MIN(CASE WHEN 1.0 * rn / n >= 0.5 THEN wait_minutes END)     AS median_wait_minutes,
           MIN(CASE WHEN 1.0 * rn / n >= 0.9 THEN wait_minutes END)     AS p90_wait_minutes
    FROM ranked GROUP BY 1, 2
)
SELECT
    v.hospital_id,
    h.hospital_name,
    v.triage_level,
    v.triage_name,
    v.target_minutes,
    COUNT(*)                                                            AS visits,
    SUM(CASE WHEN v.wait_minutes IS NOT NULL THEN 1 ELSE 0 END)         AS visits_seen,
    SUM(v.met_triage_target)                                            AS visits_within_target,
    ROUND(1.0 * SUM(v.met_triage_target) / SUM(CASE WHEN v.wait_minutes IS NOT NULL THEN 1 ELSE 0 END), 4) AS compliance_rate,
    p.median_wait_minutes,
    p.p90_wait_minutes,
    SUM(v.is_lwbs)                                                      AS lwbs_visits,
    ROUND(1.0 * SUM(v.is_lwbs) / COUNT(*), 4)                           AS lwbs_rate
FROM fct_ed_visits v
JOIN dim_hospital h ON h.hospital_id = v.hospital_id
LEFT JOIN pct p ON p.hospital_id = v.hospital_id AND p.triage_level = v.triage_level
GROUP BY v.hospital_id, h.hospital_name, v.triage_level, v.triage_name, v.target_minutes,
         p.median_wait_minutes, p.p90_wait_minutes;


-- LWBS vs. how long others were waiting at the same time -------------------------------
-- Each hospital-hour is classified by the average wait of patients seen in it (triage 3-5);
-- then LWBS rates are compared across those wait bands.
DROP TABLE IF EXISTS mart_ed_lwbs_by_wait_band;
CREATE TABLE mart_ed_lwbs_by_wait_band AS
WITH with_hour_wait AS (
    SELECT
        is_lwbs,
        triage_level,
        AVG(CASE WHEN triage_level >= 3 THEN wait_minutes END)
            OVER (PARTITION BY hospital_id, STRFTIME('%Y-%m-%d %H', arrival_ts)) AS avg_wait_in_hour
    FROM fct_ed_visits
),
banded AS (
    SELECT
        is_lwbs,
        CASE
            WHEN avg_wait_in_hour IS NULL THEN NULL
            WHEN avg_wait_in_hour < 30  THEN '1. <30 min'
            WHEN avg_wait_in_hour < 60  THEN '2. 30-60 min'
            WHEN avg_wait_in_hour < 90  THEN '3. 60-90 min'
            WHEN avg_wait_in_hour < 120 THEN '4. 90-120 min'
            WHEN avg_wait_in_hour < 180 THEN '5. 120-180 min'
            ELSE '6. 180+ min'
        END                                                             AS wait_band
    FROM with_hour_wait
    WHERE triage_level >= 3
)
SELECT
    wait_band,
    COUNT(*)                                                            AS visits,
    SUM(is_lwbs)                                                        AS lwbs_visits,
    ROUND(1.0 * SUM(is_lwbs) / COUNT(*), 4)                             AS lwbs_rate
FROM banded
WHERE wait_band IS NOT NULL
GROUP BY wait_band
ORDER BY wait_band;
