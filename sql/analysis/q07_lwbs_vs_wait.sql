-- Question: Do long waits make patients leave without being seen?
-- Skills: reading a banded mart, relative risk against the best band
SELECT
    wait_band                                                           AS avg_wait_of_others_in_same_hour,
    visits,
    lwbs_visits,
    ROUND(100 * lwbs_rate, 1)                                           AS lwbs_rate_pct,
    ROUND(lwbs_rate / FIRST_VALUE(lwbs_rate) OVER (ORDER BY wait_band), 1) AS times_the_lowest_band
FROM mart_ed_lwbs_by_wait_band
ORDER BY wait_band;
