#!/usr/bin/env python3
"""Builds the animated SVGs in assets/ for the profile README.

Everything mirrors galles-dev.vercel.app: colour tokens, the reel HUD
(REC dot, timecode, chapter scrub), scanlines, vignette and the amber sweep.
Fonts (Unbounded, Manrope, JetBrains Mono) are taken from the live site,
instanced to static weights and subset per SVG, so GitHub's <img> sandbox
renders the real typefaces without loading anything external.

    python3 -m pip install fonttools brotli
    python3 scripts/build.py

If a font download 404s, the site was redeployed with new hashed names:
copy the latin (`U+??`) woff2 URLs from the site's CSS into FONT_FILES.
"""
import base64
import io
import urllib.request
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CACHE = ROOT / "scripts" / ".fonts"
SITE_MEDIA = "https://galles-dev.vercel.app/_next/static/media/"
FONT_FILES = {
    "unbounded": "b59689b1142d37ce-s.p.1bk8_xp319hr4.woff2",
    "manrope": "a343f882a40d2cc9-s.p.1sj6eobyi31rd.woff2",
    "jbmono": "70bc3e132a0a741e-s.p.3t6q91iet4nsy.woff2",
}
FACE_SPECS = {
    "display": ("unbounded", 800),
    "display5": ("unbounded", 500),
    "ui": ("manrope", 500),
    "mono": ("jbmono", 500),
    "mono7": ("jbmono", 700),
}

# Tokens from the site's :root. Light = the site's "paper" sections.
THEMES = {
    "dark": dict(
        bg="#0b0d11", floor="#0e1116", wall="#191d25", line="#232833", lit="#2f3642",
        ink="#dfe4ec", dim="#8892a0", accent="#f0b25e", scan="#ffffff", vignette="#00000080",
        inv_bg="#e9e4d8", inv_ink="#12141a", inv_dim="#12141a9e", inv_accent="#a2601a",
    ),
    "light": dict(
        bg="#e9e4d8", floor="#12141a0a", wall="#12141a14", line="#12141a24", lit="#12141a40",
        ink="#12141a", dim="#12141a9e", accent="#a2601a", scan="#000000", vignette="#12141a26",
        inv_bg="#0b0d11", inv_ink="#dfe4ec", inv_dim="#8892a0", inv_accent="#f0b25e",
    ),
}

W = 840
PAD = 32
REEL = 30  # seconds, same as the site's 00:30 reel
CHAPTERS = ["Opening", "Work", "Toolkit", "Method", "Let's talk"]


# ── fonts ────────────────────────────────────────────────────────────────

class Face:
    def __init__(self, file, wght):
        path = CACHE / f"{file}.woff2"
        if not path.exists():
            CACHE.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(SITE_MEDIA + FONT_FILES[file], path)
        font = instancer.instantiateVariableFont(TTFont(path), {"wght": wght})
        font.flavor = None
        buf = io.BytesIO()
        font.save(buf)
        self.data = buf.getvalue()
        self.cmap = font.getBestCmap()
        self.hmtx = font["hmtx"]
        self.upm = font["head"].unitsPerEm
        self.cap = font["OS/2"].sCapHeight / self.upm

    def width(self, s, size, track=0):
        units = sum(self.hmtx[self.cmap[ord(c)]][0] for c in s)
        return units / self.upm * size + track * len(s)

    def subset_b64(self, chars):
        missing = [c for c in chars if ord(c) not in self.cmap]
        assert not missing, f"glyphs missing: {missing}"
        font = TTFont(io.BytesIO(self.data))
        opts = Options()
        opts.flavor = "woff2"
        opts.hinting = False
        opts.layout_features = []
        sub = Subsetter(opts)
        sub.populate(text="".join(sorted(chars)))
        sub.subset(font)
        font.flavor = "woff2"
        buf = io.BytesIO()
        font.save(buf)
        return base64.b64encode(buf.getvalue()).decode()


FACES = {}


def face(key):
    if key not in FACES:
        FACES[key] = Face(*FACE_SPECS[key])
    return FACES[key]


# ── svg ──────────────────────────────────────────────────────────────────

