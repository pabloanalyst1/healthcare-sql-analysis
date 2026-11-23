-- Question: When is the emergency department most congested?
-- Skills: aggregation over the additive hourly mart, ranking with DENSE_RANK
WITH hours AS (
    SELECT
        arrival_hour,
        SUM(visits)                                                     AS visits,
        SUM(total_wait_minutes) / SUM(visits_seen)                      AS avg_wait_minutes,
        1.0 * SUM(lwbs_visits) / SUM(visits)                            AS lwbs_rate
    FROM mart_ed_hourly
    GROUP BY arrival_hour
)
SELECT
    PRINTF('%02d:00', arrival_hour)                                     AS hour,
    visits,
    ROUND(avg_wait_minutes, 1)                                          AS avg_wait_minutes,
    ROUND(100 * lwbs_rate, 1)                                           AS lwbs_rate_pct,
    DENSE_RANK() OVER (ORDER BY avg_wait_minutes DESC)                  AS wait_rank
FROM hours
ORDER BY wait_rank
LIMIT 6;
