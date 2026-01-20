# main.py
import argparse, json, time, os
from client import RH
from feed import coinbase_spot, qty_from_usd
from strategy import SMAStrategy, PriceMoveStrategy, SwingStrategy, SwingWithTrend
from risk import Risk
from paper_account import PaperAccount
import datetime
from alerts import send_trade_email


# Per-symbol precision + min USD (tweak if RH rejects sizes)
ASSET_RULES = {
    "BTC-USD": {"decimals": 2, "min_usd": 0.01},
    "ETH-USD": {"decimals": 2, "min_usd": 0.10},
    "DOGE-USD": {"decimals": 2, "min_usd": 0.15},
    "SHIB-USD": {"decimals": 9, "min_usd": 0.05},
}

def _fmt(x, nd=8):
    return f"{x:.{nd}f}" if isinstance(x, (int, float)) else "None"

def load_limits(path="limits.json"):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)

def allowed_time():
    now = datetime.datetime.utcnow().hour
    # e.g., only trade 12:00–22:00 UTC
    return 12 <= now <= 22

def cmd_list(_):
    rh = RH()
    print(json.dumps(rh.list_orders(), indent=2))

def cmd_market_order(a):
    rh = RH()
    if a.notional is not None:
        dec = ASSET_RULES.get(a.symbol, {}).get("decimals", 8)
        qty = qty_from_usd(a.symbol, a.notional, side=a.side, decimals=dec)
        res = rh.market_order(a.symbol, a.side, quantity=qty)  # send quantity
    else:
        res = rh.market_order(a.symbol, a.side, quantity=a.quantity)
    print(json.dumps(res, indent=2))

def cmd_sma_bot(a):
    rh = RH()
    account = PaperAccount(usd_start=10000.0)

    if a.strategy == "sma":
        strat = SMAStrategy(a.short, a.long)
        print(f"Running SMA strategy: short={a.short}, long={a.long}")
    elif a.strategy == "swing":
        strat = SwingStrategy(threshold=a.threshold)
        print(f"Running Swing strategy: threshold={a.threshold}")
    elif a.strategy == "swingT":
        limits = load_limits()
        coin = a.symbol.upper()   # "SHIB-USD"
        coin_limits = limits.get(coin, {})

        strat = SwingWithTrend(
            buy_pct=a.buy_pct,    
            sell_pct=a.sell_pct,  
            atr_mult=a.atr_mult,
            atr_window=a.atr_window,
            rsi_window=a.rsi_window,
            trend_window=a.trend,
            mb = coin_limits.get("max_buy_price"),
            ms = coin_limits.get("min_sell_price")
        
        )
        print(
            "Running Swing-with-Trend strategy: "
            f"Buy%={a.buy_pct} "
            f"Sell%={a.sell_pct} "
            f"trend_window={a.trend} "
            f"max_buy_price={_fmt(mb)} "
            f"min_sell_price={_fmt(ms)}"
        )
        
    else:
        strat = PriceMoveStrategy(threshold=a.threshold)
        print(f"Running PriceMove strategy: threshold={a.threshold}")
        

    risk = Risk(
        max_per_order=a.notional,
        max_daily=max(5 * a.notional, 25.0),
        cooldown=6,
        trail_pct=a.trail,
    )

    symbol = a.symbol
    position = 0
    entry = None
    peak = None

    dec = ASSET_RULES.get(symbol, {}).get("decimals", 8)
    min_usd = ASSET_RULES.get(symbol, {}).get("min_usd", 0.05)

    print(f"Bot start | {symbol} strategy={a.strategy} notional=${a.notional} live={a.live}")
    try:
        while True:
            try:
                p = coinbase_spot(symbol)
            except Exception as e:
                print("price error:", e)
                time.sleep(a.period)
                continue

            sig = strat.update(p)

            # trailing stop check
            if position == 1:
                peak = p if peak is None else max(peak, p)
                drop_pct = (peak - p) / peak * 100 if peak else 0.0
                if drop_pct >= risk.trail_pct:
                    trade_usd = max(a.notional, min_usd)
                    qty = qty_from_usd(symbol, trade_usd, side="sell", decimals=dec)
                    if a.live:
                        out = rh.market_order(symbol, "sell", quantity=qty)
                        print(out)
                    else:
                        account.sell(qty, p, symbol)
                        print(f"\n(paper) TRAIL STOP SELL {symbol} qty={qty} @ {p:.8f} | {account.summary(p)}")
                        trade_msg = f"TRAIL SELL {symbol} qty={qty} @ {p:.8f}"                   
                        send_trade_email(trade_msg)
                    position, entry, peak = 0, None, None

            # entry/exit
            if sig in ("bull", "buy") and position == 0:
                ok, why = risk.allow(a.notional)
                if not ok:
                    print("blocked buy:", why)
                else:
                    trade_usd = max(a.notional, min_usd)
                    qty = qty_from_usd(symbol, trade_usd, side="buy", decimals=dec)
                    if a.live:
                        out = rh.market_order(symbol, "buy", quantity=qty)
                        print(out)
                        trade_msg = f"\nBUY {symbol} qty={qty} @ {p:.8f}"
                        print(trade_msg)
                        #send_trade_email(trade_msg)
                        risk.record(trade_usd)
                    else:
                        account.buy(qty, p, symbol)
                        print(f"\n(paper) BUY {symbol} qty={qty} @ {p:.8f} | {account.summary(p)}")
                        trade_msg = f"BUY {symbol} qty={qty} @ {p:.8f}"
                        #print(trade_msg)
                        send_trade_email(trade_msg)
                    position, entry, peak = 1, p, p

            elif sig in ("bear", "sell") and position == 1:
                trade_usd = max(a.notional, min_usd)
                qty = min(account.asset, qty_from_usd(symbol, trade_usd, side="sell", decimals=dec))
                if a.live:
                    out = rh.market_order(symbol, "sell", quantity=qty)
                    trade_msg = f"\nSELL {symbol} qty={qty} @ {p:.8f}"
                    #send_trade_email(trade_msg)
                    print(out)
                else:
                    account.sell(qty, p, symbol)
                    print(f"\n(paper) SELL {symbol} qty={qty} @ {p:.8f} | {account.summary(p)}")
                    trade_msg = f"SELL {symbol} qty={qty} @ {p:.8f}"                   
                    send_trade_email(trade_msg)
                position, entry, peak = 0, None, None

            time.sleep(a.period)

    except KeyboardInterrupt:
        fname = account.export_csv()
        print(f"\nStopped. Trade history saved to {fname}")


