from __future__ import annotations

import math
from typing import Optional, Iterable, Tuple

from textual.app import ComposeResult, RenderResult
from textual.widget import Widget
from textual.widgets import Label, Static


class LabelCard(Static):
    DEFAULT_CSS = """
    LabelCard {
        border: tall $accent-darken-1;
        height: auto; 
        width: auto;
        background: $panel-darken-1;
        color: $accent;
        padding: 0 2;
    }
    .bold { text-style: bold; }
    .italic { text-style: italic; }
    .accent { color: $accent; }
    .muted { color: $text-muted; }
    .card-spacer { width: 3; }
    """
    def __init__(
        self,
        *labels: Iterable[Tuple[str, Optional[str]]],
        sep: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._labels = labels
        self._sep = sep
    
    def compose(self) -> ComposeResult:
        for label, cls in self._labels:
            # yield Label(label, markup=True,classes=)
            yield Label(label, markup=True, classes=cls)
            if self._sep:
                yield Label(self._sep, markup=True, classes="muted")
            
        


class StatCard(Static):
    DEFAULT_CSS = """
    StatCard {
        border: round $panel-darken-2;
        padding: 0 2;
        height: 100%;
        width: 1fr;
        margin: 0 1;
        background: $panel;
    }
    .card-title { color: $text-muted; }
    .card-value { text-style: bold; color: $accent; }
    .card-delta-pos { color: ansi_green; }
    .card-delta-neg { color: ansi_red; }
    .card-delta-neu { color: $text-muted; }
    """

    def __init__(
        self,
        title: str,
        value: str,
        delta: Optional[str] = None,
        delta_positive: Optional[bool] = None,
        **kwargs
    ) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._value = value
        self._delta = delta
        self._delta_positive = delta_positive

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="card-title")
        yield Label(self._value, classes="card-value")
        if self._delta is not None:
            _class = (
                "card-delta-pos" if self._delta_positive
                else "card-delta-neg" if self._delta_positive is False
                else "card-delta-neu"
            )
            yield Label(self._delta, classes=_class)