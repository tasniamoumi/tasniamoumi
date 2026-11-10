#!/usr/bin/env python3
"""Render the profile README cards as self-contained animated SVGs.

Usage:
    python3 render_cards.py            # animated cards
    STATIC=1 python3 render_cards.py   # final frame only (for screenshots)

Reads:   data/contributions.json, data/repos.json, assets/portrait.(jpg|png) [optional]
Writes:  cards/*.svg

Everything works inside an <img> tag: inline <style> with @keyframes, SMIL
<animate> elements, and fonts subset with pyftsubset and embedded as WOFF
data URIs. All motion is disabled under prefers-reduced-motion.
"""
from __future__ import annotations

import base64
import datetime as dt
import html
import io
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "cards"
DATA = ROOT / "data"
FONTS = ROOT / "assets" / "fonts"
STATIC = os.environ.get("STATIC", "") not in ("", "0", "false")

# ---------------------------------------------------------------- content
LOGIN = "tasniamoumi"
NAME = "Tasnia Haque Moumi"
TAGLINE = "Software engineer building backends and integrations for real businesses."
SUBLINE = "Kuala Lumpur · open to remote roles"

TILES = [
    # label, sub, glyph
    ("LinkedIn", "linkedin.com/in/tasniamoumi", "in"),
    ("Email", "say hello", "@"),
    ("Portfolio", "in progress", "↗"),
]

# Curated blurbs; stars / language / last push are refreshed by the Action.
FEATURED = [
    {
        "name": "faunabehav-backend",
        "blurb": "FastAPI + Supabase backend for wildlife camera events: risk scoring, deterrence actions, alerts and dashboard data.",
    },
    {
        "name": "procuremind-ai-mvp",
        "blurb": "Prompt-based procurement decision-support MVP on Microsoft Foundry: demand validation, supplier ranking, risk alerts, human approval.",
    },
    {
        "name": "ai-customer-guardian-mvp",
        "blurb": "After-sales support MVP on Microsoft Foundry: troubleshooting flows, sentiment detection, case logging and escalation.",
    },
]

# ---------------------------------------------------------------- palette
C = dict(
    bg="#0B0D12",
    card="#11141B",
    card2="#161A23",
    line="#232838",
    text="#EEF0F6",
    muted="#8A92A6",
    accent="#FFB454",
    accent2="#6FA8FF",
    levels=["#1A1E29", "#4A3814", "#8A651F", "#C8902C", "#FFB454"],
)
W = 900  # full-width card viewBox width

LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#F1E05A", "TypeScript": "#3178C6",
    "HTML": "#E34C26", "CSS": "#563D7C", "Shell": "#89E051", "Jupyter Notebook": "#DA5B0B",
}

# ---------------------------------------------------------------- fonts
_font_cache: dict[tuple[str, str], str] = {}


def subset_font(file: str, text: str) -> str:
    """Return a base64 WOFF of `file` containing only the glyphs in `text`."""
    chars = "".join(sorted(set(text) | set(" .,:-–·/@()+0123456789")))
    key = (file, chars)
    if key in _font_cache:
        return _font_cache[key]
    out = io.BytesIO()
    tmp = ROOT / "cards" / f".{file}.woff"
    subprocess.run(
        [sys.executable, "-m", "fontTools.subset", str(FONTS / file),
         f"--text={chars}", "--flavor=woff", "--with-zopfli" if False else "--no-hinting",
         "--desubroutinize", "--layout-features=kern,liga,tnum",
         f"--output-file={tmp}"],
        check=True, capture_output=True)
    data = base64.b64encode(tmp.read_bytes()).decode()
    tmp.unlink()
    _font_cache[key] = data
    return data


