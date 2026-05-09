#!/usr/bin/env python3
"""Generates index.html from all markdown files in summaries/ and opens it."""

import os
import re
import json
import webbrowser
from pathlib import Path
from datetime import datetime

SUMMARIES_DIR = Path(__file__).parent / "summaries"
OUTPUT_FILE = Path(__file__).parent / "index.html"


def md_to_html(text: str) -> str:
    lines = text.split("\n")
    html_lines = []
    in_ul = False

    for line in lines:
        stripped = line.rstrip()

        # Horizontal rule
        if re.match(r"^---+$", stripped):
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append("<hr>")
            continue

        # Headings
        h_match = re.match(r"^(#{1,4})\s+(.*)", stripped)
        if h_match:
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            level = len(h_match.group(1))
            content = inline_md(h_match.group(2))
            html_lines.append(f"<h{level}>{content}</h{level}>")
            continue

        # Bullet list item
        li_match = re.match(r"^[-*]\s+(.*)", stripped)
        if li_match:
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            content = inline_md(li_match.group(1))
            html_lines.append(f"  <li>{content}</li>")
            continue

        # Empty line
        if stripped == "":
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            html_lines.append("")
            continue

        # Regular paragraph line
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False
        html_lines.append(f"<p>{inline_md(stripped)}</p>")

    if in_ul:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def inline_md(text: str) -> str:
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Inline code
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    # Links
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" target="_blank">\1</a>', text)
    return text


def render_market_widget(instruments: list, fetched_at: str = "") -> str:
    if not instruments:
        return ""

    def fmt(value, decimals, prefix, sign=False):
        if value is None:
            return "—"
        s = ("+" if value >= 0 else "") if sign else ""
        if decimals == 0:
            return f"{s}{prefix}{value:,.0f}"
        return f"{s}{prefix}{value:,.{decimals}f}"

    def pct_td(value, extra_class=""):
        if value is None:
            return f'<td class="mkt-pct mkt-neutral {extra_class}">—</td>'
        cls = "mkt-pos" if value >= 0 else "mkt-neg"
        sign = "+" if value >= 0 else ""
        return f'<td class="mkt-pct {cls} {extra_class}">{sign}{value:.2f}%</td>'

    def abs_td(value, decimals, prefix):
        if value is None:
            return '<td class="mkt-pct mkt-neutral">—</td>'
        cls = "mkt-pos" if value >= 0 else "mkt-neg"
        sign = "+" if value >= 0 else ""
        if decimals == 0:
            return f'<td class="mkt-pct {cls}">{sign}{prefix}{value:,.0f}</td>'
        return f'<td class="mkt-pct {cls}">{sign}{prefix}{value:,.{decimals}f}</td>'

    def dot_pos(current, low, high):
        if high is None or low is None or high <= low:
            return 50.0
        return max(0.0, min(100.0, (current - low) / (high - low) * 100))

    rows = []
    for item in instruments:
        d, p = item["decimals"], item["prefix"]
        price = fmt(item["last_close"], d, p)
        w52l  = fmt(item["week52_low"],  d, p)
        w52h  = fmt(item["week52_high"], d, p)
        pos   = dot_pos(item["last_close"], item["week52_low"], item["week52_high"])

        # Market status dot
        state = item.get("market_state", "closed")
        state_titles = {"open": "Markt geöffnet", "pre": "Pre-Market",
                        "post": "After-Market", "closed": "Markt geschlossen"}
        dot = (f'<span class="mkt-status mkt-status-{state}" '
               f'title="{state_titles.get(state, "")}">'
               f'●</span>')

        # Pre-market direction via futures (US indices only)
        pre_html = ""
        ppct = item.get("pre_pct")
        if ppct is not None and state != "open":
            pc  = "mkt-pre-pos" if ppct >= 0 else "mkt-pre-neg"
            sgn = "+" if ppct >= 0 else ""
            pre_html = (
                f'<span class="mkt-pre {pc}">'
                f'<span class="mkt-pre-label">futs▸</span> '
                f'{sgn}{ppct:.2f}%'
                f'</span>'
            )

        url = item.get("url", "")
        name_html = (f'<a href="{url}" target="_blank" class="mkt-link">{item["name"]}</a>'
                     if url else item["name"])
        rows.append(
            f'<tr>'
            f'<td class="mkt-name">{dot}{name_html}</td>'
            f'<td class="mkt-close">{price}{pre_html}</td>'
            f'{abs_td(item.get("day_abs"), d, p)}'
            f'{pct_td(item.get("day_pct"), "mkt-day")}'
            f'<td class="mkt-range">'
            f'<div class="mkt-range-labels"><span>{w52l}</span><span>{w52h}</span></div>'
            f'<div class="mkt-track"><div class="mkt-dot" style="left:{pos:.1f}%"></div></div>'
            f'</td>'
            f'{pct_td(item.get("ytd_pct"))}'
            f'{pct_td(item.get("month_pct"))}'
            f'{pct_td(item.get("week_pct"))}'
            f'</tr>'
        )

    data_date = instruments[0].get("last_date", "") if instruments else ""
    if fetched_at:
        date_label = f"Stand: {fetched_at} Uhr"
    elif data_date:
        date_label = f"Stand: {data_date}"
    else:
        date_label = ""

    return (
        '<div class="mkt-widget">'
        '<div class="mkt-header">'
        '<div class="mkt-title">📊 Marktübersicht</div>'
        f'<div class="mkt-date-label">{date_label}</div>'
        '</div>'
        '<table class="mkt-table"><thead><tr>'
        '<th>Instrument</th><th>Letzter Kurs</th>'
        '<th>Δ 1T</th><th>1T %</th>'
        '<th>52W-Bereich</th>'
        '<th>YTD</th><th>1M</th><th>1W</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + '</tbody></table>'
    )


