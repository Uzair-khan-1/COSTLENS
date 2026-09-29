"""
Simple inline SVG illustrations for a non-technical audience (land owners, small contractors).
All drawings are generated in code - no image files, no external requests - and use the app palette.
"""
from __future__ import annotations

from html import escape
from typing import List, Optional, Tuple

NAVY, TEAL, GOLD, SKY, SAND, GREY = "#0B1E3D", "#0D9488", "#FBBF24", "#DCEBFA", "#F5E6C8", "#94A3B8"


def _svg(w: int, h: int, body: str, max_w: Optional[int] = None, panel: bool = True) -> str:
    """Every illustration sits on its own light rounded panel, so it stays readable in light AND dark themes."""
    mw = f"max-width:{max_w or w}px;" if max_w is not False else ""
    bg = f'<rect x="0" y="0" width="{w}" height="{h}" rx="12" fill="#F8FAFC"/>' if panel else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" style="{mw}display:block;'
            f'margin:auto;font-family:Arial,sans-serif">{bg}{body}</svg>')


# ---------------------------------------------------------------------------
# "What do you have?" cards
# ---------------------------------------------------------------------------
def card_cad() -> str:
    grid = "".join(f'<line x1="{x}" y1="18" x2="{x}" y2="102" stroke="#9EC5F0" stroke-width="0.6"/>' for x in range(30, 170, 12))
    grid += "".join(f'<line x1="22" y1="{y}" x2="178" y2="{y}" stroke="#9EC5F0" stroke-width="0.6"/>' for y in range(26, 102, 12))
    rooms = ('<rect x="40" y="32" width="120" height="60" fill="none" stroke="white" stroke-width="3"/>'
             '<line x1="95" y1="32" x2="95" y2="92" stroke="white" stroke-width="2"/>'
             '<line x1="40" y1="62" x2="95" y2="62" stroke="white" stroke-width="2"/>'
             '<text x="66" y="52" font-size="8" fill="white" text-anchor="middle">BED 12x13</text>'
             '<text x="127" y="65" font-size="8" fill="white" text-anchor="middle">LOUNGE</text>'
             '<line x1="40" y1="100" x2="160" y2="100" stroke="white" stroke-width="1"/>'
             '<text x="100" y="98" font-size="7" fill="white" text-anchor="middle">33\'-0"</text>')
    return _svg(200, 120, f'<rect x="18" y="14" width="164" height="92" rx="4" fill="#1E5AA8"/>{grid}{rooms}', 220)


def card_sketch() -> str:
    body = ('<rect x="30" y="12" width="140" height="96" rx="3" fill="#FFFDF5" stroke="#D6C9A8"/>'
            '<path d="M50 30 L150 31 L149 90 L51 89 Z" fill="none" stroke="#475569" stroke-width="2" stroke-linejoin="round"/>'
            '<path d="M98 31 L99 89 M51 58 L98 60" fill="none" stroke="#475569" stroke-width="1.6"/>'
            '<text x="72" y="48" font-size="8" fill="#1D4ED8" font-style="italic">bed 12x13</text>'
            '<text x="110" y="62" font-size="8" fill="#1D4ED8" font-style="italic">lounge</text>'
            '<text x="62" y="78" font-size="8" fill="#1D4ED8" font-style="italic">bath</text>'
            '<g transform="rotate(35 160 95)"><rect x="140" y="90" width="44" height="8" fill="' + GOLD + '"/>'
            '<polygon points="184,90 194,94 184,98" fill="#F5D0A9"/><rect x="136" y="90" width="5" height="8" fill="#F87171"/></g>')
    return _svg(200, 120, body, 220)


def card_idea() -> str:
    body = ('<circle cx="100" cy="46" r="26" fill="#FEF3C7" stroke="' + GOLD + '" stroke-width="3"/>'
            '<path d="M86 50 L100 36 L114 50 L114 62 L86 62 Z" fill="white" stroke="' + NAVY + '" stroke-width="2"/>'
            '<rect x="96" y="52" width="8" height="10" fill="' + TEAL + '"/>'
            '<rect x="91" y="74" width="18" height="10" rx="2" fill="' + GREY + '"/>'
            + "".join(f'<line x1="{100 + 36 * c}" y1="{46 + 36 * s}" x2="{100 + 44 * c}" y2="{46 + 44 * s}" stroke="{GOLD}" '
                      f'stroke-width="3" stroke-linecap="round"/>'
                      for c, s in ((1, 0), (-1, 0), (0.7, -0.7), (-0.7, -0.7), (0, -1)))
            + '<text x="100" y="106" font-size="10" fill="' + NAVY + '" text-anchor="middle">"5 marla, 4 bedrooms..."</text>')
    return _svg(200, 120, body, 220)


