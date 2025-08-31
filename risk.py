# risk.py
import time

class Risk:
    def __init__(self, max_per_order=5.0, max_daily=25.0, cooldown=60, trail_pct=0.8):
        self.max_per_order = float(max_per_order)
        self.max_daily = float(max_daily)
        self.cooldown = int(cooldown)
        self.trail_pct = float(trail_pct)  # e.g., 0.8% trailing stop
        self._day = time.strftime("%Y-%m-%d")
        self._spent = 0.0
        self._last_ts = 0.0

    def new_day_if_needed(self):
        d = time.strftime("%Y-%m-%d")
        if d != self._day:
            self._day, self._spent = d, 0.0

    def allow(self, notional: float):
        self.new_day_if_needed()
        if notional > self.max_per_order:
            return False, "per-order cap"
        if self._spent + notional > self.max_daily:
            return False, "daily cap"
        if time.time() - self._last_ts < self.cooldown:
            return False, "cooldown"
        return True, ""

    def record(self, notional: float):
        self._last_ts = time.time()
        self._spent += notional