def font_faces(text: str, serif: bool = False, bold: bool = True) -> str:
    faces = [("Inter-Regular.ttf", "Inter", 400, "normal")]
    if bold:
        faces.append(("Inter-SemiBold.ttf", "Inter", 600, "normal"))
    if serif:
        faces.append(("InstrumentSerif-Regular.ttf", "Instrument Serif", 400, "normal"))
        faces.append(("InstrumentSerif-Italic.ttf", "Instrument Serif", 400, "italic"))
    css = []
    for file, family, weight, style in faces:
        b64 = subset_font(file, text)
        css.append(
            f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:{style};"
            f"src:url(data:font/woff;base64,{b64}) format('woff')}}")
    return "".join(css)


# ---------------------------------------------------------------- helpers
def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def anim_css() -> str:
    """Shared keyframes. Animations are referenced by class; delays are inline."""
    if STATIC:
        return ""
    return (
        "@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}"
        "@keyframes fade{from{opacity:0}to{opacity:1}}"
        "@keyframes grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}"
        "@keyframes pop{0%{transform:scale(.6);opacity:0}70%{transform:scale(1.08);opacity:1}100%{transform:scale(1);opacity:1}}"
        "@keyframes breathe{0%,100%{opacity:.55}50%{opacity:1}}"
        ".up{opacity:0;animation:up .7s cubic-bezier(.2,.7,.2,1) forwards}"
        ".fade{opacity:0;animation:fade .6s ease forwards}"
        ".grow{transform:scaleY(0);transform-box:fill-box;transform-origin:50% 100%;animation:grow .8s cubic-bezier(.2,.7,.2,1) forwards}"
        ".pop{transform:scale(.6);opacity:0;transform-box:fill-box;transform-origin:50% 50%;animation:pop .6s cubic-bezier(.2,.7,.2,1) forwards}"
        ".breathe{animation:breathe 2.4s ease-in-out infinite}"
    )


def reduced_motion_css() -> str:
    # CSS beats SMIL-animated presentation attributes, so forcing the final
    # values here freezes both the keyframes and the <animate> elements.
    return (
        "@media (prefers-reduced-motion:reduce){"
        "*{animation:none!important;transition:none!important}"
        ".up,.fade,.grow,.pop{opacity:1!important;transform:none!important}"
        ".smil-o{opacity:1!important}.smil-d{stroke-dashoffset:0!important}}"
    )


def delay(t: float) -> str:
    return "" if STATIC else f' style="animation-delay:{t:.2f}s"'


def smil_opacity(begin: float, dur: float = 0.5) -> str:
    """SMIL fade-in; the parent must carry class="smil-o" and opacity="0"."""
    if STATIC:
        return ""
    return (f'<animate attributeName="opacity" from="0" to="1" begin="{begin:.2f}s" '
            f'dur="{dur:.2f}s" fill="freeze" calcMode="spline" keySplines=".2 .7 .2 1"/>')


def smil_draw(begin: float, dur: float, length: float) -> str:
    """SMIL line draw; parent needs class="smil-d" and stroke-dasharray/offset set."""
    if STATIC:
        return ""
    return (f'<animate attributeName="stroke-dashoffset" from="{length:.0f}" to="0" '
            f'begin="{begin:.2f}s" dur="{dur:.2f}s" fill="freeze" calcMode="spline" keySplines=".2 .7 .2 1"/>')


def o0() -> str:
    return "" if STATIC else ' opacity="0"'


def svg(width: int, height: int, body: str, css: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="t">\n'
        f'<title id="t">{esc(title)}</title>\n'
        f'<style>{css}{anim_css()}{reduced_motion_css()}'
        f"text{{font-family:'Inter',system-ui,sans-serif;fill:{C['text']}}}"
        f".serif{{font-family:'Instrument Serif',Georgia,serif}}.mut{{fill:{C['muted']}}}"
        f".sb{{font-weight:600}}.num{{font-variant-numeric:tabular-nums}}</style>\n"
        f'<rect width="{width}" height="{height}" rx="18" fill="{C["card"]}" stroke="{C["line"]}"/>\n'
        f"{body}\n</svg>\n")


