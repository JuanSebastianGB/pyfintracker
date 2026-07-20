"""Unit tests for tag validation."""

from __future__ import annotations

import pytest

from pyfintracker.validation import validate_tag_name


class TestValidateTagName:
    """validate_tag_name canonicalises and validates tag names."""

    def test_empty_raises(self) -> None:
        """Empty or whitespace-only tag names raise ValueError."""
        with pytest.raises(ValueError, match="Tag name must not be empty"):
            validate_tag_name("")
        with pytest.raises(ValueError, match="Tag name must not be empty"):
            validate_tag_name("  ")
        with pytest.raises(ValueError, match="Tag name must not be empty"):
            validate_tag_name("\t")

    def test_comma_raises(self) -> None:
        """Tag names containing commas raise ValueError."""
        with pytest.raises(ValueError, match="must not contain commas"):
            validate_tag_name("groceries,food")

    def test_trims_whitespace(self) -> None:
        """Leading/trailing whitespace is stripped."""
        result = validate_tag_name("  groceries  ")
        assert result == "groceries"

    def test_lowercases(self) -> None:
        """Tag name is lowercased."""
        result = validate_tag_name("Groceries")
        assert result == "groceries"

    def test_valid_name(self) -> None:
        """A clean lowercase name passes through."""
        result = validate_tag_name("groceries")
        assert result == "groceries"

    def test_valid_with_hyphen(self) -> None:
        """Hyphens in tag names are allowed."""
        result = validate_tag_name("take-out")
        assert result == "take-out"

    def test_valid_with_underscore(self) -> None:
        """Underscores in tag names are allowed."""
        result = validate_tag_name("monthly_bill")
        assert result == "monthly_bill"

    def test_valid_with_numbers(self) -> None:
        """Numbers in tag names are allowed."""
        result = validate_tag_name("2025-expense")
        assert result == "2025-expense"
