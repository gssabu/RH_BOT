# strategy.py
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Optional, Dict, Any

# -------- Simple SMA crossover (utility / baseline) --------
class SMAStrategy:
    def __init__(self, short: int = 5, long: int = 20):
        if short >= long:
            raise ValueError("short must be < long")
        self.s = deque(maxlen=short)
        self.l = deque(maxlen=long)
        self._prev_cross: Optional[int] = None  # -1 below, +1 above

    def update(self, price: float) -> Optional[str]:
        self.s.append(price); self.l.append(price)
        if len(self.l) < self.l.maxlen:
            return None
        sp = sum(self.s) / len(self.s)
        lp = sum(self.l) / len(self.l)
        cross = 1 if sp >= lp else -1
        if self._prev_cross is None:
            self._prev_cross = cross
            return None
        signal = None
        if self._prev_cross == -1 and cross == 1:
            signal = "buy"
        elif self._prev_cross == 1 and cross == -1:
            signal = "sell"
        self._prev_cross = cross
        return signal

# -------- RSI (Wilder) --------
class RSICalc:
    def __init__(self, window: int = 14):
        if window <= 0:
            raise ValueError("window must be > 0")
        self.window = window
        self.prev: Optional[float] = None
        self.gains: deque = deque()
        self.losses: deque = deque()

    def update(self, price: float) -> Optional[float]:
        if self.prev is None:
            self.prev = price
            return None
        delta = price - self.prev
        self.prev = price
        self.gains.append(max(delta, 0.0))
        self.losses.append(abs(min(delta, 0.0)))
        if len(self.gains) > self.window:
            self.gains.popleft(); self.losses.popleft()
        if len(self.gains) < self.window:
            return None
        avg_gain = sum(self.gains) / self.window
        avg_loss = sum(self.losses) / self.window
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

# -------- ATR proxy (close-to-close) --------
class ATRLite:
    """
    Simplified ATR proxy using |close_t - close_(t-1)| averaged over N.
    Not a full true-range, but good enough for a volatility gate.
    """
    def __init__(self, window: int = 14):
        if window <= 0:
            raise ValueError("window must be > 0")
        self.window = window
        self.prev: Optional[float] = None
        self.moves: deque = deque(maxlen=window)

    def update(self, price: float) -> Optional[float]:
        if self.prev is None:
            self.prev = price
            return None
        self.moves.append(abs(price - self.prev))
        self.prev = price
        if len(self.moves) < self.window:
            return None
        return sum(self.moves) / len(self.moves)

# -------- Swing-with-Trend --------
@dataclass
class SwingConfig:
    buy_pct: float        # e.g., 2 => buy when price <= SMA * (1 - 0.02)
    sell_pct: float       # e.g., 4 => sell when price >= SMA * (1 + 0.04)
    trend_window: int     # SMA window for trend anchor
    rsi_window: int = 14
    atr_window: int = 14
    enable_rsi: bool = True
    enable_atr: bool = True
    rsi_buy: float = 35.0
    rsi_sell: float = 65.0
    atr_cap_pct: float = 5.0     # trade disabled if ATR% > this (percent of price)
    threshold_abs: float = 0.0   # ignore ticks smaller than this absolute change
    trail_pct: Optional[float] = None  # track high-water and block sells below (percent drop)

class SwingWithTrend:
    """
    Mean-reversion around a trend SMA, gated by RSI and ATR (both optional).
    Emits dicts like: {"signal":"buy","reason":"below_band","sma":..., "rsi":..., "atr_pct":..., "dev_pct":...}
    """
    def __init__(self, cfg: SwingConfig):
        if cfg.trend_window <= 1:
            raise ValueError("trend_window must be > 1")
        self.cfg = cfg
        self.prices = deque(maxlen=cfg.trend_window)
        self.rsi = RSICalc(cfg.rsi_window) if cfg.enable_rsi else None
        self.atr = ATRLite(cfg.atr_window) if cfg.enable_atr else None
        self.prev_price: Optional[float] = None
        self.high_water: Optional[float] = None  # for optional trailing logic

    def _trend_sma(self) -> Optional[float]:
        if len(self.prices) < self.prices.maxlen:
            return None
        return sum(self.prices) / len(self.prices)

    def update(self, price: float) -> Optional[Dict[str, Any]]:
        # threshold filter on raw ticks
        if self.prev_price is not None and self.cfg.threshold_abs > 0:
            if abs(price - self.prev_price) < self.cfg.threshold_abs:
                return None
        self.prev_price = price

        self.prices.append(price)
        sma = self._trend_sma()
        if sma is None or sma <= 0:
            # Warm-up
            if self.rsi: self.rsi.update(price)
            if self.atr: self.atr.update(price)
            return None

        # deviation from SMA in percent
        dev_pct = (price / sma - 1.0) * 100.0

        # optional RSI/ATR gates
        rsi_val = self.rsi.update(price) if self.rsi else None
        atr_val = self.atr.update(price) if self.atr else None
        atr_pct = (atr_val / price * 100.0) if (atr_val is not None and price > 0) else None

        if self.cfg.enable_atr and (atr_pct is None or atr_pct > self.cfg.atr_cap_pct):
            return None  # too volatile (or not enough ATR yet)

        # Trailing high-water (sell guard), if configured
        if self.cfg.trail_pct is not None:
            if self.high_water is None or price > self.high_water:
                self.high_water = price
            # If price drops more than trail_pct from high_water, prefer sell
            if self.high_water and price <= self.high_water * (1.0 - self.cfg.trail_pct / 100.0):
                return {"signal": "sell", "reason": "trail_stop", "sma": sma, "rsi": rsi_val, "atr_pct": atr_pct, "dev_pct": dev_pct}

        # Core swing logic around SMA bands
        want_buy = dev_pct <= -float(self.cfg.buy_pct)
        want_sell = dev_pct >=  float(self.cfg.sell_pct)

        # Apply RSI gates if enabled
        if self.cfg.enable_rsi and rsi_val is not None:
            if want_buy and not (rsi_val <= self.cfg.rsi_buy):
                want_buy = False
            if want_sell and not (rsi_val >= self.cfg.rsi_sell):
                want_sell = False

        # Prefer sell over buy if both somehow true
        if want_sell:
            return {"signal": "sell", "reason": "above_band", "sma": sma, "rsi": rsi_val, "atr_pct": atr_pct, "dev_pct": dev_pct}
        if want_buy:
            return {"signal": "buy", "reason": "below_band", "sma": sma, "rsi": rsi_val, "atr_pct": atr_pct, "dev_pct": dev_pct}

        return None
