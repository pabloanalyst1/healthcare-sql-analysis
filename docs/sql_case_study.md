# SQL case study: business questions and answers

Each question is answered by one query in [`sql/analysis/`](../sql/analysis). Results come from the default run (`python run_pipeline.py`, seed 42). Regenerate this file with `python scripts/run_case_study.py`.

1. [How has the network's 30-day readmission rate evolved, year over year?](#q1)
2. [Which diagnoses drive readmissions, and how many readmissions does each one cause?](#q2)
3. [Which hospitals readmit more patients than their case mix predicts?](#q3)
4. [Did the transitional care program reduce readmissions for its target conditions?](#q4)
5. [Which patients had 3+ admissions within any 12-month window ("frequent flyers"),](#q5)
6. [When is the emergency department most congested?](#q6)
7. [Do long waits make patients leave without being seen?](#q7)
8. [Which hospitals miss the Manchester triage targets, and for which levels?](#q8)
9. [Which diagnoses concentrate the hospital spend, and why (volume, length of stay or ICU)?](#q9)
10. [How much do readmissions cost the network per year, and which index diagnoses cause it?](#q10)
11. [Which stays are length-of-stay outliers (above Q3 + 1.5 x IQR for their diagnosis),](#q11)
12. [How do readmissions, length of stay and cost differ by payer?](#q12)

## <a id="q1"></a>1. How has the network's 30-day readmission rate evolved, year over year?

[`q01_network_readmission_trend.sql`](../sql/analysis/q01_network_readmission_trend.sql)

<details><summary>Show SQL</summary>

```sql
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
```

</details>

| year | index_stays | readmissions | readmission_rate_pct | change_pp |
| --- | --- | --- | --- | --- |
| 2023 | 7212 | 959 | 13.3 |  |
| 2024 | 8386 | 1116 | 13.31 | 0.01 |
| 2025 | 8762 | 1042 | 11.89 | -1.42 |
| 2026 | 3612 | 378 | 10.47 | -1.42 |

## <a id="q2"></a>2. Which diagnoses drive readmissions, and how many readmissions does each one cause?

[`q02_highest_risk_diagnoses.sql`](../sql/analysis/q02_highest_risk_diagnoses.sql)

<details><summary>Show SQL</summary>

```sql
-- Question: Which diagnoses drive readmissions, and how many readmissions does each one cause?
-- Skills: CTEs, share of total with a window SUM, running total
WITH by_dx AS (
    SELECT
        diagnosis,
        COUNT(*)                                                        AS index_stays,
        SUM(is_readmitted_30d)                                          AS readmissions
    FROM fct_admissions
    WHERE is_index_stay = 1
    GROUP BY diagnosis
)
SELECT
    diagnosis,
    index_stays,
    readmissions,
    ROUND(100.0 * readmissions / index_stays, 1)                        AS readmission_rate_pct,
    ROUND(100.0 * readmissions / SUM(readmissions) OVER (), 1)          AS share_of_readmissions_pct,
    ROUND(100.0 * SUM(readmissions) OVER (ORDER BY readmissions DESC)
          / SUM(readmissions) OVER (), 1)                               AS cumulative_share_pct
FROM by_dx
ORDER BY readmissions DESC
LIMIT 8;
```

</details>

| diagnosis | index_stays | readmissions | readmission_rate_pct | share_of_readmissions_pct | cumulative_share_pct |
| --- | --- | --- | --- | --- | --- |
| Heart failure | 2386 | 600 | 25.1 | 17.2 | 17.2 |
| Pneumonia | 2829 | 432 | 15.3 | 12.4 | 29.5 |
| COPD with acute exacerbation | 1698 | 426 | 25.1 | 12.2 | 41.7 |
| Type 2 diabetes with hyperglycemia | 2012 | 345 | 17.1 | 9.9 | 51.6 |
| Colon cancer | 1297 | 312 | 24.1 | 8.9 | 60.5 |
| Sepsis | 1103 | 213 | 19.3 | 6.1 | 66.6 |
| Acute myocardial infarction | 1222 | 198 | 16.2 | 5.7 | 72.3 |
| Urinary tract infection | 1942 | 194 | 10.0 | 5.6 | 77.8 |

## <a id="q3"></a>3. Which hospitals readmit more patients than their case mix predicts?

[`q03_risk_adjusted_hospital_ranking.sql`](../sql/analysis/q03_risk_adjusted_hospital_ranking.sql)

<details><summary>Show SQL</summary>

```sql
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
```

</details>

| rank | hospital_name | index_stays | observed_rate_pct | expected_rate_pct | oe_ratio | risk_standardized_rate_pct | assessment |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Volcán Central | 8310 | 11.3 | 12.5 | 0.906 | 11.3 | Better than expected |
| 2 | Volcán Occidente | 5541 | 11.5 | 12.4 | 0.928 | 11.6 | Better than expected |
| 3 | Volcán Mixco | 6184 | 12.9 | 12.5 | 1.033 | 12.9 | As expected |
| 4 | Volcán Sur | 4249 | 13.6 | 12.6 | 1.08 | 13.5 | Worse than expected |
| 5 | Volcán Norte | 3688 | 14.8 | 12.7 | 1.167 | 14.6 | Worse than expected |

## <a id="q4"></a>4. Did the transitional care program reduce readmissions for its target conditions?

[`q04_program_difference_in_differences.sql`](../sql/analysis/q04_program_difference_in_differences.sql)

<details><summary>Show SQL</summary>

```sql
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
```

</details>

| program_group | pre_rate_pct | post_rate_pct | change_pp | diff_in_diff_pp |
| --- | --- | --- | --- | --- |
| Program hospitals | 21.2 | 13.93 | -7.27 | -4.71 |
| Comparison hospitals | 23.67 | 21.11 | -2.56 | 0.0 |

## <a id="q5"></a>5. Which patients had 3+ admissions within any 12-month window ("frequent flyers"),

[`q05_frequent_flyers.sql`](../sql/analysis/q05_frequent_flyers.sql)

<details><summary>Show SQL</summary>

```sql
-- Question: Which patients had 3+ admissions within any 12-month window ("frequent flyers"),
-- and what share of total cost do they represent?
-- Skills: window frame with RANGE over a numeric date (rolling 365 days per patient)
WITH rolling AS (
    SELECT
        patient_id,
        admission_id,
        total_cost_gtq,
        COUNT(*) OVER (
            PARTITION BY patient_id
            ORDER BY JULIANDAY(admit_date)
            RANGE BETWEEN 365 PRECEDING AND CURRENT ROW
        )                                                               AS admissions_last_365d
    FROM fct_admissions
),
flyers AS (
    SELECT DISTINCT patient_id FROM rolling WHERE admissions_last_365d >= 3
)
SELECT
    (SELECT COUNT(*) FROM flyers)                                       AS frequent_flyer_patients,
    ROUND(100.0 * (SELECT COUNT(*) FROM flyers)
          / (SELECT COUNT(DISTINCT patient_id) FROM fct_admissions), 1) AS share_of_patients_pct,
    ROUND(100.0 * SUM(CASE WHEN patient_id IN (SELECT patient_id FROM flyers) THEN total_cost_gtq END)
          / SUM(total_cost_gtq), 1)                                     AS share_of_cost_pct,
    ROUND(100.0 * SUM(CASE WHEN patient_id IN (SELECT patient_id FROM flyers) THEN 1 END)
          / COUNT(*), 1)                                                AS share_of_admissions_pct
FROM fct_admissions;
```

</details>

| frequent_flyer_patients | share_of_patients_pct | share_of_cost_pct | share_of_admissions_pct |
| --- | --- | --- | --- |
| 1153 | 4.8 | 18.2 | 14.3 |

## <a id="q6"></a>6. When is the emergency department most congested?

[`q06_ed_peak_hours.sql`](../sql/analysis/q06_ed_peak_hours.sql)

<details><summary>Show SQL</summary>

```sql
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
```

</details>

| hour | visits | avg_wait_minutes | lwbs_rate_pct | wait_rank |
| --- | --- | --- | --- | --- |
| 18:00 | 7421 | 96.8 | 8.5 | 1 |
| 11:00 | 8447 | 96.7 | 8.3 | 2 |
| 17:00 | 7278 | 96.2 | 8.1 | 3 |
| 10:00 | 8206 | 95.3 | 7.9 | 4 |
| 12:00 | 7885 | 94.6 | 8.0 | 5 |
| 19:00 | 7273 | 94.6 | 9.0 | 6 |

## <a id="q7"></a>7. Do long waits make patients leave without being seen?

[`q07_lwbs_vs_wait.sql`](../sql/analysis/q07_lwbs_vs_wait.sql)

<details><summary>Show SQL</summary>

```sql
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
```

</details>

| avg_wait_of_others_in_same_hour | visits | lwbs_visits | lwbs_rate_pct | times_the_lowest_band |
| --- | --- | --- | --- | --- |
| 1. <30 min | 4344 | 57 | 1.3 | 1.0 |
| 2. 30-60 min | 21775 | 722 | 3.3 | 2.5 |
| 3. 60-90 min | 28462 | 1361 | 4.8 | 3.6 |
| 4. 90-120 min | 24340 | 1478 | 6.1 | 4.6 |
| 5. 120-180 min | 23356 | 1846 | 7.9 | 6.0 |
| 6. 180+ min | 8957 | 1162 | 13.0 | 9.9 |

## <a id="q8"></a>8. Which hospitals miss the Manchester triage targets, and for which levels?

[`q08_triage_target_compliance.sql`](../sql/analysis/q08_triage_target_compliance.sql)

<details><summary>Show SQL</summary>

```sql
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
```

</details>

| hospital_name | overall_pct | very_urgent_10min_pct | urgent_60min_pct | standard_120min_pct | urgent_median_wait_min | lwbs_pct |
| --- | --- | --- | --- | --- | --- | --- |
| Volcán Mixco | 44.7 | 10.3 | 36.9 | 48.6 | 71.4 | 10.3 |
| Volcán Norte | 44.7 | 9.6 | 36.3 | 49.1 | 71.6 | 10.1 |
| Volcán Sur | 53.3 | 13.7 | 46.1 | 57.9 | 63.1 | 8.2 |
| Volcán Occidente | 63.8 | 25.1 | 57.2 | 68.3 | 54.1 | 6.3 |
| Volcán Central | 72.7 | 35.2 | 68.4 | 76.4 | 46.7 | 4.9 |

## <a id="q9"></a>9. Which diagnoses concentrate the hospital spend, and why (volume, length of stay or ICU)?

[`q09_cost_by_diagnosis.sql`](../sql/analysis/q09_cost_by_diagnosis.sql)

<details><summary>Show SQL</summary>

```sql
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
```

</details>

| diagnosis | stays | total_cost_m_gtq | share_of_cost_pct | avg_cost_gtq | median_cost_gtq | p90_cost_gtq | avg_los_days | icu_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Acute myocardial infarction | 1393 | 104.2 | 10.8 | 75,323 | 71,267 | 102,100 | 5.67 | 40.2 |
| Colon cancer | 1421 | 87.0 | 9.0 | 61,756 | 57,659 | 85,297 | 7.66 | 11.8 |
| Pneumonia | 3257 | 86.4 | 8.9 | 26,866 | 22,677 | 46,400 | 6.63 | 13.1 |
| Heart failure | 2715 | 84.0 | 8.7 | 31,310 | 26,752 | 55,012 | 7.75 | 13.7 |
| Hip fracture | 982 | 75.4 | 7.8 | 77,734 | 74,330 | 104,404 | 9.98 | 5.6 |
| Sepsis | 1453 | 74.4 | 7.7 | 51,676 | 43,779 | 91,206 | 10.23 | 46.4 |
| Knee osteoarthritis (knee replacement) | 954 | 65.8 | 6.8 | 69,617 | 68,743 | 85,753 | 3.31 | 0.8 |
| Acute appendicitis | 1869 | 55.4 | 5.7 | 29,900 | 28,795 | 38,512 | 2.92 | 2.4 |

## <a id="q10"></a>10. How much do readmissions cost the network per year, and which index diagnoses cause it?

[`q10_cost_of_readmissions.sql`](../sql/analysis/q10_cost_of_readmissions.sql)

<details><summary>Show SQL</summary>

```sql
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
```

</details>

| index_diagnosis | readmission_stays | total_cost_m_gtq | cost_per_year_m_gtq | avg_cost_per_readmission_gtq |
| --- | --- | --- | --- | --- |
| Heart failure | 601 | 20.51 | 5.87 | 34,706 |
| Colon cancer | 287 | 14.52 | 4.15 | 51,144 |
| Pneumonia | 436 | 12.81 | 3.67 | 29,663 |
| COPD with acute exacerbation | 426 | 12.71 | 3.63 | 29,901 |
| Acute myocardial infarction | 198 | 9.79 | 2.8 | 49,674 |
| Sepsis | 214 | 9.07 | 2.59 | 42,389 |

## <a id="q11"></a>11. Which stays are length-of-stay outliers (above Q3 + 1.5 x IQR for their diagnosis),

[`q11_length_of_stay_outliers.sql`](../sql/analysis/q11_length_of_stay_outliers.sql)

<details><summary>Show SQL</summary>

```sql
-- Question: Which stays are length-of-stay outliers (above Q3 + 1.5 x IQR for their diagnosis),
-- and how much extra cost do they carry?
-- Skills: quartiles with NTILE, joins back to the detail, outlier rule
WITH quartiles AS (
    SELECT icd10_code, los_days, NTILE(4) OVER (PARTITION BY icd10_code ORDER BY los_days) AS q
    FROM fct_admissions
),
bounds AS (
    SELECT icd10_code,
           MAX(CASE WHEN q = 1 THEN los_days END)                       AS q1,
           MAX(CASE WHEN q = 3 THEN los_days END)                       AS q3
    FROM quartiles GROUP BY icd10_code
),
flagged AS (
    SELECT f.*, b.q3 + 1.5 * (b.q3 - b.q1) AS upper_fence
    FROM fct_admissions f JOIN bounds b USING (icd10_code)
)
SELECT
    diagnosis,
    COUNT(*)                                                            AS stays,
    SUM(los_days > upper_fence)                                         AS outlier_stays,
    ROUND(100.0 * SUM(los_days > upper_fence) / COUNT(*), 1)            AS outlier_pct,
    ROUND(MAX(upper_fence), 1)                                          AS los_fence_days,
    ROUND(100.0 * SUM(CASE WHEN los_days > upper_fence THEN total_cost_gtq END)
          / SUM(total_cost_gtq), 1)                                     AS share_of_dx_cost_pct
FROM flagged
GROUP BY diagnosis
ORDER BY outlier_stays DESC
LIMIT 6;
```

</details>

| diagnosis | stays | outlier_stays | outlier_pct | los_fence_days | share_of_dx_cost_pct |
| --- | --- | --- | --- | --- | --- |
| Pneumonia | 3257 | 148 | 4.5 | 13.5 | 11.7 |
| Normal delivery | 2704 | 90 | 3.3 | 3.4 | 6.1 |
| Urinary tract infection | 2093 | 87 | 4.2 | 7.8 | 10.5 |
| Heart failure | 2715 | 86 | 3.2 | 16.7 | 8.3 |
| Type 2 diabetes with hyperglycemia | 2158 | 78 | 3.6 | 11.2 | 8.9 |
| Cesarean delivery | 2081 | 76 | 3.7 | 5.4 | 6.0 |

## <a id="q12"></a>12. How do readmissions, length of stay and cost differ by payer?

[`q12_payer_mix.sql`](../sql/analysis/q12_payer_mix.sql)

<details><summary>Show SQL</summary>

```sql
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
```

</details>

| payer_type | stays | share_of_stays_pct | readmission_rate_pct | left_ama_pct | avg_los_days | avg_cost_gtq |
| --- | --- | --- | --- | --- | --- | --- |
| Private insurance | 15684 | 50.6 | 11.3 | 0.77 | 5.31 | 32,028 |
| Self-pay | 10134 | 32.7 | 15.1 | 3.05 | 5.24 | 30,727 |
| Corporate agreement | 5184 | 16.7 | 11.0 | 0.71 | 5.2 | 31,754 |