BASE_CSS = (
    "text{font-kerning:none;white-space:pre}"
    ".rec{animation:blink 1.7s step-end infinite}"
    "@keyframes blink{0%,58%{opacity:1}59%,100%{opacity:.14}}"
)
REDUCED = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"


class Svg:
    def __init__(self, w, h, t):
        self.w, self.h, self.t = w, h, t
        self.defs, self.css, self.body = [], [], []
        self.chars = defaultdict(set)

    def add(self, *parts):
        self.body.extend(parts)

    def text(self, x, y, s, key, size, fill, anchor="start", track=0, attrs=""):
        self.chars[key].update(s)
        ls = f' letter-spacing="{track:g}"' if track else ""
        an = f' text-anchor="{anchor}"' if anchor != "start" else ""
        return (f'<text x="{x:g}" y="{y:g}" font-family="{key}" font-size="{size:g}" '
                f'fill="{fill}"{an}{ls}{attrs}>{escape(s)}</text>')

    def hud(self, x, y, s, fill, anchor="start", size=11, key="mono", attrs=""):
        return self.text(x, y, s.upper(), key, size, fill, anchor, round(size * .16, 2), attrs)

    def render(self):
        fonts = "".join(
            f"@font-face{{font-family:{k};src:url(data:font/woff2;base64,{face(k).subset_b64(c)}) format('woff2')}}"
            for k, c in self.chars.items()
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" fill="none">'
            f"<style>{fonts}{BASE_CSS}{''.join(self.css)}{REDUCED}</style>"
            f"<defs>{''.join(self.defs)}</defs>{''.join(self.body)}</svg>"
        )


def measure(key, s, size, track=0):
    return face(key).width(s, size, track)


def hud_w(s, size=11, key="mono"):
    return measure(key, s.upper(), size, round(size * .16, 2))


