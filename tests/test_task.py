import datetime
from typing import Optional
import unittest

import omegaconf as oc
import pandas as pd

from aqueduct.artifact import (
    Artifact,
    ArtifactSpec,
    InMemoryArtifact,
    CompositeArtifact,
    resolve_artifact_from_spec,
)
from aqueduct.config import set_config, resolve_config_from_spec
from aqueduct.task import (
    Task,
    AggregateTask,
)

from aqueduct.task.autoresolve import fetch_args_from_config
from aqueduct.task.autostore import resolve_writer
from aqueduct.base import run
from aqueduct import apply


class TestCompute(unittest.TestCase):
    def test_simple_task(self):
        class SimpleTask(Task):
            def __init__(self, value):
                self.value = value

            def run(self):
                return self.value

        t = SimpleTask(2)
        self.assertEqual(2, run(t))


class PretenseTask(Task):
    def __init__(self, a, b=None, c=12):
        self.a = a
        self.b = b
        self.c = c

    def run(self, requirements=None):
        return self.a + self.b + self.c


class TestFullyQualifiedName(unittest.TestCase):
    def test_fqn(self):
        t = PretenseTask(1, 2, 3)
        self.assertEqual("tests.test_task.PretenseTask", t._fully_qualified_name())


class TestResolveConfig(unittest.TestCase):
    def setUp(self):
        pass

    def test_resolve_dict(self):
        class LocalTask(Task):
            def cfg(self):
                return {}

            def run(self):
                pass

        task = LocalTask()
        self.assertEqual(task.cfg(), oc.OmegaConf.create(task.config()))

    def test_resolve_str(self):
        cfg = {"section": {"value": 2}}
        set_config(cfg)

        class LocalTask(Task):
            CONFIG = "section"

            def run(self):
                pass

        task = LocalTask()

        self.assertEqual(oc.OmegaConf.create({"value": 2}), task.config())

    def test_resolve_object_name_class(self):
        inner_dict = {"a": 1, "b": 2}
        set_config({"tests": {"test_task": {"PretenseTask": inner_dict}}})

        t = PretenseTask(14)
        config = resolve_config_from_spec(None, t)

        self.assertEqual(config, inner_dict)


class TestFetchArgs(unittest.TestCase):
    def test_empty_config(self):
        def fn(a, b=None):
            self.assertEqual(a, 2)
            self.assertIsNone(b)

        new_args, new_kwargs = fetch_args_from_config({}, fn, 2)

        fn(*new_args, **new_kwargs)

    def test_should_use_config(self):
        def fn(a, b=None):
            self.assertEqual(b, 13)
            self.assertEqual(a, 14)

        new_args, new_kwargs = fetch_args_from_config({"b": 13}, fn, 14)

        fn(*new_args, **new_kwargs)


class TestFetchArgsOnCall(unittest.TestCase):
    def tearDown(self):
        set_config({})

    def test_missing_params(self):
        inner_dict = {"a": 2, "b": 3}
        set_config({"tests": {"test_task": {"PretenseTask": inner_dict}}})

        t = PretenseTask(3)
        self.assertEqual(18, run(t))


store = {}


class StoringTask(Task):
    AQ_AUTOSAVE = False

    def __init__(self, should_succeed=True):
        self.succeed = should_succeed

    def run(self):
        if self.succeed:
            store["testkey"] = 1

    def artifact(self):
        return InMemoryArtifact("testkey", store)


class TestTaskIO(unittest.TestCase):
    def test_resolve_writer(self):
        writer = resolve_writer(pd.DataFrame)
        self.assertEqual(writer.__name__, "write_to_parquet")


class TaskWithArtifact(Task):
    def __init__(self):
        self.store = {}
        super().__init__()

    def artifact(self):
        return InMemoryArtifact("test", self.store)


class TaskWithoutArtifact(Task):
    pass


class TestAggregateTask(unittest.TestCase):
    def setUp(self):
        self.store = {}

    def test_empty_artifacts(self):
        class Aggregate(AggregateTask):
            def requirements(self):
                return [TaskWithoutArtifact(), TaskWithoutArtifact()]

        t = Aggregate()
        self.assertIsNone(t.artifact())

    def test_with_artifacts(self):
        class Aggregate(AggregateTask):
            def requirements(self):
                return [TaskWithArtifact(), TaskWithArtifact()]

        t = Aggregate()
        spec = t.artifact()
        assert spec is not None
        resolved_artifact = resolve_artifact_from_spec(spec)

        self.assertIsInstance(resolved_artifact, CompositeArtifact)
        self.assertEqual(2, len(resolved_artifact.artifacts))


class FixedDateArtifact(Artifact):
    def __init__(self, date):
        self.date = date

    def last_modified(self):
        return self.date

    def exists(self):
        return True

    def size(self):
        return 0


class TaskDependsOnDate(Task):
    def requirements(self):
        return {"nested": TaskWithDate()}

    def artifact(self):
        return FixedDateArtifact(datetime.datetime(2021, 1, 1))


class TaskNoDate(Task):
    pass


class TaskWithDate(Task):
    AQ_UPDATED = "2022-01-01"

    def artifact(self):
        return FixedDateArtifact(datetime.datetime(2023, 1, 1))


class FarDepOnDate(Task):
    def requirements(self):
        return TaskDependsOnDate()


def square(x):
    return x * x


class TestApply(unittest.TestCase):
    def test_map(self):
        t = PretenseTask(2, 2, 2)

        t_map = apply(square, t)
        result = run(t_map)
        self.assertEqual(36, result)
        self.assertEqual("PretenseTask*square", t_map.task_name())

    def test_class_apply(self):
        AppliedClass: type[PretenseTask] = apply(square, PretenseTask)

        t = AppliedClass(2, 2, 2)
        result = run(t)
        self.assertEqual(36, result)
