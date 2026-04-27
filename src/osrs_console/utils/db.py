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


