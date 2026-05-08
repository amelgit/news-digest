import os
import sys
import json
import subprocess
import yaml
import logging
from datetime import date, datetime
from pathlib import Path
from scraper import scrape_source
from summarizer import generate_briefing, generate_market_analysis
from market_data import fetch_market_data

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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


def collect_headlines(config: dict) -> tuple:
    """Returns (headlines_for_claude, sources_structured)."""
    max_per_source = config.get("max_headlines_per_source", 10)
    claude_input = {}
    sources = []

    for category_key, category_data in config["sources"].items():
        text_lines = []
        for site in category_data["sites"]:
            logger.info(f"Scraping {site['name']} …")
            items = scrape_source(site, max_per_source)
            if items:
                text_lines.append(f"### {site['name']}")
                text_lines.extend(f"- {item['title']}" for item in items)
                logger.info(f"  → {len(items)} Schlagzeilen")
                sources.append({
                    "category": category_data["name"],
                    "source": site["name"],
                    "items": items,
                })
            else:
                logger.warning(f"  → Keine Schlagzeilen von {site['name']}")

        claude_input[category_key] = {
            "name": category_data["name"],
            "headlines": text_lines,
        }

    return claude_input, sources


def save_summary(summary: str, output_dir: str) -> Path:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    filepath = out_path / f"{today}.md"
    filepath.write_text(summary, encoding="utf-8")
    return filepath


def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY ist nicht gesetzt (Umgebungsvariable oder .env).")

    config = load_config()

    logger.info("Starte Schlagzeilen-Sammlung …")
    headlines, sources = collect_headlines(config)
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

    sources_path = filepath.with_suffix(".sources.json")
    sources_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Quellen gespeichert: {sources_path}")

    analysis = None
    market_path = None
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

    if sys.platform == "darwin":
        subprocess.run([
            "osascript", "-e",
            f'display notification "Briefing vom {date.today().strftime("%d.%m.%Y")} wurde gespeichert." '
            f'with title "News Digest" subtitle "{total} Schlagzeilen verarbeitet" sound name "Glass"'
        ], check=False)

    git_publish(filepath, market_path if market else None, sources_path)


def git_publish(md_path: Path, market_path: Path, sources_path: Path = None) -> None:
    repo = Path(__file__).parent
    today = date.today().isoformat()

    logger.info("Regeneriere index.html …")
    result = subprocess.run(
        ["python3", str(repo / "view.py")],
        cwd=repo, capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.warning(f"view.py fehlgeschlagen: {result.stderr.strip()}")
        return

    files = [str(md_path)]
    if market_path and market_path.exists():
        files.append(str(market_path))
    if sources_path and sources_path.exists():
        files.append(str(sources_path))
    files.append(str(repo / "index.html"))

    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)

    git("add", *files)

    staged = git("diff", "--cached", "--name-only")
    if not staged.stdout.strip():
        logger.info("Keine Änderungen zum Committen.")
        return

    msg = f"Briefing {today}"
    commit = git("commit", "-m", msg)
    if commit.returncode != 0:
        logger.warning(f"git commit fehlgeschlagen: {commit.stderr.strip()}")
        return
    logger.info(f"Committed: {msg}")

    push = git("push", "origin", "main")
    if push.returncode != 0:
        logger.warning(f"git push fehlgeschlagen: {push.stderr.strip()}")
        return
    logger.info("Gepusht nach GitHub.")


if __name__ == "__main__":
    main()
