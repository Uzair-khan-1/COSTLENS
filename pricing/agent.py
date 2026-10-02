"""
Price agent - keeps the frequently changing material rates up to date per city.

For every live item x city it:
  1. SEARCHES the web (DuckDuckGo by default; Tavily / Brave if their free keys are set)
  2. READS the top pages (plain text, size-limited, polite user agent)
  3. EXTRACTS prices with the AI (Groq/Gemini via ai/groq_client) - or with rules when no AI key -
     and every price must come with a QUOTE from the page that contains the number
  4. VERIFIES: quote really is on the page, unit converted to the database unit, inside the plausible
     range, city matches (or national price), outliers dropped (median absolute deviation)
  5. DECIDES: combines the sources (median, low/high) and compares with the current rate:
       |change| < 5 % and (trusted source or >= 2 sites agree)   -> auto-approved (live immediately)
       |change| > 40 %                                            -> rejected as outlier (logged)
       otherwise                                                  -> waits for admin approval
Nothing here raises: problems are logged in the run report.
"""
from __future__ import annotations

import json
import re
import statistics
import time
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from typing import Callable, Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from pricing.base_rates import CITIES, LIVE_ITEMS, city_key
from pricing.ratebook import Proposal, RateBook

AUTO_APPROVE_PCT = 5.0
REJECT_PCT = 40.0
MAX_RESULTS = 5
MAX_PAGE_CHARS = 400_000
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
      "CostLensPriceCheck/1.1")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "en-PK,en;q=0.9"}
MAX_AGE_DAYS = 120  # pages whose newest date is older than this are not used

TRUSTED_DOMAINS = {
    "pbs.gov.pk", "dawn.com", "tribune.com.pk", "brecorder.com", "arynews.tv", "geo.tv", "thenews.com.pk", "dailyausaf.com",
    "urdupoint.com", "samaa.tv", "propakistani.pk", "amreli.com", "amrelisteels.com", "mughalsteel.com", "aghasteel.com",
    "luckycement.com", "dgcement.com", "bestway.com.pk", "pakistancables.com", "fastcables.com", "zameen.com", "graana.com",
}

CITY_WORDS = {"Islamabad": ["islamabad", "isb"], "Rawalpindi": ["rawalpindi", "pindi"], "Lahore": ["lahore"],
              "Karachi": ["karachi", "khi"], "Peshawar": ["peshawar"], "Quetta": ["quetta"]}


# ---------------------------------------------------------------------------
# data classes
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    price: float  # already converted to the database unit
    raw_price: float
    raw_unit: str
    city: str  # city named in the source or "Pakistan"
    quote: str
    url: str
    domain: str
    trusted: bool
    date: str = ""


@dataclass
class ItemResult:
    city: str
    mat_id: str
    name: str
    status: str  # auto-approved | pending | rejected | no-data | unchanged | error
    old_rate: float
    new_rate: Optional[float] = None
    change_pct: Optional[float] = None
    candidates: List[Candidate] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class RunReport:
    started: str
    results: List[ItemResult] = field(default_factory=list)
    searches: int = 0
    pages: int = 0

    def summary(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for r in self.results:
            out[r.status] = out.get(r.status, 0) + 1
        return out

    def markdown(self) -> str:
        lines = [f"#### Price update {self.started}", "", f"Searches: {self.searches} - pages read: {self.pages}",
                 "", "Summary: " + ", ".join(f"{k}: {v}" for k, v in sorted(self.summary().items())), "",
                 "| City | Item | Status | Old | New | Change | Sources |", "|---|---|---|---|---|---|---|"]
        for r in self.results:
            src = ", ".join(sorted({c.domain for c in r.candidates})[:4])
            lines.append(f"| {r.city} | {r.name} | {r.status} | {r.old_rate:,.2f} | "
                         f"{'' if r.new_rate is None else f'{r.new_rate:,.2f}'} | "
                         f"{'' if r.change_pct is None else f'{r.change_pct:+.1f}%'} | {src} |")
            for n in r.notes[:6]:
                lines.append(f"|  | | note: {n} | | | | |")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# web access (replaceable in tests)
# ---------------------------------------------------------------------------
class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg", "head"):
            self._skip += 1
        elif tag in ("p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table"):
            self.parts.append("\n")  # table cells stay on their row's line ("Lucky Cement | 1,560 |")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "head") and self._skip:
            self._skip -= 1
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - broken html still gives partial text
        pass
    text = "".join(p.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def http_get(url: str, timeout: float = 15.0) -> str:
    import requests
    r = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
    r.raise_for_status()
    raw = r.raw.read(MAX_PAGE_CHARS, decode_content=True)
    return raw.decode(r.encoding or "utf-8", errors="replace")


def search_duckduckgo(query: str) -> List[dict]:
    import requests
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "pk-en"},
                      headers={"User-Agent": UA}, timeout=15)
    r.raise_for_status()
    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r.text, flags=re.S):
        href = m.group(1)
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        if href.startswith("//"):
            href = "https:" + href
        title = re.sub(r"<[^>]+>", "", m.group(2))
        if href.startswith("http") and "duckduckgo.com" not in href:
            out.append({"url": href, "title": title})
        if len(out) >= MAX_RESULTS:
            break
    return out


