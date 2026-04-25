from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Rule, Select, Static, Footer


ACCOUNT_TYPES = [
    ("Normal", "normal"),
    ("Ironman", "ironman"),
    ("Hardcore Ironman", "hardcore"),
    ("Ultimate Ironman", "ultimate"),
]


class HomeScreen(Screen):

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("c", "open_calculator", "Skill Calc."),
        ("w", "open_wealth", "Wealth / GE"),
        ("f", "open_analytics", "$ Analytics"),
    ]

    DEFAULT_CSS = """
    HomeScreen {
        align: center middle;
    }
    #home-box {
        width: 64;
        height: auto; 
        border: double $accent;
        padding: 2 4;
        background: $panel;
    }
    #home-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 0;
    }
    #home-subtitle {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }
    #username-input { margin-bottom: 1; }
    #account-select { margin-bottom: 1; }
    #lookup-btn { width: 100%; margin-bottom: 1; }
    .nav-section-label {
        color: $text-muted; 
        text-align: center;
        margin-top: 1;
        margin-bottom: 1;
    }
    .nav-btn { width: 100%; margin-bottom: 1; }
    #error-label {
        color: $error;
        text-align: center;
        margin-top: 1;
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        with Static(id="home-box"):
            yield Label("⚔  OSRS TUI Console  ⚔", id="home-title")
            yield Label("Old School Runescape - Terminal Interface Console", id="home-subtitle")
            yield Rule()

            yield Input(placeholder="Enter RSN (e.g. Zesima)", id="username-input")
            yield Select(
                [(label, value) for label, value in ACCOUNT_TYPES],
                value="normal",
                id="account-select"
            )
            yield Button("🔍 Look Up Player Skills", variant="primary", id="lookup-btn")

            yield Rule()
            yield Label("--- Tools ---", classes="nav-section-label")

            yield Button("🧮 Skill Calculator", classes="nav-btn", id="nav-calc")
            yield Button("💰 Wealth & GE Tracker", classes="nav-btn", id="nav-wealth")
            yield Button("📊 Financial Analytics", classes="nav-btn", id="nav-analytics")

            yield Label("", id="error-label")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        err = self.query_one("#error-label", Label)
        err.display = False
        dispatch = {
            "lookup-btn": self._do_lookup(),
            "nav-calc": self.action_open_calculator,
            "nav-wealth" : self.action_open_wealth,
            "nav-analytics": self.action_open_analytics
        }
        handler = dispatch.get(bid, None)
        if handler:
            handler()
        
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._do_lookup()

    def _do_lookup(self) -> None:
        username = self.query_one("#username-input", Input).value.strip()
        account_type = str(self.query_one("#account-select", Select).value)
        err = self.query_one("#error-label", Label)

        if not username:
            err.update("⚠ Please enter a username.")
            err.display = True
            return
        
        err.display = False
        try:
            from osrs_console.screens.skills import SkillsScreen
            self.app.push_screen(SkillsScreen(username=username, account_type=account_type))
        except ImportError:
            err.update("⚠ Skills screen not implemented.")
            err.display = True
            return
        
    def action_open_calculator(self) -> None:
        err = self.query_one("#error-label", Label)
        err.display = False
        try:
            from osrs_console.screens.calculator import CalculatorScreen
            self.app.push_screen(CalculatorScreen())
        except ImportError:
            err.update("⚠ Skill Calculator not implemented.")
            err.display = True
            return
        
    def action_open_wealth(self) -> None:
        err = self.query_one("#error-label", Label)
        err.display = False
        try:
            from osrs_console.screens.wealth import WealthScreen
            self.app.push_screen(WealthScreen())
        except ImportError:
            err.update("⚠ Wealth & GE Tracker not implemented.")
            err.display = True
            return
        
    def action_open_analytics(self) -> None:
        err = self.query_one("#error-label", Label)
        err.display = False
        try:
            from osrs_console.screens.analytics import AnalyticsScreen
            self.app.push_screen(AnalyticsScreen())
        except ImportError:
            err.update("⚠ Financial Analytics not implemented.")
            err.display = True
            return
        
    
