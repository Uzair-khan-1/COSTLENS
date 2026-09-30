"""
Importer for the Punjab Finance Department "Market Rate System" (MRS) PDF - one district, one edition.

The MRS lists, for every item of work, a LABOUR rate and a COMPOSITE (labour + materials) rate in British
and metric units. The PDF has a text layer with fixed columns:

    Sr. | Description | Unit | Labour | Composite | Unit | Labour | Composite | Spec. No. | Remarks

The parser reads the words with their x-positions (PyMuPDF), finds the column positions from each page's
header row, and rebuilds items: item number, parent description, sub-item (i, ii, a, b ...), unit and rates.
The result is saved as JSON (data/rates/mrs_<district>_<edition>.json) and used by pricing/government.py.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

_NUM = re.compile(r"^-?\d[\d,]*\.?\d*$")
_EDITION = re.compile(r"MRS,?\s*(\d)(?:st|nd|rd|th)\s*BI-?ANNUAL-?(\d{4})", re.I)
_DISTRICT = re.compile(r"DISTRICT\s+([A-Z][A-Z ]+)")
_CHAPTER = re.compile(r"(?:chapter|chap)-?\s*(\d+)\s*\(([^)]*)\)", re.I)


@dataclass
class MRSItem:
    chapter: int
    chapter_name: str
    item_no: str
    sub: str
    description: str  # parent description + sub-item text
    unit: str
    labour: Optional[float]
    composite: Optional[float]
    unit_m: str
    labour_m: Optional[float]
    composite_m: Optional[float]
    page: int

    @property
    def key(self) -> str:
        return f"{self.chapter}-{self.item_no}{('-' + self.sub) if self.sub else ''}"


def _num(t: str) -> Optional[float]:
    t = t.replace(",", "").strip()
    try:
        return float(t)
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


def parse_mrs(pdf_path: str) -> dict:
    import pymupdf
    doc = pymupdf.open(pdf_path)
    first = "\n".join(doc[i].get_text() for i in range(min(3, len(doc))))
    m = _EDITION.search(first)
    edition = f"{m.group(2)}-{m.group(1)}" if m else "unknown"
    dm = _DISTRICT.search(first)
    district = dm.group(1).strip().title() if dm else "Unknown"
    items: List[MRSItem] = []
    chapter, chapter_name = 0, ""
    item_no, parent, sub, sub_text = "", "", "", ""
    for pno, page in enumerate(doc, 1):
        words = page.get_text("words")
        foot = [w for w in words if w[1] > page.rect.height * 0.9]
        cm = _CHAPTER.search(" ".join(w[4] for w in foot))
        if cm:
            chapter, chapter_name = int(cm.group(1)), cm.group(2).strip()
        hdr = [w for w in words if w[4] in ("Labour", "Composite", "Unit")]
        lab = sorted(w[0] for w in hdr if w[4] == "Labour")
        comp = sorted(w[0] for w in hdr if w[4] == "Composite")
        unit = sorted(w[0] for w in hdr if w[4] == "Unit")
        if len(lab) < 2 or len(comp) < 2:
            continue
        head_y = max(w[3] for w in hdr)
        x_unit = unit[0] - 12 if unit else lab[0] - 45
        x_lab, x_comp = lab[0] - 12, comp[0] - 8
        x_unit_m = unit[1] - 10 if len(unit) > 1 else comp[0] + 45
        x_lab_m, x_comp_m = lab[1] - 12, comp[1] - 8
        x_spec = x_comp_m + 60
        for _y, ws in _lines([w for w in words if w[1] > head_y + 2 and w[1] < page.rect.height * 0.9]):
            desc = [w[4] for w in ws if w[0] < x_unit]
            cols = {"unit": [], "lab": [], "comp": [], "unit_m": [], "lab_m": [], "comp_m": []}
            for w in ws:
                x = w[0]
                if x < x_unit:
                    continue
                if x < x_lab:
                    cols["unit"].append(w[4])
                elif x < x_comp:
                    cols["lab"].append(w[4])
                elif x < x_unit_m:
                    cols["comp"].append(w[4])
                elif x < x_lab_m:
                    cols["unit_m"].append(w[4])
                elif x < x_comp_m:
                    cols["lab_m"].append(w[4])
                elif x < x_spec:
                    cols["comp_m"].append(w[4])
            text = " ".join(desc).strip()
            lab_v = next((_num(t) for t in cols["lab"] if _NUM.match(t.replace(",", ""))), None)
            comp_v = next((_num(t) for t in cols["comp"] if _NUM.match(t.replace(",", ""))), None)
            has_rate = lab_v is not None or comp_v is not None
            row_label = ""
            # new item: line starts with its number at the left margin
            if desc and re.fullmatch(r"\d{1,3}", desc[0]) and ws[0][0] < 40:
                item_no, parent, sub, sub_text = desc[0], " ".join(desc[1:]), "", ""
            elif desc:
                sm = re.match(r"^\(?([ivx]{1,5}|[a-z])\)\s*(.*)$", text)
                if sm:
                    sub, sub_text = sm.group(1), sm.group(2)
                elif has_rate:
                    row_label = text  # e.g. "Ratio 1:4" - belongs to this rate line only
                elif sub:
                    sub_text = (sub_text + " " + text).strip()
                else:
                    parent = (parent + " " + text).strip()
            if not has_rate or not item_no:
                continue
            lab_m = next((_num(t) for t in cols["lab_m"] if _NUM.match(t.replace(",", ""))), None)
            comp_m = next((_num(t) for t in cols["comp_m"] if _NUM.match(t.replace(",", ""))), None)
            u = " ".join(cols["unit"]).strip()  # keep "100" in "100 Sft." - it is part of the unit
            um = " ".join(cols["unit_m"]).strip()
            parts = [parent]
            if sub:
                parts.append(sub_text)
            if row_label:
                parts.append(row_label)
            description = " - ".join(x for x in parts if x).strip()
            same = [i for i in items if i.chapter == chapter and i.item_no == item_no]
            key_sub = sub
            if any(i.sub == sub or i.sub.startswith(sub + ".") for i in same) and (row_label or not sub):
                key_sub = f"{sub}.{sum(1 for i in same if i.sub == sub or i.sub.startswith(sub + '.'))}" if sub \
                    else str(len(same))
            items.append(MRSItem(chapter, chapter_name, item_no, key_sub, re.sub(r"\s+", " ", description)[:400],
                                 u or "", lab_v, comp_v, um or "", lab_m, comp_m, pno))
    return {"source": Path(pdf_path).name, "district": district, "edition": edition,
            "items": [asdict(i) for i in items]}


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


if __name__ == "__main__":  # python -m pricing.mrs path/to/MRS.pdf
    import sys
    data = parse_mrs(sys.argv[1])
    path = save(data, Path(__file__).resolve().parent.parent / "data" / "rates")
    print(f"{data['district']} {data['edition']}: {len(data['items'])} items -> {path}")