def search_tavily(query: str, key: str) -> List[dict]:
    import requests
    r = requests.post("https://api.tavily.com/search", json={"api_key": key, "query": query, "max_results": MAX_RESULTS,
                                                              "include_raw_content": False}, timeout=20)
    r.raise_for_status()
    return [{"url": x.get("url", ""), "title": x.get("title", ""), "content": x.get("content", "")} for x in r.json().get("results", [])]


def search_brave(query: str, key: str) -> List[dict]:
    import requests
    r = requests.get("https://api.search.brave.com/res/v1/web/search?q=" + quote_plus(query) + f"&count={MAX_RESULTS}&country=pk",
                     headers={"X-Subscription-Token": key, "Accept": "application/json"}, timeout=20)
    r.raise_for_status()
    return [{"url": x.get("url", ""), "title": x.get("title", "")} for x in (r.json().get("web", {}).get("results") or [])]


def search_ddgs(query: str) -> List[dict]:
    """The maintained DuckDuckGo client library (pip install ddgs) - much more reliable than scraping."""
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS  # older package name
    with DDGS() as d:
        return [{"url": r.get("href") or r.get("url", ""), "title": r.get("title", ""), "content": r.get("body", "")}
                for r in d.text(query, region="pk-en", max_results=MAX_RESULTS)]


def search_ddg_lite(query: str) -> List[dict]:
    import requests
    r = requests.post("https://lite.duckduckgo.com/lite/", data={"q": query, "kl": "pk-en"}, headers=HEADERS, timeout=15)
    r.raise_for_status()
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*class=[\'"]result-link[\'"][^>]*>(.*?)</a>', r.text, flags=re.S):
        href = m.group(1)
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        if href.startswith("//"):
            href = "https:" + href
        if href.startswith("http"):
            out.append({"url": href, "title": re.sub(r"<[^>]+>", "", m.group(2))})
        if len(out) >= MAX_RESULTS:
            break
    return out


def search_bing(query: str) -> List[dict]:
    import requests
    r = requests.get("https://www.bing.com/search?q=" + quote_plus(query) + "&setlang=en&cc=PK", headers=HEADERS, timeout=15)
    r.raise_for_status()
    out = []
    for m in re.finditer(r'<li class="b_algo".*?<h2[^>]*><a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', r.text, flags=re.S):
        out.append({"url": m.group(1), "title": re.sub(r"<[^>]+>", "", m.group(2))})
        if len(out) >= MAX_RESULTS:
            break
    return out


SEARCH_LOG: List[str] = []  # which engine answered / failed (shown in the run report)


def default_search(tavily_key: str = "", brave_key: str = "") -> Callable[[str], List[dict]]:
    engines = ([("Tavily", lambda x: search_tavily(x, tavily_key))] if tavily_key else []) + \
              ([("Brave", lambda x: search_brave(x, brave_key))] if brave_key else []) + \
              [("DuckDuckGo (ddgs)", search_ddgs), ("DuckDuckGo lite", search_ddg_lite), ("Bing", search_bing),
               ("DuckDuckGo html", search_duckduckgo)]

    def run(q: str) -> List[dict]:
        for name, fn in engines:
            try:
                res = fn(q)
                if res:
                    SEARCH_LOG.append(f"{name}: {len(res)} results")
                    return res
                SEARCH_LOG.append(f"{name}: no results")
            except Exception as exc:  # noqa: BLE001 - try the next search engine
                SEARCH_LOG.append(f"{name}: {type(exc).__name__} {str(exc)[:60]}")
        return []
    return run


