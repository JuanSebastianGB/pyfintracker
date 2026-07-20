"""Textual TUI browser — full dashboard, drilldown, and search.

FinanceApp is the root Textual ``App``.  It handles gg/G (top/bottom) via a
manual prefix state machine because Textual 8.2.8 does not support multi-key
bindings.

The heavy lifting (screen classes, rendering, DB queries) lives in
``tui_screens.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding

from pyfintracker.tui_screens import DashboardScreen

# ── CSS ──────────────────────────────────────────────────────────────────────

CSS = """
DashboardScreen {
    background: #1a1b26;
}
"""


# ── app ──────────────────────────────────────────────────────────────────────


class FinanceApp(App[None]):
    """Full finance TUI browser — real DB data, Vim-style keys."""

    CSS = CSS
    TITLE = "pyfintracker"

    BINDINGS: ClassVar[
        list[Binding | tuple[str, str] | tuple[str, str, str]]
    ] = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "focus_previous", "Left", show=False),
        Binding("l", "focus_next", "Right", show=False),
        Binding("enter", "drilldown", "Drill down", show=False),
        Binding("q", "quit", "Quit"),
        Binding("slash", "focus_search", "Search", show=False),
    ]

    def __init__(self, db_path: str | None = None) -> None:
        super().__init__()
        self._db_path = db_path or str(
            Path("~/.local/share/fin/fin.db").expanduser()
        )
        # gg/G prefix state machine
        self._g_pending: bool = False

    def compose(self) -> ComposeResult:
        yield DashboardScreen(self._db_path)

    # ── gg / G (manual prefix state machine) ────────────────────────────

    def _clear_g_pending(self) -> None:
        """Timer callback — clear the gg prefix latch."""
        self._g_pending = False

    def key_g(self) -> None:
        """``g`` prefix: first press arms, second press fires gg → top."""
        if self._g_pending:
            self._g_pending = False
            self.query_one(DashboardScreen).go_top()
        else:
            self._g_pending = True
            self.set_timer(0.5, self._clear_g_pending)

    def key_G(self) -> None:  # noqa: N802 - Textual key handler is case-sensitive
        """``shift+g`` → go to bottom."""
        self._g_pending = False
        self.query_one(DashboardScreen).go_bottom()

    # ── delegated actions ───────────────────────────────────────────────

    def action_drilldown(self) -> None:
        """Forward Enter drilldown to the active DashboardScreen."""
        self.query_one(DashboardScreen).action_drilldown()

    def action_focus_search(self) -> None:
        """Forward ``/`` search-focus to the active DashboardScreen."""
        self.query_one(DashboardScreen).action_focus_search()


def run_tui(db_path: str | None = None) -> None:
    """Launch the Textual TUI browser.

    Creates a ``FinanceApp`` with the given DB path (defaults to
    ``~/.local/share/fin/fin.db``) and calls ``app.run()``.
    """
    FinanceApp(db_path).run()
