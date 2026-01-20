import os, time, json, base64, requests
from nacl.signing import SigningKey
from dotenv import load_dotenv

load_dotenv()

BASE = "https://trading.robinhood.com"
ORDERS = "/api/v1/crypto/trading/orders/"

def _canon(d: dict | None) -> str:
    if not d: return ""
    return json.dumps(d, separators=(',', ':'), sort_keys=True)

class RH:
    def __init__(self, api_key=None, priv_b64=None, dry_run=None):
        self.api_key = api_key or os.getenv("RH_API_KEY")
        priv_b64 = priv_b64 or os.getenv("RH_PRIVATE_KEY_B64")
        if not self.api_key or not priv_b64:
            raise ValueError("Missing RH_API_KEY or RH_PRIVATE_KEY_B64")
        self.key = SigningKey(base64.b64decode(priv_b64))
        self.dry = (str(dry_run).lower()=="true") if dry_run is not None else (os.getenv("RH_DRY_RUN","true").lower()=="true")

    def _sign(self, method: str, path: str, body: dict | None):
        ts = str(int(time.time()))
        msg = f"{self.api_key}{ts}{path}{method.upper()}{_canon(body)}"
        sig = self.key.sign(msg.encode()).signature
        return ts, base64.b64encode(sig).decode()

    def _headers(self, method, path, body):
        ts, sig = self._sign(method, path, body)
        return {
            "x-api-key": self.api_key,
            "x-timestamp": ts,
            "x-signature": sig,
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _req(self, method: str, path: str, body: dict | None = None):
        url = BASE + path
        hdr = self._headers(method, path, body)
        if self.dry and method.upper()=="POST":
            redacted = {**hdr, "x-api-key":"***", "x-signature":"***"}
            return {"dry_run": True, "url": url, "headers": redacted, "body": body}
        payload = _canon(body) if body is not None else None
        r = requests.request(
            method.upper(),
            url,
            headers=hdr,
            data=payload,                     # send EXACT json we signed
            timeout=30
        )
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text}") from e
        return r.json() if r.content else {}

    # ---- public methods ----
    def list_orders(self):
        return self._req("GET", ORDERS, None)   # signed GET with empty body

    def market_order(self, symbol: str, side: str,
                     quantity: float | None = None, usd_notional: float | None = None,
                     client_order_id: str | None = None):
        if side not in ("buy","sell"):
            raise ValueError("side must be buy/sell")
        if (quantity is None) == (usd_notional is None):
            raise ValueError("provide exactly one of quantity or usd_notional")
        body = {
            "client_order_id": client_order_id or __import__("uuid").uuid4().hex,
            "side": side,
            "symbol": symbol,
            "type": "market",
            "market_order_config": {}
        }
        if quantity is not None:
            body["market_order_config"]["asset_quantity"] = str(quantity)
        else:
            body["market_order_config"]["usd_notional"] = str(usd_notional)
        return self._req("POST", ORDERS, body)



