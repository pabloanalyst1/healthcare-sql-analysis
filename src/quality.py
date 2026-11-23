"""Data quality checks. Each check is a SQL query that returns the number of bad rows (0 = pass).

If any check fails the pipeline stops before exporting, so the dashboard never shows bad data.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

CHECKS: list[tuple[str, str]] = [
    ("Every raw admission is either staged or rejected (after removing duplicates)",
     """SELECT ABS((SELECT COUNT(DISTINCT TRIM(admission_id)) FROM raw_admissions)
                - (SELECT COUNT(*) FROM stg_admissions) - (SELECT COUNT(*) FROM stg_rejected_admissions))"""),
    ("Rejected admissions are below 0.5% of the extract",
     """SELECT CASE WHEN 1.0 * (SELECT COUNT(*) FROM stg_rejected_admissions)
                       / (SELECT COUNT(*) FROM stg_admissions) > 0.005 THEN 1 ELSE 0 END"""),
    ("Every admission has a valid ICD-10 code after cleaning",
     "SELECT COUNT(*) FROM stg_admissions a LEFT JOIN dim_diagnosis d USING (icd10_code) WHERE d.icd10_code IS NULL"),
    ("Every admission belongs to a known patient",
     "SELECT COUNT(*) FROM stg_admissions a LEFT JOIN stg_patients p USING (patient_id) WHERE p.patient_id IS NULL"),
    ("Every admission and ED visit belongs to a known hospital",
     """SELECT (SELECT COUNT(*) FROM stg_admissions WHERE hospital_id NOT IN (SELECT hospital_id FROM dim_hospital))
             + (SELECT COUNT(*) FROM stg_ed_visits WHERE hospital_id NOT IN (SELECT hospital_id FROM dim_hospital))"""),
    ("Patient sex is standardized to M/F",
     "SELECT COUNT(*) FROM stg_patients WHERE sex IS NULL OR sex NOT IN ('M', 'F')"),
    ("Joins do not duplicate or drop admissions (fact rows = staged rows)",
     "SELECT ABS((SELECT COUNT(*) FROM fct_admissions) - (SELECT COUNT(*) FROM stg_admissions))"),
    ("Joins do not duplicate or drop ED visits (fact rows = staged rows)",
     "SELECT ABS((SELECT COUNT(*) FROM fct_ed_visits) - (SELECT COUNT(*) FROM stg_ed_visits))"),
    ("Readmission flags are consistent (index stay, unplanned, within 30 days)",
     """SELECT COUNT(*) FROM fct_admissions i
        LEFT JOIN fct_admissions r ON r.admission_id = i.readmission_id
        WHERE i.is_readmitted_30d = 1
          AND (i.is_index_stay = 0 OR r.is_planned = 1 OR i.days_to_readmission NOT BETWEEN 0 AND 30
               OR r.patient_id <> i.patient_id)"""),
    # An ED visit can point to an admission rejected in staging (impossible dates); that is expected
    ("Admitted ED visits link to an admission in the extract (staged or rejected)",
     """SELECT COUNT(*) FROM fct_ed_visits v
        WHERE v.is_admitted = 1
          AND v.admission_id NOT IN (SELECT admission_id FROM fct_admissions
                                     UNION ALL SELECT admission_id FROM stg_rejected_admissions)"""),
    ("ED wait times are non-negative and triage levels are 1-5",
     "SELECT COUNT(*) FROM fct_ed_visits WHERE wait_minutes < 0 OR triage_level NOT BETWEEN 1 AND 5"),
    ("Unbilled stays are below 3% (cost metrics stay representative)",
     "SELECT CASE WHEN AVG(1 - is_billed) > 0.03 THEN 1 ELSE 0 END FROM fct_admissions"),
    ("Network readmission rate is plausible (5%-25%)",
     """SELECT CASE WHEN 1.0 * SUM(is_readmitted_30d) / SUM(is_index_stay) NOT BETWEEN 0.05 AND 0.25
                    THEN 1 ELSE 0 END FROM fct_admissions"""),
    ("Lengths of stay are positive and below 90 days",
     "SELECT COUNT(*) FROM fct_admissions WHERE los_days <= 0 OR los_days > 90"),
]


class DataQualityError(RuntimeError):
    pass


def run_quality_checks(db_path: Path) -> dict[str, int]:
    """Run every check, log the result and raise if any check fails."""
    results: dict[str, int] = {}
    with sqlite3.connect(db_path) as conn:
        for name, sql in CHECKS:
            bad = int(conn.execute(sql).fetchone()[0] or 0)
            results[name] = bad
            log.info("%s %s%s", "PASS" if bad == 0 else "FAIL", name, "" if bad == 0 else f" ({bad} bad rows)")
    failed = [n for n, b in results.items() if b]
    if failed:
        raise DataQualityError(f"{len(failed)} data quality check(s) failed: {failed}")
    return results
