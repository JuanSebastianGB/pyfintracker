"""Property-based tests for account name regex — T-2.13.

Uses hypothesis to generate valid account names and verify that
validate_account_name accepts them, and that any arbitrary string
either returns str or raises InvalidAccountName without crashing.
"""

from __future__ import annotations

import string

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pyfintracker.exceptions import InvalidAccountName
from pyfintracker.validation import validate_account_name

ROOTS = ["Assets", "Liabilities", "Equity", "Income", "Expenses"]

# Characters allowed in subname components — ASCII only because the regex
# uses [A-Z] / [a-z] / \w which only match ASCII in default re mode.
SUBNAME_CHARS: str = string.ascii_uppercase + string.ascii_lowercase + string.digits + "-_"


@pytest.mark.property
class TestAccountNameRegexProperty:
    """T-2.13: Property tests for ACCOUNT_NAME_RE."""

    @given(
        root=st.sampled_from(ROOTS),
        sub1=st.text(min_size=2, max_size=20, alphabet=SUBNAME_CHARS).filter(
            lambda s: s and s[0].isupper()
        ),
        sub2=st.one_of(
            st.none(),
            st.text(min_size=2, max_size=20, alphabet=SUBNAME_CHARS).filter(
                lambda s: s and s[0].isupper()
            ),
        ),
    )
    def test_valid_names_pass(self, root: str, sub1: str, sub2: str | None) -> None:
        """Generate valid account names in both 2-level and 3-level form."""
        name = f"{root}:{sub1}"
        if sub2 is not None:
            name = f"{name}:{sub2}"
        result = validate_account_name(name)
        assert result == name

    @given(name=st.text())
    def test_any_name_doesnt_crash(self, name: str) -> None:
        """For any string, validate_account_name either returns str or raises.

        This is a safety property — the function must never panic/crash
        on any input, regardless of validity.
        """
        try:
            result = validate_account_name(name)
            assert isinstance(result, str)
        except InvalidAccountName:
            pass
