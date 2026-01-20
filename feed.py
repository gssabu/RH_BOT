# feed.py
import time
import random
import requests

# ------- Provider fetchers -------

def _fetch_coinbase(symbol: str) -> float:
    # Coinbase v2 spot
    url = f"https://api.coinbase.com/v2/prices/{symbol}/spot"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return float(r.json()["data"]["amount"])

def _fetch_kraken(symbol: str) -> float:
    """
    Kraken pair mapping:
      BTC-USD -> XBTUSD
      ETH-USD -> ETHUSD
      DOGE-USD -> XDGUSD
      SHIB-USD -> SHIBUSD
    """
    mapping = {
        "BTC-USD": "XBTUSD",
        "ETH-USD": "ETHUSD",
        "DOGE-USD": "XDGUSD",
        "SHIB-USD": "SHIBUSD",  # <-- fixed typo (was SHIB-USB)
    }
    pair = mapping.get(symbol, symbol.replace("-", ""))  # default heuristic
    url = f"https://api.kraken.com/0/public/Ticker?pair={pair}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    j = r.json()
    if j.get("error"):
        raise RuntimeError(j["error"])
    # Kraken returns dict keyed by the pair code; 'c'[0] is last trade price
    k = next(iter(j["result"].keys()))
    return float(j["result"][k]["c"][0])

# ------- Core helpers -------

# small in-memory cache so we can fall back if both providers fail
_LAST_PRICE = {}

def _try_with_retries(fn, attempts=2, backoff=0.3):
    last_err = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(backoff * (2 ** i))
    raise last_err

def get_price(symbol: str, side: str | None = None, bias_bps: int = 50) -> float:
    """
    Return a spot price for symbol (e.g., 'BTC-USD').
    Optional 'side' applies a conservative bias:
      buy  -> +bias_bps
      sell -> -bias_bps
    """
    providers = [_fetch_coinbase, _fetch_kraken]
    # randomize order a bit to avoid always hammering one provider
    random.shuffle(providers)

    price = None
    err = None
    for fn in providers:
        try:
            price = _try_with_retries(lambda: fn(symbol))
            break
        except Exception as e:
            err = e
            continue

    if price is None:
        # last-resort: stale cache if we have it
        if symbol in _LAST_PRICE:
            price = _LAST_PRICE[symbol]
        else:
            # surface the last provider error
            raise RuntimeError(f"all providers failed for {symbol}: {err!r}")

    # apply side bias (slippage cushion) consistently with comment
    if side == "buy":
        price *= (1.0 + bias_bps / 10_000.0)   # +50 bps by default
    elif side == "sell":
        price *= (1.0 - bias_bps / 10_000.0)   # -50 bps by default

    # update cache with unbiased price for next time
    _LAST_PRICE[symbol] = price / (1.0 + bias_bps / 10_000.0) if side == "buy" else \
                          price / (1.0 - bias_bps / 10_000.0) if side == "sell" else price
    return float(price)

def qty_from_usd(usd: float, price: float, decimals: int = 8) -> float:
    """
    Convert USD notional to asset quantity, honoring exchange decimals.
    """
    if price <= 0:
        raise ValueError("price must be > 0")
    qty = usd / price
    # many crypto assets permit up to 8 decimals; clamp to provided rule
    q = round(qty, decimals)
    # guard tiny non-zero that rounds to 0 after broker truncation
    if q == 0.0 and qty > 0:
        step = 10 ** (-decimals)
        q = step
    return q
