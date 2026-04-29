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
from osrs_console.utils.calc import CalcSession
# try:
#     from osrs_console.utils.calc import CalcSession
# except ImportError:
#     CalcSession = None


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
        ("ctrl+1", "open_skills", "⚔️ Skills"),
        ("ctrl+2", "open_calculator", "🧮 XP Calc"),
        ("ctrl+3", "open_wealth", "💰 Wealth"),
        ("ctrl+4", "open_analytics", "📊 Analytics"),
        ("ctrl+h", "open_home", "🏚️ Home"),
    ]


    DEFAULT_CSS = """
    GEPricesScreen { layout: vertical; height: 100%; scrollbar-visibility: hidden; }
    #ge-p-toolbar {
        height: 4;
        background: $panel;
        outline-bottom: tall $accent-darken-1;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
    }
    Tabs { margin-top: 1; }
    TabbedContent { height: 1fr; }
    TabbedContent ContentSwitcher { height: 1fr; }
    TabPane { height: 1fr; }
    #ge-p-toolbar {
        height: auto;
        background: $panel;
        outline-bottom: tall $accent-darken-1;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
    }
    #ge-p-title { color: $accent; text-style: bold; width: 22; }
    #ge-p-search { width: 1fr; margin-right: 1; }
    #ge-p-search-btn { margin-right: 1; }

    #lookup-body { height: 1fr; layout: vertical; }
    #search-status { color: $text-muted; height: 1; padding: 0 1; }
    #search-loading { align: center middle; height: 5; display: none; }
    #results-table { height: 1fr; }
    #lookup-actions {
        height: 4;
        layout: horizontal;
        align: left middle;
        padding: 0 1;
        background: $panel;
        border-top: tall $panel-darken-2;
        display: none;
    }
    #lookup-actions Button { margin-right: 1; }
    
    #saved-body { height: 1fr; layout: vertical; }
    #saved-table { height: 1fr; }
    #saved-actions {
        height: 4;
        layout: horizontal;
        align: left middle;
        padding: 0 1;
        background: $panel;
        border-top: tall $panel-darken-2;
        display: none;
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
        height: auto;
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
        border-top: tall $panel-darken-2;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
        display: none;
    }
    .summary-card {
        width: 1fr;
        height: 3;
        border: round $panel-darken-2;
        padding: 0 1;
        margin-right: 1;
    }
    .summary-label { color: $text-muted; }
    .summary-value { text-style: bold; color: $accent; }
    .profit { color: ansi_green; text-style: bold; }
    .loss { color: $error; text-style: bold; }
    .neutral { color: $text-muted; text-style: bold; }

    #ge-p-footer {
        height: 2;
        background: $panel; 
        border-top: tall $panel-darken-2;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
    }
    #ge-p-statusbar {
        height: 2;
        background: $panel;
        layout: horizontal;
        align: left middle;
        padding: 0 2;
    }
    #ge-p-status { color: $text-muted; margin-left: 2; }
    #ge-p-dock {
        layout: vertical;
        dock:  bottom;
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
            with Horizontal(id="lookup-actions"):
                yield Button("* Tag Item", id="btn-tag", disabled=True)
                yield Button("+ Expense", id="btn-add-expense", disabled=True, variant="error")
                yield Button("+ Sale", id="btn-add-sale", disabled=True, variant="success")
                yield Button("🏷️ Fetch Price", id="btn-fetch-price", disabled=True)
            with Horizontal(id="saved-actions"):
                yield Button("+ Expense", id="btn-saved-expense", disabled=True, variant="error")
                yield Button("+ Sale", id="btn-saved-sale", variant="success", disabled=True)
                yield Button("x Untag", id="btn-untag", disabled=True)
            with Horizontal(id="summary-bar"):
                with Vertical(classes="summary-card"):
                    yield Label("Total Expense", classes="summary-label")
                    yield Label("-", id="lbl-total-expense", classes="summary-value")
                with Vertical(classes="summary-card"):
                    yield Label("Total Income", classes="summary-label")
                    yield Label("-", id="lbl-total-sale", classes="summary-value")
                with Vertical(classes="summary-card"):
                    yield Label("Net P/L  (per action cycle)", classes="summary-label")
                    yield Label("-", id="lbl-net-pl", classes="summary-value")
                with Vertical(classes="summary-card"):
                    yield Label("XP / gp spent", classes="summary-label")
                    yield Label("-", id="lbl-xp-per-gp", classes="summary-value")
            with Horizontal(id="ge-p-footer"):
                yield Label("", id="ge-p-status", markup=True)
            yield Footer()

    def _compose_lookup_tab(self) -> ComposeResult:
        with Vertical(id="lookup-body"):
            with Container(id="search-loading"):
                yield LoadingIndicator()
            yield Label("Enter a search term above.", id="search-status")
            yield DataTable(id="results-table", zebra_stripes=True, cursor_type="row")

    def _compose_saved_tab(self) -> ComposeResult:
        with Vertical(id="saved-body"):
            yield DataTable(id="saved-table", zebra_stripes=True, cursor_type="row")

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

    def on_mount(self) -> None:
        self._setup_tables()
        self._load_saved_tab()
        self.query_one("#lookup-actions").display = True

        if self._session is not None:
            self._import_from_session(self._session)

            self.query_one("#ge-p-tabs", TabbedContent).active = "tab-lists"
            self._status(
                f"Loaded from Skill Calculator: [b]{self._session.skill.title()}[/b]  "
                f"Lvl [b]{self._session.start_level}[/b] → [b]{self._session.target_level}[/b]  "
                f"[i]([b]{self._session.actions_needed:,}[/b] action cycles)[/i]"
            )

    def _setup_tables(self) -> None:
        rt = self.query_one("#results-table", DataTable)
        rt.add_columns("Item Name", "Members", "GE Limit", "High Alch", "Low Alch")

        st = self.query_one("#saved-table", DataTable)
        st.add_columns("Item Name", "Item ID#", "Note", "Tagged")

        et = self.query_one("#expense-table", DataTable)
        et.add_columns("Item", "Qty", "Instant Buy (ea)", "Total Cost")

        salt = self.query_one("#sale-table", DataTable)
        salt.add_columns("Item", "Qty", "Instant Sell (ea)", "Total Income")

    def _import_from_session(self, session: "CalcSession") -> None:
        n = session.actions_needed
        seen_inputs: dict[str, int] = {}
        seen_outputs: dict[str, int] = {}

        for result in session.results:
            action = result.action

            for mat in action.input_materials():
                if mat.qty > 0:
                    seen_inputs[mat.name] = seen_inputs.get(mat.name, 0) + int(math.ceil(mat.qty * n))

            for mat in action.output_materials():
                if mat.qty > 0:
                    seen_outputs[mat.name] = seen_outputs.get(mat.name, 0) + int(math.ceil(mat.qty * n))

        for name, qty in seen_inputs.items():
            self._expense_items.append({
                "row_id": None,
                "item_id": -1,
                "name": name,
                "qty": qty,
                "price": None,
            })
        for name, qty in seen_outputs.items():
            self._sale_items.append({
                "row_id": None,
                "item_id": -1,
                "name": name,
                "qty": qty,
                "price": None,
            })
        
        self._refresh_list_tables()

        self.run_worker(self._fetch_prices_for_lists(), exclusive=False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "ge-p-search":
            self._do_search(event.value.strip())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        dispatch = {
            "ge-p-search-btn": self._on_search_btn,
            "btn-tag": self._on_tag,
            "btn-add-expense": lambda: self._on_add_to_list("expense"),
            "btn-add-sale": lambda: self._on_add_to_list("sale"),
            "btn-fetch-price": self._on_fetch_price_for_selected,
            "btn-saved-expense": lambda: self._on_saved_to_list("expense"),
            "btn-saved-sale": lambda: self._on_saved_to_list("sale"),
            "btn-untag": self._on_untag,
            "btn-rm-expense": lambda: self._on_remove_list_row("expense"),
            "btn-rm-sale": lambda: self._on_remove_list_row("sale"),
            "btn-refresh-expense": lambda: self.run_worker(
                self._fetch_prices_for_lists(), exclusive=False
            ),
            "btn-refresh-sale": lambda: self.run_worker(
                self._fetch_prices_for_lists(), exclusive=False
            ),
            "back-btn": self.action_go_back,
        }
        handler = dispatch.get(bid)
        if handler:
            handler()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        tid = event.pane.id
        panes = {
            "tab-lookup": "lookup-actions",
            "tab-saved": "saved-actions",
            "tab-lists": "summary-bar"
        }
        to_show = panes[tid]
        for barid in panes.values():
            self.query_one(f"#{barid}").display = False
        self.query_one(f"#{to_show}").display = True


    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        tid = event.data_table.id
        has_row = event.cursor_row is not None

        if tid == "results-table":
            for btn_id in (
                "btn-tag",
                "btn-add-expense",
                "btn-add-sale",
                "btn-fetch-price"
            ):
                self.query_one(f"#{btn_id}", Button).disabled = not has_row
        elif tid == "saved-table":
            for btn_id in ("btn-saved-expense", "btn-saved-sale", "btn-untag"):
                self.query_one(f"#{btn_id}", Button).disabled = not has_row
        elif tid == "expense-table":
            self.query_one("#btn-rm-expense", Button).disabled = not has_row
        elif tid == "sale-table":
            self.query_one("#btn-rm-sale", Button).disabled = not has_row

    def _on_search_btn(self) -> None:
        q = self.query_one("#ge-p-search", Input).value.strip()
        if q:
            self._do_search(q)
        
    def _do_search(self, query: str) -> None:
        if not query:
            return
        loading = self.query_one("#search-loading", Container)
        loading.display = True
        self.query_one("#search-status", Label).update(f"Searching '{query}'...")
        self.run_worker(self._async_search(query), exclusive=False)
    
    async def _async_search(self, query: str) -> None:
        try:
            results = await search_items(query)
        except GEAPIError as e:
            self._finish_search([], error=str(e))
            return
        self._search_results = sorted(results, key=lambda i: i.name)
        self._finish_search(self._search_results)

    def _finish_search(
        self,
        results: list[GEItem],
        error: str = ""
    ) -> None:
        self.query_one("#search-loading", Container).display = False
        table = self.query_one("#results-table", DataTable)
        table.clear()

        if error:
            self.query_one("#search-status", Label).update(f"⚠ {error}")
            return
        
        for item in results:
            table.add_row(
                item.name,
                "Yes" if item.members else "No",
                str(item.limit) if item.limit else "-",
                _gp(item.highalch),
                _gp(item.lowalch)
            )
        self.query_one("#search-status", Label).update(
            f"{len(results)} result(s)." if results else "No results found."
        )

    def _on_tag(self) -> None:
        item = self._get_selected_search_item()
        if item is None:
            return
        db.ge_save_item(item.id, item.name)
        self._load_saved_tab()
        self._status(f"* Tagged [b]{item.name}[/b].")

    def _on_untag(self) -> None:
        saved = self._get_selected_saved_row()
        if saved is None:
            return
        db.ge_unsave_item(saved["item_id"])
        self._load_saved_tab()
        self._status(f"Untagged [b]{saved['item_name']}[/b].")

    def _load_saved_tab(self) -> None:
        table = self.query_one("#saved-table", DataTable)
        table.clear()
        for row in db.ge_get_saved_items():
            table.add_row(
                row["item_name"],
                str(row["item_id"]),
                row["note"] or "-",
                row["tagged_at"][:10]
            )

    def _on_add_to_list(self, list_type: str) -> None:
        item = self._get_selected_search_item()
        if item is None:
            return
        self._add_item_to_list(
            list_type,
            item_id=item.id,
            name=item.name,
            qty=1
        )

    def _on_saved_to_list(self, list_type: str) -> None:
        saved = self._get_selected_saved_row()
        if saved is None:
            return
        self._add_item_to_list(
            list_type,
            item_id=saved["item_id"],
            name=saved["item_name"],
            qty=1
        )

    def _add_item_to_list(
        self,
        list_type: str,
        item_id: int,
        name: str,
        qty: int,
        price: Optional[int] = None
    ) -> None:
        entry = {
            "row_id": None,
            "item_id": item_id,
            "name": name,
            "qty": qty,
            "price": price,
        }
        if list_type == "expense":
            self._expense_items.append(entry)
        else:
            self._sale_items.append(entry)
        self._refresh_list_tables()
        self._status(f"Added [b]{name}[/b] to [i]{list_type}[/i] list.")

        if item_id > 0 and item_id not in self._price_cache:
            self.run_worker(self._fetch_single_price(item_id), exclusive=False)

    def _on_remove_list_row(self, list_type: str) -> None:
        table_id = f"#{list_type}-table"
        table = self.query_one(table_id, DataTable)
        row_key = table.cursor_row
        if row_key is None:
            return
        target = self._expense_items if list_type == "expense" else self._sale_items
        if 0 <= row_key < len(target):
            removed = target.pop(row_key)
            self._refresh_list_tables()
            self._status(f"Removed [b]{removed['name']}[/b] from [i]{list_type}[/i] list.")

    def _on_fetch_price_for_selected(self) -> None:
        item = self._get_selected_search_item()
        if item is None:
            return
        self._status(f"Fetching price for [b]{item.name}[/b]...")
        self.run_worker(self._fetch_single_price_and_show(item), exclusive=False)

    async def _fetch_single_price_and_show(self, item: GEItem) -> None:
        try:
            from osrs_console.utils.ge_api import fetch_price
            price = await fetch_price(item.id)
        except GEAPIError as e:
            self._status(f"⚠ Price fetch failed: {e}")
            return
        self._price_cache[item.id] = price
        self._status(
            f"[b]{item.name}[/b]  "
            f"Instant Buy: {_gp(price.high)} gp  |  "
            f"Instant Sell: {_gp(price.low)} gp  |  "
            f"Mid: {_gp(price.mid)} gp  |  "
            f"Spread: {_gp(price.spread)} gp  "
            f"(updated {price.high_time_str})"
        )

    async def _fetch_single_price(self, item_id: int) -> None:
        try:
            from osrs_console.utils.ge_api import fetch_price
            price = await fetch_price(item_id)
            self._price_cache[item_id] = price
            self._refresh_list_tables()
            self._update_summary()
        except GEAPIError:
            pass

    async def _fetch_prices_for_lists(self) -> None:
        all_ids = list({
            e["item_id"]
            for e in (self._expense_items + self._sale_items)
            if e["item_id"] > 0
        })
        if not all_ids:
            return
        self._status("Fetching live prices...")
        try:
            prices = await fetch_prices_bulk(all_ids)
            self._price_cache.update(prices)
        except GEAPIError as e:
            self._status(f"⚠ Bulk price fetch failed: {e}")
            return
        self._refresh_list_tables()
        self._update_summary()
        self._status(f"Prices updated for {len(prices)} item(s).")

    def _refresh_list_tables(self) -> None:
        self._render_list_table("expense")
        self._render_list_table("sale")
        self._update_summary()

    def _render_list_table(self, list_type: str) -> None:
        table = self.query_one(f"#{list_type}-table", DataTable)
        table.clear()
        items = self._expense_items if list_type == "expense" else self._sale_items

        for entry in items:
            iid = entry["item_id"]
            qty = entry["qty"]
            price = self._price_for_entry(entry, list_type)
            total = (qty * price) if price is not None else None

            table.add_row(
                entry["name"],
                f"{qty:,}",
                _gp(price, "fetching..."),
                _gp(total, "-"),
            )

    def _price_for_entry(self, entry: dict, list_type: str) -> Optional[int]:
        if entry.get("price") is not None:
            return entry["price"]
        iid = entry["item_id"]
        cached = self._price_cache.get(iid)
        if cached is None:
            return None
        return cached.high if list_type == "expense" else cached.low
    
    def _update_summary(self) -> None:
        expense_total = sum(
            (e["qty"] * p)
            for e in self._expense_items
            if (p := self._price_for_entry(e, "expense")) is not None
        )
        sale_total = sum(
            (e["qty"] * p)
            for e in self._sale_items
            if (p := self._price_for_entry(e, "sale")) is not None
        )
        net = sale_total - expense_total

        self.query_one("#lbl-total-expense", Label).update(_gp(expense_total))
        self.query_one("#lbl-total-sale", Label).update(_gp(sale_total))

        net_label = self.query_one("#lbl-net-pl", Label)
        net_label.update(_signed_gp(net))
        net_label.set_class(net > 0, "profit")
        net_label.set_class(net < 0, "loss")
        net_label.set_class(net == 0, "neutral")

        xp_gp_label = self.query_one("#lbl-xp-per-gp", Label)
        if self._session and expense_total > 0:
            xp_total = sum(
                r.action.xp * self._session.actions_needed
                for r in self._session.results
            )
            ratio = xp_total / expense_total
            xp_gp_label.update(f"{ratio:.3f} xp/gp")
        elif expense_total == 0:
            xp_gp_label.update("-")
        else:
            xp_gp_label.update("N/A (no session)")

    def action_go_back(self) -> None:
        self.app.pop_screen()
    
    def action_refresh_prices(self) -> None:
        self.run_worker(self._fetch_prices_for_lists(), exclusive=False)

    def action_save_lists(self) -> None:
        label = (
            f"{self._session.skill.title()} run"
            if self._session
            else "Manual"
        )
        # if self._expense_items:
            # list_id = 
        if self._expense_items:
            list_id = db.ge_create_list(label, "expense")
            for e in self._expense_items:
                p = self._price_for_entry(e, "expense")
                db.ge_add_list_item(list_id, e["item_id"], e["name"], e["qty"], p)
        if self._sale_items:
            list_id = db.ge_create_list(label, "sale")
            for e in self._sale_items:
                p = self._price_for_entry(e, "sale")
                db.ge_add_list_item(list_id, e["item_id"], e["name"], e["qty"], p)
        self._status("✅ Lists saved to database.")

    def _get_selected_search_item(self) -> Optional[GEItem]:
        table = self.query_one("#results-table", DataTable)
        row = table.cursor_row
        if row is None or row >= len(self._search_results):
            return None
        return self._search_results[row]
    
    def _get_selected_saved_row(self) -> Optional[dict]:
        table = self.query_one("#saved-table", DataTable)
        row_idx = table.cursor_row
        if row_idx is None:
            return None
        rows = db.ge_get_saved_items()
        if row_idx >= len(rows):
            return None
        return dict(rows[row_idx])
    
    def _status(self, msg: str) -> None:
        self.query_one("#ge-p-status", Label).update(msg)
