from typing import Callable

from python_library.job.job import IJob


class PlanJob(IJob):
    def __init__(
        self,
        plan_and_start: Callable[[], None],
        on_failed: Callable[[Exception], None],
    ):
        super().__init__()
        self.plan_and_start = plan_and_start
        self.on_failed = on_failed

    def execute(self) -> None:
        try:
            self.plan_and_start()
        except Exception as e:
            self.on_failed(e)
