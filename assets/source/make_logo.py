import cairosvg
from PIL import Image

DEFS = '''<defs>
<linearGradient id="lens" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3B9BE8"/><stop offset="1" stop-color="#14B8A6"/></linearGradient>
<linearGradient id="handle" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2E86DE"/><stop offset="1" stop-color="#1B2F5B"/></linearGradient>
<radialGradient id="glass" cx=".38" cy=".32" r=".85"><stop offset="0" stop-color="#24426F"/><stop offset="1" stop-color="#0F1E38"/></radialGradient>
<radialGradient id="gold" cx=".35" cy=".3" r=".85"><stop offset="0" stop-color="#FFE08A"/><stop offset=".65" stop-color="#F4B023"/><stop offset="1" stop-color="#D48A00"/></radialGradient>
<linearGradient id="roof" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5CC8E8"/><stop offset="1" stop-color="#2E86DE"/></linearGradient>
<linearGradient id="word" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#3B9BE8"/><stop offset="1" stop-color="#14B8A6"/></linearGradient>
<clipPath id="wall"><rect x="160" y="250" width="180" height="112"/></clipPath>
</defs>'''

def bricks():
    out = ['<rect x="160" y="250" width="180" height="112" fill="#D9653B"/>', '<g clip-path="url(#wall)" stroke="#FBE3D6" stroke-width="4">']
    for i, y in enumerate(range(250, 370, 22)):
        out.append(f'<line x1="160" y1="{y}" x2="340" y2="{y}"/>')
        off = 0 if i % 2 == 0 else 22
        for x in range(160 + off, 345, 44):
            out.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y + 22}"/>')
    out.append('</g>')
    return "".join(out)

def mark():
    return (
        '<circle cx="250" cy="250" r="170" fill="url(#glass)"/>'
        # house = materials take-off
        '<polygon points="138,258 250,160 362,258" fill="url(#roof)" stroke="#FFFFFF" stroke-width="8" stroke-linejoin="round"/>'
        + bricks() +
        '<rect x="160" y="250" width="180" height="112" fill="none" stroke="#FFFFFF" stroke-width="8"/>'
        '<rect x="226" y="300" width="48" height="62" rx="4" fill="#0F1E38" stroke="#FFFFFF" stroke-width="5"/>'
        '<line x1="120" y1="364" x2="380" y2="364" stroke="#FFFFFF" stroke-width="8" stroke-linecap="round"/>'
        # lens ring + handle
        '<circle cx="250" cy="250" r="170" fill="none" stroke="url(#lens)" stroke-width="30"/>'
        '<path d="M 140 120 A 170 170 0 0 1 220 84" fill="none" stroke="#FFFFFF" stroke-opacity=".55" stroke-width="10" stroke-linecap="round"/>'
        '<line x1="376" y1="376" x2="482" y2="482" stroke="url(#handle)" stroke-width="42" stroke-linecap="round"/>'
        # Rs coin = cost (bottom-left, on the ring)
        '<g transform="translate(112,392)"><circle r="66" fill="#FFFFFF"/><circle r="58" fill="url(#gold)"/>'
        '<circle r="47" fill="none" stroke="#FFF3CF" stroke-opacity=".8" stroke-width="4"/>'
        '<text x="0" y="16" text-anchor="middle" font-family="Poppins" font-weight="800" font-size="46" fill="#6B3F00">Rs</text></g>'
        # calendar = schedule (top-right, on the ring)
        '<g transform="translate(334,58)">'
        '<rect x="-8" y="-8" width="148" height="140" rx="24" fill="#FFFFFF"/>'
        '<rect x="0" y="0" width="132" height="124" rx="18" fill="#FFFFFF" stroke="url(#lens)" stroke-width="8"/>'
        '<rect x="0" y="0" width="132" height="38" rx="16" fill="url(#lens)"/><rect x="0" y="22" width="132" height="16" fill="url(#lens)"/>'
        '<rect x="26" y="-16" width="14" height="32" rx="7" fill="#1B2F5B"/><rect x="92" y="-16" width="14" height="32" rx="7" fill="#1B2F5B"/>'
        '<path d="M34 82 l18 18 l44 -44" fill="none" stroke="#16A34A" stroke-width="15" stroke-linecap="round" stroke-linejoin="round"/></g>'
    )

def icon_svg():
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">{DEFS}<g transform="translate(6,6) scale(.97)">{mark()}</g></svg>'

def full_svg(dark=False):
    cost = "#FFFFFF" if dark else "#1B2F5B"
    tag = "#C7D7EE" if dark else "#5B6B85"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1500 512" width="1500" height="512">{DEFS}'
            f'<g transform="translate(10,6) scale(.97)">{mark()}</g>'
            f'<text x="545" y="298" font-family="Poppins" font-weight="700" font-size="190" letter-spacing="-4">'
            f'<tspan fill="{cost}">Cost</tspan><tspan fill="url(#word)">Lens</tspan></text>'
            f'<text x="553" y="380" font-family="Poppins" font-weight="600" font-size="44" letter-spacing="9" fill="{tag}">'
            f'MATERIALS <tspan fill="#F4B023">\u2022</tspan> COST <tspan fill="#F4B023">\u2022</tspan> SCHEDULE</text></svg>')

for name, svg, w, h in (("costlens_icon", icon_svg(), 512, 512), ("costlens_logo", full_svg(), 1500, 512),
                        ("costlens_logo_on_dark", full_svg(True), 1500, 512)):
    open(name + ".svg", "w").write(svg)
    cairosvg.svg2png(bytestring=svg.encode(), write_to=name + ".png", output_width=w, output_height=h)
for name, bg in (("costlens_logo", "#FFFFFF"), ("costlens_logo_on_dark", "#0E1A2F")):
    base = Image.new("RGBA", (1500, 512), bg); base.alpha_composite(Image.open(name + ".png")); base.convert("RGB").save(f"prev2_{name}.png")
base = Image.new("RGBA", (512, 512), "#FFFFFF"); base.alpha_composite(Image.open("costlens_icon.png"))
small = base.resize((64, 64), Image.LANCZOS); small.save("prev2_icon64.png")