def write(name: str, content: str) -> None:
    (OUT / name).write_text(content, encoding="utf-8")
    print(f"  {name:22} {len(content.encode()) / 1024:6.1f} KB")


# ---------------------------------------------------------------- data
def load_json(name: str, default):
    p = DATA / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def contribution_stats(days: list[dict]):
    """days: [{date: 'YYYY-MM-DD', count: int}] sorted ascending."""
    days = sorted(days, key=lambda d: d["date"])
    by_date = {d["date"]: int(d["count"]) for d in days}
    dates = [dt.date.fromisoformat(d["date"]) for d in days]
    total = sum(by_date.values())
    active = sum(1 for v in by_date.values() if v > 0)

    # per calendar month, last 12 months
    months: dict[str, int] = defaultdict(int)
    for d in dates:
        months[d.strftime("%Y-%m")] += by_date[d.isoformat()]
    last12 = sorted(months)[-12:]
    monthly = [(m, months[m]) for m in last12]

    # streaks
    cur = longest = run = 0
    for d in dates:
        run = run + 1 if by_date[d.isoformat()] > 0 else 0
        longest = max(longest, run)
    # current streak: count back from the last day with data
    for d in reversed(dates):
        if by_date[d.isoformat()] > 0:
            cur += 1
        else:
            break

    busiest = max(dates, key=lambda d: by_date[d.isoformat()]) if dates else None
    busiest_n = by_date[busiest.isoformat()] if busiest else 0
    return dict(total=total, active=active, monthly=monthly, current=cur,
                longest=longest, busiest=busiest, busiest_n=busiest_n,
                by_date=by_date, first=dates[0] if dates else None,
                last=dates[-1] if dates else None)


# ---------------------------------------------------------------- cards
def card_hero(portrait: Path | None) -> None:
    h = 250
    text = NAME + TAGLINE + SUBLINE + LOGIN
    css = font_faces(text, serif=True)
    x = 56
    body = []
    # accent rule that draws in
    body.append(f'<path class="smil-d" d="M{x} 70 H{x + 44}" stroke="{C["accent"]}" stroke-width="3" '
                f'stroke-linecap="round" stroke-dasharray="44" stroke-dashoffset="{0 if STATIC else 44}">'
                f'{smil_draw(0.1, 0.6, 44)}</path>')
    body.append(f'<text class="up mut sb" x="{x}" y="105" font-size="13" letter-spacing="2.5"{delay(0.25)}>'
                f'@{esc(LOGIN)}</text>')
    first, _, rest = NAME.partition(" ")
    body.append(f'<text class="up serif" x="{x - 2}" y="156" font-size="56"{delay(0.4)}>'
                f'{esc(first)} <tspan font-style="italic" fill="{C["accent"]}">{esc(rest)}</tspan></text>')
    body.append(f'<text class="up" x="{x}" y="192" font-size="17"{delay(0.6)}>{esc(TAGLINE)}</text>')
    body.append(f'<text class="up mut" x="{x}" y="218" font-size="14"{delay(0.75)}>{esc(SUBLINE)}</text>')

    # portrait (optional)
    if portrait and portrait.exists():
        mime = "image/png" if portrait.suffix.lower() == ".png" else "image/jpeg"
        b64 = base64.b64encode(portrait.read_bytes()).decode()
        cx, cy, r = W - 56 - 70, h / 2, 70
        body.append(f'<defs><clipPath id="pc"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath></defs>')
        body.append(f'<g class="pop"{delay(0.5)}>'
                    f'<image href="data:{mime};base64,{b64}" x="{cx - r}" y="{cy - r}" width="{2 * r}" height="{2 * r}" '
                    f'preserveAspectRatio="xMidYMid slice" clip-path="url(#pc)"/>'
                    f'<circle cx="{cx}" cy="{cy}" r="{r + 4}" fill="none" stroke="{C["accent"]}" stroke-width="2" opacity=".7"/></g>')
    else:
        # monogram until a portrait is added
        cx, cy, r = W - 56 - 70, h / 2, 62
        initials = "".join(w[0] for w in NAME.split()[:2])
        body.append(f'<g class="pop"{delay(0.5)}>'
                    f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{C["card2"]}" stroke="{C["line"]}"/>'
                    f'<circle class="smil-d" cx="{cx}" cy="{cy}" r="{r + 6}" fill="none" stroke="{C["accent"]}" stroke-width="2" '
                    f'stroke-dasharray="{2 * 3.1416 * (r + 6):.0f}" stroke-dashoffset="{0 if STATIC else 2 * 3.1416 * (r + 6):.0f}" '
                    f'transform="rotate(-90 {cx} {cy})">{smil_draw(0.7, 1.0, 2 * 3.1416 * (r + 6))}</circle>'
                    f'<text class="serif" x="{cx}" y="{cy + 18}" text-anchor="middle" font-size="52" fill="{C["accent"]}">{esc(initials)}</text></g>')
    write("hero.svg", svg(W, h, "\n".join(body), css, f"{NAME} — {TAGLINE}"))


