"""Unit tests for REPL transaction entry (contract e)."""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from pyfintracker.models import Transaction

# Make stdin.isatty() return True for all tests except TestReplTTY
# so the TTY guard doesn't block ordinary tests.


@pytest.fixture(autouse=True)
def _ensure_tty(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Ensure stdin appears as TTY for non-TTY tests."""
    if request.cls is not TestReplTTY:
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)


@pytest.mark.unit
class TestReplCollectsInputs:
    """T-5.1: repl_add_postings returns Transaction + Postings on valid input."""

    def test_balanced_two_postings(self) -> None:
        """Two postings that sum to zero."""
        from pyfintracker.cli import repl_add_postings

        console = MagicMock()
        replies = iter(
            [
                "2024-01-15",  # date
                "Grocery run",  # description
                "COP",  # currency
                "Expenses:Food",  # account 1
                "50000",  # amount 1
                "Assets:Cash",  # account 2
                "-50000",  # amount 2
            ]
        )

        txn, postings = repl_add_postings(console, lambda *a, **kw: next(replies))

        assert isinstance(txn, Transaction)
        assert txn.date == date(2024, 1, 15)
        assert txn.description == "Grocery run"
        assert txn.currency == "COP"
        assert len(postings) == 2
        assert sum(p.amount for p in postings) == Decimal("0")

    def test_three_postings(self) -> None:
        """Three postings that sum to zero (split payment)."""
        from pyfintracker.cli import repl_add_postings

        console = MagicMock()
        replies = iter(
            [
                "2024-06-01",
                "Split payment",
                "COP",
                "Expenses:Food",
                "30000",
                "Expenses:Transport",
                "20000",
                "Assets:Cash",
                "-50000",
            ]
        )

        txn, postings = repl_add_postings(console, lambda *a, **kw: next(replies))

        assert len(postings) == 3
        assert sum(p.amount for p in postings) == Decimal("0")
        assert txn.date == date(2024, 6, 1)


@pytest.mark.unit
class TestReplPromptOrder:
    """T-5.2: REPL prompts in correct order."""

    def test_prompt_order(self) -> None:
        """Prompts appear in Date → Description → Currency → Account → Amount order."""
        from pyfintracker.cli import repl_add_postings

        console = MagicMock()
        prompts_called: list[str] = []

        prompt_responses = [
            ("Date (YYYY-MM-DD)", "2024-01-15"),
            ("Description", "Test"),
            ("Currency", "COP"),
            ("Account", "Expenses:Food"),
            ("Amount", "50000"),
            ("Account", "Assets:Cash"),
            ("Amount", "-50000"),
        ]
        response_index = [0]

        def smart_prompt(text: str, default: str = "") -> str:
            prompts_called.append(text)
            _expected_text, response = prompt_responses[response_index[0]]
            response_index[0] += 1
            return response

        repl_add_postings(console, smart_prompt)

        assert len(prompts_called) >= 5
        assert "date" in prompts_called[0].lower()
        assert "description" in prompts_called[1].lower()
        assert "currency" in prompts_called[2].lower()
        assert "account" in prompts_called[3].lower()
        assert "amount" in prompts_called[4].lower()


@pytest.mark.unit
class TestReplAbort:
    """T-5.3: :abort command raises SystemExit(130)."""

    def test_abort_at_account_prompt(self) -> None:
        """Entering :abort at account prompt raises SystemExit(130)."""
        from pyfintracker.cli import repl_add_postings

        console = MagicMock()
        replies = iter(
            [
                "2024-01-15",
                "Test",
                "COP",
                ":abort",
            ]
        )

        with pytest.raises(SystemExit) as exc:
            repl_add_postings(console, lambda *a, **kw: next(replies))
        assert exc.value.code == 130

    def test_abort_at_amount_prompt(self) -> None:
        """Entering :abort at amount prompt raises SystemExit(130)."""
        from pyfintracker.cli import repl_add_postings

        console = MagicMock()
        replies = iter(
            [
                "2024-01-15",
                "Test",
                "COP",
                "Expenses:Food",
                ":abort",
            ]
        )

        with pytest.raises(SystemExit) as exc:
            repl_add_postings(console, lambda *a, **kw: next(replies))
        assert exc.value.code == 130


@pytest.mark.unit
class TestReplCtrlC:
    """T-5.4: CTRL-C handler."""

    def test_ctrl_c_confirms_discard(self) -> None:
        """CTRL-C then 'y' raises SystemExit(130)."""
        from pyfintracker.cli import repl_add_postings

        console = MagicMock()
        call_count = [0]

        def prompt_fn(text: str, default: str = "") -> str:
            call_count[0] += 1
            if call_count[0] == 4:  # first Account prompt: CTRL-C
                raise KeyboardInterrupt()
            if call_count[0] == 5:  # confirmation prompt
                return "y"  # discard
            responses = {
                1: "2024-01-15",
                2: "Test",
                3: "COP",
            }
            return responses.get(call_count[0], "")

        with pytest.raises(SystemExit) as exc:
            repl_add_postings(console, prompt_fn)
        assert exc.value.code == 130

    def test_ctrl_c_continues_on_no(self) -> None:
        """CTRL-C then 'n' continues and completes successfully."""
        from pyfintracker.cli import repl_add_postings

        console = MagicMock()
        call_count = [0]

        def prompt_fn(text: str, default: str = "") -> str:
            call_count[0] += 1
            if call_count[0] == 4:  # first Account: CTRL-C
                raise KeyboardInterrupt()
            if call_count[0] == 5:  # confirmation
                return "n"  # continue, retries the account prompt
            responses = {
                1: "2024-01-15",
                2: "Test",
                3: "COP",
                6: "Expenses:Food",
                7: "50000",
                8: "Assets:Cash",
                9: "-50000",
            }
            return responses.get(call_count[0], "")

        _txn, postings = repl_add_postings(console, prompt_fn)
        assert len(postings) == 2
        assert sum(p.amount for p in postings) == Decimal("0")


@pytest.mark.unit
class TestReplTTY:
    """T-5.5: TTY detection."""

    def test_repl_requires_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-TTY stdin raises ReplRequiresTTYError."""
        import sys

        from pyfintracker.cli import repl_add_postings
        from pyfintracker.exceptions import ReplRequiresTTYError

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

        with pytest.raises(ReplRequiresTTYError):
            repl_add_postings(MagicMock(), lambda *a, **kw: "")

    def test_repl_works_in_tty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TTY stdin allows the REPL to proceed."""
        import sys

        from pyfintracker.cli import repl_add_postings

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

        console = MagicMock()
        replies = iter(
            [
                "2024-01-15",
                "Test",
                "COP",
                "Expenses:Food",
                "50000",
                "Assets:Cash",
                "-50000",
            ]
        )

        _txn, postings = repl_add_postings(console, lambda *a, **kw: next(replies))
        assert len(postings) == 2


@pytest.mark.unit
class TestReplParseAmount:
    """T-5.7: _parse_repl_amount strips commas and validates."""

    def test_parses_with_commas(self) -> None:
        """Comma-formatted number parses correctly."""
        from pyfintracker.cli import _parse_repl_amount

        assert _parse_repl_amount("50,000") == Decimal("50000")

    def test_parses_negative(self) -> None:
        """Negative numbers with commas parse correctly."""
        from pyfintracker.cli import _parse_repl_amount

        assert _parse_repl_amount("-50,000") == Decimal("-50000")

    def test_rejects_zero(self) -> None:
        """Zero raises InvalidAmount."""
        from pyfintracker.cli import _parse_repl_amount
        from pyfintracker.exceptions import InvalidAmount

        with pytest.raises(InvalidAmount):
            _parse_repl_amount("0")

    def test_rejects_non_numeric(self) -> None:
        """Non-numeric input raises InvalidAmount."""
        from pyfintracker.cli import _parse_repl_amount
        from pyfintracker.exceptions import InvalidAmount

        with pytest.raises(InvalidAmount):
            _parse_repl_amount("abc")


@pytest.mark.unit
class TestSuggestAccounts:
    """T-5.10: Account fuzzy match suggestion."""

    def test_exact_match(self) -> None:
        """Exact match returns the account."""
        from pyfintracker.cli import _suggest_accounts

        accounts = ["Assets:Cash", "Expenses:Food", "Income:Salary"]
        assert _suggest_accounts("Assets:Cash", accounts) == ["Assets:Cash"]

    def test_fuzzy(self) -> None:
        """Fuzzy match returns containing accounts (case-insensitive)."""
        from pyfintracker.cli import _suggest_accounts

        accounts = ["Assets:Cash", "Assets:Bank", "Expenses:Food"]
        result = _suggest_accounts("cash", accounts)
        assert "Assets:Cash" in result
        assert len(result) <= 5

    def test_no_match_returns_empty(self) -> None:
        """No match returns empty list."""
        from pyfintracker.cli import _suggest_accounts

        assert _suggest_accounts("zzzz", ["Assets:Cash"]) == []

    def test_empty_account_list(self) -> None:
        """Empty available list returns empty result."""
        from pyfintracker.cli import _suggest_accounts

        assert _suggest_accounts("cash", []) == []


class TestReplResolve:
    """T-5.11: REPL retries on unknown account (unit-level)."""

    def test_resolve_account_ok(self) -> None:
        """resolve_account callback maps name to ID."""
        from pyfintracker.cli import repl_add_postings

        console = MagicMock()
        replies = iter(
            [
                "2024-01-15",
                "Test",
                "COP",
                "Expenses:Food",
                "50000",
                "Assets:Cash",
                "-50000",
            ]
        )

        account_ids = {"Expenses:Food": 1, "Assets:Cash": 2}

        def resolve(name: str) -> int | None:
            return account_ids.get(name)

        _txn, postings = repl_add_postings(console, lambda *a, **kw: next(replies), resolve)
        assert len(postings) == 2
        assert postings[0].account_id == 1
        assert postings[1].account_id == 2

    def test_retries_on_unknown(self) -> None:
        """Unknown account retries after error."""
        from pyfintracker.cli import repl_add_postings

        console = MagicMock()
        call_count = [0]
        account_ids = {"Expenses:Food": 1, "Assets:Cash": 2}

        def resolve(name: str) -> int | None:
            return account_ids.get(name)

        # REPL prompts: Account → Amount → (resolve returns None → continue)
        # → Account → Amount...
        # So after "Expenses:Nope" (Account), we still need a valid Amount
        # before the retry picks up the next Account.
        def prompt_fn(text: str, default: str = "") -> str:
            call_count[0] += 1
            responses = {
                1: "2024-01-15",
                2: "Test",
                3: "COP",
                4: "Expenses:Nope",  # Account → unknown
                5: "50000",  # Amount (still collected before resolve happens)
                6: "Expenses:Food",  # Account → known (retry)
                7: "50000",  # Amount
                8: "Assets:Cash",  # Account
                9: "-50000",  # Amount
            }
            return responses.get(call_count[0], "")

        _txn, postings = repl_add_postings(console, prompt_fn, resolve)
        assert len(postings) == 2
        assert postings[0].account_id == 1
