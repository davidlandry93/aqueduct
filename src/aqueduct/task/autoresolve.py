import dask.base
import functools
import inspect
from typing import cast, Type, Callable, Any, TYPE_CHECKING, Mapping, Tuple

from ..config import AqueductConfig, resolve_config_from_spec

if TYPE_CHECKING:
    from .abstract_task import AbstractTask


def fetch_bind_from_config(
    cfg: Mapping[str, Any], fn: Callable, *args, **kwargs: Mapping[str, Any]
) -> inspect.BoundArguments:
    signature = inspect.signature(fn)
    bind = signature.bind_partial(*args, **kwargs)

    for p in signature.parameters:
        # Find all arguments which do not have a defined value.
        was_specified_by_user = p in bind.arguments
        # has_no_default_value = signature.parameters[p].default != inspect._empty

        # Here I commented out `has_no_default_value`, I'm still undecided as to if
        # we should fetch args from config even if they are positional.

        if (
            p not in ["self", "args", "kwargs", "*", "/"]
            and not was_specified_by_user
            # and has_no_default_value
        ):
            if p in cfg:
                bind.arguments[p] = cfg[p]

    bind.apply_defaults()

    return bind


def fetch_args_from_config(
    cfg: Mapping[str, Any], fn: Callable, *args, **kwargs: Mapping[str, Any]
) -> Tuple[Tuple, Mapping[str, Any]]:
    """Given a callable and a configuration dict, try and fetch argument values from
    the config dict if needed.

    Arguments:
        fn: The function for which we want to fetch arguments from config.
        args: The arguments the functino would be called with.
        kwargs: The kwargs the function would be called with.
        cfg: The config dictionary from which to tech default values if needed.

    Returns:
        args: The same args, except if an argument is `None`, it is replaced by the
            corresponding value in `cfg`, if it exists there.
        kwargs: The same kwargs, except if an argument value was `None`, it is replaced
            by the value of the corresponding key in `cfg`."""
    bind = fetch_bind_from_config(cfg, fn, *args, **kwargs)

    return bind.args, bind.kwargs


def init_wrapper(task_class: Type["AbstractTask"], fn):
    @functools.wraps(fn)
    def wrapped_init(self, *args, **kwargs):
        cfg = resolve_config_from_spec(task_class.CONFIG, task_class)

        bind = fetch_bind_from_config(cfg, fn, self, *args, **kwargs)

        if hasattr(self, "AQ_HASH_EXCLUDE"):
            for arg in self.AQ_HASH_EXCLUDE:
                if arg in bind.arguments:
                    del bind.arguments[arg]

        new_args, new_kwargs = bind.args, bind.kwargs

        # Remove self from new_args
        self._args_hash = dask.base.tokenize(
            self._fully_qualified_name(), *new_args[1:], **new_kwargs
        )
        self._args = new_args
        self._kwargs = new_kwargs

        return fn(*new_args, **new_kwargs)

    return wrapped_init


class WrapInitMeta(type):
    def __new__(cls, name, bases, dct, **kwds):
        x = super().__new__(cls, name, bases, dct, **kwds)
        x.__init__ = init_wrapper(x, x.__init__)  # type: ignore
        return x
