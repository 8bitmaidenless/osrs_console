from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from osrs_console.screens.home import HomeScreen


class OSRSConsole(App):
    TITLE = "OSRS Console"
    SUB_TITLE = "Old School Runescape - Terminal Interface Console"

    CSS = """
    $accent: #e8c253;
    $accent-darken-1: #b8972f;
    $contrast: #1a1209;
    
    Screen {
        background: $surface;
    }
    Header {
        background: #1a1209;
        color: $accent;
    }
    Footer {
        background: $contrast;
        color: $accent;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
    ]

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())


def main() -> None:
    OSRSConsole().run()


if __name__ == "__main__":
    main()