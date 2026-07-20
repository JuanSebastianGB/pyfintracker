"""Unit tests for recurring transaction domain logic.

Tests ``compute_next_date`` across all four frequencies and edge cases.
"""

from __future__ import annotations

from pyfintracker.models import RecurringPosting, RecurringRule, compute_next_date


class TestComputeNextDate:
    """``compute_next_date(current_iso, frequency) -> str``."""

    def test_daily(self) -> None:
        """Daily: next day."""
        assert compute_next_date("2026-07-20", "daily") == "2026-07-21"
        assert compute_next_date("2026-12-31", "daily") == "2027-01-01"

    def test_weekly(self) -> None:
        """Weekly: +7 days."""
        assert compute_next_date("2026-07-20", "weekly") == "2026-07-27"
        assert compute_next_date("2026-12-31", "weekly") == "2027-01-07"

    def test_monthly_same_day(self) -> None:
        """Monthly: same day of month when possible."""
        assert compute_next_date("2026-01-15", "monthly") == "2026-02-15"
        assert compute_next_date("2026-03-01", "monthly") == "2026-04-01"

    def test_monthly_jan31_to_feb28_non_leap(self) -> None:
        """Jan 31 → Feb 28 in a non-leap year."""
        assert compute_next_date("2026-01-31", "monthly") == "2026-02-28"

    def test_monthly_jan31_to_feb29_leap(self) -> None:
        """Jan 31 → Feb 29 in a leap year."""
        assert compute_next_date("2024-01-31", "monthly") == "2024-02-29"

    def test_monthly_mar31_to_apr30(self) -> None:
        """Mar 31 → Apr 30 (30-day month)."""
        assert compute_next_date("2026-03-31", "monthly") == "2026-04-30"

    def test_monthly_dec_to_jan(self) -> None:
        """Dec → Jan: year rolls over."""
        assert compute_next_date("2026-12-01", "monthly") == "2027-01-01"
        assert compute_next_date("2026-12-31", "monthly") == "2027-01-31"

    def test_yearly(self) -> None:
        """Yearly: same month/day, next year."""
        assert compute_next_date("2026-07-20", "yearly") == "2027-07-20"
        assert compute_next_date("2026-12-31", "yearly") == "2027-12-31"

    def test_yearly_feb29_non_leap_target(self) -> None:
        """Feb 29 → Feb 28 when next year is not leap."""
        assert compute_next_date("2024-02-29", "yearly") == "2025-02-28"

    def test_invalid_frequency(self) -> None:
        """Unknown frequency raises ValueError."""
        import pytest

        with pytest.raises(ValueError, match="unknown"):
            compute_next_date("2026-07-20", "unknown")


class TestRecurringRuleModel:
    """RecurringRule dataclass — to_row / from_row roundtrip."""

    def test_to_row_basic(self) -> None:
        """to_row produces expected keys."""
        rule = RecurringRule(
            name="Rent",
            description="Monthly rent",
            frequency="monthly",
            start_date="2026-07-01",
            next_date="2026-07-01",
            is_active=True,
        )
        row = rule.to_row()
        assert row["name"] == "Rent"
        assert row["description"] == "Monthly rent"
        assert row["frequency"] == "monthly"
        assert row["start_date"] == "2026-07-01"
        assert row["next_date"] == "2026-07-01"
        assert row["is_active"] == 1
        assert "id" not in row

    def test_to_row_with_id(self) -> None:
        """to_row includes id when set."""
        rule = RecurringRule(id=5, name="Test", start_date="2026-07-01", next_date="2026-07-01")
        row = rule.to_row()
        assert row["id"] == 5

    def test_from_row_roundtrip(self) -> None:
        """from_row(reconstructed) matches original."""
        rule = RecurringRule(
            id=1,
            name="Rent",
            description="Monthly office rent",
            frequency="monthly",
            interval_days=0,
            day_of_month=None,
            day_of_week=None,
            start_date="2026-07-01",
            end_date=None,
            next_date="2026-08-01",
            is_active=True,
            created_at="2026-07-20",
        )
        row = rule.to_row()
        # Simulate a SQLAlchemy Row
        class MockRow:
            def __init__(self) -> None:
                self._mapping = row

        restored = RecurringRule.from_row(MockRow())
        assert restored.name == rule.name
        assert restored.frequency == rule.frequency
        assert restored.start_date == rule.start_date
        assert restored.next_date == rule.next_date
        assert restored.is_active == rule.is_active

    def test_from_row_inactive(self) -> None:
        """from_row reads is_active correctly when 0."""
        class MockRow:
            def __init__(self) -> None:
                self._mapping = {
                    "id": 1,
                    "name": "Test",
                    "description": "",
                    "frequency": "monthly",
                    "interval_days": 0,
                    "start_date": "2026-07-01",
                    "next_date": "2026-07-01",
                    "is_active": 0,
                    "created_at": "2026-07-20",
                }

        rule = RecurringRule.from_row(MockRow())
        assert rule.is_active is False


class TestRecurringPostingModel:
    """RecurringPosting dataclass — to_row / from_row roundtrip."""

    def test_to_row_basic(self) -> None:
        """to_row produces expected keys."""
        from decimal import Decimal

        rp = RecurringPosting(account_id=1, amount=Decimal("50000"), currency="COP")
        row = rp.to_row()
        assert row["account_id"] == 1
        assert row["amount"] == "50000"
        assert row["currency"] == "COP"

    def test_from_row_roundtrip(self) -> None:
        """from_row(reconstructed) matches original."""
        from decimal import Decimal

        class MockRow:
            def __init__(self) -> None:
                self._mapping = {
                    "id": 1,
                    "rule_id": 1,
                    "account_id": 2,
                    "amount": "100000",
                    "currency": "COP",
                }

        rp = RecurringPosting.from_row(MockRow())
        assert rp.id == 1
        assert rp.rule_id == 1
        assert rp.account_id == 2
        assert rp.amount == Decimal("100000")
        assert rp.currency == "COP"
