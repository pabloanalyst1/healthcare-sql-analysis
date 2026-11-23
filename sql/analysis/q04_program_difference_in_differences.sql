-- Question: Did the transitional care program reduce readmissions for its target conditions?
-- Method: difference-in-differences. The change in program hospitals minus the change in
-- comparison hospitals removes the network-wide trend that a simple before/after would include.
-- Skills: conditional aggregation, pivoting a 2x2 table
WITH rates AS (
    SELECT
        program_group,
        100.0 * SUM(CASE WHEN program_period = 'Pre'  THEN readmissions_30d END)
              / SUM(CASE WHEN program_period = 'Pre'  THEN index_stays END) AS pre_rate,
        100.0 * SUM(CASE WHEN program_period = 'Post' THEN readmissions_30d END)
              / SUM(CASE WHEN program_period = 'Post' THEN index_stays END) AS post_rate
    FROM mart_program_evaluation
    WHERE condition_group = 'Target conditions'
    GROUP BY program_group
)
SELECT
    program_group,
    ROUND(pre_rate, 2)                                                  AS pre_rate_pct,
    ROUND(post_rate, 2)                                                 AS post_rate_pct,
    ROUND(post_rate - pre_rate, 2)                                      AS change_pp,
    ROUND((post_rate - pre_rate)
          - (SELECT post_rate - pre_rate FROM rates WHERE program_group = 'Comparison hospitals'), 2) AS diff_in_diff_pp
FROM rates
ORDER BY program_group DESC;
