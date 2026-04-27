from __future__ import annotations

import math
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Label,
    Select,
    Static,
    Footer
)

from osrs_console.utils.api import PlayerData, SKILLS
from osrs_console.utils.calc import (
    CalcSession,
    TrainingAction,
    ActionResult,
    calculate,
    load_actions
)
from osrs_console.widgets.charts import LabelCard


SUPPORTED_SKILLS = [s for s in SKILLS if s != "Overall"]


class CalculatorScreen(Screen):

    BINDINGS = [
        ("escape", "go_back", "Back"),
        ("r", "calculate", "Calculate"),
        ("shift+1", "open_skills", "⚔️ View skills"),
        ("shift+3", "open_wealth", "💰 Wealth"),
        ("shift+4", "open_analytics", "📊 Analytics"),
        ("shift+5", "export_to_prices", "🔍 Export → GE Prices"),
        ("ctrl+h", "open_home", "🏚️ Home"),
    ]

    DEFAULT_CSS = """
    CalculatorScreen {
        layout: vertical;
    }
    #calc-header {
        height: auto;
        background: $panel;
        border-bottom: tall $panel-darken-2;
        padding: 0 2;
        layout: horizontal;
    }
    #calc-header > * {
        margin-right: 2;
    }
    #skill-select { width: 22; }
    .xp-group { width: 30; height: auto; }
    .xp-group Label {
        margin-bottom: 0;
        color: $text-muted;
    }
    .xp-row { layout: horizontal; height: auto; }
    .xp-label { layout: horizontal; }
    .xp-label-fields { layout: horizontal; width: 30; height: auto; }
    .xp-label-fields .field { width: 13; content-align: center middle; text-align: center; }
    .xp-label-fields .spacer { width: 3; content-align: center middle; text-align: center; }
    .xp-row Input { width: 13; }
    .xp-row Label { width: 3; content-align: center middle; }
    #calc-body {
        height: 1fr;
        layout: horizontal;
    }
    #actions-col {
        width: 36;
        border-right: tall $panel-darken-2;
    }
    #actions-title {
        background: $panel-darken-1;
        padding: 0 1;
        text-style: bold;
        height: 1;
    }
    #actions-scroll {
        height: 1fr;
    }
    .action-check { margin: 0 1; }
    #results-col {
        width: 1fr;
    }
    #results-title {
        background: $panel-darken-1;
        padding: 0 1;
        text-style: bold;
        height: 1;
    }
    #results-table { height: 1fr; width: 100%; }
    #calc-footer {
        height: 4;
        background: $panel;
        border-top: tall $panel-darken-2;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
    }
    #calc-footer Button {
        height: auto; 
    }
    #calc-btn { margin-right: 2; }
    #export-btn { }
    #calc-status { color: $text-muted; margin-left: 2; }
    #dock {
        height: auto;
        dock: bottom;
        layout: vertical; 
    }
    """

    def __init__(
        self,
        player: Optional[PlayerData] = None,
        initial_skill: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._player = player
        self._initial_skill = initial_skill or "Woodcutting"
        self._all_actions: list[TrainingAction] = []
        self._last_results: list[ActionResult] = []
        self._last_session: Optional[CalcSession] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="calc-header"):
            with Vertical(classes="xp-group"):
                yield Label("Skill")
                yield Select(
                    [(s.title(), s) for s in SUPPORTED_SKILLS],
                    value=self._initial_skill,
                    id="skill-select"
                )
            with Vertical(classes="xp-group"):
                yield Label("Start")
                with Horizontal(classes="xp-row"):
                    yield Input("0", id="start-xp", placeholder="XP")
                    yield Label(" | ")
                    yield Input("1", id="start-lvl", placeholder="LVL")
                with Horizontal(classes="xp-label-fields"):
                    yield Label("XP", classes="field")
                    yield Label("", classes="spacer")
                    yield Label("LVL", classes="field")

            with Vertical(classes="xp-group"):
                yield Label("Target")
                with Horizontal(classes="xp-row"):
                    yield Input("0", id="target-xp", placeholder="XP")
                    yield Label(" | ")
                    yield Input("1", id="target-lvl", placeholder="LVL")
                with Horizontal(classes="xp-label-fields"):
                    yield Label("XP", classes="field")
                    yield Label("", classes="spacer")
                    yield Label("LVL", classes="field")

            with Vertical(classes="xp-group"):
                yield Label("0 Actions selected", id="actions-counter")
                yield Static(id="agg-card-slot")

        with Horizontal(id="calc-body"):
            with Vertical(id="actions-col"):
                yield Static("Training Methods", id="actions-title")
                with ScrollableContainer(id="actions-scroll"):
                    pass

            with Vertical(id="results-col"):
                yield Static("Results", id="results-title")
                yield DataTable(id="results-table", zebra_stripes=True)
        with Vertical(id="dock"):
            with Horizontal(id="calc-footer"):
                yield Button("Calculate  [R key]", variant="primary", id="calc-btn")
                yield Button("Export to GE Prices →", id="export-btn")
                yield Label("", id="calc-status")

            yield Footer()

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#results-table", DataTable)
        table.add_columns("Method", "Actions Needed", "Total XP", "Inputs / action", "Tools", "Outputs / action")

        if self._player:
            skill = self._player.skills.get(self._initial_skill)
            if skill:
                self._set_start_xp(skill.xp)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "skill-select":
            skill = str(event.value)
            self._load_skill(skill)
            if self._player:
                s = self._player.skills.get(skill)
                if s:
                    self._set_start_xp(s.xp)

    def _load_skill(self, skill: str) -> None:
        self._all_actions = load_actions(skill)
        scroll = self.query_one("#actions-scroll", ScrollableContainer)
        scroll.remove_children()
        for action in sorted(self._all_actions, key=lambda a: a.level_req):
            lbl = f"[{action.level_req}] {action.name}"
            scroll.mount(Checkbox(lbl, id=f"action-{action.name.lower().replace(' ', '-')}", classes="action-check"))
        aggslot = self.query_one("#agg-card-slot", Static)
        aggslot.remove_children()

    def on_input_changed(self, event: Input.Changed) -> None:
        iid = event.input.id
        try:
            val = int(event.value.replace(",",""))
        except ValueError:
            return
        
        self._sync_fields(iid, val)

    def _sync_fields(self, changed_id: str, val: int) -> None:
        inputs = [
            "start-xp",
            "start-lvl",
            "target-xp",
            "target-lvl",
        ]
        fields_updated = [
            self.query_one("#start-lvl", Input),
            self.query_one("#start-xp", Input),
            self.query_one("#target-lvl", Input),
            self.query_one("#target-xp", Input),
        ]

        if getattr(self, "_syncing", False):
            return
        if changed_id not in inputs:
            return
        self._syncing = True
        linked_field = fields_updated[inputs.index(changed_id)]
        try:
            if changed_id in ("start-xp", "target-xp"):
                linkedval = f"{CalcSession._xp_to_level(val)}"
            elif changed_id in ("start-lvl", "target-lvl"):
                linkedval = f"{CalcSession._level_to_xp(val)}"
            with linked_field.prevent(Input.Changed):
                linked_field.value = linkedval

        finally:
            self._syncing = False

    def _set_start_xp(self, xp: int) -> None:
        start_xp = self.query_one("#start-xp", Input)
        start_lvl = self.query_one("#start-lvl", Input)
        with start_xp.prevent(Input.Changed):
            start_xp.value = str(xp)
        with start_lvl.prevent(Input.Changed):
            start_lvl.value = str(CalcSession._xp_to_level(xp))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "calc-btn":
            self.action_calculate()
        elif event.button.id == "export-btn":
            self.action_export_to_prices()

    def action_calculate(self) -> None:
        try:
            start_xp = int(self.query_one("#start-xp", Input).value.replace(",","") or 0)
            target_xp = int(self.query_one("#target-xp", Input).value .replace(",","")or 0)
        except ValueError:
            self._set_status("⚠ Invalid XP values.")
            return
        
        skill = str(self.query_one("#skill-select", Select).value)

        if target_xp <= start_xp:
            self._set_status("⚠ Target XP must be greater than Start XP.")
            return
        
        selected = [
            cb.label.plain.split("] ", 1)[-1].replace("-", " ").capitalize()
            for cb in self.query(".action-check")
            if isinstance(cb, Checkbox) and cb.value
        ]

        if not selected:
            self._set_status("⚠ Select at least one training method.")
            return
        
        session = CalcSession(
            skill=skill,
            start_xp=start_xp,
            target_xp=target_xp,
            selected_actions=selected
        )

        results, aggregates = calculate(session, self._all_actions)
        total_xp_per, agg_needed = aggregates
        session.results = results
        session.total_xp_per = total_xp_per
        session.total_actions = agg_needed
        self._last_session = session
        self._last_results = results

        self._populate_results(results, session)
        self.query_one("#export-btn", Button).disabled = len(results) == 0

    def _populate_results(self, results: list[ActionResult], session: CalcSession) -> None:
        table = self.query_one("#results-table", DataTable)
        table.clear()

        if not results:
            self._set_status("No results.")
            return
        
        for r in results:
            mats = ", ".join(
                f"{int(m.qty)}x {m.name}" for m in r.material_totals()
            )
            tools = ", ".join(
                f"{int(t.qty)}x {t.name} [lv. {t.level_req}]" 
                for t in r.action.skill_tools()
            )
            inputs_per = ", ".join(
                f"{m.qty}x {m.name}" for m in r.action.input_materials()
            )
            outputs_per = ", ".join(
                f"{o.qty}x {o.name} [{o.rarity * 100}%]" for o in r.action.output_materials()
            )

            table.add_row(
                r.action.name,
                f"{r.actions_needed:,}",
                f"{r.total_xp:,.0f}",
                inputs_per,
                tools,
                outputs_per
            )

            aggslot = self.query_one("#agg-card-slot", Static)
            aggslot.remove_children()
            labels = [
                (
                    f"[b]Action cycles needed[/b]",
                    None,
                ),
                (
                    f"[i]{session.total_actions:,}[/i] [b]@ {session.total_xp_per:,} XP/Cy.[/b]",
                    None,
                ),
            ]
            aggslot.mount(
                LabelCard(*labels)
            )
            self.query_one("#actions-counter", Label).update(
                f"{len(session.results)} Actions selected"
            )

            xp_gap = session.xp_needed
            self._set_status(
                f"XP needed: {xp_gap:,}  |  "
                f"Lvl {session.start_level} → {session.target_level}"
            )
    
    def _set_status(self, msg: str) -> None:
        self.query_one("#calc-status", Label).update(msg)

    def action_export_to_prices(self) -> None:
        try:
            from osrs_console.screens.prices import GEPricesScreen
        except ImportError:
            self._set_status("⚠ GE Prices screen not implemented.")
            return
        if not self._last_session:
            self.app.push_screen(GEPricesScreen())
        else:
            self.app.push_screen(GEPricesScreen(session=self._last_session))

    def action_open_wealth(self) -> None:
        try:
            from osrs_console.screens.wealth import WealthScreen
            self.app.push_screen(WealthScreen(player=self._player))
        except ImportError:
            self._set_status("⚠ WealthScreen not implemented.")
            return
    
    def action_open_analytics(self) -> None:
        user = getattr(self._player, "username", None)
        try:
            from osrs_console.screens.analytics import AnalyticsScreen
            self.app.push_screen(AnalyticsScreen(username=user))
        except ImportError:
            self._set_status("⚠ AnalyticsScreen not implemented.")
            return
        
    def action_open_skills(self) -> None:
        if not self._player:
            self._set_status("⚠ No character skill data currently loaded... [enter your RSN at the Home screen]")
            return
        username = self._player.username
        acctype = self._player.account_type
        from osrs_console.screens.skills import SkillsScreen
        self.app.push_screen(SkillsScreen(username, acctype))

    def action_go_back(self) -> None:
        self.app.pop_screen()