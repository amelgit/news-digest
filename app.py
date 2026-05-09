#!/usr/bin/env python3
"""Stock research API — Flask backend for index.html."""

import os
import requests
import yfinance as yf
from flask import Flask, jsonify, request
from flask_cors import CORS

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
CORS(app)


# ── Search ───────────────────────────────────────────────────────

def _yahoo_search(q: str, max_results: int = 8) -> list:
    url = "https://query2.finance.yahoo.com/v1/finance/search"
    params = {"q": q, "quotesCount": max_results, "newsCount": 0,
              "listsCount": 0, "enableFuzzyQuery": True}
    headers = {"User-Agent": "Mozilla/5.0 (compatible)"}
    resp = requests.get(url, params=params, headers=headers, timeout=5)
    resp.raise_for_status()
    return resp.json().get("quotes", [])


@app.route("/api/search")
def search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    try:
        quotes = _yahoo_search(q)
        out = []
        for r in quotes:
            if r.get("quoteType") not in ("EQUITY", "ETF"):
                continue
            out.append({
                "symbol":   r.get("symbol", ""),
                "name":     r.get("shortname") or r.get("longname") or r.get("symbol", ""),
                "exchange": r.get("exchange", ""),
                "type":     r.get("quoteType", ""),
            })
        return jsonify(out[:6])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Stock overview ───────────────────────────────────────────────

@app.route("/api/stock/<ticker>")
def stock_info(ticker):
    try:
        t = yf.Ticker(ticker.upper())
        info = t.info

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price is None:
            return jsonify({"error": f"Keine Kursdaten für {ticker.upper()}"}), 404

        prev = info.get("previousClose") or info.get("regularMarketPreviousClose") or price
        change = round(float(price) - float(prev), 4)
        change_pct = round(change / float(prev) * 100, 4) if prev else None

        return jsonify({
            "symbol":      info.get("symbol", ticker.upper()),
            "name":        info.get("longName") or info.get("shortName", ticker.upper()),
            "price":       round(float(price), 4),
            "change":      change,
            "change_pct":  change_pct,
            "market_cap":  info.get("marketCap"),
            "pe_ratio":    info.get("trailingPE") or info.get("forwardPE"),
            "week52_high": info.get("fiftyTwoWeekHigh"),
            "week52_low":  info.get("fiftyTwoWeekLow"),
            "volume":      info.get("volume") or info.get("regularMarketVolume"),
            "avg_volume":  info.get("averageVolume") or info.get("averageVolume10days"),
            "currency":    info.get("currency", "USD"),
            "sector":      info.get("sector"),
            "industry":    info.get("industry"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── 30-day price history ─────────────────────────────────────────

@app.route("/api/stock/<ticker>/history")
def stock_history(ticker):
    try:
        t = yf.Ticker(ticker.upper())
        hist = t.history(period="30d")
        if hist.empty:
            return jsonify({"error": "Keine Kursdaten verfügbar"}), 404

        data = [
            {
                "date":   str(ts.date()),
                "close":  round(float(row["Close"]), 4),
                "open":   round(float(row["Open"]), 4),
                "high":   round(float(row["High"]), 4),
                "low":    round(float(row["Low"]), 4),
                "volume": int(row["Volume"]),
            }
            for ts, row in hist.iterrows()
        ]
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── AI summary ───────────────────────────────────────────────────

@app.route("/api/stock/<ticker>/summary")
def stock_summary(ticker):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY nicht gesetzt"}), 500

    try:
        import anthropic

        t = yf.Ticker(ticker.upper())
        info = t.info
        news_raw = t.news[:6] if hasattr(t, "news") else []

        price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
        prev  = float(info.get("previousClose") or price)
        chg   = ((price - prev) / prev * 100) if prev else 0

        def _title(n):
            c = n.get("content", {})
            return (c.get("title") if isinstance(c, dict) else None) or n.get("title", "")

        headlines = [f"- {_title(n)}" for n in news_raw if _title(n)]
        news_block = "\n".join(headlines) or "Keine aktuellen Nachrichten."

        cap = info.get("marketCap")
        if cap and cap >= 1e12:
            cap_str = f"{cap/1e12:.2f} Bio. $"
        elif cap and cap >= 1e9:
            cap_str = f"{cap/1e9:.1f} Mrd. $"
        else:
            cap_str = "k.A."

        prompt = (
            f"Erstelle eine prägnante Zusammenfassung (3–4 Sätze) auf Deutsch für:\n"
            f"{info.get('longName', ticker)} ({ticker.upper()})\n\n"
            f"Daten: Kurs {price:.2f} {info.get('currency','USD')} ({chg:+.2f}% heute), "
            f"Marktkapitalisierung {cap_str}, Sektor {info.get('sector','k.A.')}, "
            f"KGV {info.get('trailingPE','k.A.')}\n\n"
            f"Aktuelle Schlagzeilen:\n{news_block}\n\n"
            f"Was bewegt die Aktie? Was sollten Investoren jetzt wissen?"
        )

        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=320,
            messages=[{"role": "user", "content": prompt}],
        )
        return jsonify({"summary": msg.content[0].text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("Stock Research API  →  http://localhost:5001")
    app.run(host="127.0.0.1", port=5001, debug=False)
