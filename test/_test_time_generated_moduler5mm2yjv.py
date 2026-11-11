
from luigi.metrics import NoMetricsCollector

class CustomMetricsCollector(NoMetricsCollector):
    def __init__(self, *args, **kwargs):
        super(CustomMetricsCollector, self).__init__(*args, **kwargs)
        self.elapsed = {}

    def handle_task_statistics(self, task, statistics):
        if "elapsed" in statistics:
            self.elapsed[(task.family, task.params.get("n"))] = statistics["elapsed"]
