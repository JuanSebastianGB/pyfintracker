"""Tests for DecimalAsText SQLAlchemy TypeDecorator.

Ensures Decimal values roundtrip byte-exactly through SQLite TEXT storage
without float conversion or precision loss.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pyfintracker.db import DecimalAsText


@pytest.mark.unit
class TestDecimalAsText:
    """T-3.1: DecimalAsText TypeDecorator preserves Decimal precision as TEXT."""

    def setup_method(self) -> None:
        """Create a fresh TypeDecorator instance per test."""
        self.type_ = DecimalAsText()

    def test_process_bind_param(self) -> None:
        """Decimal('123.45') → '123.45' (string)."""
        result = self.type_.process_bind_param(Decimal("123.45"), None)
        assert result == "123.45"
        assert isinstance(result, str)

    def test_process_result_value(self) -> None:
        """'123.45' → Decimal('123.45')."""
        result = self.type_.process_result_value("123.45", None)
        assert result == Decimal("123.45")
        assert isinstance(result, Decimal)

    def test_preserves_precision(self) -> None:
        """High-precision Decimal roundtrips byte-exact through bind/result."""
        original = Decimal("0.0012345678901234567890")
        bound = self.type_.process_bind_param(original, None)
        restored = self.type_.process_result_value(bound, None)
        assert restored == original
        # Check that the string repr is byte-exact (no silent truncation)
        assert str(restored) == str(original)

    def test_accepts_float_via_repr(self) -> None:
        """Float is coerced to string by caller — DecimalAsText only sees str.

        This is an acceptance test documenting that DecimalAsText itself
        does not reject float (it converts via str()). The upstream
        validate_amount function rejects float before it reaches here.
        """
        result = self.type_.process_bind_param(123.45, None)
        assert result is not None
        # str(123.45) is platform-dependent; just verify it's a string
        assert isinstance(result, str)

    def test_none_roundtrip(self) -> None:
        """None → None (both bind and result)."""
        assert self.type_.process_bind_param(None, None) is None
        assert self.type_.process_result_value(None, None) is None

    def test_negative(self) -> None:
        """Decimal('-50000') roundtrips preserving sign."""
        original = Decimal("-50000")
        bound = self.type_.process_bind_param(original, None)
        restored = self.type_.process_result_value(bound, None)
        assert restored == original
        assert restored < 0

    def test_zero(self) -> None:
        """Decimal('0') roundtrips."""
        original = Decimal("0")
        bound = self.type_.process_bind_param(original, None)
        restored = self.type_.process_result_value(bound, None)
        assert restored == original

    def test_large(self) -> None:
        """Large value with 2 decimal places roundtrips."""
        original = Decimal("999999999999999999.99")
        bound = self.type_.process_bind_param(original, None)
        restored = self.type_.process_result_value(bound, None)
        assert restored == original

    def test_cache_ok(self) -> None:
        """cache_ok is True (safe to cache since TEXT is immutable)."""
        assert self.type_.cache_ok is True

    def test_python_type_is_decimal(self) -> None:
        """python_type() returns Decimal."""
        assert self.type_.python_type() is Decimal

    def test_impl_is_text(self) -> None:
        """The underlying implementation type is Text."""
        from sqlalchemy.types import Text

        assert issubclass(DecimalAsText.impl, Text)
