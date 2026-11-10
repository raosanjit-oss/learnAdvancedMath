"""One job at a time and a small daily budget for the single-server beta."""

from contextlib import contextmanager
from datetime import date
from threading import Lock

job_lock = Lock()
budget_lock = Lock()
counts = {}


def check_budget(kind, limit):
    with budget_lock:
        key = (date.today(), kind)
        if counts.get(key, 0) >= limit:
            raise ValueError("The beta has reached today's capacity. Please try tomorrow.")
        counts[key] = counts.get(key, 0) + 1


@contextmanager
def generation_slot():
    if not job_lock.acquire(blocking=False):
        raise ValueError("Another lesson is being made. Please try again in a few minutes.")
    try:
        check_budget("video", 5)
        yield
    finally:
        job_lock.release()
