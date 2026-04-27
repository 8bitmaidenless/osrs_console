from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_DB_DIR = Path.home() / ".local" / "share" / "osrs-console"
DB_PATH = _DB_DIR / "osrs_console.db"
SQL_PATH = Path(__file__).parent / "data" / "sql"
if not SQL_PATH.exists():
    SQL_PATH.mkdir(parents=True, exist_ok=True)

_local = threading.local()


def get_db() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        _DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _create_schema(conn)
        _local.conn = conn
    return _local.conn


def _create_schema(conn: sqlite3.Connection) -> None:
    sql_path = SQL_PATH / "schema.sql"
    with open(sql_path, "r") as file:
        sql = file.read()
    conn.executescript(sql)
    conn.commit()


def save_snapshot(
    username: str,
    items: list[dict],
    note: str = ""
) -> int:
    conn = get_db()
    now = _now()
    total = sum(i["qty"] * i["price"] for i in items)
    cur = conn.execute(
        "INSERT INTO wealth_snapshots (username, recorded_at, note, total_value) VALUES (?, ?, ?, ?)",
        (username, now, note, total)
    )
    snapshot_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO bank_items (snapshot_id, item_name, quantity, unit_price) VALUES (?, ?, ?, ?)",
        [(snapshot_id, i["name"], i["qty"], i["price"],) for i in items]
    )
    conn.commit()
    return snapshot_id


def get_snapshots(username: str) -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT * FROM wealth_snapshots WHERE username=? ORDER BY recorded_at DESC",
        (username,)
    ).fetchall()


def get_snapshot_items(snapshot_id: int) -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT * FROM bank_items WHERE snapshot_id=? ORDER BY total_value DESC",
        (snapshot_id,)
    ).fetchall()


