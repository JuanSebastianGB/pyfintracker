"""AST scan: reject float annotations in money-touching modules.

CI gate — if someone introduces ``float`` for amounts, this test fails.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parents[3] / "src" / "pyfintracker"


def _has_float_annotation(tree: ast.AST) -> bool:
    """Walk AST to find ``float`` type annotations or usage."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "float":
            # Not in a function call context? Check if it's part of an annotation
            return True
        if isinstance(node, ast.Subscript):
            # e.g. list[float], Optional[float]
            if isinstance(node.value, ast.Name) and node.value.id == "float":
                return True
            if isinstance(node.slice, ast.Name) and node.slice.id == "float":
                return True
    return False


def _check_module(name: str) -> None:
    """Assert a single module has no ``float`` references."""
    path = SRC / f"{name}.py"
    if not path.exists():
        return  # skip nonexistent (future modules)
    with open(path) as f:
        tree = ast.parse(f.read())
    if _has_float_annotation(tree):
        pytest.fail(f"{name}.py contains 'float' annotation. Use Decimal for money amounts.")


def test_no_float_in_models() -> None:
    """Fail if any 'float' annotation exists in models.py."""
    _check_module("models")


def test_no_float_in_repository() -> None:
    """Fail if any 'float' annotation exists in repository.py."""
    _check_module("repository")


def test_no_float_in_reports() -> None:
    """Fail if any 'float' annotation exists in reports.py."""
    _check_module("reports")