def card_tiles() -> None:
    w, h = 290, 96
    for i, (label, sub, glyph) in enumerate(TILES):
        css = font_faces(label + sub + glyph)
        t0 = 1.1 + i * 0.18
        body = [
            f'<g class="up"{delay(t0)}>'
            f'<rect x="20" y="24" width="48" height="48" rx="12" fill="{C["card2"]}" stroke="{C["line"]}"/>'
            f'<text x="44" y="56" text-anchor="middle" font-size="20" class="sb" fill="{C["accent"]}">{esc(glyph)}</text>'
            f'<text x="84" y="46" font-size="16" class="sb">{esc(label)}</text>'
            f'<text x="84" y="68" font-size="13" class="mut">{esc(sub)}</text>'
            f'<text class="breathe" x="{w - 26}" y="56" text-anchor="end" font-size="18" fill="{C["accent"]}">→</text>'
            f"</g>"
        ]
        write(f"tile-{i + 1}.svg", svg(w, h, "\n".join(body), css, f"{label}: {sub}"))


def card_activity(stats) -> None:
    h = 300
    monthly = stats["monthly"]
    labels = [dt.date.fromisoformat(m + "-01").strftime("%b") for m, _ in monthly]
    css_text = "Contributions last 12 months " + "".join(labels) + \
        "Current streak Longest streak Active days Busiest day days contributions " + \
        (stats["busiest"].strftime("%d %b %Y") if stats["busiest"] else "")
    css = font_faces(css_text)
    body = [f'<text class="up sb" x="40" y="44" font-size="15"{delay(1.7)}>Contributions</text>',
            f'<text class="up mut" x="40" y="64" font-size="12"{delay(1.8)}>last 12 months · {stats["total"]:,} total</text>']

    # bars
    cx0, cy_base, cw, gap = 40, 220, 540, 10
    n = max(1, len(monthly))
    bw = (cw - gap * (n - 1)) / n
    peak = max([v for _, v in monthly] + [1])
    pts = []
    for i, ((m, v), lab) in enumerate(zip(monthly, labels)):
        x = cx0 + i * (bw + gap)
        bh = max(3, 120 * v / peak)
        y = cy_base - bh
        pts.append((x + bw / 2, y))
        body.append(f'<rect class="grow" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="4" '
                    f'fill="{C["accent"] if v == peak else C["accent2"]}" opacity="{1 if v == peak else .75}"{delay(1.9 + i * 0.06)}/>')
        body.append(f'<text class="fade mut" x="{x + bw / 2:.1f}" y="{cy_base + 20}" text-anchor="middle" font-size="11"{delay(2.0 + i * 0.06)}>{lab}</text>')
        body.append(f'<text class="fade num" x="{x + bw / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-size="11"{delay(2.2 + i * 0.06)}>{v}</text>')
    # trend line drawn with SMIL
    if len(pts) > 1:
        d = "M" + " L".join(f"{x:.1f} {y - 3:.1f}" for x, y in pts)
        length = sum(((pts[i][0] - pts[i - 1][0]) ** 2 + (pts[i][1] - pts[i - 1][1]) ** 2) ** 0.5 for i in range(1, len(pts)))
        body.append(f'<path class="smil-d" d="{d}" fill="none" stroke="{C["text"]}" stroke-opacity=".35" stroke-width="1.5" '
                    f'stroke-dasharray="{length:.0f}" stroke-dashoffset="{0 if STATIC else length:.0f}">{smil_draw(2.6, 0.9, length)}</path>')

    # stats column
    sx = 630
    body.append(f'<line x1="{sx - 24}" y1="40" x2="{sx - 24}" y2="{h - 40}" stroke="{C["line"]}"/>')
    rows = [
        ("Current streak", f'{stats["current"]}', "days"),
        ("Longest streak", f'{stats["longest"]}', "days"),
        ("Active days", f'{stats["active"]}', f"of {len(stats['by_date'])}"),
        ("Busiest day", stats["busiest"].strftime("%d %b") if stats["busiest"] else "–", f'{stats["busiest_n"]} contributions'),
    ]
    for i, (k, v, unit) in enumerate(rows):
        y = 70 + i * 56
        body.append(f'<g class="up"{delay(2.3 + i * 0.15)}>'
                    f'<text class="mut" x="{sx}" y="{y}" font-size="12">{esc(k)}</text>'
                    f'<text class="sb num" x="{sx}" y="{y + 26}" font-size="24" fill="{C["accent"] if i == 0 else C["text"]}">{esc(v)}</text>'
                    f'<text class="mut num" x="{sx + 8 + 14 * len(v)}" y="{y + 26}" font-size="12">{esc(unit)}</text></g>')
    write("activity.svg", svg(W, h, "\n".join(body), css, "Contributions per month, streaks and busiest day"))


