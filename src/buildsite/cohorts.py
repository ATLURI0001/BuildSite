"""Cohort retention and activity analysis utilities."""
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class CohortRecord:
    cohort_id: str
    total_users: int
    active_users: int

    @property
    def retention_rate(self) -> float:
        if self.total_users <= 0:
            return 0.0
        return round(self.active_users / self.total_users, 4)

def aggregate_cohort_retention(records: List[CohortRecord]) -> Dict[str, float]:
    """Aggregate retention rate across multiple cohort periods."""
    return {r.cohort_id: r.retention_rate for r in records}
