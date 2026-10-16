"""Only a fully counted/paginated cloud response may imply deletions."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CompleteServerSnapshot:
    rows: tuple

    def __len__(self):
        return len(self.rows)


class SyncConflictError(ValueError):
    pass
