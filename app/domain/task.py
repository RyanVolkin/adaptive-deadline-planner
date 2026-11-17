from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


TASK_TYPES = ("homework", "project", "reading", "studying", "other")
PRIORITIES = ("low", "medium", "high")
# Leave room for estimates up to four times the original in PostgreSQL integers.
MAX_ORIGINAL_ESTIMATE = 536_870_911


class TaskState(str, Enum):
    ACTIVE = "Active"
    OVERDUE = "Overdue"
    COMPLETED = "Completed"


@dataclass
class Task:
    user_id: str
    name: str
    type: str
    priority: str
    deadline: date
    original_estimate: int
    starting_estimate: int
    adjusted_estimate: int
    remaining_work: int
    created_at: datetime
    updated_at: datetime
    id: int | None = None
    completion_pct: int = 0
    estimate_ratio: float | None = None
    completed_at: datetime | None = None

    def is_complete(self):
        return self.completion_pct == 100

    def state(self, today):
        if self.is_complete():
            return TaskState.COMPLETED
        if self.deadline < today:
            return TaskState.OVERDUE
        return TaskState.ACTIVE
