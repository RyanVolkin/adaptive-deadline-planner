from dataclasses import dataclass
from datetime import datetime


@dataclass
class WorkRecord:
    task_id: int
    minutes: int
    completion_pct: int
    created_at: datetime
    id: int | None = None
