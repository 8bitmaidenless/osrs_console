from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Label, ProgressBar, Static

from osrs_console.utils.api import PlayerData, SKILLS, SkillData


class PlayerHeader(Static):
    
    DEFAULT_CSS = """
    PlayerHeader {
        background: $panel;
        border: tall $accent;
        padding: 0 2;
        height: auto;
    }
    PlayerHeader .header-name {
        text-style: bold;
        color: $accent;
        content-align: center middle;
    }
    PlayerHeader .header-stats {
        color: $text-muted;
        content-align: center middle;
    }
    """

    def __init__(self, player: PlayerData, **kwargs) -> None:
        super().__init__(**kwargs)
        self._player = player

    def compose(self) -> ComposeResult:
        p = self._player
        account_badge = {
            "ironman": " [IM]",
            "hardcore": " [HC]",
            "ultimate": " [UIM]"
        }.get(p.account_type, "")

        yield Label(f"👤 {p.username}{account_badge}", classes="header-name")
        yield Label(
            f"⚔ Combat: {p.combat_level}   "
            f"📊 Total Level: {p.total_level:,}   "
            f"✨ Total XP: {p.total_xp:,}",
            classes="header-stats"
        )


class SkillsTable(Widget):
    DEFAULT_CSS = """
    SkillsTable {
        height: 1fr;
    }
    SkillsTable DataTable {
        height: 1fr;
    }
    """

    def __init__(self, player: PlayerData, **kwargs) -> None:
        super().__init__(**kwargs)
        self._player = player

    def compose(self) -> ComposeResult:
        yield DataTable(id="skills-dt", zebra_stripes=True, cursor_type="row")

    def on_mount(self) -> None:
        table = self.query_one("#skills-dt", DataTable)
        table.add_columns("", "Skill", "Level", "Rank", "XP", "XP to Next")

        for skill_name in SKILLS:
            skill = self._player.skills.get(skill_name)
            if skill is None:
                continue

            xp_next = (
                f"{skill.xp_to_next:,}"
                if skill.level < 99 and skill_name != "Overall"
                else ("MAX" if skill_name != "Overall" else "-")
            )
            table.add_row(
                skill.icon,
                skill.name.replace("_", " ").title(),
                str(skill.level),
                skill.rank_formatted,
                skill.xp_formatted,
                xp_next
            )


class SkillBars(Widget):
    _COMBAT_SKILLS = [
        "Attack",
        "Strength",
        "Defence",
        "Ranged",
        "Magic",
        "Prayer",
        "Hitpoints",
        "Slayer",
    ]

    _GATHERING_SKILLS = [
        "Mining",
        "Fishing",
        "Thieving",
        "Woodcutting"
    ]

    _PRODUCTION_SKILLS = [
        "Smithing",
        "Herblore",
        "Cooking",
        "Crafting",
        "Runecraft",
        "Farming",
        "Fletching",
    ]

    _OTHER_SKILLS = [
        "Agility",
        "Firemaking",
        "Slayer",
        "Hunter",
        "Construction",
        "Sailing",
    ]
    _SKILL_SETS = {
        "combat": _COMBAT_SKILLS,
        "gathering": _GATHERING_SKILLS,
        "production": _PRODUCTION_SKILLS,
        "other": _OTHER_SKILLS,
    }

    DEFAULT_CSS = """
    SkillBars {
        height: auto;
        padding: 0 1;
    }
    SkillBars Label {
        margin-top: 1;
    }
    SkillBars ProgressBar {
        width: 1fr;
    }
    """

    def __init__(self, player: PlayerData, **kwargs):
        super().__init__(**kwargs)
        self._player = player
        self._set_name: str = "combat"

    def compose(self) -> ComposeResult:
        skills = self._SKILL_SETS[self._set_name]
        for name in skills:
            skill = self._player.skills.get(name)
            if skill is None:
                continue
            pct = min(skill.level / 99, 1.0)
            icon = skill.icon
            yield Label(f"{icon} {name.title()}  lvl {skill.level}/99")
            bar = ProgressBar(total=100, show_eta=False, show_percentage=True)
            yield bar

            bar._osrs_pct = pct

    def on_mount(self) -> None:
        for bar in self.query(ProgressBar):
            pct = getattr(bar, "_osrs_pct", 0.0)
            bar.advance(pct * 100)