# Pages that publish current rates, read directly every run (no search engine needed). Old pages are skipped by date.
DIRECT_SOURCES = {
    "CON-001": ["https://icons.com.pk/cement-rate-today", "https://priceguide.pk/cement-price-in-pakistan/",
                "https://propertydealer.pk/today-cement-rate-in-pakistan",
                "https://hamariweb.com/finance/info/cement-rate-today-in-pakistan/"],
    "RBR-002": ["https://icons.com.pk/steel-rate-today", "https://pricesin.pk/saria-rate-today-in-pakistan/"],
}
# brand / row names that mark a table row as being about the item (for tables without "Rs ... per bag")
ROW_WORDS = {
    "CON-001": ["cement", "lucky", "bestway", "maple", "dg khan", "fauji", "cherat", "kohat", "pioneer", "power", "askari",
                "flying", "pakcem", "falcon", "paidar", "islamabad", "lahore", "karachi", "rawalpindi", "peshawar", "quetta"],
    "RBR-002": ["steel", "saria", "sarya", "amreli", "mughal", "agha", "af steel", "moiz", "union", "naveena", "five star",
                "ittefaq", "kamran", "grade 60", "60 grade", "sutar", "islamabad", "lahore", "karachi", "rawalpindi", "peshawar",
                "quetta"],
}


