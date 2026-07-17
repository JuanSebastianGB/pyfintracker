"""Verify all public modules resolve and define __all__."""

import importlib

import pytest

MODULES = [
    "pyfintracker.models",
    "pyfintracker.validation",
    "pyfintracker.repository",
    "pyfintracker.reports",
    "pyfintracker.cli",
    "pyfintracker.db",
    "pyfintracker.config",
    "pyfintracker.exceptions",
]


@pytest.mark.unit
@pytest.mark.parametrize("module_name", MODULES)
def test_modules_resolve(module_name: str) -> None:
    """Each module imports cleanly and defines __all__."""
    mod = importlib.import_module(module_name)
    assert hasattr(mod, "__all__")