def card_repos(repos_meta: dict) -> None:
    h = 132
    for i, repo in enumerate(FEATURED):
        meta = repos_meta.get(repo["name"], {})
        lang = meta.get("language") or ""
        stars = int(meta.get("stars") or 0)
        pushed = meta.get("pushed_at", "")[:10]
        blurb = trunc(repo["blurb"], 116)
        css = font_faces(repo["name"] + blurb + lang + "★ updated " + pushed + f"{stars}")
        t0 = 3.0 + i * 0.3
        body = [
            f'<g class="up"{delay(t0)}>'
            f'<text class="mut sb" x="40" y="40" font-size="11" letter-spacing="2">FEATURED {i + 1:02d}</text>'
            f'<text class="sb" x="40" y="70" font-size="20">{esc(repo["name"])}</text>'
            f'<text class="mut" x="40" y="100" font-size="13.5">{esc(blurb)}</text></g>'
        ]
        # meta on the title row, right-aligned, laid out right to left
        rx = W - 40
        body.append(f'<text class="breathe" x="{rx}" y="40" text-anchor="end" font-size="16" fill="{C["accent"]}"{delay(t0)}>→</text>')
        body.append(f'<text class="fade num" x="{rx}" y="70" text-anchor="end" font-size="13"{delay(t0 + 0.4)}>'
                    f'<tspan fill="{C["accent"]}">★</tspan> {stars}</text>')
        cursor = rx - 46 - 8 * len(str(stars))
        if pushed:
            body.append(f'<text class="fade mut num" x="{cursor}" y="70" text-anchor="end" font-size="12"{delay(t0 + 0.5)}>updated {esc(pushed)}</text>')
            cursor -= 156
        if lang:
            body.append(f'<text class="fade" x="{cursor}" y="70" text-anchor="end" font-size="13"{delay(t0 + 0.3)}>{esc(lang)}</text>'
                        f'<circle class="pop" cx="{cursor - 7.5 * len(lang) - 12}" cy="66" r="5" fill="{LANG_COLORS.get(lang, C["accent2"])}"{delay(t0 + 0.3)}/>')
        write(f"repo-{i + 1}.svg", svg(W, h, "\n".join(body), css, f"{repo['name']}: {repo['blurb']}"))