def delete_snapshot(snapshot_id: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM wealth_snapshots WHERE id=?", (snapshot_id,))
    conn.commit()


def save_ge_transaction(
    username: str,
    item_name: str,
    tx_type: str,
    quantity: int,
    price_each: int,
    note: str = ""
) -> int:
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO ge_transactions
           (username, recorded_at, item_name, transaction_type, quantity, price_each, note)
           VALUES (?,?,?,?,?,?,?)""",
        (username, _now(), item_name, tx_type, quantity, price_each, note)
    )
    conn.commit()
    return cur.lastrowid


def get_ge_transactions(username: str, limit: int = 200) -> list[sqlite3.Row]:
    return get_db().execute(
        """SELECT * FROM ge_transactions WHERE username=?
           ORDER BY recorded_at DESC LIMIT ?""",
        (username, limit)
    ).fetchall()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_wealth_history(username: str) -> list[sqlite3.Row]:
    return get_db().execute(
        """SELECT recorded_at, total_value
           FROM wealth_snapshots
           WHERE username=?
           ORDER BY recorded_at ASC""",
        (username,)
    ).fetchall()


def get_ge_summary(username: str) -> dict:
    conn = get_db()

    agg = conn.execute(
        """SELECT
                COALESCE(SUM(CASE WHEN transaction_type='buy'  THEN total_value ELSE 0 END), 0) AS total_spent,
                COALESCE(SUM(CASE WHEN transaction_type='sell' THEN total_value ELSE 0 END), 0)) AS total_earned,
                COUNT(*) AS tx_count
            FROM ge_transactions
            WHERE username=?""",
        (username,)
    ).fetchone()

    top_items = conn.execute(
        """SELECT
                item_name,
                SUM(CASE WHEN transaction_type='sell' THEN total_value ELSE 0 END) -
                SUM(CASE WHEN transaction_type='buy'  THEN total_value ELSE 0 END) AS net
            FROM ge_transactions
            WHERE username=?
            GROUP BY item_name
            ORDER BY ABS(net) DESC
            LIMIT 10""",
        (username,)
    ).fetchall()

    return {
        "total_spent": agg["total_spent"],
        "total_earned": agg["total_earned"],
        "net_profit": agg["total_earned"] - agg["total_spent"],
        "tx_count": agg["tx_count"],
        "top_items": [dict(r) for r in top_items],
    }


def get_wealth_delta(username: str) -> dict:
    rows = get_db().execute(
        """SELECT total_value FROM wealth_snapshots
           WHERE username=?
           ORDER BY recorded_at DESC
           LIMIT 2""",
        (username,)
    ).fetchall()

    latest = rows[0]["total_value"] if len(rows) > 0 else 0
    previous = rows[1]["total_value"] if len(rows) > 1 else 0

    snap_count = get_db().execute(
        "SELECT COUNT(*) FROM wealth_snapshots WHERE username=?",
        (username,)
    ).fetchone()[0]

    return {
        "latest": latest,
        "previous": previous,
        "delta": latest - previous,
        "snapshot_count": snap_count,
    }


def get_ge_monthly_flow(username: str) -> list[dict]:
    rows = get_db().execute(
        """SELECT
                SUBSTR(recorded_at, 1, 7) AS month,
                SUM(CASE WHEN transaction_type='buy'  THEN total_value ELSE 0 END) AS spent,
                SUM(CASE WHEN transaction_type='sell' THEN total_value ELSE 0 END) AS earned
            FROM ge_transactions
            WHERE username=?
            GROUP BY month
            ORDER BY month ASC
            LIMIT 12""",
        (username,)
    ).fetchall()
    return [dict(r) for r in rows]


def _ensure_price_tables(conn: sqlite3.Connection) -> None:
    sql_path = SQL_PATH / "schema_ge.sql"
    with open(sql_path, "r") as file:
        sql = file.read()
    conn.executescript(sql)
    conn.commit()


_orig_create_schema = _create_schema


def _create_schema(conn: sqlite3.Connection) -> None:
    _orig_create_schema(conn)
    _ensure_price_tables(conn)

def ge_save_item(item_id: int, item_name: str, note: str = "") -> None:
    conn = get_db()
    conn.execute(
        """INSERT INTO ge_saved_items (item_id, item_name, note, tagged_at)
           VALUES (?,?,?,?)
           ON CONFLICT(item_id) DO UPDATE SET note=excluded.note""",
        (item_id, item_name, note, _now())
    )
    conn.commit()


def ge_unsave_item(item_id: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM ge_saved_items WHERE item_id=?", (item_id,))
    conn.commit()


def ge_get_saved_items() -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT * FROM ge_saved_items ORDER BY tagged_at DESC"
    ).fetchall()


def ge_is_saved(item_id: int) -> bool:
    row = get_db().execute(
        "SELECT 1 FROM ge_saved_items WHERE item_id=?", (item_id,)
    ).fetchone()
    return row is not None


def ge_create_list(list_name: str, list_type: str) -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO ge_price_lists (list_name, list_type, created_at) VALUES (?, ?, ?)",
        (list_name, list_type, _now())
    )
    conn.commit()
    return cur.lastrowid


def ge_get_lists() -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT * FROM ge_price_lists ORDER BY list_type, list_name"
    ).fetchall()


def ge_delete_list(list_id: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM ge_price_lists WHERE id=?", (list_id,))
    conn.commit()


def ge_add_list_item(
    list_id: int,
    item_id: int,
    item_name: str,
    quantity: int = 1,
    pinned_price: Optional[int] = None
) -> int:
    conn = get_db()
    cur = conn.exeute(
        """INSERT INTO ge_list_items
           (list_id, item_id, item_name, quantity, pinned_price, added_at)
           VALUES (?,?,?,?,?,?)"""
        (list_id, item_id, item_name, quantity, pinned_price, _now())
    )
    conn.commit()
    return cur.lastrowid


def ge_remove_list_item(item_row_id: int) -> None:
    conn = get_db()
    conn.execute("DELETE FROM ge_list_items WHERE id=?", (item_row_id,))
    conn.commit()


def ge_get_list_items(list_id: int) -> list[sqlite3.Row]:
    return get_db().execute(
        "SELECT * FROM ge_list_items WHERE list_id=? ORDER BY added_at ASC",
        (list_id,)
    ).fetchall()