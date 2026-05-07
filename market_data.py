import math
import logging
import yfinance as yf
from datetime import date, datetime as _dt, time as _time
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

INSTRUMENTS = [
    {"symbol": "^GDAXI",  "name": "DAX",       "decimals": 0, "prefix": "",  "url": "https://finance.yahoo.com/quote/%5EGDAXI/"},
    {"symbol": "^DJI",    "name": "Dow Jones",  "decimals": 0, "prefix": "",  "url": "https://finance.yahoo.com/quote/%5EDJI/"},
    {"symbol": "^GSPC",   "name": "S&P 500",    "decimals": 0, "prefix": "",  "url": "https://finance.yahoo.com/quote/%5EGSPC/"},
    {"symbol": "^IXIC",   "name": "NASDAQ",     "decimals": 0, "prefix": "",  "url": "https://finance.yahoo.com/quote/%5EIXIC/"},
    {"symbol": "CL=F",    "name": "Crude Oil",  "decimals": 2, "prefix": "$", "url": "https://finance.yahoo.com/quote/CL%3DF/"},
    {"symbol": "BTC-USD", "name": "Bitcoin",    "decimals": 0, "prefix": "$", "url": "https://finance.yahoo.com/quote/BTC-USD/"},
    {"symbol": "GC=F",    "name": "Gold",       "decimals": 2, "prefix": "$", "url": "https://finance.yahoo.com/quote/GC%3DF/"},
]

# Futures proxies for pre-market direction on US equity indices
_PREMARKET_PROXY = {
    "^DJI":  "YM=F",   # E-mini Dow Jones futures
    "^GSPC": "ES=F",   # E-mini S&P 500 futures
    "^IXIC": "NQ=F",   # E-mini NASDAQ 100 futures (proxy for Composite direction)
}


def _safe(value):
    try:
        f = float(value)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _pct_change(last, closes, offset):
    if len(closes) <= offset:
        return None
    old = _safe(closes.iloc[-(offset + 1)])
    if not old:
        return None
    return (last - old) / old * 100


def _market_state(symbol: str, now_utc) -> str:
    """Return 'open', 'pre', 'post', or 'closed' for the given instrument."""
    wd = now_utc.weekday()  # 0 = Monday, 6 = Sunday

    if symbol == "BTC-USD":
        return "open"  # trades 24/7

    if symbol == "^GDAXI":
        loc = now_utc.astimezone(ZoneInfo("Europe/Berlin"))
        t = loc.time()
        if wd >= 5:
            return "closed"
        return "open" if _time(9, 0) <= t <= _time(17, 30) else "closed"

    if symbol in _PREMARKET_PROXY:
        loc = now_utc.astimezone(ZoneInfo("America/New_York"))
        t = loc.time()
        if wd >= 5:
            return "closed"
        if _time(4, 0) <= t < _time(9, 30):
            return "pre"
        if _time(9, 30) <= t <= _time(16, 0):
            return "open"
        if _time(16, 0) < t <= _time(20, 0):
            return "post"
        return "closed"

    if symbol in ("CL=F", "GC=F"):
        # CME Globex: nearly 24/7 on weekdays with 1-hour break at 5 PM ET
        loc = now_utc.astimezone(ZoneInfo("America/New_York"))
        t = loc.time()
        if wd == 6 and t < _time(18, 0):
            return "closed"
        if wd == 5:
            return "closed"
        if _time(17, 0) <= t < _time(18, 0):
            return "closed"
        return "open"

    return "closed"


def fetch_market_data() -> list:
    results = []
    current_year = str(date.today().year)
    now_utc = _dt.now(ZoneInfo("UTC"))

    for inst in INSTRUMENTS:
        try:
            ticker = yf.Ticker(inst["symbol"])
            hist = ticker.history(period="1y")
            if hist.empty:
                logger.warning(f"No data for {inst['name']}")
                continue

            last_close = _safe(hist["Close"].iloc[-1])
            if last_close is None:
                continue

            week52_low  = _safe(hist["Low"].min())
            week52_high = _safe(hist["High"].max())

            ytd_mask = hist.index.strftime("%Y") == current_year
            ytd_hist = hist[ytd_mask]
            ytd_pct = None
            if not ytd_hist.empty:
                ytd_start = _safe(ytd_hist["Close"].iloc[0])
                if ytd_start:
                    ytd_pct = (last_close - ytd_start) / ytd_start * 100

            prev_close = _safe(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
            day_abs = (last_close - prev_close) if prev_close is not None else None
            day_pct = (last_close - prev_close) / prev_close * 100 if prev_close else None
            last_date = hist.index[-1].strftime("%d.%m.%Y")

            mstate = _market_state(inst["symbol"], now_utc)

            # Pre-market direction via futures (US equity indices only)
            pre_pct = None
            proxy_sym = _PREMARKET_PROXY.get(inst["symbol"])
            if proxy_sym:
                try:
                    fi = yf.Ticker(proxy_sym).fast_info
                    f_current = _safe(fi.last_price)
                    f_prev    = _safe(fi.regular_market_previous_close)
                    if f_current and f_prev:
                        pre_pct = (f_current - f_prev) / f_prev * 100
                except Exception as e:
                    logger.warning(f"Pre-market proxy unavailable for {inst['name']}: {e}")

            results.append({
                "name":        inst["name"],
                "last_close":  last_close,
                "last_date":   last_date,
                "day_abs":     day_abs,
                "day_pct":     day_pct,
                "week52_low":  week52_low,
                "week52_high": week52_high,
                "ytd_pct":     ytd_pct,
                "month_pct":   _pct_change(last_close, hist["Close"], 21),
                "week_pct":    _pct_change(last_close, hist["Close"], 5),
                "decimals":    inst["decimals"],
                "prefix":      inst["prefix"],
                "url":         inst.get("url", ""),
                "market_state": mstate,
                "pre_pct":     pre_pct,
            })
            logger.info(f"  → {inst['name']}: {last_close:.2f} [{mstate}]"
                        + (f"  futs: {pre_pct:+.2f}%" if pre_pct is not None else ""))
        except Exception as e:
            logger.warning(f"Failed to fetch {inst['name']}: {e}")

    return results
