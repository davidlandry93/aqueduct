import unittest
from aqueduct.backend.dask import DaskBackend
from aqueduct.task import Task
from aqueduct.task.parallel_task import ParallelTask


class TaskB(Task):
    def __init__(self, value):
        self.value = value

    def run(self):
        return self.value


class TaskA(ParallelTask):
    def requirements(self):
        return TaskB(2)

    def items(self):
        return [1, 2, 3]

    def map(self, x, requirements=None):
        return x**2

    def accumulator(self, requirements=None):
        return requirements

    def reduce(self, x, acc, requirements=None):
        return acc + x


class TestDaskParallelTask(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = DaskBackend()

    def test_run(self):
        task = TaskA()
        result = self.backend.run(task)
        self.assertEqual(result, 16)