def card_graph(stats) -> None:
    by = stats["by_date"]
    last = stats["last"] or dt.date.today()
    # 53 columns ending on the week containing `last`
    end = last + dt.timedelta(days=(6 - last.weekday() + 1) % 7)  # Sunday-start weeks: pad to Saturday
    start = end - dt.timedelta(days=53 * 7 - 1)
    cell, gap, pad_x, pad_y = 13, 3, 40, 56
    cols = 53
    wdt = pad_x * 2 + cols * (cell + gap) - gap
    h = pad_y + 7 * (cell + gap) - gap + 44
    peak = max([v for v in by.values()] + [1])
    css = font_faces("Contribution graph past year less more JanFebMarAprMayJunJulAugSepOctNovDec MonWedFri")
    body = [f'<text class="up sb" x="{pad_x}" y="32" font-size="15"{delay(3.9)}>Contribution graph</text>',
            f'<text class="up mut" x="{pad_x}" y="32" font-size="12" dx="150"{delay(4.0)}>past year</text>']

    def level(v: int) -> str:
        if v <= 0:
            return C["levels"][0]
        q = v / peak
        return C["levels"][1 if q <= .25 else 2 if q <= .5 else 3 if q <= .75 else 4]

    seen_month = None
    for c in range(cols):
        wk_start = start + dt.timedelta(days=c * 7)
        x = pad_x + c * (cell + gap)
        cells = []
        for r in range(7):
            d = wk_start + dt.timedelta(days=r)
            v = by.get(d.isoformat(), 0)
            if d > last and d.isoformat() not in by:
                continue
            y = pad_y + r * (cell + gap)
            cells.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{level(v)}"/>')
        if wk_start.month != seen_month and wk_start.day <= 7:
            seen_month = wk_start.month
            body.append(f'<text class="fade mut" x="{x}" y="{pad_y - 10}" font-size="11"{delay(4.0 + c * 0.03)}>{wk_start.strftime("%b")}</text>')
        body.append(f'<g class="smil-o"{o0()}>{smil_opacity(4.0 + c * 0.035, 0.45)}{"".join(cells)}</g>')
    # legend
    lx = wdt - pad_x - 5 * (cell + gap) - 70
    ly = h - 26
    body.append(f'<g class="fade"{delay(5.8)}><text class="mut" x="{lx - 8}" y="{ly + 11}" text-anchor="end" font-size="11">less</text>')
    for i, col in enumerate(C["levels"]):
        body.append(f'<rect x="{lx + i * (cell + gap)}" y="{ly}" width="{cell}" height="{cell}" rx="3" fill="{col}"/>')
    body.append(f'<text class="mut" x="{lx + 5 * (cell + gap) + 4}" y="{ly + 11}" font-size="11">more</text></g>')
    write("graph.svg", svg(wdt, h, "\n".join(body), css, "Contribution graph for the past year"))


# ---------------------------------------------------------------- main
def main() -> None:
    OUT.mkdir(exist_ok=True)
    contributions = load_json("contributions.json", {"days": []})
    repos_meta = {r["name"]: r for r in load_json("repos.json", [])}
    stats = contribution_stats(contributions.get("days", []))
    portrait = next((p for p in (ROOT / "assets" / "portrait.jpg", ROOT / "assets" / "portrait.png") if p.exists()), None)
    print(("STATIC " if STATIC else "animated ") + "render → cards/")
    card_hero(portrait)
    card_tiles()
    card_activity(stats)
    card_repos(repos_meta)
    card_graph(stats)


if __name__ == "__main__":
    main()
