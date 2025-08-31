# feed.py
import requests
import sys

def _fetch_coinbase(symbol):
    url = f"https://api.coinbase.com/v2/prices/{symbol}/spot"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return float(r.json()["data"]["amount"])

def _fetch_kraken(symbol):
    # Kraken uses "XDGUSD" for DOGE, "XBTUSD" for BTC, "ETHUSD" for ETH
    mapping = {"DOGE-USD": "XDGUSD", "BTC-USD": "XBTUSD", "ETH-USD": "ETHUSD", "SHIB-USB": "SHIBUSD"}
    pair = mapping.get(symbol, symbol.replace("-", ""))
    url = f"https://api.kraken.com/0/public/Ticker?pair={pair}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()["result"]
    return float(list(data.values())[0]["c"][0])  # last trade close price

def _fetch_robinhood(symbol):
    url = f"https://api.robinhood.com/marketdata/crypto/quotes/{symbol}/"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return float(r.json()["mark_price"])

def coinbase_spot(symbol, retries=3, base_delay=2):
    """
    Multi-source feed: try Coinbase → Kraken → Robinhood.
    Retries each source with exponential backoff before failing.
    """
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"

    prev_price = None
    sources = [
        ("Coinbase", _fetch_coinbase),
        ("Kraken", _fetch_kraken),
        ("Robinhood", _fetch_robinhood),
    ]

    for name, fn in sources:
        for i in range(retries):
            try:
                price = fn(symbol)
                if prev_price is not None:
                    diff = price - prev_price
                    if diff >= 0:
                        color = GREEN
                        sign = "+"
                    else:
                        color = RED
                        sign = "-"
                    sys.stdout.write(f"[feed] {name} price {symbol} = {price:.6f}   prev: {prev_price:.6f}, {color}{sign}{abs(diff):.6f}{RESET}\n")
                    sys.stdout.flush()
                prev_price = price
                return price
            except Exception as e:
                wait = base_delay * (2 ** i) + random.uniform(0, 1)
                print(f"[feed error] {name} {e} | retry {i+1}/{retries} in {wait:.1f}s")
                time.sleep(wait)
        print(f"[feed] {name} failed after {retries} retries, switching...")

    raise RuntimeError(f"All feeds failed for {symbol}")

def qty_from_usd(symbol: str, usd: float, side: str = "buy", decimals: int = 8) -> float:
    """
    Convert USD notional to asset quantity using Coinbase spot.
    - side adjusts a tiny bias so buys assume slightly higher price, sells slightly lower.
    - decimals clamps to typical crypto precision (RH will validate real steps per asset).
    """
    price = coinbase_spot(symbol)          # e.g., BTC-USD price
    if side == "buy":
        price *= 1.0085    # +85 bps skid
    elif side == "sell":
        price *= 1.0085    # -5 bps
    qty = usd / price
    # round to something sane; many assets allow up to 8 decimals
    return round(qty, decimals)



