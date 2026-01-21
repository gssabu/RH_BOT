# main.py
import argparse, json, time, os
from client import RH
from feed import coinbase_spot, qty_from_usd
from strategy import SwingWithTrend, SwingConfig
from risk import Risk
from paper_account import PaperAccount
import datetime
from alerts import send_trade_email
import csv


# Per-symbol precision + min USD (tweak if RH rejects sizes)
ASSET_RULES = {
    "BTC-USD": {"decimals": 2, "min_usd": 0.01},
    "ETH-USD": {"decimals": 2, "min_usd": 0.10},
    "DOGE-USD": {"decimals": 2, "min_usd": 0.15},
    "SHIB-USD": {"decimals": 9, "min_usd": 0.05},
}

def append_live_csv(path: str, row: dict):
    keys = ["ts","symbol","side","qty","price","notional","order_id","state","note"]
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        if new_file:
            w.writeheader()
        w.writerow({k: row.get(k) for k in keys})
        f.flush()
        os.fsync(f.fileno())

def _to_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def load_last_trade(csv_path: str, symbol: str):
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        return None
    last = None
    with open(csv_path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if (row.get("symbol") or "").upper() == symbol.upper():
                last = row
    return last

def wait_for_fill(rh: RH, order_id: str, timeout=45, poll=1.0):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        od = rh.get_order(order_id)
        last = od
        state = str(od.get("state") or od.get("status") or "").lower()
        if state in ("filled", "completed"):
            return od
        if state in ("canceled", "rejected", "failed", "error"):
            return od
        time.sleep(poll)
    return last

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
        p = coinbase_spot(a.symbol)
        dec = ASSET_RULES.get(a.symbol, {}).get("decimals", 8)
        qty = qty_from_usd(trade_usd, p, decimals=dec)
        res = rh.market_order(a.symbol, a.side, quantity=qty)  # send quantity
    else:
        res = rh.market_order(a.symbol, a.side, quantity=a.quantity)
    print(json.dumps(res, indent=2))


def cmd_sma_bot(a):
    symbol = a.symbol
    position = 0
    entry = None
    peak = None
    cycle_usd = 0.0
    est_tranche_qty
    rh = RH()
    account = PaperAccount(starting_usd=11000.0)
    state_csv = "live_trades.csv" if a.live else "paper_trades.csv"
    last = load_last_trade(state_csv, symbol)
    
    # estimated tranche qty held (used in live mode safety)
    est_tranche_qty = 0.0
    
    if last:
        last_side = (last.get("side") or "").lower()
        last_price = _to_float(last.get("price"), 0.0)
        last_notional = _to_float(last.get("notional"), 0.0)
        last_qty = _to_float(last.get("qty"), 0.0)
    
        # paper CSV has fee + cash_after. live CSV doesn't (currently).
        last_fee = _to_float(last.get("fee"), 0.0) if "fee" in (last or {}) else 0.0
        last_cash = _to_float(last.get("cash_after"), 0.0) if "cash_after" in (last or {}) else 0.0
    
        if last_side == "buy":
            position = 1
            cycle_usd = last_notional  # resume "sell the same $ value"
            est_tranche_qty = last_qty
    
            # Use avg_cost if paper CSV has fee+notional, else fallback to price
            if (not a.live) and last_qty > 0 and last_notional > 0:
                entry = (last_notional + last_fee) / last_qty
            else:
                entry = last_price
    
            peak = last_price
    
            if not a.live:
                # resync paper account so it matches your last saved state
                # (requires Position import if you want to set holdings explicitly)
                account.usd = last_cash
                # If PaperAccount already has positions from earlier rows you didn't replay,
                # then this won't rebuild everything. Best is to replay the whole CSV later.
            print(f"[resume] last=BUY, entry={entry:.8f}, cycle_usd={cycle_usd}, est_qty={est_tranche_qty}")
    
        elif last_side == "sell":
            position = 0
            entry = None
            peak = None
            cycle_usd = 0.0
            est_tranche_qty = 0.0
            if not a.live:
                account.usd = last_cash
            print("[resume] last=SELL, starting flat")


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

        cfg = SwingConfig(
            buy_pct=float(a.buy_pct),
            sell_pct=float(a.sell_pct),
            trend_window=int(a.trend),
            rsi_window=int(getattr(a, "rsi_window", 14)),
            atr_window=int(getattr(a, "atr_window", 14)),
            enable_rsi=not bool(getattr(a, "no_rsi", False)),
            enable_atr=not bool(getattr(a, "no_atr", False)),
            rsi_buy=35.0,
            rsi_sell=65.0,
            atr_cap_pct=5.0,
            threshold_abs=float(getattr(a, "threshold", 0.0)),
            trail_pct=(float(a.trail) if getattr(a, "trail", None) else None),
        )
    
        strat = SwingWithTrend(cfg)
    
        mb = coin_limits.get("max_buy_price")
        ms = coin_limits.get("min_sell_price")
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
            if isinstance(sig, dict):
                sig = sig.get("signal")
            tp = None
            if position == 1 and entry is not None:
                tp = float(entry) * (1.0 + float(a.sell_pct) / 100.0)

            # entry/exit
            if sig in ("bull", "buy") and position == 0:
                ok, why = risk.allow(a.notional)
                if not ok:
                    print("blocked buy:", why)
                else:
                    trade_usd = max(a.notional, min_usd)
                    cycle_usd = trade_usd
                    qty = qty_from_usd(a.notional, p, decimals=dec)
                    if a.live:
                        out = rh.market_order(symbol, "buy", quantity=qty)
                        order_id = out.get("id") or out.get("order_id")
                    
                        filled = wait_for_fill(rh, order_id) if order_id else out
                        state = (filled.get("state") or filled.get("status") or "unknown")
                    
                        filled_qty = (
                            filled.get("filled_asset_quantity")
                            or filled.get("executed_quantity")
                            or filled.get("asset_quantity")
                            or qty
                        )
                        avg_price = filled.get("average_price") or filled.get("price") or p
                    
                        row = {
                            "ts": time.time(),
                            "symbol": symbol,
                            "side": "buy",
                            "qty": float(filled_qty) if filled_qty is not None else None,
                            "price": float(avg_price) if avg_price is not None else None,
                            "notional": (float(filled_qty) * float(avg_price)) if filled_qty and avg_price else None,
                            "order_id": order_id,
                            "state": state,
                            "note": "",
                        }
                    
                        if str(state).lower() in ("filled", "completed"):
                            est_tranche_qty = float(filled_qty)
                            append_live_csv("live_trades.csv", row)
                            cycle_qty = float(filled_qty)
                            cycle_usd = trade_usd
                            position, entry, peak = 1, float(avg_price), float(avg_price)

                    
                        trade_msg = f"BUY {symbol} qty={qty} @ {p:.8f} state={state}"
                        print(trade_msg)
                        # send_trade_email(trade_msg)
                        risk.record(trade_usd)
                                            
                    else:
                        account.buy(symbol, qty, p)
                        account.export_csv("paper_trades.csv")
                        print(f"\n(paper) BUY {symbol} qty={qty} @ {p:.8f}")
                        trade_msg = f"BUY {symbol} qty={qty} @ {p:.8f}"
                        #print(trade_msg)
                        #send_trade_email(trade_msg)
                        cycle_usd = trade_usd
                        pos = account.positions.get(symbol)
                        position, entry, peak = 1, (pos.avg_cost if pos else p), p
                        cycle_qty = qty

            elif position == 1 and (tp is not None and p >= tp) and sig in ("bear", "sell"):
                trade_usd = max(a.notional, min_usd)
                held = account.positions.get(symbol).qty if symbol in account.positions else 0.0
                target_qty = qty_from_usd(trade_usd, p, decimals=dec)
                qty = min(held, qty_from_usd(cycle_usd, p, decimals=dec))
                if a.live:
                    qty = qty_from_usd(cycle_usd, p, decimals=dec)
                    qty = min(qty, est_tranche_qty)
                    if qty <= 0:
                        print("Live SELL blocked: held_qty is 0")
                    else:
                        out = rh.market_order(symbol, "sell", quantity=qty)
                        order_id = out.get("id") or out.get("order_id")
                
                        filled = wait_for_fill(rh, order_id) if order_id else out
                        state = (filled.get("state") or filled.get("status") or "unknown")
                
                        filled_qty = (
                            filled.get("filled_asset_quantity")
                            or filled.get("executed_quantity")
                            or filled.get("asset_quantity")
                            or qty
                        )
                        avg_price = filled.get("average_price") or filled.get("price") or p
                
                        row = {
                            "ts": time.time(),
                            "symbol": symbol,
                            "side": "sell",
                            "qty": float(filled_qty) if filled_qty is not None else None,
                            "price": float(avg_price) if avg_price is not None else None,
                            "notional": (float(filled_qty) * float(avg_price)) if filled_qty and avg_price else None,
                            "order_id": order_id,
                            "state": state,
                            "note": "",
                        }
                
                        if str(state).lower() in ("filled", "completed"):
                            append_live_csv("live_trades.csv", row)
                            cycle_qty = 0.0
                            est_tranche_qty = 0.0
                            cycle_usd = 0.0
                            position, entry, peak = 0, None, None
                
                        trade_msg = f"SELL {symbol} qty={qty} @ {p:.8f} state={state}"
                        print(trade_msg)
                    
                else:
                    trade_usd = max(a.notional, min_usd)
                    target_qty = qty_from_usd(trade_usd, p, decimals=dec)
                    held = account.positions.get(symbol).qty if symbol in account.positions else 0.0
                    qty = min(held, qty_from_usd(cycle_usd, p, decimals=dec))
                    account.sell(symbol, qty, p)
                    print(f"\n(paper) SELL {symbol} qty={qty} @ {p:.8f}")
                    trade_msg = f"SELL {symbol} qty={qty} @ {p:.8f}"                   
                    #send_trade_email(trade_msg)
                    account.export_csv("paper_trades.csv")
                    cycle_qty = 0.0
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










































