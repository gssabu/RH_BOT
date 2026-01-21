# paper_account.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List
import time
import os
import csv

@dataclass
class Position:
    qty: float = 0.0
    avg_cost: float = 0.0  # USD per unit, includes buy-fee in cost basis

@dataclass
class Fill:
    ts: float
    symbol: str
    side: str          # "buy" or "sell"
    qty: float
    price: float
    fee: float
    notional: float    # qty * price
    realized_pnl: float = 0.0
    cash_after: float = 0.0

def _csv_escape(v):
    if v is None:
        return ""
    s = str(v)
    # quote if needed
    if any(c in s for c in [",", '"', "\n"]):
        s = '"' + s.replace('"', '""') + '"'
    return s
        
class PaperAccount:
    def __init__(self, starting_usd: float = 10000.0, fee_bps: int = 35):
        self.usd: float = float(starting_usd)
        self.fee_bps: int = int(fee_bps)
        self.positions: Dict[str, Position] = {}
        self.history: List[Dict] = []
        self.realized_pnl_total: float = 0.0
        self.wins: int = 0
        self.losses: int = 0

    # --- helpers ---
    def _fee(self, notional: float) -> float:
        return round(notional * self.fee_bps / 10_000.0, 8)

    def _pos(self, symbol: str) -> Position:
        return self.positions.setdefault(symbol, Position())

    def qty_held(self, symbol: str) -> float:
        return self.positions.get(symbol, Position()).qty

    # --- public API ---
    def buy(self, symbol: str, qty: float, price: float) -> bool:
        if qty <= 0 or price <= 0:
            return False
        notional = qty * price
        fee = self._fee(notional)
        total_cost = notional + fee
        if total_cost > self.usd + 1e-12:
            return False  # insufficient cash

        # update cash
        self.usd -= total_cost

        # update position (avg_cost includes buy fee via total_cost)
        p = self._pos(symbol)
        new_qty = p.qty + qty
        if new_qty <= 0:
            p.qty, p.avg_cost = 0.0, 0.0
        else:
            p.avg_cost = ((p.qty * p.avg_cost) + total_cost) / new_qty
            p.qty = new_qty

        self._record(symbol, "buy", qty, price, fee, notional, realized=0.0)
        return True

    def sell(self, symbol: str, qty: float, price: float) -> bool:
        if qty <= 0 or price <= 0:
            return False
        p = self._pos(symbol)
        # cap to held qty
        qty = min(qty, p.qty)
        if qty <= 0:
            return False

        notional = qty * price
        fee = self._fee(notional)
        proceeds = notional - fee

        # realized PnL uses avg_cost that includes buy fees
        realized = (price - p.avg_cost) * qty - fee
        self.realized_pnl_total += realized
        if realized >= 0:
            self.wins += 1
        else:
            self.losses += 1

        # update cash and position
        self.usd += proceeds
        p.qty -= qty
        if p.qty <= 1e-12:
            p.qty, p.avg_cost = 0.0, 0.0  # flat

        self._record(symbol, "sell", qty, price, fee, notional, realized=realized)
        return True

    def equity(self, marks: Dict[str, float]) -> float:
        value = self.usd
        for sym, pos in self.positions.items():
            if pos.qty > 0 and sym in marks and marks[sym] > 0:
                value += pos.qty * float(marks[sym])
        return round(value, 8)

    def stats(self) -> Dict:
        total_trades = self.wins + self.losses
        win_rate = (self.wins / total_trades) * 100.0 if total_trades else 0.0
        return {
            "cash_usd": round(self.usd, 8),
            "realized_pnl_total": round(self.realized_pnl_total, 8),
            "wins": self.wins,
            "losses": self.losses,
            "win_rate_pct": round(win_rate, 2),
            "positions": {k: asdict(v) for k, v in self.positions.items()},
        }

    def qty_held(self, symbol: str) -> float:
        p = self.positions.get(symbol)
        return 0.0 if p is None else float(p.qty)
    
    def set_csv(self, path: str):
        self.csv_path = path
    
    
    def _append_csv_row(self, row: dict):
        path = getattr(self, "csv_path", None)
        if not path:
            return
    
        cols = [
            ("ts", "TS"),
            ("symbol", "SYMBOL"),
            ("side", "SIDE"),
            ("qty", "QTY"),
            ("price", "PRICE"),
            ("fee", "FEE"),
            ("notional", "NOTIONAL"),
            ("realized_pnl", "REALIZED_PNL"),
            ("cash_after", "BALANCE"),
        ]
    
        new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    
        with open(path, "a", newline="") as f:
            if new_file:
                f.write(", ".join(h for _, h in cols) + "\n")
    
            line = ", ".join(_csv_escape(row.get(k)) for k, _ in cols) + "\n"
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
    
    def export_csv(self, path: str = "paper_trades.csv"):
        cols = [
            ("ts", "TS"),
            ("symbol", "SYMBOL"),
            ("side", "SIDE"),
            ("qty", "QTY"),
            ("price", "PRICE"),
            ("fee", "FEE"),
            ("notional", "NOTIONAL"),
            ("realized_pnl", "REALIZED_PNL"),
            ("cash_after", "BALANCE"),
        ]
    
        tmp = path + ".tmp"
        with open(tmp, "w", newline="") as f:
            f.write(", ".join(h for _, h in cols) + "\n")
            for row in self.history:
                f.write(", ".join(_csv_escape(row.get(k)) for k, _ in cols) + "\n")
            f.flush()
            os.fsync(f.fileno())
    
        os.replace(tmp, path)
        return path


    # --- internals ---
    def _record(self, symbol, side, qty, price, fee, notional, realized):
        rec = Fill(
            ts=time.time(),
            symbol=symbol,
            side=side,
            qty=round(qty, 12),
            price=round(price, 12),
            fee=round(fee, 3),
            notional=round(notional, 3),
            realized_pnl=round(realized, 3),
            cash_after=round(self.usd, 2),
        )
        self.history.append(asdict(rec))
        self._append_csv_row(asdict(rec))









