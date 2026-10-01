import cairosvg

def cuboid(x, y, w, d, h, top, left, right):
    """Isometric block: (x,y) = front-bottom corner on screen; w along +x/-y, d along -x/-y, h up."""
    import math
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    def P(a, b, z):  # a along width axis, b along depth axis, z up
        return (x + a * c - b * c, y - a * s - b * s - z)
    A0, B0, C0, D0 = P(0, 0, 0), P(w, 0, 0), P(w, d, 0), P(0, d, 0)
    A1, B1, C1, D1 = P(0, 0, h), P(w, 0, h), P(w, d, h), P(0, d, h)
    pts = lambda *ps: " ".join(f"{px:.1f},{py:.1f}" for px, py in ps)
    return (f'<polygon points="{pts(A0, A1, D1, D0)}" fill="{left}"/>'
            f'<polygon points="{pts(A0, B0, B1, A1)}" fill="{right}"/>'
            f'<polygon points="{pts(A1, B1, C1, D1)}" fill="{top}"/>')

NAVY, NAVY2, NAVY3 = "#1B2F5B", "#26417A", "#3A5C9E"

def mark(dark=False):
    blocks = (cuboid(205, 252, 140, 86, 32, "#4A6FB5", NAVY, NAVY2) +
              cuboid(218, 214, 98, 64, 32, "#5B82C8", NAVY, NAVY2) +
              cuboid(230, 176, 58, 44, 38, "#7DA2DE", NAVY2, NAVY3))
    coin = ('<g transform="translate(150,330)">'
            '<circle r="50" fill="url(#gold)"/><circle r="40" fill="none" stroke="#FFF3CF" stroke-opacity=".7" stroke-width="4"/>'
            '<text x="0" y="13" text-anchor="middle" font-family="Poppins" font-weight="700" font-size="38" fill="#7A4B00">Rs</text></g>')
    cal = ('<g transform="translate(250,286)">'
           '<rect x="0" y="0" width="128" height="112" rx="16" fill="#FFFFFF" stroke="url(#lens)" stroke-width="10"/>'
           '<rect x="0" y="0" width="128" height="32" rx="14" fill="url(#lens)"/>'
           '<rect x="22" y="-14" width="12" height="28" rx="6" fill="' + NAVY + '"/><rect x="94" y="-14" width="12" height="28" rx="6" fill="' + NAVY + '"/>'
           '<rect x="18" y="48" width="54" height="9" rx="4.5" fill="#2E86DE"/><rect x="82" y="48" width="26" height="9" rx="4.5" fill="#9CC9F2"/>'
           '<rect x="18" y="66" width="38" height="9" rx="4.5" fill="#9CC9F2"/><rect x="64" y="66" width="44" height="9" rx="4.5" fill="#2E86DE"/>'
           '<path d="M24 90 l10 10 l20 -22" fill="none" stroke="#16A34A" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/></g>')
    ring = ('<path d="M 236 58 A 172 172 0 1 1 82 150" fill="none" stroke="url(#lens)" stroke-width="28" stroke-linecap="round"/>'
            '<path d="M 120 120 A 150 150 0 0 1 180 78" fill="none" stroke="#FFFFFF" stroke-opacity=".55" stroke-width="10" stroke-linecap="round"/>'
            '<line x1="352" y1="352" x2="470" y2="470" stroke="url(#handle)" stroke-width="40" stroke-linecap="round"/>'
            '<line x1="352" y1="352" x2="386" y2="386" stroke="#FFFFFF" stroke-opacity=".25" stroke-width="40" stroke-linecap="round"/>')
    glass = '<circle cx="230" cy="230" r="158" fill="url(#glass)"/>'
    return glass + ring + blocks + coin + cal

DEFS = '''<defs>
<linearGradient id="lens" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2E86DE"/><stop offset="1" stop-color="#14B8A6"/></linearGradient>
<linearGradient id="handle" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1B2F5B"/><stop offset="1" stop-color="#2E86DE"/></linearGradient>
<radialGradient id="glass" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#E8F4FF"/><stop offset="1" stop-color="#E8F4FF" stop-opacity="0"/></radialGradient>
<radialGradient id="gold" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#FFD873"/><stop offset=".7" stop-color="#F4B023"/><stop offset="1" stop-color="#D98E04"/></radialGradient>
<linearGradient id="word" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2E86DE"/><stop offset="1" stop-color="#14B8A6"/></linearGradient>
</defs>'''

def icon_svg():
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">{DEFS}{mark()}</svg>'

def full_svg(dark=False):
    cost = "#FFFFFF" if dark else "#1B2F5B"
    tag = "#C7D7EE" if dark else "#5B6B85"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1500 512" width="1500" height="512">{DEFS}'
            f'<g transform="translate(10,0)">{mark(dark)}</g>'
            f'<text x="540" y="300" font-family="Poppins" font-weight="700" font-size="190" letter-spacing="-4">'
            f'<tspan fill="{cost}">Cost</tspan><tspan fill="url(#word)">Lens</tspan></text>'
            f'<text x="548" y="382" font-family="Poppins" font-weight="500" font-size="44" letter-spacing="9" fill="{tag}">'
            f'MATERIALS <tspan fill="#F4B023">\u2022</tspan> COST <tspan fill="#F4B023">\u2022</tspan> SCHEDULE</text></svg>')

open("costlens_icon.svg", "w").write(icon_svg())
open("costlens_logo.svg", "w").write(full_svg())
open("costlens_logo_on_dark.svg", "w").write(full_svg(True))
cairosvg.svg2png(bytestring=icon_svg().encode(), write_to="costlens_icon.png", output_width=512, output_height=512)
cairosvg.svg2png(bytestring=full_svg().encode(), write_to="costlens_logo.png", output_width=1500, output_height=512)
cairosvg.svg2png(bytestring=full_svg(True).encode(), write_to="costlens_logo_on_dark.png", output_width=1500, output_height=512)
# previews
from PIL import Image
bg = Image.new("RGBA", (1500, 512), "#FFFFFF"); im = Image.open("costlens_logo.png"); bg.alpha_composite(im); bg.convert("RGB").save("preview_light.png")
bg = Image.new("RGBA", (1500, 512), "#13294B"); im = Image.open("costlens_logo_on_dark.png"); bg.alpha_composite(im); bg.convert("RGB").save("preview_dark.png")
