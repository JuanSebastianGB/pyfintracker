"""Direct unit tests for the ``_to_lines`` helper."""

from __future__ import annotations

from decimal import Decimal

import pytest


@pytest.mark.unit
class TestToLines:
    """Direct unit tests for the ``_to_lines`` helper.

    Coverage gap: previously only exercised indirectly via
    ``compute_monthly_report``. These tests pin the aggregation,
    ordering, and Decimal behavior.
    """

    def test_empty_input_returns_empty_list(self) -> None:
        from pyfintracker.reports import _to_lines

        assert _to_lines([]) == []

    def test_single_entry(self) -> None:
        from pyfintracker.reports import _to_lines

        entries = [{"day": 5, "label": "Income:Salary", "amount": Decimal("1000")}]
        lines = _to_lines(entries)

        assert len(lines) == 1
        assert lines[0].day == 5
        assert lines[0].label == "Income:Salary"
        assert lines[0].amount == Decimal("1000")
        assert lines[0].balance == Decimal("1000")

    def test_multiple_entries_same_day_aggregated(self) -> None:
        from pyfintracker.reports import _to_lines

        entries = [
            {"day": 15, "label": "Income:Salary", "amount": Decimal("3000")},
            {"day": 15, "label": "Income:Bonus", "amount": Decimal("500")},
        ]
        lines = _to_lines(entries)

        assert len(lines) == 2
        # Sorted by (day, label): Bonus comes before Salary alphabetically
        assert lines[0].label == "Income:Bonus"
        assert lines[0].amount == Decimal("500")
        assert lines[0].balance == Decimal("500")
        assert lines[1].label == "Income:Salary"
        assert lines[1].amount == Decimal("3000")
        assert lines[1].balance == Decimal("3500")

    def test_running_balance_across_days(self) -> None:
        from pyfintracker.reports import _to_lines

        entries = [
            {"day": 1, "label": "Expenses:Rent", "amount": Decimal("1000")},
            {"day": 5, "label": "Expenses:Food", "amount": Decimal("200")},
            {"day": 10, "label": "Expenses:Food", "amount": Decimal("50")},
        ]
        lines = _to_lines(entries)

        # Day 1 Rent only, day 5 Food first entry, day 10 Food aggregated with day 5
        assert [line.day for line in lines] == [1, 5, 10]
        assert lines[0].balance == Decimal("1000")
        assert lines[1].balance == Decimal("1200")  # 1000 + 200
        assert lines[2].balance == Decimal("1250")  # 1200 + 50 (same key aggregated)

    def test_preserves_order_across_days(self) -> None:
        from pyfintracker.reports import _to_lines

        entries = [
            {"day": 10, "label": "Expenses:A", "amount": Decimal("100")},
            {"day": 5, "label": "Expenses:B", "amount": Decimal("200")},
            {"day": 15, "label": "Expenses:C", "amount": Decimal("50")},
        ]
        lines = _to_lines(entries)

        assert [line.day for line in lines] == [5, 10, 15]

    def test_aggregates_same_key_with_negative_amounts(self) -> None:
        from pyfintracker.reports import _to_lines

        entries = [
            {"day": 1, "label": "X", "amount": Decimal("100")},
            {"day": 1, "label": "X", "amount": Decimal("-50")},
            {"day": 1, "label": "X", "amount": Decimal("-100")},
        ]
        lines = _to_lines(entries)

        assert len(lines) == 1
        # Sum: 100 - 50 - 100
        assert lines[0].amount == Decimal("-50")
        assert lines[0].balance == Decimal("-50")


@pytest.mark.unit
class TestToLinesProperty:
    """Property-based tests: any list of entries round-trips through ``_to_lines``.

    Invariants under test:
      1. Output length equals the number of distinct ``(day, label)`` keys.
      2. Sum of output amounts equals sum of input amounts.
      3. Final running balance equals total sum.
      4. Output is sorted by ``(day, label)``.
    """

    @pytest.mark.property
    @pytest.mark.parametrize(
        "entries",
        [
            # (day, label, amount)
            [],
            [(1, "A", "100")],
            [(1, "A", "100"), (1, "A", "200")],
            [(2, "B", "50"), (1, "A", "100"), (1, "A", "-100")],
            [(15, "X", "0"), (31, "Y", "9999999999.99")],
        ],
    )
    def test_invariants_hold_for_finite_examples(self, entries: list[tuple[int, str, str]]) -> None:
        from pyfintracker.reports import _to_lines

        entry_dicts = [
            {"day": d, "label": label, "amount": Decimal(amt)} for d, label, amt in entries
        ]
        lines = _to_lines(entry_dicts)

        # 1. Output length equals distinct (day, label) keys.
        assert len(lines) == len({(d, label) for d, label, _ in entries})

        # 2. Sum of output amounts equals sum of input amounts.
        assert sum((line.amount for line in lines), Decimal("0")) == sum(
            (Decimal(amt) for _, _, amt in entries), Decimal("0")
        )

        # 3. Final running balance equals total sum (when sorted is non-empty).
        if lines:
            expected_total = sum((Decimal(amt) for _, _, amt in entries), Decimal("0"))
            assert lines[-1].balance == expected_total

        # 4. Output is sorted by (day, label).
        days_labels = [(line.day, line.label) for line in lines]
        assert days_labels == sorted(days_labels)