def build():
    p = argparse.ArgumentParser("rhbot")
    sub = p.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("list-orders")
    s1.set_defaults(func=cmd_list)

    s2 = sub.add_parser("market-order")
    s2.add_argument("--side", choices=["buy", "sell"], required=True)
    s2.add_argument("--symbol", required=True)
    g = s2.add_mutually_exclusive_group(required=True)
    g.add_argument("--quantity", type=float)
    g.add_argument("--notional", type=float)
    s2.set_defaults(func=cmd_market_order)

    s3 = sub.add_parser("sma-bot", help="Run trading bot")
    s3.add_argument("--symbol", default="DOGE-USD")
    s3.add_argument("--short", type=int, default=10)
    s3.add_argument("--long", type=int, default=30)
    s3.add_argument("--period", type=int, default=15, help="seconds between polls")
    s3.add_argument("--notional", type=float, default=0.05, help="USD per trade")
    s3.add_argument("--live", action="store_true", help="send real orders")
    s3.add_argument("--trail", type=float, default=2.0, help="trailing stop in %")
    s3.add_argument("--strategy", choices=["sma", "move", "swing", "swingT"], default="sma", help="strategy type")
    s3.add_argument("--threshold", type=float, default=0.0001, help="price move threshold (for 'move' strategy)")
    s3.add_argument("--trend", type=int, default=50, help="trend SMA window (for swing)")
    s3.add_argument("--no-atr", action="store_true", help="disable ATR filter")
    s3.add_argument("--no-rsi", action="store_true", help="disable RSI filter")
    s3.add_argument("--atr-mult", type=float, default=1.0, help="ATR multiplier")
    s3.add_argument("--atr-window", type=int, default=14, help="ATR window length")
    s3.add_argument("--rsi-window", type=int, default=14, help="RSI window length")
    s3.add_argument("--buy_pct", type=float, default=1.0, help="Percent dip from recent high to trigger buy (for swingT strategy)")
    s3.add_argument("--sell_pct", type=float, default=3.0, help="Percent rise from recent low to trigger sell (for swingT strategy)")
    s3.set_defaults(func=cmd_sma_bot)

    return p

if __name__ == "__main__":
    args = build().parse_args()
    args.func(args)





















