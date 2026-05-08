import anthropic
from datetime import date

SYSTEM_PROMPT = """Du bist ein erfahrener Nachrichtenredakteur. Deine Aufgabe ist es, \
aus täglich gesammelten Schlagzeilen ein strukturiertes Briefing auf Deutsch zu erstellen.

Dein Briefing soll:
- Professionell und prägnant geschrieben sein
- Die wichtigsten Entwicklungen klar herausstellen
- Nach Kategorien gegliedert sein
- Pro Kategorie 3–5 Kernaussagen als Aufzählungsliste enthalten
- Mit einer kurzen Einleitung (2–3 Sätze) beginnen
- Mit einem kurzen Ausblick (1–2 Sätze) enden

Formatiere das Ergebnis als Markdown."""


def generate_briefing(headlines_by_category: dict, model: str) -> str:
    client = anthropic.Anthropic()

    today = date.today().strftime("%d.%m.%Y")
    content = f"Heute ist der {today}. Hier sind die aktuellen Schlagzeilen nach Kategorie:\n\n"

    for category_data in headlines_by_category.values():
        content += f"## {category_data['name']}\n"
        headlines = category_data["headlines"]
        if headlines:
            content += "\n".join(headlines)
        else:
            content += "_Keine Schlagzeilen verfügbar._"
        content += "\n\n"

    content += (
        "Erstelle bitte ein strukturiertes Briefing mit einer Einleitung, "
        "3–5 Kernpunkten pro Kategorie und einem kurzen Ausblick. Verwende Markdown."
    )

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": content}],
    )

    return response.content[0].text


def generate_market_analysis(market_data: list, previous_briefing: str, model: str) -> str:
    client = anthropic.Anthropic()

    lines = []
    for item in market_data:
        pct = item.get("day_pct")
        abs_chg = item.get("day_abs")
        if pct is None:
            continue
        sign = "+" if pct >= 0 else ""
        d, p = item.get("decimals", 2), item.get("prefix", "")
        abs_str = (
            f"{'+'if abs_chg>=0 else ''}{p}{abs_chg:,.{d}f}"
            if abs_chg is not None else "—"
        )
        lines.append(f"- {item['name']}: {sign}{pct:.2f}% ({abs_str})")

    prompt = (
        f"Heutige Kursbewegungen im Vergleich zum Vortag:\n" + "\n".join(lines) +
        f"\n\nGestrige Nachrichten (Briefing vom Vortag):\n{previous_briefing}\n\n"
        "Analysiere in maximal 5 prägnanten Sätzen auf Deutsch, ob die heutigen Kursbewegungen "
        "wirtschaftlich plausibel im Kontext der gestrigen Nachrichten sind. "
        "Nenne konkrete Kausalzusammenhänge, wo dies sinnvoll ist. "
        "Hebe hervor, wenn eine Bewegung überraschend oder kontraintuitiv ist. "
        "Beende deine Antwort zwingend mit einem vollständigen Satz."
    )

    response = client.messages.create(
        model=model,
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
