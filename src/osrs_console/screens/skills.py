from __future__ import annotations

# from rich.padding import Padding
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Label, LoadingIndicator, Static, Footer

from osrs_console.utils.api import APIError, PlayerData, fetch_player
from osrs_console.widgets.stats import PlayerHeader, SkillsTable, SkillBars


class SkillsScreen(Screen):
    
    DEFAULT_CSS = """
    SkillsScreen {
        layout: vertical;
    }
    #loading-container {
        align: center middle;
        height: 1fr;
    }
    #error-container {
        align: center middle;
        height: 1fr;
    }
    #error-msg {
        color: $error;
        text-align: center;
    }
    #skills-body {
        height: 1fr;
        display: none;
    }
    #skills-col {
        width: 2fr;
    }
    #bars-col {
        width: 1fr;
        border-left: tall $panel-darken-2;
        overflow-y: auto;
    }
    #dock {
        height: auto;
        layout: vertical;
        dock: bottom;
    }
    """

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("r", "reload", "Reload"),
        ("shift+2", "open_calculator", "🧮 XP Calc"),
        ("shift+3", "open_wealth", "💰 Wealth"),
        ("shift+4", "open_analytics", "📊 Analytics"),
        ("shift+5", "open_prices", "🔍 GE Prices"),
        ("ctrl+h", "open_home", "🏚️ Home"),
    ]

    def __init__(self, username: str, account_type: str = "normal", **kwargs) -> None:
        super().__init__(**kwargs)
        self._username = username
        self._account_type = account_type
        self._player: PlayerData | None = None

    def compose(self) -> ComposeResult:
        with Container(id="loading-container"):
            yield LoadingIndicator()
            yield Label(f"Fetching data for '{self._username}'...")

        with Container(id="error-container"):
            yield Label("", id="error-msg")
            yield Label("Press [b]Esc[/b] to go back.", markup=True)

        with Horizontal(id="skills-body"):
            with Vertical(id="skills-col"):
                yield Static(id="player-header-slot")
                yield Static(id="skills-table-slot")
            with ScrollableContainer(id="bars-col"):
                yield Static(id="bars-slot")

        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#error-container").display = False
        self.query_one("#skills-body").display = False

        self.run_worker(self._load_player(), exclusive=True)

    async def _load_player(self) -> None:
        try:
            player = await fetch_player(self._username, self._account_type)
        except APIError as err:
            self._show_error(str(err))
            return
        except Exception as err:
            self._show_error(f"Unexpected error: {err}")
            return
        
        self._player = player
        self._populate(player)
    
    def _show_error(self, message: str) -> None:
        self.query_one("#loading-container").display = False
        self.query_one("#error-container").display = True
        self.query_one("#error-msg", Label).update(f"⚠ {message}")

    def _populate(self, player: PlayerData) -> None:
        self.query_one("#loading-container").display = False
        self.query_one("#skills-body").display = True

        header_slot = self.query_one("#player-header-slot", Static)
        header_slot.remove_children()
        header = PlayerHeader(player)
        header_slot.mount(header)

        table_slot = self.query_one("#skills-table-slot", Static)
        table_slot.remove_children()
        table_slot.mount(SkillsTable(player))

        bars_slot = self.query_one("#bars-slot", Static)
        bars_slot.remove_children()
        bars_slot.mount(SkillBars(player))

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_reload(self) -> None:
        self.query_one("#loading-container").display = True
        self.query_one("#error-container").display = False
        self.query_one("#skills-body").display = False
        self.run_worker(self._load_player(), exclusive=True)

    def action_open_calculator(self) -> None:
        try:
            from osrs_console.screens.calculator import CalculatorScreen
            self.app.push_screen(CalculatorScreen(player=self._player))
        except ImportError:
            self._show_error("⚠ CalculatorScreen not implemented.")
            return

    def action_open_wealth(self) -> None:
        try:
            from osrs_console.screens.wealth import WealthScreen
            self.app.push_screen(WealthScreen(player=self._player))
        except ImportError:
            self._show_error("⚠ WealthScreen not implemented.")
            return

    def action_open_analytics(self) -> None:
        user = getattr(self._player, "username", None)
        try:
            from osrs_console.screens.analytics import AnalyticsScreen
            self.app.push_screen(AnalyticsScreen(username=user))
        except ImportError:
            self._show_error("⚠ AnalyticsScreen not implemented.")
            return
        
    def action_open_prices(self) -> None:
        try:
            from osrs_console.screens.prices import GEPricesScreen
            self.app.push_screen(GEPricesScreen())
        except ImportError:
            self._show_error("⚠ GEPricesScreen not implemented.")
            return
        
        