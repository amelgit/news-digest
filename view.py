#!/usr/bin/env python3
"""Generates briefings.html from all markdown files in summaries/ and opens it."""

import os
import re
import json
import webbrowser
from pathlib import Path
from datetime import datetime

SUMMARIES_DIR = Path(__file__).parent / "summaries"
OUTPUT_FILE = Path(__file__).parent / "briefings.html"


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
        if ppct is not None:
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
        briefings.append({
            "id": path.stem,
            "date": path.stem,
            "date_display": date.strftime("%-d. %B %Y"),
            "weekday": date.strftime("%A"),
            "html": html,
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
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morgen-Briefings</title>
<style>
  :root {
    --sidebar-bg: #111827;
    --sidebar-text: #d1d5db;
    --sidebar-active: #f3f4f6;
    --sidebar-hover: #1f2937;
    --sidebar-accent: #3b82f6;
    --main-bg: #f9fafb;
    --card-bg: #ffffff;
    --text: #111827;
    --text-muted: #6b7280;
    --heading: #0f172a;
    --border: #e5e7eb;
    --hr: #e5e7eb;
    --link: #2563eb;
    --code-bg: #f1f5f9;
    --today-badge: #3b82f6;
    --sidebar-w: 260px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: var(--main-bg);
    color: var(--text);
    display: flex;
    height: 100vh;
    overflow: hidden;
  }

  /* ── Sidebar ── */
  #sidebar {
    width: var(--sidebar-w);
    min-width: var(--sidebar-w);
    background: var(--sidebar-bg);
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  #sidebar-header {
    padding: 24px 20px 16px;
    border-bottom: 1px solid #1f2937;
  }
  #sidebar-header h1 {
    font-size: 15px;
    font-weight: 700;
    color: #f9fafb;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  #sidebar-header p {
    font-size: 12px;
    color: var(--sidebar-text);
    margin-top: 4px;
  }
  #nav {
    flex: 1;
    overflow-y: auto;
    padding: 12px 0;
  }
  #nav::-webkit-scrollbar { width: 4px; }
  #nav::-webkit-scrollbar-track { background: transparent; }
  #nav::-webkit-scrollbar-thumb { background: #374151; border-radius: 2px; }
  .nav-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 20px;
    cursor: pointer;
    border-left: 3px solid transparent;
    transition: background 0.15s, border-color 0.15s;
  }
  .nav-item:hover { background: var(--sidebar-hover); }
  .nav-item.active {
    background: #1e3a5f;
    border-left-color: var(--sidebar-accent);
  }
  .nav-date {
    flex: 1;
  }
  .nav-weekday {
    font-size: 11px;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .nav-datestr {
    font-size: 13px;
    color: var(--sidebar-active);
    font-weight: 500;
    margin-top: 1px;
  }
  .nav-item.active .nav-datestr { color: #93c5fd; }
  .today-badge {
    font-size: 10px;
    font-weight: 600;
    background: var(--today-badge);
    color: white;
    padding: 2px 7px;
    border-radius: 10px;
    letter-spacing: 0.03em;
  }

  /* ── Main content ── */
  #main {
    flex: 1;
    overflow-y: auto;
    padding: 40px;
  }
  #main::-webkit-scrollbar { width: 6px; }
  #main::-webkit-scrollbar-track { background: var(--main-bg); }
  #main::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 3px; }
  .briefing { display: none; }
  .briefing.visible { display: block; }
  .briefing-card {
    max-width: 780px;
    margin: 0 auto;
    background: var(--card-bg);
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,.06), 0 4px 16px rgba(0,0,0,.04);
    padding: 40px 48px;
  }
  .briefing-card h1 {
    font-size: 26px;
    font-weight: 800;
    color: var(--heading);
    line-height: 1.25;
    margin-bottom: 6px;
  }
  .briefing-card h2 {
    font-size: 18px;
    font-weight: 700;
    color: var(--heading);
    margin: 32px 0 12px;
    padding-bottom: 6px;
    border-bottom: 2px solid var(--border);
  }
  .briefing-card h3 {
    font-size: 15px;
    font-weight: 600;
    color: var(--heading);
    margin: 20px 0 8px;
  }
  .briefing-card p {
    font-size: 15px;
    line-height: 1.75;
    color: #374151;
    margin-bottom: 12px;
  }
  .briefing-card ul {
    list-style: none;
    padding: 0;
    margin-bottom: 8px;
  }
  .briefing-card ul li {
    font-size: 15px;
    line-height: 1.7;
    color: #374151;
    padding: 5px 0 5px 20px;
    position: relative;
  }
  .briefing-card ul li::before {
    content: "→";
    position: absolute;
    left: 0;
    color: var(--sidebar-accent);
    font-size: 13px;
    top: 7px;
  }
  .briefing-card hr {
    border: none;
    border-top: 1px solid var(--hr);
    margin: 24px 0;
  }
  .briefing-card strong { color: var(--heading); }
  .briefing-card em { color: #4b5563; }
  .briefing-card code {
    background: var(--code-bg);
    padding: 1px 6px;
    border-radius: 4px;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 13px;
  }
  .briefing-card a {
    color: var(--link);
    text-decoration: none;
  }
  .briefing-card a:hover { text-decoration: underline; }

  /* ── Market Widget ── */
  .mkt-widget {
    background: #f8fafc;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px 22px;
    margin-bottom: 28px;
  }
  .mkt-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;
  }
  .mkt-title {
    font-size: 17px;
    font-weight: 700;
    color: var(--heading);
  }
  .mkt-date-label {
    font-size: 11px;
    color: var(--text-muted);
    white-space: nowrap;
  }
  .mkt-table {
    width: 100%;
    border-collapse: collapse;
  }
  .mkt-table th {
    font-size: 10px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 0 6px 6px;
    border-bottom: 1px solid var(--border);
    text-align: right;
    white-space: nowrap;
  }
  .mkt-table th:first-child { text-align: left; }
  .mkt-table th:nth-child(3) { text-align: left; }
  .mkt-table td {
    padding: 5px 6px;
    border-bottom: 1px solid #f1f5f9;
    vertical-align: middle;
    font-size: 12px;
  }
  .mkt-table tr:last-child td { border-bottom: none; }
  .mkt-name { font-weight: 600; color: var(--heading); white-space: nowrap; }
  .mkt-close {
    text-align: right;
    font-family: "SF Mono", "Fira Code", monospace;
    color: var(--text);
    white-space: nowrap;
  }
  .mkt-range { min-width: 150px; padding-top: 7px !important; padding-bottom: 7px !important; }
  .mkt-range-labels {
    display: flex;
    justify-content: space-between;
    font-size: 9px;
    color: var(--text-muted);
    font-family: "SF Mono", "Fira Code", monospace;
    margin-bottom: 3px;
  }
  .mkt-track {
    height: 3px;
    background: #e5e7eb;
    border-radius: 2px;
    position: relative;
  }
  .mkt-dot {
    position: absolute;
    width: 8px;
    height: 8px;
    background: var(--sidebar-accent);
    border-radius: 50%;
    top: -2.5px;
    transform: translateX(-50%);
    box-shadow: 0 0 0 2px #f8fafc;
  }
  .mkt-pct {
    text-align: right;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }
  .mkt-pos { color: #16a34a; }
  .mkt-neg { color: #dc2626; }
  .mkt-neutral { color: var(--text-muted); }
  .mkt-day { border-left: 2px solid var(--border); }
  .mkt-link { color: inherit; text-decoration: none; border-bottom: 1px dotted #9ca3af; }
  .mkt-link:hover { color: var(--link); border-bottom-color: var(--link); }
  .mkt-status { font-size: 9px; margin-right: 5px; }
  .mkt-status-open   { color: #22c55e; }
  .mkt-status-pre    { color: #f59e0b; }
  .mkt-status-post   { color: #f59e0b; }
  .mkt-status-closed { color: #d1d5db; }
  .mkt-pre {
    display: block;
    font-size: 10px;
    font-family: "SF Mono", "Fira Code", monospace;
    margin-top: 2px;
  }
  .mkt-pre-label { color: var(--text-muted); }
  .mkt-pre-pos { color: #16a34a; }
  .mkt-pre-neg { color: #dc2626; }
  .mkt-analysis {
    margin-top: 14px;
    padding: 12px 16px;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 8px;
    font-size: 13px;
    line-height: 1.65;
    color: #1e3a5f;
  }
  .mkt-analysis-title {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #3b82f6;
    margin-bottom: 6px;
  }
  .mkt-analysis p { margin: 0 0 6px; font-size: 13px; color: #1e3a5f; line-height: 1.65; }
  .mkt-analysis p:last-child { margin-bottom: 0; }

  /* ── Responsive ── */
  @media (max-width: 700px) {
    body { flex-direction: column; overflow: auto; height: auto; }
    #sidebar { width: 100%; min-width: unset; height: auto; }
    #nav { display: flex; overflow-x: auto; padding: 8px; gap: 6px; }
    .nav-item { min-width: 130px; border-left: none; border-bottom: 3px solid transparent; border-radius: 8px; }
    .nav-item.active { border-bottom-color: var(--sidebar-accent); }
    #main { padding: 20px 16px; }
    .briefing-card { padding: 24px 20px; }
  }
</style>
</head>
<body>

<nav id="sidebar">
  <div id="sidebar-header">
    <h1>Morgen-Briefings</h1>
    <p id="count-label"></p>
  </div>
  <div id="nav"></div>
</nav>

<main id="main">
  <div id="content"></div>
</main>

<script>
const briefings = BRIEFINGS_DATA;

const today = new Date().toISOString().slice(0, 10);
const nav = document.getElementById("nav");
const content = document.getElementById("content");

document.getElementById("count-label").textContent =
  briefings.length + " Ausgabe" + (briefings.length !== 1 ? "n" : "");

briefings.forEach((b, i) => {
  // Nav item
  const item = document.createElement("div");
  item.className = "nav-item";
  item.dataset.id = b.id;
  const isToday = b.date === today;
  item.innerHTML = `
    <div class="nav-date">
      <div class="nav-weekday">${b.weekday}</div>
      <div class="nav-datestr">${b.date_display}</div>
    </div>
    ${isToday ? '<span class="today-badge">Heute</span>' : ""}
  `;
  item.addEventListener("click", () => show(b.id));
  nav.appendChild(item);

  // Content panel
  const panel = document.createElement("div");
  panel.className = "briefing";
  panel.id = "briefing-" + b.id;
  panel.innerHTML = `<div class="briefing-card">${b.html}</div>`;
  content.appendChild(panel);
});

function show(id) {
  document.querySelectorAll(".briefing").forEach(el => el.classList.remove("visible"));
  document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));
  document.getElementById("briefing-" + id)?.classList.add("visible");
  document.querySelector(`.nav-item[data-id="${id}"]`)?.classList.add("active");
  document.getElementById("main").scrollTo(0, 0);
}

// Show newest (first) briefing on load
if (briefings.length > 0) show(briefings[0].id);
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
