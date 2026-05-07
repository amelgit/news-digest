import os
import json
import subprocess
import yaml
import logging
from datetime import date, datetime
from pathlib import Path
from dotenv import load_dotenv

from scraper import scrape_source
from summarizer import generate_briefing, generate_market_analysis
from market_data import fetch_market_data

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def collect_headlines(config: dict) -> dict:
    max_per_source = config.get("max_headlines_per_source", 10)
    result = {}

    for category_key, category_data in config["sources"].items():
        all_headlines = []
        for site in category_data["sites"]:
            logger.info(f"Scraping {site['name']} …")
            headlines = scrape_source(site, max_per_source)
            if headlines:
                all_headlines.append(f"### {site['name']}")
                all_headlines.extend(headlines)
                logger.info(f"  → {len(headlines)} Schlagzeilen")
            else:
                logger.warning(f"  → Keine Schlagzeilen von {site['name']}")

        result[category_key] = {
            "name": category_data["name"],
            "headlines": all_headlines,
        }

    return result


def save_summary(summary: str, output_dir: str) -> Path:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    filepath = out_path / f"{today}.md"
    filepath.write_text(summary, encoding="utf-8")
    return filepath


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY ist nicht gesetzt. Bitte .env prüfen.")

    config = load_config()

    logger.info("Starte Schlagzeilen-Sammlung …")
    headlines = collect_headlines(config)
    total = sum(len(v["headlines"]) for v in headlines.values())
    logger.info(f"Insgesamt {total} Einträge gesammelt.")

    logger.info("Lade Marktdaten …")
    market = fetch_market_data()
    logger.info(f"{len(market)} Instrumente geladen.")

    model = config.get("model", "claude-sonnet-4-6")
    logger.info(f"Generiere Briefing mit {model} …")
    summary = generate_briefing(headlines, model)

    output_dir = config.get("output_dir", "summaries")
    filepath = save_summary(summary, output_dir)
    logger.info(f"Briefing gespeichert: {filepath}")

    analysis = None
    if market:
        today_str = date.today().isoformat()
        summaries_path = Path(output_dir)
        prev_md = next(
            (p for p in sorted(summaries_path.glob("*.md"), reverse=True) if p.stem != today_str),
            None,
        )
        if prev_md:
            logger.info(f"Generiere Marktanalyse (Vergleich mit {prev_md.stem}) …")
            analysis = generate_market_analysis(market, prev_md.read_text(encoding="utf-8"), model)

        market_path = filepath.with_suffix(".market.json")
        payload = {
            "instruments": market,
            "analysis": analysis,
            "fetched_at": datetime.now().strftime("%d.%m.%Y, %H:%M"),
        }
        market_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Marktdaten gespeichert: {market_path}")

    subprocess.run([
        "osascript", "-e",
        f'display notification "Morgen-Briefing vom {date.today().strftime("%d.%m.%Y")} wurde gespeichert." '
        f'with title "News Digest" subtitle "{total} Schlagzeilen verarbeitet" sound name "Glass"'
    ], check=False)


if __name__ == "__main__":
    main()