def domain_of(url: str) -> str:
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def is_trusted(url: str) -> bool:
    d = domain_of(url)
    return any(d == t or d.endswith("." + t) for t in TRUSTED_DOMAINS)


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------
_NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def relevant_snippets(text: str, keywords: List[str], window: int = 700, limit: int = 6000) -> str:
    """Only the parts of a page around the material's keywords (keeps AI requests small)."""
    low = text.lower()
    spans = []
    for kw in keywords:
        for m in re.finditer(re.escape(kw.lower()), low):
            spans.append((max(0, m.start() - window // 2), min(len(text), m.end() + window // 2)))
    spans.sort()
    merged: List[list] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out = "\n...\n".join(text[a:b] for a, b in merged)
    return out[:limit]


def _convert(price: float, unit: str, spec: dict) -> Optional[float]:
    u = (unit or "").strip().lower().replace("per ", "").replace(".", "")
    u = re.sub(r"\s+", " ", u)
    units = {k.lower(): v for k, v in spec["units"].items()}
    if u in units:
        return price * units[u]
    for k, v in sorted(units.items(), key=lambda kv: -len(kv[0])):
        if k in u:
            return price * v
    return None


def rule_extract(snippet: str, spec: dict) -> List[dict]:
    """No-AI fallback: 'Rs 1,450 per bag', 'Rs. 258-265 per kg', 'PKR 17,000 per 1000 bricks'."""
    unit_alt = "|".join(sorted((re.escape(u) for u in spec["units"]), key=len, reverse=True))
    pat = re.compile(rf"(?:rs\.?|pkr|rupees)\s*{_NUM}(?:\s*(?:-|to|–)\s*(?:rs\.?|pkr)?\s*{_NUM})?\s*(?:/|per|a|each)\s*({unit_alt})",
                     re.I)
    out = []
    for m in pat.finditer(snippet):
        lo, hi = _num(m.group(1)), _num(m.group(2)) if m.group(2) else None
        price = (lo + hi) / 2 if hi else lo
        a, b = max(0, m.start() - 120), min(len(snippet), m.end() + 40)
        out.append({"price": price, "unit": m.group(3), "city": "", "quote": snippet[m.start():m.end()], "context": snippet[a:b]})
    return out


def table_extract(snippet: str, spec: dict) -> List[dict]:
    """Rate tables without 'Rs ... per bag' on each row, e.g. 'Lucky Cement | 1,560' under a 'Price/50 kg bag (PKR)'
    header, or 'Mughal Steel | 255 | 255,000 | 261 | 261,000'. A row counts when it names the item (brand / city / item
    word) and holds a number that is a plausible price in the item's unit (or per ton for steel)."""
    lo, hi = spec["sane"]
    words = [w.lower() for w in spec.get("row_words", spec["keywords"])]
    unit_words = {"bag": r"bag|bori", "kg": r"\bkg\b|kilo", "Nos": r"brick|1000|thousand", "cft": r"cft|cubic"}.get(spec["unit"], "")
    if unit_words and not re.search(unit_words, snippet, re.I):
        return []
    out = []
    for raw in re.split(r"\n", snippet):
        line = raw.strip()
        if len(line) < 5 or len(line) > 220 or not any(w in line.lower() for w in words):
            continue
        nums = []
        for mm in re.finditer(_NUM, line):
            v = _num(mm.group(0))
            before = line[max(0, mm.start() - 4):mm.start()].lower()
            if 1990 <= v <= 2100 and float(v).is_integer() and "," not in mm.group(0) and not re.search(r"rs\.?\s*$|pkr\s*$|\u20a8\s*$", before):
                continue  # a year (e.g. "Cement Rate Today 2026"), not a price
            if re.search(r"[-/.]\s*$", before) or re.match(r"\s*[-/.]\d", line[mm.end():mm.end() + 3]):
                continue  # part of a date like 27-09-2026
            nums.append(v)
        vals = []
        for v in nums:
            if lo <= v <= hi:
                vals.append(v)
            elif spec["unit"] == "kg" and lo <= v / 1000 <= hi:  # per-ton column
                vals.append(v / 1000)
        if not vals:
            continue
        price = max(vals) if spec["unit"] == "kg" else vals[0]  # steel rows: grade 60 is the higher column
        out.append({"price": price, "unit": spec["unit"], "city": "", "quote": line[:200], "context": line})
    return out[:40]


_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def page_date(text: str):
    """Newest date written on the page (not in the future) - used to skip old rate pages."""
    from datetime import date as _date
    today = _date.today()
    found = []
    for m in re.finditer(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d\d)\b", text):
        try:
            found.append(_date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    mon = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    for m in re.finditer(rf"\b(\d{{1,2}})\s+{mon},?\s+(20\d\d)", text, re.I):
        try:
            found.append(_date(int(m.group(3)), _MONTHS[m.group(2).lower()[:3]], int(m.group(1))))
        except ValueError:
            pass
    for m in re.finditer(rf"\b{mon}\s+(\d{{1,2}}),?\s+(20\d\d)", text, re.I):
        try:
            found.append(_date(int(m.group(3)), _MONTHS[m.group(1).lower()[:3]], int(m.group(2))))
        except ValueError:
            pass
    for m in re.finditer(rf"\b{mon},?\s+(20\d\d)\b", text, re.I):
        try:
            found.append(_date(int(m.group(2)), _MONTHS[m.group(1).lower()[:3]], 15))
        except ValueError:
            pass
    found = [d for d in found if d <= today and d.year >= today.year - 3]
    return max(found) if found else None


LLM_SYSTEM = ("You extract construction material prices from web page text for Pakistan. Answer only with JSON. "
              "Never invent numbers: every price must be copied from the text, with an exact quote.")


def llm_extract(snippet: str, spec: dict, city: str, keys) -> List[dict]:
    from ai.groq_client import call_text_model
    prompt = (f"Material: {spec['name']}. Target city: {city}.\n"
              f"Find retail prices for this material in the text. Allowed units: {', '.join(spec['units'])}.\n"
              "Return JSON: {\"prices\": [{\"price\": number (single value; for a range give the middle), "
              "\"unit\": one of the allowed units, \"city\": city named for this price or \"Pakistan\", "
              "\"date\": date mentioned or \"\", \"quote\": exact sentence/cell from the text containing the number}]}. "
              "Only prices for THIS material (e.g. not a different brick class or pipe size). Empty list if none.\n\n"
              f"TEXT:\n{snippet}")
    raw = call_text_model(getattr(keys, "groq", ""), LLM_SYSTEM, prompt, max_tokens=700, json_mode=True, keys=keys)
    try:
        data = json.loads(re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M))
    except json.JSONDecodeError:
        return []
    return [p for p in (data.get("prices") or []) if isinstance(p, dict)]


def _norm(s: str) -> str:
    return re.sub(r"[\s,]+", " ", (s or "").lower()).strip()


def _price_in_quote(price: float, quote: str) -> bool:
    nums = [_num(n) for n in re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", quote)]
    cands = nums + [(a + b) / 2 for a, b in zip(nums, nums[1:])]
    return any(abs(n - price) <= max(0.01 * price, 0.01) for n in cands)


def verify(raw: List[dict], page_text: str, spec: dict, target_city: str, url: str) -> List[Candidate]:
    """Keep only prices whose quote is on the page, contains the number, converts to the DB unit, is plausible
    and belongs to the target city (or is a national price)."""
    out = []
    page_n = _norm(page_text)
    lo, hi = spec["sane"]
    city_words = CITY_WORDS.get(target_city, [target_city.lower()])
    other_cities = [w for c, ws in CITY_WORDS.items() if c != target_city for w in ws]
    for r in raw:
        try:
            price = float(r.get("price"))
        except (TypeError, ValueError):
            continue
        quote = str(r.get("quote") or "")
        qn = _norm(quote)
        if len(qn) < 6 or qn[:60] not in page_n:
            continue  # quote not really on the page -> possible hallucination
        if not _price_in_quote(price, quote):
            continue  # the number must really be in the quote (a single value or the middle of a range)
        conv = _convert(price, str(r.get("unit", "")), spec)
        if conv is None or not (lo <= conv <= hi):
            continue
        rc = str(r.get("city") or "").lower()
        ctx = _norm(r.get("context", quote))
        named_other = any(w in rc for w in other_cities) or (not rc and any(w in ctx for w in other_cities)
                                                               and not any(w in ctx for w in city_words))
        if named_other and not spec.get("national"):
            continue
        city = target_city if (any(w in rc for w in city_words) or any(w in ctx for w in city_words)) else "Pakistan"
        out.append(Candidate(round(conv, 2), price, str(r.get("unit", "")), city, quote[:300], url, domain_of(url), is_trusted(url),
                             str(r.get("date") or "")))
    return out


def combine(cands: List[Candidate]) -> Optional[dict]:
    """Median of sources after dropping outliers (> 3 MAD); prefers city-specific prices over national ones."""
    if not cands:
        return None
    local = [c for c in cands if c.city != "Pakistan"]
    use = local if len(local) >= 1 else cands
    vals = [c.price for c in use]
    med = statistics.median(vals)
    mad = statistics.median([abs(v - med) for v in vals]) or med * 0.05
    kept = [c for c in use if abs(c.price - med) <= 3 * mad] or use
    vals = sorted(c.price for c in kept)
    return {"rate": statistics.median(vals), "low": vals[0], "high": vals[-1], "kept": kept,
            "domains": sorted({c.domain for c in kept}), "trusted": any(c.trusted for c in kept),
            "agree": _agreement(vals)}


def _agreement(vals: List[float]) -> bool:
    if len(vals) < 2:
        return False
    med = statistics.median(vals)
    return sum(1 for v in vals if abs(v - med) / med <= 0.05) >= 2


# ---------------------------------------------------------------------------
# the agent
# ---------------------------------------------------------------------------
class PriceAgent:
    def __init__(self, book: RateBook, keys=None, search: Optional[Callable[[str], List[dict]]] = None,
                 fetch: Optional[Callable[[str], str]] = None, extractor: Optional[Callable] = None,
                 auto_pct: float = AUTO_APPROVE_PCT, reject_pct: float = REJECT_PCT, pause_s: float = 1.0,
                 log: Optional[Callable[[str], None]] = None, direct: Optional[Dict[str, List[str]]] = None):
        self.book = book
        self.keys = keys
        self.search = search or default_search()
        self.fetch = fetch or (lambda u: html_to_text(http_get(u)))
        self.extractor = extractor
        self.auto_pct = auto_pct
        self.reject_pct = reject_pct
        self.pause_s = pause_s
        self.log = log or (lambda m: None)
        self._page_cache: Dict[str, str] = {}
        self.direct = DIRECT_SOURCES if direct is None else direct

    def _extract(self, snippet: str, spec: dict, city: str) -> List[dict]:
        if self.extractor is not None:
            return self.extractor(snippet, spec, city)
        if self.keys is not None and getattr(self.keys, "any", lambda: False)():
            try:
                found = llm_extract(snippet, spec, city, self.keys)
                if found:
                    return found
            except Exception as exc:  # noqa: BLE001 - fall back to the rules
                self.log(f"AI extraction failed ({exc}); using rules")
        return rule_extract(snippet, spec) + table_extract(snippet, spec)

    def _page(self, url: str) -> str:
        if url not in self._page_cache:
            self._page_cache[url] = self.fetch(url)
            time.sleep(self.pause_s)
        return self._page_cache[url]

    def update_item(self, mat_id: str, city: str, report: Optional[RunReport] = None) -> ItemResult:
        spec = LIVE_ITEMS[mat_id]
        city = city_key(city)
        current = self.book.rate(mat_id, city).rate
        res = ItemResult(city, mat_id, spec["name"], "no-data", current)
        spec = dict(spec, row_words=ROW_WORDS.get(mat_id, spec["keywords"]))
        q = spec["query"].format(city=city)
        n_log = len(SEARCH_LOG)
        try:
            hits = self.search(q)
        except Exception as exc:  # noqa: BLE001
            hits = []
            res.notes.append(f"search failed: {exc}")
        if report is not None:
            report.searches += 1
        res.notes += [f"search - {m}" for m in SEARCH_LOG[n_log:]]
        if not hits:
            res.notes.append("the search engines returned nothing - only the known rate pages were read")
        urls, seen = [], set()
        for h in [{"url": u} for u in self.direct.get(mat_id, [])] + list(hits[:MAX_RESULTS]):
            u = h.get("url", "")
            if u and domain_of(u) not in seen:
                seen.add(domain_of(u))
                urls.append(h)
        cands: List[Candidate] = []
        from datetime import date as _date
        for h in urls:
            url = h["url"]
            try:
                text = h.get("content") if h.get("content") and len(h.get("content", "")) > 400 else self._page(url)
                if report is not None:
                    report.pages += 1
            except Exception as exc:  # noqa: BLE001 - blocked / timeout / 404
                res.notes.append(f"could not read {domain_of(url)}: {str(exc)[:60]}")
                continue
            d = page_date(text)
            if d is not None and (_date.today() - d).days > MAX_AGE_DAYS:
                res.notes.append(f"skipped {domain_of(url)}: newest date on the page is {d:%d %b %Y} (too old)")
                continue
            snippet = relevant_snippets(text, spec["keywords"] + spec["row_words"][:6], limit=9000)
            if not snippet:
                continue
            found = verify(self._extract(snippet, spec, city), text, spec, city, url)
            if found:  # one vote per website: its median price (a table with 15 brands must not outvote others)
                found.sort(key=lambda c: c.price)
                local = [c for c in found if c.city != "Pakistan"] or found
                cands.append(local[len(local) // 2])
                if d is not None:
                    cands[-1].date = d.isoformat()
        res.candidates = cands
        comb = combine(cands)
        if comb is None:
            res.notes.append("no verified price found - keeping the current rate")
            return res
        new = round(comb["rate"], 2)
        change = (new / current - 1) * 100 if current else 100.0
        res.new_rate, res.change_pct = new, round(change, 2)
        prop = Proposal(city, mat_id, spec["name"], current, new, comb["low"], comb["high"], spec["unit"], round(change, 2),
                        [{"url": c.url, "domain": c.domain, "quote": c.quote, "price": c.price, "raw": f"{c.raw_price:g} {c.raw_unit}",
                          "trusted": c.trusted, "city": c.city} for c in comb["kept"]],
                        created=date.today().isoformat())
        if abs(change) > self.reject_pct:
            res.status = "rejected"
            res.notes.append(f"change {change:+.1f}% is too large to trust automatically - check the sources manually")
            prop.reason = "outlier"
            self.book.add_pending(prop)  # still visible to the admin, flagged
            return res
        if abs(change) < 0.5 and self.book.live_entry(mat_id, city) is not None:
            res.status = "unchanged"
            prop.reason = "confirmed"
            self.book.approve(prop, by="agent (confirmed)")
            return res
        if abs(change) < self.auto_pct and (comb["trusted"] or comb["agree"] or len(comb["domains"]) >= 2):
            prop.reason = f"auto: {change:+.1f}% from {', '.join(comb['domains'][:3])}"
            self.book.approve(prop, by="agent (auto)")
            res.status = "auto-approved"
        else:
            prop.reason = (f"{change:+.1f}% vs current" + ("" if (comb["trusted"] or comb["agree"])
                                                           else " - single untrusted source"))
            self.book.add_pending(prop)
            res.status = "pending"
        return res

    def run(self, cities: Optional[List[str]] = None, items: Optional[List[str]] = None, save: bool = True) -> RunReport:
        report = RunReport(started=time.strftime("%Y-%m-%d %H:%M"))
        for city in cities or CITIES:
            for mid in items or list(LIVE_ITEMS):
                if LIVE_ITEMS[mid].get("national") and city != (cities or CITIES)[0]:
                    continue  # national prices are searched once
                self.log(f"{city}: {LIVE_ITEMS[mid]['name']}")
                report.results.append(self.update_item(mid, city, report))
        if save:
            self.book.save()
        return report
