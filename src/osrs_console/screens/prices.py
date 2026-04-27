from __future__ import annotations

import asyncio
import math
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    LoadingIndicator,
    Static,
    TabbedContent,
    TabPane,
    Footer
)

from osrs_console.utils import db
from osrs_console.utils.ge_api import (
    GEAPIError,
    GEItem,
    GEPrice,
    fetch_prices_bulk,
    search_items,
)
try:
    from osrs_console.utils.calc import CalcSession
except ImportError:
    CalcSession = None


def _gp(n: Optional[int], fallback: str = "-") -> str:
    if n is None:
        return fallback
    if abs(n) >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,}"


def _signed_gp(n: int) -> str:
    sign = "▲ +" if n > 0 else ("▼ " if n < 0 else "↔ ")
    return f"{sign}{_gp(abs(n))}"


class GEPricesScreen(Screen):

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("ctrl+r", "refresh_prices", "📈 Refresh"),
        ("ctrl+s", "save_lists", "💾 Lists"),
        ("shift+1", "open_skills", "⚔️ Skills"),
        ("shift+2", "open_calculator", "🧮 XP Calc"),
        ("shift+3", "open_wealth", "💰 Wealth"),
        ("shift+4", "open_analytics", "📊 Analytics"),
        ("ctrl+h", "open_home", "🏚️ Home"),
    ]

    DEFAULT_CSS = """
    GEPricesScreen { layout: vertical; }
    
    #ge-p-toolbar {
        height: 3;
        background: $panel;
        border-bottom: tall $accent-darken-1;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
    }
    #ge-p-title { color: $accent; text-style: bold; width: 22; }
    #ge-p-search { width: 1fr; margin-right: 1; }
    #ge-p-search-btn { margin-right: 1; }
    
    TabbedContent { height: 1fr; }
    
    #lookup-body { height: 1fr; layout: vertical; }
    #search-status { color: $text-muted; height: 1; padding: 0 1; }
    #search-loading { align: center middle; height: 5; display: none; }
    #results-table { height: 1fr; }
    #lookup-actions {
        height: 3;
        layout: horizontal;
        align: left middle;
        padding: 0 1;
        background: $panel;
        border-top: tall $panel-darken-2;
    }
    #lookup-actions Button { margin-right: 1; }
    
    #saved-body { height: 1fr; layout: vertical; }
    #saved-table { height: 1fr; }
    #saved-actions {
        height: 3;
        layout: horizontal;
        align: left middle;
        padding: 0 1;
        background: $panel;
        border-top: tall $panel-darken-2;
    }
    #saved-actions Button { margin-right: 1; }
    
    #lists-body { height: 1fr; layout: vertical; }
    #lists-upper {
        height: 1fr;
        layout: horizontal;
    }
    
    .list-panel {
        width: 1fr;
        layout: vertical;
        border: round $panel-darken-2;
        margin: 1;
    }
    .list-panel-title {
        height: 1;
        background: $panel-darken-1;
        padding: 0 1;
        text-style: bold;
    }
    .expense-title { color: $error; }
    .sale-title { color: ansi_green; }
    .list-table { height: 1fr; }
    .list-actions {
        height: 3;
        layout: horizontal;
        align: left middle;
        padding: 0 1;
        background: $panel;
        border-top: tall $panel-darken-2;
    }
    .list-actions Button { margin-right: 1; }
    
    #summary-bar {
        height: 4;
        background: $panel;
        border-top: tall $accent-darken-1;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
    }
    .summary-card {
        width: 1fr;
        height: 3;
        border: round $panel-darken-2;
        padding: 0 1;
        margin-right: 1; 
    }
    .summary-label { color: $text-muted; }
    .summary-value  { text-style: bold; color: $accent; }
    .profit { color: ansi_green; text-style: bold; }
    .loss { color: $error; text-style: bold; }
    .neutral { color: $text-muted; text-style: bold; }
    
    #ge-p-footer {
        height: 3;
        background: $panel;
        border-top: inner $accent-darken-1;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
    }
    #ge-p-status { color: $accent; margin-left: 2; }
    #ge-p-dock {
        layout: vertical;
        dock: bottom;
        height: auto;
    }
    """

    def __init__(
        self,
        session: Optional["CalcSession"] = None,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._session = session

        self._expense_items: list[dict] = []
        self._sale_items: list[dict] = []

        self._search_results: list[GEItem] = []

        self._price_cache: dict[int, GEPrice] = {}

    def compose(self) -> ComposeResult:
        with Horizontal(id="ge-p-toolbar"):
            yield Label("🏦 GE Prices", id="ge-p-title")
            yield Input(placeholder="Search item name...", id="ge-p-search")
            yield Button("Search", variant="primary", id="ge-p-search-btn")

        with TabbedContent(id="ge-p-tabs"):
            with TabPane("🔍 Item Lookup", id="tab-lookup"):
                yield from self._compose_lookup_tab()
            with TabPane("* Saved Items", id="tab-saved"):
                yield from self._compose_saved_tab()
            with TabPane("📋 Price Lists", id="tab-lists"):
                yield from self._compose_lists_tab()

        with Vertical(id="ge-p-dock"):
            with Horizontal(id="ge-p-footer"):
                yield Button("← Back", id="back-btn")
                yield Label("", id="ge-p-status", markup=True)

            yield Footer()

    def _compose_lookup_tab(self) -> ComposeResult:
        with Vertical(id="lookup-body"):
            with Container(id="search-loading"):
                yield LoadingIndicator()
            yield Label("Enter a search term above.", id="search-status")
            yield DataTable(id="results-table", zebra_stripes=True, cursor_type="row")
            with Horizontal(id="lookup-actions"):
                yield Button("* Tag Item", id="btn-tag", disabled=True)
                yield Button("+ Expense", id="btn-add-expense", disabled=True, variant="error")
                yield Button("+ Sale", id="btn-add-sale", disabled=True, variant="success")
                yield Button("🏷️ Fetch Price", id="btn-fetch-price", disabled=True)

    def _compose_saved_tab(self) -> ComposeResult:
        with Vertical(id="saved-body"):
            yield DataTable(id="saved-table", zebra_stripes=True, cursor_type="row")
            with Horizontal(id="saved-actions"):
                yield Button("+ Expense", id="btn-saved-expense", disabled=True, variant="error")
                yield Button("+ Sale", id="btn-saved-sale", variant="success", disabled=True)
                yield Button("x Untag", id="btn-untag", disabled=True)

    def _compose_lists_tab(self) -> ComposeResult:
        with Vertical(id="lists-body"):
            with Horizontal(id="lists-upper"):
                with Vertical(classes="list-panel"):
                    yield Static("💸 Expense List", classes="list-panel-title expense-title")
                    yield DataTable(
                        id="expense-table",
                        zebra_stripes=True,
                        cursor_type="row",
                        classes="list-table"
                    )
                    with Horizontal(classes="list-actions"):
                        yield Button("x Remove", id="btn-rm-expense", disabled=True)
                        yield Button("↩️ Refresh", id="btn-refresh-expense")
                
                with Vertical(classes="list-panel"):
                    yield Static("💰 Sale List", classes="list-panel-title sale-title")
                    yield DataTable(
                        id="sale-table",
                        zebra_stripes=True,
                        cursor_type="row",
                        classes="list-table"
                    )
                    with Horizontal(classes="list-actions"):
                        yield Button("x Remove", id="btn-rm-sale", disabled=True)
                        yield Button("↩️ Refresh", id="btn-refresh-sale")

            with Horizontal(id="summary-bar"):
                with Vertical()