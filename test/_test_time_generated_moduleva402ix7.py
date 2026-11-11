
import time

class CustomTaskContext:
    def __init__(self, task_process):
        self._task_process = task_process
        self._start = None

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        assert self._start is not None
        elapsed = time.perf_counter() - self._start
        self._task_process.status_reporter.report_task_statistics({"elapsed": elapsed})
