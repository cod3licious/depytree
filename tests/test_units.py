import depytree.build_depytree as dpt
from depytree.metrics import MinMaxScaler, norm_counts


def test_MinMaxScaler():
    test_dict = {f"{i}": {"key": i} for i in range(1, 12)}
    scaler = MinMaxScaler(test_dict, "key")
    assert scaler.scale(1) == 0
    assert scaler.scale(6) == 0.5
    assert scaler.scale(11) == 1


def test_norm_counts():
    git_deps = {
        "mock_module.py": {"mock_module.py": 8, "utils/__init__.py": 1, "utils/mock_utils.py": 2},
        "utils/__init__.py": {"mock_module.py": 1, "utils/__init__.py": 3, "utils/mock_utils.py": 2},
        "utils/mock_utils.py": {"mock_module.py": 2, "utils/__init__.py": 2, "utils/mock_utils.py": 5},
    }
    git_deps_normed = norm_counts(git_deps, norm_global=False, scale=1.0)
    assert "mock_module.py" not in git_deps_normed["mock_module.py"]
    assert git_deps_normed["mock_module.py"]["utils/__init__.py"] == 1 / 8
    assert git_deps_normed["mock_module.py"]["utils/mock_utils.py"] == 2 / 8
    assert git_deps_normed["utils/__init__.py"]["mock_module.py"] == 1 / 3
    git_deps_normed = norm_counts(git_deps, norm_global=True, scale=1.0)
    assert "mock_module.py" not in git_deps_normed["mock_module.py"]
    assert git_deps_normed["mock_module.py"]["utils/__init__.py"] == 1 / 5
    assert git_deps_normed["mock_module.py"]["utils/mock_utils.py"] == 2 / 5
    assert git_deps_normed["utils/__init__.py"]["mock_module.py"] == 1 / 5
    assert git_deps_normed["utils/mock_utils.py"]["mock_module.py"] == 2 / 5


def test_is_private():
    assert dpt.is_private("_private_function")
    assert dpt.is_private("__private_function")
    assert dpt.is_private("__main__") is False
    assert dpt.is_private("not_private") is False


def test_get_parent():
    assert dpt.get_parent("a.b.c") == "a.b"
    assert dpt.get_parent("a.b.c", 2) == "a"
    assert dpt.get_parent("a.b.c", 5) == "a"
    assert dpt.get_parent("a.b.c", 0) == "a.b.c"
    assert dpt.get_parent("a.b.c", -1) == "a.b.c"


def test_get_all_parents():
    assert dpt.get_all_parents("a.b.c.d") == ["a", "a.b", "a.b.c"]
    assert dpt.get_all_parents("a") == []


def test_resolve_relative_import():
    # from __future__ import annotations
    assert dpt.resolve_relative_import("anyio.pytest_plugin", "__future__", 0) == "__future__"
    # from ._core._exceptions import iterate_exceptions
    assert dpt.resolve_relative_import("anyio.pytest_plugin", "_core._exceptions", 1) == "anyio._core._exceptions"
    # from .abc import TestRunner
    assert dpt.resolve_relative_import("anyio.pytest_plugin", "abc", 1) == "anyio.abc"
    # from . import current_time
    assert dpt.resolve_relative_import("anyio.to_interpreter", None, 1) == "anyio"
    # from .. import CapacityLimiterStatistics
    assert dpt.resolve_relative_import("anyio._backends._asyncio", None, 2) == "anyio"
    # from .._core._eventloop import claim_worker_thread
    assert dpt.resolve_relative_import("anyio._backends._asyncio", "_core._eventloop", 2) == "anyio._core._eventloop"
