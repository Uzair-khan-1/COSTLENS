"""
Importer for Pakistani government rate books (PDF with a text layer):

  * Punjab "Market Rate System" (MRS), Finance Department - one district per book, bi-annual
      Sr. | Description | Unit | Labour | Composite | Unit | Labour | Composite | Spec | Remarks
  * Khyber Pakhtunkhwa MRS (MRS Cell, Finance Department) - item codes like 06-07-a-03
      Item Code | Description | Unit | Labour | Composite | Unit | Labour | Composite | Spec | Remarks
  * Sindh Composite Schedule of Rates (CSR), Standing Rates Committee - one unit system
      S.No. | Description | Unit | Labour | Composite | Specification | Remarks

The parser reads words with their x-positions (PyMuPDF), finds the columns from each page's header row
("Unit", "Labour", "Composite"), and rebuilds ITEM BLOCKS: every line of an item's description (before and
after the line that carries the rates) belongs to the item; sub-items (a), (i) ... get their own text. Each
rate line becomes one record with the full description, so items can be found by their wording
(pricing/government.py) in any edition or province.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

_NUM = re.compile(r"^-?\d[\d,]*\.?\d*$")
_EDITION = re.compile(r"(\d)(?:st|nd|rd|th)\s*BI-?ANNUAL[-\s]*(\d{4})", re.I)
_EDITION_KP = re.compile(r"MRS-?\s*(\d{4})\s*\(\s*(\d)\s*(?:st|nd|rd|th)?\s*BI-?ANNUAL", re.I)
_DISTRICT = re.compile(r"DISTRICT\s+([A-Z][A-Z ]+)")
_CHAPTER = re.compile(r"(?:chapter|chap)\s*[-#:]*\s*(\d+)\s*[(:]?\s*([A-Za-z][A-Za-z &,]*)", re.I)
_KP_CODE = re.compile(r"^\d{2}-\d{2}(?:-[a-z0-9]+)*$", re.I)
_SUB = re.compile(r"^\(?([ivx]{1,5}|[a-z])\)\s*(.*)$")


@dataclass
class MRSItem:
    chapter: int
    chapter_name: str
    item_no: str
    sub: str
    description: str
    unit: str
    labour: Optional[float]
    composite: Optional[float]
    unit_m: str
    labour_m: Optional[float]
    composite_m: Optional[float]
    page: int


def _num(t: str) -> Optional[float]:
    try:
        return float(t.replace(",", "").strip())
    except ValueError:
        return None


def _lines(words, tol=2.5):
    rows: List[list] = []
    for w in sorted(words, key=lambda w: (round(w[1]), w[0])):
        if rows and abs(rows[-1][0] - w[1]) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([w[1], [w]])
    return [(y, sorted(ws, key=lambda w: w[0])) for y, ws in rows]


def _identify(first: str) -> dict:
    t = re.sub(r"\s+", " ", first)
    up = t.upper()
    if "KHYBER" in up or "PESHAWAR" in up:
        m = _EDITION_KP.search(t)
        return {"book": "KP MRS", "province": "Khyber Pakhtunkhwa", "district": "Peshawar",
                "edition": f"{m.group(1)}-{m.group(2)}" if m else "unknown"}
    if "SINDH" in up:
        y = re.search(r"SCHEDULE OF RATES\s*(\d{4})", up) or re.search(r"(20\d\d)", up)
        return {"book": "Sindh CSR", "province": "Sindh", "district": "Karachi", "edition": y.group(1) if y else "unknown"}
    m = _EDITION.search(t)
    dm = re.search(r"DISTRICT\s+([A-Z][A-Z ]*?)\s*(?:\n|$)", first.upper())
    return {"book": "Punjab MRS", "province": "Punjab", "district": dm.group(1).strip().title() if dm else "Unknown",
            "edition": f"{m.group(2)}-{m.group(1)}" if m else "unknown"}


def parse_mrs(pdf_path: str) -> dict:
    import pymupdf
    doc = pymupdf.open(pdf_path)
    first = "\n".join(doc[i].get_text() for i in range(min(4, len(doc))))
    meta = _identify(first)
    items: List[MRSItem] = []
    chapter, chapter_name = 0, ""
    block: Optional[dict] = None
    last_unit = [""]

    def flush():
        if not block or not block["rates"]:
            return
        pre = re.sub(r"\s+", " ", " ".join(block["pre"])).strip()
        if len(pre) > 360:  # long general wording: keep the start; the specific parts (sub-item, ratio) must survive
            pre = pre[:360] + "..."
        for r in block["rates"]:
            parts = [pre]
            if r["sub"]:
                parts.append(" ".join(block["subs"].get(r["sub"], [])))
            elif not block["subs"]:
                parts.append(" ".join(block["post"]))  # single item: text after the rate line belongs to it
            if r["label"]:
                parts.append(r["label"])
            desc = re.sub(r"\s+", " ", " - ".join(p for p in parts if p)).strip()
            same = [i for i in items if i.chapter == block["chapter"] and i.item_no == block["no"]]
            sub = r["sub"]
            if any(i.sub == sub or i.sub.startswith(sub + ".") for i in same):
                n = sum(1 for i in same if i.sub == sub or i.sub.startswith(sub + "."))
                sub = f"{sub}.{n}" if sub else str(n)
            items.append(MRSItem(block["chapter"], block["chapter_name"], block["no"], sub, desc[:900], r["unit"], r["lab"],
                                 r["comp"], r["unit_m"], r["lab_m"], r["comp_m"], r["page"]))

    for pno, page in enumerate(doc, 1):
        words = page.get_text("words")
        h = page.rect.height
        cm = _CHAPTER.search(" ".join(w[4] for w in words if w[1] > h * 0.88 or w[1] < h * 0.18))
        if cm:
            chapter, chapter_name = int(cm.group(1)), cm.group(2).strip()[:40]
        hdr = [w for w in words if w[4] in ("Labour", "Composite", "Unit")]
        labs = [w for w in hdr if w[4] == "Labour"]
        if labs:  # the header row only - "Composite" also appears inside remarks text
            y0 = min(w[1] for w in labs)
            hdr = [w for w in hdr if abs(w[1] - y0) < 8]
        lab = sorted(w[0] for w in hdr if w[4] == "Labour")
        comp = sorted(w[0] for w in hdr if w[4] == "Composite")
        unit = sorted(w[0] for w in hdr if w[4] == "Unit")
        if not lab or not comp:
            continue
        head_y = max(w[3] for w in hdr if w[4] in ("Labour", "Composite"))
        dx = [w[0] for w in words if w[4] == "Description" and w[1] < head_y + 5]
        x_item = (min(dx) - 2) if dx else 60  # item numbers sit left of the description column
        two = len(lab) >= 2 and len(comp) >= 2
        x_unit = (unit[0] - 14) if unit else lab[0] - 50
        x_lab, x_comp = lab[0] - 14, comp[0] - 10
        if two:
            x_unit_m = (unit[1] - 12) if len(unit) > 1 else comp[0] + 45
            x_lab_m, x_comp_m = lab[1] - 14, comp[1] - 10
        else:
            x_unit_m = x_lab_m = x_comp_m = comp[0] + 55
        x_end = (x_comp_m if two else x_comp) + 62
        for _y, ws in _lines([w for w in words if head_y + 2 < w[1] < h * 0.93]):
            desc_w = [w for w in ws if w[0] < x_unit]
            cols: Dict[str, List[str]] = {k: [] for k in ("unit", "lab", "comp", "unit_m", "lab_m", "comp_m")}
            for w in ws:
                x = w[0]
                if x < x_unit:
                    continue
                if x < x_lab:
                    cols["unit"].append(w[4])
                elif x < x_comp:
                    cols["lab"].append(w[4])
                elif not two and x < x_end:
                    cols["comp"].append(w[4])
                elif two and x < x_unit_m:
                    cols["comp"].append(w[4])
                elif two and x < x_lab_m:
                    cols["unit_m"].append(w[4])
                elif two and x < x_comp_m:
                    cols["lab_m"].append(w[4])
                elif two and x < x_end:
                    cols["comp_m"].append(w[4])
            toks = [w[4] for w in desc_w]

            def num(k):
                return next((_num(t) for t in cols[k] if _NUM.match(t.replace(",", ""))), None)

            lab_v, comp_v = num("lab"), num("comp")
            has_rate = lab_v is not None or comp_v is not None
            if toks and ws[0][0] < x_item and (re.fullmatch(r"\d{1,3}", toks[0]) or _KP_CODE.match(toks[0])):
                flush()
                block = {"no": toks[0], "chapter": chapter, "chapter_name": chapter_name, "pre": [" ".join(toks[1:])],
                         "post": [], "subs": {}, "sub": "", "rates": []}
                toks = []
            if block is None:
                continue
            text = " ".join(toks).strip()
            label = ""
            if text:
                sm = _SUB.match(text)
                if sm:
                    block["sub"] = sm.group(1)
                    block["subs"].setdefault(block["sub"], []).append(sm.group(2))
                elif has_rate and (block["rates"] or block["sub"]):
                    label = text  # "Ratio 1:4" next to its own rates
                elif block["sub"]:
                    block["subs"][block["sub"]].append(text)
                elif block["rates"]:
                    block["post"].append(text)
                else:
                    block["pre"].append(text)
            if has_rate:
                u = " ".join(cols["unit"]).strip()
                if re.fullmatch(r"(?i)-?do-?|ditto|\"", u) or (not u and block["rates"]):
                    u = block["rates"][-1]["unit"] if block["rates"] else last_unit[0]
                last_unit[0] = u or last_unit[0]
                block["rates"].append({"sub": block["sub"], "label": label, "unit": u,
                                       "lab": lab_v, "comp": comp_v, "unit_m": " ".join(cols["unit_m"]).strip(),
                                       "lab_m": num("lab_m"), "comp_m": num("comp_m"), "page": pno})
    flush()
    return {"source": Path(pdf_path).name, **meta, "items": [asdict(i) for i in items]}


def save(data: dict, folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"mrs_{data['district'].lower().replace(' ', '_')}_{data['edition']}.json"
    p.write_text(json.dumps(data, indent=0, ensure_ascii=False), encoding="utf-8")
    return p


def load_all(folder: Path) -> Dict[str, dict]:
    """{district: latest edition data}"""
    out: Dict[str, dict] = {}
    for p in sorted(Path(folder).glob("mrs_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cur = out.get(d["district"])
        if cur is None or d["edition"] > cur["edition"]:
            out[d["district"]] = d
    return out


if __name__ == "__main__":  # python -m pricing.mrs path/to/book.pdf
    import sys
    data = parse_mrs(sys.argv[1])
    path = save(data, Path(__file__).resolve().parent.parent / "data" / "rates")
    print(f"{data.get('book')} {data['district']} {data['edition']}: {len(data['items'])} items -> {path}")
