"""Component test: TUI spike Dashboard screen via Textual Pilot.

Asserts the app boots, renders the Dashboard, key sections are visible,
and Vim-style keybindings do not crash.
"""

from __future__ import annotations

import html

import pytest

from pyfintracker.tui import FinanceApp


def _decode_svg(svg: str) -> str:
    """Decode HTML entities and normalize NBSP in Textual's SVG output."""
    return html.unescape(svg).replace("\xa0", " ")


@pytest.mark.component
async def test_dashboard_renders() -> None:
    """Pilot boots FinanceApp; verify all screen sections render."""
    app = FinanceApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        text = _decode_svg(app.export_screenshot())
        assert "Net worth" in text, "net-worth header missing"
        assert "Accounts" in text, "accounts table missing"
        assert "Monthly summary" in text, "summary card missing"
        assert "Recent transactions" in text, "txns list missing"
        assert "Salary July" in text, "mock txn data missing"


@pytest.mark.component
async def test_keybindings_do_not_crash() -> None:
    """Press each bound key; verify the app stays up."""
    app = FinanceApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("j", "k", "h", "l", "enter", "q")
        # 'q' triggers quit — the context manager closes cleanly
    # If we reach here, no crash