def render_market_analysis(analysis: str) -> str:
    if not analysis:
        return '</div>\n\n'
    safe = (analysis
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n\n", "</p><p>").replace("\n", " "))
    return (
        '<div class="mkt-analysis">'
        '<div class="mkt-analysis-title">🔍 Marktbewegung &amp; Nachrichten</div>'
        f'<p>{safe}</p>'
        '</div>'
        '</div>\n\n'
    )


def render_sources(sources: list) -> str:
    if not sources:
        return ""

    by_category = {}
    for s in sources:
        by_category.setdefault(s["category"], []).append(s)

    categories_html = []
    for cat_name, cat_sources in by_category.items():
        sources_html = []
        for src in cat_sources:
            items_html = []
            for item in src["items"]:
                title = (item["title"]
                         .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
                url = item.get("url", "")
                date = item.get("published", "")
                date_html = f'<span class="src-date">{date}</span>' if date else ""
                link_html = (f'<a href="{url}" target="_blank" class="src-link">{title}</a>'
                             if url else f'<span class="src-no-link">{title}</span>')
                items_html.append(f'<div class="src-item">{link_html}{date_html}</div>')
            sources_html.append(
                f'<div class="src-source">'
                f'<div class="src-source-name">{src["source"]}</div>'
                + "".join(items_html)
                + '</div>'
            )
        categories_html.append(
            f'<div class="src-category">'
            f'<div class="src-category-name">{cat_name}</div>'
            + "".join(sources_html)
            + '</div>'
        )

    total = sum(len(s["items"]) for s in sources)
    return (
        f'<details class="src-details">'
        f'<summary class="src-summary">'
        f'<span class="src-arrow">▶</span>'
        f'📰 Quellen &amp; Schlagzeilen ({total} Artikel)'
        f'</summary>'
        f'<div class="src-body">'
        + "".join(categories_html)
        + '</div></details>'
    )


def load_briefings() -> list[dict]:
    briefings = []
    for path in sorted(SUMMARIES_DIR.glob("*.md"), reverse=True):
        if path.stem == ".gitkeep":
            continue
        try:
            date = datetime.strptime(path.stem, "%Y-%m-%d")
        except ValueError:
            continue
        content = path.read_text(encoding="utf-8")
        html = md_to_html(content)
        market_path = path.with_suffix(".market.json")
        if market_path.exists():
            raw = json.loads(market_path.read_text(encoding="utf-8"))
            # Support both old list format and new {"instruments": [...], "analysis": "..."}
            if isinstance(raw, list):
                instruments, analysis, fetched_at = raw, None, ""
            else:
                instruments = raw.get("instruments", [])
                analysis = raw.get("analysis")
                fetched_at = raw.get("fetched_at", "")
            market_html = render_market_widget(instruments, fetched_at) + render_market_analysis(analysis)
            if market_html:
                html = market_html + html
        sources_path = path.with_suffix(".sources.json")
        if sources_path.exists():
            sources = json.loads(sources_path.read_text(encoding="utf-8"))
            html += render_sources(sources)

        # Plain-text preview for archive cards
        plain = re.sub(r"<[^>]+>", " ", html)
        plain = re.sub(r"\s+", " ", plain).strip()
        preview = (plain[:155].rsplit(" ", 1)[0] + "…") if len(plain) > 155 else plain

        briefings.append({
            "id": path.stem,
            "date": path.stem,
            "date_display": date.strftime("%-d. %B %Y"),
            "weekday": date.strftime("%A"),
            "html": html,
            "preview": preview,
        })
    return briefings


WEEKDAY_DE = {
    "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
    "Thursday": "Donnerstag", "Friday": "Freitag", "Saturday": "Samstag",
    "Sunday": "Sonntag",
}
MONTH_DE = {
    "January": "Januar", "February": "Februar", "March": "März",
    "April": "April", "May": "Mai", "June": "Juni",
    "July": "Juli", "August": "August", "September": "September",
    "October": "Oktober", "November": "November", "December": "Dezember",
}


def localize(briefings: list[dict]) -> None:
    for b in briefings:
        for en, de in WEEKDAY_DE.items():
            b["weekday"] = b["weekday"].replace(en, de)
        for en, de in MONTH_DE.items():
            b["date_display"] = b["date_display"].replace(en, de)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="de" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morgen-Briefing</title>
<style>
/* ── Variables ───────────────────────────────────────── */
:root {
  --bg:       #f8f7f4;
  --sf:       #ffffff;
  --sf2:      #f2f1ee;
  --bd:       #e8e5e0;
  --tx:       #1a1917;
  --mu:       #78716c;
  --ac:       #1d4ed8;
  --ac2:      #eff6ff;
  --gn:       #15803d;
  --rd:       #b91c1c;
  --qbg:      #fffbeb;
  --qbd:      #fde68a;
  --fin-bg:   #dcfce7; --fin-tx: #166534;
  --pol-bg:   #f3e8ff; --pol-tx: #6d28d9;
  --tec-bg:   #dbeafe; --tec-tx: #1d4ed8;
}
[data-theme="dark"] {
  --bg:       #0d0c0a;
  --sf:       #181614;
  --sf2:      #211e1b;
  --bd:       #2e2b27;
  --tx:       #f4f2ed;
  --mu:       #9e9188;
  --ac:       #60a5fa;
  --ac2:      #172036;
  --gn:       #4ade80;
  --rd:       #f87171;
  --qbg:      #1a1508;
  --qbd:      #5a4e28;
  --fin-bg:   #14532d; --fin-tx: #86efac;
  --pol-bg:   #2d1f5e; --pol-tx: #c4b5fd;
  --tec-bg:   #172036; --tec-tx: #93c5fd;
}
/* ── Reset ───────────────────────────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
     background:var(--bg);color:var(--tx);line-height:1.6;min-height:100vh;
     transition:background .25s,color .25s}
/* ── Header ──────────────────────────────────────────── */
#hdr{position:sticky;top:0;z-index:100;background:var(--sf);border-bottom:1px solid var(--bd)}
.hdr-in{max-width:900px;margin:0 auto;padding:0 24px;height:54px;
        display:flex;align-items:center;justify-content:space-between}
.logo{font-size:14px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;
      color:var(--tx);text-decoration:none}
.logo em{color:var(--ac);font-style:normal}
.hdr-r{display:flex;align-items:center;gap:14px}
#dlbl{font-size:12px;color:var(--mu)}
.tbtn{display:flex;align-items:center;gap:5px;background:var(--sf2);
      border:1px solid var(--bd);border-radius:20px;padding:5px 13px;
      font-size:12px;cursor:pointer;color:var(--mu);transition:border-color .15s,color .15s}
.tbtn:hover{border-color:var(--ac);color:var(--tx)}
/* ── Page ────────────────────────────────────────────── */
.pg{max-width:900px;margin:0 auto;padding:36px 24px 80px}
/* ── Stoic quote ─────────────────────────────────────── */
.quote{background:var(--qbg);border:1px solid var(--qbd);border-radius:12px;
       padding:20px 26px;margin-bottom:28px;display:flex;align-items:flex-start;gap:14px}
.qm{font-size:48px;line-height:1;color:var(--qbd);font-family:Georgia,serif;
    margin-top:-8px;flex-shrink:0;user-select:none}
.qt{font-size:15px;line-height:1.65;font-style:italic;
    font-family:Georgia,"Times New Roman",serif;color:var(--tx);margin-bottom:6px}
.qa{font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:var(--mu)}
/* ── Filter bar ──────────────────────────────────────── */
.filters{display:flex;gap:8px;margin-bottom:24px;flex-wrap:wrap}
.fbtn{padding:6px 16px;border-radius:20px;border:1px solid var(--bd);
      background:var(--sf);color:var(--mu);font-size:13px;font-weight:500;
      cursor:pointer;transition:all .15s;white-space:nowrap}
.fbtn:hover{border-color:var(--ac);color:var(--tx)}
.fbtn.on{background:var(--ac);border-color:var(--ac);color:#fff}
/* ── Briefing card ───────────────────────────────────── */
.bc{background:var(--sf);border:1px solid var(--bd);border-radius:16px;
    padding:44px 52px;
    box-shadow:0 1px 4px rgba(0,0,0,.05),0 8px 24px rgba(0,0,0,.04);
    margin-bottom:52px}
.cs{transition:opacity .15s}
.cs.off{display:none}
/* typography */
.bc h1{font-size:27px;font-weight:800;line-height:1.25;letter-spacing:-.01em;margin-bottom:6px}
.bc h2{font-size:15px;font-weight:700;margin:36px 0 14px;padding:10px 14px;
        background:var(--sf2);border-radius:8px;border-left:3px solid var(--ac);
        display:flex;align-items:center;justify-content:space-between;gap:10px}
.stag{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
      padding:2px 8px;border-radius:10px;flex-shrink:0}
.stag.fin{background:var(--fin-bg);color:var(--fin-tx)}
.stag.pol{background:var(--pol-bg);color:var(--pol-tx)}
.stag.tec{background:var(--tec-bg);color:var(--tec-tx)}
.bc h3{font-size:13px;font-weight:700;margin:20px 0 8px;
        text-transform:uppercase;letter-spacing:.05em;color:var(--mu)}
.bc p{font-size:15px;line-height:1.82;color:var(--tx);margin-bottom:14px;
      font-family:Georgia,"Times New Roman",serif}
.bc ul{list-style:none;padding:0;margin:0 0 16px}
.bc li{font-size:15px;line-height:1.75;padding:7px 0 7px 26px;position:relative;
        border-bottom:1px solid var(--bd);
        font-family:Georgia,"Times New Roman",serif}
.bc li:last-child{border-bottom:none}
.bc li::before{content:"→";position:absolute;left:0;top:9px;
               color:var(--ac);font-size:12px;font-family:sans-serif}
.bc hr{border:none;border-top:1px solid var(--bd);margin:28px 0}
.bc strong{font-weight:700}
.bc a{color:var(--ac);text-decoration:none}
.bc a:hover{text-decoration:underline}
.bc code{background:var(--sf2);padding:1px 5px;border-radius:4px;
          font-size:12px;font-family:"SF Mono","Fira Code",monospace}
/* ── Market widget ───────────────────────────────────── */
.mkt-widget{background:var(--sf2);border:1px solid var(--bd);border-radius:12px;
             padding:20px 24px;margin-bottom:32px;overflow-x:auto}
.mkt-header{display:flex;align-items:baseline;justify-content:space-between;
             gap:12px;margin-bottom:16px}
.mkt-title{font-size:14px;font-weight:700}
.mkt-date-label{font-size:11px;color:var(--mu);white-space:nowrap}
.mkt-table{width:100%;border-collapse:collapse;min-width:480px}
.mkt-table th{font-size:10px;font-weight:600;color:var(--mu);text-transform:uppercase;
               letter-spacing:.06em;padding:0 6px 8px;border-bottom:1px solid var(--bd);
               text-align:right;white-space:nowrap}
.mkt-table th:first-child{text-align:left}
.mkt-table th:nth-child(3){text-align:left}
.mkt-table td{padding:6px;border-bottom:1px solid var(--bd);vertical-align:middle;font-size:12px}
.mkt-table tr:last-child td{border-bottom:none}
.mkt-name{font-weight:600;white-space:nowrap}
.mkt-close{text-align:right;font-family:"SF Mono",monospace;white-space:nowrap}
.mkt-range{min-width:130px;padding-top:8px !important;padding-bottom:8px !important}
.mkt-range-labels{display:flex;justify-content:space-between;font-size:9px;
                   color:var(--mu);font-family:"SF Mono",monospace;margin-bottom:4px}
.mkt-track{height:3px;background:var(--bd);border-radius:2px;position:relative}
.mkt-dot{position:absolute;width:7px;height:7px;background:var(--ac);border-radius:50%;
          top:-2px;transform:translateX(-50%);box-shadow:0 0 0 2px var(--sf2)}
.mkt-pct{text-align:right;font-family:"SF Mono",monospace;font-size:11px;
          font-weight:600;white-space:nowrap}
.mkt-pos{color:var(--gn)}
.mkt-neg{color:var(--rd)}
.mkt-neutral{color:var(--mu)}
.mkt-day{border-left:2px solid var(--bd)}
.mkt-link{color:inherit;text-decoration:none;border-bottom:1px dotted var(--mu)}
.mkt-link:hover{color:var(--ac)}
.mkt-status{font-size:9px;margin-right:4px}
.mkt-status-open{color:#22c55e}
.mkt-status-pre,.mkt-status-post{color:#f59e0b}
.mkt-status-closed{color:var(--mu)}
.mkt-pre{display:block;font-size:10px;font-family:"SF Mono",monospace;margin-top:2px}
.mkt-pre-label{color:var(--mu)}
.mkt-pre-pos{color:var(--gn)}
.mkt-pre-neg{color:var(--rd)}
.mkt-analysis{margin-top:16px;padding:14px 18px;background:var(--ac2);
               border:1px solid var(--ac);border-radius:8px;
               font-size:13px;line-height:1.65;color:var(--tx)}
.mkt-analysis-title{font-size:10px;font-weight:700;letter-spacing:.08em;
                      text-transform:uppercase;color:var(--ac);margin-bottom:8px}
.mkt-analysis p{margin:0 0 6px;font-size:13px;color:var(--tx);line-height:1.65}
.mkt-analysis p:last-child{margin-bottom:0}
/* ── Sources ─────────────────────────────────────────── */
.src-details{margin-top:32px;border:1px solid var(--bd);border-radius:10px;overflow:hidden}
.src-summary{cursor:pointer;padding:12px 18px;background:var(--sf2);font-size:12px;
              font-weight:600;color:var(--mu);list-style:none;user-select:none;
              display:flex;align-items:center;gap:6px}
.src-summary::-webkit-details-marker{display:none}
.src-arrow{font-size:9px;transition:transform .15s;display:inline-block}
details[open] .src-arrow{transform:rotate(90deg)}
.src-body{padding:16px 20px}
.src-category{margin-bottom:20px}
.src-category:last-child{margin-bottom:0}
.src-category-name{font-size:10px;font-weight:700;letter-spacing:.08em;
                    text-transform:uppercase;color:var(--ac);margin-bottom:10px}
.src-source{margin-bottom:14px}
.src-source:last-child{margin-bottom:0}
.src-source-name{font-size:11px;font-weight:600;color:var(--mu);margin-bottom:5px;
                  padding-bottom:4px;border-bottom:1px solid var(--bd)}
.src-item{display:flex;justify-content:space-between;align-items:baseline;
           gap:16px;padding:4px 0;border-bottom:1px solid var(--sf2)}
.src-item:last-child{border-bottom:none}
.src-link{font-size:13px;color:var(--tx);text-decoration:none;flex:1;line-height:1.4}
.src-link:hover{color:var(--ac);text-decoration:underline}
.src-no-link{font-size:13px;color:var(--tx);flex:1;line-height:1.4}
.src-date{font-size:10px;color:var(--mu);white-space:nowrap;
           font-family:"SF Mono",monospace;flex-shrink:0}
/* ── Archive ─────────────────────────────────────────── */
.arc-hd{font-size:11px;font-weight:700;letter-spacing:.08em;
         text-transform:uppercase;color:var(--mu);margin-bottom:16px}
.arc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.arc-card{background:var(--sf);border:1px solid var(--bd);border-radius:12px;
           padding:16px 18px;cursor:pointer;
           transition:border-color .15s,transform .15s,box-shadow .15s}
.arc-card:hover{border-color:var(--ac);
                box-shadow:0 4px 16px rgba(0,0,0,.08);transform:translateY(-2px)}
.arc-card.on{border-color:var(--ac);background:var(--ac2)}
.arc-wd{font-size:10px;font-weight:600;letter-spacing:.06em;
         text-transform:uppercase;color:var(--mu);margin-bottom:3px}
.arc-dt{font-size:14px;font-weight:700;margin-bottom:7px;
         display:flex;align-items:center;gap:7px}
.today-pill{font-size:10px;font-weight:600;background:var(--ac);
             color:#fff;padding:1px 8px;border-radius:10px}
.arc-pre{font-size:12px;color:var(--mu);line-height:1.5;
          display:-webkit-box;-webkit-line-clamp:2;
          -webkit-box-orient:vertical;overflow:hidden}
/* ── Responsive ──────────────────────────────────────── */
@media(max-width:640px){
  .pg{padding:20px 16px 60px}
  .bc{padding:24px 20px;border-radius:12px}
  .bc h1{font-size:22px}
  .bc h2{font-size:14px}
  .quote{padding:16px 18px}
  .qm{font-size:32px}
  .arc-grid{grid-template-columns:1fr 1fr;gap:8px}
  .arc-card{padding:12px 14px}
  .filters{gap:6px}
  .fbtn{padding:5px 12px;font-size:12px}
  #dlbl{display:none}
}
/* ── Stock Research ──────────────────────────────────── */
.stk-sec{margin-top:52px;padding-top:48px;border-top:1px solid var(--bd)}
.stk-hdr{display:flex;align-items:center;justify-content:space-between;
          flex-wrap:wrap;gap:16px;margin-bottom:22px}
.stk-wrap{position:relative;width:340px}
.stk-inp{width:100%;padding:10px 14px 10px 38px;border:1px solid var(--bd);
          border-radius:10px;background:var(--sf);color:var(--tx);
          font-size:14px;outline:none;transition:border-color .15s,box-shadow .15s}
.stk-inp::placeholder{color:var(--mu)}
.stk-inp:focus{border-color:var(--ac);box-shadow:0 0 0 3px color-mix(in srgb,var(--ac) 15%,transparent)}
.stk-ico{position:absolute;left:11px;top:50%;transform:translateY(-50%);
          font-size:14px;pointer-events:none;opacity:.5}
.stk-sug{position:absolute;top:calc(100% + 5px);left:0;right:0;
          background:var(--sf);border:1px solid var(--bd);border-radius:10px;
          box-shadow:0 8px 28px rgba(0,0,0,.12);z-index:50;overflow:hidden;display:none}
.stk-sug-item{padding:10px 14px;cursor:pointer;display:flex;
               align-items:center;gap:10px;border-bottom:1px solid var(--bd)}
.stk-sug-item:last-child{border-bottom:none}
.stk-sug-item:hover,.stk-sug-item.hi{background:var(--sf2)}
.sug-sym{font-size:13px;font-weight:700;min-width:52px;color:var(--tx)}
.sug-nm{font-size:12px;color:var(--mu);flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.sug-ex{font-size:10px;color:var(--mu);flex-shrink:0;letter-spacing:.04em}
/* Stock result */
.stk-res{display:none}
.stk-ov{background:var(--sf);border:1px solid var(--bd);border-radius:16px;
         padding:28px 32px;margin-bottom:16px}
.stk-co{font-size:13px;color:var(--mu);margin-bottom:8px;
         display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.stk-co strong{color:var(--tx);font-size:14px}
.stk-sector{font-size:10px;font-weight:600;background:var(--sf2);
             padding:2px 8px;border-radius:8px;color:var(--mu)}
.stk-pr-row{display:flex;align-items:baseline;gap:14px;margin-bottom:24px;flex-wrap:wrap}
.stk-pr{font-size:40px;font-weight:800;letter-spacing:-.025em;line-height:1}
.stk-ch{font-size:17px;font-weight:600}
.stk-up{color:var(--gn)}
.stk-dn{color:var(--rd)}
.stk-mets{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:10px}
.stk-met{background:var(--sf2);border-radius:10px;padding:12px 16px}
.stk-ml{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
         color:var(--mu);margin-bottom:5px}
.stk-mv{font-size:15px;font-weight:700;color:var(--tx)}
/* 52-week range bar */
.w52-bar{margin-top:7px;position:relative;height:4px;background:var(--bd);border-radius:2px}
.w52-dot{position:absolute;width:10px;height:10px;background:var(--ac);
          border-radius:50%;top:-3px;transform:translateX(-50%);
          box-shadow:0 0 0 2px var(--sf2)}
/* Chart */
.stk-ch-card{background:var(--sf);border:1px solid var(--bd);border-radius:16px;
              padding:22px 28px;margin-bottom:16px}
.stk-ch-ttl{font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
              color:var(--mu);margin-bottom:14px}
.chart-lbl{font-size:10px;fill:var(--mu);font-family:"SF Mono","Fira Code",monospace}
/* AI summary */
.stk-ai{background:var(--sf);border:1px solid var(--bd);border-radius:16px;padding:24px 32px}
.ai-ttl{font-size:11px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;
         color:var(--ac);margin-bottom:10px}
.ai-body{font-size:15px;line-height:1.78;font-family:Georgia,"Times New Roman",serif;color:var(--tx)}
.ai-spin{display:flex;align-items:center;gap:10px;color:var(--mu);font-size:14px}
/* Spinner */
@keyframes sp{to{transform:rotate(360deg)}}
.spin{width:16px;height:16px;border:2px solid var(--bd);border-top-color:var(--ac);
       border-radius:50%;animation:sp .7s linear infinite;flex-shrink:0}
@media(max-width:640px){
  .stk-sec{margin-top:36px;padding-top:36px}
  .stk-hdr{flex-direction:column;align-items:stretch}
  .stk-wrap{width:100%}
  .stk-ov{padding:20px}
  .stk-ai{padding:20px}
  .stk-pr{font-size:32px}
  .stk-mets{grid-template-columns:repeat(auto-fill,minmax(115px,1fr))}
}
</style>
</head>
<body>

<header id="hdr">
  <div class="hdr-in">
    <a class="logo" href="#">Morgen<em>·</em>Briefing</a>
    <div class="hdr-r">
      <span id="dlbl"></span>
      <button class="tbtn" id="tbtn" onclick="toggleTheme()">
        <span id="tico">🌙</span><span id="tlbl">Dark</span>
      </button>
    </div>
  </div>
</header>

<div class="pg">

  <div class="quote">
    <div class="qm">"</div>
    <div>
      <div class="qt" id="qt"></div>
      <div class="qa" id="qa"></div>
    </div>
  </div>

  <div class="filters">
    <button class="fbtn on" data-cat="all"     onclick="setFilter('all')">Alle</button>
    <button class="fbtn"    data-cat="finance"  onclick="setFilter('finance')">Finanzen</button>
    <button class="fbtn"    data-cat="politics" onclick="setFilter('politics')">Politik</button>
    <button class="fbtn"    data-cat="tech"     onclick="setFilter('tech')">Tech</button>
  </div>

  <div id="bview"></div>

  <div class="arc-hd">Archiv</div>
  <div class="arc-grid" id="agrid"></div>

  <!-- Stock Research -->
  <section class="stk-sec" id="stk-sec">
    <div class="stk-hdr">
      <div class="arc-hd" style="margin-bottom:0">Aktienrecherche</div>
      <div class="stk-wrap">
        <span class="stk-ico">🔍</span>
        <input class="stk-inp" id="stk-inp" type="text"
               placeholder="Ticker oder Unternehmen, z.B. AAPL oder Siemens"
               autocomplete="off" spellcheck="false">
        <div class="stk-sug" id="stk-sug"></div>
      </div>
    </div>
    <div class="stk-res" id="stk-res"></div>
  </section>

</div>

<script>
const briefings = BRIEFINGS_DATA;

/* ── Stoic quotes (30) ──────────────────────────────── */
const QQ = [
  {t:"Es ist nicht wenig Zeit, die uns fehlt — es ist viel Zeit, die wir verschwenden.",a:"Seneca"},
  {t:"Verliere keine Zeit damit, was ein guter Mensch sein könnte. Sei es.",a:"Marcus Aurelius"},
  {t:"Du hast Macht über deinen Geist, nicht über äußere Ereignisse. Erkenne das, und du wirst Stärke finden.",a:"Marcus Aurelius"},
  {t:"Die Hindernisse auf dem Weg werden selbst zum Weg.",a:"Marcus Aurelius"},
  {t:"Nicht die Dinge beunruhigen die Menschen, sondern ihre Urteile über die Dinge.",a:"Epiktet"},
  {t:"Wünsche nicht, dass die Dinge so sind, wie du willst — wünsche, dass sie so sind, wie sie sind.",a:"Epiktet"},
  {t:"Wer überall ist, ist nirgends.",a:"Seneca"},
  {t:"Es kommt nicht darauf an, wie lange man lebt, sondern wie gut.",a:"Seneca"},
  {t:"Dein Geist nimmt die Farbe seiner häufigsten Gedanken an.",a:"Marcus Aurelius"},
  {t:"Zuerst sage dir selbst, was du sein willst; dann tue, was nötig ist.",a:"Epiktet"},
  {t:"Wir leiden mehr in der Vorstellung als in der Wirklichkeit.",a:"Seneca"},
  {t:"Handle jetzt so, wie ein guter und weiser Mensch handeln würde.",a:"Marcus Aurelius"},
  {t:"Lass nichts unversucht, was du dir gewünscht hättest getan zu haben.",a:"Seneca"},
  {t:"Die Ruhe der Seele hängt nicht vom äußeren Zustand ab, sondern von unserer Einstellung.",a:"Epiktet"},
  {t:"Der Weise lebt so lange er muss, nicht so lange er kann.",a:"Seneca"},
  {t:"Niemand wird durch Zufall weise. Tugend muss gelernt werden.",a:"Seneca"},
  {t:"Lass dich nicht von dem kontrollieren, was du nicht kontrollieren kannst.",a:"Epiktet"},
  {t:"Sei ein Beispiel, nicht ein Ratgeber.",a:"Marcus Aurelius"},
  {t:"Nicht der Mensch leidet Mangel, der wenig besitzt, sondern der, der mehr begehrt.",a:"Seneca"},
  {t:"Dankbarkeit für das Vergangene und Mut für das Kommende — das sind die Stützen des Geistes.",a:"Marcus Aurelius"},
  {t:"Das Glück begünstigt den vorbereiteten Geist.",a:"Seneca"},
  {t:"Wähle nicht die leichteste Aufgabe, sondern die richtige.",a:"Epiktet"},
  {t:"Jeder Tag ist ein neues Leben — ergreife ihn.",a:"Seneca"},
  {t:"Die Zeit vergeht; nutze sie, bevor sie dich benutzt.",a:"Seneca"},
  {t:"Mach dir keine Sorgen, ob du anerkannt wirst — arbeite daran, es zu verdienen.",a:"Marcus Aurelius"},
  {t:"Ein gutes Gewissen ist die beste Grundlage für innere Ruhe.",a:"Seneca"},
  {t:"Richte deinen Geist auf das aus, was du tun kannst — und tu es.",a:"Marcus Aurelius"},
  {t:"Der Mensch leidet nicht an dem, was er erlebt, sondern an dem, was er erlebt zu haben glaubt.",a:"Seneca"},
  {t:"Beginne; das ist die halbe Tat.",a:"Marcus Aurelius"},
  {t:"Vertraue nicht dem Glück, wenn es dir günstig ist; misstraue ihm auch, wenn es dir treu erscheint.",a:"Seneca"},
];
const _n = new Date();
const _doy = Math.floor((_n - new Date(_n.getFullYear(),0,0)) / 86400000);
const _q = QQ[_doy % QQ.length];
document.getElementById("qt").textContent = _q.t;
document.getElementById("qa").textContent = "— " + _q.a;

/* ── Date label ─────────────────────────────────────── */
const DAYS = ["Sonntag","Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag"];
const MONS = ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"];
document.getElementById("dlbl").textContent =
  DAYS[_n.getDay()] + ", " + _n.getDate() + ". " + MONS[_n.getMonth()] + " " + _n.getFullYear();
const todayStr = _n.toISOString().slice(0,10);

/* ── Theme ──────────────────────────────────────────── */
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  document.getElementById("tico").textContent = t === "dark" ? "☀️" : "🌙";
  document.getElementById("tlbl").textContent = t === "dark" ? "Hell" : "Dark";
}
function toggleTheme() {
  const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("theme", t); applyTheme(t);
}
applyTheme(localStorage.getItem("theme") ||
  (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

/* ── Category detection ─────────────────────────────── */
function catOf(txt) {
  const t = txt.toLowerCase();
  if (/finanz|wirtschaft|markt|börse|konjunktur|handel/.test(t)) return "finance";
  if (/politik|geopolit|sicherheit|außenpolitik|nachrichten|ausblick/.test(t)) return "politics";
  if (/tech|künstlich| ki |produkt|digital|startup/.test(t)) return "tech";
  return "other";
}
const CAT_MAP = {finance:"fin",politics:"pol",tech:"tec"};
const CAT_LBL = {finance:"Finanzen",politics:"Politik",tech:"Tech"};

function wrapSections(card) {
  const nodes = Array.from(card.childNodes);
  let sec = null;
  const frag = document.createDocumentFragment();
  for (const node of nodes) {
    const isH2 = node.nodeType === 1 && node.tagName === "H2";
    if (isH2) {
      const cat = catOf(node.textContent);
      sec = document.createElement("div");
      sec.className = "cs";
      sec.dataset.cat = cat;
      if (CAT_MAP[cat]) {
        const tag = document.createElement("span");
        tag.className = "stag " + CAT_MAP[cat];
        tag.textContent = CAT_LBL[cat];
        node.appendChild(tag);
      }
      frag.appendChild(sec);
    }
    (sec || frag).appendChild(node);
  }
  card.appendChild(frag);
}

/* ── Filter ─────────────────────────────────────────── */
let curFilter = "all";
function setFilter(cat) {
  curFilter = cat;
  document.querySelectorAll(".fbtn").forEach(b => b.classList.toggle("on", b.dataset.cat === cat));
  document.querySelectorAll(".cs").forEach(s =>
    s.classList.toggle("off", cat !== "all" && s.dataset.cat !== cat));
}

/* ── Show briefing ──────────────────────────────────── */
function show(id) {
  const b = briefings.find(x => x.id === id);
  if (!b) return;
  const view = document.getElementById("bview");
  view.innerHTML = '<div class="bc" id="bc">' + b.html + '</div>';
  wrapSections(document.getElementById("bc"));
  setFilter(curFilter);
  document.querySelectorAll(".arc-card").forEach(c => c.classList.toggle("on", c.dataset.id === id));
  window.scrollTo({top:0,behavior:"smooth"});
}

/* ── Archive grid ───────────────────────────────────── */
const grid = document.getElementById("agrid");
briefings.forEach(b => {
  const c = document.createElement("div");
  c.className = "arc-card";
  c.dataset.id = b.id;
  c.innerHTML =
    '<div class="arc-wd">' + b.weekday + '</div>' +
    '<div class="arc-dt">' + b.date_display +
      (b.date === todayStr ? '<span class="today-pill">Heute</span>' : '') + '</div>' +
    '<div class="arc-pre">' + (b.preview || "") + '</div>';
  c.addEventListener("click", () => show(b.id));
  grid.appendChild(c);
});

if (briefings.length) show(briefings[0].id);

/* ── Stock Research ─────────────────────────────────── */
const STK = 'http://localhost:5001';
const _inp = document.getElementById('stk-inp');
const _sug = document.getElementById('stk-sug');
const _res = document.getElementById('stk-res');
let _st = null, _hi = -1;

_inp.addEventListener('input', () => {
  clearTimeout(_st);
  const q = _inp.value.trim();
  if (q.length < 2) { _hideSug(); return; }
  _st = setTimeout(() => _doSearch(q), 280);
});

_inp.addEventListener('keydown', e => {
  const items = _sug.querySelectorAll('.stk-sug-item');
  if (e.key === 'ArrowDown') { e.preventDefault(); _nav(items, 1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); _nav(items, -1); }
  else if (e.key === 'Enter') {
    e.preventDefault();
    if (_hi >= 0 && items[_hi]) items[_hi].click();
    else { _hideSug(); const q = _inp.value.trim().toUpperCase(); if (q) _loadStock(q); }
  }
  else if (e.key === 'Escape') _hideSug();
});

document.addEventListener('click', e => { if (!e.target.closest('#stk-sec')) _hideSug(); });

function _nav(items, dir) {
  if (!items.length) return;
  if (_hi >= 0) items[_hi].classList.remove('hi');
  _hi = Math.max(0, Math.min(items.length - 1, _hi + dir));
  items[_hi].classList.add('hi');
  items[_hi].scrollIntoView({block:'nearest'});
}

async function _doSearch(q) {
  try {
    const r = await fetch(`${STK}/api/search?q=${encodeURIComponent(q)}`);
    if (!r.ok) throw new Error();
    const data = await r.json();
    if (!Array.isArray(data) || !data.length) { _hideSug(); return; }
    _hi = -1;
    _sug.innerHTML = data.map(s =>
      `<div class="stk-sug-item" onclick="_pick(${JSON.stringify(s.symbol)})">` +
      `<span class="sug-sym">${_e(s.symbol)}</span>` +
      `<span class="sug-nm">${_e(s.name)}</span>` +
      `<span class="sug-ex">${_e(s.exchange||'')}</span></div>`
    ).join('');
    _sug.style.display = 'block';
  } catch { _hideSug(); }
}

function _pick(sym) { _inp.value = sym; _hideSug(); _loadStock(sym); }
function _hideSug() { _sug.style.display = 'none'; _hi = -1; }
function _e(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _fmt(n, d=2) {
  if (n == null || isNaN(n)) return '—';
  if (Math.abs(n) >= 1e12) return (n/1e12).toFixed(2) + ' Bio.';
  if (Math.abs(n) >= 1e9)  return (n/1e9).toFixed(2)  + ' Mrd.';
  if (Math.abs(n) >= 1e6)  return (n/1e6).toFixed(1)  + ' Mio.';
  return n.toLocaleString('de-DE', {maximumFractionDigits: d});
}
function _vol(n) {
  if (n == null || isNaN(n)) return '—';
  if (n >= 1e9) return (n/1e9).toFixed(2) + 'Mrd';
  if (n >= 1e6) return (n/1e6).toFixed(1) + 'Mio';
  if (n >= 1e3) return Math.round(n/1e3) + 'k';
  return String(n);
}

async function _loadStock(sym) {
  _res.style.display = 'block';
  _res.innerHTML = `<div class="stk-ov"><div style="display:flex;align-items:center;gap:10px;padding:12px 0">` +
    `<div class="spin"></div><span style="color:var(--mu);font-size:14px">Lade ${_e(sym)}…</span></div></div>`;
  document.getElementById('stk-sec').scrollIntoView({behavior:'smooth', block:'nearest'});

  try {
    const [ir, hr] = await Promise.all([
      fetch(`${STK}/api/stock/${sym}`),
      fetch(`${STK}/api/stock/${sym}/history`),
    ]);
    const info = await ir.json();
    const hist = await hr.json();
    if (info.error) throw new Error(info.error);

    const up = (info.change ?? 0) >= 0;
    const cc = up ? 'stk-up' : 'stk-dn';
    const cs = up ? '+' : '';

    // 52-week dot position
    const lo = info.week52_low, hi52 = info.week52_high, pr = info.price;
    const dot = (lo && hi52 && hi52 > lo)
      ? Math.max(0, Math.min(100, (pr - lo) / (hi52 - lo) * 100)).toFixed(1) : '50';

    const ov =
      `<div class="stk-ov">` +
      `<div class="stk-co">` +
      `<strong>${_e(info.name)}</strong>` +
      `<span style="opacity:.35">·</span><span>${_e(info.symbol)}</span>` +
      `<span style="opacity:.35">·</span><span>${_e(info.currency||'USD')}</span>` +
      (info.sector ? `<span class="stk-sector">${_e(info.sector)}</span>` : '') +
      `</div>` +
      `<div class="stk-pr-row">` +
      `<span class="stk-pr">${info.price?.toFixed(2) ?? '—'}</span>` +
      `<span class="stk-ch ${cc}">${cs}${info.change?.toFixed(2) ?? '—'}&ensp;(${cs}${info.change_pct?.toFixed(2) ?? '—'}%)</span>` +
      `</div>` +
      `<div class="stk-mets">` +
      `<div class="stk-met"><div class="stk-ml">Marktkapital.</div><div class="stk-mv">${_fmt(info.market_cap)}</div></div>` +
      `<div class="stk-met"><div class="stk-ml">KGV (P/E)</div><div class="stk-mv">${info.pe_ratio ? info.pe_ratio.toFixed(1) : '—'}</div></div>` +
      `<div class="stk-met"><div class="stk-ml">52W Hoch / Tief</div>` +
        `<div class="stk-mv">${info.week52_high?.toFixed(2) ?? '—'} / ${info.week52_low?.toFixed(2) ?? '—'}</div>` +
        `<div class="w52-bar"><div class="w52-dot" style="left:${dot}%"></div></div></div>` +
      `<div class="stk-met"><div class="stk-ml">Volumen</div><div class="stk-mv">${_vol(info.volume)}</div></div>` +
      `<div class="stk-met"><div class="stk-ml">Ø Volumen</div><div class="stk-mv">${_vol(info.avg_volume)}</div></div>` +
      (info.industry ? `<div class="stk-met"><div class="stk-ml">Branche</div><div class="stk-mv" style="font-size:13px">${_e(info.industry)}</div></div>` : '') +
      `</div></div>`;

    const ch = Array.isArray(hist) && hist.length > 1
      ? `<div class="stk-ch-card"><div class="stk-ch-ttl">Kursverlauf — 30 Tage</div>${_chart(hist, up)}</div>`
      : '';

    const ai =
      `<div class="stk-ai" id="stk-ai-box">` +
      `<div class="ai-ttl">KI-Analyse</div>` +
      `<div class="ai-spin"><div class="spin"></div>Analysiere ${_e(info.name)}…</div>` +
      `</div>`;

    _res.innerHTML = ov + ch + ai;
    _loadAI(sym);

  } catch(e) {
    _res.innerHTML =
      `<div class="stk-ov" style="text-align:center;padding:36px">` +
      `<div style="font-size:28px;margin-bottom:10px">⚠️</div>` +
      `<div style="color:var(--rd);margin-bottom:8px;font-weight:600">${_e(e.message)}</div>` +
      `<div style="font-size:13px;color:var(--mu)">Läuft der Flask-Server?&ensp;` +
      `<code style="background:var(--sf2);padding:2px 6px;border-radius:5px">python app.py</code></div></div>`;
  }
}

async function _loadAI(sym) {
  try {
    const r = await fetch(`${STK}/api/stock/${sym}/summary`);
    const d = await r.json();
    const box = document.getElementById('stk-ai-box');
    if (!box) return;
    box.innerHTML = `<div class="ai-ttl">KI-Analyse</div>` +
      (d.error
        ? `<div style="color:var(--mu);font-size:13px">${_e(d.error)}</div>`
        : `<div class="ai-body">${_e(d.summary)}</div>`);
  } catch {
    const box = document.getElementById('stk-ai-box');
    if (box) box.innerHTML = `<div class="ai-ttl">KI-Analyse</div><div style="color:var(--mu);font-size:13px">Nicht verfügbar</div>`;
  }
}

function _chart(data, isUp) {
  const prices = data.map(d => d.close);
  const min = Math.min(...prices), max = Math.max(...prices);
  const rng = (max - min) || max * 0.005 || 1;
  const col = isUp ? 'var(--gn)' : 'var(--rd)';
  const W=660, H=150, pL=54, pR=10, pT=8, pB=26;
  const cw = W-pL-pR, ch = H-pT-pB, n = data.length;
  const px = i => pL + (i/(n-1))*cw;
  const py = v => pT + ch - ((v-min)/rng)*ch;

  const line = data.map((d,i) => `${i?'L':'M'}${px(i).toFixed(1)},${py(d.close).toFixed(1)}`).join('');
  const area = `${line} L${px(n-1).toFixed(1)},${(pT+ch).toFixed(1)} L${pL},${(pT+ch).toFixed(1)} Z`;
  const gid  = 'g' + Math.random().toString(36).slice(2,8);

  let grid='', yl='';
  for (let i=0; i<=4; i++) {
    const v=min+rng*i/4, yy=py(v).toFixed(1);
    grid += `<line x1="${pL}" y1="${yy}" x2="${W-pR}" y2="${yy}" stroke="var(--bd)" stroke-width="1" stroke-dasharray="3,3"/>`;
    yl   += `<text x="${pL-5}" y="${(+yy+4).toFixed(1)}" text-anchor="end" class="chart-lbl">${v.toFixed(2)}</text>`;
  }
  let xl='';
  [0,.25,.5,.75,1].forEach(f => {
    const i = Math.min(n-1, Math.round(f*(n-1)));
    xl += `<text x="${px(i).toFixed(1)}" y="${H-5}" text-anchor="middle" class="chart-lbl">${data[i].date.slice(5)}</text>`;
  });
  const lx=px(n-1).toFixed(1), ly=py(prices[n-1]).toFixed(1);

  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;overflow:visible">` +
    `<defs><linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">` +
    `<stop offset="0%" stop-color="${col}" stop-opacity=".18"/>` +
    `<stop offset="100%" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>` +
    `${grid}` +
    `<path d="${area}" fill="url(#${gid})"/>` +
    `<path d="${line}" style="stroke:${col}" stroke-width="1.8" fill="none" stroke-linejoin="round" stroke-linecap="round"/>` +
    `<circle cx="${lx}" cy="${ly}" r="4" style="fill:${col}" stroke="var(--sf)" stroke-width="2"/>` +
    `${yl}${xl}</svg>`;
}
</script>
</body>
</html>
"""


def build_html(briefings: list[dict]) -> str:
    data = json.dumps(briefings, ensure_ascii=False, indent=2)
    return HTML_TEMPLATE.replace("BRIEFINGS_DATA", data)


def main():
    briefings = load_briefings()
    localize(briefings)

    if not briefings:
        print("Keine Briefings in summaries/ gefunden.")
        return

    html = build_html(briefings)
    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"✓ {len(briefings)} Briefing(s) → {OUTPUT_FILE}")
    webbrowser.open(OUTPUT_FILE.as_uri())


if __name__ == "__main__":
    main()