# ---------------------------------------------------------------------------
# how it works strip
# ---------------------------------------------------------------------------
def how_it_works() -> str:
    steps = [("Your project", "drawings & city", "plot"), ("Your design", "we read it", "doc"),
             ("Your scope", "what you want", "check"), ("Materials & BOQ", "what to buy", "list"), ("Download", "Excel, PDF, WhatsApp", "down")]
    icons = {
        "plot": '<rect x="-16" y="-12" width="32" height="24" fill="#E6F4E1" stroke="{c}" stroke-width="2"/><rect x="-9" y="-6" width="14" height="12" fill="{c}"/>',
        "doc": '<rect x="-12" y="-15" width="24" height="30" rx="2" fill="white" stroke="{c}" stroke-width="2"/><path d="M-7 -6 H7 M-7 0 H7 M-7 6 H3" stroke="{c}" stroke-width="2"/>',
        "check": '<circle r="15" fill="white" stroke="{c}" stroke-width="2"/><path d="M-7 0 L-2 6 L8 -6" fill="none" stroke="{c}" stroke-width="3"/>',
        "list": '<rect x="-12" y="-15" width="24" height="30" rx="2" fill="white" stroke="{c}" stroke-width="2"/><path d="M-6 -7 H8 M-6 0 H8 M-6 7 H8" stroke="{c}" stroke-width="2"/><circle cx="-9" cy="-7" r="1.5" fill="{c}"/><circle cx="-9" cy="0" r="1.5" fill="{c}"/><circle cx="-9" cy="7" r="1.5" fill="{c}"/>',
        "down": '<path d="M0 -14 V6 M-8 -2 L0 6 L8 -2" fill="none" stroke="{c}" stroke-width="3"/><path d="M-12 10 H12" stroke="{c}" stroke-width="3"/>',
    }
    parts = []
    n = len(steps)
    for i, (t, sub, ic) in enumerate(steps):
        x = 60 + i * 150
        parts.append(f'<g transform="translate({x},40)"><circle r="28" fill="{SKY}"/>{icons[ic].format(c=NAVY)}</g>')
        parts.append(f'<circle cx="{x + 20}" cy="18" r="10" fill="{GOLD}"/><text x="{x + 20}" y="22" font-size="11" '
                     f'font-weight="bold" text-anchor="middle" fill="{NAVY}">{i + 1}</text>')
        parts.append(f'<text x="{x}" y="86" font-size="13" font-weight="bold" text-anchor="middle" fill="{NAVY}">{escape(t)}</text>')
        parts.append(f'<text x="{x}" y="102" font-size="11" text-anchor="middle" fill="#64748B">{escape(sub)}</text>')
        if i < n - 1:
            parts.append(f'<path d="M{x + 36} 40 H{x + 112}" stroke="{GREY}" stroke-width="2" stroke-dasharray="4 4"/>'
                         f'<polygon points="{x + 112},35 {x + 120},40 {x + 112},45" fill="{GREY}"/>')
    return _svg(720, 112, "".join(parts), 760)


# ---------------------------------------------------------------------------
# plot & house
# ---------------------------------------------------------------------------
def plot_diagram(width_ft: float, depth_ft: float, marla: float, marla_sqft: float,
                 footprint: Optional[Tuple[float, float]] = None) -> str:
    """Top view of the plot with its size, the road in front and the typical covered area."""
    maxw, maxh = 220, 220
    s = min(maxw / max(width_ft, 1), maxh / max(depth_ft, 1))
    W, D = width_ft * s, depth_ft * s
    x0, y0 = 60 + (maxw - W) / 2, 30
    body = [f'<rect x="{x0}" y="{y0}" width="{W:.1f}" height="{D:.1f}" fill="#E6F4E1" stroke="{NAVY}" stroke-width="2.5" stroke-dasharray="6 3"/>']
    if footprint:
        cw, cd = footprint
        fw, fd = min(cw, width_ft) * s, min(cd, depth_ft) * s
        fy = y0 + D - fd - (D - fd) * 0.15  # house sits towards the back, open space in front (porch / lawn)
        body.append(f'<rect x="{x0 + (W - fw) / 2:.1f}" y="{fy:.1f}" width="{fw:.1f}" height="{fd:.1f}" fill="{SKY}" '
                    f'stroke="{NAVY}" stroke-width="1.5"/>')
        body.append(f'<text x="{x0 + W / 2:.1f}" y="{fy + fd / 2 + 4:.1f}" font-size="11" text-anchor="middle" fill="{NAVY}">house</text>')
    body.append(f'<rect x="20" y="{y0 + D + 8:.1f}" width="300" height="22" fill="#CBD5E1"/>'
                f'<text x="170" y="{y0 + D + 23:.1f}" font-size="11" text-anchor="middle" fill="#334155">ROAD / STREET</text>')
    # dimension lines
    body.append(f'<path d="M{x0} {y0 - 8} H{x0 + W}" stroke="{TEAL}" stroke-width="1.5"/>'
                f'<text x="{x0 + W / 2:.1f}" y="{y0 - 11}" font-size="12" font-weight="bold" text-anchor="middle" fill="{TEAL}">{width_ft:.0f} ft</text>')
    body.append(f'<path d="M{x0 + W + 10:.1f} {y0} V{y0 + D:.1f}" stroke="{TEAL}" stroke-width="1.5"/>'
                f'<text x="{x0 + W + 14:.1f}" y="{y0 + D / 2:.1f}" font-size="12" font-weight="bold" fill="{TEAL}">{depth_ft:.0f} ft</text>')
    body.append(f'<text x="170" y="{y0 + D + 50:.1f}" font-size="12" text-anchor="middle" fill="{NAVY}">'
                f'{marla:g} marla = {marla * marla_sqft:,.0f} sq ft</text>')
    return _svg(340, int(y0 + D + 60), "".join(body), 300)


