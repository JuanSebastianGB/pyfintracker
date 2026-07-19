"""AST scan: reject cross-currency Decimal addition in reports.py.

CI gate — if someone adds raw `Decimal + posting.amount` across accounts
without going through ``fx.convert``, this test fails.

Whitelist: ``aggregated.get(key, Decimal("0")) + e["amount"]`` where
``e["amount"]`` is already converted to the display currency.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parents[2] / "src" / "pyfintracker"
REPORTS_PATH = SRC / "reports.py"


def _is_posting_amount(node: ast.AST) -> bool:
    """Heuristic: node references a posting's ``amount`` field via subscript.

    Matches ``e["amount"]``, ``p.amount``, ``row.amount``, etc.
    """
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and node.slice.value == "amount":
        # e["amount"] or row["amount"]
        return True
    return isinstance(node, ast.Attribute) and node.attr == "amount"


def _is_converted_amount(node: ast.AST) -> bool:
    """Heuristic: node is a value known to already be in display currency.

    Whitelisted patterns:
    - ``aggregated.get(key, Decimal("0"))`` — aggregated is same-currency by
      construction (all entries inside have been converted)
    """
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
    )


def _walk_binops(tree: ast.AST) -> list[tuple[ast.AST, ast.AST]]:
    """Yield ``(left, right)`` operands of every ``Decimal + x`` BinOp."""
    results: list[tuple[ast.AST, ast.AST]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Add):
            continue
        # Left side must involve Decimal — either a Name "Decimal" / a literal
        left_is_decimal = (
            (isinstance(node.left, ast.Name) and node.left.id == "Decimal")
            or (isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Name)
                and node.left.func.id == "Decimal")
            or _is_converted_amount(node.left)
        )
        if not left_is_decimal:
            continue
        results.append((node.left, node.right))
    return results


def _is_violation(left: ast.AST, right: ast.AST) -> bool:
    """True if ``left + right`` adds raw posting amounts across currencies.

    A violation: either side is a posting amount AND the other side is not
    already-converted (i.e. the LHS or RHS sums postings from different
    accounts without going through ``fx.convert``).
    """
    return (
        (_is_posting_amount(right) and not _is_converted_amount(left))
        or (_is_posting_amount(left) and not _is_converted_amount(right))
    )


def test_no_raw_currency_sum_in_reports() -> None:
    """Reports.py must not add raw posting amounts across currencies."""
    tree = ast.parse(REPORTS_PATH.read_text())
    violations: list[str] = []
    for left, right in _walk_binops(tree):
        if _is_violation(left, right):
            snippet = ast.unparse(ast.BinOp(left=left, op=ast.Add(), right=right))
            violations.append(snippet)
    assert not violations, (
        "Cross-currency Decimal addition without convert():\n  "
        + "\n  ".join(violations)
    )
