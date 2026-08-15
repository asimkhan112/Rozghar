"""Scheduled background work.

`scheduler.py` owns registration and lifecycle; `scheduled_tasks.py` owns what
the tasks actually do. The split matters because the tasks are useful without
the scheduler — the CLI and the test suite call them directly, which is how
they get tested without waiting for a trigger to fire.
"""

from app.tasks.scheduled_tasks import TASKS, TaskResult

__all__ = ["TASKS", "TaskResult"]
