from typing import (
    Any,
    TypeVar,
    cast,
    Mapping,
    Optional,
    TYPE_CHECKING,
    TypedDict,
    Literal,
)

import logging
import tqdm

from dask.distributed import Client, Future, as_completed, SpecCluster, LocalCluster
from dask_jobqueue import SLURMCluster

from ..config import set_config, get_config
from .backend import Backend
from ..task import AbstractTask
from ..util import resolve_task_tree
from ..task_tree import TaskTree, _map_type_in_tree, OptionalTaskTree

if TYPE_CHECKING:
    from .base import BackendSpec

_T = TypeVar("_T")

_logger = logging.getLogger(__name__)


class DaskBackendDictSpec(TypedDict):
    type: Literal["dask"]
    address: str


class DaskBackend(Backend):
    """Execute :class:`Task` on a Dask cluster.

    Arguments:
        client (`dask.Client`): Client pointing to the desired Dask cluster."""

    def __init__(self, client: Optional[Client] = None):
        if client is None:
            cluster = LocalCluster()
            self.client = cluster.get_client()
        else:
            self.client = client

    def execute(self, task: OptionalTaskTree):
        _logger.info("Creating graph...")
        graph = create_dask_graph(task, self.client, backend_spec=self._spec())

        return compute_dask_graph(graph)

    def _scheduler_address(self):
        return self.client.scheduler_info()["address"]

    def _spec(self) -> DaskBackendDictSpec:
        return {"type": "dask", "address": self._scheduler_address()}

    def __str__(self):
        return f"DaskBackend(scheduler={self._scheduler_address()})"


def wrap_task(cfg: Mapping[str, Any], task: AbstractTask, *args, **kwargs):
    set_config(cfg)
    return task(*args, **kwargs)


def create_dask_graph(
    task: OptionalTaskTree, client: Client, backend_spec: "Optional[BackendSpec]"
) -> Any:
    def task_to_dask_future(task: AbstractTask, requirements=None) -> Future:
        cfg = get_config()

        if requirements is not None:
            future = client.submit(
                wrap_task,
                cfg,
                task,
                requirements,
                backend_spec=backend_spec,
                key=task._unique_key(),
            )
        else:
            future = client.submit(
                wrap_task, cfg, task, backend_spec=backend_spec, key=task._unique_key()
            )

        return future

    future = resolve_task_tree(task, task_to_dask_future)

    return future


def compute_dask_graph(graph):
    computed = _map_type_in_tree(graph, Future, dask_future_to_result)
    return computed


def resolve_dask_dict_backend_spec(spec: DaskBackendDictSpec) -> DaskBackend:
    return DaskBackend(Client(address=spec["address"]))


def dask_future_to_result(future: Future):
    return future.result()
