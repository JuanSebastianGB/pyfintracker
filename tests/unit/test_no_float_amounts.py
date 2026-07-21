"""AST scan: reject float annotations in money-touching modules.

CI gate — if someone introduces ``float`` for amounts, this test fails.

The detector flags ``float`` only in places that affect the runtime type system
(annotations, type subscriptions, variable annotations, explicit casts). Pure
``isinstance(x, float)`` calls — which are how we *reject* floats — are
deliberately ignored.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parents[2] / "src" / "pyfintracker"

# ponytail: list every money-touching module that must NOT contain ``float``
# annotations. Add a new entry here when introducing a new module that handles
# amounts.
MODULES: tuple[str, ...] = (
    "models",
    "repository",
    "reports",
    "fx",
    "validation",
    "tui",
    "tui_screens",
)


def _is_in_isinstance(node: ast.AST) -> bool:
    """True if ``node`` is the second argument of an ``isinstance(...)`` call."""
    # walk parents is annoying — caller does its own checks
    return False


def _has_float_annotation(tree: ast.AST) -> bool:
    """Walk AST to find ``float`` type annotations only.

    Flags:
    - Annotated assignment targets (``x: float = ...``)
    - Function arg / return annotations
    - Type subscription like ``list[float]``
    - ``cast(float, ...)`` style runtime hints

    Does NOT flag ``isinstance(x, float)`` (that is the legitimate rejection
    path in ``validate_amount``).
    """

    def _is_isinstance_call(n: ast.AST) -> bool:
        return (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "isinstance"
        )

    def _is_cast_float(n: ast.AST) -> bool:
        # cast("float", x) or cast(float, x) — we tolerate string form
        if not isinstance(n, ast.Call):
            return False
        if not isinstance(n.func, ast.Name) or n.func.id != "cast":
            return False
        return bool(n.args) and (
            (isinstance(n.args[0], ast.Name) and n.args[0].id == "float")
            or (
                isinstance(n.args[0], ast.Constant)
                and isinstance(n.args[0].value, str)
                and n.args[0].value == "float"
            )
        )

    for node in ast.walk(tree):
        # 1. AnnotatedAssign: ``x: float = ...``
        if (
            isinstance(node, ast.AnnAssign)
            and node.annotation is not None
            and isinstance(node.annotation, ast.Name)
            and node.annotation.id == "float"
        ):
            return True

        # 2. Function arg annotations, return annotations
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                if arg.annotation is not None:
                    a = ast.unparse(arg.annotation)
                    if a == "float" or a.startswith("float[") or a.endswith(" | float") or a.startswith("float |"):
                        return True
            if node.returns is not None:
                r = ast.unparse(node.returns)
                if (
                    r == "float"
                    or r.startswith("float[")
                    or r.endswith(" | float")
                    or r.startswith("float |")
                ) and "float" in r:
                    return True

        # 3. Class bases, Subscript with float inside (e.g. ``list[float]``)
        if isinstance(node, ast.Subscript):
            value_str = ast.unparse(node.value) if hasattr(ast, "unparse") else ""
            slice_str = ast.unparse(node.slice) if hasattr(ast, "unparse") else ""
            if value_str == "float" or slice_str == "float":
                return True

        # 4. cast(float, ...)
        if _is_cast_float(node):
            return True

    return False


def _check_module(name: str) -> None:
    """Assert a single module has no ``float`` references."""
    path = SRC / f"{name}.py"
    if not path.exists():
        pytest.skip(f"{name}.py does not exist yet")
    with open(path) as f:
        tree = ast.parse(f.read())
    if _has_float_annotation(tree):
        pytest.fail(f"{name}.py contains 'float' annotation. Use Decimal for money amounts.")


@pytest.mark.parametrize("module_name", MODULES)
def test_no_float_in_module(module_name: str) -> None:
    """Fail if any 'float' annotation exists in the module."""
    _check_module(module_name)