def house_elevation(storeys: int, mumty: bool = True) -> str:
    fh = 34
    W = 150
    x0 = 25
    ground = 30 + fh * storeys + (26 if mumty else 0)
    parts = []
    for i in range(storeys):
        y = ground - fh * (i + 1)
        parts.append(f'<rect x="{x0}" y="{y}" width="{W}" height="{fh}" fill="{SAND}" stroke="{NAVY}" stroke-width="2"/>')
        for wx in (x0 + 18, x0 + 62, x0 + 106):
            parts.append(f'<rect x="{wx}" y="{y + 9}" width="24" height="16" fill="{SKY}" stroke="{NAVY}" stroke-width="1.2"/>')
        parts.append(f'<text x="{x0 + W + 8}" y="{y + fh / 2 + 4}" font-size="10" fill="#64748B">'
                     f'{["Ground", "First", "Second"][i]}</text>')
    top = ground - fh * storeys
    parts.append(f'<rect x="{x0 - 4}" y="{top - 6}" width="{W + 8}" height="6" fill="{NAVY}"/>')
    if mumty:
        parts.append(f'<rect x="{x0 + W - 52}" y="{top - 30}" width="44" height="24" fill="{SAND}" stroke="{NAVY}" stroke-width="2"/>'
                     f'<rect x="{x0 + W - 36}" y="{top - 22}" width="12" height="16" fill="{TEAL}"/>'
                     f'<text x="{x0 + W + 8}" y="{top - 14}" font-size="10" fill="#64748B">Mumty</text>')
    parts.append(f'<rect x="{x0 + 62}" y="{ground - 24}" width="22" height="24" fill="{TEAL}"/>')
    parts.append(f'<line x1="5" y1="{ground}" x2="215" y2="{ground}" stroke="#475569" stroke-width="3"/>')
    return _svg(230, ground + 8, "".join(parts), 200)


# ---------------------------------------------------------------------------
# small pictograms for results
# ---------------------------------------------------------------------------
MATERIAL_ICON = {"Cement": "\U0001f9f1", "Steel": "\U0001f529", "Bricks": "\U0001f9f1", "Sand": "\u26f1\ufe0f", "Crush": "\U0001faa8",
                 "Tiles": "\U0001f7eb", "Paint": "\U0001f3a8", "Wiring": "\U0001f50c"}


def stat_cards_html(items: List[Tuple[str, str, str, str]]) -> str:
    """items: (emoji, title, value, sub) -> responsive card grid (HTML)."""
    cards = "".join(
        f'<div style="flex:1 1 150px;min-width:140px;background:white;border:1px solid #E2E8F0;border-radius:14px;'
        f'padding:12px 14px;box-shadow:0 1px 3px rgba(15,23,42,.06)">'
        f'<div style="font-size:26px;line-height:1">{e}</div>'
        f'<div style="font-size:12.5px;color:#64748B;margin-top:6px">{escape(t)}</div>'
        f'<div style="font-size:21px;font-weight:700;color:{NAVY};margin-top:2px">{escape(v)}</div>'
        f'<div style="font-size:11.5px;color:#94A3B8">{escape(s)}</div></div>'
        for e, t, v, s in items)
    return f'<div style="display:flex;flex-wrap:wrap;gap:10px;margin:6px 0 12px 0">{cards}</div>'


def tip_box_html(title: str, lines: List[str], urdu: str = "") -> str:
    lis = "".join(f"<li style='margin:2px 0'>{escape(x)}</li>" for x in lines)
    ur = (f"<div dir='rtl' style='font-size:13px;color:#475569;margin-top:4px;font-family:\"Noto Nastaliq Urdu\",serif'>"
          f"{escape(urdu)}</div>") if urdu else ""
    return (f'<div style="background:#F0FDFA;border:1px solid #99F6E4;border-left:5px solid {TEAL};border-radius:12px;'
            f'padding:10px 14px;margin:4px 0 14px 0"><div style="font-weight:700;color:{NAVY}">\U0001f4a1 {escape(title)}</div>'
            f'<ul style="margin:6px 0 0 18px;padding:0;color:#334155;font-size:14px">{lis}</ul>{ur}</div>')
