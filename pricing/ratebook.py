"""
City rate book with provenance.

Lookup order for a material in a city:
  1. user / supplier quote for this project                          status "user"
  2. approved live rate for this city (price agent)                   status "live"
  3. approved live rate of a national item (same all over Pakistan)
     adjusted by the city factor                                      status "live"
  4. indicative base rate x city factor                               status "indicative"
Items that follow a live item (e.g. #3 and #5 bars follow the #4 bar price) move with it by the
ratio of their base rates.

Files (committed to the repo so every deployment shares them):
  data/rates/ratebook.json   approved live rates  {city: {mat_id: entry}}
  data/rates/pending.json    agent proposals waiting for approval
  data/rates/history.json    every approved change (audit trail)
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

from pricing.base_rates import (BASE_DATE, BASE_SOURCE, CITIES, LABOUR, LABOUR_CITY_FACTOR, LIVE_ITEMS,
                                MATERIAL_CITY_FACTOR, R, city_key)

RATES_DIR = Path(os.environ.get("COSTLENS_RATES_DIR", Path(__file__).resolve().parent.parent / "data" / "rates"))
STALE_DAYS = 45
_LOCK = threading.Lock()


@dataclass
class RateEntry:
    rate: float
    low: float
    high: float
    unit: str
    as_of: str
    source: str
    url: str = ""
    quote: str = ""
    n_sources: int = 1
    trusted: bool = False
    national: bool = False
    approved_by: str = "agent"


@dataclass
class RateInfo:
    """What the costing uses for one material in one city."""
    rate: float
    low: float
    high: float
    status: str  # user | live | indicative
    as_of: str
    source: str
    url: str = ""
    follows: str = ""  # mat_id of the live item it moves with

    @property
    def age_days(self) -> Optional[int]:
        try:
            return (date.today() - date.fromisoformat(self.as_of[:10])).days
        except ValueError:
            return None

    @property
    def stale(self) -> bool:
        a = self.age_days
        return self.status == "live" and a is not None and a > STALE_DAYS


@dataclass
class Proposal:
    city: str
    mat_id: str
    name: str
    old_rate: float
    new_rate: float
    low: float
    high: float
    unit: str
    change_pct: float
    sources: List[dict] = field(default_factory=list)  # {url, quote, price, unit, trusted}
    reason: str = ""
    created: str = ""

    @property
    def key(self) -> str:
        return f"{self.city}|{self.mat_id}"


# which base items follow which live item
FOLLOWERS: Dict[str, str] = {f: k for k, spec in LIVE_ITEMS.items() for f in spec.get("also", [])}


class RateBook:
    def __init__(self, folder: Optional[Path] = None):
        self.folder = Path(folder or RATES_DIR)
        self.live: Dict[str, Dict[str, RateEntry]] = {c: {} for c in CITIES}
        self.pending: List[Proposal] = []
        self.history: List[dict] = []
        self.updated_at = ""
        self.load()

    # ---------------------------------------------------------------- files
    def _read(self, name: str, default):
        p = self.folder / name
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default

    def load(self) -> None:
        book = self._read("ratebook.json", {})
        self.updated_at = book.get("updated_at", "")
        for city, items in (book.get("cities") or {}).items():
            if city in self.live:
                for mid, e in items.items():
                    try:
                        self.live[city][mid] = RateEntry(**e)
                    except TypeError:
                        continue
        self.pending = []
        for p in self._read("pending.json", []):
            try:
                self.pending.append(Proposal(**p))
            except TypeError:
                continue
        self.history = self._read("history.json", [])

    def save(self) -> None:
        with _LOCK:
            self.folder.mkdir(parents=True, exist_ok=True)
            self.updated_at = datetime.now().isoformat(timespec="seconds")
            book = {"format": "costlens-ratebook", "updated_at": self.updated_at, "base_date": BASE_DATE,
                    "cities": {c: {m: asdict(e) for m, e in items.items()} for c, items in self.live.items() if items}}
            (self.folder / "ratebook.json").write_text(json.dumps(book, indent=1, ensure_ascii=False), encoding="utf-8")
            (self.folder / "pending.json").write_text(json.dumps([asdict(p) for p in self.pending], indent=1, ensure_ascii=False),
                                                      encoding="utf-8")
            (self.folder / "history.json").write_text(json.dumps(self.history[-2000:], indent=1, ensure_ascii=False), encoding="utf-8")

    # ---------------------------------------------------------------- lookup
    def base(self, mat_id: str, city: str) -> RateInfo:
        c = city_key(city)
        typ, low, high = R.get(mat_id, (0.0, 0.0, 0.0))
        f = MATERIAL_CITY_FACTOR.get(c, 1.0)
        return RateInfo(round(typ * f, 2), round(low * f, 2), round(high * f, 2), "indicative", BASE_DATE, BASE_SOURCE)

    def live_entry(self, mat_id: str, city: str) -> Optional[RateEntry]:
        c = city_key(city)
        e = self.live.get(c, {}).get(mat_id)
        if e is not None:
            return e
        spec = LIVE_ITEMS.get(mat_id)
        if spec and spec.get("national"):  # a national price found for another city applies everywhere
            for other in CITIES:
                e = self.live.get(other, {}).get(mat_id)
                if e is not None:
                    return e
        return None

    def rate(self, mat_id: str, city: str, user_rates: Optional[Dict[str, float]] = None) -> RateInfo:
        c = city_key(city)
        if user_rates and user_rates.get(mat_id) is not None:
            v = float(user_rates[mat_id])
            return RateInfo(v, v, v, "user", date.today().isoformat(), "Your quote")
        leader = mat_id if mat_id in LIVE_ITEMS else FOLLOWERS.get(mat_id)
        if leader:
            e = self.live_entry(leader, c)
            if e is not None:
                f = 1.0
                if e.national:
                    f = MATERIAL_CITY_FACTOR.get(c, 1.0)
                if leader != mat_id:  # follower: keep its base ratio to the live leader
                    f *= R[mat_id][0] / R[leader][0] if R.get(leader, (0,))[0] else 1.0
                return RateInfo(round(e.rate * f, 2), round(e.low * f, 2), round(e.high * f, 2), "live", e.as_of,
                                e.source + (f" (via {LIVE_ITEMS[leader]['name']})" if leader != mat_id else ""), e.url,
                                follows=leader if leader != mat_id else "")
        return self.base(mat_id, c)

    def labour_rate(self, wi_id: str, city: str, user_labour: Optional[Dict[str, float]] = None) -> RateInfo:
        if user_labour and user_labour.get(wi_id) is not None:
            v = float(user_labour[wi_id])
            return RateInfo(v, v, v, "user", date.today().isoformat(), "Your rate")
        c = city_key(city)
        v = LABOUR.get(wi_id, 0.0) * LABOUR_CITY_FACTOR.get(c, 1.0)
        return RateInfo(round(v, 2), round(v * 0.85, 2), round(v * 1.2, 2), "indicative", BASE_DATE, "Indicative labour rate - to confirm")

    # ---------------------------------------------------------------- approvals
    def approve(self, p: Proposal, by: str = "admin") -> None:
        src = p.sources[0] if p.sources else {}
        self.live.setdefault(p.city, {})[p.mat_id] = RateEntry(
            rate=round(p.new_rate, 2), low=round(p.low, 2), high=round(p.high, 2), unit=p.unit, as_of=date.today().isoformat(),
            source=src.get("domain") or src.get("url", "web"), url=src.get("url", ""), quote=src.get("quote", "")[:300],
            n_sources=len({s.get("domain") for s in p.sources}) or 1, trusted=any(s.get("trusted") for s in p.sources),
            national=bool(LIVE_ITEMS.get(p.mat_id, {}).get("national")), approved_by=by)
        self.history.append({"at": datetime.now().isoformat(timespec="seconds"), "city": p.city, "mat_id": p.mat_id,
                             "old": p.old_rate, "new": p.new_rate, "by": by, "reason": p.reason})
        self.pending = [x for x in self.pending if x.key != p.key]

    def reject(self, key: str) -> None:
        self.pending = [x for x in self.pending if x.key != key]

    def add_pending(self, p: Proposal) -> None:
        self.pending = [x for x in self.pending if x.key != p.key] + [p]

    # ---------------------------------------------------------------- summaries
    def freshness(self, city: str) -> dict:
        c = city_key(city)
        rows = []
        for mid, spec in LIVE_ITEMS.items():
            info = self.rate(mid, c)
            rows.append({"mat_id": mid, "name": spec["name"], "rate": info.rate, "unit": spec["unit"], "status": info.status,
                         "as_of": info.as_of, "age_days": info.age_days, "stale": info.stale, "source": info.source, "url": info.url})
        live = [r for r in rows if r["status"] == "live"]
        return {"rows": rows, "n_live": len(live), "n_items": len(rows),
                "latest": max((r["as_of"] for r in live), default=""), "n_stale": sum(r["stale"] for r in live)}
