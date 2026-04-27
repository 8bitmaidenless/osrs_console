from __future__ import annotations

import asyncio
import urllib.request
import urllib.error
import json
import time
from dataclasses import dataclass, field
from typing import Optional


_BASE = "https://prices.runescape.wiki/api/v1/osrs"
_UA = "osrs-console / github.com/8bitmaidenless/osrs_console"

_mapping_cache: dict[str, "GEItem"] = {}
_mapping_loaded: bool = False


@dataclass
class GEItem:
    id: int
    name: str
    examine: str = ""
    members: bool = False
    limit: Optional[int] = None
    highalch: Optional[int] = None
    lowalch: Optional[int] = None
    value: Optional[int] = None
    icon: str = ""


@dataclass
class GEPrice:
    item_id: int
    name: str
    high: Optional[int]
    high_time: Optional[int]
    low: Optional[int]
    low_time: Optional[int]
    fetched_at: float = field(default_factory=time.time)

    @property
    def mid(self) -> Optional[int]:
        if self.high is not None and self.low is not None:
            return (self.high + self.low) // 2
        return self.high or self.low
    
    @property
    def spread(self) -> Optional[int]:
        if self.high is not None and self.low is not None:
            return self.high - self.low
        return None
    
    @property
    def high_time_str(self) -> str:
        if self.high_time is None:
            return "-"
        import datetime
        return datetime.datetime.fromtimestamp(self.high_time).strftime("%H:%M:%S")
    
    @property
    def low_time_str(self) -> str:
        if self.low_time is None:
            return "-"
        import datetime
        return datetime.datetime.fromtimestamp(self.low_time).strftime("%H:%M:%S")
    

class GEAPIError(Exception):
    pass


async def fetch_mapping() -> dict[str, GEItem]:
    global _mapping_cache, _mapping_loaded
    if _mapping_loaded:
        return _mapping_cache
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        _blocking_fetch_mapping
    )
    _mapping_cache = result
    _mapping_loaded = True
    return result


async def search_items(query: str) -> list[GEItem]:
    mapping = await fetch_mapping()
    q = query.lower().strip()
    return [item for name, item in mapping.items() if q in name]


async def fetch_price(item_id: int) -> GEPrice:
    mapping = await fetch_mapping()

    name = next((i.name for i in mapping.values() if i.id == item_id), f"Item #{item_id}")
    price = await asyncio.get_event_loop().run_in_executor(
        None,
        _blocking_fetch_price,
        item_id
    )
    price.name = name
    return price


async def fetch_prices_bulk(item_ids: list[int]) -> dict[int, GEPrice]:
    mapping = await fetch_mapping()
    id_to_name = {i.id: i.name for i in mapping.values()}
    raw = await asyncio.get_event_loop().run_in_executor(
        None,
        _blocking_fetch_latest_all
    )
    result: dict[int, GEPrice] = {}
    for iid in item_ids:
        entry = raw.get(str(iid)) or raw.get(iid)
        if entry:
            result[iid] = GEPrice(
                item_id=iid,
                name=id_to_name.get(iid, f"Item #{iid}"),
                high=entry.get("high"),
                high_time=entry.get("highTime"),
                low=entry.get("low"),
                low_time=entry.get("lowTime"),
            )
    return result


def _http_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise GEAPIError(f"HTTP {e.code}: {url}") from e
    except json.JSONDecodeError:
        raise GEAPIError(f"Bad JSON from API: {e}")
    

def _blockng_fetch_mapping() -> dict[str, GEItem]:
    data = _http_get(f"{_BASE}/mapping")
    result: dict[str, GEItem] = {}
    for entry in data:
        item = GEItem(
            id=entry.get("id"),
            name=entry.get("name", ""),
            examine=entry.get("examine", ""),
            members=entry.get("members", False),
            limit=entry.get("limit"),
            highalch=entry.get("highalch"),
            lowalch=entry.get("lowalch"),
            value=entry.get("value"),
            icon=entry.get("icon", "")
        )
        result[item.name.lower()] = item
    return result


def _blocking_fetch_price(item_id: int) -> GEPrice:
    data = _http_get(f"{_BASE}/latest?id={item_id}")
    entry = data.get("data", {}).get(str(item_id), {})
    return GEPrice(
        item_id=item_id,
        name="",
        high=entry.get("high"),
        high_time=entry.get("highTime"),
        low=entry.get("low"),
        low_time=entry.get("lowTime")
    )


def _blocking_fetch_latest_all() -> dict:
    data = _http_get(f"{_BASE}/latest")
    return data.get("data", {})
    