def wrap(key, s, size, max_w):
    lines, cur = [], ""
    for word in s.split():
        nxt = f"{cur} {word}".strip()
        if cur and measure(key, nxt, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = nxt
    return lines + [cur]


def arrow(x, y, size, color, sw=1.6, cls=""):
    # Animation goes on an inner group: a CSS transform would override the translate attribute
    c = f' class="{cls}"' if cls else ""
    return (f'<g transform="translate({x:g} {y:g})"><g{c} stroke="{color}" stroke-width="{sw}" '
            f'stroke-linecap="square"><path d="M0 {size:g}L{size:g} 0M{size * .3:g} 0H{size:g}V{size * .7:g}"/></g></g>')


def play(x, y, size, color, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<path{c} d="M{x:g} {y:g}l{size * .86:g} {size / 2:g}l-{size * .86:g} {size / 2:g}z" fill="{color}"/>'


def diamond(cx, cy, r, color):
    return f'<rect x="{cx - r:g}" y="{cy - r:g}" width="{2 * r:g}" height="{2 * r:g}" fill="{color}" transform="rotate(45 {cx:g} {cy:g})"/>'


def film_texture(s, h, grain=True):
    """Scanlines + vignette (+ animated grain) exactly as the site's film layer."""
    t = s.t
    s.defs.append(
        f'<pattern id="sl" width="4" height="3" patternUnits="userSpaceOnUse">'
        f'<rect width="4" height="1" fill="{t["scan"]}" fill-opacity=".031"/></pattern>'
        f'<radialGradient id="vg" cx="50%" cy="42%" r="70%">'
        f'<stop offset=".42" stop-color="{t["vignette"]}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{t["vignette"]}"/></radialGradient>'
    )
    if grain:
        s.defs.append(
            '<filter id="grain" x="0" y="0" width="100%" height="100%">'
            '<feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="2" seed="1">'
            '<animate attributeName="seed" values="1;4;7;2;9;5" dur=".6s" calcMode="discrete" repeatCount="indefinite"/>'
            '</feTurbulence><feColorMatrix values="0 0 0 0 .5  0 0 0 0 .5  0 0 0 0 .5  0 0 0 .07 0"/></filter>'
        )
        s.add(f'<rect width="{s.w}" height="{h}" filter="url(#grain)"/>')
    s.add(f'<rect width="{s.w}" height="{h}" fill="url(#sl)" opacity=".35"/>',
          f'<rect width="{s.w}" height="{h}" fill="url(#vg)"/>')


def sweep(s, h, cycle, delay=0, id_="sw"):
    """The site's amber scan line, replayed once per `cycle` seconds."""
    t = s.t
    end = round(1.9 / cycle * 100, 2)
    s.defs.append(
        f'<linearGradient id="{id_}g"><stop offset="0" stop-color="{t["accent"]}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{t["accent"]}"/><stop offset="1" stop-color="{t["accent"]}" stop-opacity="0"/></linearGradient>'
        f'<filter id="{id_}f" x="-10%" y="-2000%" width="120%" height="4100%"><feGaussianBlur stdDeviation="10"/></filter>'
    )
    s.css.append(
        f".{id_}{{opacity:0;animation:{id_} {cycle}s cubic-bezier(.4,0,.2,1) {delay}s infinite}}"
        f"@keyframes {id_}{{0%{{opacity:0;transform:translateY(0)}}{end * .1:.2f}%{{opacity:.9}}"
        f"{end}%,100%{{opacity:0;transform:translateY({h}px)}}}}"
    )
    s.add(f'<g class="{id_}"><rect width="{s.w}" height="14" y="-6" fill="url(#{id_}g)" opacity=".25" filter="url(#{id_}f)"/>'
          f'<rect width="{s.w}" height="2" fill="url(#{id_}g)"/></g>')


def timecode(s, x_right, y, t_color, tail_color):
    """Right-aligned `00:SS / 00:30`; SS ticks once a second in sync with the scrub."""
    tail = " / 00:30"
    w_tail, w_ss = hud_w(tail), hud_w("00")
    x_ss = x_right - w_tail - w_ss
    s.add(s.hud(x_right, y, tail, tail_color, anchor="end"), s.hud(x_ss, y, "00:", t_color, anchor="end"))
    lh = 16
    s.defs.append(f'<clipPath id="tc"><rect x="{x_ss - 2:g}" y="{y - 12}" width="{w_ss + 4:g}" height="15"/></clipPath>')
    s.css.append(f".tick{{animation:tick {REEL}s steps({REEL}) infinite}}"
                 f"@keyframes tick{{to{{transform:translateY(-{REEL * lh}px)}}}}")
    digits = "".join(s.hud(x_ss, y + i * lh, f"{i % REEL:02d}", t_color) for i in range(REEL + 1))
    s.add(f'<g clip-path="url(#tc)"><g class="tick">{digits}</g></g>')


def scrub(s, y, x0, x1, labels=True, filled=False):
    t = s.t
    span = x1 - x0
    s.add(f'<rect x="{x0}" y="{y}" width="{span}" height="1" fill="{t["lit"]}"/>')
    if filled:
        s.add(f'<rect x="{x0}" y="{y - .5}" width="{span}" height="2" fill="{t["accent"]}"/>')
    else:
        s.css.append(f".fill{{transform-box:fill-box;transform-origin:left;animation:fill {REEL}s linear infinite}}"
                     f".head{{animation:head {REEL}s linear infinite}}"
                     f"@keyframes fill{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}"
                     f"@keyframes head{{from{{transform:translateX(0)}}to{{transform:translateX({span}px)}}}}")
        s.add(f'<rect class="fill" x="{x0}" y="{y - .5}" width="{span}" height="2" fill="{t["accent"]}"/>',
              f'<g class="head"><rect x="{x0 - 1}" y="{y - 6}" width="2" height="13" fill="{t["accent"]}"/></g>')
    for i, name in enumerate(CHAPTERS):
        mx = x0 + span * i / len(CHAPTERS)
        s.add(f'<rect x="{mx:g}" y="{y - 8}" width="1" height="7" fill="{t["dim"]}"/>')
        if labels:
            s.add(s.hud(mx, y + 20, f"{i} {name}", t["dim"], size=10))


# ── assets ───────────────────────────────────────────────────────────────

def hero(t):
    H = 420
    s = Svg(W, H, t)
    s.add(f'<rect width="{W}" height="{H}" fill="{t["bg"]}"/>')
    film_texture(s, H)

    # HUD: REC · chapter · timecode
    s.add(f'<circle class="rec" cx="{PAD + 3.5}" cy="30" r="3.5" fill="{t["accent"]}"/>',
          s.hud(PAD + 14, 34, "Rec", t["accent"]),
          s.hud(PAD + 14 + hud_w("Rec") + 18, 34, "Galles.dev — Reel", t["dim"]))
    timecode(s, W - PAD, 34, t["ink"], t["dim"])

    s.add(s.hud(PAD, 112, "Full-stack developer · Shopify · WordPress · React / Next.js", t["dim"]))

    # Kinetic name: letters rise out of a mask, staggered
    size, base = 118, 248
    cap = face("display").cap * size
    s.defs.append(f'<clipPath id="nm"><rect x="0" y="{base - cap - 14:g}" width="{W}" height="{cap + 30:g}"/></clipPath>')
    s.css.append(".rise{animation:rise .95s cubic-bezier(.2,.8,.2,1) both}"
                 f"@keyframes rise{{from{{transform:translateY({cap + 30:.0f}px)}}to{{transform:none}}}}")
    x, letters = PAD - 4, []
    for i, ch in enumerate("ARTUR"):
        letters.append(f'<g class="rise" style="animation-delay:{.25 + i * .07:.2f}s">'
                       f'{s.text(x, base, ch, "display", size, t["ink"])}</g>')
        x += measure("display", ch, size)
    s.add(f'<g clip-path="url(#nm)">{"".join(letters)}</g>')
    name_end = x

    # Accent caret after the name, blinking like the REC dot
    s.add(f'<rect class="rec" x="{name_end + 10:g}" y="{base - cap:g}" width="10" height="{cap:g}" fill="{t["accent"]}"/>')

    # "I build ___" — rolling word slot
    ky, ksize, lh = 306, 24, 34
    lead = "I build "
    s.add(s.text(PAD, ky, lead.upper(), "display5", ksize, t["ink"]))
    sx = PAD + measure("display5", lead.upper(), ksize)
    words = ["Shopify stores", "WordPress sites", "React / Next.js apps"]
    s.defs.append(f'<clipPath id="slot"><rect x="{sx:g}" y="{ky - lh + 6}" width="{W - sx - PAD:g}" height="{lh + 4}"/></clipPath>')
    s.css.append(".roll{animation:roll 7.5s cubic-bezier(.7,0,.2,1) infinite}"
                 f"@keyframes roll{{0%,27%{{transform:none}}33%,60%{{transform:translateY(-{lh}px)}}"
                 f"66%,94%{{transform:translateY(-{2 * lh}px)}}100%{{transform:translateY(-{3 * lh}px)}}}}")
    roll = "".join(s.text(sx, ky + i * lh, w.upper(), "display5", ksize, t["accent"])
                   for i, w in enumerate(words + words[:1]))
    s.add(f'<g clip-path="url(#slot)"><g class="roll">{roll}</g></g>')
    s.add(s.text(PAD, ky + 32, "End to end — and I stay on after launch.", "ui", 16, t["dim"]))

    # Vertical edge mark
    s.add(f'<g transform="translate({W - PAD + 4} 78) rotate(90)">'
          f'{s.hud(0, 0, "Ukraine · Remote / Hybrid · Worldwide", t["accent"], size=10)}</g>')

    scrub(s, 380, PAD, W - PAD)
    sweep(s, H, REEL)
    return s


def chapter_key(t, n):
    label = CHAPTERS[n]
    w = 40 + hud_w(label) + 6
    s = Svg(round(w), 32, t)
    # Each key lights up while its chapter plays on the hero reel (6s per chapter)
    delay = -((REEL - n * REEL / len(CHAPTERS)) % REEL)
    s.css.append(f".k{{animation:key {REEL}s linear {delay:g}s infinite}}"
                 f".kl{{animation:keyl {REEL}s linear {delay:g}s infinite}}"
                 f"@keyframes key{{0%,19%{{stroke:{t['accent']};transform:translateY(1px)}}20%,100%{{stroke:{t['lit']};transform:none}}}}"
                 f"@keyframes keyl{{0%,19%{{fill:{t['accent']}}}20%,100%{{fill:{t['dim']}}}}}")
    s.add(f'<g class="k" stroke="{t["lit"]}"><rect x="1.5" y="1.5" width="28" height="28" rx="3" fill="{t["floor"]}"/>'
          f'<rect x="1.5" y="27.5" width="28" height="2" fill="{t["lit"]}" stroke="none"/></g>',
          s.text(15.5, 20.5, str(n), "mono7", 13, t["ink"], anchor="middle"),
          s.hud(40, 20, label, t["dim"], attrs=' class="kl"'))
    return s


CHAPTER_KICKERS = {
    1: "4 frames · 3 live demos · click to play",
    2: "Stack on rotation",
    3: "Three steps · click to expand",
    4: "Replies within a day",
}


def chapter_header(t, n):
    H = 112
    s = Svg(W, H, t)
    tc = f"00:{n * REEL // len(CHAPTERS):02d} / 00:30"
    s.add(s.hud(0, 16, CHAPTER_KICKERS[n], t["dim"]),
          f'<circle class="rec" cx="{W - hud_w(tc) - 14:g}" cy="12" r="3" fill="{t["accent"]}"/>',
          s.hud(W, 16, tc, t["dim"], anchor="end"))
    num = f"{n:02d}"
    s.css.append(".draw{stroke-dasharray:420;animation:draw 2.4s cubic-bezier(.4,0,.2,1) both}"
                 "@keyframes draw{from{stroke-dashoffset:420}to{stroke-dashoffset:0}}"
                 ".rule{transform-box:fill-box;transform-origin:left;animation:rule 1.6s cubic-bezier(.2,.8,.2,1) .3s both}"
                 "@keyframes rule{from{transform:scaleX(0)}to{transform:scaleX(1)}}")
    s.add(s.text(-3, 92, num, "display", 72, "none",
                 attrs=f' stroke="{t["accent"]}" stroke-width="1.3" class="draw"'))
    nx = measure("display", num, 72) + 22
    s.add(s.text(nx, 90, CHAPTERS[n].upper(), "display", 40, t["ink"]))
    s.add(f'<rect x="0" y="{H - 1}" width="{W}" height="1" fill="{t["line"]}"/>',
          f'<rect class="rule" x="0" y="{H - 1.5}" width="{W}" height="2" fill="{t["accent"]}" opacity=".85"/>')
    return s


PROJECTS = [
    dict(slug="motion", title="Motion", status="Live demo", cta="Open demo",
         desc="Tasks, projects, calendar, focus timer, password vault and a tutoring-student tracker — in one free workspace.",
         tags=["Next.js", "TypeScript", "Supabase", "Claude"]),
    dict(slug="snapchef", title="SnapChef", status="Live demo", cta="Open demo",
         desc="AI recipe book: snap a photo of a recipe and get it back structured, step by step.",
         tags=["Next.js", "TypeScript", "Supabase", "Gemini", "Claude"]),
    dict(slug="site", title="This site", status="Live", cta="Visit site",
         desc="The portfolio itself — kinetic type, a scroll reel and two languages.",
         tags=["Next.js", "React", "TypeScript", "Three.js", "Claude"]),
    dict(slug="axis", title="Axis", status="Coming soon", cta="Request access",
         desc=None, tags=[]),
]


def project_card(t, i, p):
    H, strip = 214, 20
    s = Svg(W, H, t)
    s.add(f'<rect width="{W}" height="{H}" fill="{t["bg"]}"/>',
          f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" fill="{t["floor"]}" stroke="{t["line"]}"/>')

    # Running film: sprocket holes slide left forever
    step = 24
    s.css.append(f".film{{animation:film 1.1s linear infinite}}@keyframes film{{to{{transform:translateX(-{step}px)}}}}")
    for y0 in (0, H - strip):
        holes = "".join(f'<rect x="{x}" y="{y0 + 6}" width="12" height="8" rx="2" fill="{t["bg"]}"/>'
                        for x in range(6, W + step * 2, step))
        s.add(f'<rect x="0" y="{y0}" width="{W}" height="{strip}" fill="{t["wall"]}"/>',
              f'<g class="film">{holes}</g>')

    live = p["desc"] is not None
    frame = f"Frame {i + 1:02d} · {p['status']}"
    s.add(f'<circle class="rec" cx="{PAD + 3}" cy="45" r="3" fill="{t["accent"] if live else t["dim"]}"/>',
          s.hud(PAD + 13, 49, frame, t["dim"], size=10))

    # Big outlined frame number, right side
    s.add(s.text(W - PAD, 130, f"{i + 1:02d}", "display", 96, "none", anchor="end",
                 attrs=f' stroke="{t["lit"]}" stroke-width="1.2"'))

    s.add(s.text(PAD - 1, 98, p["title"].upper(), "display", 34, t["ink"]))
    if live:
        for j, line in enumerate(wrap("ui", p["desc"], 15, 520)[:2]):
            s.add(s.text(PAD, 126 + j * 22, line, "ui", 15, t["dim"]))
        x = PAD
        for tag in p["tags"]:
            tw = hud_w(tag, 10) + 16
            s.add(f'<rect x="{x:g}" y="160.5" width="{tw:g}" height="21" rx="3" stroke="{t["lit"]}"/>',
                  s.hud(x + 8, 174.5, tag, t["dim"], size=10))
            x += tw + 6
    else:
        # Redacted lines with a shimmer pass
        s.add(s.text(PAD, 126, "Unreleased. Access on request.", "ui", 15, t["dim"]))
        s.defs.append(f'<linearGradient id="sh" x1="0" x2="1"><stop offset="0" stop-color="{t["lit"]}"/>'
                      f'<stop offset=".5" stop-color="{t["accent"]}" stop-opacity=".55"/><stop offset="1" stop-color="{t["lit"]}"/>'
                      f'<animate attributeName="x1" values="-1;1" dur="2.6s" repeatCount="indefinite"/>'
                      f'<animate attributeName="x2" values="0;2" dur="2.6s" repeatCount="indefinite"/></linearGradient>')
        for j, bw in enumerate((380, 300, 220)):
            s.add(f'<rect x="{PAD}" y="{142 + j * 15}" width="{bw}" height="9" rx="2" fill="url(#sh)"/>')

    # CTA
    cta = p["cta"]
    cw = hud_w(cta, 11, "mono7")
    cx = W - PAD - cw - 20
    s.css.append(".nudge{animation:nudge 2.4s ease-in-out infinite}"
                 "@keyframes nudge{0%,70%,100%{transform:none}82%{transform:translate(3px,-3px)}}")
    s.add(play(cx - 18, 168.5, 10, t["accent"], cls="rec") if live else "",
          s.hud(cx, 178, cta, t["accent"], size=11, key="mono7"),
          arrow(W - PAD - 10, 168, 10, t["accent"], cls="nudge"))
    sweep(s, H, 9, delay=i * 2.2)
    return s


TOOLKIT = [
    ("Frontend / App", ["Next.js", "React", "TypeScript", "Tailwind CSS", "Framer Motion", "Node.js", "REST API"]),
    ("Shopify", ["Liquid", "Shopify CLI", "Custom themes", "Shopify Apps", "Metafields", "Shopify Plus", "Integrations"]),
    ("WordPress", ["WooCommerce", "Elementor", "ACF", "Gutenberg", "PHP", "Supabase", "PostgreSQL"]),
    ("Other", ["Claude", "ChatGPT", "Gemini", "Grok", "Figma", "Git", "Docker", "SEO", "Core Web Vitals", "Vercel", "Accessibility"]),
]


def toolkit(t):
    row, panel = 58, 184
    H = row * len(TOOLKIT)
    s = Svg(W, H, t)
    s.add(f'<rect width="{W}" height="{H}" fill="{t["bg"]}"/>')
    s.defs.append(f'<clipPath id="lane"><rect x="{panel}" y="0" width="{W - panel}" height="{H}"/></clipPath>'
                  f'<linearGradient id="fade"><stop offset="0" stop-color="{t["bg"]}"/>'
                  f'<stop offset="1" stop-color="{t["bg"]}" stop-opacity="0"/></linearGradient>')
    size, gap = 19, 22
    lanes = []
    for r, (label, items) in enumerate(TOOLKIT):
        y = r * row
        base = y + row / 2 + face("display5").cap * size / 2
        seq, x = [], 0
        for item in items:
            seq.append((x, item))
            x += measure("display5", item.upper(), size) + gap * 2 + 8
        loop_w = x
        reps = int((W - panel) // loop_w) + 2
        parts = []
        for k in range(reps):
            for ox, item in seq:
                px = panel + gap + k * loop_w + ox
                parts.append(s.text(px, base, item.upper(), "display5", size, t["ink"]))
                iw = measure("display5", item.upper(), size)
                parts.append(diamond(px + iw + gap + 4, y + row / 2, 3.2, t["accent"]))
        dur = loop_w / 38
        direction = "normal" if r % 2 == 0 else "reverse"
        s.css.append(f".m{r}{{animation:m{r} {dur:.1f}s linear infinite {direction}}}"
                     f"@keyframes m{r}{{to{{transform:translateX(-{loop_w:.1f}px)}}}}")
        lanes.append(f'<g class="m{r}">{"".join(parts)}</g>')
        s.add(f'<rect x="0" y="{y + row - 1}" width="{W}" height="1" fill="{t["line"]}"/>')
    s.add(f'<g clip-path="url(#lane)">{"".join(lanes)}</g>',
          f'<rect x="{panel}" y="0" width="56" height="{H}" fill="url(#fade)"/>',
          f'<rect x="{W - 56}" y="0" width="56" height="{H}" fill="url(#fade)" transform="rotate(180 {W - 28} {H / 2})"/>')
    for r, (label, items) in enumerate(TOOLKIT):
        y = r * row
        s.add(f'<rect x="0" y="{y}" width="{panel}" height="{row - 1}" fill="{t["floor"]}"/>',
              f'<rect x="{panel}" y="{y}" width="1" height="{row - 1}" fill="{t["line"]}"/>',
              s.hud(16, y + 26, label, t["accent"], size=10, key="mono7"),
              s.hud(16, y + 42, f"{len(items):02d} tools", t["dim"], size=10))
    return s


def contact(t):
    H = 236
    s = Svg(W, H, t)
    s.add(f'<rect width="{W}" height="{H}" fill="{t["inv_bg"]}"/>')
    s.add(f'<circle class="rec" cx="{PAD + 3.5}" cy="30" r="3.5" fill="{t["inv_accent"]}"/>',
          s.hud(PAD + 14, 34, "Ch 4 — Let's talk", t["inv_dim"]),
          s.hud(W - PAD, 34, "Replies within a day", t["inv_dim"], anchor="end"))
    size, base = 78, 140
    cap = face("display").cap * size
    title = "LET'S TALK"
    s.add(s.text(PAD - 3, base, title, "display", size, t["inv_ink"]))
    tw = measure("display", title, size)
    s.add(f'<rect class="rec" x="{PAD + tw + 6:g}" y="{base - cap:g}" width="12" height="{cap:g}" fill="{t["inv_accent"]}"/>')
    mail = "agavrik464@gmail.com"
    s.add(s.text(PAD, 190, mail, "mono7", 16, t["inv_accent"]),
          arrow(PAD + measure("mono7", mail, 16) + 10, 178, 11, t["inv_accent"], cls="nudge"),
          s.text(PAD, 214, "Free first call: Shopify, WordPress or a custom Next.js build — we pick together.", "ui", 14, t["inv_dim"]))
    s.css.append(".nudge{animation:nudge 2.4s ease-in-out infinite}"
                 "@keyframes nudge{0%,70%,100%{transform:none}82%{transform:translate(3px,-3px)}}")
    s.add(f'<g transform="translate({W - PAD + 4} 62) rotate(90)">'
          f'{s.hud(0, 0, "Open for projects", t["inv_accent"], size=10)}</g>')
    return s


LINKS = ["Email", "Telegram", "Upwork", "CV · PDF", "Portfolio"]


def link_button(t, label):
    w = round(18 + hud_w(label, 11, "mono7") + 30)
    s = Svg(w, 40, t)
    s.css.append(".nudge{animation:nudge 2.4s ease-in-out infinite}"
                 "@keyframes nudge{0%,70%,100%{transform:none}82%{transform:translate(2px,-2px)}}")
    s.add(f'<rect x=".5" y=".5" width="{w - 1}" height="39" rx="3" fill="{t["floor"]}" stroke="{t["lit"]}"/>',
          s.hud(18, 24.5, label, t["ink"], size=11, key="mono7"),
          arrow(w - 22, 15, 9, t["accent"], 1.5, cls="nudge"))
    return s


CREDITS = [
    ("A galles.dev production", None),
    ("Directed, designed & built by", "ARTUR"),
    ("In-house, one year", "MKEY MEDIA"),
    ("Freelance", "SHOPIFY · WORDPRESS · NEXT.JS"),
    ("Shipping for real clients", "~1.5 YEARS"),
    ("Shot on", "NEXT.JS · REACT · THREE.JS"),
    ("AI crew", "CLAUDE · CHATGPT · GEMINI · GROK"),
    ("Filmed in", "UKRAINE"),
    ("Available", "REMOTE · HYBRID · WORLDWIDE"),
    ("Next scene", "YOUR PROJECT"),
]


def credits(t):
    H = 300
    s = Svg(W, H, t)
    s.add(f'<rect width="{W}" height="{H}" fill="{t["bg"]}"/>')
    film_texture(s, H, grain=False)
    parts, y = [], 0
    for role, name in CREDITS:
        parts.append(s.hud(W / 2, y, role, t["dim"], anchor="middle", size=10))
        if name:
            parts.append(s.text(W / 2, y + 34, name, "display", 24, t["ink"], anchor="middle"))
            y += 96
        else:
            y += 60
    total = y
    s.css.append(f".roll{{animation:credits {total / 26:.1f}s linear infinite}}"
                 f"@keyframes credits{{from{{transform:translateY({H - 110}px)}}to{{transform:translateY(-{total}px)}}}}")
    s.add(f'<g class="roll">{"".join(parts)}</g>')
    s.defs.append(f'<linearGradient id="tf" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="{t["bg"]}"/>'
                  f'<stop offset="1" stop-color="{t["bg"]}" stop-opacity="0"/></linearGradient>')
    s.add(f'<rect width="{W}" height="70" fill="url(#tf)"/>',
          f'<rect width="{W}" height="70" y="{H - 70}" fill="url(#tf)" transform="rotate(180 {W / 2} {H - 35})"/>')
    return s


def footer(t):
    H = 76
    s = Svg(W, H, t)
    scrub(s, 14, 0, W, labels=False, filled=True)
    s.add(s.hud(0, 52, "End of reel", t["dim"]),
          s.hud(W, 52, "00:30 / 00:30", t["dim"], anchor="end"))
    label = "Rewind to 00:00"
    lw = hud_w(label, 11, "mono7")
    x = W / 2 - (lw + 22) / 2
    s.css.append(".spin{transform-box:fill-box;transform-origin:center;animation:spin 2.8s cubic-bezier(.6,0,.2,1) infinite}"
                 "@keyframes spin{0%,55%{transform:none}100%{transform:rotate(-360deg)}}")
    s.add(f'<g class="spin" stroke="{t["accent"]}" stroke-width="1.6" fill="none">'
          f'<path d="M{x + 12:g} 42a6 6 0 1 1-1.8-4.3"/><path d="M{x + 5:g} 34.5v4h4" stroke-linecap="square"/></g>',
          s.hud(x + 22, 52, label, t["accent"], size=11, key="mono7"))
    return s


def main():
    ASSETS.mkdir(exist_ok=True)
    jobs = {"hero": hero, "toolkit": toolkit, "contact": contact, "credits": credits, "footer": footer}
    for n in range(len(CHAPTERS)):
        jobs[f"key-{n}"] = lambda t, n=n: chapter_key(t, n)
    for n in CHAPTER_KICKERS:
        jobs[f"ch-{n}"] = lambda t, n=n: chapter_header(t, n)
    for i, p in enumerate(PROJECTS):
        jobs[f"frame-{p['slug']}"] = lambda t, i=i, p=p: project_card(t, i, p)
    for label in LINKS:
        slug = label.split()[0].lower()
        jobs[f"btn-{slug}"] = lambda t, label=label: link_button(t, label)
    for name, build in jobs.items():
        for theme, tokens in THEMES.items():
            out = ASSETS / f"{name}-{theme}.svg"
            out.write_text(build(tokens).render())
            print(f"{out.relative_to(ROOT)}  {out.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
